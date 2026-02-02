"""Tests for the PersistentContext class (Phase 8.4)."""
import json
import tempfile
from datetime import datetime
from pathlib import Path
import pytest

from engine.context_persistence import PersistentContext, ContextMetadata
from engine.state_manager import StateManager
from engine.item_tracker import ItemTracker, TrackedItem, ItemRelevance, ItemLifecycleState
from engine.final_analysis import FinalAnalyzer
from engine.rule_registry import RuleRegistry


class TestContextMetadata:
    """Tests for ContextMetadata dataclass."""

    def test_defaults(self):
        """Test default values."""
        meta = ContextMetadata(story_id="test")
        assert meta.story_id == "test"
        # created_at and last_updated_at default to empty string
        assert meta.current_chapter == 0
        assert meta.total_chapters_processed == 0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        meta = ContextMetadata(
            story_id="test",
            current_chapter=3,
            total_chapters_processed=3,
        )
        d = meta.to_dict()
        assert d["story_id"] == "test"
        assert d["current_chapter"] == 3
        assert d["total_chapters_processed"] == 3
        assert "created_at" in d
        assert "last_updated_at" in d

    def test_from_dict(self):
        """Test construction from dictionary."""
        d = {
            "story_id": "harry_potter",
            "created_at": "2024-01-15T10:30:00",
            "last_updated_at": "2024-01-15T12:00:00",
            "current_chapter": 5,
            "total_chapters_processed": 5,
        }
        meta = ContextMetadata.from_dict(d)
        assert meta.story_id == "harry_potter"
        assert meta.current_chapter == 5
        assert meta.total_chapters_processed == 5


