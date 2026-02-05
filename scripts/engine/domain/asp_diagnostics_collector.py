"""
ASP Diagnostics Collector - Collects ASP universe statistics across chapters.

Phase 8.8: Used to verify entity counts stabilize across chapters.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .asp_universe_stats import ASPUniverseStats

logger = logging.getLogger(__name__)


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
    chapter_stats: List['ASPUniverseStats'] = field(default_factory=list)
    
    def analyze_facts(self, facts: str, chapter_num: int) -> 'ASPUniverseStats':
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
        from .asp_universe_stats import ASPUniverseStats
        
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
    
    def log_chapter_stats(self, stats: 'ASPUniverseStats', diagnostics_enabled: bool) -> None:
        """
        Log chapter stats and store for summary.
        
        Only logs if diagnostics are enabled.
        
        Args:
            stats: The stats to log
            diagnostics_enabled: Whether diagnostics are enabled
        """
        self.chapter_stats.append(stats)
        
        if diagnostics_enabled:
            stats.log_summary()
    
    def log_summary(self, diagnostics_enabled: bool) -> None:
        """
        Log summary of all chapters to detect growth patterns.
        
        Only logs if diagnostics are enabled.
        
        Args:
            diagnostics_enabled: Whether diagnostics are enabled
        """
        if not diagnostics_enabled or not self.chapter_stats:
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
    
    def get_latest_stats(self) -> Optional['ASPUniverseStats']:
        """Get the most recent chapter stats."""
        return self.chapter_stats[-1] if self.chapter_stats else None
    
    def to_dict(self) -> Dict:
        """Convert all stats to dictionary for JSON export."""
        return {
            'chapters': [s.to_dict() for s in self.chapter_stats],
            'total_chapters': len(self.chapter_stats),
        }
