from net_io__linux import *
from net_io_method__epoll_lt import *
from transport_protocol import *
from server_list_loader import load_server_list
from transport_protocol_constants import *
import marshal
import sys
from threading import Thread, Lock
from multiprocessing import Process
from random import randint

"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


class GlobalDataForAllWorkers:
    def __init__(self):
        self.all_servers_list = list()
        self.clients_per_server = None

        self.need_to_exit = False
        self.lock_for__need_to_exit = Lock()

        self.input_messages = list()
        self.lock_for__input_messages = Lock()


class MainWorker(WorkerBase):
    def __init__(self, global_data: GlobalDataForAllWorkers):
        super().__init__()
        self.global_data = global_data
        self.server_address = None
        self.connected_to_destination_server = False
        self.is_normal_reconnection = False

    def on_connect(self):
        if self.global_data.clients_per_server:
            self.connected_to_destination_server = True
            print('CONNECTED TO SERVER ({})'.format(self.server_address))
            print()
        else:
            self.send_request__give_me_clients_per_server()

    def on_read(self):
        try:
            while True:
                message, remaining_data = get_message(self.connection.read_data)
                self.connection.read_data = remaining_data
                self.message_handler(message)
        except ThereIsNoMessages:
            return

    def on_no_more_data_to_write(self):
        if self.connected_to_destination_server:
            with self.global_data.lock_for__input_messages:
                for string in self.global_data.input_messages:
                    self.send_request__client_string(string)

            with self.global_data.lock_for__need_to_exit:
                if self.global_data.need_to_exit:
                    self.api.stop()

    def on_connection_lost(self):
        print('CONNECTION TO THE SERVER ({}) IS LOST'.format(self.server_address))
        print()

        self.connected_to_destination_server = False
        server_address = None
        if self.global_data.clients_per_server:
            # try to reconnect to next best server
            if not self.is_normal_reconnection:
                del self.global_data.clients_per_server[self.server_address]
            server_address = min(self.global_data.clients_per_server, key=self.global_data.clients_per_server.get)
            print('TRYING TO RECONNECT TO THE BEST SERVER ({})'.format(server_address))
            print()
        else:
            # try to reconnect to random server
            server_number = randint(0, len(self.global_data.all_servers_list) - 1)
            server_address = self.global_data.all_servers_list[server_number]
            print('TRYING TO RECONNECT TO THE RANDOM SERVER ({})'.format(server_address))
            print()
        self.make_connection_to_the_server(server_address)

    def __copy__(self):
        return type(self)(self.global_data)

    def make_connection_to_the_server(self, server_address):
        worker_for_server_connection = MainWorker(self.global_data)
        worker_for_server_connection.server_address = server_address
        main_server_connection_info = ConnectionInfo(worker_for_server_connection,
                                                     ConnectionType.active_connected,
                                                     server_address)
        self.api.make_connection(main_server_connection_info)

    def send_request__give_me_clients_per_server(self):
        message = {
            FieldName.name: RPCName.give_me_clients_per_server,
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.must_be_written_data += packed_message

    def send_request__client_string(self, string: str):
        message = {
            FieldName.name: RPCName.client_string,
            FieldName.string: string
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.must_be_written_data += packed_message

    def message_handler(self, message: bytes):
        message = marshal.loads(message)
        if RPCName.clients_per_server == message[FieldName.name]:
            self.global_data.clients_per_server = message[FieldName.clients_per_server]
            server_address = min(self.global_data.clients_per_server, key=self.global_data.clients_per_server.get)
            if server_address != self.server_address:
                self.is_normal_reconnection = True
                self.api.remove_connection(self.connection)
        elif RPCName.print_string == message[FieldName.name]:
            string = message[FieldName.string]
            print('IN: "{}"'.format(string))


class ConsoleInputThread(Thread):
    def __init__(self, global_data: GlobalDataForAllWorkers):
        super().__init__()
        self.global_data = global_data
        self.exit_phrase = 'exit'

    def run(self):
        print()
        print('ENTER \'{}\' TO EXIT'.format(self.exit_phrase))
        print()

        while True:
            new_string = input()
            if self.exit_phrase == new_string:
                with self.global_data.lock_for__need_to_exit:
                    self.global_data.need_to_exit = True
                break
            with self.global_data.lock_for__input_messages:
                self.global_data.input_messages.append(new_string)


class Client(Process):
    def __init__(self, all_servers_list: list=None):
        super().__init__()
        self.all_servers_list = all_servers_list
        if self.all_servers_list is None:
            self.all_servers_list = load_server_list()

        self.global_data = GlobalDataForAllWorkers()
        self.global_data.all_servers_list = self.all_servers_list

    def run(self):
        input_thread = ConsoleInputThread(self.global_data)
        input_thread.daemon = True
        input_thread.start()

        io = NetIO(IOMethodEpollLT)
        with net_io(io) as io:
            server_number = randint(0, len(self.all_servers_list) - 1)
            server_address = self.all_servers_list[server_number]
            print('TRYING TO CONNECT TO THE RANDOM SERVER ({})'.format(server_address))
            print()
            worker_for_server_connection = MainWorker(self.global_data)
            worker_for_server_connection.server_address = server_address
            main_server_connection_info = ConnectionInfo(worker_for_server_connection,
                                                         ConnectionType.active_connected,
                                                         server_address)
            io.make_connection(main_server_connection_info)


def main():
    all_server_list = load_server_list()
    client = Client(all_server_list)
    client.run()

if __name__ == '__main__':
    main()
