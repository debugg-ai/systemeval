"""
Backward compatibility shim for e2e protocols.

After Phase 2 reorganization, protocols moved to e2e/core/protocols.py
This file provides backward compatibility for imports like:
    from systemeval.e2e.protocols import E2EProvider

Prefer importing from systemeval.e2e directly:
    from systemeval.e2e import E2EProvider
"""

from .core.protocols import (
    E2EProvider,
    E2EOrchestrator,
)

__all__ = [
    "E2EProvider",
    "E2EOrchestrator",
]