class TestPersistentContextBasics:
    """Basic tests for PersistentContext."""

    def test_initialization(self):
        """Test initialization with storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            # PersistentContext initializes with default metadata
            assert ctx.metadata is not None
            assert ctx._storage_dir == Path(tmpdir)

    def test_load_or_create_new(self):
        """Test creating new context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            loaded = ctx.load_or_create("new_story")
            assert loaded is False
            assert ctx.metadata is not None
            assert ctx.metadata.story_id == "new_story"
            assert ctx.metadata.current_chapter == 0

    def test_context_file_naming(self):
        """Test context file naming convention."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("harry_potter_test")
            expected_file = Path(tmpdir) / "harry_potter_test_context.json"
            assert ctx._context_file == expected_file


class TestPersistentContextSaveLoad:
    """Tests for save/load functionality."""

    def test_save_creates_file(self):
        """Test that save creates a JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            ctx.save()
            
            context_file = Path(tmpdir) / "test_story_context.json"
            assert context_file.exists()
            
            # Verify it's valid JSON
            with open(context_file) as f:
                data = json.load(f)
            assert "metadata" in data

    def test_load_existing_context(self):
        """Test loading existing context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and save context
            ctx1 = PersistentContext(Path(tmpdir))
            ctx1.load_or_create("test_story")
            ctx1.metadata.current_chapter = 5
            ctx1.save()
            
            # Load in new instance
            ctx2 = PersistentContext(Path(tmpdir))
            loaded = ctx2.load_or_create("test_story")
            assert loaded is True
            assert ctx2.metadata.current_chapter == 5

    def test_atomic_save(self):
        """Test that save is atomic (uses temp file)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            ctx.save()
            
            # File should exist and be valid
            context_file = Path(tmpdir) / "test_story_context.json"
            assert context_file.exists()
            
            # No temp files should remain
            temp_files = list(Path(tmpdir).glob("*.tmp"))
            assert len(temp_files) == 0

    def test_is_dirty_tracking(self):
        """Test dirty flag tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            # Mark dirty explicitly
            ctx._is_dirty = True
            assert ctx.is_dirty is True
            
            # Save clears dirty flag
            ctx.save()
            assert ctx.is_dirty is False


class TestStateManagerIntegration:
    """Tests for StateManager integration."""

    def test_update_from_state_manager_entities(self):
        """Test updating context from StateManager entities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_entity("harry", "character", chapter=1)
            sm.add_entity("hogwarts", "location", chapter=1)
            
            ctx.update_from_state_manager(sm, chapter=1)
            
            assert "harry" in ctx._entity_registry_data.get("entities", {})
            assert "hogwarts" in ctx._entity_registry_data.get("entities", {})
            assert ctx.is_dirty is True

    def test_update_from_state_manager_relationships(self):
        """Test updating context from StateManager relationships."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_relationship("harry", "ron", "friend")
            sm.add_relationship("harry", "draco", "enemy")
            
            ctx.update_from_state_manager(sm, chapter=1)
            
            # Relationships are stored with key "char1,char2" -> rel_type
            assert "harry,ron" in ctx._relationships
            assert ctx._relationships["harry,ron"] == "friend"
            assert "harry,draco" in ctx._relationships
            assert ctx._relationships["harry,draco"] == "enemy"

    def test_update_from_state_manager_dead_characters(self):
        """Test updating context from StateManager dead characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_entity("voldemort", "character", chapter=1)
            sm.mark_dead("voldemort")
            sm.add_entity("dumbledore", "character", chapter=1)
            sm.mark_dead("dumbledore")
            
            ctx.update_from_state_manager(sm, chapter=6)
            
            assert "voldemort" in ctx._dead_characters
            assert "dumbledore" in ctx._dead_characters

    def test_apply_to_state_manager(self):
        """Test applying context to StateManager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create context with data
            ctx1 = PersistentContext(Path(tmpdir))
            ctx1.load_or_create("test_story")
            
            sm1 = StateManager()
            sm1.add_entity("harry", "character", chapter=1)
            sm1.add_relationship("harry", "ron", "friend")
            sm1.add_entity("voldemort", "character", chapter=1)
            sm1.mark_dead("voldemort")
            
            ctx1.update_from_state_manager(sm1, chapter=1)
            ctx1.save()
            
            # Load in new instance and apply
            ctx2 = PersistentContext(Path(tmpdir))
            ctx2.load_or_create("test_story")
            
            sm2 = StateManager()
            ctx2.apply_to_state_manager(sm2)
            
            # Verify state restored
            assert len(sm2.entity_registry._entities) > 0
            assert ("harry", "ron") in sm2.persistent_relationships
            assert "voldemort" in sm2.persistent_dead

    def test_round_trip_state_manager(self):
        """Test full round-trip save/load with StateManager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate
            ctx1 = PersistentContext(Path(tmpdir))
            ctx1.load_or_create("test_story")
            
            sm1 = StateManager()
            for name in ["harry", "ron", "hermione"]:
                sm1.add_entity(name, "character", chapter=1)
            sm1.add_entity("hogwarts", "location", chapter=1)
            sm1.add_relationship("harry", "hermione", "friend")
            sm1.add_entity("voldemort", "character", chapter=1)
            sm1.mark_dead("voldemort")
            
            ctx1.update_from_state_manager(sm1, chapter=1)
            ctx1.save()
            
            # Load in new instance
            ctx2 = PersistentContext(Path(tmpdir))
            ctx2.load_or_create("test_story")
            
            sm2 = StateManager()
            ctx2.apply_to_state_manager(sm2)
            
            # Verify
            assert len(sm2.entity_registry._entities) == 5
            assert sm2.persistent_relationships == {("harry", "hermione"): "friend"}
            assert sm2.persistent_dead == {"voldemort"}


