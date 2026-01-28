#!/usr/bin/env python3
"""
ilasp_learner.py - Incremental Learning Module for Narrative Consistency
=========================================================================

This module implements incremental learning for narrative consistency checking.
It processes stories chapter by chapter, learning facts and rules as it goes,
then checking subsequent chapters against accumulated knowledge.

KEY DESIGN: COMPLETE ISOLATION
──────────────────────────────

Each experiment (story run) starts with a COMPLETELY CLEAN STATE.
There is NO data sharing between experiments:

    Experiment 1: original_books/Harry Potter/ → Clean start → Learn → 0 errors
    Experiment 2: modified_books/Harry Potter/ → Clean start → Learn → Detect errors

The modified story experiment knows NOTHING from the original story.
It detects errors based on INTERNAL inconsistencies within itself.

WORKFLOW:
─────────

    Chapter 1 (001.txt):
        → LLM structures the text
        → Extract entities, events, relationships, states
        → Store in knowledge base
        → Learn frame axioms (what persists)
        → No checking yet (nothing to check against)
    
    Chapter 2 (002.txt):
        → LLM structures the text
        → CHECK new facts against Chapter 1 knowledge
        → If violation found → Report error
        → If consistent → Update knowledge base, learn new rules
    
    Chapter N:
        → CHECK against all previous chapters
        → Update or report violations

Author: Research Project - Narrative Evaluation
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Script and repo paths
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent


@dataclass
class LearnedRule:
    """Represents a rule learned by ILASP or heuristics."""
    head: str
    body: List[str]
    confidence: float
    chapter_learned: int
    rule_type: str  # 'frame', 'causal', 'constraint'
    
    def to_asp(self) -> str:
        """Convert to ASP rule string."""
        if self.body:
            body_str = ", ".join(self.body)
            return f"{self.head} :- {body_str}."
        return f"{self.head}."


class StoryKnowledge:
    """
    Accumulated knowledge about a story across chapters.
    
    This is the STATE that grows as chapters are processed within ONE experiment.
    Each new experiment creates a FRESH instance of this class.
    """
    
    def __init__(self, experiment_id: str):
        self.experiment_id = experiment_id
        
        # Entities
        self.characters: Dict[str, Dict[str, Any]] = {}
        self.objects: Dict[str, Dict[str, Any]] = {}
        self.locations: Dict[str, Dict[str, Any]] = {}
        
        # States (current)
        self.alive_characters: Set[str] = set()
        self.dead_characters: Set[str] = set()
        self.character_locations: Dict[str, str] = {}  # char -> current location
        self.object_ownership: Dict[str, str] = {}     # object -> current owner
        
        # Relationships (persistent)
        self.relationships: List[Tuple[str, str, str]] = []  # (type, from, to)
        
        # Traits (persistent)
        self.character_traits: Dict[str, Set[str]] = {}
        
        # Event history for checking
        self.events: List[Dict[str, Any]] = []
        self.death_events: Dict[str, int] = {}  # character -> chapter they died
        
        # Timeline tracking
        self.current_chapter: int = 0
        self.chapters_processed: List[int] = []
        
        # Learned rules
        self.learned_rules: List[LearnedRule] = []
        
        # All raw facts (for ASP)
        self.all_facts: List[str] = []
    
    def to_asp(self) -> str:
        """Generate ASP representation of accumulated knowledge."""
        lines = [
            f"% Experiment Knowledge Base: {self.experiment_id}",
            f"% Chapters processed: {self.chapters_processed}",
            "",
            "% === ENTITIES ===",
        ]
        
        # Characters
        for char_id in self.characters:
            lines.append(f"character({char_id}).")
        
        # Objects
        for obj_id, obj_data in self.objects.items():
            lines.append(f"object({obj_id}).")
            if 'type' in obj_data:
                obj_type = self._sanitize(obj_data['type'])
                lines.append(f"object_type({obj_id}, {obj_type}).")
        
        # Locations
        for loc_id in self.locations:
            lines.append(f"location_entity({loc_id}).")
        
        lines.append("")
        lines.append("% === CHARACTER STATES ===")
        
        # Alive/Dead with chapter info
        for char in self.alive_characters:
            lines.append(f"alive({char}).")
        for char, death_chapter in self.death_events.items():
            lines.append(f"dead({char}).")
            lines.append(f"died_in_chapter({char}, {death_chapter}).")
        
        # Current locations
        for char, loc in self.character_locations.items():
            lines.append(f"current_location({char}, {loc}).")
        
        lines.append("")
        lines.append("% === RELATIONSHIPS ===")
        
        for rel_type, from_char, to_char in self.relationships:
            lines.append(f"{rel_type}({from_char}, {to_char}).")
        
        lines.append("")
        lines.append("% === TRAITS ===")
        
        for char, traits in self.character_traits.items():
            for trait in traits:
                lines.append(f"trait({char}, {trait}).")
        
        lines.append("")
        lines.append("% === OBJECT OWNERSHIP ===")
        
        for obj, owner in self.object_ownership.items():
            lines.append(f"has({owner}, {obj}).")
        
        lines.append("")
        lines.append("% === ACCUMULATED FACTS ===")
        
        for fact in self.all_facts:
            lines.append(fact)
        
        lines.append("")
        lines.append("% === LEARNED RULES ===")
        
        for rule in self.learned_rules:
            lines.append(f"% Type: {rule.rule_type}, Chapter: {rule.chapter_learned}")
            lines.append(rule.to_asp())
        
        return "\n".join(lines)
    
    def _sanitize(self, value: str) -> str:
        """Sanitize a value for ASP."""
        if not value:
            return "unknown"
        s = str(value).lower()
        s = re.sub(r'[^a-z0-9_]', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        if s and s[0].isdigit():
            s = 'n' + s
        return s or "unknown"


class ILASPLearner:
    """
    Incremental learner for narrative consistency checking.
    
    IMPORTANT: Each instance represents ONE ISOLATED EXPERIMENT.
    Create a new instance for each experiment to ensure clean state.
    """
    
    def __init__(
        self,
        experiment_id: str,
        ilasp_binary: str = "ILASP",
        clingo_timeout: int = 60,
        verbose: bool = True,
    ):
        """
        Initialize a FRESH learner for an experiment.
        
        Args:
            experiment_id: Unique identifier for this experiment run
            ilasp_binary: Path to ILASP binary
            clingo_timeout: Timeout for Clingo in seconds
            verbose: Print progress messages
        """
        self.experiment_id = experiment_id
        self.ilasp_binary = ilasp_binary
        self.clingo_timeout = clingo_timeout
        self.verbose = verbose
        
        # FRESH knowledge base - completely clean state
        self.knowledge = StoryKnowledge(experiment_id)
        
        # Find general rules file
        self.general_rules_path = self._find_general_rules()
        
        # Load mode declarations
        self.mode_declarations_path = REPO_ROOT / "rules" / "ilasp_mode_declarations.las"
    
    def log(self, msg: str) -> None:
        """Log message if verbose."""
        if self.verbose:
            print(f"[ILASP:{self.experiment_id}] {msg}", file=sys.stderr)
    
    def _find_general_rules(self) -> Path:
        """Find the general rules file."""
        candidates = [
            REPO_ROOT / "rules" / "general_narrative.lp",
            REPO_ROOT / "rules" / "general.lp",
            REPO_ROOT / "rules" / "base.lp",
        ]
        for path in candidates:
            if path.exists():
                return path
        raise FileNotFoundError("No general rules file found in rules/")
    
    def process_chapter(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
        chapter_text: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Process a chapter: check for violations, then learn.
        
        For the FIRST chapter: Only learn (nothing to check against)
        For subsequent chapters: Check first, then learn if consistent
        
        Args:
            structured_json: Structured story data from LLM
            chapter_num: Chapter number (for ordering)
            chapter_text: Original chapter text (for error context)
            
        Returns:
            List of violations found (empty if consistent)
        """
        self.log(f"Processing chapter {chapter_num}...")
        
        violations = []
        
        # For first chapter, just learn
        if not self.knowledge.chapters_processed:
            self.log(f"  First chapter - learning initial knowledge")
            self._learn_from_chapter(structured_json, chapter_num)
            self.knowledge.chapters_processed.append(chapter_num)
            return []
        
        # For subsequent chapters, check then learn
        self.log(f"  Checking against {len(self.knowledge.chapters_processed)} previous chapters")
        
        # Step 1: Check for violations
        violations = self._check_chapter(structured_json, chapter_num, chapter_text)
        
        if violations:
            self.log(f"  Found {len(violations)} violations")
            # Still learn from the chapter (errors are flagged but story continues)
        else:
            self.log(f"  No violations found")
        
        # Step 2: Learn from this chapter
        self._learn_from_chapter(structured_json, chapter_num)
        self.knowledge.chapters_processed.append(chapter_num)
        
        return violations
    
    def _check_chapter(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
        chapter_text: str = "",
    ) -> List[Dict[str, Any]]:
        """Check chapter for violations against accumulated knowledge."""
        violations = []
        
        # Check 1: Dead agent violations
        dead_violations = self._check_dead_agents(structured_json, chapter_num)
        violations.extend(dead_violations)
        
        # Check 2: Ubiquity violations (same character in two places)
        ubiquity_violations = self._check_ubiquity(structured_json, chapter_num)
        violations.extend(ubiquity_violations)
        
        # Check 3: Object ownership conflicts
        ownership_violations = self._check_ownership(structured_json, chapter_num)
        violations.extend(ownership_violations)
        
        # Check 4: Trait violations (blind character seeing, etc.)
        trait_violations = self._check_trait_violations(structured_json, chapter_num)
        violations.extend(trait_violations)
        
        # Check 5: Use Clingo for more complex violations
        clingo_violations = self._check_with_clingo(structured_json, chapter_num)
        violations.extend(clingo_violations)
        
        return violations
    
    def _check_dead_agents(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """Check if dead characters are performing actions."""
        violations = []
        
        events = structured_json.get("events", [])
        
        for event in events:
            agent = self._sanitize(event.get("agent", ""))
            
            if not agent or agent == "unknown":
                continue
            
            # Check if agent is dead
            if agent in self.knowledge.dead_characters:
                death_chapter = self.knowledge.death_events.get(agent, "earlier")
                violations.append({
                    "category": "coherence",
                    "type": "dead_agent",
                    "event": event.get("id", "unknown"),
                    "detail": f"Character '{agent}' died in chapter {death_chapter}",
                    "description": f"Character '{agent}' performs action '{event.get('type', 'unknown')}' but died in chapter {death_chapter}",
                    "chapter": chapter_num,
                    "severity": "high",
                })
        
        return violations
    
    def _check_ubiquity(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """Check for characters being in two places at once."""
        violations = []
        
        events = structured_json.get("events", [])
        
        # Track locations within this chapter
        chapter_locations: Dict[str, List[Tuple[str, str]]] = {}  # char -> [(location, event_id)]
        
        for event in events:
            agent = self._sanitize(event.get("agent", ""))
            location = self._sanitize(event.get("location", ""))
            event_id = event.get("id", "unknown")
            
            if not agent or not location or agent == "unknown":
                continue
            
            if agent not in chapter_locations:
                chapter_locations[agent] = []
            
            chapter_locations[agent].append((location, event_id))
        
        # Check for simultaneous different locations
        for char, loc_events in chapter_locations.items():
            locations = set(loc for loc, _ in loc_events)
            if len(locations) > 1:
                # Multiple locations - check if it's travel or a violation
                # For now, flag as potential issue (travel should update location)
                pass  # This needs time-based analysis, handled by Clingo
        
        return violations
    
    def _check_ownership(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """Check for object ownership conflicts."""
        violations = []
        
        events = structured_json.get("events", [])
        
        for event in events:
            event_type = self._sanitize(event.get("type", ""))
            agent = self._sanitize(event.get("agent", ""))
            patient = self._sanitize(event.get("patient", ""))
            
            # Check if someone uses an object they don't have
            if event_type in ("give", "use", "throw", "drop"):
                if patient in self.knowledge.object_ownership:
                    current_owner = self.knowledge.object_ownership[patient]
                    if current_owner != agent and current_owner != "unknown":
                        violations.append({
                            "category": "coherence",
                            "type": "ownership_violation",
                            "event": event.get("id", "unknown"),
                            "detail": f"Object '{patient}' owned by '{current_owner}'",
                            "description": f"Character '{agent}' uses object '{patient}' but it belongs to '{current_owner}'",
                            "chapter": chapter_num,
                            "severity": "medium",
                        })
        
        return violations
    
    def _check_trait_violations(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """Check for trait-based violations (blind seeing, deaf hearing, etc.)."""
        violations = []
        
        events = structured_json.get("events", [])
        
        # Trait -> incompatible actions
        trait_conflicts = {
            "blind": ["see", "look", "observe", "read", "watch"],
            "deaf": ["hear", "listen"],
            "mute": ["speak", "say", "tell", "shout", "sing"],
            "paralyzed": ["walk", "run", "move", "fight", "attack"],
        }
        
        for event in events:
            agent = self._sanitize(event.get("agent", ""))
            event_type = self._sanitize(event.get("type", ""))
            
            if agent not in self.knowledge.character_traits:
                continue
            
            char_traits = self.knowledge.character_traits[agent]
            
            for trait, forbidden_actions in trait_conflicts.items():
                if trait in char_traits and event_type in forbidden_actions:
                    violations.append({
                        "category": "coherence",
                        "type": "trait_violation",
                        "event": event.get("id", "unknown"),
                        "detail": f"Character has trait '{trait}'",
                        "description": f"Character '{agent}' (who is {trait}) performs incompatible action '{event_type}'",
                        "chapter": chapter_num,
                        "severity": "high",
                    })
        
        return violations
    
    def _check_with_clingo(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """Use Clingo for complex violation checking."""
        violations = []
        
        try:
            import clingo
        except ImportError:
            self.log("  Clingo not available, skipping complex checks")
            return []
        
        # Generate ASP facts for this chapter
        chapter_facts = self._structured_to_asp(structured_json, chapter_num)
        
        # Combine with accumulated knowledge
        combined_program = self.knowledge.to_asp() + "\n\n% === CURRENT CHAPTER ===\n" + chapter_facts
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(combined_program)
            facts_path = f.name
        
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load general rules
            if self.general_rules_path.exists():
                ctl.load(str(self.general_rules_path))
            
            # Load facts
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
                                "description": parts[4] if len(parts) > 4 else f"Violation: {parts[1] if len(parts) > 1 else 'unknown'}",
                                "chapter": chapter_num,
                                "severity": "medium",
                            })
        except Exception as e:
            self.log(f"  Clingo error: {e}")
        finally:
            os.unlink(facts_path)
        
        return violations
    
    def _learn_from_chapter(
        self,
        structured_json: Dict[str, Any],
        chapter_num: int,
    ) -> None:
        """Extract and store knowledge from a chapter."""
        self.knowledge.current_chapter = chapter_num
        
        # Extract entities
        self._extract_entities(structured_json, chapter_num)
        
        # Extract and apply events (updates state)
        self._extract_events(structured_json, chapter_num)
        
        # Extract relationships
        self._extract_relationships(structured_json, chapter_num)
        
        # Extract traits
        self._extract_traits(structured_json, chapter_num)
        
        # Extract fluents
        self._extract_fluents(structured_json, chapter_num)
        
        # Learn rules (with ILASP or heuristics)
        self._learn_rules(chapter_num)
        
        self.log(f"  Knowledge updated: {len(self.knowledge.characters)} chars, "
                 f"{len(self.knowledge.dead_characters)} dead, "
                 f"{len(self.knowledge.learned_rules)} rules")
    
    def _extract_entities(self, data: Dict, chapter_num: int) -> None:
        """Extract entities from structured JSON."""
        entities = data.get("entities", {})
        
        # Characters
        for char in entities.get("characters", []):
            char_id = self._sanitize(char.get("id", ""))
            if char_id and char_id not in self.knowledge.characters:
                self.knowledge.characters[char_id] = {
                    "name": char.get("name", char_id),
                    "description": char.get("description", ""),
                    "introduced_chapter": chapter_num,
                }
                # New characters start alive
                self.knowledge.alive_characters.add(char_id)
        
        # Objects
        for obj in entities.get("objects", []):
            obj_id = self._sanitize(obj.get("id", ""))
            if obj_id and obj_id not in self.knowledge.objects:
                self.knowledge.objects[obj_id] = {
                    "type": self._sanitize(obj.get("type", "object")),
                    "description": obj.get("description", ""),
                    "introduced_chapter": chapter_num,
                }
        
        # Locations
        for loc in entities.get("locations", []):
            loc_id = self._sanitize(loc.get("id", ""))
            if loc_id and loc_id not in self.knowledge.locations:
                self.knowledge.locations[loc_id] = {
                    "description": loc.get("description", ""),
                    "introduced_chapter": chapter_num,
                }
    
    def _extract_events(self, data: Dict, chapter_num: int) -> None:
        """Extract events and update state accordingly."""
        events = data.get("events", [])
        
        for event in events:
            event_type = self._sanitize(event.get("type", ""))
            agent = self._sanitize(event.get("agent", ""))
            patient = self._sanitize(event.get("patient", ""))
            location = self._sanitize(event.get("location", ""))
            
            # Store event in history
            self.knowledge.events.append({
                "type": event_type,
                "agent": agent,
                "patient": patient,
                "location": location,
                "chapter": chapter_num,
            })
            
            # Update state based on event type
            if event_type == "die":
                if agent in self.knowledge.alive_characters:
                    self.knowledge.alive_characters.remove(agent)
                self.knowledge.dead_characters.add(agent)
                self.knowledge.death_events[agent] = chapter_num
            
            elif event_type == "kill":
                if patient in self.knowledge.alive_characters:
                    self.knowledge.alive_characters.remove(patient)
                self.knowledge.dead_characters.add(patient)
                self.knowledge.death_events[patient] = chapter_num
            
            elif event_type in ("take", "grab", "pick_up", "acquire"):
                if patient:
                    self.knowledge.object_ownership[patient] = agent
            
            elif event_type in ("drop", "put", "place", "release"):
                if patient and patient in self.knowledge.object_ownership:
                    del self.knowledge.object_ownership[patient]
            
            elif event_type == "give":
                recipient = self._sanitize(event.get("recipient", ""))
                if patient and recipient:
                    self.knowledge.object_ownership[patient] = recipient
            
            elif event_type in ("move", "go", "travel", "walk", "run", "enter"):
                destination = self._sanitize(event.get("destination", location))
                if agent and destination:
                    self.knowledge.character_locations[agent] = destination
            
            # Store as ASP fact
            fact = f"event_occurred({event_type}, {agent}, {patient}, {location}, ch{chapter_num})."
            self.knowledge.all_facts.append(fact)
    
    def _extract_relationships(self, data: Dict, chapter_num: int) -> None:
        """Extract relationships from structured JSON."""
        relationships = data.get("relationships", [])
        
        for rel in relationships:
            rel_type = self._sanitize(rel.get("type", ""))
            from_char = self._sanitize(rel.get("from", ""))
            to_char = self._sanitize(rel.get("to", ""))
            
            if rel_type and from_char and to_char:
                rel_tuple = (rel_type, from_char, to_char)
                if rel_tuple not in self.knowledge.relationships:
                    self.knowledge.relationships.append(rel_tuple)
    
    def _extract_traits(self, data: Dict, chapter_num: int) -> None:
        """Extract character traits from structured JSON."""
        traits = data.get("traits", [])
        
        for trait_data in traits:
            char = self._sanitize(trait_data.get("character", ""))
            trait = self._sanitize(trait_data.get("trait", ""))
            
            if char and trait:
                if char not in self.knowledge.character_traits:
                    self.knowledge.character_traits[char] = set()
                self.knowledge.character_traits[char].add(trait)
    
    def _extract_fluents(self, data: Dict, chapter_num: int) -> None:
        """Extract fluent states from structured JSON."""
        fluents = data.get("fluents", [])
        
        for fluent in fluents:
            fluent_id = fluent.get("id", "")
            
            # Parse fluent like "alive(alice)" or "has(bob, sword)"
            match = re.match(r"(\w+)\(([^)]+)\)", fluent_id)
            if match:
                pred = match.group(1)
                args = ",".join(self._sanitize(a.strip()) for a in match.group(2).split(","))
                fact = f"{pred}({args})."
                if fact not in self.knowledge.all_facts:
                    self.knowledge.all_facts.append(fact)
    
    def _learn_rules(self, chapter_num: int) -> None:
        """Learn rules from observed patterns."""
        # Check if ILASP is available
        if self._ilasp_available():
            self._learn_with_ilasp(chapter_num)
        else:
            self._learn_heuristic_rules(chapter_num)
    
    def _ilasp_available(self) -> bool:
        """Check if ILASP binary is available."""
        try:
            result = subprocess.run(
                [self.ilasp_binary, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _learn_with_ilasp(self, chapter_num: int) -> None:
        """Use ILASP to learn rules from observations."""
        self.log(f"  Learning with ILASP...")
        
        # Generate ILASP task
        task = self._generate_ilasp_task(chapter_num)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".las", delete=False) as f:
            f.write(task)
            task_path = f.name
        
        try:
            result = subprocess.run(
                [self.ilasp_binary, str(task_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                learned = self._parse_ilasp_output(result.stdout)
                for rule in learned:
                    rule.chapter_learned = chapter_num
                    self.knowledge.learned_rules.append(rule)
                self.log(f"  Learned {len(learned)} rules via ILASP")
            
        except subprocess.TimeoutExpired:
            self.log(f"  ILASP timeout, using heuristics")
            self._learn_heuristic_rules(chapter_num)
        except Exception as e:
            self.log(f"  ILASP error: {e}, using heuristics")
            self._learn_heuristic_rules(chapter_num)
        finally:
            os.unlink(task_path)
    
    def _generate_ilasp_task(self, chapter_num: int) -> str:
        """Generate ILASP learning task."""
        lines = [
            "% ILASP Learning Task",
            f"% Experiment: {self.experiment_id}, Chapter: {chapter_num}",
            "",
        ]
        
        # Include mode declarations if available
        if self.mode_declarations_path.exists():
            lines.append(self.mode_declarations_path.read_text())
        
        lines.append("")
        lines.append("% === BACKGROUND KNOWLEDGE ===")
        lines.append(self.knowledge.to_asp())
        
        return "\n".join(lines)
    
    def _parse_ilasp_output(self, output: str) -> List[LearnedRule]:
        """Parse ILASP output to extract learned rules."""
        rules = []
        
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            
            if ":-" in line:
                parts = line.rstrip(".").split(":-")
                head = parts[0].strip()
                body = [b.strip() for b in parts[1].split(",")]
            else:
                head = line.rstrip(".")
                body = []
            
            if head:
                rules.append(LearnedRule(
                    head=head,
                    body=body,
                    confidence=1.0,
                    chapter_learned=0,
                    rule_type=self._classify_rule(head),
                ))
        
        return rules
    
    def _classify_rule(self, head: str) -> str:
        """Classify rule by type."""
        if "holds" in head or "has(" in head or "at_location" in head:
            return "frame"
        if "causes" in head or "terminates" in head:
            return "causal"
        return "constraint"
    
    def _learn_heuristic_rules(self, chapter_num: int) -> None:
        """Learn basic rules using heuristics when ILASP is not available."""
        existing_heads = {r.head for r in self.knowledge.learned_rules}
        
        # Only add each rule type once
        basic_rules = [
            LearnedRule(
                head="stays_dead(C)",
                body=["dead(C)"],
                confidence=1.0,
                chapter_learned=chapter_num,
                rule_type="frame",
            ),
            LearnedRule(
                head="cannot_act(C)",
                body=["dead(C)"],
                confidence=1.0,
                chapter_learned=chapter_num,
                rule_type="constraint",
            ),
        ]
        
        for rule in basic_rules:
            if rule.head not in existing_heads:
                self.knowledge.learned_rules.append(rule)
    
    def _structured_to_asp(self, data: Dict, chapter_num: int) -> str:
        """Convert structured JSON to ASP facts."""
        try:
            from json_to_asp import json_to_asp
            return json_to_asp(data)
        except ImportError:
            return self._basic_json_to_asp(data, chapter_num)
    
    def _basic_json_to_asp(self, data: Dict, chapter_num: int) -> str:
        """Basic JSON to ASP conversion."""
        lines = [f"% Chapter {chapter_num} facts"]
        
        entities = data.get("entities", {})
        for char in entities.get("characters", []):
            lines.append(f"character({self._sanitize(char.get('id', ''))}).")
        for obj in entities.get("objects", []):
            lines.append(f"object({self._sanitize(obj.get('id', ''))}).")
        for loc in entities.get("locations", []):
            lines.append(f"location_entity({self._sanitize(loc.get('id', ''))}).")
        
        for i, event in enumerate(data.get("events", [])):
            eid = event.get("id", f"e{i+1}")
            lines.append(f"event({eid}).")
            if event.get("type"):
                lines.append(f"event_type({eid}, {self._sanitize(event['type'])}).")
            if event.get("agent"):
                lines.append(f"agent({eid}, {self._sanitize(event['agent'])}).")
            if event.get("patient"):
                lines.append(f"patient({eid}, {self._sanitize(event['patient'])}).")
            if event.get("location"):
                lines.append(f"location({eid}, {self._sanitize(event['location'])}).")
        
        return "\n".join(lines)
    
    def _sanitize(self, value: str) -> str:
        """Sanitize a value for ASP."""
        if not value:
            return "unknown"
        s = str(value).lower()
        s = re.sub(r'[^a-z0-9_]', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        if s and s[0].isdigit():
            s = 'n' + s
        return s or "unknown"
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of current knowledge state."""
        return {
            "experiment_id": self.experiment_id,
            "chapters_processed": len(self.knowledge.chapters_processed),
            "characters": len(self.knowledge.characters),
            "alive_characters": len(self.knowledge.alive_characters),
            "dead_characters": len(self.knowledge.dead_characters),
            "objects": len(self.knowledge.objects),
            "locations": len(self.knowledge.locations),
            "relationships": len(self.knowledge.relationships),
            "learned_rules": len(self.knowledge.learned_rules),
            "total_events": len(self.knowledge.events),
        }
