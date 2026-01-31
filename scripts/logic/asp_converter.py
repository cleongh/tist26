"""
ASP fact conversion utilities.

Converts structured JSON to ASP facts for Clingo.
"""

import re
from typing import Dict, List, Set

from ..state.config import normalize_character_id


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
    """Sanitize and normalize character ID."""
    s = sanitize(v)
    if s and s != "unknown":
        s = normalize_character_id(s)
    return s


def to_asp(data: Dict, chapter_num: int, story_rules: List[Dict] = None) -> str:
    """
    Convert structured JSON to ASP facts.
    
    Args:
        data: Structured chapter data with entities and events
        chapter_num: Chapter number for context
        story_rules: Optional list of story rules to include
        
    Returns:
        ASP program as string
    """
    story_rules = story_rules or []
    lines = [f"% Chapter {chapter_num} facts"]
    
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
    
    # Process relationships
    for rel in entities.get("relationships", []):
        from_char = sanitize_char(rel.get("from", ""))
        to_char = sanitize_char(rel.get("to", ""))
        rel_type = sanitize(rel.get("type", "neutral"))
        if from_char != "unknown" and to_char != "unknown" and rel_type != "neutral":
            lines.append(f"relationship({from_char}, {to_char}, {rel_type}).")
    
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
        
        source_text = event.get('source_text', '')
        if source_text:
            escaped_source = source_text.replace('"', '\\"').replace('\n', ' ')[:80]
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
        
        after_event = sanitize(event.get("after", ""))
        if after_event and after_event != "unknown" and after_event != "null":
            lines.append(f"must_precede({after_event}, {eid}).")
    
    # Generate implicit time ordering
    event_ids = [sanitize(e.get("global_id", e.get("id", f"e{chapter_num}_{i+1}"))) 
                 for i, e in enumerate(data.get("events", []))]
    for i in range(len(event_ids) - 1):
        lines.append(f"time_order({event_ids[i]}, {event_ids[i+1]}).")
    
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
    
    return "\n".join(lines)
