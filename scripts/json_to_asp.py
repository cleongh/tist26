#!/usr/bin/env python3
"""
json_to_asp.py - Convert Structured Story JSON to ASP Facts
============================================================

This module transforms the structured JSON representation of a story (produced
by the LLM structurer) into Answer Set Programming (ASP) facts that can be
processed by the Clingo solver.

Overview
--------

The conversion process takes JSON like:

```json
{
  "entities": {
    "characters": [{"id": "hansel"}, {"id": "gretel"}],
    "objects": [{"id": "bread", "type": "bread"}],
    "locations": [{"id": "forest"}]
  },
  "events": [
    {
      "id": "e1",
      "type": "eat",
      "agent": "hansel",
      "patient": "bread",
      "time": {"start": "t1", "end": "t1"}
    }
  ],
  "traits": [{"character": "witch", "trait": "evil"}]
}
```

And produces ASP facts like:

```prolog
character(hansel).
character(gretel).
object(bread).
bread(bread).
location(forest).
event(e1).
event_type(e1, eat).
agent(e1, hansel).
patient(e1, bread).
time(e1, t1, t1).
trait(witch, evil).
time_order(t1, t2).
```

ASP Symbol Requirements
-----------------------

ASP (Answer Set Programming) has strict requirements for symbols (identifiers):

1. Must start with a lowercase letter (a-z)
2. Can only contain alphanumeric characters and underscores
3. Cannot contain spaces, hyphens, or special characters
4. Are case-sensitive (but we normalize to lowercase)

The `sanitize_symbol()` function handles these requirements by:
- Replacing spaces and hyphens with underscores
- Removing special characters
- Ensuring the first character is a lowercase letter
- Converting everything to lowercase

Array Handling
--------------

When the LLM produces arrays for agent or patient (e.g., when multiple
characters perform an action together), we emit separate facts for each:

JSON:
```json
{"agent": ["hansel", "gretel"], "patient": "bread"}
```

ASP:
```prolog
agent(e1, hansel).
agent(e1, gretel).
patient(e1, bread).
```

This allows the ASP rules to reason about each participant individually.

Time Ordering
-------------

Events have temporal information (start/end times). We extract all unique
time points and emit `time_order/2` facts based on their order of appearance
in the story. This creates a linear timeline that the ASP rules use for
temporal reasoning.

Usage
-----

As a module:
```python
from json_to_asp import json_to_asp

data = {"entities": {...}, "events": [...], ...}
asp_facts = json_to_asp(data)
print(asp_facts)
```

From command line:
```bash
python json_to_asp.py < story.json > facts.lp
```

Author: Research Project - Narrative Evaluation
"""

import json
import re
from pathlib import Path


def emit_fact(f, *args):
    """
    Create an ASP fact string from a functor and arguments.
    
    An ASP fact is a statement that is unconditionally true. It has the form:
        functor(arg1, arg2, ...).
    
    For example:
        emit_fact("character", "hansel") -> "character(hansel)."
        emit_fact("time", "e1", "t1", "t2") -> "time(e1,t1,t2)."
    
    Args:
        f: The functor (predicate name)
        *args: Arguments to the predicate
        
    Returns:
        A string representing the ASP fact, ending with a period
    """
    args_str = ",".join(args)
    return f"{f}({args_str})."


