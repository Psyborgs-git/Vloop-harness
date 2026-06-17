import sqlite3
from typing import List
from core.ports import IRelationalDB

class SQLiteAdapter(IRelationalDB):
    """
    Zero-dependency SQLite adapter for relational data.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def connect(self) -> None:
        self.conn = sqlite3.connect(self.db_path)

    def execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        if not self.conn:
            self.connect()
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        self.conn.commit()
        return cursor.fetchall()

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
