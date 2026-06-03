"""Component validation utilities for safety and correctness.

This module provides functions to validate component source code for:
- Import safety (blocking dangerous imports)
- Signature conformance (matching expected interfaces)
- Syntax correctness
- Security vulnerabilities
"""

from __future__ import annotations

import ast
import re
from typing import Any, List
from dataclasses import dataclass


# Dangerous imports that should be blocked
DANGEROUS_IMPORTS = {
    # System-level operations
    "os.system",
    "os.popen",
    "subprocess.call",
    "subprocess.run",
    "subprocess.Popen",
    # Network operations
    "socket",
    "urllib.request",
    "urllib2",
    "requests",
    "httpx",
    # File system operations (beyond allowed)
    "shutil.rmtree",
    "tempfile.mktemp",
    # Code execution
    "eval",
    "exec",
    "compile",
    # Pickle (can execute arbitrary code)
    "pickle",
    "cPickle",
    # Other potentially dangerous modules
    "ctypes",
    "multiprocessing",
}

# Allowed imports for safe component operation
ALLOWED_IMPORTS = {
    # Standard library (safe subset)
    "typing",
    "dataclasses",
    "datetime",
    "json",
    "re",
    "math",
    "random",
    "collections",
    "itertools",
    "functools",
    "pathlib",
    # DSPy
    "dspy",
    # Harness internal
    "harness",
}


@dataclass
class ValidationResult:
    """Result of a component validation."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ComponentValidator:
    """Validates component source code for safety and correctness."""

    def __init__(self, allow_list: List[str] | None = None) -> None:
        """Initialize the validator.

        Args:
            allow_list: Additional allowed imports beyond the default.
        """
        self._allowed = ALLOWED_IMPORTS.copy()
        if allow_list:
            self._allowed.update(allow_list)

    def validate_imports(self, source_code: str) -> ValidationResult:
        """Validate that all imports are safe.

        Args:
            source_code: Python source code to validate.

        Returns:
            ValidationResult with any import violations.
        """
        errors = []
        warnings = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Syntax error: {e}"],
                warnings=[],
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    self._check_import(module_name, errors, warnings)

            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                self._check_import(module_name, errors, warnings)

                # Check specific imports from module
                for alias in node.names:
                    full_name = f"{module_name}.{alias.name}" if module_name else alias.name
                    self._check_import(full_name, errors, warnings)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _check_import(self, import_name: str, errors: List[str], warnings: List[str]) -> None:
        """Check if an import is allowed.

        Args:
            import_name: Full import name (e.g., "os.system").
            errors: List to append errors to.
            warnings: List to append warnings to.
        """
        # Check if it's a dangerous import
        for dangerous in DANGEROUS_IMPORTS:
            if import_name == dangerous or import_name.startswith(f"{dangerous}."):
                errors.append(f"Dangerous import blocked: {import_name}")
                return

        # Check if it's in the allow list
        base_module = import_name.split(".")[0]
        if base_module not in self._allowed:
            warnings.append(f"Import not in allow list: {import_name}")

    def validate_syntax(self, source_code: str) -> ValidationResult:
        """Validate Python syntax.

        Args:
            source_code: Python source code to validate.

        Returns:
            ValidationResult with any syntax errors.
        """
        errors = []

        try:
            ast.parse(source_code)
        except SyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[],
        )

    def validate_signature(
        self,
        source_code: str,
        expected_input_schema: dict[str, Any],
        expected_output_schema: dict[str, Any],
    ) -> ValidationResult:
        """Validate that component matches expected signature.

        Args:
            source_code: Python source code to validate.
            expected_input_schema: Expected input schema.
            expected_output_schema: Expected output schema.

        Returns:
            ValidationResult with any signature mismatches.
        """
        errors = []
        warnings = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Syntax error: {e}"],
                warnings=[],
            )

        # Look for the main function/class
        has_function = False
        has_class = False
        function_names = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                has_function = True
                function_names.append(node.name)
                # Check function parameters against input schema
                if expected_input_schema.get("properties"):
                    expected_params = set(expected_input_schema["properties"].keys())
                    actual_params = {arg.arg for arg in node.args.args}
                    if not expected_params.issubset(actual_params):
                        missing = expected_params - actual_params
                        errors.append(f"Function {node.name} missing expected parameters: {missing}")
            if isinstance(node, ast.ClassDef):
                has_class = True

        if not has_function and not has_class:
            errors.append("Component must define at least one function or class")

        # Check for required methods if it's a class-based component
        if has_class and not has_function:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    method_names = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
                    if "on_mount" not in method_names:
                        warnings.append(f"Class {node.name} missing on_mount method")
                    if "on_event" not in method_names:
                        warnings.append(f"Class {node.name} missing on_event method")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_security(self, source_code: str) -> ValidationResult:
        """Validate for security vulnerabilities.

        Args:
            source_code: Python source code to validate.

        Returns:
            ValidationResult with any security issues.
        """
        errors = []
        warnings = []

        # Check for hardcoded secrets
        secret_patterns = [
            r'api_key\s*=\s*["\'][\w-]{20,}["\']',
            r'secret\s*=\s*["\'][\w-]{20,}["\']',
            r'password\s*=\s*["\'][\w-]{10,}["\']',
            r'token\s*=\s*["\'][\w-]{20,}["\']',
        ]

        for pattern in secret_patterns:
            if re.search(pattern, source_code, re.IGNORECASE):
                warnings.append("Potential hardcoded secret detected")
                break

        # Check for shell command patterns
        shell_patterns = [
            r'os\.system\(',
            r'subprocess\.(call|run|Popen)\(',
            r'eval\(',
            r'exec\(',
        ]

        for pattern in shell_patterns:
            if re.search(pattern, source_code):
                errors.append(f"Potentially dangerous pattern detected: {pattern}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_all(
        self,
        source_code: str,
        expected_input_schema: dict[str, Any] | None = None,
        expected_output_schema: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Run all validations.

        Args:
            source_code: Python source code to validate.
            expected_input_schema: Optional expected input schema.
            expected_output_schema: Optional expected output schema.

        Returns:
            Combined ValidationResult from all checks.
        """
        all_errors = []
        all_warnings = []

        # Syntax validation
        syntax_result = self.validate_syntax(source_code)
        all_errors.extend(syntax_result.errors)
        all_warnings.extend(syntax_result.warnings)

        if not syntax_result.is_valid:
            return ValidationResult(
                is_valid=False,
                errors=all_errors,
                warnings=all_warnings,
            )

        # Import validation
        import_result = self.validate_imports(source_code)
        all_errors.extend(import_result.errors)
        all_warnings.extend(import_result.warnings)

        # Security validation
        security_result = self.validate_security(source_code)
        all_errors.extend(security_result.errors)
        all_warnings.extend(security_result.warnings)

        # Signature validation (if schemas provided)
        if expected_input_schema and expected_output_schema:
            signature_result = self.validate_signature(
                source_code,
                expected_input_schema,
                expected_output_schema,
            )
            all_errors.extend(signature_result.errors)
            all_warnings.extend(signature_result.warnings)

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
        )
