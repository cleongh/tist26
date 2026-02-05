#!/usr/bin/env python3
"""
domain_generator.py - Generate Domain-Specific ASP Rules from Stories
======================================================================

This module analyzes stories and generates domain-specific ASP facts and rules
that work together with the general rules module (rules/general.lp).

ARCHITECTURE:
- Input: List of story texts or structured JSON from LLM
- Output: ASP rules file containing domain-specific knowledge

GENERATED CONTENT:
1. Location distance facts (distant/2)
2. Character relationships (loves/2, hates/2, fears/2, etc.)
3. Emotional states (emotional_state/3)
4. Event significance markers (significant_event/1)
5. Custom preconditions and effects (causes/4, precondition/4)
6. Domain-specific object properties

The domain module is story-collection-specific and is regenerated for each
experiment based on the stories being analyzed.

Author: Research Project - Narrative Evaluation
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional


def sanitize_symbol(value: Any) -> str:
    """Convert a value to a valid ASP symbol."""
    if value is None:
        return "null"
    if isinstance(value, list):
        return "__".join(sanitize_symbol(v) for v in value)
    s = str(value)
    s = s.replace(" ", "_").replace("-", "_").replace("'", "").replace('"', "")
    s = s.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    s = s.replace(".", "_").replace(",", "_").replace(":", "_")
    s = re.sub(r'[^a-zA-Z0-9_]', '', s)
    if not s:
        return "unknown"
    if s[0].isdigit():
        s = "n" + s
    return s.lower()


class DomainGenerator:
    """
    Generates domain-specific ASP rules from analyzed stories.
    
    The generator extracts:
    - Character relationships from narrative context
    - Location geography and distances
    - Emotional states over time
    - Domain-specific causal rules
    - Event significance markers
    """
    
    def __init__(self):
        self.locations: set = set()
        self.characters: set = set()
        self.objects: set = set()
        self.relationships: List[tuple] = []
        self.emotional_states: List[tuple] = []
        self.location_distances: List[tuple] = []
        self.significant_events: set = set()
        self.initial_events: set = set()
        self.custom_causes: List[tuple] = []
        self.custom_preconditions: List[tuple] = []
        self.decorative_objects: set = set()
        self.justified_harms: set = set()
        
    def add_story_data(self, structured_data: Dict[str, Any]) -> None:
        """
        Process structured story data and extract domain knowledge.
        
        Args:
            structured_data: JSON structure from LLM story parsing
        """
        # Extract entities
        entities = structured_data.get("entities", {})
        
        for ch in entities.get("characters", []):
            self.characters.add(sanitize_symbol(ch.get("id", "")))
            
        for obj in entities.get("objects", []):
            self.objects.add(sanitize_symbol(obj.get("id", "")))
            
        for loc in entities.get("locations", []):
            self.locations.add(sanitize_symbol(loc.get("id", "")))
            
        # Extract relationships from explicit relationship data
        for rel in structured_data.get("relationships", []):
            rel_type = sanitize_symbol(rel.get("type", ""))
            from_char = sanitize_symbol(rel.get("from", ""))
            to_char = sanitize_symbol(rel.get("to", ""))
            if rel_type and from_char and to_char:
                self.relationships.append((rel_type, from_char, to_char))
                
        # Extract emotional states from fluents
        for fl in structured_data.get("fluents", []):
            fl_id = fl.get("id", "")
            # Parse emotional state fluents like "happy(alice)"
            if any(emotion in fl_id.lower() for emotion in 
                   ["happy", "sad", "angry", "afraid", "calm", "excited", "jealous"]):
                # Extract emotion and character from fluent
                match = re.match(r"(\w+)\((\w+)\)", fl_id)
                if match:
                    emotion = sanitize_symbol(match.group(1))
                    character = sanitize_symbol(match.group(2))
                    time_info = fl.get("time", {})
                    start = sanitize_symbol(time_info.get("start", "t0"))
                    self.emotional_states.append((character, emotion, start))
                    
        # Extract location distances from constraints
        for constraint in structured_data.get("constraints", []):
            if constraint.get("type") == "distance":
                loc1 = sanitize_symbol(constraint.get("location1", ""))
                loc2 = sanitize_symbol(constraint.get("location2", ""))
                if loc1 and loc2:
                    self.location_distances.append((loc1, loc2))
                    
        # Mark first event as initial
        events = structured_data.get("events", [])
        if events:
            first_event = sanitize_symbol(events[0].get("id", ""))
            if first_event:
                self.initial_events.add(first_event)
                
        # Extract causal rules
        for rule in structured_data.get("rules", []):
            if rule.get("type") == "causes":
                event_type = sanitize_symbol(rule.get("head", ""))
                effect = rule.get("effect", {})
                prop = sanitize_symbol(effect.get("property", ""))
                polarity = "pos" if effect.get("positive", True) else "neg"
                role = sanitize_symbol(effect.get("role", "patient"))
                if event_type and prop:
                    self.custom_causes.append((event_type, polarity, prop, role))
                    
            elif rule.get("type") == "precondition":
                event_type = sanitize_symbol(rule.get("head", ""))
                precond = rule.get("precondition", {})
                prop = sanitize_symbol(precond.get("property", ""))
                polarity = "pos" if precond.get("required", True) else "neg"
                role = sanitize_symbol(precond.get("role", "agent"))
                if event_type and prop:
                    self.custom_preconditions.append((event_type, polarity, prop, role))
                    
    def add_relationship(self, rel_type: str, from_char: str, to_char: str) -> None:
        """Manually add a character relationship."""
        self.relationships.append((
            sanitize_symbol(rel_type),
            sanitize_symbol(from_char),
            sanitize_symbol(to_char)
        ))
        
    def add_location_distance(self, loc1: str, loc2: str) -> None:
        """Mark two locations as distant from each other."""
        self.location_distances.append((
            sanitize_symbol(loc1),
            sanitize_symbol(loc2)
        ))
        
    def add_emotional_state(self, character: str, emotion: str, time: str) -> None:
        """Add an emotional state for a character at a time."""
        self.emotional_states.append((
            sanitize_symbol(character),
            sanitize_symbol(emotion),
            sanitize_symbol(time)
        ))
        
    def mark_significant_event(self, event_id: str) -> None:
        """Mark an event as significant (requires causation)."""
        self.significant_events.add(sanitize_symbol(event_id))
        
    def mark_decorative(self, obj_id: str) -> None:
        """Mark an object as decorative (exempt from Chekhov's gun)."""
        self.decorative_objects.add(sanitize_symbol(obj_id))
        
    def generate_asp(self) -> str:
        """
        Generate the complete domain-specific ASP module.
        
        Returns:
            String containing all domain-specific ASP rules
        """
        lines = []
        
        # Header
        lines.append("% =============================================================================")
        lines.append("% DOMAIN-SPECIFIC MODULE (Auto-generated)")
        lines.append("% =============================================================================")
        lines.append("%")
        lines.append("% This file contains domain-specific facts and rules extracted from the")
        lines.append("% stories being analyzed. It should be used together with rules/general.lp.")
        lines.append("%")
        lines.append("% Generated content:")
        lines.append(f"% - {len(self.relationships)} character relationships")
        lines.append(f"% - {len(self.emotional_states)} emotional states")
        lines.append(f"% - {len(self.location_distances)} location distance pairs")
        lines.append(f"% - {len(self.significant_events)} significant events")
        lines.append(f"% - {len(self.custom_causes)} custom causal rules")
        lines.append("% =============================================================================")
        lines.append("")
        
        # Location distances
        if self.location_distances:
            lines.append("% ----- Location Distances -----")
            lines.append("% Locations that are far apart (require travel time)")
            for loc1, loc2 in self.location_distances:
                lines.append(f"distant({loc1}, {loc2}).")
                lines.append(f"distant({loc2}, {loc1}).")  # Symmetric
            lines.append("")
            
        # Character relationships
        if self.relationships:
            lines.append("% ----- Character Relationships -----")
            for rel_type, from_char, to_char in self.relationships:
                lines.append(f"{rel_type}({from_char}, {to_char}).")
            lines.append("")
            
        # Emotional states
        if self.emotional_states:
            lines.append("% ----- Emotional States -----")
            for char, emotion, time in self.emotional_states:
                lines.append(f"emotional_state({char}, {emotion}, {time}).")
            lines.append("")
            
        # Significant events
        if self.significant_events:
            lines.append("% ----- Significant Events (require causation) -----")
            for event in self.significant_events:
                lines.append(f"significant_event({event}).")
            lines.append("")
            
        # Initial events
        if self.initial_events:
            lines.append("% ----- Initial Events (don't require prior cause) -----")
            for event in self.initial_events:
                lines.append(f"initial_event({event}).")
            lines.append("")
            
        # Decorative objects
        if self.decorative_objects:
            lines.append("% ----- Decorative Objects (exempt from Chekhov's gun) -----")
            for obj in self.decorative_objects:
                lines.append(f"decorative({obj}).")
            lines.append("")
            
        # Justified harms
        if self.justified_harms:
            lines.append("% ----- Justified Harmful Actions -----")
            for event in self.justified_harms:
                lines.append(f"justified_harm({event}).")
            lines.append("")
            
        # Custom causal rules
        if self.custom_causes:
            lines.append("% ----- Domain-Specific Causal Rules -----")
            for event_type, polarity, prop, role in self.custom_causes:
                lines.append(f"causes({event_type}, {polarity}, {prop}, {role}).")
            lines.append("")
            
        # Custom preconditions
        if self.custom_preconditions:
            lines.append("% ----- Domain-Specific Preconditions -----")
            for event_type, polarity, prop, role in self.custom_preconditions:
                lines.append(f"precondition({event_type}, {polarity}, {prop}, {role}).")
            lines.append("")
            
        # Default rules (always included)
        lines.append("% ----- Default Causal Rules -----")
        lines.append("% Common-sense rules that apply to most narratives")
        lines.append("")
        lines.append("% Opening/closing")
        lines.append("causes(open, pos, open, patient).")
        lines.append("causes(close, neg, open, patient).")
        lines.append("")
        lines.append("% Locking/unlocking")
        lines.append("causes(lock, pos, locked, patient).")
        lines.append("causes(unlock, neg, locked, patient).")
        lines.append("")
        lines.append("% Breaking/fixing")
        lines.append("causes(break, pos, broken, patient).")
        lines.append("causes(fix, neg, broken, patient).")
        lines.append("causes(repair, neg, broken, patient).")
        lines.append("")
        lines.append("% Sleep/wake")
        lines.append("causes(sleep, pos, asleep, agent).")
        lines.append("causes(wake, neg, asleep, agent).")
        lines.append("precondition(wake, pos, asleep, agent).")
        lines.append("")
        lines.append("% Possession")
        lines.append("causes(take, pos, has, agent).")
        lines.append("causes(give, neg, has, agent).")
        lines.append("causes(give, pos, has, patient).")
        lines.append("causes(drop, neg, has, agent).")
        lines.append("")
        
        lines.append("% =============================================================================")
        lines.append("% END OF DOMAIN MODULE")
        lines.append("% =============================================================================")
        
        return "\n".join(lines) + "\n"
    
    def save(self, path: Path) -> None:
        """Save the domain module to a file."""
        path.write_text(self.generate_asp())


def generate_domain_from_stories(
    structured_stories: List[Dict[str, Any]],
    output_path: Optional[Path] = None
) -> str:
    """
    Generate domain module from multiple structured stories.
    
    Args:
        structured_stories: List of structured JSON from LLM parsing
        output_path: Optional path to save the generated module
        
    Returns:
        Generated ASP rules as string
    """
    generator = DomainGenerator()
    
    for story_data in structured_stories:
        generator.add_story_data(story_data)
        
    asp_content = generator.generate_asp()
    
    if output_path:
        output_path.write_text(asp_content)
        
    return asp_content


# =============================================================================
# COMMAND-LINE INTERFACE
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python domain_generator.py <structured_story.json> [output.lp]")
        sys.exit(1)
        
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    
    if input_path.suffix == ".json":
        data = json.loads(input_path.read_text())
        if isinstance(data, list):
            structured_stories = data
        else:
            structured_stories = [data]
    else:
        print("Input must be a JSON file")
        sys.exit(1)
        
    asp_content = generate_domain_from_stories(structured_stories, output_path)
    
    if not output_path:
        print(asp_content)
