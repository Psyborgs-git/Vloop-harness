"""Secret redaction utilities for sanitizing logs, traces, and telemetry.

This module provides functions to detect and redact sensitive information
from strings, dictionaries, and other data structures before they are
persisted or displayed.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that likely contain secrets
_SECRET_PATTERNS = [
    # API keys (common prefixes)
    r"(?i)(api[_-]?key|apikey|secret[_-]?key|secretkey|access[_-]?key|accesskey)['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?",
    # JWT tokens
    r"eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+",
    # Bearer tokens
    r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}",
    # Basic auth (base64)
    r"(?i)basic\s+[a-zA-Z0-9+/=]{20,}",
    # AWS keys
    r"(?i)aws[_-]?(access[_-]?key[_-]?id|secret[_-]?access[_-]?key)['\"]?\s*[:=]\s*['\"]?([A-Z0-9]{20})['\"]?",
    # Anthropic API keys
    r"sk-ant-[a-zA-Z0-9_\-]{30,}",
    # OpenAI API keys
    r"sk-[a-zA-Z0-9]{48}",
    # Generic API key patterns
    r"[a-zA-Z0-9_\-]{32,}",  # Long alphanumeric strings likely to be keys
]

# Compiled regex patterns
_COMPILED_PATTERNS = [re.compile(pattern) for pattern in _SECRET_PATTERNS]

# Fields that commonly contain secrets
_SECRET_FIELDS = {
    "api_key",
    "apikey",
    "secret",
    "secret_key",
    "secretkey",
    "access_key",
    "accesskey",
    "access_token",
    "accesstoken",
    "auth_token",
    "authtoken",
    "bearer_token",
    "bearertoken",
    "password",
    "passwd",
    "private_key",
    "privatekey",
    "session_token",
    "sessiontoken",
    "token",
    "refresh_token",
    "refreshtoken",
    "client_secret",
    "clientsecret",
    "webhook_secret",
    "webhooksecret",
    "signing_secret",
    "signingsecret",
}


def redact_string(text: str) -> str:
    """Redact potential secrets from a string.
    
    Args:
        text: The input string that may contain secrets.
        
    Returns:
        The string with secrets replaced by [REDACTED].
    """
    if not text:
        return text
    
    result = text
    for pattern in _COMPILED_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    
    return result


def redact_dict(data: dict[str, Any], recursive: bool = True) -> dict[str, Any]:
    """Redact secrets from a dictionary.
    
    This function:
    1. Redacts values for known secret field names
    2. Recursively redacts nested dictionaries if recursive=True
    3. Redacts string values that match secret patterns
    
    Args:
        data: The dictionary to sanitize.
        recursive: Whether to recursively process nested structures.
        
    Returns:
        A new dictionary with secrets redacted.
    """
    if not isinstance(data, dict):
        return data
    
    result = {}
    for key, value in data.items():
        # Check if this is a known secret field
        if isinstance(key, str) and key.lower() in _SECRET_FIELDS:
            result[key] = "[REDACTED]"
            continue
        
        # Process the value based on type
        if isinstance(value, str):
            result[key] = redact_string(value)
        elif isinstance(value, dict) and recursive:
            result[key] = redact_dict(value, recursive)
        elif isinstance(value, list) and recursive:
            result[key] = redact_list(value, recursive)
        else:
            result[key] = value
    
    return result


def redact_list(data: list[Any], recursive: bool = True) -> list[Any]:
    """Redact secrets from a list.
    
    Args:
        data: The list to sanitize.
        recursive: Whether to recursively process nested structures.
        
    Returns:
        A new list with secrets redacted.
    """
    if not isinstance(data, list):
        return data
    
    result = []
    for item in data:
        if isinstance(item, str):
            result.append(redact_string(item))
        elif isinstance(item, dict) and recursive:
            result.append(redact_dict(item, recursive))
        elif isinstance(item, list) and recursive:
            result.append(redact_list(item, recursive))
        else:
            result.append(item)
    
    return result


def redact_any(data: Any) -> Any:
    """Redact secrets from any data structure.
    
    This is a convenience function that dispatches to the appropriate
    redaction function based on the input type.
    
    Args:
        data: The data to sanitize (str, dict, list, or other).
        
    Returns:
        The sanitized data.
    """
    if isinstance(data, str):
        return redact_string(data)
    elif isinstance(data, dict):
        return redact_dict(data)
    elif isinstance(data, list):
        return redact_list(data)
    else:
        return data


def add_secret_pattern(pattern: str) -> None:
    """Add a custom regex pattern for secret detection.
    
    Args:
        pattern: A regex pattern string that matches secrets.
    """
    global _COMPILED_PATTERNS
    _COMPILED_PATTERNS.append(re.compile(pattern))


def add_secret_field(field_name: str) -> None:
    """Add a custom field name that should be treated as a secret.
    
    Args:
        field_name: The field name (case-insensitive).
    """
    _SECRET_FIELDS.add(field_name.lower())
