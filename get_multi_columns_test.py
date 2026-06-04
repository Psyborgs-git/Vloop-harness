import asyncio
import time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlalchemy import inspect

async def setup_db():
    import os
    db_path = "test_perf.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}', echo=False)
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with engine.begin() as conn:
        for i in range(10):
            await conn.execute(text(f"CREATE TABLE table_{i} (id INTEGER PRIMARY KEY, name TEXT, value REAL, is_active BOOLEAN)"))

    return engine, async_session, db_path


async def method8(session):
    def _inspect(conn):
        insp = inspect(conn)
        tables = {}
        table_names = insp.get_table_names()

        if hasattr(insp, "get_multi_columns"):
            multi_cols = insp.get_multi_columns(schema=None)
            print("multi_cols keys:", multi_cols.keys())

        return tables

    return await session.run_sync(lambda session: _inspect(session.connection()))

async def main():
    import os
    engine, session_factory, db_path = await setup_db()

    async with session_factory() as session:
        await method8(session)

    await engine.dispose()
    os.remove(db_path)

if __name__ == "__main__":
    asyncio.run(main())
