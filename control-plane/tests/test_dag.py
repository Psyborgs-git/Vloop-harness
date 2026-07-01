"""Unit tests for core.dag cycle detection and topology helpers.

Covers Requirements 1.2 (cycle detection / rejection support) and 3.2
(dependency layering for executor scheduling): acyclic vs cyclic graphs,
transitive dependents, topological layering / concurrency layers, and roots.
"""

from __future__ import annotations

import pytest

from core.dag import Dag, DagNode


# -- helpers ---------------------------------------------------------------


def _node(step_id: str, *deps: str, step_type: str = "agent") -> DagNode:
    return DagNode(step_id=step_id, step_type=step_type, depends_on=tuple(deps))


def _dag(*nodes: DagNode) -> Dag:
    node_map = {n.step_id: n for n in nodes}
    edges = tuple(
        (dep, n.step_id) for n in nodes for dep in n.depends_on if dep in node_map
    )
    return Dag(nodes=node_map, edges=edges)


# -- detect_cycle: acyclic -------------------------------------------------


def test_detect_cycle_returns_none_for_empty_graph():
    assert Dag(nodes={}).detect_cycle() is None


def test_detect_cycle_returns_none_for_single_node():
    assert _dag(_node("a")).detect_cycle() is None


def test_detect_cycle_returns_none_for_linear_chain():
    dag = _dag(_node("a"), _node("b", "a"), _node("c", "b"))
    assert dag.detect_cycle() is None


def test_detect_cycle_returns_none_for_diamond():
    # a -> b, a -> c, b -> d, c -> d  (diamond, still acyclic)
    dag = _dag(
        _node("a"),
        _node("b", "a"),
        _node("c", "a"),
        _node("d", "b", "c"),
    )
    assert dag.detect_cycle() is None


def test_detect_cycle_ignores_unknown_dependency_references():
    # Dependency on a missing node is not an edge and not a cycle.
    dag = _dag(_node("a", "ghost"), _node("b", "a"))
    assert dag.detect_cycle() is None


# -- detect_cycle: cyclic --------------------------------------------------


def test_detect_cycle_finds_self_loop():
    dag = _dag(_node("a", "a"))
    cycle = dag.detect_cycle()
    assert cycle == ["a", "a"]


def test_detect_cycle_finds_two_node_cycle():
    dag = _dag(_node("a", "b"), _node("b", "a"))
    cycle = dag.detect_cycle()
    assert cycle is not None
    # Path closes the loop by repeating the recurrence step.
    assert cycle[0] == cycle[-1]
    # The offending steps are named.
    assert set(cycle) == {"a", "b"}


def test_detect_cycle_finds_three_node_cycle_and_names_steps():
    dag = _dag(_node("a", "c"), _node("b", "a"), _node("c", "b"))
    cycle = dag.detect_cycle()
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert {"a", "b", "c"}.issubset(set(cycle))


def test_detect_cycle_finds_cycle_among_acyclic_nodes():
    # d -> e is an acyclic tail hanging off a b<->c cycle.
    dag = _dag(
        _node("a"),
        _node("b", "c"),
        _node("c", "b"),
        _node("d", "a"),
        _node("e", "d"),
    )
    cycle = dag.detect_cycle()
    assert cycle is not None
    assert set(cycle) == {"b", "c"}


# -- topological_layers: correctness & concurrency -------------------------


def test_topological_layers_empty_graph():
    assert Dag(nodes={}).topological_layers() == []


def test_topological_layers_linear_chain_is_one_per_layer():
    dag = _dag(_node("a"), _node("b", "a"), _node("c", "b"))
    assert dag.topological_layers() == [["a"], ["b"], ["c"]]


def test_topological_layers_groups_independent_steps_for_concurrency():
    # a and b are independent roots; c depends on both.
    dag = _dag(_node("a"), _node("b"), _node("c", "a", "b"))
    layers = dag.topological_layers()
    # Layer 0 holds both independent roots (may run concurrently).
    assert layers[0] == ["a", "b"]
    assert layers[1] == ["c"]


def test_topological_layers_diamond_layering():
    dag = _dag(
        _node("a"),
        _node("b", "a"),
        _node("c", "a"),
        _node("d", "b", "c"),
    )
    layers = dag.topological_layers()
    assert layers == [["a"], ["b", "c"], ["d"]]


def test_topological_layers_respects_dependency_ordering():
    # Every dependency must appear in an earlier layer than its dependent.
    dag = _dag(
        _node("a"),
        _node("b", "a"),
        _node("c", "a"),
        _node("d", "b"),
        _node("e", "b", "c"),
    )
    layers = dag.topological_layers()
    position = {step: i for i, layer in enumerate(layers) for step in layer}
    for node in dag.nodes.values():
        for dep in node.depends_on:
            assert position[dep] < position[node.step_id]
    # All nodes are present exactly once.
    assert sorted(position) == ["a", "b", "c", "d", "e"]


def test_topological_layers_are_sorted_within_layer():
    dag = _dag(_node("c"), _node("a"), _node("b"))
    assert dag.topological_layers() == [["a", "b", "c"]]


def test_topological_layers_raises_on_cycle():
    dag = _dag(_node("a", "b"), _node("b", "a"))
    with pytest.raises(ValueError) as excinfo:
        dag.topological_layers()
    # Error surfaces the offending cycle for diagnosis.
    assert "cycle" in str(excinfo.value).lower()


# -- dependents_of: transitive ---------------------------------------------


def test_dependents_of_unknown_step_is_empty():
    dag = _dag(_node("a"), _node("b", "a"))
    assert dag.dependents_of("ghost") == set()


def test_dependents_of_leaf_is_empty():
    dag = _dag(_node("a"), _node("b", "a"))
    assert dag.dependents_of("b") == set()


def test_dependents_of_direct_dependent():
    dag = _dag(_node("a"), _node("b", "a"))
    assert dag.dependents_of("a") == {"b"}


def test_dependents_of_is_transitive():
    # a -> b -> c -> d ; dependents of a are b, c, d (transitively).
    dag = _dag(_node("a"), _node("b", "a"), _node("c", "b"), _node("d", "c"))
    assert dag.dependents_of("a") == {"b", "c", "d"}
    assert dag.dependents_of("b") == {"c", "d"}
    assert dag.dependents_of("c") == {"d"}


def test_dependents_of_collects_all_branches():
    # a fans out to b and c; both feed d.
    dag = _dag(
        _node("a"),
        _node("b", "a"),
        _node("c", "a"),
        _node("d", "b", "c"),
    )
    assert dag.dependents_of("a") == {"b", "c", "d"}
    assert dag.dependents_of("b") == {"d"}


def test_dependents_of_excludes_the_step_itself():
    dag = _dag(_node("a"), _node("b", "a"))
    assert "a" not in dag.dependents_of("a")


# -- roots -----------------------------------------------------------------


def test_roots_empty_graph():
    assert Dag(nodes={}).roots() == []


def test_roots_returns_dependency_free_steps_sorted():
    dag = _dag(_node("c"), _node("a"), _node("b", "a"), _node("d"))
    # a, c, d have no dependencies; b depends on a.
    assert dag.roots() == ["a", "c", "d"]


def test_roots_all_nodes_when_no_edges():
    dag = _dag(_node("x"), _node("y"), _node("z"))
    assert dag.roots() == ["x", "y", "z"]


def test_roots_single_root_in_linear_chain():
    dag = _dag(_node("a"), _node("b", "a"), _node("c", "b"))
    assert dag.roots() == ["a"]
