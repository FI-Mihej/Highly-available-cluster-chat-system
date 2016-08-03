import socket
import select
import errno
import copy
import enum

from tornado.platform.select import _Select

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
        return WorkerBase(self.api, self.connection)


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

    def make_connection(self, connection_info: ConnectionInfo = None, name=None):
        raise NotImplemented

    def add_connection(self, connection: Connection):
        raise NotImplemented

    def remove_connection(self, connection: Connection):
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


class NetIO(NetIOBase):
    def __init__(self, transport):
        super().__init__()
        self.method = transport(self)
        self.method = IOMethodBase(self)

        self._need_to_stop = False
        self._already_begun = False

        self._new_connection_id = 0

    def destroy(self):
        self.method.destroy()

    def start(self):
        if self._already_begun:
            raise LoopIsAlreadyBegun()

        self._already_begun = True
        try:
            while not self._need_to_stop:
                self.method.loop_iteration()
        finally:
            self._already_begun = False
            self.destroy()

    def stop(self):
        self._need_to_stop = True

    def make_connection(self, connection_info: ConnectionInfo=None, name=None):
        if ConnectionType.passive == connection_info.connection_type:
            self._make_passive_connection(connection_info, name)
        elif ConnectionType.active_connected == connection_info.connection_type:
            self._make_active_connected_connection(connection_info, name)
        else:
            raise WrongConnectionType()

    def add_connection(self, connection: Connection):
        self.all_connections.add(connection)
        if ConnectionType.passive == connection.connection_info.connection_type:
            self.passive_connections.add(connection)
        self.connection_by_id[connection.connection_id] = connection
        if connection.connection_name is not None:
            self.connection_by_name[connection.connection_name] = connection
        self.connection_by_fileno[connection.conn.fileno()] = connection

        if connection.worker_obj.api is None:
            connection.worker_obj.api = self
        if connection.worker_obj.connection is None:
            connection.worker_obj.connection = connection
            
        self.method.add_connection(connection.conn)
        self._check_is_connection_need_to_sent_data(connection)

    def remove_connection(self, connection: Connection):
        connection.connection_state = ConnectionState.waiting_for_disconnection
        self.method.set__should_be_closed(connection.conn)

    def on_accept_connection(self, connection):
        new_conn = None
        try:
            conn_and_address_pair = connection.conn.accept()
            new_conn, new_address = conn_and_address_pair
            new_connection = self._construct_active_accepted_connection(connection, conn_and_address_pair)
            self.add_connection(new_connection)
            try:
                new_connection.worker_obj.on_connect()
                self._check_is_connection_need_to_sent_data(new_connection)
            except:
                self._set_connection_to_be_closed(new_connection, ConnectionState.worker_fault)
        except BlockingIOError:
            pass
        except:
            if new_conn is not None:
                self.method.should_be_closed.add(new_conn)

    def on_connected(self, connection: Connection):
        connection.connection_state = ConnectionState.connected
        try:
            connection.worker_obj.on_connect()
            self._check_is_connection_need_to_sent_data(connection)
        except:
            self._set_connection_to_be_closed(connection, ConnectionState.worker_fault)

    def on_read(self, connection: Connection):
        try:
            another_read_data_part = connection.conn.recv(1024)
            if another_read_data_part:
                connection.read_data += another_read_data_part
                try:
                    connection.worker_obj.on_read()
                    self._check_is_connection_need_to_sent_data(connection)
                except:
                    self._set_connection_to_be_closed(connection, ConnectionState.worker_fault)
            else:
                self._set_connection_to_be_closed(connection, ConnectionState.io_fault)
        except BlockingIOError:
            pass
        except:
            self._set_connection_to_be_closed(connection, ConnectionState.io_fault)

    def on_write(self, connection: Connection):
        try:
            nsent = connection.conn.send(connection.must_be_written_data)
            connection.must_be_written_data = connection.must_be_written_data[nsent:]
            if not connection.must_be_written_data:
                try:
                    connection.worker_obj.on_no_more_data_to_write()
                    self._check_is_connection_need_to_sent_data(connection)
                except:
                    self._set_connection_to_be_closed(connection, ConnectionState.worker_fault)
        except BlockingIOError:
            pass
        except:
            self._set_connection_to_be_closed(connection, ConnectionState.io_fault)

    def on_close(self, connection: Connection):
        self._remove_connection_from_internal_structures(connection)
        connection.conn.close()
        connection.connection_state = ConnectionState.disconnected
        try:
            connection.worker_obj.on_connection_lost()
        except:
            pass

    def _get_new_connection_id(self):
        result = self._new_connection_id
        self._new_connection_id += 1
        return result

    def _construct_active_accepted_connection(self, base_passive_connection: Connection,
                                              conn_and_address_pair: tuple):
        conn, address = conn_and_address_pair
        new_connection_info = ConnectionInfo(copy.copy(base_passive_connection.worker_obj),
                                             ConnectionType.active_accepted,
                                             address, conn.family, conn.type, conn.proto)
        new_connection = Connection(self._get_new_connection_id(), new_connection_info, conn_and_address_pair,
                                    ConnectionState.connected)
        return new_connection

    def _make_active_connected_connection(self, connection_info: ConnectionInfo=None, name=None)->Connection:
        conn = None
        try:
            conn = socket.socket(connection_info.socket_family, connection_info.socket_type,
                                 connection_info.socket_protocol, connection_info.socket_fileno)
            conn.setblocking(0)
            conn.connect(connection_info.socket_address)
        except (socket.error, OSError) as err:
            if err.errno not in {errno.EINPROGRESS, errno.EAGAIN}:
                conn.close()
                raise err
        conn_and_address_pair = (conn, connection_info.socket_address)
        new_connection = Connection(self._get_new_connection_id(), connection_info, conn_and_address_pair,
                                    ConnectionState.waiting_for_connection, name)
        self.add_connection(new_connection)
        self.method.set__need_write(new_connection.conn, True)

    def _make_passive_connection(self, connection_info: ConnectionInfo=None, name=None)->Connection:
        conn = None
        try:
            conn = socket.socket(connection_info.socket_family, connection_info.socket_type,
                                 connection_info.socket_protocol, connection_info.socket_fileno)
            conn.setblocking(0)
            conn.bind(connection_info.socket_address)
            conn.listen(connection_info.backlog)
        except:
            conn.close()
            raise
        conn_and_address_pair = (conn, connection_info.socket_address)
        new_connection = Connection(self._get_new_connection_id(), connection_info, conn_and_address_pair,
                                    ConnectionState.connected, name)
        self.add_connection(new_connection)

    def _remove_connection_from_internal_structures(self, connection: Connection):
        if connection in self.all_connections:
            self.all_connections.remove(connection)
        if connection in self.passive_connections:
            self.passive_connections.remove(connection)
        if connection.connection_id in self.connection_by_id:
            del self.connection_by_id[connection.connection_id]
        if connection.connection_name is not None:
            if connection.connection_name in self.connection_by_name:
                del self.connection_by_name[connection.connection_name]
        if connection.conn.fileno() in self.connection_by_fileno:
            del self.connection_by_fileno[connection.conn.fileno()]
        self.method.remove_connection(connection.conn)

    def _set_connection_to_be_closed(self, connection: Connection, state: ConnectionState):
        connection.connection_state = state
        self.method.set__should_be_closed(connection.conn)

    def _check_is_connection_need_to_sent_data(self, connection: Connection):
        if connection.must_be_written_data:
            if not isinstance(connection.must_be_written_data, memoryview):
                connection.must_be_written_data = memoryview(connection.must_be_written_data)
            self.method.set__need_write(connection.conn, True)
        else:
            self.method.set__need_write(connection.conn, False)


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