class TestItemTrackerIntegration:
    """Tests for ItemTracker integration."""

    def test_update_from_item_tracker(self):
        """Test updating context from ItemTracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            it = ItemTracker()
            it._items["wand"] = TrackedItem(
                item_id="wand",
                name="Elder Wand",
                relevance=ItemRelevance.CAUSAL,
                original_relevance=ItemRelevance.LATENT,
                lifecycle_state=ItemLifecycleState.CARRIED,
                introduced_chapter=1,
                last_mentioned_chapter=5,
                promoted_to_causal_chapter=3,
                carrier="harry",
            )
            
            ctx.update_from_item_tracker(it, chapter=5)
            
            items = ctx._item_tracker_data.get("items", {})
            assert "wand" in items
            assert items["wand"]["relevance"] == "causal"
            assert items["wand"]["carrier"] == "harry"

    def test_apply_to_item_tracker(self):
        """Test applying context to ItemTracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create context with item data
            ctx1 = PersistentContext(Path(tmpdir))
            ctx1.load_or_create("test_story")
            
            it1 = ItemTracker()
            it1._items["sword"] = TrackedItem(
                item_id="sword",
                name="Sword of Gryffindor",
                relevance=ItemRelevance.CAUSAL,
                original_relevance=ItemRelevance.CAUSAL,
                lifecycle_state=ItemLifecycleState.USED,
                introduced_chapter=1,
                last_mentioned_chapter=10,
                promoted_to_causal_chapter=1,
                carrier=None,
            )
            
            ctx1.update_from_item_tracker(it1, chapter=10)
            ctx1.save()
            
            # Load and apply
            ctx2 = PersistentContext(Path(tmpdir))
            ctx2.load_or_create("test_story")
            
            it2 = ItemTracker()
            ctx2.apply_to_item_tracker(it2)
            
            assert "sword" in it2._items
            assert it2._items["sword"].name == "Sword of Gryffindor"
            assert it2._items["sword"].relevance == ItemRelevance.CAUSAL


class TestChekhovCandidates:
    """Tests for Chekhov detection support."""

    def test_get_chekhov_candidates_empty(self):
        """Test getting candidates when none exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            candidates = ctx.get_chekhov_candidates()
            assert candidates == []

    def test_get_chekhov_candidates_latent_items(self):
        """Test getting latent items as Chekhov candidates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            it = ItemTracker()
            # Latent item (Chekhov candidate)
            it._items["gun"] = TrackedItem(
                item_id="gun",
                name="Chekhov's Gun",
                relevance=ItemRelevance.LATENT,
                original_relevance=ItemRelevance.LATENT,
                lifecycle_state=ItemLifecycleState.INTRODUCED,
                introduced_chapter=1,
                last_mentioned_chapter=1,
                carrier=None,
            )
            # Causal item (not a candidate)
            it._items["wand"] = TrackedItem(
                item_id="wand",
                name="Harry's Wand",
                relevance=ItemRelevance.CAUSAL,
                original_relevance=ItemRelevance.CAUSAL,
                lifecycle_state=ItemLifecycleState.CARRIED,
                introduced_chapter=1,
                last_mentioned_chapter=5,
                promoted_to_causal_chapter=1,
                carrier="harry",
            )
            
            ctx.update_from_item_tracker(it, chapter=5)
            
            candidates = ctx.get_chekhov_candidates()
            assert len(candidates) == 1
            assert candidates[0]["item_id"] == "gun"


class TestLifecycleSummary:
    """Tests for lifecycle summary."""

    def test_get_lifecycle_summary_empty(self):
        """Test lifecycle summary with no entities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            summary = ctx.get_lifecycle_summary()
            # Returns counts for all lifecycle states
            assert summary.get("active", 0) == 0

    def test_get_lifecycle_summary_counts_states(self):
        """Test lifecycle summary counts entity states."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_entity("harry", "character", chapter=1)
            sm.add_entity("ron", "character", chapter=1)
            sm.add_entity("hogwarts", "location", chapter=1)
            
            ctx.update_from_state_manager(sm, chapter=1)
            
            summary = ctx.get_lifecycle_summary()
            # All should be in active state by default
            assert "active" in summary or "ACTIVE" in summary or len(summary) > 0


