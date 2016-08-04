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
        self.unknown__client_or_server_connection = True
        self.is_on_connect_was_called = False

        self.input_rpc_handlers = dict()
        self.prepare_input_rpc_handlers()

    def on_connect(self):
        self.is_on_connect_was_called = True
        if ConnectionType.passive == self.connection.connection_info.connection_type:
            self.process__on_connect__as_passive_connection()
        else:
            self.process__on_connect__as_an_active_connection()

    def on_read(self):
        try:
            while True:
                message, remaining_data = get_message(self.connection.read_data)
                self.connection.read_data = remaining_data
                self.input_message_handler(message)
        except ThereIsNoMessages:
            return

    def on_connection_lost(self):
        if ConnectionType.passive == self.connection.connection_info.connection_type:
            self.process__on_connection_lost__as_passive_connection()
        else:
            self.process__on_connection_lost__as_an_active_connection()

    def __copy__(self):
        return type(self)(self.global_data)

    def process__on_connect__as_passive_connection(self):
        # this is passive socket.
        # send 'server arrived' message to other servers
        self.connection.conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.change_number_of_connected_clients(0)

    def process__on_connect__as_an_active_connection(self):
        if self.is_connection_to_the_server:
            print('SERVER ARRIVED: {}'.format(self.server_address))

    def process__on_connection_lost__as_passive_connection(self):
        # This is was passive socket
        # Try to restart passive connection:
        new_connection_info = copy.copy(self.connection.connection_info)
        self.api.make_connection(new_connection_info, self.connection.connection_name)

    def process__on_connection_lost__as_an_active_connection(self):
        # if active connection
        if self.is_connection_to_the_server:
            # if connection to the server
            self.unregister_current_connection_to_the_server()
            if self.is_on_connect_was_called:
                # if on_connection_lost() was called NOT immediately after connection creation because of some error
                # (peer is not accessible, etc.)
                print('SERVER GONE: {}'.format(self.server_address))
        else:
            # if connection to the client
            if not self.unknown__client_or_server_connection:
                self.change_number_of_connected_clients(-1)

    @staticmethod
    def register_connection_as_a_connection_to_the_server(connection, address=None):
        worker_obj = connection.worker_obj
        worker_obj.server_address = address or worker_obj.server_address
        worker_obj.is_connection_to_the_server = True
        worker_obj.global_data.deployed_servers_addresses[worker_obj.server_address] = connection
        worker_obj.global_data.server_by_connection_id[connection.connection_id] = worker_obj.server_address
        worker_obj.global_data.clients_per_server[worker_obj.server_address] = 0

    def register_current_connection_as_a_connection_to_the_server(self, address=None):
        self.register_connection_as_a_connection_to_the_server(self.connection, address)

    @staticmethod
    def unregister_connection_to_the_server(connection):
        worker_obj = connection.worker_obj
        server_address = worker_obj.server_address
        if server_address in worker_obj.global_data.deployed_servers_addresses:
            worker_obj.global_data.deployed_servers_addresses[server_address] = None
        if connection.connection_id in worker_obj.global_data.server_by_connection_id:
            del worker_obj.global_data.server_by_connection_id[connection.connection_id]
        if server_address is not None:
            if server_address in worker_obj.global_data.clients_per_server:
                del worker_obj.global_data.clients_per_server[server_address]
        connection.worker_obj.is_connection_to_the_server = False

    def unregister_current_connection_to_the_server(self):
        self.unregister_connection_to_the_server(self.connection)

    def change_number_of_connected_clients(self, delta_num: int):
        self.global_data.number_of_clients += delta_num
        print('NUMBER OF OWN CONNECTED CLIENTS: {}'.format(self.global_data.number_of_clients))
        self.global_data.clients_per_server[self.global_data.own_address] = self.global_data.number_of_clients
        self.broadcast_request__to_servers__number_of_clients_changed()

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
            self.register_connection_as_a_connection_to_the_server(connection, address)
            self.send_request__server_arrived(connection)
        return connection

    def send_request__server_arrived(self, connection):
        message = {
            FieldName.name: RPCName.server_arrived,
            FieldName.address: self.global_data.own_address
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        connection.add_must_be_written_data(packed_message)
        self.api.check_is_connection_need_to_sent_data(connection)

    def broadcast_request__to_servers__server_arrived(self):
        for address in self.global_data.deployed_servers_addresses:
            self.check_connection_to_the_server(address)

    def broadcast_request__to_servers__number_of_clients_changed(self):
        for address in self.global_data.deployed_servers_addresses:
            connection = self.check_connection_to_the_server(address)
            message = {
                FieldName.name: RPCName.number_of_clients_changed,
                FieldName.clients: self.global_data.number_of_clients
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            connection.add_must_be_written_data(packed_message)
            self.api.check_is_connection_need_to_sent_data(connection)

    def broadcast_request__to_servers__client_string(self, client_string):
        for address in self.global_data.deployed_servers_addresses:
            connection = self.check_connection_to_the_server(address)
            message = {
                FieldName.name: RPCName.broadcast_string,
                FieldName.string: client_string
            }
            bin_message = marshal.dumps(message)
            packed_message = pack_message(bin_message)
            connection.add_must_be_written_data(packed_message)
            self.api.check_is_connection_need_to_sent_data(connection)

    def broadcast_request__to_own_clients__client_string(self, client_string):
        for connection in self.api.all_connections:
            if ConnectionState.connected != connection.connection_state:
                continue
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
            connection.add_must_be_written_data(packed_message)
            self.api.check_is_connection_need_to_sent_data(connection)

    def input_message_handler(self, message: bytes):
        message = marshal.loads(message)
        if message[FieldName.name] in self.input_rpc_handlers:
            # run an appropriate rpc handler
            self.input_rpc_handlers[message[FieldName.name]](message)
        else:
            print('WRONG RPC: {}'.format(message))

    def prepare_input_rpc_handlers(self):
        self.input_rpc_handlers = {
            RPCName.server_arrived: self.rpc_input__server_arrived,
            RPCName.number_of_clients_changed: self.rpc_input__number_of_clients_changed,
            RPCName.client_string: self.rpc_input__client_string,
            RPCName.give_me_best_server: self.rpc_input__give_me_best_server,
            RPCName.give_me_clients_per_server: self.rpc_input__give_me_clients_per_server,
            RPCName.broadcast_string: self.rpc_input__broadcast_string,
            RPCName.client_arrived: self.rpc_input__client_arrived,
        }

    def rpc_input__server_arrived(self, message):
        address = message[FieldName.address]
        if address in self.global_data.deployed_servers_addresses:
            if self.unknown__client_or_server_connection:
                self.unknown__client_or_server_connection = False
            if self.global_data.deployed_servers_addresses[address] is None:
                self.register_current_connection_as_a_connection_to_the_server(address)
                print('SERVER ARRIVED: {}'.format(address))
        else:
            self.api.remove_connection(self.connection)

    def rpc_input__client_arrived(self, message):
        if self.unknown__client_or_server_connection:
            self.unknown__client_or_server_connection = False
        self.change_number_of_connected_clients(1)

    def rpc_input__number_of_clients_changed(self, message):
        if self.server_address is not None:
            self.global_data.clients_per_server[self.server_address] = message[FieldName.clients]

    def rpc_input__client_string(self, message):
        client_string = message[FieldName.string]
        self.broadcast_request__to_servers__client_string(client_string)
        self.broadcast_request__to_own_clients__client_string(client_string)

    def rpc_input__give_me_best_server(self, message):
        best_server_address = min(self.global_data.clients_per_server, key=self.global_data.clients_per_server.get)
        message = {
            FieldName.name: RPCName.best_server,
            FieldName.address: best_server_address
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.add_must_be_written_data(packed_message)

    def rpc_input__give_me_clients_per_server(self, message):
        message = {
            FieldName.name: RPCName.clients_per_server,
            FieldName.clients_per_server: self.global_data.clients_per_server
        }
        bin_message = marshal.dumps(message)
        packed_message = pack_message(bin_message)
        self.connection.add_must_be_written_data(packed_message)

    def rpc_input__broadcast_string(self, message):
        client_string = message[FieldName.string]
        self.broadcast_request__to_own_clients__client_string(client_string)


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
            if address == self.own_server_address:
                continue
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
    all_server_list = load_server_list()

    server_number = 0
    if len(sys.argv) > 1:
        server_number = int(sys.argv[1])
    else:
        index = 0
        for address in all_server_list:
            print(index, address)
            index += 1
        server_number = int(input('ENTER SERVER NUMBER:'))

    server = Server(all_server_list[server_number], all_server_list)
    server.run()

if __name__ == '__main__':
    main()
