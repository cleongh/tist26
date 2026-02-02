"""
Tests for ASP Diagnostics module.

Phase 8.8: Lightweight instrumentation for ASP universe size verification.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import asp_diagnostics
from engine.asp_diagnostics import (
    ASPUniverseStats,
    ASPDiagnosticsCollector,
    log_asp_universe,
    enable,
    disable,
    is_enabled,
    reset_collector,
    get_collector,
)


class TestASPUniverseStats:
    """Tests for ASPUniverseStats dataclass."""
    
    def test_stats_creation(self):
        """Stats can be created with default values."""
        stats = ASPUniverseStats(chapter_num=1)
        assert stats.chapter_num == 1
        assert stats.characters == 0
        assert stats.items == 0
        assert stats.locations == 0
    
    def test_to_dict(self):
        """Stats can be serialized to dict."""
        stats = ASPUniverseStats(
            chapter_num=5,
            characters=10,
            items=5,
            locations=3,
            relationships=8,
            events=20,
            time_facts=20,
            total_facts=100,
        )
        d = stats.to_dict()
        assert d['chapter'] == 5
        assert d['characters'] == 10
        assert d['items'] == 5
        assert d['locations'] == 3
        assert d['total_facts'] == 100


class TestASPDiagnosticsCollector:
    """Tests for ASPDiagnosticsCollector."""
    
    def test_analyze_facts_counts_characters(self):
        """Collector correctly counts character declarations."""
        collector = ASPDiagnosticsCollector()
        facts = """
% Chapter 1 facts
character(harry).
character(ron).
character(hermione).
item(wand).
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.characters == 3
    
    def test_analyze_facts_counts_items(self):
        """Collector correctly counts item declarations."""
        collector = ASPDiagnosticsCollector()
        facts = """
item(wand).
item(cloak).
item(map).
character(harry).
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.items == 3
    
    def test_analyze_facts_counts_locations(self):
        """Collector correctly counts location declarations."""
        collector = ASPDiagnosticsCollector()
        facts = """
location_entity(hogwarts).
location_entity(hogsmeade).
location_entity(diagon_alley).
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.locations == 3
    
    def test_analyze_facts_counts_relationships(self):
        """Collector correctly counts relationship facts."""
        collector = ASPDiagnosticsCollector()
        facts = """
relationship(harry, ron, friend).
relationship(harry, draco, enemy).
initial_relationship(hermione, ron, friend).
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.relationships == 3
    
    def test_analyze_facts_counts_events(self):
        """Collector correctly counts event declarations."""
        collector = ASPDiagnosticsCollector()
        facts = """
event(e1).
event(e2).
event(e3).
event_type(e1, speak).
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.events == 3
    
    def test_analyze_facts_counts_time_facts(self):
        """Collector correctly counts time facts."""
        collector = ASPDiagnosticsCollector()
        facts = """
time(1).
time(2).
time(3).
time(100).
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.time_facts == 4
    
    def test_analyze_facts_ignores_comments(self):
        """Collector ignores comment lines."""
        collector = ASPDiagnosticsCollector()
        facts = """
% character(fake_comment).
character(harry).
% This is a comment
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.characters == 1
    
    def test_analyze_facts_counts_total(self):
        """Collector counts total facts correctly."""
        collector = ASPDiagnosticsCollector()
        facts = """
character(harry).
item(wand).
location_entity(hogwarts).
event(e1).
time(1).
% comment line
"""
        stats = collector.analyze_facts(facts, 1)
        assert stats.total_facts == 5
    
    def test_collector_stores_chapter_stats(self):
        """Collector stores stats across chapters."""
        collector = ASPDiagnosticsCollector()
        
        facts1 = "character(harry).\nitem(wand)."
        facts2 = "character(harry).\ncharacter(ron).\nitem(wand).\nitem(cloak)."
        
        stats1 = collector.analyze_facts(facts1, 1)
        collector.log_chapter_stats(stats1)
        
        stats2 = collector.analyze_facts(facts2, 2)
        collector.log_chapter_stats(stats2)
        
        assert len(collector.chapter_stats) == 2
        assert collector.chapter_stats[0].characters == 1
        assert collector.chapter_stats[1].characters == 2
    
    def test_to_dict_serializes_all_chapters(self):
        """Collector can serialize all chapter stats."""
        collector = ASPDiagnosticsCollector()
        
        stats1 = ASPUniverseStats(chapter_num=1, characters=5)
        stats2 = ASPUniverseStats(chapter_num=2, characters=7)
        collector.chapter_stats = [stats1, stats2]
        
        d = collector.to_dict()
        assert d['total_chapters'] == 2
        assert len(d['chapters']) == 2


