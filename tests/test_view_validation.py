"""Unit tests for harness.server.routes.view_validation.

Covers:
  - validate_component_name  — valid / invalid PascalCase names
  - validate_react_code      — banned patterns caught, clean code passes
  - write_view_stub           — correct files written, idempotent main.tsx
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.server.routes.view_validation import (
    validate_component_name,
    validate_react_code,
    write_view_stub,
)


# ── validate_component_name ────────────────────────────────────────────────────


class TestValidateComponentName:
    def test_simple_pascal_case_accepted(self) -> None:
        assert validate_component_name("MyView") == "MyView"

    def test_two_char_minimum_accepted(self) -> None:
        assert validate_component_name("Ab") == "Ab"

    def test_single_uppercase_rejected(self) -> None:
        # Only one character — too short (regex requires 2+)
        with pytest.raises(ValueError, match="PascalCase"):
            validate_component_name("A")

    def test_lowercase_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="PascalCase"):
            validate_component_name("myView")

    def test_hyphen_rejected(self) -> None:
        with pytest.raises(ValueError, match="PascalCase"):
            validate_component_name("My-View")

    def test_underscore_rejected(self) -> None:
        with pytest.raises(ValueError, match="PascalCase"):
            validate_component_name("My_View")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_component_name("")

    def test_space_padded_stripped_then_validated(self) -> None:
        # Leading/trailing whitespace is stripped before validation
        assert validate_component_name("  MyView  ") == "MyView"

    def test_name_with_digits_accepted(self) -> None:
        assert validate_component_name("View123") == "View123"

    def test_64_char_limit_accepted(self) -> None:
        # 64 chars total starting with uppercase: 1 upper + 63 alphanumeric
        name = "A" + "b" * 63
        assert validate_component_name(name) == name

    def test_65_chars_rejected(self) -> None:
        name = "A" + "b" * 64  # 65 chars total
        with pytest.raises(ValueError):
            validate_component_name(name)

    def test_slash_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_component_name("My/View")

    def test_dot_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_component_name("My.View")


# ── validate_react_code ────────────────────────────────────────────────────────


class TestValidateReactCode:
    def test_clean_code_passes(self) -> None:
        code = 'import React from "react";\nexport default function Hello() { return <div>Hi</div>; }'
        validate_react_code(code)  # must not raise

    def test_eval_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code('const x = eval("1+1");')

    def test_exec_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code('exec("rm -rf /");')

    def test_child_process_require_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code("const cp = require('child_process');")

    def test_process_env_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code("const key = process.env.API_KEY;")

    def test_dirname_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code("const p = __dirname + '/secret';")

    def test_filename_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code("const f = __filename;")

    def test_fs_require_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code('const fs = require("fs");')

    def test_path_require_blocked(self) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            validate_react_code("const path = require('path');")

    def test_empty_code_passes(self) -> None:
        validate_react_code("")  # nothing to flag — should not raise

    def test_eval_in_comment_still_blocked(self) -> None:
        # The regex doesn't distinguish comments; that's intentional (conservative)
        with pytest.raises(ValueError):
            validate_react_code("// eval() is dangerous\nconst x = eval('ok');")

    def test_mui_imports_passes(self) -> None:
        code = (
            'import { Box, Typography } from "@mui/material";\n'
            'import { useState } from "react";\n'
            "export default function MyWidget() { return <Box>ok</Box>; }"
        )
        validate_react_code(code)  # must not raise


# ── write_view_stub ────────────────────────────────────────────────────────────


class TestWriteViewStub:
    def test_creates_app_tsx(self, tmp_path: Path) -> None:
        code = 'export default function Hello() { return <div>hi</div>; }'
        result = write_view_stub(tmp_path, "HelloWorld", code)
        assert result is not None
        app_file = tmp_path / "HelloWorld" / "App.tsx"
        assert app_file.exists()
        assert app_file.read_text() == code

    def test_creates_main_tsx(self, tmp_path: Path) -> None:
        code = 'export default function Foo() { return null; }'
        write_view_stub(tmp_path, "FooBar", code)
        main_file = tmp_path / "FooBar" / "main.tsx"
        assert main_file.exists()
        main_content = main_file.read_text()
        assert "FooBar" in main_content
        assert "ReactDOM" in main_content

    def test_main_tsx_not_overwritten(self, tmp_path: Path) -> None:
        write_view_stub(tmp_path, "Widget", "// first")
        main_file = tmp_path / "Widget" / "main.tsx"
        original_content = main_file.read_text()
        # Write again with different code
        write_view_stub(tmp_path, "Widget", "// second")
        assert main_file.read_text() == original_content  # unchanged

    def test_app_tsx_overwritten(self, tmp_path: Path) -> None:
        write_view_stub(tmp_path, "Comp", "// v1")
        write_view_stub(tmp_path, "Comp", "// v2")
        app_file = tmp_path / "Comp" / "App.tsx"
        assert app_file.read_text() == "// v2"

    def test_returns_absolute_path_of_app_tsx(self, tmp_path: Path) -> None:
        result = write_view_stub(tmp_path, "MyComp", "// code")
        expected = str(tmp_path / "MyComp" / "App.tsx")
        assert result == expected

    def test_nested_react_root_created(self, tmp_path: Path) -> None:
        react_root = tmp_path / "react" / "src" / "components" / "generated"
        write_view_stub(react_root, "DeepComp", "// deep")
        assert (react_root / "DeepComp" / "App.tsx").exists()

    def test_returns_none_on_permission_error(self, tmp_path: Path, monkeypatch) -> None:
        # Simulate a write failure by making the directory read-only
        react_root = tmp_path / "locked"
        react_root.mkdir()
        react_root.chmod(0o555)
        result = write_view_stub(react_root, "FailComp", "// code")
        assert result is None
        react_root.chmod(0o755)  # restore so tmp_path cleanup works
