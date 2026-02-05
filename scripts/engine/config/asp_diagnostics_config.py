"""
ASP Diagnostics Configuration - Debug settings for ASP universe diagnostics.

Phase 8.8: Lightweight instrumentation for ASP universe size.
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain import ASPDiagnosticsCollector

# Global flag - disabled by default
_DIAGNOSTICS_ENABLED: bool = False

# Global collector instance for convenience
_global_collector: Optional['ASPDiagnosticsCollector'] = None
