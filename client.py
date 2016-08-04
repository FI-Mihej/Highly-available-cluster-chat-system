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
        print('__init__')
        super().__init__()
        self.global_data = global_data
        self.server_address = None
        self.connected_to_destination_server = False
        self.is_normal_reconnection = False

        self.input_rpc_handlers = dict()
        self.prepare_input_rpc_handlers()

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

        if self.global_data.clients_per_server:
            # already got clients_per_server dict. This means that we currently already connected to best server.
            # We can start working now
            self.process__on_connect__already_got_clients_per_server_dict()
        else:
            # need to get clients_per_server dict from current (random) server
            self.process__on_connect__still_need_to_get_clients_per_server_dict()

    def on_read(self):
        print('on_read')
        try:
            while True:
                message, remaining_data = get_message(self.connection.read_data)
                self.connection.read_data = remaining_data
                self.input_message_handler(message)
        except ThereIsNoMessages:
            return

    def on_no_more_data_to_write(self):
        # print('on_no_more_data_to_write')
        if self.connected_to_destination_server:
            # server has send all data, so we ned to check user input for some new strings
            with self.global_data.lock_for__input_messages:
                if self.global_data.input_messages:
                    for string in self.global_data.input_messages:
                        self.send_request__client_string(string)
                    self.global_data.input_messages = list()

            with self.global_data.lock_for__need_to_exit:
                if self.global_data.need_to_exit:
                    self.api.stop()

    def on_connection_lost(self):
        print('on_connection_lost. ID: {}; Address: {}'.format(
            self.connection.connection_id, self.connection.connection_info.socket_address))
        # print('CONNECTION TO THE SERVER ({}) IS LOST'.format(self.server_address))
        # print()

        self.connected_to_destination_server = False
        server_address = None
        if self.global_data.clients_per_server:
            # try to reconnect to next best server
            server_address = self.process__on_connection_lost__already_got_clients_per_server_dict()
        else:
            # try to reconnect to random server
            server_address = self.process__on_connection_lost__still_need_to_get_clients_per_server_dict()
        self.make_connection_to_the_server(server_address)

    def __copy__(self):
        print("__copy__")
        return type(self)(self.global_data)

    def process__on_connect__already_got_clients_per_server_dict(self):
        self.mark_this_connection_as_connection_to_destination_server()

    def process__on_connect__still_need_to_get_clients_per_server_dict(self):
        self.send_request__give_me_clients_per_server()

    def process__on_connection_lost__already_got_clients_per_server_dict(self):
        if not self.is_normal_reconnection:
            del self.global_data.clients_per_server[self.server_address]
        server_address = min(self.global_data.clients_per_server, key=self.global_data.clients_per_server.get)
        # print('TRYING TO RECONNECT TO THE BEST SERVER ({})'.format(server_address))
        # print()
        return server_address

    def process__on_connection_lost__still_need_to_get_clients_per_server_dict(self):
        server_number = randint(0, len(self.global_data.all_servers_list) - 1)
        server_address = self.global_data.all_servers_list[server_number]
        # print('TRYING TO RECONNECT TO THE RANDOM SERVER ({})'.format(server_address))
        # print()
        return server_address

    def make_connection_to_the_server(self, server_address):
        worker_for_server_connection = MainWorker(self.global_data)
        worker_for_server_connection.server_address = server_address
        main_server_connection_info = ConnectionInfo(worker_for_server_connection,
                                                     ConnectionType.active_connected,
                                                     server_address)
        self.api.make_connection(main_server_connection_info)

    def mark_this_connection_as_connection_to_destination_server(self):
        self.connected_to_destination_server = True
        print('CONNECTED TO THE DESTINATION SERVER ({})'.format(self.server_address))
        print()
        self.connection.force_write_call = True
        self.send_request__client_arrived()

    def send_request__client_arrived(self):
        message = {
            FieldName.name: RPCName.client_arrived,
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.add_must_be_written_data(packed_message)

    def send_request__give_me_clients_per_server(self):
        message = {
            FieldName.name: RPCName.give_me_clients_per_server,
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.add_must_be_written_data(packed_message)

    def send_request__client_string(self, string: str):
        message = {
            FieldName.name: RPCName.client_string,
            FieldName.string: string
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.add_must_be_written_data(packed_message)

    def input_message_handler(self, message: bytes):
        message = marshal.loads(message)
        print('IN: {}'.format(message))
        if message[FieldName.name] in self.input_rpc_handlers:
            self.input_rpc_handlers[message[FieldName.name]](message)
        else:
            print('WRONG RPC')
        print()

    def prepare_input_rpc_handlers(self):
        self.input_rpc_handlers = {
            RPCName.clients_per_server: self.rpc_input__clients_per_server,
            RPCName.print_string: self.rpc_input__print_string,
        }

    def rpc_input__clients_per_server(self, message):
        self.global_data.clients_per_server = message[FieldName.clients_per_server]
        server_address = min(self.global_data.clients_per_server, key=self.global_data.clients_per_server.get)
        if server_address != self.server_address:
            # if this is not the best server - reconnect to the best server
            self.is_normal_reconnection = True
            self.api.remove_connection(self.connection)
        else:
            # this is already the best server. We can start working now
            self.mark_this_connection_as_connection_to_destination_server()

    def rpc_input__print_string(self, message):
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
