import sqlite3
from contextlib import closing, contextmanager

@contextmanager
def state():
    with closing(sqlite3.connect("/state/jobs.db")) as connection, connection:
        connection.row_factory = sqlite3.Row
        yield connection
