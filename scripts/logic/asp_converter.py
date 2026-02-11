"""
ASP fact conversion utilities.

Converts structured JSON to ASP facts for Clingo.

Phase 8.10: Supports active_universe parameter to filter relationship facts.
No relationship fact is emitted unless BOTH endpoints are in the active universe.

Phase 8.10.1: Removed dependency on deprecated normalize_character_id.
Character IDs are now only sanitized (lowercased, snake_cased), not aliased.
Dynamic alias resolution should be handled by AliasResolver at extraction time.
"""

import re
from typing import Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.active_universe import ActiveUniverseResult


def sanitize(v) -> str:
    """Sanitize a value for use in ASP."""
    if not v: 
        return "unknown"
    s = str(v).lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit(): 
        s = 'n' + s
    return s or "unknown"


def sanitize_char(v) -> str:
    """
    Sanitize a character ID for use in ASP.
    
    This function only performs basic sanitization (lowercase, snake_case).
    It does NOT perform character alias resolution - that should be handled
    by engine.alias_resolver.AliasResolver at extraction time.
    
    Args:
        v: Character ID or name to sanitize
        
    Returns:
        Sanitized character ID suitable for ASP
    """
    return sanitize(v)


def to_asp(
    data: Dict,
    chapter_num: int,
    story_rules: List[Dict] = None,
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> str:
    """
    Convert structured JSON to ASP facts.
    
    Args:
        data: Structured chapter data with entities and events
        chapter_num: Chapter number for context
        story_rules: Optional list of story rules to include
        active_universe: Optional filter - only include relationship facts where
                        BOTH endpoints are in this universe. If None, all
                        relationships are included.
        
    Returns:
        ASP program as string
        
    Phase 8.10: Relationship facts are now guarded by active_universe.
    """
    story_rules = story_rules or []
    lines = [f"% Chapter {chapter_num} facts"]
    
    # Extract active entity set for relationship filtering
    universe_entities: Optional[Set[str]] = None
    if active_universe is not None:
        universe_entities = active_universe.all_entities
    
    # Track all character/location IDs and their name variants
    char_ids: Set[str] = set()
    location_ids: Set[str] = set()
    item_ids: Set[str] = set()
    
    entities = data.get("entities", {})
    
    # Process characters
    for char in entities.get("characters", []):
        cid = sanitize_char(char.get("id", ""))
        cname = sanitize_char(char.get("name", ""))
        if cid and cid != "unknown":
            lines.append(f"character({cid}).")
            char_ids.add(cid)
        if cname and cname != "unknown" and cname != cid:
            lines.append(f"character({cname}).")
            char_ids.add(cname)
        
        # Add emotional state if provided
        emotion = sanitize(char.get("emotion", ""))
        if emotion and emotion != "unknown" and emotion != "neutral":
            char_key = cid if cid != "unknown" else cname
            if char_key != "unknown":
                lines.append(f"character_emotion({char_key}, {emotion}).")
        
        # Add physical state if provided
        state = sanitize(char.get("state", ""))
        if state and state != "unknown" and state != "normal":
            char_key = cid if cid != "unknown" else cname
            if char_key != "unknown":
                lines.append(f"character_state({char_key}, {state}).")
                if state == "dead":
                    lines.append(f"is_dead({char_key}).")
        
        # Add appearance if provided
        appearance = sanitize(char.get("appearance", ""))
        if appearance and appearance != "unknown" and appearance not in ("normal", "none"):
            char_key = cid if cid != "unknown" else cname
            if char_key != "unknown":
                lines.append(f"character_appearance({char_key}, {appearance}).")
    
    # Process items
    for item in entities.get("items", []):
        iid = sanitize(item.get("id", ""))
        iname = sanitize(item.get("name", ""))
        if iid and iid != "unknown":
            lines.append(f"item({iid}).")
            item_ids.add(iid)
        if iname and iname != "unknown" and iname != iid:
            lines.append(f"item({iname}).")
            item_ids.add(iname)
        
        item_state = sanitize(item.get("state", ""))
        if item_state and item_state != "unknown" and item_state != "intact":
            item_key = iid if iid != "unknown" else iname
            if item_key != "unknown":
                lines.append(f"item_state({item_key}, {item_state}).")
    
    # Legacy support for "objects" field
    for obj in entities.get("objects", []):
        oid = sanitize(obj.get("id", obj.get("name", "")))
        if oid and oid != "unknown":
            lines.append(f"object({oid}).")
            item_ids.add(oid)
    
    # Process locations
    for loc in entities.get("locations", []):
        lid = sanitize(loc.get("id", ""))
        lname = sanitize(loc.get("name", ""))
        if lid and lid != "unknown":
            lines.append(f"location_entity({lid}).")
            location_ids.add(lid)
        if lname and lname != "unknown" and lname != lid:
            lines.append(f"location_entity({lname}).")
            location_ids.add(lname)
        
        loc_key = lid if lid != "unknown" else lname
        for conn in loc.get("connections", []):
            conn_id = sanitize(conn)
            if conn_id and conn_id != "unknown" and loc_key != "unknown":
                lines.append(f"connected({loc_key}, {conn_id}).")
                lines.append(f"connected({conn_id}, {loc_key}).")
        
        for sub in loc.get("contains", []):
            sub_id = sanitize(sub)
            if sub_id and sub_id != "unknown" and loc_key != "unknown":
                lines.append(f"contains({loc_key}, {sub_id}).")
                lines.append(f"connected({loc_key}, {sub_id}).")
                lines.append(f"connected({sub_id}, {loc_key}).")
    
    # Process relationships - only emit if BOTH endpoints are in active universe
    # Phase 8.10: Strict ASP universe boundary enforcement
    for rel in entities.get("relationships", []):
        from_char = sanitize_char(rel.get("from", ""))
        to_char = sanitize_char(rel.get("to", ""))
        rel_type = sanitize(rel.get("type", "neutral"))
        if from_char != "unknown" and to_char != "unknown" and rel_type != "neutral":
            # Guard: skip if either endpoint is not in active universe
            if universe_entities is not None:
                if from_char not in universe_entities or to_char not in universe_entities:
                    continue  # Silently skip - no error logging per requirements
            lines.append(f"relationship({from_char}, {to_char}, {rel_type}).")
            # Also emit initial_relationship for EC framework
            lines.append(f"initial_relationship({from_char}, {to_char}, {rel_type}).")
    
    # Process events
    for i, event in enumerate(data.get("events", [])):
        eid = sanitize(event.get("global_id", event.get("id", f"e{chapter_num}_{i+1}")))
        lines.append(f"event({eid}).")
        etype = sanitize(event.get("type", "action"))
        lines.append(f"event_type({eid}, {etype}).")
        
        lines.append(f"event_global({eid}, {etype}, {chapter_num}).")
        
        if eid.startswith('e') and eid[1:].isdigit():
            event_num = int(eid[1:])
            lines.append(f"event_order({eid}, {event_num}).")
            # Emit event_time/2 for time-indexed rules (emotional.lp, etc.)
            # Time is derived from event order to maintain monotonicity
            lines.append(f"event_time({eid}, {event_num}).")
        
        # Emit narrative_time_relation for non-linear narration detection
        narrative_time = event.get('narrative_time')
        if narrative_time:
            nt = sanitize(narrative_time)
            lines.append(f"narrative_time_relation({eid}, {nt}).")
        
        source_text = event.get('source_text', '')
        if source_text:
            # Escape/replace problematic characters for ASP
            # Replace curly quotes and other Unicode with ASCII equivalents
            escaped_source = source_text.replace(''', "'").replace(''', "'")
            escaped_source = escaped_source.replace('"', "'").replace('"', "'")
            escaped_source = escaped_source.replace('—', '-').replace('–', '-')
            escaped_source = escaped_source.replace('\n', ' ')
            # Remove double quotes entirely (they cause ASP parsing issues)
            escaped_source = escaped_source.replace('"', "'")
            # Remove any remaining non-ASCII characters
            escaped_source = ''.join(c if ord(c) < 128 else '' for c in escaped_source)
            escaped_source = escaped_source[:80]
            lines.append(f'event_source({eid}, "{escaped_source}").')
        
        if event.get("agent"):
            agent_id = sanitize_char(event['agent'])
            lines.append(f"agent({eid}, {agent_id}).")
            if agent_id not in char_ids and agent_id != "unknown":
                lines.append(f"character({agent_id}).")
                char_ids.add(agent_id)
        
        if event.get("patient"):
            patient_raw = event['patient']
            patient_id = sanitize(patient_raw)
            if patient_id in char_ids or patient_id not in item_ids:
                patient_id = sanitize_char(patient_raw)
            lines.append(f"patient({eid}, {patient_id}).")
            if etype == "death":
                lines.append(f"is_dead({patient_id}).")
        
        if event.get("location"):
            loc_id = sanitize(event['location'])
            lines.append(f"location({eid}, {loc_id}).")
            if loc_id not in location_ids and loc_id != "unknown":
                lines.append(f"location_entity({loc_id}).")
                location_ids.add(loc_id)
        
        event_emotion = sanitize(event.get("emotion", ""))
        if event_emotion and event_emotion != "unknown":
            lines.append(f"event_emotion({eid}, {event_emotion}).")
        
        # Social action type (emotion-aware event classification)
        social_action_type = sanitize(event.get("social_action_type", ""))
        if social_action_type and social_action_type != "unknown":
            lines.append(f"social_action({eid}, {social_action_type}).")
        
        # Report events: emit report/1 and recipient/3
        if etype == "report":
            lines.append(f"report({eid}).")
            recipient_id = sanitize_char(event.get("recipient", ""))
            if recipient_id and recipient_id != "unknown":
                lines.append(f"recipient({eid}, {recipient_id}).")
                # Ensure recipient is declared as a character
                if recipient_id not in char_ids:
                    lines.append(f"character({recipient_id}).")
                    char_ids.add(recipient_id)
        
        # Learn events: emit learned/3 for knowledge acquisition
        if etype == "learn":
            agent_id = sanitize_char(event.get("agent", ""))
            fact_id = sanitize(event.get("fact", ""))
            # Use event_time if available, otherwise chapter number
            event_time = event.get("event_time", chapter_num)
            if agent_id != "unknown" and fact_id != "unknown":
                lines.append(f"learned({agent_id}, {fact_id}, {event_time}).")
                lines.append(f"learn_event({eid}).")
                # Emit source if provided
                source_id = sanitize(event.get("source", ""))
                if source_id and source_id != "unknown":
                    lines.append(f"knowledge_source({eid}, {source_id}).")
    
    # Process implied_presence entries
    # Emit implied_presence/3: implied_presence(entity, location, chapter_time)
    # Chapter time is used since no specific event time is available
    # Also emit event_location for the synthetic implied presence event
    implied_presence_count = 0
    for presence in data.get("implied_presence", []):
        entity_id = sanitize(presence.get("entity", ""))
        location_id = sanitize(presence.get("location", ""))
        if entity_id != "unknown" and location_id != "unknown":
            # Check active universe filtering
            if universe_entities is not None:
                if entity_id not in universe_entities:
                    continue  # Entity not in active universe
            implied_presence_count += 1
            # Create synthetic event ID for this implied presence
            synthetic_eid = f"ip_{chapter_num}_{implied_presence_count}"
            lines.append(f"implied_presence({entity_id}, {location_id}, {chapter_num}).")
            # Emit synthetic event facts for ASP integration
            lines.append(f"implied_presence_event({synthetic_eid}).")
            lines.append(f"event({synthetic_eid}).")
            lines.append(f"event_time({synthetic_eid}, {chapter_num}).")
            lines.append(f"agent({synthetic_eid}, {entity_id}).")
            lines.append(f"event_location({synthetic_eid}, {location_id}).")
            # Ensure entity is declared (character or item)
            if entity_id not in char_ids and entity_id not in item_ids:
                # Assume character if not already known
                if universe_entities is None or entity_id in universe_entities:
                    lines.append(f"character({entity_id}).")
                    char_ids.add(entity_id)
            # Ensure location is declared
            if location_id not in location_ids:
                if universe_entities is None or location_id in universe_entities:
                    lines.append(f"location_entity({location_id}).")
                    location_ids.add(location_id)
    
    # Add story rules
    lines.append(f"\n% Story rules (dynamic, established by events)")
    lines.append(f"event_order(e0, 0).  % Initial state event")
    
    for rule in story_rules:
        if not rule.get('valid'):
            continue
        
        subj = sanitize_char(rule['subject'])
        pred = sanitize(rule['predicate'])
        obj_raw = rule.get('object')
        est_by = rule['established_by']
        
        if rule['type'] == 'relationship':
            obj = sanitize_char(obj_raw) if obj_raw else None
            # Phase 8.10: Guard relationship_rule by active universe
            # relationship_rule derives initial_relationship, so must be filtered
            if universe_entities is not None:
                if subj not in universe_entities or (obj and obj not in universe_entities):
                    continue  # Silently skip - no error logging
            lines.append(f"relationship_rule({subj}, {pred}, {obj}, {est_by}).")
        elif rule['type'] == 'trait':
            lines.append(f"trait_rule({subj}, {pred}, {est_by}).")
        elif rule['type'] == 'location':
            obj = sanitize(obj_raw) if obj_raw else None
            lines.append(f"location_rule({subj}, {obj}, {est_by}).")
        elif rule['type'] == 'possession':
            obj = sanitize(obj_raw) if obj_raw else None
            lines.append(f"possession_rule({subj}, {obj}, {est_by}).")
        elif rule['type'] == 'temporal':
            obj = sanitize(obj_raw) if obj_raw else None
            lines.append(f"temporal_rule({subj}, must_precede, {obj}, {est_by}).")
    
    # Process initial_rules from extraction data
    # These are relationship/trait rules extracted from the narrative
    initial_rules = data.get('initial_rules', [])
    if initial_rules:
        lines.append(f"\n% Initial rules from extraction")
        for rule in initial_rules:
            subj = sanitize_char(rule.get('subject', ''))
            pred = sanitize(rule.get('predicate', ''))
            obj = rule.get('object', '')
            
            if not subj or not pred:
                continue
            
            # Check if this is a relationship (has object that looks like a character)
            if obj and obj not in ('true', 'false', 'none', ''):
                obj_san = sanitize_char(obj)
                # Guard by active universe
                if universe_entities is not None:
                    if subj not in universe_entities or obj_san not in universe_entities:
                        continue
                # Emit as initial_relationship for relationship predicates
                if pred in ('hostile', 'friendly', 'friend', 'enemy', 'ally', 'love', 
                           'hate', 'fear', 'trust', 'distrust', 'respect', 'family'):
                    lines.append(f"initial_relationship({subj}, {obj_san}, {pred}).")
                else:
                    # Other predicates as trait rules
                    lines.append(f"trait_rule({subj}, {pred}, e0).")
            else:
                # This is a trait (predicate without object or boolean object)
                lines.append(f"character_trait({subj}, {pred}).")
    
    return "\n".join(lines)
