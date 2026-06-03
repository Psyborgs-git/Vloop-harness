"""DSPyComponentRegistry — runtime cache of compiled DSPy Module classes.

When a ``DSPyComponentDef`` is loaded from the database, its ``code`` field
is exec-compiled into a real Python class and cached here so it can be
instantiated on demand by routes and the PipelineBuilder.

Security note
─────────────
exec() is used deliberately — this harness is a local developer tool and the
component code is authored by the user (or generated on their behalf). The same
trust model applies as running any Python file locally.
"""

from __future__ import annotations

import ast
import textwrap
from typing import TYPE_CHECKING, Any

import dspy

if TYPE_CHECKING:
    from harness.data.models import DSPyComponentDef


class ComponentCompileError(ValueError):
    """Raised when component source code cannot be compiled or validated."""


class DSPyComponentRegistry:
    """Compile, cache, and instantiate user-defined DSPy Module classes."""

    def __init__(self) -> None:
        self._compiled: dict[str, type[dspy.Module]] = {}

    # ── Compilation ───────────────────────────────────────────────────────────

    def compile(self, component_def: DSPyComponentDef) -> type[dspy.Module]:
        """Exec the source code and cache the resulting Module subclass.

        Returns the compiled class; also updates the in-memory cache.
        Raises ``ComponentCompileError`` on syntax or structural problems.
        """
        code = textwrap.dedent(component_def.code)
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise ComponentCompileError(
                f"Syntax error in component {component_def.id!r}: {exc}"
            ) from exc

        namespace: dict[str, Any] = {"dspy": dspy}
        try:
            exec(compile(tree, f"<component:{component_def.id}>", "exec"), namespace)
        except Exception as exc:
            raise ComponentCompileError(
                f"Runtime error while loading component {component_def.id!r}: {exc}"
            ) from exc

        # Find the first dspy.Module subclass in the namespace (not dspy.Module itself)
        module_class: type[dspy.Module] | None = None
        for obj in namespace.values():
            if (
                isinstance(obj, type)
                and issubclass(obj, dspy.Module)
                and obj is not dspy.Module
            ):
                module_class = obj
                break

        if module_class is None:
            raise ComponentCompileError(
                f"No dspy.Module subclass found in component {component_def.id!r}. "
                "Ensure your code defines a class that inherits from dspy.Module."
            )

        self._compiled[component_def.id] = module_class
        return module_class

    # ── Access ────────────────────────────────────────────────────────────────

    def get_class(self, component_id: str) -> type[dspy.Module] | None:
        return self._compiled.get(component_id)

    def instantiate(self, component_id: str) -> dspy.Module | None:
        cls = self._compiled.get(component_id)
        if cls is None:
            return None
        return cls()

    def is_loaded(self, component_id: str) -> bool:
        return component_id in self._compiled

    def unload(self, component_id: str) -> None:
        self._compiled.pop(component_id, None)

    def loaded_ids(self) -> list[str]:
        return list(self._compiled.keys())

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def extract_signature_fields(code: str) -> dict[str, list[dict[str, str]]]:
        """Parse input/output fields from a DSPy Signature class in ``code``.

        Returns::

            {
                "inputs":  [{"name": "article", "desc": "The text to summarise"}, ...],
                "outputs": [{"name": "summary", "desc": "A brief summary"}, ...],
            }

        Falls back to empty lists on any parse error.
        """
        inputs: list[dict[str, str]] = []
        outputs: list[dict[str, str]] = []
        try:
            tree = ast.parse(textwrap.dedent(code))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for base in node.bases:
                    base_name = ast.unparse(base)
                    if "Signature" not in base_name:
                        continue
                    for item in node.body:
                        if not isinstance(item, ast.AnnAssign):
                            continue
                        field_name = ast.unparse(item.target)
                        if item.value is None:
                            continue
                        call_str = ast.unparse(item.value)
                        desc = ""
                        if "desc=" in call_str:
                            try:
                                desc_start = call_str.index("desc=") + 5
                                desc_end = call_str.index('"', desc_start + 1)
                                desc = call_str[desc_start + 1 : desc_end]
                            except (ValueError, IndexError):
                                pass
                        if "InputField" in call_str:
                            inputs.append({"name": field_name, "desc": desc})
                        elif "OutputField" in call_str:
                            outputs.append({"name": field_name, "desc": desc})
        except Exception:
            pass
        return {"inputs": inputs, "outputs": outputs}
