"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


MESSAGE_SIZE_LEN = 4


class ThereIsNoMessages(Exception):
    pass


def get_message(data: bytes)->tuple:
    '''
    Retrieves message from bytes data
    :param data: input data
    :return: tuple of (message, the_remaining_data)
    :raise ThereIsNoMessages: when there is no complete messages in input data
    '''
    result = tuple()
    remaining_data = None
    message = None
    message_length = None

    if len(data) >= MESSAGE_SIZE_LEN:
        bin_message_length = data[:MESSAGE_SIZE_LEN]
        if bin_message_length:
            message_length = int.from_bytes(bin_message_length, 'little')
    else:
        raise ThereIsNoMessages()

    bin_messages = data[MESSAGE_SIZE_LEN:]
    if len(bin_messages) >= message_length:
        message = bin_messages[:message_length]
        remaining_data = bin_messages[message_length:]
    else:
        raise ThereIsNoMessages()

    result = (message, remaining_data)
    return result


def pack_message(message: bytes)->bytes:
    '''
    Packs message
    :param message: message
    :return: packed message with length
    '''
    packed_message = len(message).to_bytes(MESSAGE_SIZE_LEN, 'little') + message
    return packed_message