def sanitize_symbol(value):
    """
    Convert a value to a valid ASP symbol.
    
    ASP symbols (atoms) must follow specific lexical rules:
    - Must start with a lowercase letter
    - Can only contain letters, digits, and underscores
    - Cannot contain spaces, hyphens, or special characters
    
    This function performs the following transformations:
    1. For arrays: recursively sanitize each element and join with "__"
    2. Replace spaces, hyphens, dots, etc. with underscores
    3. Remove any remaining invalid characters
    4. Prefix with 'n' if starts with a digit
    5. Convert to lowercase
    6. Return "unknown" if result is empty
    
    Examples:
        "Hansel" -> "hansel"
        "white pebbles" -> "white_pebbles"
        "e-1" -> "e_1"
        "123abc" -> "n123abc"
        ["hansel", "gretel"] -> "hansel__gretel"
    
    Args:
        value: The value to sanitize (string, number, list, or None)
        
    Returns:
        A valid ASP symbol string
    """
    if value is None:
        return "null"
        
    # Handle arrays by joining with double underscore
    # This maintains backward compatibility while allowing array representation
    if isinstance(value, list):
        return "__".join(sanitize_symbol(v) for v in value)
        
    s = str(value)
    
    # Replace common problematic characters with underscores
    s = s.replace(" ", "_")   # "white pebbles" -> "white_pebbles"
    s = s.replace("-", "_")   # "e-1" -> "e_1"
    s = s.replace("'", "")    # "don't" -> "dont"
    s = s.replace('"', "")    # remove quotes
    s = s.replace("[", "")    # remove brackets
    s = s.replace("]", "")
    s = s.replace("(", "")    # remove parentheses
    s = s.replace(")", "")
    s = s.replace(".", "_")   # "1.5" -> "1_5"
    s = s.replace(",", "_")   # "a,b" -> "a_b"
    s = s.replace(":", "_")   # "time:1" -> "time_1"
    
    # Remove any remaining non-alphanumeric characters except underscore
    s = re.sub(r'[^a-zA-Z0-9_]', '', s)
    
    # Handle empty string
    if not s:
        return "unknown"
        
    # ASP symbols cannot start with a digit - prefix with 'n'
    if s[0].isdigit():
        s = "n" + s
        
    # ASP symbols should be lowercase for consistency
    s = s.lower()
    
    return s


def parse_term(term):
    """
    Parse an ASP-like term string into its components.
    
    This function parses terms that may appear in the structured JSON,
    particularly in fluent definitions. Terms can be:
    - Simple atoms: "alive"
    - Compound terms: "alive(hansel)"
    - Negated terms: "not(alive(hansel))"
    
    Examples:
        "alive" -> (False, "alive", [])
        "alive(hansel)" -> (False, "alive", ["hansel"])
        "not(alive(hansel))" -> (True, "alive", ["hansel"])
    
    Args:
        term: A string representing an ASP-like term
        
    Returns:
        Tuple of (is_negated, functor, arguments_list)
    """
    term = term.strip()
    neg = False
    
    # Check for negation wrapper
    if term.startswith("not(") and term.endswith(")"):
        neg = True
        term = term[4:-1].strip()
        
    # Try to match compound term: functor(arg1, arg2, ...)
    m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\(([^()]*)\)$", term)
    if not m:
        # Simple atom - no arguments
        return neg, term, []
        
    functor = m.group(1)
    args = [a.strip() for a in m.group(2).split(",") if a.strip()]
    return neg, functor, args


def role_from_var(var, head_args):
    """
    Determine the role of a variable based on its position in the head.
    
    In ASP rules extracted from the story, variables in the body may
    correspond to different roles (agent, patient, etc.) based on their
    position in the head predicate.
    
    Convention:
    - Position 0 -> "agent" (who does the action)
    - Position 1 -> "patient" (who/what receives the action)
    - Other positions -> "arg{n}"
    
    Args:
        var: The variable name to look up
        head_args: List of arguments from the rule head
        
    Returns:
        Role string: "agent", "patient", "arg3", etc., or "unknown"
    """
    if var in head_args:
        idx = head_args.index(var)
        if idx == 0:
            return "agent"
        if idx == 1:
            return "patient"
        return f"arg{idx + 1}"
    return "unknown"


