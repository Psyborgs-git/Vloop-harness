"""Tests for smoke tests."""

import pytest

from harness.engine.smoke_tests import (
    SmokeTestResult,
    SmokeTestRunner,
    SmokeTestSuite,
)


def test_smoke_test_result():
    """Test SmokeTestResult creation and serialization."""
    result = SmokeTestResult(
        test_name="syntax_check",
        passed=True,
        output="Syntax is valid",
        duration_ms=10,
    )
    
    assert result.test_name == "syntax_check"
    assert result.passed is True
    
    data = result.to_dict()
    assert data["test_name"] == "syntax_check"
    assert data["passed"] is True


def test_smoke_test_suite():
    """Test SmokeTestSuite creation and serialization."""
    suite = SmokeTestSuite(
        component_name="test_component",
        tests=[
            SmokeTestResult("test1", True, "ok", None, 10),
            SmokeTestResult("test2", False, "failed", "error", 20),
        ],
        total_tests=2,
        passed_tests=1,
        failed_tests=1,
        duration_ms=30,
    )
    
    assert suite.component_name == "test_component"
    assert suite.passed_tests == 1
    assert suite.failed_tests == 1
    
    data = suite.to_dict()
    assert data["total_tests"] == 2
    assert data["passed_tests"] == 1


def test_smoke_test_runner_syntax_check():
    """Test smoke test runner with syntax check."""
    import asyncio
    
    runner = SmokeTestRunner()
    code = "def test(): return 'hello'"
    
    async def run():
        return await runner.run_tests("test_component", code)
    
    result = asyncio.run(run())
    
    assert isinstance(result, SmokeTestSuite)
    assert result.component_name == "test_component"
    assert result.total_tests > 0


def test_smoke_test_runner_invalid_syntax():
    """Test smoke test runner with invalid syntax."""
    import asyncio
    
    runner = SmokeTestRunner()
    code = "def test(: return 'hello'"
    
    async def run():
        return await runner.run_tests("test_component", code)
    
    result = asyncio.run(run())
    
    assert isinstance(result, SmokeTestSuite)
    assert result.failed_tests > 0


def test_smoke_test_runner_custom_tests():
    """Test smoke test runner with custom test definitions."""
    import asyncio
    
    runner = SmokeTestRunner()
    code = "def test(): return 'hello'"
    custom_tests = [
        {"name": "custom_test", "description": "Custom test", "type": "syntax"},
    ]
    
    async def run():
        return await runner.run_tests("test_component", code, custom_tests)
    
    result = asyncio.run(run())
    
    assert isinstance(result, SmokeTestSuite)
    assert len(result.tests) == 1
