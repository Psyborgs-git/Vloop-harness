"""Dynamic provider configuration and LM factory for the control plane (shim).

All functionality has been split into focused sub-modules.
This module re-exports the public API for backward compatibility.
"""

from core.provider_service import ProviderService
from core.provider_types import PROVIDER_TYPES, ProviderTypeSpec

__all__ = ["ProviderService", "ProviderTypeSpec", "PROVIDER_TYPES"]
