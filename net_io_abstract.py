import socket
import errno
import copy
import enum

"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


class LoopIsAlreadyBegun(Exception):
    pass


class WrongConnectionType(Exception):
    pass


class CanNotMakeConnection(Exception):
    pass


class ConnectionType(enum.Enum):
    passive = 0
    active_accepted = 1
    active_connected = 2


class ConnectionState(enum.Enum):
    not_connected_yet = 0
    waiting_for_connection = 1
    connected = 2
    worker_fault = 3
    io_fault = 4
    waiting_for_disconnection = 5
    disconnected = 6


class WorkerBase:
    def __init__(self, api: NetIOUserApi=None, connection: Connection=None):
        self.api = api
        self.connection = connection

    def on_connect(self):
        pass

    def on_read(self):
        pass

    def on_no_more_data_to_write(self):
        pass

    def on_connection_lost(self):
        pass

    def __copy__(self):
        raise NotImplemented


class ConnectionInfo:
    def __init__(self,
                 worker_obj: WorkerBase,
                 connection_type: ConnectionType,
                 socket_address=None,
                 socket_family=socket.AF_INET,
                 socket_type=socket.SOCK_STREAM,
                 socket_protocol=0,
                 socket_fileno=None,
                 backlog=0):
        '''
        :param worker_obj: constructed worker object. If this is a passive connection - it will be inherited by the
            descendant active_accepted connections by copy.copy() call
        :param connection_type: see ConnectionType() description
        :param socket_address:  see socket.bind()/socket.connect() docs
        :param socket_family: see socket.socket() docs
        :param socket_type: see socket.socket() docs
        :param socket_protocol: see socket.socket() docs
        :param socket_fileno: see socket.socket() docs
        :param backlog: see socket.listen() docs
        '''
        self.worker_obj = worker_obj
        self.connection_type = connection_type
        self.socket_address = socket_address
        self.socket_family = socket_family
        self.socket_type = socket_type
        self.socket_protocol = socket_protocol
        self.socket_fileno = socket_fileno
        self.backlog = backlog


class Connection:
    def __init__(self,
                 connection_id,
                 connection_info: ConnectionInfo,
                 connection_and_address_pair: tuple,
                 connection_state: ConnectionState,
                 connection_name=None,
                 ):
        self.connection_id = connection_id
        self.connection_info = connection_info
        self.conn, self.address = connection_and_address_pair
        self.connection_state = connection_state
        self.connection_name = connection_name
        self.worker_obj = connection_info.worker_obj
        self.read_data = b''  # already read data
        self.must_be_written_data = memoryview(b'')  # this data should be written


class NetIOUserApi:
    def __init__(self):
        super().__init__()
        self.all_connections = set()
        self.passive_connections = set()

        self.connection_by_id = dict()
        self.connection_by_name = dict()
        self.connection_by_fileno = dict()

    def start(self):
        raise NotImplemented

    def stop(self):
        raise NotImplemented

    def make_connection(self, connection_info: ConnectionInfo = None, name=None)->Connection:
        raise NotImplemented

    def add_connection(self, connection: Connection):
        raise NotImplemented

    def remove_connection(self, connection: Connection):
        raise NotImplemented

    def check_is_connection_need_to_sent_data(self, connection: Connection):
        raise NotImplemented


class NetIOCallbacks:
    def __init__(self):
        super().__init__()

    def on_accept_connection(self, connection: Connection):
        raise NotImplemented

    def on_connected(self, connection: Connection):
        raise NotImplemented

    def on_read(self, connection: Connection):
        raise NotImplemented

    def on_write(self, connection: Connection):
        raise NotImplemented

    def on_close(self, connection: Connection):
        raise NotImplemented


class NetIOBase(NetIOUserApi, NetIOCallbacks):
    def __init__(self):
        super().__init__()

    def destroy(self):
        raise NotImplemented


class IOMethodBase:
    def __init__(self, interface: NetIOBase):
        self.interface = interface
        self.should_be_closed = set()
        pass

    def loop_iteration(self):
        raise NotImplemented

    def destroy(self):
        raise NotImplemented

    def set__can_read(self, conn: socket.socket, state=True):
        raise NotImplemented

    def set__need_write(self, conn: socket.socket, state=True):
        raise NotImplemented

    def set__should_be_closed(self, conn: socket.socket):
        raise NotImplemented

    def add_connection(self, conn: socket.socket):
        raise NotImplemented

    def remove_connection(self, conn: socket.socket):
        raise NotImplemented
