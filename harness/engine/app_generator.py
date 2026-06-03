"""Spec-to-app generator for creating full-stack applications.

This module provides functionality to generate both backend (Python component/DSPy pipeline)
and frontend (React) code from a single application specification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppSpec:
    """Specification for a full-stack application."""

    name: str
    description: str
    backend_type: str  # "component" | "pipeline" | "dspy_module"
    backend_logic: str  # Python code or DSPy pipeline definition
    frontend_views: list[dict[str, Any]] = field(default_factory=list)
    state_schema: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "backend_type": self.backend_type,
            "backend_logic": self.backend_logic,
            "frontend_views": self.frontend_views,
            "state_schema": self.state_schema,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSpec:
        return cls(
            name=data["name"],
            description=data["description"],
            backend_type=data["backend_type"],
            backend_logic=data["backend_logic"],
            frontend_views=data.get("frontend_views", []),
            state_schema=data.get("state_schema", {}),
            permissions=data.get("permissions", []),
        )


@dataclass
class GeneratedApp:
    """Result of app generation."""

    backend_code: str
    frontend_code: dict[str, str]  # Map of view name to React code
    app_manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_code": self.backend_code,
            "frontend_code": self.frontend_code,
            "app_manifest": self.app_manifest,
        }


class AppGenerator:
    """Generates full-stack applications from specifications."""

    def __init__(self) -> None:
        """Initialize the app generator."""
        pass

    def generate_from_spec(self, spec: AppSpec) -> GeneratedApp:
        """Generate a full-stack app from a specification.

        Args:
            spec: The application specification.

        Returns:
            GeneratedApp with backend code, frontend code, and manifest.
        """
        # Generate backend code
        backend_code = self._generate_backend(spec)

        # Generate frontend code for each view
        frontend_code = {}
        for view_spec in spec.frontend_views:
            view_name = view_spec.get("name", "View")
            frontend_code[view_name] = self._generate_view(view_spec, spec)

        # Generate app manifest
        app_manifest = self._generate_manifest(spec, list(frontend_code.keys()))

        return GeneratedApp(
            backend_code=backend_code,
            frontend_code=frontend_code,
            app_manifest=app_manifest,
        )

    def _generate_backend(self, spec: AppSpec) -> str:
        """Generate backend code from spec.

        Args:
            spec: The application specification.

        Returns:
            Python code for the backend.
        """
        if spec.backend_type == "component":
            return self._generate_component_backend(spec)
        elif spec.backend_type == "pipeline":
            return self._generate_pipeline_backend(spec)
        elif spec.backend_type == "dspy_module":
            return self._generate_dspy_module_backend(spec)
        else:
            raise ValueError(f"Unknown backend type: {spec.backend_type}")

    def _generate_component_backend(self, spec: AppSpec) -> str:
        """Generate a Python component backend.

        Args:
            spec: The application specification.

        Returns:
            Python component code.
        """
        # Wrap the provided logic in a component structure
        code = f'''"""Auto-generated component: {spec.name}

{spec.description}
"""

from __future__ import annotations

from typing import Any
from harness.core.base_component import BaseComponent


class {self._to_class_name(spec.name)}(BaseComponent):
    """Auto-generated component for {spec.name}."""

    def on_mount(self) -> None:
        """Initialize the component."""
        self.state = {json.dumps(spec.state_schema, indent=4)}

    def on_event(self, event: str, payload: dict[str, Any]) -> Any:
        """Handle events from the UI."""
        # User-provided logic
{self._indent_code(spec.backend_logic, 8)}

        return {{"result": "processed"}}
'''
        return code

    def _generate_pipeline_backend(self, spec: AppSpec) -> str:
        """Generate a DSPy pipeline backend.

        Args:
            spec: The application specification.

        Returns:
            DSPy pipeline code.
        """
        code = f'''"""Auto-generated DSPy pipeline: {spec.name}

