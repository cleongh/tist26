"""
ASP Diagnostics - Lightweight instrumentation for ASP universe size.

Phase 8.8: Added to verify entity counts stabilize across chapters.

This module provides optional diagnostics that can be enabled via:
    - Environment variable: ASP_DIAGNOSTICS=1
    - Programmatic: asp_diagnostics.enable()

Per LOGIC_DESIGN.md Section 8: No runtime overhead when disabled.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Global flag - disabled by default
_diagnostics_enabled = os.environ.get('ASP_DIAGNOSTICS', '').lower() in ('1', 'true', 'yes')


def enable() -> None:
    """Enable ASP diagnostics programmatically."""
    global _diagnostics_enabled
    _diagnostics_enabled = True
    logger.info("ASP diagnostics enabled")


def disable() -> None:
    """Disable ASP diagnostics programmatically."""
    global _diagnostics_enabled
    _diagnostics_enabled = False


def is_enabled() -> bool:
    """Check if ASP diagnostics are enabled."""
    return _diagnostics_enabled


@dataclass
class ASPUniverseStats:
    """
    Statistics about ASP universe size for a single chapter.
    
    Tracks entity counts to detect grounding explosion.
    """
    chapter_num: int
    characters: int = 0
    items: int = 0
    locations: int = 0
    relationships: int = 0
    events: int = 0
    time_facts: int = 0
    total_facts: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'chapter': self.chapter_num,
            'characters': self.characters,
            'items': self.items,
            'locations': self.locations,
            'relationships': self.relationships,
            'events': self.events,
            'time_facts': self.time_facts,
            'total_facts': self.total_facts,
        }
    
    def log_summary(self) -> None:
        """Log a concise summary of universe stats."""
        logger.info(
            f"[ASP Ch.{self.chapter_num}] "
            f"chars={self.characters} items={self.items} locs={self.locations} "
            f"rels={self.relationships} events={self.events} time={self.time_facts} "
            f"total={self.total_facts}"
        )


@dataclass
class ASPDiagnosticsCollector:
    """
    Collects ASP universe statistics across chapters.
    
    Usage:
        collector = ASPDiagnosticsCollector()
        stats = collector.analyze_facts(facts_string, chapter_num)
        collector.log_chapter_stats(stats)
        
        # At end of run:
        collector.log_summary()
    """
    chapter_stats: List[ASPUniverseStats] = field(default_factory=list)
    
    def analyze_facts(self, facts: str, chapter_num: int) -> ASPUniverseStats:
        """
        Analyze ASP facts string to extract universe statistics.
        
        This is a lightweight parse - just counts predicate occurrences.
        No ASP parsing overhead.
        
        Args:
            facts: ASP facts string
            chapter_num: Current chapter number
            
        Returns:
            ASPUniverseStats with entity counts
        """
        stats = ASPUniverseStats(chapter_num=chapter_num)
        
        # Count total facts (lines ending with .)
        lines = facts.split('\n')
        stats.total_facts = sum(
            1 for line in lines 
            if line.strip() and not line.strip().startswith('%') and line.strip().endswith('.')
        )
        
        # Count specific predicates using simple regex
        # character(X). - global character declaration
        stats.characters = len(re.findall(r'^character\([^)]+\)\.$', facts, re.MULTILINE))
        
        # item(X). - global item declaration  
        stats.items = len(re.findall(r'^item\([^)]+\)\.$', facts, re.MULTILINE))
        
        # location_entity(X). - global location declaration
        stats.locations = len(re.findall(r'^location_entity\([^)]+\)\.$', facts, re.MULTILINE))
        
        # relationship(X, Y, Z). - relationship facts
        stats.relationships = len(re.findall(r'^(?:relationship|initial_relationship)\([^)]+\)\.$', facts, re.MULTILINE))
        
        # event(X). - event declarations
        stats.events = len(re.findall(r'^event\([^)]+\)\.$', facts, re.MULTILINE))
        
        # time(N). - time facts
        stats.time_facts = len(re.findall(r'^time\(\d+\)\.$', facts, re.MULTILINE))
        
        return stats
    
    def log_chapter_stats(self, stats: ASPUniverseStats) -> None:
        """
        Log chapter stats and store for summary.
        
        Only logs if diagnostics are enabled.
        """
        self.chapter_stats.append(stats)
        
        if _diagnostics_enabled:
            stats.log_summary()
    
    def log_summary(self) -> None:
        """
        Log summary of all chapters to detect growth patterns.
        
        Only logs if diagnostics are enabled.
        """
        if not _diagnostics_enabled or not self.chapter_stats:
            return
        
        logger.info("=" * 60)
        logger.info("ASP UNIVERSE DIAGNOSTICS SUMMARY")
        logger.info("=" * 60)
        
        # Show per-chapter stats
        for stats in self.chapter_stats:
            logger.info(
                f"  Ch.{stats.chapter_num:2d}: "
                f"chars={stats.characters:3d} items={stats.items:3d} "
                f"locs={stats.locations:3d} rels={stats.relationships:3d}"
            )
        
        # Compute growth metrics
        if len(self.chapter_stats) >= 2:
            first = self.chapter_stats[0]
            last = self.chapter_stats[-1]
            
            char_growth = last.characters - first.characters
            item_growth = last.items - first.items
            loc_growth = last.locations - first.locations
            rel_growth = last.relationships - first.relationships
            
            logger.info("-" * 60)
            logger.info(
                f"  GROWTH: chars={char_growth:+d} items={item_growth:+d} "
                f"locs={loc_growth:+d} rels={rel_growth:+d}"
            )
            
            # Warn if exponential growth detected
            if char_growth > len(self.chapter_stats) * 5:
                logger.warning(
                    f"  ⚠️  Character count grew by {char_growth} over "
                    f"{len(self.chapter_stats)} chapters - possible grounding explosion!"
                )
        
        logger.info("=" * 60)
    
    def get_latest_stats(self) -> Optional[ASPUniverseStats]:
        """Get the most recent chapter stats."""
        return self.chapter_stats[-1] if self.chapter_stats else None
    
    def to_dict(self) -> Dict:
        """Convert all stats to dictionary for JSON export."""
        return {
            'chapters': [s.to_dict() for s in self.chapter_stats],
            'total_chapters': len(self.chapter_stats),
        }


# Global collector instance for convenience
_global_collector: Optional[ASPDiagnosticsCollector] = None


def get_collector() -> ASPDiagnosticsCollector:
    """Get or create the global diagnostics collector."""
    global _global_collector
    if _global_collector is None:
        _global_collector = ASPDiagnosticsCollector()
    return _global_collector


def reset_collector() -> None:
    """Reset the global collector (for testing or new runs)."""
    global _global_collector
    _global_collector = None


def log_asp_universe(facts: str, chapter_num: int) -> Optional[ASPUniverseStats]:
    """
    Convenience function to log ASP universe stats for a chapter.
    
    This is the main entry point for instrumentation.
    Call this before invoking Clingo.
    
    Args:
        facts: ASP facts string about to be sent to Clingo
        chapter_num: Current chapter number
        
    Returns:
        ASPUniverseStats if diagnostics enabled, None otherwise
    """
    if not _diagnostics_enabled:
        return None
    
    collector = get_collector()
    stats = collector.analyze_facts(facts, chapter_num)
    collector.log_chapter_stats(stats)
    return stats


def log_run_summary() -> None:
    """Log summary of all collected stats at end of run."""
    if _diagnostics_enabled:
        get_collector().log_summary()
