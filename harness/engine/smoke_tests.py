"""Deterministic smoke tests for component validation.

This module provides a framework for running smoke tests on components
to ensure they can be instantiated and execute basic operations correctly.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SmokeTestResult:
    """Result of a single smoke test."""
    
    test_name: str
    passed: bool
    output: str
    error: str | None = None
    duration_ms: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "passed": self.passed,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SmokeTestSuite:
    """Results of running all smoke tests for a component."""
    
    component_name: str
    tests: list[SmokeTestResult]
    total_tests: int
    passed_tests: int
    failed_tests: int
    duration_ms: int
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "component_name": self.component_name,
            "tests": [t.to_dict() for t in self.tests],
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "duration_ms": self.duration_ms,
        }


class SmokeTestRunner:
    """Runs deterministic smoke tests on component source code."""
    
    def __init__(self, timeout_seconds: int = 30) -> None:
        """Initialize the smoke test runner.
        
        Args:
            timeout_seconds: Maximum time to wait for each test.
        """
        self._timeout = timeout_seconds
    
    async def run_tests(
        self,
        component_name: str,
        source_code: str,
        test_definitions: list[dict[str, Any]] | None = None,
    ) -> SmokeTestSuite:
        """Run all smoke tests for a component.
        
        Args:
            component_name: Name of the component.
            source_code: Python source code of the component.
            test_definitions: Optional custom test definitions.
            
        Returns:
            SmokeTestSuite with all test results.
        """
        import time
        
        start_time = time.time()
        results = []
        
        # Use default tests if none provided
        if test_definitions is None:
            test_definitions = self._get_default_tests()
        
        for test_def in test_definitions:
            result = await self._run_single_test(
                component_name,
                source_code,
                test_def,
            )
            results.append(result)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        
        return SmokeTestSuite(
            component_name=component_name,
            tests=results,
            total_tests=len(results),
            passed_tests=passed,
            failed_tests=failed,
            duration_ms=duration_ms,
        )
    
    def _get_default_tests(self) -> list[dict[str, Any]]:
        """Get default smoke test definitions."""
        return [
            {
                "name": "syntax_check",
                "description": "Check if code has valid Python syntax",
                "type": "syntax",
            },
            {
                "name": "import_check",
                "description": "Check if code can be imported without errors",
                "type": "import",
            },
            {
                "name": "instantiation_check",
                "description": "Check if component can be instantiated",
                "type": "instantiation",
            },
        ]
    
    async def _run_single_test(
        self,
        component_name: str,
        source_code: str,
        test_def: dict[str, Any],
    ) -> SmokeTestResult:
        """Run a single smoke test.
        
        Args:
            component_name: Name of the component.
            source_code: Python source code.
            test_def: Test definition.
            
        Returns:
            SmokeTestResult for this test.
        """
        import time
        
        test_name = test_def["name"]
        test_type = test_def["type"]
        start_time = time.time()
        
        try:
            if test_type == "syntax":
                output = self._test_syntax(source_code)
                passed = True
                error = None
            elif test_type == "import":
                output = await self._test_import(component_name, source_code)
                passed = True
                error = None
            elif test_type == "instantiation":
                output = await self._test_instantiation(component_name, source_code)
                passed = True
                error = None
            else:
                output = f"Unknown test type: {test_type}"
                passed = False
                error = "Unknown test type"
        except Exception as e:
            output = ""
            passed = False
            error = f"{type(e).__name__}: {str(e)}"
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return SmokeTestResult(
            test_name=test_name,
            passed=passed,
            output=str(output),
            error=error,
            duration_ms=duration_ms,
        )
    
    def _test_syntax(self, source_code: str) -> str:
        """Test if source code has valid Python syntax."""
        import ast
        
        try:
            ast.parse(source_code)
            return "Syntax is valid"
        except SyntaxError as e:
            raise Exception(f"Syntax error at line {e.lineno}: {e.msg}")
    
    async def _test_import(self, component_name: str, source_code: str) -> str:
        """Test if source code can be imported without errors."""
        # Create a temporary module
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / f"{component_name}.py"
            module_path.write_text(source_code, encoding="utf-8")
            
            # Add tmpdir to sys.path temporarily
            sys.path.insert(0, tmpdir)
            try:
                spec = importlib.util.spec_from_file_location(component_name, module_path)
                if spec is None or spec.loader is None:
                    raise Exception("Could not create module spec")
                
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                return "Module imported successfully"
            finally:
                sys.path.remove(tmpdir)
    
    async def _test_instantiation(self, component_name: str, source_code: str) -> str:
        """Test if component can be instantiated."""
        import ast
        
        # Parse to find the main class
        tree = ast.parse(source_code)
        class_names = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_names.append(node.name)
        
        if not class_names:
            return "No classes found to instantiate (function-based component)"
        
        # Try to instantiate the first class
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / f"{component_name}.py"
            module_path.write_text(source_code, encoding="utf-8")
            
            sys.path.insert(0, tmpdir)
            try:
                spec = importlib.util.spec_from_file_location(component_name, module_path)
                if spec is None or spec.loader is None:
                    raise Exception("Could not create module spec")
                
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Try to instantiate the class
                cls = getattr(module, class_names[0])
                
                # Check if it requires arguments
                import inspect
                sig = inspect.signature(cls.__init__)
                params = list(sig.parameters.keys())
                
                # Remove 'self' if present
                if params and params[0] == "self":
                    params = params[1:]
                
                if params:
                    return f"Class {class_names[0]} requires parameters: {params}"
                
                # Try instantiation
                cls()
                return f"Successfully instantiated {class_names[0]}"
            finally:
                sys.path.remove(tmpdir)
