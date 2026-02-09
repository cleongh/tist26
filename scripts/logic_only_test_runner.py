#!/usr/bin/env python3
"""
Logic-Only Test Runner

Runs the ASP/Clingo logic engine on pre-extracted chapter data without invoking LLMs.
Useful for testing rule changes or validating logic on existing extractions.

Usage:
    python scripts/logic_only_test_runner.py --experiment_dir experiments/08_openai_one_book --output_log logic_test.txt

Required inputs:
    - step2_extractions.jsonl in experiment_dir (per-chapter extraction data)

Outputs:
    - Text log file with violations per chapter
    - Aggregated violation counts
    - Per-statement evaluation traces (with --trace flag)

Does NOT import:
    - LLM clients
    - Extraction prompts
    - Any inference/generation code
"""

import argparse
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Set

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import logic modules only
from scripts.logic.asp_converter import to_asp
from engine.rule_registry import RuleRegistry, RuleLayer


# =============================================================================
# Statement Representation for Tracing
# =============================================================================

@dataclass
class Statement:
    """Represents a logical statement extracted from ASP facts."""
    statement_type: str  # event, relationship, presence, learned, character, location, item
    identifier: str      # Primary ID (event ID, character pair, etc.)
    asp_fact: str        # Original ASP fact line
    human_readable: str  # Human-readable representation (legacy, single-line)
    related_ids: Set[str] = field(default_factory=set)  # All IDs this statement references
    # Structured data for rich formatting
    data: Dict[str, Any] = field(default_factory=dict)
    chapter: Optional[int] = None
    
    def format_human_readable(self) -> str:
        """
        Format this statement as a clear, multi-line human-readable string.
        
        Returns structured output like:
            REPORT event:
              agent: neville_longbottom
              patient: harry_potter
              recipient: professor_mcgonagall
              chapter: 14
        """
        lines = []
        
        if self.statement_type == "event":
            event_type = self.data.get("type", "action").upper()
            lines.append(f"{event_type} event:")
            lines.append(f"    id: {self.identifier}")
            
            # Core roles
            if self.data.get("agent"):
                lines.append(f"    agent: {self.data['agent']}")
            if self.data.get("patient"):
                lines.append(f"    patient: {self.data['patient']}")
            if self.data.get("recipient"):
                lines.append(f"    recipient: {self.data['recipient']}")
            
            # Location and context
            if self.data.get("location"):
                lines.append(f"    location: {self.data['location']}")
            if self.data.get("social_action"):
                lines.append(f"    social_action: {self.data['social_action']}")
            
            # For learn events
            if self.data.get("fact"):
                lines.append(f"    fact: {self.data['fact']}")
            if self.data.get("source"):
                lines.append(f"    source: {self.data['source']}")
            
            # Time reference
            if self.data.get("time") is not None:
                lines.append(f"    time: {self.data['time']}")
            if self.chapter is not None:
                lines.append(f"    chapter: {self.chapter}")
        
        elif self.statement_type == "relationship":
            rel_type = self.data.get("type", "related").upper()
            lines.append(f"{rel_type} relationship:")
            if self.data.get("from"):
                lines.append(f"    from: {self.data['from']}")
            if self.data.get("to"):
                lines.append(f"    to: {self.data['to']}")
            if self.chapter is not None:
                lines.append(f"    chapter: {self.chapter}")
        
        elif self.statement_type == "presence":
            lines.append("PRESENCE fact:")
            if self.data.get("entity"):
                lines.append(f"    entity: {self.data['entity']}")
            if self.data.get("location"):
                lines.append(f"    location: {self.data['location']}")
            if self.data.get("time") is not None:
                lines.append(f"    time: {self.data['time']}")
            if self.chapter is not None:
                lines.append(f"    chapter: {self.chapter}")
        
        elif self.statement_type == "learned":
            lines.append("LEARNED / KNOWS fact:")
            if self.data.get("agent"):
                lines.append(f"    agent: {self.data['agent']}")
            if self.data.get("fact"):
                lines.append(f"    fact: {self.data['fact']}")
            if self.data.get("source"):
                lines.append(f"    source: {self.data['source']}")
            if self.data.get("time") is not None:
                lines.append(f"    time: {self.data['time']}")
            if self.chapter is not None:
                lines.append(f"    chapter: {self.chapter}")
        
        elif self.statement_type == "character":
            lines.append("CHARACTER entity:")
            lines.append(f"    id: {self.identifier}")
            if self.data.get("name"):
                lines.append(f"    name: {self.data['name']}")
            if self.data.get("emotion") and self.data["emotion"] != "neutral":
                lines.append(f"    emotion: {self.data['emotion']}")
            if self.data.get("state") and self.data["state"] != "normal":
                lines.append(f"    state: {self.data['state']}")
            if self.chapter is not None:
                lines.append(f"    chapter: {self.chapter}")
        
        elif self.statement_type == "location":
            lines.append("LOCATION entity:")
            lines.append(f"    id: {self.identifier}")
            if self.data.get("name"):
                lines.append(f"    name: {self.data['name']}")
            if self.data.get("connections"):
                lines.append(f"    connections: {', '.join(self.data['connections'])}")
            if self.chapter is not None:
                lines.append(f"    chapter: {self.chapter}")
        
        else:
            # Fallback for unknown types
            lines.append(f"{self.statement_type.upper()}:")
            lines.append(f"    id: {self.identifier}")
            for key, value in self.data.items():
                if value:
                    lines.append(f"    {key}: {value}")
            if self.chapter is not None:
                lines.append(f"    chapter: {self.chapter}")
        
        return "\n".join(lines)
    
    def matches_violation(self, violation: Dict[str, Any]) -> bool:
        """
        Check if this statement is directly involved in a violation.
        
        Matching rules:
        - For events: the violation's event field must match this statement's identifier
        - For characters: the violation's detail must match this character's ID
        - For relationships: either endpoint must appear in violation
        - For locations: the location must appear in violation detail
        """
        event_id = violation.get("event", "").lower()
        detail = violation.get("detail", "").lower()
        vtype = violation.get("type", "").lower()
        
        stmt_id = self.identifier.lower()
        
        # Event statements: match on event ID
        if self.statement_type == "event":
            return event_id == stmt_id
        
        # Character statements: match if character appears in detail
        if self.statement_type == "character":
            return stmt_id == detail or stmt_id == event_id
        
        # Relationship statements: match if either endpoint appears
        if self.statement_type == "relationship":
            # identifier is "from->to"
            parts = stmt_id.split("->")
            if len(parts) == 2:
                from_char, to_char = parts[0].strip(), parts[1].strip()
                return from_char == detail or to_char == detail
            return False
        
        # Location statements: match if location appears in detail
        if self.statement_type == "location":
            return stmt_id == detail or stmt_id in detail
        
        # Presence statements: match if entity or location appears
        if self.statement_type == "presence":
            # identifier is "entity@location"
            parts = stmt_id.split("@")
            if len(parts) == 2:
                entity, location = parts[0].strip(), parts[1].strip()
                return entity == detail or location == detail
            return False
        
        # Learned statements: match if agent or fact appears
        if self.statement_type == "learned":
            # identifier is "agent:fact"
            parts = stmt_id.split(":")
            if len(parts) == 2:
                agent, fact = parts[0].strip(), parts[1].strip()
                return agent == detail or fact in detail
            return False
            
        return False


