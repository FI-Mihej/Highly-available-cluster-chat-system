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
        self.messages = ['message {}'.format(message_number) for message_number in range(3)]

    def on_connect(self):
        print('on_connection. ID: {}'.format(self.connection.connection_id))
        sockname = self.connection.conn.getsockname()
        peername = None
        if ConnectionType.passive == self.connection.connection_info.connection_type:
            print('passive on {}'.format(sockname))
        else:
            if ConnectionState.connected == self.connection.connection_state:
                peername = self.connection.conn.getpeername()
            print('active from {} to {}'.format(sockname, peername))
        print()
        self.send_another_message()

    def on_read(self):
        print('on_read')
        try:
            while True:
                message, remaining_data = get_message(self.connection.read_data)
                self.connection.read_data = remaining_data
                print('IN: "{}"'.format(message))
        except ThereIsNoMessages:
            print()
            return

    def on_no_more_data_to_write(self):
        print('on_no_more_data_to_write')
        print()
        self.send_another_message()

    def on_connection_lost(self):
        print('on_connection_lost. ID: {}'.format(self.connection.connection_id))
        self.api.stop()

    def __copy__(self):
        print("__copy__")
        return type(self)()

    def send_another_message(self):
        if not self.messages:
            return

        message = self.messages[0]
        self.messages = self.messages[1:]

        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.add_must_be_written_data(packed_message)


class Client():
    def __init__(self, server_address):
        super().__init__()
        self.server_address = server_address

    def run(self):
        io = NetIO(IOMethodEpollLT)
        with net_io(io) as io:
            worker_for_server_connection = MainWorker()
            main_server_connection_info = ConnectionInfo(worker_for_server_connection,
                                                         ConnectionType.active_connected,
                                                         self.server_address)
            io.make_connection(main_server_connection_info)


def main():
    server_address = ('localhost', 9090)
    client = Client(server_address)
    client.run()

if __name__ == '__main__':
    main()
