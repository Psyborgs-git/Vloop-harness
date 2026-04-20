"""Unit tests for StateStore."""

import pytest
import pytest_asyncio
from harness.core.state_store import StateStore


@pytest.fixture
async def store(tmp_path):
    s = StateStore(db_path=tmp_path / "test.db")
    await s.open()
    yield s
    await s.close()


async def test_set_get(store):
    await store.set("comp_1", "count", 42)
    assert await store.get("comp_1", "count") == 42


async def test_get_default(store):
    assert await store.get("comp_1", "missing", default="hello") == "hello"


async def test_get_all(store):
    await store.set("comp_2", "a", 1)
    await store.set("comp_2", "b", 2)
    all_vals = await store.get_all("comp_2")
    assert all_vals == {"a": 1, "b": 2}


async def test_flush(store):
    await store.set("comp_3", "x", 99)
    await store.flush("comp_3")
    assert await store.get("comp_3", "x") is None


async def test_persist_restore(tmp_path):
    s1 = StateStore(db_path=tmp_path / "persist.db")
    await s1.open()
    await s1.set("c1", "val", "hello")
    await s1.persist()
    await s1.close()

    s2 = StateStore(db_path=tmp_path / "persist.db")
    await s2.open()
    assert await s2.get("c1", "val") == "hello"
    await s2.close()
