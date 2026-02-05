#!/usr/bin/env python3
"""
ilasp_task_generator.py - ILASP Task Generation for Narrative Consistency
==========================================================================

This module generates ILASP learning tasks with proper positive and negative
examples for learning narrative consistency rules.

KEY DESIGN:
───────────
- Per-story isolation: Each story generates its own task
- Positive examples: Consistent states that should NOT trigger violations
- Negative examples: Inconsistent states that SHOULD trigger violations
- Context-sensitive: Uses story structure to generate relevant examples

ILASP TASK STRUCTURE:
─────────────────────
1. Mode declarations (hypothesis space)
2. Background knowledge (story facts, general rules)
3. Positive examples (consistent states → no violations)
4. Negative examples (inconsistent states → violations expected)

Author: Research Project - Narrative Evaluation
"""

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
RULES_DIR = REPO_ROOT / "rules"


@dataclass
class ILASPExample:
    """An ILASP positive or negative example."""
    inclusions: List[str] = field(default_factory=list)  # Atoms that MUST be true
    exclusions: List[str] = field(default_factory=list)  # Atoms that MUST be false
    weight: int = 1
    context: str = ""  # Additional context atoms
    
    def to_positive(self) -> str:
        """Generate positive example syntax."""
        inc = "{" + ", ".join(self.inclusions) + "}" if self.inclusions else "{}"
        exc = "{" + ", ".join(self.exclusions) + "}" if self.exclusions else "{}"
        ctx = ", {" + self.context + "}" if self.context else ""
        return f"#pos({inc}, {exc}{ctx})."
    
    def to_negative(self) -> str:
        """Generate negative example syntax (flip inclusions/exclusions logic)."""
        inc = "{" + ", ".join(self.inclusions) + "}" if self.inclusions else "{}"
        exc = "{" + ", ".join(self.exclusions) + "}" if self.exclusions else "{}"
        ctx = ", {" + self.context + "}" if self.context else ""
        return f"#neg({inc}, {exc}{ctx})."


@dataclass
class NarrativeContext:
    """Extracted context from a narrative for example generation."""
    characters: Set[str] = field(default_factory=set)
    alive_characters: Set[str] = field(default_factory=set)
    dead_characters: Set[str] = field(default_factory=set)
    locations: Set[str] = field(default_factory=set)
    objects: Set[str] = field(default_factory=set)
    character_locations: Dict[str, str] = field(default_factory=dict)
    object_owners: Dict[str, str] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Tuple[str, str, str]] = field(default_factory=list)
    traits: Dict[str, Set[str]] = field(default_factory=dict)


def sanitize(value: str) -> str:
    """Sanitize a value for ASP."""
    if not value:
        return "unknown"
    s = str(value).lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit():
        s = 'n' + s
    return s or "unknown"