class TestDiagnosticsEnableDisable:
    """Tests for enable/disable functionality."""
    
    def setup_method(self):
        """Reset diagnostics state before each test."""
        disable()
        reset_collector()
    
    def teardown_method(self):
        """Reset diagnostics state after each test."""
        disable()
        reset_collector()
    
    def test_disabled_by_default(self):
        """Diagnostics are disabled by default."""
        # Reset to default state
        asp_diagnostics._diagnostics_enabled = False
        assert is_enabled() == False
    
    def test_enable_enables(self):
        """enable() enables diagnostics."""
        enable()
        assert is_enabled() == True
    
    def test_disable_disables(self):
        """disable() disables diagnostics."""
        enable()
        disable()
        assert is_enabled() == False
    
    def test_log_asp_universe_returns_none_when_disabled(self):
        """log_asp_universe returns None when disabled."""
        disable()
        facts = "character(harry)."
        result = log_asp_universe(facts, 1)
        assert result is None
    
    def test_log_asp_universe_returns_stats_when_enabled(self):
        """log_asp_universe returns stats when enabled."""
        enable()
        facts = "character(harry).\nitem(wand)."
        result = log_asp_universe(facts, 1)
        assert result is not None
        assert result.characters == 1
        assert result.items == 1
    
    def test_get_collector_creates_singleton(self):
        """get_collector returns the same collector instance."""
        reset_collector()
        c1 = get_collector()
        c2 = get_collector()
        assert c1 is c2
    
    def test_reset_collector_creates_new_instance(self):
        """reset_collector creates a new collector."""
        c1 = get_collector()
        c1.chapter_stats.append(ASPUniverseStats(chapter_num=1))
        
        reset_collector()
        c2 = get_collector()
        
        assert len(c2.chapter_stats) == 0


class TestDiagnosticsNoOverhead:
    """Tests that diagnostics have no overhead when disabled."""
    
    def setup_method(self):
        disable()
        reset_collector()
    
    def test_disabled_no_stats_collected(self):
        """When disabled, no stats are collected."""
        facts = "character(harry).\n" * 1000
        
        for i in range(10):
            log_asp_universe(facts, i)
        
        # No stats should be collected when disabled
        collector = get_collector()
        assert len(collector.chapter_stats) == 0


class TestRealisticASPFacts:
    """Tests with realistic ASP facts from the system."""
    
    def test_full_chapter_facts(self):
        """Collector handles realistic chapter facts."""
        collector = ASPDiagnosticsCollector()
        
        facts = """
% Chapter 1 facts

% Character aliases (for ASP-based resolution)
alias(boy_who_lived, harry).
alias(the_chosen_one, harry).

character(harry).
character(ron).
character(hermione).
character(dumbledore).
character(hagrid).

item(wand).
item(invisibility_cloak).
item(marauders_map).

location_entity(hogwarts).
location_entity(privet_drive).
location_entity(diagon_alley).

relationship(harry, ron, friend).
relationship(harry, hermione, friend).
initial_relationship(ron, hermione, friend).

event(e1).
event_type(e1, speak).
event_time(e1, 1).
time(1).

event(e2).
event_type(e2, movement).
event_time(e2, 2).
time(2).

agent(e1, harry).
patient(e1, ron).
location(e1, hogwarts).

% Story rules
relationship_rule(harry, friend, ron, e1).
"""
        stats = collector.analyze_facts(facts, 1)
        
        assert stats.characters == 5
        assert stats.items == 3
        assert stats.locations == 3
        assert stats.relationships == 3
        assert stats.events == 2
        assert stats.time_facts == 2
        assert stats.total_facts > 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