def parse_asp_facts_to_statements(asp_facts: str, chapter_data: Dict) -> List[Statement]:
    """
    Parse ASP facts string into structured Statement objects.
    
    Args:
        asp_facts: The ASP program string
        chapter_data: Original chapter data for context
        
    Returns:
        List of Statement objects for tracing
    """
    statements = []
    
    # Extract chapter index from asp_facts if available
    chapter_idx: Optional[int] = None
    chapter_match = re.search(r'chapter\((\d+)\)', asp_facts)
    if chapter_match:
        chapter_idx = int(chapter_match.group(1))
    
    # Parse events from chapter data (more structured than ASP text)
    for event in chapter_data.get("events", []):
        eid = event.get("id", event.get("global_id", ""))
        etype = event.get("type", "action")
        agent = event.get("agent", "")
        patient = event.get("patient", "")
        recipient = event.get("recipient", "")  # Some events have recipient
        location = event.get("location", "")
        social_action = event.get("social_action_type", "")
        fact = event.get("fact", "")
        source = event.get("source", "")
        time_idx = event.get("time", event.get("t", None))
        
        # Build human-readable representation (legacy single-line)
        parts = [f"event({eid}"]
        if agent:
            parts.append(f"agent={agent}")
        parts.append(f"type={etype}")
        if patient:
            parts.append(f"patient={patient}")
        if recipient:
            parts.append(f"recipient={recipient}")
        if location:
            parts.append(f"location={location}")
        if social_action:
            parts.append(f"social_action={social_action}")
        if fact:
            parts.append(f"fact={fact}")
        human = ", ".join(parts) + ")"
        
        # Collect related IDs
        related = {eid}
        if agent:
            related.add(agent.lower().replace(" ", "_"))
        if patient:
            related.add(patient.lower().replace(" ", "_"))
        if location:
            related.add(location.lower().replace(" ", "_"))
        
        # Find corresponding ASP fact lines
        asp_lines = []
        for line in asp_facts.split("\n"):
            if f"event({eid.lower()}" in line.lower() or f"({eid.lower()}," in line.lower():
                asp_lines.append(line.strip())
        
        # Build structured data dict for rich formatting
        event_data = {
            "type": etype,
            "agent": agent,
            "patient": patient,
            "recipient": recipient,
            "location": location,
            "social_action": social_action,
            "fact": fact,
            "source": source,
            "time": time_idx,
        }
        
        statements.append(Statement(
            statement_type="event",
            identifier=eid,
            asp_fact="; ".join(asp_lines[:3]) if asp_lines else f"event({eid}).",
            human_readable=human,
            related_ids=related,
            data=event_data,
            chapter=chapter_idx,
        ))
        
        # Special handling for learn events
        if etype == "learn" and fact:
            learned_data = {
                "agent": agent,
                "fact": fact,
                "source": source or "unknown",
                "time": time_idx,
            }
            statements.append(Statement(
                statement_type="learned",
                identifier=f"{agent}:{fact}",
                asp_fact=f"learned({agent}, {fact}, ...).",
                human_readable=f"learned({agent}, fact={fact}, source={source or 'unknown'})",
                related_ids={agent.lower().replace(" ", "_") if agent else "", fact.lower().replace(" ", "_")},
                data=learned_data,
                chapter=chapter_idx,
            ))
    
    # Parse relationships from entities
    entities = chapter_data.get("entities", {})
    for rel in entities.get("relationships", []):
        from_char = rel.get("from", "")
        to_char = rel.get("to", "")
        rel_type = rel.get("type", "neutral")
        
        if from_char and to_char and rel_type != "neutral":
            rel_data = {
                "from": from_char,
                "to": to_char,
                "type": rel_type,
            }
            statements.append(Statement(
                statement_type="relationship",
                identifier=f"{from_char}->{to_char}",
                asp_fact=f"relationship({from_char}, {to_char}, {rel_type}).",
                human_readable=f"relationship({from_char} -> {to_char}, type={rel_type})",
                related_ids={from_char.lower().replace(" ", "_"), to_char.lower().replace(" ", "_")},
                data=rel_data,
                chapter=chapter_idx,
            ))
    
    # Parse characters
    for char in entities.get("characters", []):
        cid = char.get("id", "")
        cname = char.get("name", "")
        emotion = char.get("emotion", "neutral")
        state = char.get("state", "normal")
        
        if cid:
            char_data = {
                "name": cname,
                "emotion": emotion,
                "state": state,
            }
            statements.append(Statement(
                statement_type="character",
                identifier=cid,
                asp_fact=f"character({cid}).",
                human_readable=f"character({cid}, name={cname}, emotion={emotion}, state={state})",
                related_ids={cid.lower().replace(" ", "_")},
                data=char_data,
                chapter=chapter_idx,
            ))
    
    # Parse locations
    for loc in entities.get("locations", []):
        lid = loc.get("id", "")
        lname = loc.get("name", "")
        connections = loc.get("connections", [])
        
        if lid:
            loc_data = {
                "name": lname,
                "connections": connections,
            }
            statements.append(Statement(
                statement_type="location",
                identifier=lid,
                asp_fact=f"location_entity({lid}).",
                human_readable=f"location({lid}, name={lname}, connections={connections})",
                related_ids={lid.lower().replace(" ", "_")},
                data=loc_data,
                chapter=chapter_idx,
            ))
    
    # Parse implied_presence if exists
    for presence in chapter_data.get("implied_presence", []):
        entity = presence.get("entity", "")
        location = presence.get("location", "")
        
        if entity and location:
            presence_time = presence.get("time", presence.get("t", None))
            presence_data = {
                "entity": entity,
                "location": location,
                "time": presence_time,
            }
            statements.append(Statement(
                statement_type="presence",
                identifier=f"{entity}@{location}",
                asp_fact=f"implied_presence({entity}, {location}, ...).",
                human_readable=f"implied_presence({entity} at {location})",
                related_ids={entity.lower().replace(" ", "_"), location.lower().replace(" ", "_")},
                data=presence_data,
                chapter=chapter_idx,
            ))
    
    return statements