class ILASPTaskGenerator:
    """
    Generates ILASP learning tasks from narrative data.
    
    This class creates comprehensive learning tasks that help ILASP
    induce rules for detecting narrative inconsistencies.
    """
    
    def __init__(
        self,
        story_name: str,
        mode_declarations_path: Optional[Path] = None,
        general_rules_path: Optional[Path] = None,
    ):
        self.story_name = story_name
        self.mode_declarations_path = mode_declarations_path or (RULES_DIR / "ilasp_mode_declarations.las")
        self.general_rules_path = general_rules_path or (RULES_DIR / "general.lp")
        
        # Track context for example generation
        self.context = NarrativeContext()
    
    def extract_context(self, structured_json: Dict[str, Any]) -> NarrativeContext:
        """Extract narrative context from structured JSON."""
        ctx = NarrativeContext()
        
        entities = structured_json.get("entities", {})
        
        # Characters
        for char in entities.get("characters", []):
            char_id = sanitize(char.get("id", char.get("name", "")))
            if char_id and char_id != "unknown":
                ctx.characters.add(char_id)
                ctx.alive_characters.add(char_id)  # Assume alive initially
        
        # Locations
        for loc in entities.get("locations", []):
            loc_id = sanitize(loc.get("id", loc.get("name", "")))
            if loc_id and loc_id != "unknown":
                ctx.locations.add(loc_id)
        
        # Objects
        for obj in entities.get("objects", []):
            obj_id = sanitize(obj.get("id", obj.get("name", "")))
            if obj_id and obj_id != "unknown":
                ctx.objects.add(obj_id)
        
        # Events
        for event in structured_json.get("events", []):
            event_type = sanitize(event.get("type", ""))
            agent = sanitize(event.get("agent", ""))
            patient = sanitize(event.get("patient", ""))
            location = sanitize(event.get("location", ""))
            
            ctx.events.append({
                "id": sanitize(event.get("id", "")),
                "type": event_type,
                "agent": agent,
                "patient": patient,
                "location": location,
            })
            
            # Update state based on events
            if event_type in ("die", "death"):
                if agent in ctx.alive_characters:
                    ctx.alive_characters.remove(agent)
                ctx.dead_characters.add(agent)
            elif event_type == "kill":
                if patient in ctx.alive_characters:
                    ctx.alive_characters.remove(patient)
                ctx.dead_characters.add(patient)
            elif event_type in ("move", "go", "travel", "enter"):
                if agent and location:
                    ctx.character_locations[agent] = location
            elif event_type in ("take", "grab", "pick_up"):
                if agent and patient:
                    ctx.object_owners[patient] = agent
        
        # Relationships
        for rel in structured_json.get("relationships", []):
            rel_type = sanitize(rel.get("type", ""))
            from_char = sanitize(rel.get("from", ""))
            to_char = sanitize(rel.get("to", ""))
            if rel_type and from_char and to_char:
                ctx.relationships.append((rel_type, from_char, to_char))
        
        # Traits
        for trait_data in structured_json.get("traits", []):
            char = sanitize(trait_data.get("character", ""))
            trait = sanitize(trait_data.get("trait", ""))
            if char and trait:
                if char not in ctx.traits:
                    ctx.traits[char] = set()
                ctx.traits[char].add(trait)
        
        self.context = ctx
        return ctx
    
    def generate_background_knowledge(self) -> str:
        """Generate background knowledge from context."""
        lines = [
            f"% Background Knowledge for: {self.story_name}",
            "",
            "% === ENTITIES ===",
        ]
        
        for char in self.context.characters:
            lines.append(f"character({char}).")
        
        for loc in self.context.locations:
            lines.append(f"location_entity({loc}).")
        
        for obj in self.context.objects:
            lines.append(f"object({obj}).")
        
        lines.append("")
        lines.append("% === STATES ===")
        
        for char in self.context.alive_characters:
            lines.append(f"alive({char}).")
        
        for char in self.context.dead_characters:
            lines.append(f"dead({char}).")
        
        for char, loc in self.context.character_locations.items():
            lines.append(f"at_location({char}, {loc}).")
        
        for obj, owner in self.context.object_owners.items():
            lines.append(f"has({owner}, {obj}).")
        
        lines.append("")
        lines.append("% === RELATIONSHIPS ===")
        
        for rel_type, from_char, to_char in self.context.relationships:
            lines.append(f"{rel_type}({from_char}, {to_char}).")
        
        lines.append("")
        lines.append("% === TRAITS ===")
        
        for char, traits in self.context.traits.items():
            for trait in traits:
                lines.append(f"trait({char}, {trait}).")
        
        lines.append("")
        lines.append("% === EVENTS ===")
        
        for event in self.context.events:
            eid = event["id"]
            if eid:
                lines.append(f"event({eid}).")
                if event["type"]:
                    lines.append(f"event_type({eid}, {event['type']}).")
                if event["agent"]:
                    lines.append(f"agent({eid}, {event['agent']}).")
                if event["patient"]:
                    lines.append(f"patient({eid}, {event['patient']}).")
                if event["location"]:
                    lines.append(f"location({eid}, {event['location']}).")
        
        return "\n".join(lines)
    
    def generate_positive_examples(self) -> List[ILASPExample]:
        """
        Generate positive examples (consistent states → no violations).
        
        Positive examples tell ILASP that certain states should NOT
        produce violations.
        """
        examples = []
        
        # Example 1: Alive character performing actions is OK
        for char in list(self.context.alive_characters)[:3]:  # Limit for efficiency
            examples.append(ILASPExample(
                inclusions=[],  # No violations expected
                exclusions=[f"violation(coherence, dead_agent, _, {char}, _)"],
                context=f"alive({char})",
            ))
        
        # Example 2: Character at single location is OK
        for char, loc in list(self.context.character_locations.items())[:3]:
            examples.append(ILASPExample(
                inclusions=[],
                exclusions=[f"violation(location, ubiquity, _, {char}, _)"],
                context=f"at_location({char}, {loc})",
            ))
        
        # Example 3: Object with single owner is OK
        for obj, owner in list(self.context.object_owners.items())[:3]:
            examples.append(ILASPExample(
                inclusions=[],
                exclusions=[f"violation(coherence, ownership, _, {obj}, _)"],
                context=f"has({owner}, {obj})",
            ))
        
        return examples
    
    def generate_negative_examples(self) -> List[ILASPExample]:
        """
        Generate negative examples (inconsistent states → violations expected).
        
        Negative examples tell ILASP that certain states SHOULD produce
        violations. These are synthetic examples of what would be wrong.
        """
        examples = []
        
        # Example 1: Dead character performing action
        for char in list(self.context.dead_characters)[:2]:
            # Create a synthetic event with dead character as agent
            examples.append(ILASPExample(
                inclusions=[f"violation(coherence, dead_agent, synthetic_event, {char}, dead_character_acting)"],
                exclusions=[],
                context=f"dead({char}), event(synthetic_event), agent(synthetic_event, {char})",
            ))
        
        # Example 2: Character in two places (ubiquity)
        chars = list(self.context.characters)[:2]
        locs = list(self.context.locations)[:2]
        if len(chars) >= 1 and len(locs) >= 2:
            char = chars[0]
            loc1, loc2 = locs[0], locs[1]
            examples.append(ILASPExample(
                inclusions=[f"violation(location, ubiquity, _, {char}, _)"],
                exclusions=[],
                context=f"character({char}), at_location({char}, {loc1}), at_location({char}, {loc2}), {loc1} != {loc2}",
            ))
        
        # Example 3: Object with two owners
        objs = list(self.context.objects)[:1]
        if len(chars) >= 2 and len(objs) >= 1:
            obj = objs[0]
            c1, c2 = chars[0], chars[1]
            examples.append(ILASPExample(
                inclusions=[f"violation(coherence, ownership, _, {obj}, _)"],
                exclusions=[],
                context=f"object({obj}), has({c1}, {obj}), has({c2}, {obj}), {c1} != {c2}",
            ))
        
        # Example 4: Trait violations
        for char, traits in list(self.context.traits.items())[:2]:
            for trait in traits:
                if trait in ("blind", "deaf", "mute", "paralyzed"):
                    conflicting_actions = {
                        "blind": ["see", "look", "read"],
                        "deaf": ["hear", "listen"],
                        "mute": ["speak", "say"],
                        "paralyzed": ["walk", "run", "move"],
                    }
                    for action in conflicting_actions.get(trait, [])[:1]:
                        examples.append(ILASPExample(
                            inclusions=[f"violation(coherence, trait_conflict, synthetic_event, {char}, _)"],
                            exclusions=[],
                            context=f"trait({char}, {trait}), event(synthetic_event), agent(synthetic_event, {char}), event_type(synthetic_event, {action})",
                        ))
        
        return examples
    
    def generate_full_task(self, structured_json: Dict[str, Any]) -> str:
        """
        Generate complete ILASP learning task.
        
        Args:
            structured_json: Structured narrative data from LLM
            
        Returns:
            Complete ILASP task as string
        """
        # Extract context
        self.extract_context(structured_json)
        
        lines = [
            "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%",
            f"%% ILASP Learning Task: {self.story_name}",
            "%% Generated automatically for narrative consistency learning",
            "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%",
            "",
        ]
        
        # Include mode declarations
        if self.mode_declarations_path.exists():
            lines.append("% === MODE DECLARATIONS ===")
            lines.append(self.mode_declarations_path.read_text())
            lines.append("")
        
        # Background knowledge
        lines.append("% === BACKGROUND KNOWLEDGE ===")
        lines.append(self.generate_background_knowledge())
        lines.append("")
        
        # Positive examples
        lines.append("% === POSITIVE EXAMPLES ===")
        lines.append("% States where NO violations should occur")
        for ex in self.generate_positive_examples():
            lines.append(ex.to_positive())
        lines.append("")
        
        # Negative examples
        lines.append("% === NEGATIVE EXAMPLES ===")
        lines.append("% States where violations SHOULD occur")
        for ex in self.generate_negative_examples():
            lines.append(ex.to_negative())
        lines.append("")
        
        # Add frame axiom templates
        lines.append("% === FRAME AXIOM LEARNING ===")
        lines.append("% Learn persistence rules")
        lines.append("")
        
        # Persistence examples
        if self.context.alive_characters:
            char = list(self.context.alive_characters)[0]
            lines.append(f"% Alive persists unless killed")
            lines.append(f"#pos({{alive({char})}}, {{}}, {{alive({char}), not dead({char})}}).")
        
        if self.context.dead_characters:
            char = list(self.context.dead_characters)[0]
            lines.append(f"% Dead persists forever")
            lines.append(f"#pos({{dead({char})}}, {{alive({char})}}, {{dead({char})}}).")
        
        return "\n".join(lines)
    
    def save_task(self, structured_json: Dict[str, Any], output_path: Path) -> str:
        """Generate and save ILASP task to file."""
        task = self.generate_full_task(structured_json)
        output_path.write_text(task)
        return str(output_path)