def json_to_asp(data, *, include_candidates=False):
    """
    Convert structured story JSON to ASP facts.
    
    This is the main conversion function. It processes all sections of the
    structured JSON and generates corresponding ASP facts.
    
    Sections processed:
    1. **entities.characters**: character(id) facts
    2. **entities.objects**: object(id) + type(id) facts
    3. **entities.locations**: location(id) facts
    4. **events**: event(id), event_type(id, type), agent(id, who), 
       patient(id, what), location(id, where), time(id, start, end),
       requires_focus(id) facts
    5. **fluents**: holds(fluent(...), start, end) facts
    6. **traits**: trait(character, trait) facts
    7. **rules**: precondition/causes facts (if extractable)
    8. **candidate_rules**: raw ASP rules (if include_candidates=True)
    
    The function also generates:
    - time_order(t1, t2) facts for temporal sequencing
    
    Args:
        data: Dictionary containing structured story data from LLM
        include_candidates: If True, include candidate_rules as raw ASP
        
    Returns:
        String containing all ASP facts, one per line, ending with newline
        
    Example:
        >>> data = {
        ...     "entities": {
        ...         "characters": [{"id": "hansel"}],
        ...         "objects": [{"id": "bread", "type": "bread"}],
        ...         "locations": [{"id": "forest"}]
        ...     },
        ...     "events": [{
        ...         "id": "e1", "type": "eat",
        ...         "agent": "hansel", "patient": "bread",
        ...         "time": {"start": "t1"}
        ...     }],
        ...     "traits": [{"character": "hansel", "trait": "brave"}]
        ... }
        >>> print(json_to_asp(data))
        character(hansel).
        object(bread).
        bread(bread).
        location(forest).
        event(e1).
        event_type(e1,eat).
        agent(e1,hansel).
        patient(e1,bread).
        time(e1,t1,t1).
        time_order(t1,t1).
        trait(hansel,brave).
    """
    out_lines = []

    # =========================================================================
    # ENTITIES
    # =========================================================================
    
    # Characters - people, animals, or other agents that can perform actions
    for ch in data.get("entities", {}).get("characters", []):
        out_lines.append(emit_fact("character", sanitize_symbol(ch["id"])))
        
    # Objects - things that can be manipulated, used, or affected
    for obj in data.get("entities", {}).get("objects", []):
        obj_id = sanitize_symbol(obj["id"])
        out_lines.append(emit_fact("object", obj_id))
        
        # If object has a type, emit a type-specific fact
        # This enables type-based reasoning (e.g., bread is edible)
        if obj.get("type"):
            obj_type = sanitize_symbol(obj["type"])
            out_lines.append(emit_fact(obj_type, obj_id))
            
    # Locations - places where events can occur
    for loc in data.get("entities", {}).get("locations", []):
        out_lines.append(emit_fact("location", sanitize_symbol(loc["id"])))

    # =========================================================================
    # EVENTS
    # =========================================================================
    
    # Track time points in order of appearance for temporal ordering
    times_seen = []
    
    for ev in data.get("events", []):
        ev_id = sanitize_symbol(ev["id"])
        
        # Basic event declaration
        out_lines.append(emit_fact("event", ev_id))
        
        # Event type (e.g., eat, walk, take, die)
        if ev.get("type"):
            out_lines.append(emit_fact("event_type", ev_id, sanitize_symbol(ev["type"])))
            
        # Agent(s) - who performs the action
        # Can be single value or array (multiple agents acting together)
        if ev.get("agent"):
            agents = ev["agent"] if isinstance(ev["agent"], list) else [ev["agent"]]
            for a in agents:
                out_lines.append(emit_fact("agent", ev_id, sanitize_symbol(a)))
                
        # Patient(s) - who/what receives the action
        # Can be single value or array (multiple patients)
        if ev.get("patient"):
            patients = ev["patient"] if isinstance(ev["patient"], list) else [ev["patient"]]
            for p in patients:
                out_lines.append(emit_fact("patient", ev_id, sanitize_symbol(p)))
                
        # Location - where the event occurs
        if ev.get("location"):
            out_lines.append(emit_fact("location", ev_id, sanitize_symbol(ev["location"])))
            
        # Time interval - when the event occurs
        if ev.get("time"):
            start = sanitize_symbol(ev["time"].get("start", "t0"))
            # If no end time specified, assume instantaneous (end = start)
            end = sanitize_symbol(ev["time"].get("end", start))
            out_lines.append(emit_fact("time", ev_id, start, end))
            
            # Track time points for ordering
            if start not in times_seen:
                times_seen.append(start)
            if end not in times_seen:
                times_seen.append(end)
                
        # Focus requirement - does this action require full attention?
        if ev.get("requires_focus"):
            out_lines.append(emit_fact("requires_focus", ev_id))
        
        # Story fragment - exact quote from the story for traceability
        # This is crucial for error reporting: allows us to show which text caused errors
        if ev.get("story_fragment"):
            # Store as a comment and also as a fact for later lookup
            fragment = str(ev["story_fragment"]).replace('"', '\\"').replace('\n', ' ')[:500]
            out_lines.append(f'% Fragment for {ev_id}: "{fragment[:100]}..."')
            # Also emit as a fact (quoted string) for programmatic access
            out_lines.append(f'story_fragment({ev_id}, "{fragment}").')

    # =========================================================================
    # TEMPORAL ORDERING
    # =========================================================================
    
    # Generate time_order facts based on order of appearance
    # This creates a linear timeline: t1 < t2 < t3 < ...
    for i in range(len(times_seen) - 1):
        out_lines.append(emit_fact("time_order", times_seen[i], times_seen[i + 1]))

    # =========================================================================
    # FLUENTS
    # =========================================================================
    
    # Fluents are time-varying properties (e.g., "door is open", "hansel is alive")
    for fl in data.get("fluents", []):
        # Parse the fluent ID which may be a compound term like "alive(hansel)"
        neg, pred, term_args = parse_term(fl["id"])
        
        # Handle different JSON formats for time specification
        # Format 1: {"time": {"start": ..., "end": ...}}
        # Format 2: {"start": ..., "end": ...}  (flat)
        # Format 3: {"time_start": ..., "time_end": ...}
        if "time" in fl and isinstance(fl["time"], dict):
            start = sanitize_symbol(fl["time"].get("start", "t_unknown"))
            end = sanitize_symbol(fl["time"].get("end", start))
        elif "start" in fl:
            start = sanitize_symbol(fl.get("start", "t_unknown"))
            end = sanitize_symbol(fl.get("end", start))
        elif "time_start" in fl:
            start = sanitize_symbol(fl.get("time_start", "t_unknown"))
            end = sanitize_symbol(fl.get("time_end", start))
        else:
            # Default fallback - use t_unknown for missing time info
            start = "t_unknown"
            end = "t_unknown"
        
        # Build the fluent term for ASP
        if len(term_args) == 1:
            fluent_term = f"fluent({pred},{sanitize_symbol(term_args[0])})"
        else:
            fluent_term = f"fluent({pred})"
            
        # Handle negated fluents
        if neg:
            fluent_term = f"not({fluent_term})"
            
        out_lines.append(emit_fact("holds", fluent_term, start, end))

    # =========================================================================
    # RELATIONSHIPS (Emotional relations between characters)
    # =========================================================================
    
    # Character relationships (loves, hates, fears, trusts, distrusts)
    # These are crucial for emotional error detection
    for rel in data.get("relationships", []):
        rel_type = sanitize_symbol(rel.get("type", "unknown"))
        from_char = sanitize_symbol(rel.get("from", "unknown"))
        to_char = sanitize_symbol(rel.get("to", "unknown"))
        out_lines.append(emit_fact(rel_type, from_char, to_char))
        
        # Store story fragment showing the relationship
        if rel.get("story_fragment"):
            fragment = str(rel["story_fragment"]).replace('"', '\\"').replace('\n', ' ')[:300]
            out_lines.append(f'relationship_fragment({rel_type}, {from_char}, {to_char}, "{fragment}").')

    # =========================================================================
    # EMOTIONAL STATES
    # =========================================================================
    
    # Track emotional states of characters over time
    for em_state in data.get("emotional_states", []):
        char = sanitize_symbol(em_state.get("character", "unknown"))
        emotion = sanitize_symbol(em_state.get("emotion", "neutral"))
        
        # Get time interval
        if "time" in em_state and isinstance(em_state["time"], dict):
            start = sanitize_symbol(em_state["time"].get("start", "t_unknown"))
            end = sanitize_symbol(em_state["time"].get("end", start))
        else:
            start = "t_unknown"
            end = "t_unknown"
        
        out_lines.append(emit_fact("emotional_state", char, emotion, start))
        
        # Store story fragment showing the emotional state
        if em_state.get("story_fragment"):
            fragment = str(em_state["story_fragment"]).replace('"', '\\"').replace('\n', ' ')[:300]
            out_lines.append(f'emotion_fragment({char}, {emotion}, "{fragment}").')

    # =========================================================================
    # LOCATION GRAPH
    # =========================================================================
    
    # Track spatial relationships between locations
    for loc_rel in data.get("location_graph", []):
        from_loc = sanitize_symbol(loc_rel.get("from", "unknown"))
        to_loc = sanitize_symbol(loc_rel.get("to", "unknown"))
        relation = sanitize_symbol(loc_rel.get("relation", "adjacent"))
        
        if relation == "distant":
            out_lines.append(emit_fact("distant", from_loc, to_loc))
        elif relation == "adjacent":
            out_lines.append(emit_fact("adjacent", from_loc, to_loc))
        elif relation == "contains":
            out_lines.append(emit_fact("contains", from_loc, to_loc))

    # =========================================================================
    # CAUSAL CHAINS
    # =========================================================================
    
    # Track explicit causal relationships between events
    for causal in data.get("causal_chains", []):
        cause_event = sanitize_symbol(causal.get("cause_event", "unknown"))
        effect_event = sanitize_symbol(causal.get("effect_event", "unknown"))
        out_lines.append(emit_fact("causes", cause_event, effect_event))
        
        # Store story fragment showing causation
        if causal.get("story_fragment"):
            fragment = str(causal["story_fragment"]).replace('"', '\\"').replace('\n', ' ')[:300]
            out_lines.append(f'causal_fragment({cause_event}, {effect_event}, "{fragment}").')

    # =========================================================================
    # TRAITS
    # =========================================================================
    
    # Character traits (e.g., "hansel is brave", "witch is evil")
    for tr in data.get("traits", []):
        out_lines.append(emit_fact(
            "trait",
            sanitize_symbol(tr["character"]),
            sanitize_symbol(tr["trait"])
        ))

    # =========================================================================
    # RULES (Preconditions and Effects)
    # =========================================================================
    
    # Extract rules that define preconditions or effects of actions
    for rule in data.get("rules", []):
        head = rule["head"]
        head_neg, head_functor, head_args = parse_term(head)
        
        for body in rule.get("body", []):
            body_neg, body_functor, body_args = parse_term(body)
            
            # Skip negated heads (we don't handle these)
            if head_neg:
                continue
                
            # We only handle single-argument body predicates
            if len(body_args) != 1:
                continue
                
            role = role_from_var(body_args[0], head_args)
            pol = "neg" if body_neg else "pos"
            
            if rule["type"] == "precondition":
                # Precondition: something must be true/false before action
                out_lines.append(emit_fact("precondition", head_functor, pol, body_functor, role))
            elif rule["type"] == "causes":
                # Effect: action makes something true/false
                out_lines.append(emit_fact("causes", head_functor, pol, body_functor, role))

    # =========================================================================
    # CANDIDATE RULES (Optional)
    # =========================================================================
    
    # Candidate rules are world-knowledge rules proposed by the LLM
    # They're included as raw ASP if requested (for experimentation)
    if include_candidates:
        for cand in data.get("candidate_rules", []):
            rule_text = cand["rule"].rstrip(".")
            if not rule_text.endswith("."):
                rule_text += "."
            out_lines.append(rule_text)

    return "\n".join(out_lines) + "\n"


# =============================================================================
# COMMAND-LINE INTERFACE
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Read JSON from stdin or file argument
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        data = json.loads(input_path.read_text())
    else:
        data = json.loads(sys.stdin.read())
        
    # Convert and output to stdout
    print(json_to_asp(data), end="")
