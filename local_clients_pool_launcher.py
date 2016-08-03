from client import *


"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


def main():
    number_of_clients = 1
    if len(sys.argv) > 1:
        number_of_clients = int(sys.argv[1])
    if number_of_clients < 1:
        number_of_clients = 1

    all_server_list = load_server_list()
    processes_list = list()

    print('THERE ARE WILL BE STARTED {} CLIENT PROCESSES'.format(len(all_server_list)))

    for index in range(number_of_clients):
        client = Client(all_server_list)
        processes_list.append(client)
        client.start()

    terminate = input('CLICK \'ENTER\' TO TERMINATE CLIENT PROCESS POOL')

    for process in processes_list:
        process.terminate()

    print('DONE.')

if __name__ == '__main__':
    main()