class IOMethodEpollLT(IOMethodBase):
    def __init__(self, interface: NetIO):
        super().__init__(interface)
        self.epoll = select.epoll()

    def loop_iteration(self):
        events = self.epoll.poll(1)
        for fileno, event in events:
            connection = self.interface.connection_by_fileno[fileno]

            if event & select.EPOLLIN:
                # Read available. We can try to read even even if an error occurred
                if ConnectionType.passive == connection.connection_info.connection_type:
                    self.interface.on_accept_connection(connection)
                else:
                    self.interface.on_read(connection)

            if event & select.EPOLLHUP:
                # Some error. Close connection
                self.should_be_closed.add(connection.conn)
            elif event & select.EPOLLOUT:
                # Write available. We will not write data if an error occurred
                if ConnectionState.waiting_for_connection == connection.connection_state:
                    if not connection.conn.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                        # Connected successfully:
                        self.interface.on_connected(connection)
                    else:
                        # Some connection error - will be closed:
                        self.should_be_closed.add(connection.conn)
                else:
                    self.interface.on_write(connection)

            self._close_all()

    def _close_all(self):
        for conn in self.should_be_closed:
            if conn.fileno() in self.interface.connection_by_fileno:
                connection = self.interface.connection_by_fileno[conn.fileno()]
                self.interface.on_close(connection)
            else:
                self.remove_connection(conn)
        if self.should_be_closed:
            self.should_be_closed = set()

    def destroy(self):
        self._close_all()
        self.epoll.close()

    def add_connection(self, conn: socket.socket):
        self.epoll.register(conn.fileno(), select.EPOLLIN)

    def remove_connection(self, conn: socket.socket):
        self.epoll.unregister(conn.fileno())

    def set__need_write(self, conn: socket.socket, state=True):
        if state:
            self.epoll.modify(conn.fileno(), select.EPOLLIN | select.EPOLLOUT)
        else:
            self.epoll.modify(conn.fileno(), select.EPOLLIN)

    def set__should_be_closed(self, conn: socket.socket):
        self.should_be_closed.add(conn)