{spec.description}
"""

from __future__ import annotations

import dspy
from typing import Any


class {self._to_class_name(spec.name)}Pipeline(dspy.Module):
    """Auto-generated DSPy pipeline for {spec.name}."""

    def __init__(self) -> None:
        super().__init__()
        # Initialize DSPy modules here
        self.reasoner = dspy.ChainOfThought("{spec.description}")

    def forward(self, **kwargs) -> dspy.Prediction:
        """Execute the pipeline."""
        # User-provided logic
{self._indent_code(spec.backend_logic, 8)}

        return dspy.Prediction(result="processed")
'''
        return code

    def _generate_dspy_module_backend(self, spec: AppSpec) -> str:
        """Generate a DSPy module backend.

        Args:
            spec: The application specification.

        Returns:
            DSPy module code.
        """
        code = f'''"""Auto-generated DSPy module: {spec.name}

{spec.description}
"""

from __future__ import annotations

import dspy
from typing import Any


class {self._to_class_name(spec.name)}Module(dspy.Module):
    """Auto-generated DSPy module for {spec.name}."""

    def __init__(self) -> None:
        super().__init__()
        # User-provided logic
{self._indent_code(spec.backend_logic, 8)}

    def forward(self, **kwargs) -> dspy.Prediction:
        """Execute the module."""
        # Implement forward pass
        return dspy.Prediction(result="processed")
'''
        return code

    def _generate_view(self, view_spec: dict[str, Any], spec: AppSpec) -> str:
        """Generate React view code from spec.

        Args:
            view_spec: The view specification.
            spec: The overall application specification.

        Returns:
            React TypeScript code.
        """
        view_spec.get("name", "View")
        view_type = view_spec.get("type", "form")

        if view_type == "form":
            return self._generate_form_view(view_spec, spec)
        elif view_type == "list":
            return self._generate_list_view(view_spec, spec)
        elif view_type == "dashboard":
            return self._generate_dashboard_view(view_spec, spec)
        else:
            return self._generate_generic_view(view_spec, spec)

    def _generate_form_view(self, view_spec: dict[str, Any], spec: AppSpec) -> str:
        """Generate a form view.

        Args:
            view_spec: The view specification.
            spec: The overall application specification.

        Returns:
            React form component code.
        """
        fields = view_spec.get("fields", [])
        field_code = self._generate_form_fields(fields)

        code = f'''/**
 * Auto-generated form view: {view_spec.get("name", "View")}
 */

import {{ useState }} from "react";
import {{ Box, Button, TextField, Typography }} from "@mui/material";
import {{ useHarness }} from "./hooks";

export default function {self._to_class_name(view_spec.get("name", "View"))}View() {{
  const {{ state, emit }} = useHarness();
  const [formData, setFormData] = useState<Record<string, any>>({{}});

  const handleSubmit = async () => {{
    await emit("submit", formData);
  }};

  return (
    <Box sx={{
      p: 2,
      display: "flex",
      flexDirection: "column",
      gap: 2,
    }}>
      <Typography variant="h6">{view_spec.get("title", "Form")}</Typography>
      <Typography variant="body2" color="text.secondary">
        {view_spec.get("description", "")}
      </Typography>

{field_code}

      <Button variant="contained" onClick={{handleSubmit}}>
        Submit
      </Button>
    </Box>
  );
}}
'''
        return code

    def _generate_form_fields(self, fields: list[dict[str, Any]]) -> str:
        """Generate form field code.

        Args:
            fields: List of field specifications.

        Returns:
            Indented React code for fields.
        """
        code = ""
        for field in fields:
            field_name = field.get("name", "field")
            field_label = field.get("label", field_name)
            field_type = field.get("type", "text")

            code += '      <TextField\n'
            code += f'        label="{field_label}"\n'
            code += f'        type="{field_type}"\n'
            code += f'        value={{formData["{field_name}"] || ""}}\n'
            code += f'        onChange={{(e) => setFormData({{ ...formData, "{field_name}": e.target.value }})}}\n'
            code += '        fullWidth\n'
            code += '        size="small"\n'
            code += '      />\n'

        return code

    def _generate_list_view(self, view_spec: dict[str, Any], spec: AppSpec) -> str:
        """Generate a list view.

        Args:
            view_spec: The view specification.
            spec: The overall application specification.

        Returns:
            React list component code.
        """
        code = f'''/**
 * Auto-generated list view: {view_spec.get("name", "View")}
 */

import {{ Box, List, ListItem, ListItemText, Typography }} from "@mui/material";
import {{ useHarness }} from "./hooks";

export default function {self._to_class_name(view_spec.get("name", "View"))}View() {{
  const {{ state }} = useHarness();
  const items = state?.items || [];

  return (
    <Box sx={{
      p: 2,
    }}>
      <Typography variant="h6">{view_spec.get("title", "List")}</Typography>
      <List>
        {{items.map((item: any, index: number) => (
          <ListItem key={{index}}>
            <ListItemText
              primary={{item.name || item.title || "Item " + index}}
              secondary={{item.description || ""}}
            />
          </ListItem>
        ))}}
      </List>
    </Box>
  );
}}
'''
        return code

    def _generate_dashboard_view(self, view_spec: dict[str, Any], spec: AppSpec) -> str:
        """Generate a dashboard view.

        Args:
            view_spec: The view specification.
            spec: The overall application specification.

        Returns:
            React dashboard component code.
        """
        code = f'''/**
 * Auto-generated dashboard view: {view_spec.get("name", "View")}
 */

import {{ Box, Typography, Paper }} from "@mui/material";
import {{ useHarness }} from "./hooks";

export default function {self._to_class_name(view_spec.get("name", "View"))}View() {{
  const {{ state }} = useHarness();

  return (
    <Box sx={{
      p: 2,
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
      gap: 2,
    }}>
      <Typography variant="h6" sx={{
        gridColumn: "1 / -1",
      }}>
        {view_spec.get("title", "Dashboard")}
      </Typography>

      <Paper sx={{
        p: 2,
      }}>
        <Typography variant="body2">Dashboard content</Typography>
      </Paper>
    </Box>
  );
}}
'''
        return code

    def _generate_generic_view(self, view_spec: dict[str, Any], spec: AppSpec) -> str:
        """Generate a generic view.

        Args:
            view_spec: The view specification.
            spec: The overall application specification.

        Returns:
            React component code.
        """
        code = f'''/**
 * Auto-generated view: {view_spec.get("name", "View")}
 */

import {{ Box, Typography }} from "@mui/material";
import {{ useHarness }} from "./hooks";

export default function {self._to_class_name(view_spec.get("name", "View"))}View() {{
  const {{ state }} = useHarness();

  return (
    <Box sx={{
      p: 2,
    }}>
      <Typography variant="h6">{view_spec.get("title", "View")}</Typography>
      <Typography variant="body2">
        {view_spec.get("description", "")}
      </Typography>
    </Box>
  );
}}
'''
        return code

    def _generate_manifest(self, spec: AppSpec, view_names: list[str]) -> dict[str, Any]:
        """Generate an app manifest.

        Args:
            spec: The application specification.
            view_names: List of generated view names.

        Returns:
            App manifest dictionary.
        """
        return {
            "name": spec.name,
            "description": spec.description,
            "backend_type": spec.backend_type,
            "react_views": view_names,
            "permissions": spec.permissions,
            "state_schema": spec.state_schema,
            "status": "draft",
        }

    def _to_class_name(self, name: str) -> str:
        """Convert a name to a valid class name.

        Args:
            name: The name to convert.

        Returns:
            A valid class name.
        """
        # Remove special characters and convert to PascalCase
        import re
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        parts = cleaned.split('_')
        return ''.join(part.capitalize() for part in parts)

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code by a number of spaces.

        Args:
            code: The code to indent.
            spaces: Number of spaces to indent.

        Returns:
            Indented code.
        """
        indent = ' ' * spaces
        return '\n'.join(indent + line if line.strip() else '' for line in code.split('\n'))
