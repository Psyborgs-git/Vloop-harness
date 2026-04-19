"""Validate agent-generated Python code before execution."""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


def validate_syntax(code: str) -> tuple[bool, str]:
    """Check that code parses as valid Python."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"


def validate_import(code: str) -> tuple[bool, str]:
    """Attempt to import the code in a subprocess to catch import-time errors."""
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import importlib.util; spec = importlib.util.spec_from_file_location('_validate', {tmp_path!r}); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, result.stderr
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Import validation timed out"
    except Exception as exc:
        return False, str(exc)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def validate(code: str) -> tuple[bool, str]:
    """Full validation: syntax then import."""
    ok, msg = validate_syntax(code)
    if not ok:
        return False, msg
    ok, msg = validate_import(code)
    return ok, msg
