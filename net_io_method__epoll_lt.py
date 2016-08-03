import select
from net_io__abstract import *


"""
Module Docstring
Docstrings: http://www.python.org/dev/peps/pep-0257/
"""

__author__ = 'ButenkoMS <gtalk@butenkoms.space>'


class IOMethodEpollLT(IOMethodBase):
    def __init__(self, interface: NetIOBase):
        super().__init__(interface)
        self.epoll = select.epoll()

    def loop_iteration(self):
        events = self.epoll.poll(1)
        for fileno, event in events:
            connection = self.interface.connection_by_fileno[fileno]

            if event & select.EPOLLIN:
                # Read available. We can try to read even even if an error occurred
                if ConnectionType.passive == connection.connection_info.connection_type:
                    self.interface.on_accept_connection(connection)
                else:
                    self.interface.on_read(connection)

            if event & select.EPOLLHUP:
                # Some error. Close connection
                self.should_be_closed.add(connection.conn)
            elif event & select.EPOLLOUT:
                # Write available. We will not write data if an error occurred
                if ConnectionState.waiting_for_connection == connection.connection_state:
                    if not connection.conn.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                        # Connected successfully:
                        self.interface.on_connected(connection)
                    else:
                        # Some connection error - will be closed:
                        self.should_be_closed.add(connection.conn)
                else:
                    self.interface.on_write(connection)

            self._close_all()

    def _close_all(self):
        for conn in self.should_be_closed:
            if conn.fileno() in self.interface.connection_by_fileno:
                connection = self.interface.connection_by_fileno[conn.fileno()]
                self.interface.on_close(connection)
            else:
                self.remove_connection(conn)
        if self.should_be_closed:
            self.should_be_closed = set()

    def destroy(self):
        self._close_all()
        self.epoll.close()

    def add_connection(self, conn: socket.socket):
        self.epoll.register(conn.fileno(), select.EPOLLIN)

    def remove_connection(self, conn: socket.socket):
        self.epoll.unregister(conn.fileno())

    def set__need_write(self, conn: socket.socket, state=True):
        if state:
            self.epoll.modify(conn.fileno(), select.EPOLLIN | select.EPOLLOUT)
        else:
            self.epoll.modify(conn.fileno(), select.EPOLLIN)

    def set__should_be_closed(self, conn: socket.socket):
        self.should_be_closed.add(conn)
