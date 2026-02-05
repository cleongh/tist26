"""
ASP Diagnostics Generator - Manages ASP diagnostics collection and reporting.

Phase 8.8: Lightweight instrumentation for ASP universe size.

Per LOGIC_DESIGN.md Section 8: No runtime overhead when disabled.
"""

import logging
from typing import Optional

from .domain import ASPUniverseStats, ASPDiagnosticsCollector
from .config import asp_diagnostics_config as diag_config

logger = logging.getLogger(__name__)


class ASPDiagnosticsGenerator:
    """
    Manages ASP diagnostics collection and reporting.
    
    Provides static methods for:
        - Enabling/disabling diagnostics
        - Managing the global collector
        - Logging ASP universe statistics
    """
    
    def __init__(self):
        """Initialize the ASPDiagnosticsGenerator."""
        pass
    
    @staticmethod
    def enable() -> None:
        """Enable ASP diagnostics programmatically."""
        diag_config._DIAGNOSTICS_ENABLED = True
        logger.info("ASP diagnostics enabled")
    
    @staticmethod
    def disable() -> None:
        """Disable ASP diagnostics programmatically."""
        diag_config._DIAGNOSTICS_ENABLED = False
    
    @staticmethod
    def is_enabled() -> bool:
        """Check if ASP diagnostics are enabled."""
        return diag_config._DIAGNOSTICS_ENABLED
    
    @staticmethod
    def get_collector() -> ASPDiagnosticsCollector:
        """Get or create the global diagnostics collector."""
        if diag_config._global_collector is None:
            diag_config._global_collector = ASPDiagnosticsCollector()
        return diag_config._global_collector
    
    @staticmethod
    def reset_collector() -> None:
        """Reset the global collector (for testing or new runs)."""
        diag_config._global_collector = None
    
    @staticmethod
    def log_asp_universe(facts: str, chapter_num: int) -> Optional[ASPUniverseStats]:
        """
        Log ASP universe stats for a chapter.
        
        This is the main entry point for instrumentation.
        Call this before invoking Clingo.
        
        Args:
            facts: ASP facts string about to be sent to Clingo
            chapter_num: Current chapter number
            
        Returns:
            ASPUniverseStats if diagnostics enabled, None otherwise
        """
        if not diag_config._DIAGNOSTICS_ENABLED:
            return None
        
        collector = ASPDiagnosticsGenerator.get_collector()
        stats = collector.analyze_facts(facts, chapter_num)
        collector.log_chapter_stats(stats, diag_config._DIAGNOSTICS_ENABLED)
        return stats
    
    @staticmethod
    def log_run_summary() -> None:
        """Log summary of all collected stats at end of run."""
        if diag_config._DIAGNOSTICS_ENABLED:
            ASPDiagnosticsGenerator.get_collector().log_summary(diag_config._DIAGNOSTICS_ENABLED)
