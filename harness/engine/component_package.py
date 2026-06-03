"""Component package format for stable, versioned AI components.

This module defines the structure and validation for component packages,
which include metadata, source code, tests, dependencies, and versioning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import ast


@dataclass
class ComponentMetadata:
    """Metadata for a component package."""

    name: str
    version: str
    description: str
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    category: str = "general"
    dspy_version: str = "2.5+"
    harness_version: str = "1.0+"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "category": self.category,
            "dspy_version": self.dspy_version,
            "harness_version": self.harness_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentMetadata":
        return cls(
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data.get("author", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            tags=data.get("tags", []),
            category=data.get("category", "general"),
            dspy_version=data.get("dspy_version", "2.5+"),
            harness_version=data.get("harness_version", "1.0+"),
        )


@dataclass
class ComponentSignature:
    """Expected signature for a component."""

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "required_permissions": self.required_permissions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentSignature":
        return cls(
            input_schema=data["input_schema"],
            output_schema=data["output_schema"],
            required_permissions=data.get("required_permissions", []),
        )


@dataclass
class ComponentDependencies:
    """Dependencies for a component."""

    python_packages: list[str] = field(default_factory=list)
    harness_components: list[str] = field(default_factory=list)
    external_apis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_packages": self.python_packages,
            "harness_components": self.harness_components,
            "external_apis": self.external_apis,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentDependencies":
        return cls(
            python_packages=data.get("python_packages", []),
            harness_components=data.get("harness_components", []),
            external_apis=data.get("external_apis", []),
        )


@dataclass
class ComponentTests:
    """Test definitions for a component."""

    smoke_tests: list[dict[str, Any]] = field(default_factory=list)
    integration_tests: list[dict[str, Any]] = field(default_factory=list)
    eval_dataset_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "smoke_tests": self.smoke_tests,
            "integration_tests": self.integration_tests,
            "eval_dataset_id": self.eval_dataset_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentTests":
        return cls(
            smoke_tests=data.get("smoke_tests", []),
            integration_tests=data.get("integration_tests", []),
            eval_dataset_id=data.get("eval_dataset_id"),
        )


@dataclass
class OptimizerConfig:
    """DSPy optimizer configuration for a component."""

    optimizer_type: str = "BootstrapFewShot"
    max_rounds: int = 10
    max_labeled_demos: int = 5
    max_bootstrapped_demos: int = 5
    teacher_settings: dict[str, Any] = field(default_factory=dict)
    metric: str = "exact_match"
    eval_threshold: float = 0.8

    def to_dict(self) -> dict[str, Any]:
        return {
            "optimizer_type": self.optimizer_type,
            "max_rounds": self.max_rounds,
            "max_labeled_demos": self.max_labeled_demos,
            "max_bootstrapped_demos": self.max_bootstrapped_demos,
            "teacher_settings": self.teacher_settings,
            "metric": self.metric,
            "eval_threshold": self.eval_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OptimizerConfig":
        return cls(
            optimizer_type=data.get("optimizer_type", "BootstrapFewShot"),
            max_rounds=data.get("max_rounds", 10),
            max_labeled_demos=data.get("max_labeled_demos", 5),
            max_bootstrapped_demos=data.get("max_bootstrapped_demos", 5),
            teacher_settings=data.get("teacher_settings", {}),
            metric=data.get("metric", "exact_match"),
            eval_threshold=data.get("eval_threshold", 0.8),
        )


@dataclass
class ComponentPackage:
    """Complete component package with all metadata and code."""

    metadata: ComponentMetadata
    signature: ComponentSignature
    dependencies: ComponentDependencies
    tests: ComponentTests
    source_code: str
    optimizer_config: OptimizerConfig | None = None
    checksum: str = ""

    def __post_init__(self) -> None:
        """Calculate checksum after initialization."""
        if not self.checksum:
            self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        """Calculate SHA256 checksum of the package."""
        content = json.dumps({
            "metadata": self.metadata.to_dict(),
            "signature": self.signature.to_dict(),
            "dependencies": self.dependencies.to_dict(),
            "tests": self.tests.to_dict(),
            "source_code": self.source_code,
            "optimizer_config": self.optimizer_config.to_dict() if self.optimizer_config else None,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "signature": self.signature.to_dict(),
            "dependencies": self.dependencies.to_dict(),
            "tests": self.tests.to_dict(),
            "source_code": self.source_code,
            "optimizer_config": self.optimizer_config.to_dict() if self.optimizer_config else None,
            "checksum": self.checksum,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentPackage":
        return cls(
            metadata=ComponentMetadata.from_dict(data["metadata"]),
            signature=ComponentSignature.from_dict(data["signature"]),
            dependencies=ComponentDependencies.from_dict(data["dependencies"]),
            tests=ComponentTests.from_dict(data["tests"]),
            source_code=data["source_code"],
            optimizer_config=OptimizerConfig.from_dict(data["optimizer_config"]) if data.get("optimizer_config") else None,
            checksum=data.get("checksum", ""),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ComponentPackage":
        return cls.from_dict(json.loads(json_str))

    def verify_checksum(self) -> bool:
        """Verify that the checksum matches the content."""
        calculated = self._calculate_checksum()
        return calculated == self.checksum

    def save_to_file(self, path: Path) -> None:
        """Save package to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path) -> "ComponentPackage":
        """Load package from a JSON file."""
        return cls.from_json(path.read_text(encoding="utf-8"))


def create_package_from_source(
    name: str,
    source_code: str,
    description: str,
    version: str = "1.0.0",
    author: str = "",
    tags: list[str] | None = None,
    category: str = "general",
) -> ComponentPackage:
    """Create a component package from source code.

    This function analyzes the source code to extract signature information
    and creates a complete package.

    Args:
        name: Component name.
        source_code: Python source code.
        description: Component description.
        version: Component version.
        author: Component author.
        tags: Component tags.
        category: Component category.

    Returns:
        A ComponentPackage instance.
    """
    # Parse source to extract signature info
    input_schema = {"type": "object", "properties": {}}
    output_schema = {"type": "object", "properties": {}}
    required_permissions = []

    try:
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Look for function annotations
                for arg in node.args.args:
                    if arg.annotation:
                        input_schema["properties"][arg.arg] = {"type": "string"}
                if node.returns:
                    output_schema["type"] = "string"
    except SyntaxError:
        pass  # Use default schemas if parsing fails

    metadata = ComponentMetadata(
        name=name,
        version=version,
        description=description,
        author=author,
        tags=tags or [],
        category=category,
    )

    signature = ComponentSignature(
        input_schema=input_schema,
        output_schema=output_schema,
        required_permissions=required_permissions,
    )

    dependencies = ComponentDependencies()
    tests = ComponentTests()

    return ComponentPackage(
        metadata=metadata,
        signature=signature,
        dependencies=dependencies,
        tests=tests,
        source_code=source_code,
    )