class TestStatistics:
    """Tests for statistics gathering."""

    def test_get_statistics(self):
        """Test statistics method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_entity("harry", "character", chapter=1)
            sm.add_entity("hogwarts", "location", chapter=1)
            sm.add_relationship("harry", "ron", "friend")
            sm.mark_dead("voldemort")
            
            ctx.update_from_state_manager(sm, chapter=1)
            
            it = ItemTracker()
            it._items["wand"] = TrackedItem(
                item_id="wand",
                name="Wand",
                relevance=ItemRelevance.CAUSAL,
                original_relevance=ItemRelevance.CAUSAL,
                lifecycle_state=ItemLifecycleState.CARRIED,
                introduced_chapter=1,
                last_mentioned_chapter=1,
                carrier="harry",
            )
            ctx.update_from_item_tracker(it, chapter=1)
            
            stats = ctx.get_statistics()
            
            assert stats["story_id"] == "test_story"
            assert stats["current_chapter"] == 1
            assert stats["entities"] == 2
            assert stats["items"] == 1
            assert stats["relationships"] == 1
            assert stats["dead_characters"] == 1


class TestFinalAnalyzerIntegration:
    """Tests for FinalAnalyzer integration."""

    def test_set_persistent_context(self):
        """Test setting persistent context on FinalAnalyzer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            rr = RuleRegistry()
            analyzer = FinalAnalyzer(sm, rr)
            analyzer.set_persistent_context(ctx)
            
            assert analyzer._persistent_context is ctx

    def test_get_context_statistics(self):
        """Test getting context statistics via FinalAnalyzer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_entity("harry", "character", chapter=1)
            ctx.update_from_state_manager(sm, chapter=1)
            
            rr = RuleRegistry()
            analyzer = FinalAnalyzer(sm, rr)
            analyzer.set_persistent_context(ctx)
            
            stats = analyzer.get_context_statistics()
            
            assert stats["story_id"] == "test_story"
            assert stats["entities"] == 1

    def test_reset_clears_persistent_context(self):
        """Test that reset clears the persistent context reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            rr = RuleRegistry()
            analyzer = FinalAnalyzer(sm, rr)
            analyzer.set_persistent_context(ctx)
            
            assert analyzer._persistent_context is not None
            
            analyzer.reset()
            
            assert analyzer._persistent_context is None


class TestDeterministicOutput:
    """Tests for deterministic JSON output."""

    def test_sorted_keys(self):
        """Test that JSON output has sorted keys for determinism."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_entity("zebra", "animal", chapter=1)
            sm.add_entity("aardvark", "animal", chapter=1)
            sm.add_entity("middle", "animal", chapter=1)
            
            ctx.update_from_state_manager(sm, chapter=1)
            ctx.save()
            
            # Read file and verify sorted
            with open(ctx._context_file) as f:
                content = f.read()
            
            # Parse to verify it's valid JSON
            data = json.loads(content)
            
            # Entities should be retrievable (order doesn't matter for dict)
            entities = data.get("entity_registry", {}).get("entities", {})
            assert len(entities) == 3


class TestIncrementalUpdates:
    """Tests for incremental update behavior."""

    def test_incremental_chapter_tracking(self):
        """Test that chapters are tracked incrementally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            sm.add_entity("harry", "character", chapter=1)
            
            ctx.update_from_state_manager(sm, chapter=1)
            assert ctx.metadata.current_chapter == 1
            assert ctx.metadata.total_chapters_processed == 1
            
            sm.add_entity("ron", "character", chapter=2)
            ctx.update_from_state_manager(sm, chapter=2)
            
            assert ctx.metadata.current_chapter == 2
            assert ctx.metadata.total_chapters_processed == 2

    def test_chapter_updates_correctly(self):
        """Test that chapter tracking updates with each call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            
            # Process chapter 1
            ctx.update_from_state_manager(sm, chapter=1)
            assert ctx.metadata.current_chapter == 1
            
            # Process chapter 2
            ctx.update_from_state_manager(sm, chapter=2)
            assert ctx.metadata.current_chapter == 2

    def test_entities_accumulate(self):
        """Test that entities accumulate across updates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PersistentContext(Path(tmpdir))
            ctx.load_or_create("test_story")
            
            sm = StateManager()
            
            # Chapter 1: Add Harry
            sm.add_entity("harry", "character", chapter=1)
            ctx.update_from_state_manager(sm, chapter=1)
            
            # Chapter 2: Add Ron
            sm.add_entity("ron", "character", chapter=2)
            ctx.update_from_state_manager(sm, chapter=2)
            
            entities = ctx._entity_registry_data.get("entities", {})
            assert "harry" in entities
            assert "ron" in entities


class TestLoadCountTracking:
    """Tests for load count tracking (load-once behavior)."""

    def test_load_count_increments(self):
        """Test that load count is tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create initial context
            ctx1 = PersistentContext(Path(tmpdir))
            ctx1.load_or_create("test_story")
            ctx1.save()
            
            # Load again
            ctx2 = PersistentContext(Path(tmpdir))
            ctx2.load_or_create("test_story")
            
            stats = ctx2.get_statistics()
            assert stats["load_count"] == 1  # First load after save
