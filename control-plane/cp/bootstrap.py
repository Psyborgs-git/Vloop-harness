"""Control-plane bootstrap (shim).

All functionality has been split into focused sub-modules.
This module re-exports the public API for backward compatibility.
"""

from cp.application import ControlPlaneApplication, bootstrap
from cp.runtime import ControlPlaneRuntime
from cp.session import SessionSnapshot

__all__ = [
    "ControlPlaneApplication",
    "ControlPlaneRuntime",
    "SessionSnapshot",
    "bootstrap",
]