class PerStoryILASPLearner:
    """
    ILASP-based learner with complete per-story isolation.
    
    CRITICAL DESIGN:
    ────────────────
    Each story starts with a COMPLETELY CLEAN STATE.
    NO data sharing between:
    - Different stories
    - Original vs Modified variants
    - Different k-fold runs
    
    This ensures fair comparison and prevents data leakage.
    """
    
    def __init__(
        self,
        story_name: str,
        variant: str,
        k_fold: int,
        ilasp_binary: str = "ILASP",
        clingo_timeout: int = 60,
        verbose: bool = True,
    ):
        """
        Initialize a FRESH learner for a specific story/variant/fold.
        
        Args:
            story_name: Name of the story being processed
            variant: "original" or "modified"
            k_fold: K-fold iteration number
            ilasp_binary: Path to ILASP binary
            clingo_timeout: Timeout for Clingo in seconds
            verbose: Print progress messages
        """
        # Unique experiment ID ensures isolation
        self.experiment_id = f"{sanitize(story_name)}_{variant}_k{k_fold}"
        self.story_name = story_name
        self.variant = variant
        self.k_fold = k_fold
        self.ilasp_binary = ilasp_binary
        self.clingo_timeout = clingo_timeout
        self.verbose = verbose
        
        # FRESH task generator
        self.task_generator = ILASPTaskGenerator(self.experiment_id)
        
        # FRESH learned rules (starts empty)
        self.learned_rules: List[str] = []
        
        # Statistics
        self.ilasp_calls = 0
        self.clingo_calls = 0
        self.rules_learned = 0
        
        # Paths
        self.general_rules_path = RULES_DIR / "general.lp"
    
    def log(self, msg: str) -> None:
        """Log message if verbose."""
        if self.verbose:
            print(f"[ILASP:{self.experiment_id}] {msg}", file=__import__('sys').stderr)
    
    def learn(self, structured_json: Dict[str, Any]) -> List[str]:
        """
        Learn rules from structured narrative data.
        
        This is called ONCE per story (not per chapter) in the
        consolidated story approach.
        
        Args:
            structured_json: Structured narrative from LLM
            
        Returns:
            List of learned ASP rules
        """
        self.log(f"Learning rules for {self.story_name} ({self.variant})...")
        
        # Generate ILASP task
        task = self.task_generator.generate_full_task(structured_json)
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".las", delete=False) as f:
            f.write(task)
            task_path = f.name
        
        try:
            import subprocess
            
            result = subprocess.run(
                [self.ilasp_binary, task_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            self.ilasp_calls += 1
            
            if result.returncode == 0 and result.stdout.strip():
                # Parse learned rules
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("%"):
                        self.learned_rules.append(line)
                        self.rules_learned += 1
                
                self.log(f"Learned {self.rules_learned} rules")
            else:
                self.log(f"ILASP returned no rules (exit code: {result.returncode})")
                if result.stderr:
                    self.log(f"ILASP stderr: {result.stderr[:500]}")
                    
        except subprocess.TimeoutExpired:
            self.log("ILASP timeout")
        except FileNotFoundError:
            self.log(f"ILASP binary not found: {self.ilasp_binary}")
        except Exception as e:
            self.log(f"ILASP error: {e}")
        finally:
            os.unlink(task_path)
        
        return self.learned_rules
    
    def check(self, structured_json: Dict[str, Any], asp_facts: str) -> List[Dict]:
        """
        Check for violations using Clingo with learned rules.
        
        Args:
            structured_json: Structured narrative
            asp_facts: ASP facts for the story
            
        Returns:
            List of violation dictionaries
        """
        self.log("Checking with Clingo...")
        
        violations = []
        
        try:
            import clingo
        except ImportError:
            self.log("Clingo not available")
            return []
        
        # Combine program
        program_parts = [asp_facts]
        
        if self.learned_rules:
            program_parts.append("\n% Learned rules:")
            program_parts.extend(self.learned_rules)
        
        combined = "\n".join(program_parts)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(combined)
            facts_path = f.name
        
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load general rules
            if self.general_rules_path.exists():
                ctl.load(str(self.general_rules_path))
            
            # Load facts and learned rules
            ctl.load(facts_path)
            
            # Ground and solve
            ctl.ground([("base", [])])
            
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "violation":
                            parts = [str(arg) for arg in atom.arguments]
                            violations.append({
                                "category": parts[0] if len(parts) > 0 else "unknown",
                                "type": parts[1] if len(parts) > 1 else "unknown",
                                "event": parts[2] if len(parts) > 2 else "",
                                "detail": parts[3] if len(parts) > 3 else "",
                            })
            
            self.clingo_calls += 1
            self.log(f"Found {len(violations)} violations")
            
        except Exception as e:
            self.log(f"Clingo error: {e}")
        finally:
            os.unlink(facts_path)
        
        return violations
    
    def get_statistics(self) -> Dict:
        """Get learning/checking statistics."""
        return {
            "experiment_id": self.experiment_id,
            "story_name": self.story_name,
            "variant": self.variant,
            "k_fold": self.k_fold,
            "ilasp_calls": self.ilasp_calls,
            "clingo_calls": self.clingo_calls,
            "rules_learned": self.rules_learned,
            "learned_rules": self.learned_rules,
        }


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Test with sample data
    sample_json = {
        "entities": {
            "characters": [
                {"id": "harry", "name": "Harry Potter"},
                {"id": "hermione", "name": "Hermione Granger"},
                {"id": "voldemort", "name": "Lord Voldemort"},
            ],
            "locations": [
                {"id": "hogwarts", "name": "Hogwarts"},
                {"id": "diagon_alley", "name": "Diagon Alley"},
            ],
            "objects": [
                {"id": "wand", "name": "Harry's Wand"},
            ],
        },
        "events": [
            {"id": "e1", "type": "travel", "agent": "harry", "location": "hogwarts"},
            {"id": "e2", "type": "kill", "agent": "harry", "patient": "voldemort"},
        ],
        "relationships": [
            {"type": "enemy", "from": "harry", "to": "voldemort"},
        ],
        "traits": [
            {"character": "harry", "trait": "magical"},
        ],
    }
    
    # Generate task
    generator = ILASPTaskGenerator("harry_potter_test")
    task = generator.generate_full_task(sample_json)
    
    print("Generated ILASP Task:")
    print("=" * 70)
    print(task)
