from server import *


"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


def main():
    all_server_list = load_server_list()
    processes_list = list()

    print('THERE ARE WILL BE STARTED {} SERVER PROCESSES'.format(len(all_server_list)))

    for server_address in all_server_list:
        server = Server(server_address, all_server_list)
        processes_list.append(server)
        server.start()

    terminate = input('CLICK \'ENTER\' TO TERMINATE SERVER PROCESS POOL')

    for process in processes_list:
        process.terminate()

    print('DONE.')

if __name__ == '__main__':
    main()
