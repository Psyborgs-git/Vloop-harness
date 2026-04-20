"""Unit tests for ComponentTree."""

import pytest
from harness.core.base_component import BaseComponent
from harness.core.component_tree import ComponentTree


class _Stub(BaseComponent):
    pass


def test_register_and_get():
    tree = ComponentTree()
    c = _Stub(component_id="test_1")
    tree.register(c)
    assert tree.get("test_1") is c
    assert "test_1" in tree


def test_unregister():
    tree = ComponentTree()
    c = _Stub(component_id="test_2")
    tree.register(c)
    removed = tree.unregister("test_2")
    assert removed is c
    assert tree.get("test_2") is None


def test_list_all():
    tree = ComponentTree()
    a = _Stub(component_id="a")
    b = _Stub(component_id="b")
    tree.register(a)
    tree.register(b)
    ids = {c.id for c in tree.list_all()}
    assert ids == {"a", "b"}


def test_get_or_raise_missing():
    tree = ComponentTree()
    with pytest.raises(KeyError):
        tree.get_or_raise("nonexistent")
