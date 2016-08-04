"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


class FieldName:
    name = 0
    address = 1
    clients = 2
    string = 3
    clients_per_server = 4


class RPCName:
    server_arrived = 0
    number_of_clients_changed = 2
    broadcast_string = 3
    print_string = 4
    client_string = 5
    give_me_best_server = 6
    best_server = 7
    give_me_clients_per_server = 8
    clients_per_server = 9
    client_arrived = 10

RPC_REQUESTS_ONLY_FROM_SERVER = {
    RPCName.server_arrived,
    RPCName.number_of_clients_changed,
    RPCName.broadcast_string,
    RPCName.print_string,
}

RPC_RESPONSES_ONLY_FROM_SERVER = {
    RPCName.best_server,
    RPCName.clients_per_server,
}

RPC_REQUESTS_ONLY_FROM_CLIENT = {
    RPCName.client_string,
    RPCName.give_me_best_server,
    RPCName.give_me_clients_per_server,
    RPCName.client_arrived
}

RPC_RESPONSES_ONLY_FROM_CLIENT = {
}
