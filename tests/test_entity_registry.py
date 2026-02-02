"""
Tests for EntityRegistry - Entity Storage and Lifecycle Management

Tests cover:
    - Entity registration and deduplication
    - Lifecycle state transitions (ACTIVE, LATENT, FROZEN)
    - ASP fact generation with lifecycle filtering
    - StateManager integration
"""

import pytest
from engine.entity_registry import (
    EntityRegistry, 
    RegisteredEntity, 
    EntityType, 
    LifecycleState,
    ACTIVE_THRESHOLD,
    LATENT_THRESHOLD,
)
from engine.state_manager import StateManager


class TestEntityRegistryBasics:
    """Basic EntityRegistry functionality."""
    
    def test_initialization(self):
        """EntityRegistry initializes empty."""
        registry = EntityRegistry()
        assert len(registry._entities) == 0
        assert registry._registrations == 0
        assert registry._updates == 0
    
    def test_register_new_entity(self):
        """register_entity creates new entity on first call."""
        registry = EntityRegistry()
        entity = registry.register_entity("harry", EntityType.CHARACTER, chapter=1)
        
        assert entity.canonical_id == "harry"
        assert entity.entity_type == EntityType.CHARACTER
        assert entity.first_seen_chapter == 1
        assert entity.last_seen_chapter == 1
        assert registry._registrations == 1
        assert registry._updates == 0
    
    def test_register_duplicate_updates_only(self):
        """register_entity updates existing entity on subsequent calls."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=1)
        registry.register_entity("harry", EntityType.CHARACTER, chapter=5)
        
        entity = registry.get_entity("harry")
        assert entity.first_seen_chapter == 1
        assert entity.last_seen_chapter == 5
        assert registry._registrations == 1
        assert registry._updates == 1
    
    def test_is_agent_updates_last_acted(self):
        """is_agent=True updates last_acted_chapter."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=1, is_agent=True)
        
        entity = registry.get_entity("harry")
        assert entity.last_acted_chapter == 1
    
    def test_alias_resolution(self):
        """Aliases resolve to canonical ID."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, aliases=["potter", "the_boy"])
        
        assert registry.resolve("potter") == "harry"
        assert registry.resolve("the_boy") == "harry"
        assert registry.resolve("harry") == "harry"


class TestLifecycleStates:
    """Lifecycle state computation and transitions."""
    
    def test_default_lifecycle_is_active(self):
        """New entities default to ACTIVE lifecycle state."""
        registry = EntityRegistry()
        entity = registry.register_entity("harry", EntityType.CHARACTER, chapter=0)
        
        assert entity.lifecycle_state == LifecycleState.ACTIVE
    
    def test_lifecycle_active_threshold(self):
        """Entity is ACTIVE if acted within ACTIVE_THRESHOLD chapters."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=10, is_agent=True)
        
        # At chapter 12 (2 chapters later), should still be ACTIVE
        entity = registry.get_entity("harry")
        state = entity.compute_lifecycle_state(current_chapter=12)
        assert state == LifecycleState.ACTIVE
    
    def test_lifecycle_becomes_latent(self):
        """Entity becomes LATENT after ACTIVE_THRESHOLD chapters of inactivity."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=1, is_agent=True)
        
        entity = registry.get_entity("harry")
        # 3 chapters of inactivity (1 -> 4) triggers LATENT
        state = entity.compute_lifecycle_state(current_chapter=1 + ACTIVE_THRESHOLD)
        assert state == LifecycleState.LATENT
    
    def test_lifecycle_becomes_frozen(self):
        """Entity becomes FROZEN after LATENT_THRESHOLD chapters of inactivity."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=1, is_agent=True)
        
        entity = registry.get_entity("harry")
        # 10+ chapters of inactivity triggers FROZEN
        state = entity.compute_lifecycle_state(current_chapter=1 + LATENT_THRESHOLD)
        assert state == LifecycleState.FROZEN
    
    def test_update_lifecycle_states_all_entities(self):
        """update_lifecycle_states updates all entities."""
        registry = EntityRegistry()
        
        # Active entity (acted in chapter 14, inactive for 1 chapter at ch15)
        registry.register_entity("harry", EntityType.CHARACTER, chapter=14, is_agent=True)
        
        # Latent entity (acted in chapter 10, inactive for 5 chapters at ch15)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=10, is_agent=True)
        
        # Frozen entity (acted in chapter 0, inactive for 15 chapters at ch15)
        registry.register_entity("dumbledore", EntityType.CHARACTER, chapter=0, is_agent=True)
        
        counts = registry.update_lifecycle_states(current_chapter=15)
        
        assert counts["active"] == 1  # harry
        assert counts["latent"] == 1  # ron
        assert counts["frozen"] == 1  # dumbledore
    
    def test_reactivate_frozen_entity(self):
        """reactivate_entity restores FROZEN entity to ACTIVE."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, is_agent=True)
        
        # Freeze the entity
        registry.update_lifecycle_states(current_chapter=20)
        assert registry.get_entity("harry").lifecycle_state == LifecycleState.FROZEN
        
        # Reactivate
        registry.reactivate_entity("harry", chapter=21)
        assert registry.get_entity("harry").lifecycle_state == LifecycleState.ACTIVE
        assert registry.get_entity("harry").last_acted_chapter == 21


class TestLifecycleFiltering:
    """Filtering by lifecycle state."""
    
    def test_get_active_entities(self):
        """get_active_entities returns only ACTIVE entities."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=10, is_agent=True)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=1, is_agent=True)
        
        registry.update_lifecycle_states(current_chapter=10)
        
        active = registry.get_active_entities()
        assert len(active) == 1
        assert active[0].canonical_id == "harry"
    
    def test_get_latent_entities(self):
        """get_latent_entities returns only LATENT entities."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=10, is_agent=True)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=5, is_agent=True)
        
        registry.update_lifecycle_states(current_chapter=10)
        
        latent = registry.get_latent_entities()
        assert len(latent) == 1
        assert latent[0].canonical_id == "ron"
    
    def test_get_frozen_entities(self):
        """get_frozen_entities returns only FROZEN entities."""
        registry = EntityRegistry()
        registry.register_entity("dumbledore", EntityType.CHARACTER, chapter=0, is_agent=True)
        
        registry.update_lifecycle_states(current_chapter=15)
        
        frozen = registry.get_frozen_entities()
        assert len(frozen) == 1
        assert frozen[0].canonical_id == "dumbledore"


class TestASPFactGeneration:
    """ASP fact generation with lifecycle filtering."""
    
    def test_get_asp_facts_active_only_default(self):
        """get_asp_facts defaults to active_only=True."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=10, is_agent=True)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=1, is_agent=True)
        
        registry.update_lifecycle_states(current_chapter=10)
        
        facts = registry.get_asp_facts()
        assert len(facts) == 1
        assert "character(harry)." in facts
    
    def test_get_asp_facts_all_entities(self):
        """get_asp_facts(active_only=False) includes all entities."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=10, is_agent=True)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=1, is_agent=True)
        
        registry.update_lifecycle_states(current_chapter=10)
        
        facts = registry.get_asp_facts(active_only=False)
        assert len(facts) == 2
        assert "character(harry)." in facts
        assert "character(ron)." in facts
    
    def test_get_trait_facts_filters_by_lifecycle(self):
        """get_trait_facts respects lifecycle filtering."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=10, 
                                 is_agent=True, traits={"brave"})
        registry.register_entity("ron", EntityType.CHARACTER, chapter=1, 
                                 is_agent=True, traits={"loyal"})
        
        registry.update_lifecycle_states(current_chapter=10)
        
        facts = registry.get_trait_facts(active_only=True)
        assert len(facts) == 1
        assert "trait(harry, brave)." in facts
    
    def test_get_active_canonical_ids(self):
        """get_active_canonical_ids returns only ACTIVE entity IDs."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=10, is_agent=True)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=1, is_agent=True)
        registry.register_entity("hogwarts", EntityType.LOCATION, chapter=1, is_agent=True)
        
        registry.update_lifecycle_states(current_chapter=10)
        
        active_chars = registry.get_active_canonical_ids(EntityType.CHARACTER)
        assert active_chars == {"harry"}
        
        all_active = registry.get_active_canonical_ids()
        assert all_active == {"harry"}


class TestStateManagerLifecycleIntegration:
    """StateManager integration with lifecycle filtering."""
    
    def test_reset_chapter_filters_by_lifecycle(self):
        """reset_chapter populates WorldState with ACTIVE entities only."""
        sm = StateManager()
        
        sm.add_entity("harry", "character", chapter=10)
        sm.add_entity("ron", "character", chapter=1)
        
        sm.entity_registry.update_acted("harry", 10)
        sm.entity_registry.update_acted("ron", 1)
        
        # Update lifecycle and reset chapter
        sm.reset_chapter(chapter_num=10)
        
        # WorldState should only have harry (ACTIVE)
        assert "harry" in sm.current_state.entities
        assert "ron" not in sm.current_state.entities
    
    def test_end_chapter_updates_lifecycle(self):
        """end_chapter updates lifecycle states."""
        sm = StateManager()
        
        sm.add_entity("harry", "character", chapter=1)
        sm.entity_registry.update_acted("harry", 1)
        
        # End chapter 10 (harry inactive for 9 chapters)
        counts = sm.end_chapter(10)
        
        assert counts["latent"] == 1
        assert sm.entity_registry.get_entity("harry").lifecycle_state == LifecycleState.LATENT
    
    def test_get_lifecycle_statistics(self):
        """get_lifecycle_statistics returns correct counts."""
        sm = StateManager()
        
        # Active: harry acted in chapter 14 (1 chapter inactive at ch15)
        sm.add_entity("harry", "character", chapter=14)
        sm.entity_registry.update_acted("harry", 14)
        
        # Latent: ron acted in chapter 10 (5 chapters inactive at ch15)
        sm.add_entity("ron", "character", chapter=10)
        sm.entity_registry.update_acted("ron", 10)
        
        # Frozen: dumbledore acted in chapter 0 (15 chapters inactive at ch15)
        sm.add_entity("dumbledore", "character", chapter=0)
        sm.entity_registry.update_acted("dumbledore", 0)
        
        sm.end_chapter(15)
        stats = sm.get_lifecycle_statistics()
        
        assert stats["total"] == 3
        assert stats["active"] == 1  # harry
        assert stats["latent"] == 1  # ron
        assert stats["frozen"] == 1  # dumbledore
    
    def test_latent_entity_still_in_registry(self):
        """LATENT entities remain in registry but not in WorldState."""
        sm = StateManager()
        
        sm.add_entity("ron", "character", chapter=1)
        sm.entity_registry.update_acted("ron", 1)
        
        sm.reset_chapter(chapter_num=10)
        
        # Ron should be in registry but not in WorldState
        assert sm.entity_registry.has_entity("ron")
        assert "ron" not in sm.current_state.entities
    
    def test_get_static_entity_facts_active_only(self):
        """get_static_entity_facts returns only ACTIVE entities."""
        sm = StateManager()
        
        sm.add_entity("harry", "character", chapter=10)
        sm.add_entity("ron", "character", chapter=1)
        
        sm.entity_registry.update_acted("harry", 10)
        sm.entity_registry.update_acted("ron", 1)
        sm.end_chapter(10)
        
        facts = sm.get_static_entity_facts()
        
        # Only harry should be in facts
        assert len(facts) == 1
        assert "character(harry)." in facts


class TestLifecycleSerialization:
    """Lifecycle state serialization and deserialization."""
    
    def test_to_dict_includes_lifecycle(self):
        """to_dict includes lifecycle_state."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.update_lifecycle_states(current_chapter=5)
        
        data = registry.to_dict()
        
        assert data["entities"]["harry"]["lifecycle_state"] == "latent"
    
    def test_load_from_dict_restores_lifecycle(self):
        """load_from_dict restores lifecycle_state."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.update_lifecycle_states(current_chapter=15)
        
        data = registry.to_dict()
        
        new_registry = EntityRegistry()
        new_registry.load_from_dict(data)
        
        assert new_registry.get_entity("harry").lifecycle_state == LifecycleState.FROZEN
    
    def test_load_from_dict_backward_compatible(self):
        """load_from_dict handles missing lifecycle_state (backward compatibility)."""
        data = {
            "entities": {
                "harry": {
                    "canonical_id": "harry",
                    "entity_type": "character",
                    # No lifecycle_state field
                }
            }
        }
        
        registry = EntityRegistry()
        registry.load_from_dict(data)
        
        # Should default to ACTIVE
        assert registry.get_entity("harry").lifecycle_state == LifecycleState.ACTIVE


class TestActiveUniverseFiltering:
    """Tests for Phase 8.6: ASP fact filtering by active universe."""
    
    def test_get_asp_facts_filters_by_active_universe(self):
        """get_asp_facts filters entities not in active universe."""
        from engine.active_universe import ActiveUniverseResult
        
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.register_entity("hermione", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.register_entity("hogwarts", EntityType.LOCATION, chapter=0, is_agent=True)
        
        # Active universe only includes harry and hogwarts
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations={"hogwarts"},
        )
        
        facts = registry.get_asp_facts(active_universe=universe)
        
        assert "character(harry)." in facts
        assert "location(hogwarts)." in facts
        assert "character(ron)." not in facts
        assert "character(hermione)." not in facts
    
    def test_get_asp_facts_without_universe_includes_all(self):
        """Without active_universe, all ACTIVE entities are included."""
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.register_entity("ron", EntityType.CHARACTER, chapter=0, is_agent=True)
        
        facts = registry.get_asp_facts()
        
        assert "character(harry)." in facts
        assert "character(ron)." in facts
    
    def test_get_dead_character_facts_filters_by_universe(self):
        """get_dead_character_facts filters by active universe."""
        from engine.active_universe import ActiveUniverseResult
        
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.register_entity("voldemort", EntityType.CHARACTER, chapter=0, is_agent=True)
        # Set state to "dead" (not is_dead attribute)
        registry.get_entity("harry").state = "dead"
        registry.get_entity("voldemort").state = "dead"
        
        # Only harry in universe
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations=set(),
        )
        
        facts = registry.get_dead_character_facts(active_universe=universe)
        
        assert "is_dead(harry)." in facts
        assert "is_dead(voldemort)." not in facts
    
    def test_get_trait_facts_filters_by_universe(self):
        """get_trait_facts filters by active universe."""
        from engine.active_universe import ActiveUniverseResult
        
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, 
                                 is_agent=True, traits={"brave"})
        registry.register_entity("ron", EntityType.CHARACTER, chapter=0, 
                                 is_agent=True, traits={"loyal"})
        
        universe = ActiveUniverseResult(
            characters={"ron"},
            items=set(),
            locations=set(),
        )
        
        facts = registry.get_trait_facts(active_universe=universe)
        
        assert "trait(ron, loyal)." in facts
        assert "trait(harry, brave)." not in facts
    
    def test_get_emotion_facts_filters_by_universe(self):
        """get_emotion_facts filters by active universe."""
        from engine.active_universe import ActiveUniverseResult
        
        registry = EntityRegistry()
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.register_entity("draco", EntityType.CHARACTER, chapter=0, is_agent=True)
        registry.get_entity("harry").emotion = "angry"
        registry.get_entity("draco").emotion = "smug"
        
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations=set(),
        )
        
        facts = registry.get_emotion_facts(active_universe=universe)
        
        assert "character_emotion(harry, angry)." in facts
        assert "character_emotion(draco, smug)." not in facts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
