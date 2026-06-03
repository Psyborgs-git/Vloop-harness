"""Tests for app generator."""

import pytest

from harness.engine.app_generator import (
    AppGenerator,
    AppSpec,
    GeneratedApp,
)


def test_app_spec():
    """Test AppSpec creation and serialization."""
    spec = AppSpec(
        name="test_app",
        description="A test application",
        backend_type="component",
        backend_logic="def run(): pass",
        frontend_views=[{"name": "MainView", "type": "form"}],
    )

    assert spec.name == "test_app"
    assert spec.backend_type == "component"

    data = spec.to_dict()
    restored = AppSpec.from_dict(data)
    assert restored.name == spec.name


def test_app_generator_component_backend():
    """Test generating component backend."""
    generator = AppGenerator()
    spec = AppSpec(
        name="test_app",
        description="Test",
        backend_type="component",
        backend_logic="def process(): return 'hello'",
    )

    result = generator.generate_from_spec(spec)

    assert isinstance(result, GeneratedApp)
    assert "class TestApp" in result.backend_code
    assert "BaseComponent" in result.backend_code


def test_app_generator_pipeline_backend():
    """Test generating pipeline backend."""
    generator = AppGenerator()
    spec = AppSpec(
        name="test_app",
        description="Test",
        backend_type="pipeline",
        backend_logic="def process(): return 'hello'",
    )

    result = generator.generate_from_spec(spec)

    assert isinstance(result, GeneratedApp)
    assert "class TestAppPipeline" in result.backend_code
    assert "dspy.Module" in result.backend_code


def test_app_generator_form_view():
    """Test generating form view."""
    generator = AppGenerator()
    spec = AppSpec(
        name="test_app",
        description="Test",
        backend_type="component",
        backend_logic="def process(): return 'hello'",
        frontend_views=[{
            "name": "MainView",
            "type": "form",
            "fields": [
                {"name": "query", "label": "Query", "type": "text"},
            ],
        }],
    )

    result = generator.generate_from_spec(spec)

    assert "MainView" in result.frontend_code
    assert "TextField" in result.frontend_code["MainView"]


def test_app_generator_list_view():
    """Test generating list view."""
    generator = AppGenerator()
    spec = AppSpec(
        name="test_app",
        description="Test",
        backend_type="component",
        backend_logic="def process(): return 'hello'",
        frontend_views=[{
            "name": "ListView",
            "type": "list",
        }],
    )

    result = generator.generate_from_spec(spec)

    assert "ListView" in result.frontend_code
    assert "List" in result.frontend_code["ListView"]


def test_app_generator_manifest():
    """Test app manifest generation."""
    generator = AppGenerator()
    spec = AppSpec(
        name="test_app",
        description="Test",
        backend_type="component",
        backend_logic="def process(): return 'hello'",
        frontend_views=[{"name": "MainView", "type": "form"}],
    )

    result = generator.generate_from_spec(spec)

    assert result.app_manifest["name"] == "test_app"
    assert "react_views" in result.app_manifest
    assert "MainView" in result.app_manifest["react_views"]
