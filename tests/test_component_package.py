"""Tests for component package format."""

import pytest

from harness.engine.component_package import (
    ComponentDependencies,
    ComponentMetadata,
    ComponentPackage,
    ComponentSignature,
    ComponentTests,
    OptimizerConfig,
    create_package_from_source,
)


def test_component_metadata():
    """Test ComponentMetadata creation and serialization."""
    metadata = ComponentMetadata(
        name="test_component",
        version="1.0.0",
        description="A test component",
        author="Test Author",
        tags=["test", "example"],
        category="general",
    )

    assert metadata.name == "test_component"
    assert metadata.version == "1.0.0"

    # Test to_dict
    data = metadata.to_dict()
    assert data["name"] == "test_component"
    assert data["tags"] == ["test", "example"]

    # Test from_dict
    restored = ComponentMetadata.from_dict(data)
    assert restored.name == metadata.name
    assert restored.version == metadata.version


def test_component_signature():
    """Test ComponentSignature creation and serialization."""
    signature = ComponentSignature(
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "string"},
        required_permissions=["read"],
    )

    assert signature.input_schema["properties"]["query"]["type"] == "string"

    data = signature.to_dict()
    restored = ComponentSignature.from_dict(data)
    assert restored.input_schema == signature.input_schema


def test_component_dependencies():
    """Test ComponentDependencies creation and serialization."""
    deps = ComponentDependencies(
        python_packages=["dspy", "openai"],
        harness_components=["base_component"],
        external_apis=["openai"],
    )

    assert len(deps.python_packages) == 2

    data = deps.to_dict()
    restored = ComponentDependencies.from_dict(data)
    assert restored.python_packages == deps.python_packages


def test_component_tests():
    """Test ComponentTests creation and serialization."""
    tests = ComponentTests(
        smoke_tests=[{"name": "syntax_check"}],
        integration_tests=[{"name": "full_flow"}],
        eval_dataset_id="test_dataset_123",
    )

    assert len(tests.smoke_tests) == 1
    assert tests.eval_dataset_id == "test_dataset_123"

    data = tests.to_dict()
    restored = ComponentTests.from_dict(data)
    assert restored.eval_dataset_id == tests.eval_dataset_id


def test_optimizer_config():
    """Test OptimizerConfig creation and serialization."""
    config = OptimizerConfig(
        optimizer_type="BootstrapFewShot",
        max_rounds=15,
        max_labeled_demos=8,
        metric="exact_match",
        eval_threshold=0.9,
    )

    assert config.optimizer_type == "BootstrapFewShot"
    assert config.max_rounds == 15

    data = config.to_dict()
    restored = OptimizerConfig.from_dict(data)
    assert restored.max_rounds == config.max_rounds


def test_component_package():
    """Test ComponentPackage creation and checksum verification."""
    metadata = ComponentMetadata(
        name="test_component",
        version="1.0.0",
        description="A test component",
    )
    signature = ComponentSignature(
        input_schema={"type": "object"},
        output_schema={"type": "string"},
    )
    dependencies = ComponentDependencies()
    tests = ComponentTests()
    optimizer_config = OptimizerConfig()
    source_code = "def test(): return 'hello'"

    package = ComponentPackage(
        metadata=metadata,
        signature=signature,
        dependencies=dependencies,
        tests=tests,
        source_code=source_code,
        optimizer_config=optimizer_config,
    )

    assert package.checksum != ""
    assert package.verify_checksum() is True

    # Test serialization
    data = package.to_dict()
    assert "optimizer_config" in data
    assert data["optimizer_config"]["optimizer_type"] == "BootstrapFewShot"

    restored = ComponentPackage.from_dict(data)
    assert restored.metadata.name == metadata.name
    assert restored.verify_checksum() is True


def test_create_package_from_source():
    """Test creating a package from source code."""
    source_code = """
def process(query: str) -> str:
    return query.upper()
"""

    package = create_package_from_source(
        name="text_processor",
        source_code=source_code,
        description="Processes text",
        version="1.0.0",
        author="Test",
    )

    assert package.metadata.name == "text_processor"
    assert package.source_code == source_code
    assert package.checksum != ""
    assert package.verify_checksum() is True


def test_app_spec():
    """Test AppSpec creation and serialization."""
    from harness.engine.app_generator import AppSpec

    spec = AppSpec(
        name="test_app",
        description="A test application",
        backend_type="component",
        backend_logic="def run(): pass",
        frontend_views=[{"name": "MainView", "type": "form"}],
        state_schema={"counter": 0},
        permissions=["read"],
    )

    assert spec.backend_type == "component"
    assert len(spec.frontend_views) == 1

    data = spec.to_dict()
    restored = AppSpec.from_dict(data)
    assert restored.name == spec.name
    assert restored.frontend_views == spec.frontend_views
