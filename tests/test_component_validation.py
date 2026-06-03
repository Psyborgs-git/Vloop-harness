"""Tests for component validation."""

import pytest

from harness.engine.component_validation import (
    ComponentValidator,
    ValidationResult,
)


def test_validate_syntax_valid():
    """Test syntax validation with valid code."""
    validator = ComponentValidator()
    result = validator.validate_syntax("def test(): return 'hello'")
    
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validate_syntax_invalid():
    """Test syntax validation with invalid code."""
    validator = ComponentValidator()
    result = validator.validate_syntax("def test(: return 'hello'")
    
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert "Syntax error" in result.errors[0]


def test_validate_imports_safe():
    """Test import validation with safe imports."""
    validator = ComponentValidator()
    code = """
import typing
from dataclasses import dataclass
from harness.core.base_component import BaseComponent
"""
    result = validator.validate_imports(code)
    
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validate_imports_dangerous():
    """Test import validation with dangerous imports."""
    validator = ComponentValidator()
    code = """
import os
import subprocess
from eval import eval
"""
    result = validator.validate_imports(code)
    
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert any("dangerous" in error.lower() for error in result.errors)


def test_validate_signature_matching():
    """Test signature validation with matching parameters."""
    validator = ComponentValidator()
    code = """
def process(query: str, context: dict) -> str:
    return query
"""
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "context": {"type": "object"}},
    }
    output_schema = {"type": "string"}
    
    result = validator.validate_signature(code, input_schema, output_schema)
    
    assert result.is_valid is True


def test_validate_signature_mismatch():
    """Test signature validation with missing parameters."""
    validator = ComponentValidator()
    code = """
def process(query: str) -> str:
    return query
"""
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "context": {"type": "object"}},
    }
    output_schema = {"type": "string"}
    
    result = validator.validate_signature(code, input_schema, output_schema)
    
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert "missing expected parameters" in result.errors[0]


def test_validate_security_safe():
    """Test security validation with safe code."""
    validator = ComponentValidator()
    code = """
def process(text: str) -> str:
    return text.upper()
"""
    result = validator.validate_security(code)
    
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validate_security_unsafe():
    """Test security validation with unsafe patterns."""
    validator = ComponentValidator()
    code = """
def process():
    os.system('rm -rf /')
    eval('malicious code')
"""
    result = validator.validate_security(code)
    
    assert result.is_valid is False
    assert len(result.errors) > 0


def test_validate_all_valid():
    """Test comprehensive validation with valid code."""
    validator = ComponentValidator()
    code = """
import typing
from dataclasses import dataclass

def process(query: str) -> str:
    return query.upper()
"""
    result = validator.validate_all(code)
    
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validate_all_invalid():
    """Test comprehensive validation with invalid code."""
    validator = ComponentValidator()
    code = """
import os
import subprocess

def process(:
    os.system('rm -rf /')
"""
    result = validator.validate_all(code)
    
    assert result.is_valid is False
    assert len(result.errors) > 0
