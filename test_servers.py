from net_io__linux import *
from net_io_method__epoll_lt import *
from transport_protocol import *
from server_list_loader import load_server_list
from transport_protocol_constants import *
import marshal
import sys


"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


class MainWorker(WorkerBase):
    def __init__(self):
        print('__init__')
        super().__init__()

    def on_connect(self):
        print('on_connection')
        sockname = self.connection.conn.getsockname()
        peername = None
        if ConnectionType.passive == self.connection.connection_info.connection_type:
            print('passive on {}'.format(sockname))
        else:
            if ConnectionState.connected == self.connection.connection_state:
                peername = self.connection.conn.getpeername()
            print('active from {} to {}'.format(sockname, peername))
        print()

    def on_read(self):
        print('on_read')
        try:
            while True:
                message, remaining_data = get_message(self.connection.read_data)
                self.connection.read_data = remaining_data
                message = marshal.loads(message)
                print('IN: "{}"'.format(message))
        except ThereIsNoMessages:
            print()
            return

    def on_no_more_data_to_write(self):
        print('on_no_more_data_to_write')
        print()

    def on_connection_lost(self):
        print('on_connection_lost')

    def __copy__(self):
        print("__copy__")
        return type(self)()


class Server:
    def __init__(self, own_server_address):
        super().__init__()
        self.own_server_address = own_server_address

    def run(self):
        io = NetIO(IOMethodEpollLT)
        with net_io(io) as io:
            worker_for_main_passive_socket = MainWorker()
            main_passive_connection_info = ConnectionInfo(worker_for_main_passive_socket,
                                                          ConnectionType.passive,
                                                          self.own_server_address,
                                                          backlog=10)
            io.make_connection(main_passive_connection_info, 'server')


def main():
    own_address = ('localhost', 9090)
    server = Server(own_address)
    server.run()

if __name__ == '__main__':
    main()
