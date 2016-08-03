from net_io__linux import *
from net_io_method__epoll_lt import *
from transport_protocol import *
from server_list_loader import load_server_list
from transport_protocol_constants import *
import marshal
import sys
from multiprocessing import Process


"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


class GlobalDataForAllWorkers:
    def __init__(self):
        self.deployed_servers_addresses = dict()
        self.server_by_connection_id = dict()
        self.clients_per_server = dict()

        self.number_of_clients = 0
        self.own_address = None


class MainWorker(WorkerBase):
    def __init__(self, global_data: GlobalDataForAllWorkers):
        super().__init__()
        self.global_data = global_data
        self.is_connection_to_the_server = False
        self.server_address = None

    def on_connect(self):
        if ConnectionType.passive == self.connection.connection_info.connection_type:
            # send 'arrived' message to other servers
            self.connection.conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            self.broadcast_server_arrived_message()
            self.broadcast_number_of_clients_changed()
        else:
            # if active connection
            if self.connection.connection_info.socket_address in self.global_data.deployed_servers_addresses:
                # if connection to the server
                self.global_data.deployed_servers_addresses[self.connection.connection_info.socket_address] = \
                    self.connection
                self.global_data.server_by_connection_id[self.connection.connection_id] = \
                    self.connection.connection_info.socket_address
                self.server_address = self.connection.connection_info.socket_address
            else:
                # if connection to the client
                self.global_data.number_of_clients += 1
                self.broadcast_number_of_clients_changed()

    def on_read(self):
        try:
            while True:
                message, remaining_data = get_message(self.connection.read_data)
                self.connection.read_data = remaining_data
                self.message_handler(message)
        except ThereIsNoMessages:
            return

    def on_connection_lost(self):
        if ConnectionType.passive == self.connection.connection_info.connection_type:
            # Try to restart passive connection:
            new_connection_info = copy.copy(self.connection.connection_info)
            self.api.make_connection(new_connection_info, self.connection.connection_name)
        else:
            # if active connection
            if self.is_connection_to_the_server:
                # if connection to the server
                if self.connection.connection_info.socket_address in self.global_data.deployed_servers_addresses:
                    self.global_data.deployed_servers_addresses[self.connection.connection_info.socket_address] = None
                if self.connection.connection_id in self.global_data.server_by_connection_id:
                    del self.global_data.server_by_connection_id[self.connection.connection_id]
                if self.server_address is not None:
                    del self.global_data.clients_per_server[self.server_address]
            else:
                # if connection to the client
                self.global_data.number_of_clients -= 1
                self.broadcast_number_of_clients_changed()

    def __copy__(self):
        return type(self)(self.global_data)

    def check_connection_to_the_server(self, address)->Connection:
        '''
        Check connection to the server. Reconnect if needed
        :param address: server address
        :return: old or new connection to the server
        '''
        connection = self.global_data.deployed_servers_addresses[address]
        if connection is None:
            new_worker_obj = MainWorker(self.global_data)
            new_worker_obj.is_connection_to_the_server = True
            new_worker_obj.server_address = address
            new_connection_info = ConnectionInfo(new_worker_obj, ConnectionType.active_connected, address)
            new_connection = self.api.make_connection(new_connection_info)
            self.global_data.deployed_servers_addresses[address] = new_connection
            connection = new_connection
        return connection

    def broadcast_server_arrived_message(self):
        for address in self.global_data.deployed_servers_addresses:
            connection = self.check_connection_to_the_server(address)
            message = {
                FieldName.name: RPCName.server_arrived,
                FieldName.address: self.global_data.own_address
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            connection.must_be_written_data += packed_message
            self.api.check_is_connection_need_to_sent_data(connection)

    def broadcast_number_of_clients_changed(self):
        for address in self.global_data.deployed_servers_addresses:
            connection = self.check_connection_to_the_server(address)
            message = {
                FieldName.name: RPCName.number_of_clients_changed,
                FieldName.clients: self.global_data.number_of_clients
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            connection.must_be_written_data += packed_message
            self.api.check_is_connection_need_to_sent_data(connection)

    def broadcast_client_string(self, client_string):
        for address in self.global_data.deployed_servers_addresses:
            connection = self.check_connection_to_the_server(address)
            message = {
                FieldName.name: RPCName.broadcast_string,
                FieldName.string: client_string
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            connection.must_be_written_data += packed_message
            self.api.check_is_connection_need_to_sent_data(connection)

    def broadcast_client_string_to_own_clients(self, client_string):
        for connection in self.api.all_connections:
            if connection.worker_obj.is_connection_to_the_server:
                continue
            if connection == self.connection:
                continue
            message = {
                FieldName.name: RPCName.print_string,
                FieldName.string: client_string
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            connection.must_be_written_data += packed_message
            self.api.check_is_connection_need_to_sent_data(connection)

    def message_handler(self, message: bytes):
        message = marshal.loads(message)
        if RPCName.server_arrived == message[FieldName.name]:
            address = message[FieldName.address]
            if address in self.global_data.deployed_servers_addresses:
                if not self.is_connection_to_the_server:
                    self.global_data.number_of_clients -= 1
                    self.broadcast_number_of_clients_changed()
                    self.is_connection_to_the_server = True
                self.server_address = address
                self.global_data.deployed_servers_addresses[address] = self.connection
                self.global_data.server_by_connection_id[self.connection.connection_id] = address
            else:
                self.api.remove_connection(self.connection)
        elif RPCName.number_of_clients_changed == message[FieldName.name]:
            if self.server_address is not None:
                self.global_data.clients_per_server[self.server_address] = message[FieldName.clients]
        elif RPCName.client_string == message[FieldName.name]:
            client_string = message[FieldName.string]
            self.broadcast_client_string(client_string)
            self.broadcast_client_string_to_own_clients(client_string)
        elif RPCName.give_me_best_server == message[FieldName.name]:
            best_server_address = min(self.global_data.clients_per_server, key=self.global_data.clients_per_server.get)
            message = {
                FieldName.name: RPCName.best_server,
                FieldName.address: best_server_address
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            self.connection.must_be_written_data += packed_message
        elif RPCName.give_me_clients_per_server == message[FieldName.name]:
            message = {
                FieldName.name: RPCName.clients_per_server,
                FieldName.clients_per_server: self.global_data.clients_per_server
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            self.connection.must_be_written_data += packed_message


class Server(Process):
    def __init__(self, own_server_address, all_server_list: list=None):
        super().__init__()
        self.own_server_address = own_server_address
        self.all_server_list = all_server_list
        if self.all_server_list is None:
            self.all_server_list = load_server_list()

        self.global_data = GlobalDataForAllWorkers()
        self.global_data.own_address = self.own_server_address
        for address in self.all_server_list:
            self.global_data.deployed_servers_addresses[address] = None

    def run(self):
        io = NetIO(IOMethodEpollLT)
        with net_io(io) as io:
            worker_for_main_passive_socket = MainWorker(self.global_data)
            main_passive_connection_info = ConnectionInfo(worker_for_main_passive_socket,
                                                          ConnectionType.passive,
                                                          self.own_server_address,
                                                          backlog=10)
            io.make_connection(main_passive_connection_info, 'server')


def main():
    server_number = 0
    if len(sys.argv) > 1:
        server_number = int(sys.argv[1])
    all_server_list = load_server_list()
    server = Server(all_server_list[server_number], all_server_list)
    server.run()

if __name__ == '__main__':
    main()