@dataclass
class StatementEvaluation:
    """Result of evaluating a single statement."""
    statement: Statement
    is_valid: bool
    violations: List[Dict[str, Any]]
    rules_passed: int
    rules_failed: int
    
    def format_trace(self) -> str:
        """Format this evaluation as a trace string."""
        lines = []
        lines.append("----------------------------------------")
        lines.append("Evaluating this statement now:")
        # Use structured multi-line format
        formatted = self.statement.format_human_readable()
        for line in formatted.split("\n"):
            lines.append(f"  {line}")
        lines.append("")
        
        if self.is_valid:
            lines.append("Result: VALID")
        else:
            lines.append("Result: VIOLATION")
        
        lines.append(f"Rules passed: {self.rules_passed}")
        lines.append(f"Rules failed: {self.rules_failed}")
        
        if self.violations:
            lines.append("Violations:")
            for v in self.violations:
                vtype = v.get("type", "unknown")
                event = v.get("event", "")
                detail = v.get("detail", "")
                cat = v.get("category", "")
                if detail:
                    lines.append(f"  {cat}.{vtype}({event}, {detail})")
                else:
                    lines.append(f"  {cat}.{vtype}({event})")
        
        lines.append("")
        return "\n".join(lines)


def load_extractions(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Load per-chapter extractions from JSONL file."""
    extractions = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                extractions.append(json.loads(line))
    return extractions


@dataclass
class ClingoResult:
    """Result from running Clingo solver."""
    violations: List[Tuple[str, ...]]
    total_atoms: int
    total_rules: int


def run_clingo(asp_facts: str, rule_files: List[Path]) -> ClingoResult:
    """
    Run Clingo solver and return violations with statistics.
    
    Args:
        asp_facts: ASP facts string
        rule_files: List of rule file paths to load
        
    Returns:
        ClingoResult with violations and statistics
    """
    import clingo
    
    violations = []
    total_atoms = 0
    total_rules = 0
    
    # Write facts to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.lp', delete=False) as f:
        f.write(asp_facts)
        facts_path = Path(f.name)
    
    try:
        ctl = clingo.Control(["--warn=none", "--stats"])
        
        # Load all rule files
        for rule_file in rule_files:
            if rule_file.exists():
                ctl.load(str(rule_file))
        
        # Load facts
        ctl.load(str(facts_path))
        
        # Ground and solve
        ctl.ground([("base", [])])
        
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                total_atoms = len(model.symbols(atoms=True))
                for atom in model.symbols(shown=True):
                    if atom.name == "violation":
                        parts = tuple(str(arg) for arg in atom.arguments)
                        violations.append(parts)
        
        # Try to get rule count from statistics
        try:
            stats = ctl.statistics
            if "problem" in stats and "lp" in stats["problem"]:
                total_rules = int(stats["problem"]["lp"].get("rules", 0))
        except:
            pass
    
    finally:
        facts_path.unlink(missing_ok=True)
    
    return ClingoResult(
        violations=violations,
        total_atoms=total_atoms,
        total_rules=total_rules,
    )


def categorize_violation(v: Tuple[str, ...]) -> Dict[str, Any]:
    """Categorize a violation tuple into structured format."""
    # Violations can be:
    #   (category, type, event, detail)
    #   (type, event, detail)
    #   (type, event)
    
    if len(v) >= 4:
        category = v[0].strip('"').lower()
        vtype = v[1].strip('"')
        event = v[2].strip('"')
        detail = v[3].strip('"')
    elif len(v) >= 3:
        vtype = v[0].strip('"')
        event = v[1].strip('"')
        detail = v[2].strip('"')
        category = infer_category(vtype)
    elif len(v) >= 2:
        vtype = v[0].strip('"')
        event = v[1].strip('"')
        detail = ""
        category = infer_category(vtype)
    else:
        return {
            "category": "unknown",
            "type": "unknown",
            "event": "unknown",
            "detail": str(v),
        }
    
    return {
        "category": category,
        "type": vtype,
        "event": event,
        "detail": detail,
    }


def infer_category(vtype: str) -> str:
    """Infer error category from violation type."""
    vtype = vtype.lower()
    
    if vtype in {"ubiquity", "proximity_required", "impossible_travel", "unreachable_location"}:
        return "location"
    if vtype in {"circular_time", "negative_duration", "explicit_order_violated", 
                 "epistemic_temporal_violation", "temporal_inconsistency"}:
        return "temporal"
    if vtype in {"chekhov_gun", "uncaused_event", "effect_without_cause", 
                 "precondition_missing", "causality", "dead_character_acting"}:
        return "causality"
    if vtype in {"conflicting_dialogue", "out_of_character", "relationship_violation",
                 "hostile_greeting", "friendly_threat", "neutral_departure_no_greeting"}:
        return "emotional"
    if vtype in {"appearance_change_without_cause", "state_persistence_error",
                 "appearance", "coherence", "solo_communication"}:
        return "coherence"
    
    return "other"


def collect_rule_files() -> List[Path]:
    """Collect all rule files to load into Clingo."""
    rules_dir = PROJECT_ROOT / "rules"
    rule_files = []
    
    # Core rules
    core_file = rules_dir / "core.lp"
    if core_file.exists():
        rule_files.append(core_file)
    
    # Base rules (fallback)
    base_file = rules_dir / "base.lp"
    if base_file.exists() and core_file not in rule_files:
        rule_files.append(base_file)
    
    # General narrative rules
    general_narrative = rules_dir / "general_narrative.lp"
    if general_narrative.exists():
        rule_files.append(general_narrative)
    
    # Story-specific rules (exceptions for canonical events)
    story_rules = rules_dir / "story_rules.lp"
    if story_rules.exists():
        rule_files.append(story_rules)
    
    # Universal rules (all .lp files)
    universal_dir = rules_dir / "universal"
    if universal_dir.exists():
        for lp_file in sorted(universal_dir.glob("*.lp")):
            rule_files.append(lp_file)
    
    return rule_files


def evaluate_statements(
    statements: List[Statement],
    categorized_violations: List[Dict[str, Any]],
) -> List[StatementEvaluation]:
    """
    Evaluate each statement against the violations.
    
    Rule counting is derived from actual ASP output:
    - Distinct violation types (category, type) = unique rules that can fail
    - For each statement: rules_failed = violations matching this statement
    - For each statement: rules_passed = distinct rule types - distinct failures for this statement
    
    Args:
        statements: List of parsed statements
        categorized_violations: List of categorized violation dicts
        
    Returns:
        List of StatementEvaluation results
    """
    # Calculate distinct violation rule types from actual ASP output
    # Each unique (category, type) pair represents a distinct rule that fired
    all_rule_types: Set[Tuple[str, str]] = set()
    for v in categorized_violations:
        rule_type = (v.get("category", ""), v.get("type", ""))
        all_rule_types.add(rule_type)
    
    total_distinct_rules = len(all_rule_types)
    
    evaluations = []
    
    for stmt in statements:
        # Find violations that directly involve this statement
        matching_violations = [
            v for v in categorized_violations
            if stmt.matches_violation(v)
        ]
        
        # Count distinct rule types that failed for THIS statement
        failed_rule_types: Set[Tuple[str, str]] = set()
        for v in matching_violations:
            rule_type = (v.get("category", ""), v.get("type", ""))
            failed_rule_types.add(rule_type)
        
        is_valid = len(matching_violations) == 0
        rules_failed = len(failed_rule_types)  # Distinct rule types that failed
        rules_passed = max(0, total_distinct_rules - rules_failed)  # Rules that didn't fail for this statement
        
        evaluations.append(StatementEvaluation(
            statement=stmt,
            is_valid=is_valid,
            violations=matching_violations,
            rules_passed=rules_passed,
            rules_failed=rules_failed,
        ))
    
    return evaluations


def run_logic_test(
    experiment_dir: Path,
    output_log: Path,
    verbose: bool = False,
    trace: bool = False,
    story_filter: List[str] = None,
) -> Dict[str, Any]:
    """
    Run logic test on all chapters in the experiment.
    
    Args:
        experiment_dir: Path to experiment directory containing step2_extractions.jsonl
        output_log: Path to output log file
        verbose: Whether to print verbose output
        trace: Whether to include per-statement evaluation traces
        story_filter: If provided, only process chapters from these stories
        
    Returns:
        Summary dict with violation counts
    """
    extractions_path = experiment_dir / "step2_extractions.jsonl"
    
    if not extractions_path.exists():
        raise FileNotFoundError(f"No extractions found at {extractions_path}")
    
    # Load extractions
    extractions = load_extractions(extractions_path)
    print(f"Loaded {len(extractions)} chapter extractions from {extractions_path}")
    
    # Filter by story if specified
    if story_filter:
        story_filter_lower = [s.lower() for s in story_filter]
        extractions = [e for e in extractions if e.get("story", "").lower() in story_filter_lower]
        print(f"Filtered to {len(extractions)} extractions for stories: {', '.join(story_filter)}")
    
    # Collect rule files
    rule_files = collect_rule_files()
    print(f"Loaded {len(rule_files)} rule files")
    if verbose:
        for rf in rule_files:
            print(f"  - {rf.name}")
    
    # Summary tracking
    total_violations = 0
    total_statements_evaluated = 0
    category_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    chapter_results: List[Dict[str, Any]] = []
    
    log_lines = []
    log_lines.append("=" * 80)
    log_lines.append(f"Logic-Only Test Runner")
    log_lines.append(f"Timestamp: {datetime.now().isoformat()}")
    log_lines.append(f"Experiment: {experiment_dir}")
    log_lines.append(f"Rule files: {len(rule_files)}")
    log_lines.append("=" * 80)
    log_lines.append("")
    
    # Process each chapter
    for extraction in extractions:
        story = extraction.get("story", "unknown")
        variant = extraction.get("variant", "original")
        chapter = extraction.get("chapter", -1)
        chapter_data = extraction.get("extraction", {})
        
        chapter_header = f"Chapter {chapter} ({story} - {variant})"
        log_lines.append("-" * 60)
        log_lines.append(chapter_header)
        log_lines.append("-" * 60)
        
        if verbose:
            print(f"\nProcessing {chapter_header}...")
        
        # Convert to ASP
        asp_facts = to_asp(chapter_data, chapter)
        
        # Add variant indicator for rules to use
        if variant == "modified":
            asp_facts += "\n% Variant indicator\nmodified_story.\n"
        else:
            asp_facts += "\n% Variant indicator\noriginal_story.\n"
        
        # Run Clingo
        clingo_result = run_clingo(asp_facts, rule_files)
        violations = clingo_result.violations
        
        # Categorize violations
        categorized = [categorize_violation(v) for v in violations]
        
        chapter_result = {
            "chapter": chapter,
            "story": story,
            "variant": variant,
            "violation_count": len(violations),
            "violations": categorized,
        }
        chapter_results.append(chapter_result)
        
        # Update counts
        total_violations += len(violations)
        for cat_v in categorized:
            cat = cat_v["category"]
            vtype = cat_v["type"]
            category_counts[cat] = category_counts.get(cat, 0) + 1
            type_counts[vtype] = type_counts.get(vtype, 0) + 1
        
        # Per-statement trace evaluation
        if trace:
            log_lines.append("")
            log_lines.append("=" * 40)
            log_lines.append("STATEMENT-BY-STATEMENT EVALUATION TRACE")
            log_lines.append("=" * 40)
            log_lines.append("")
            
            # Parse statements from chapter data
            statements = parse_asp_facts_to_statements(asp_facts, chapter_data)
            
            # Evaluate each statement against actual violations from ASP output
            evaluations = evaluate_statements(statements, categorized)
            
            # Log trace for each statement
            valid_count = 0
            violation_count = 0
            for eval_result in evaluations:
                log_lines.append(eval_result.format_trace())
                if eval_result.is_valid:
                    valid_count += 1
                else:
                    violation_count += 1
            
            log_lines.append(f"Trace Summary: {valid_count} VALID, {violation_count} VIOLATION")
            log_lines.append("")
            
            # Update total statements count
            total_statements_evaluated += len(evaluations)
            
            if verbose:
                print(f"  Traced {len(evaluations)} statements: {valid_count} valid, {violation_count} violations")
        
        # Log violations (summary mode)
        if violations:
            log_lines.append(f"Violations: {len(violations)}")
            for i, cat_v in enumerate(categorized, 1):
                log_lines.append(f"  {i}. [{cat_v['category']}] {cat_v['type']}: {cat_v['event']}")
                if cat_v['detail']:
                    log_lines.append(f"      Detail: {cat_v['detail']}")
        else:
            log_lines.append("Violations: 0 (clean)")
        
        log_lines.append("")
        
        if verbose:
            print(f"  Found {len(violations)} violations")
    
    # Summary
    log_lines.append("=" * 80)
    log_lines.append("SUMMARY")
    log_lines.append("=" * 80)
    log_lines.append(f"Total chapters processed: {len(extractions)}")
    log_lines.append(f"Total violations: {total_violations}")
    log_lines.append("")
    
    log_lines.append("Violations by category:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        log_lines.append(f"  {cat}: {count}")
    log_lines.append("")
    
    log_lines.append("Violations by type:")
    for vtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        log_lines.append(f"  {vtype}: {count}")
    
    # Write log in append mode
    with open(output_log, 'a', encoding='utf-8') as f:
        # Write run header
        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("LOGIC EVALUATION TRACE\n")
        f.write("=" * 80 + "\n")
        f.write(f"Experiment: {experiment_dir}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Total statements evaluated: {total_statements_evaluated}\n")
        f.write(f"Total violations: {total_violations}\n")
        f.write(f"Rule files: {len(rule_files)}\n")
        f.write("=" * 80 + "\n")
        f.write("\n")
        
        # Write all log content
        f.write("\n".join(log_lines))
        f.write("\n")
    
    print(f"\nResults written to {output_log}")
    print(f"Total violations: {total_violations}")
    
    return {
        "total_violations": total_violations,
        "category_counts": category_counts,
        "type_counts": type_counts,
        "chapters_processed": len(extractions),
        "chapter_results": chapter_results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run ASP/Clingo logic engine on pre-extracted data (no LLMs)"
    )
    parser.add_argument(
        "--experiment_dir",
        type=str,
        required=True,
        help="Path to experiment directory containing step2_extractions.jsonl"
    )
    parser.add_argument(
        "--output_log",
        type=str,
        default="logic_test_results.txt",
        help="Path to output log file (default: logic_test_results.txt)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output"
    )
    parser.add_argument(
        "--trace", "-t",
        action="store_true",
        help="Enable per-statement evaluation traces in output"
    )
    parser.add_argument(
        "--story", "-s",
        type=str,
        nargs='*',
        default=None,
        help="Filter to specific stories (e.g., --story 'Harry Potter' 'Twilight')"
    )
    
    args = parser.parse_args()
    
    experiment_dir = Path(args.experiment_dir)
    if not experiment_dir.is_absolute():
        experiment_dir = PROJECT_ROOT / experiment_dir
    
    output_log = Path(args.output_log)
    if not output_log.is_absolute():
        output_log = Path.cwd() / output_log
    
    # Append story name to output file if filtering
    if args.story:
        story_slug = "_".join(s.lower().replace(" ", "_") for s in args.story)
        stem = output_log.stem
        suffix = output_log.suffix or ".txt"
        output_log = output_log.with_name(f"{stem}_{story_slug}{suffix}")
    
    if not experiment_dir.exists():
        print(f"Error: Experiment directory not found: {experiment_dir}")
        sys.exit(1)
    
    try:
        results = run_logic_test(experiment_dir, output_log, args.verbose, args.trace, args.story)
        print(f"\nSummary:")
        print(f"  Chapters: {results['chapters_processed']}")
        print(f"  Total violations: {results['total_violations']}")
        if results['category_counts']:
            print(f"  By category: {dict(sorted(results['category_counts'].items(), key=lambda x: -x[1]))}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
