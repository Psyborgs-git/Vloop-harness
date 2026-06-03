"""React view validation utilities for isolated rendering checks.

This module provides functions to validate React/TypeScript views
by checking syntax, imports, and basic rendering capability.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List


@dataclass
class ViewValidationResult:
    """Result of a view validation."""
    
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ViewValidator:
    """Validates React/TypeScript views for correctness."""
    
    def __init__(self, project_root: Path | None = None) -> None:
        """Initialize the view validator.
        
        Args:
            project_root: Path to the React project root.
        """
        self._project_root = project_root or Path.cwd()
    
    def validate_syntax(self, source_code: str) -> ViewValidationResult:
        """Validate TypeScript syntax.
        
        Args:
            source_code: TypeScript source code to validate.
            
        Returns:
            ViewValidationResult with any syntax errors.
        """
        errors = []
        warnings = []
        
        # Basic syntax checks
        if not source_code.strip():
            errors.append("Source code is empty")
            return ViewValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        # Check for basic React structure
        if "export default" not in source_code and "export const" not in source_code:
            warnings.append("No default export found - component may not be importable")
        
        # Check for React import
        if "react" not in source_code.lower() and "@mui" not in source_code.lower():
            warnings.append("No React or MUI imports detected")
        
        # Check for common TypeScript errors
        if "interface Props" in source_code and "Props" not in source_code.split("interface Props")[1].split("{")[0]:
            warnings.append("Props interface defined but may not be used")
        
        return ViewValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    def validate_with_tsc(self, source_code: str, filename: str = "View.tsx") -> ViewValidationResult:
        """Validate using TypeScript compiler if available.
        
        Args:
            source_code: TypeScript source code to validate.
            filename: Virtual filename for the source.
            
        Returns:
            ViewValidationResult with any TypeScript errors.
        """
        errors = []
        warnings = []
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Write the source to a temporary file
                source_file = Path(tmpdir) / filename
                source_file.write_text(source_code, encoding="utf-8")
                
                # Create a minimal tsconfig.json
                tsconfig = {
                    "compilerOptions": {
                        "target": "ES2020",
                        "module": "ESNext",
                        "jsx": "react",
                        "strict": True,
                        "esModuleInterop": True,
                        "skipLibCheck": True,
                        "moduleResolution": "node",
                    },
                    "include": [filename],
                }
                
                tsconfig_file = Path(tmpdir) / "tsconfig.json"
                tsconfig_file.write_text(
                    __import__("json").dumps(tsconfig),
                    encoding="utf-8"
                )
                
                # Run tsc
                result = subprocess.run(
                    ["tsc", "--noEmit"],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode != 0:
                    # Parse TypeScript errors
                    for line in result.stderr.split("\n"):
                        if "error TS" in line:
                            errors.append(line.strip())
                
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # tsc not available or timed out - skip this check
            warnings.append("TypeScript compiler not available - skipping type checking")
        except Exception as e:
            warnings.append(f"TypeScript validation failed: {e}")
        
        return ViewValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    def validate_imports(self, source_code: str) -> ViewValidationResult:
        """Validate imports in the source code.
        
        Args:
            source_code: TypeScript source code to validate.
            
        Returns:
            ViewValidationResult with any import issues.
        """
        errors = []
        warnings = []
        
        # Extract import statements
        import_pattern = r'import\s+(?:\{[^}]*\}\s+from\s+)?["\']([^"\']+)["\']'
        imports = re.findall(import_pattern, source_code)
        
        # Check for common patterns
        for imp in imports:
            # Check for relative imports that might be invalid
            if imp.startswith("./") or imp.startswith("../"):
                # Could be valid, just warn
                pass
            # Check for node_modules imports
            elif not imp.startswith("@") and "." in imp:
                warnings.append(f"Potential missing package: {imp}")
        
        # Check for duplicate imports
        seen = set()
        for imp in imports:
            if imp in seen:
                warnings.append(f"Duplicate import: {imp}")
            seen.add(imp)
        
        return ViewValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    def validate_component_structure(self, source_code: str) -> ViewValidationResult:
        """Validate basic component structure.
        
        Args:
            source_code: TypeScript source code to validate.
            
        Returns:
            ViewValidationResult with any structural issues.
        """
        errors = []
        warnings = []
        
        # Check for function component
        if "function" in source_code or "const" in source_code:
            # Look for return statement
            if "return" not in source_code:
                errors.append("Component function has no return statement")
        
        # Check for hooks usage
        if "useState" in source_code or "useEffect" in source_code:
            if "import" not in source_code:
                errors.append("Hooks used but not imported")
        
        # Check for JSX
        if "<" not in source_code or ">" not in source_code:
            warnings.append("No JSX detected - component may not render anything")
        
        return ViewValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    def validate_all(self, source_code: str, filename: str = "View.tsx") -> ViewValidationResult:
        """Run all validations.
        
        Args:
            source_code: TypeScript source code to validate.
            filename: Virtual filename for the source.
            
        Returns:
            Combined ViewValidationResult from all checks.
        """
        all_errors = []
        all_warnings = []
        
        # Syntax validation
        syntax_result = self.validate_syntax(source_code)
        all_errors.extend(syntax_result.errors)
        all_warnings.extend(syntax_result.warnings)
        
        if not syntax_result.is_valid:
            return ViewValidationResult(
                is_valid=False,
                errors=all_errors,
                warnings=all_warnings,
            )
        
        # Import validation
        import_result = self.validate_imports(source_code)
        all_errors.extend(import_result.errors)
        all_warnings.extend(import_result.warnings)
        
        # Structure validation
        structure_result = self.validate_component_structure(source_code)
        all_errors.extend(structure_result.errors)
        all_warnings.extend(structure_result.warnings)
        
        # TypeScript validation (if available)
        tsc_result = self.validate_with_tsc(source_code, filename)
        all_errors.extend(tsc_result.errors)
        all_warnings.extend(tsc_result.warnings)
        
        return ViewValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
        )
