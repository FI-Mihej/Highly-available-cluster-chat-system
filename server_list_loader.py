"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


FILE_NAME = 'server_list.txt'


def load_server_list(file_name=FILE_NAME):
    result_list = list()
    with open(file_name, 'rb') as file:
        data = file.read()
        data_lines = data.split(b'\n')
        for line in data_lines:
            result_list.append(line.strip())
    return result_list
