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
        self.clients_per_server = dict()

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

        self.input_rpc_handlers = dict()
        self.prepare_input_rpc_handlers()
        self.is_on_connect_was_called = False

    def on_connect(self):
        self.is_on_connect_was_called = True

        self.connection.force_write_call = True  # from this moment, on_no_more_data_to_write() will be called
        #   continuously. So we wil be able to check 'exit' command within on_no_more_data_to_write() callback at any
        #   time, even if we still not connected to the destination server.

        if self.global_data.clients_per_server:
            # already got clients_per_server dict. This means that we currently already connected to best server.
            # We can start working now
            self.process__on_connect__already_got_clients_per_server_dict()
        else:
            # need to get clients_per_server dict from current (random) server
            self.process__on_connect__still_need_to_get_clients_per_server_dict()

    def on_read(self):
        try:
            while True:
                message, remaining_data = get_message(self.connection.read_data)
                self.connection.read_data = remaining_data
                self.input_message_handler(message)
        except ThereIsNoMessages:
            return

    def on_no_more_data_to_write(self):
        self.check_for_exit()
        if self.connected_to_destination_server:
            # server has sent all data, so we ned to check user input for some new strings
            self.check_and_send_user_strings_to_the_server()

    def on_connection_lost(self):
        self.check_for_exit()  # we need to check it here to prevent hung: to be able to stop client even if there is
        #   no running servers in the cluster at all (in this situation client will tend to infinitely retry the
        #   connection to the cluster if user will not stop it).

        self.print_an_appropriate_server_reconnection_message_to_the_console()

        self.check_and_maybe_remove_faulty_destination_server_from_the_clients_per_server_dict()
        self.check_whether_we_need_to_update_the_existing_clients_per_server_dict()
        self.reconnect_to_the_new_server_from_the_cluster()

    def __copy__(self):
        return type(self)(self.global_data)

    def print_an_appropriate_server_reconnection_message_to_the_console(self):
        if self.is_normal_reconnection:
            print('SWITCHING CLUSTER SERVER'.format())
        else:
            print('CONNECTION WITH THE SERVER ({}) IS LOST. WILL TRY TO RECONNECT TO THE CLUSTER'.format(
                self.server_address))

    def check_and_send_user_strings_to_the_server(self):
        with self.global_data.lock_for__input_messages:
            if self.global_data.input_messages:
                for string in self.global_data.input_messages:
                    self.send_request__client_string(string)
                self.global_data.input_messages = list()

    def check_for_exit(self):
        with self.global_data.lock_for__need_to_exit:
            if self.global_data.need_to_exit:
                self.api.stop()

    def check_and_maybe_remove_faulty_destination_server_from_the_clients_per_server_dict(self):
        if not self.is_normal_reconnection:
            # disconnection because of some error. So we do not want to probe faulty server again at this time
            if self.server_address in self.global_data.clients_per_server:
                del self.global_data.clients_per_server[self.server_address]

    def check_whether_we_need_to_update_the_existing_clients_per_server_dict(self):
        # if there was a working session with a destination server (it could take from milliseconds up to days and
        # years between connection to and disconnection from destination server) - we need to update clients_per_server
        # dict before actual reconnection
        if self.connected_to_destination_server and self.is_on_connect_was_called:
            self.global_data.clients_per_server = dict()

    def reconnect_to_the_new_server_from_the_cluster(self):
        server_address = None
        if self.global_data.clients_per_server:
            # try to reconnect to next best server from the list
            server_address = self.process__on_connection_lost__already_got_clients_per_server_dict()
        else:
            # try to reconnect to random server
            server_address = self.process__on_connection_lost__still_need_to_get_clients_per_server_dict()
        self.make_connection_to_the_server(server_address)

    def process__on_connect__already_got_clients_per_server_dict(self):
        self.mark_this_connection_as_connection_to_destination_server()

    def process__on_connect__still_need_to_get_clients_per_server_dict(self):
        self.send_request__give_me_clients_per_server()

    def process__on_connection_lost__already_got_clients_per_server_dict(self):
        server_address = min(self.global_data.clients_per_server, key=self.global_data.clients_per_server.get)
        print('TRYING TO RECONNECT TO THE BEST SERVER ({})'.format(server_address))
        return server_address

    def process__on_connection_lost__still_need_to_get_clients_per_server_dict(self):
        server_number = randint(0, len(self.global_data.all_servers_list) - 1)
        server_address = self.global_data.all_servers_list[server_number]
        print('TRYING TO RECONNECT TO THE RANDOM SERVER ({})'.format(server_address))
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
        print()
        print('SUCCESSFULLY CONNECTED TO THE DESTINATION SERVER ({})'.format(self.server_address))
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
        if message[FieldName.name] in self.input_rpc_handlers:
            self.input_rpc_handlers[message[FieldName.name]](message)
        else:
            print('WRONG RPC: {}'.format(message))

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
    def __init__(self, global_data: GlobalDataForAllWorkers, exit_phrase):
        super().__init__()
        self.global_data = global_data
        self.exit_phrase = exit_phrase

    def run(self):
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
        self.exit_phrase = 'exit'

    def run(self):
        print('!!!!!')
        print('ENTER \'{}\' TO EXIT'.format(self.exit_phrase))
        print('!!!!!')
        print()

        input_thread = ConsoleInputThread(self.global_data, self.exit_phrase)
        input_thread.daemon = True
        input_thread.start()

        io = NetIO(IOMethodEpollLT)
        with net_io(io) as io:
            server_number = randint(0, len(self.all_servers_list) - 1)
            server_address = self.all_servers_list[server_number]
            print('TRYING TO CONNECT TO THE RANDOM CLUSTER SERVER ({})'.format(server_address))
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
