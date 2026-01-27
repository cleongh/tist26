#!/usr/bin/env python3
"""
run_baseline_experiment.py - Unified Narrative Evaluation with Baseline Filtering
==================================================================================

This script runs a complete narrative evaluation experiment that:
1. Analyzes ORIGINAL books to establish a false-positive baseline
2. Analyzes MODIFIED books to detect intentional errors
3. Filters test errors using baseline signatures (errors in original = false positives)
4. Performs k-fold cross-validation across books
5. Generates comprehensive reports for academic publication

KEY DESIGN DECISIONS:
- Each story is analyzed in INDEPENDENT API calls (no context carryover)
- Temperature is set to 0 for deterministic results
- The ASP generation uses general.lp and base.lp rules as context
- Logic errors include actual story fragments for traceability

ERROR CATEGORIES:
- CAUSALITY: Chekhov's gun, cause-effect chains, unmotivated actions
- COHERENCE: Semantic correctness, physical impossibility, state contradictions
- TEMPORAL: Time intervals, ordering violations, impossible durations
- LOCATION: Spatial constraints, ubiquity, teleportation
- EMOTIONAL: Character motivations, relationship consistency

USAGE:
    source venv/bin/activate
    python scripts/run_baseline_experiment.py --model-name "gemma" --chapters-per-book 2

OUTPUT:
    experiments/<name>-<start>-<end>-<uuid>/
    ├── config.json
    ├── baseline/              # Results from original books
    │   ├── llm_results/
    │   ├── logic_results/
    │   └── baseline_signatures.json
    ├── test/                  # Results from modified books
    │   ├── llm_results/
    │   ├── logic_results/
    │   └── filtered_results.json
    ├── kfold_results/         # K-fold analysis
    ├── stories/
    ├── logs/
    ├── report.md
    └── summary.json

Author: Research Project - Narrative Evaluation Comparison
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import traceback
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.request
import urllib.error

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from json_to_asp import json_to_asp, sanitize_symbol
from llm_structurer import extract_json, strip_think

# =============================================================================
# CONSTANTS
# =============================================================================

ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]

CATEGORY_DESCRIPTIONS = {
    "causality": "Cause-effect violations (Chekhov's gun, missing causes, unmotivated actions)",
    "coherence": "Semantic/logical inconsistencies (physical impossibility, dead agents, contradictions)",
    "temporal": "Time violations (impossible ordering, duration errors, overlapping conflicts)",
    "location": "Spatial violations (ubiquity, impossible reach, teleportation)",
    "emotional": "Character motivation violations (harming loved ones, helping enemies)",
}

# LLM Lint prompt for detailed analysis
LLM_LINT_PROMPT = """You are a narrative consistency analyzer for academic research.
Analyze this story CAREFULLY for errors in 5 categories. Be thorough but precise.

## ERROR CATEGORIES

### 1. CAUSALITY (cause-effect violations)
- Chekhov's gun: Significant objects introduced but never used
- Missing cause: Major events without explanation
- Unmotivated action: Characters act without clear motivation

### 2. COHERENCE (semantic/logical violations)
- Physical impossibility: Actions impossible given constraints
- Dead agent: Character acts after being killed
- State contradiction: Entity in contradictory state

### 3. TEMPORAL (time-related violations)
- Impossible order: Events in wrong sequence
- Duration violation: Action takes impossible time
- Overlap conflict: Incompatible simultaneous activities

### 4. LOCATION (spatial violations)
- Ubiquity: Character in two places simultaneously
- Impossible reach: Interacting with distant objects
- Teleportation: Instant movement without travel

### 5. EMOTIONAL (relationship/motivation violations)
- Harm loved: Hurting someone loved without justification
- Help enemy: Helping someone hated without motivation
- Emotion mismatch: Behavior contradicts emotional state

## OUTPUT FORMAT

Return ONLY valid JSON:
{{
  "story_title": "extracted title",
  "error_count": integer,
  "errors": [
    {{
      "id": "err_1",
      "category": "causality|coherence|temporal|location|emotional",
      "type": "specific_type",
      "description": "Detailed explanation",
      "story_fragment": "exact quote from story",
      "conflicting_fragments": ["other quotes"],
      "severity": "low|medium|high"
    }}
  ],
  "summary": {{
    "by_category": {{"causality": 0, "coherence": 0, "temporal": 0, "location": 0, "emotional": 0}},
    "by_severity": {{"low": 0, "medium": 0, "high": 0}}
  }}
}}

Story to analyze:
\"\"\"
{story}
\"\"\"
"""


# =============================================================================
# LOGGING
# =============================================================================

class Logger:
    """Experiment logger with timestamps."""
    
    def __init__(self, exp_dir: Path):
        self.exp_dir = exp_dir
        self.log_file = exp_dir / "logs" / "experiment.log"
        self.llm_log_file = exp_dir / "llm_calls.jsonl"
        self.start_time = datetime.now()
        
    def _elapsed(self) -> str:
        return f"+{(datetime.now() - self.start_time).total_seconds():.1f}s"
        
    def log(self, msg: str, level: str = "INFO") -> None:
        ts = datetime.now().isoformat()
        formatted = f"[{ts}] [{level}] [{self._elapsed()}] {msg}"
        print(formatted, file=sys.stderr, flush=True)
        with open(self.log_file, "a") as f:
            f.write(formatted + "\n")
            
    def info(self, msg: str): self.log(msg, "INFO")
    def error(self, msg: str): self.log(msg, "ERROR")
    def warning(self, msg: str): self.log(msg, "WARNING")
    
    def log_llm_call(self, data: Dict) -> None:
        data["timestamp"] = datetime.now().isoformat()
        data["elapsed_since_start"] = (datetime.now() - self.start_time).total_seconds()
        with open(self.llm_log_file, "a") as f:
            f.write(json.dumps(data) + "\n")


# =============================================================================
# ERROR SIGNATURE FOR BASELINE FILTERING
# =============================================================================

def compute_error_signature(error: Dict) -> str:
    """
    Compute a signature for an error to enable deduplication.
    Errors with matching signatures in baseline are filtered as false positives.
    """
    cat = error.get("category", "unknown").lower()
    etype = error.get("type", "unknown").lower()
    # Use first 200 chars of description for matching
    desc = error.get("description", "")[:200].lower()
    content = f"{cat}:{etype}:{desc}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


# =============================================================================
# DOMAIN GENERATOR
# =============================================================================

class DomainGenerator:
    """Generates domain-specific ASP rules from analyzed stories."""
    
    def __init__(self):
        self.locations: Set[str] = set()
        self.characters: Set[str] = set()
        self.relationships: List[Tuple[str, str, str]] = []
        self.emotional_states: List[Tuple[str, str, str]] = []
        self.significant_events: Set[str] = set()
        
    def add_story_data(self, structured_data: Dict, story_name: str) -> None:
        """Extract domain knowledge from structured story data."""
        entities = structured_data.get("entities", {})
        
        # Extract characters
        for char in entities.get("characters", []):
            name = char.get("name", "")
            if name:
                self.characters.add(sanitize_symbol(name))
                
        # Extract locations
        for loc in entities.get("locations", []):
            name = loc.get("name", "")
            if name:
                self.locations.add(sanitize_symbol(name))
                
        # Extract relationships
        for rel in structured_data.get("character_relations", []):
            char1 = sanitize_symbol(rel.get("character1", ""))
            char2 = sanitize_symbol(rel.get("character2", ""))
            reltype = sanitize_symbol(rel.get("relation", ""))
            if char1 and char2 and reltype:
                self.relationships.append((char1, char2, reltype))
                
        # Extract significant events
        for ev in structured_data.get("events", []):
            if ev.get("is_significant", False):
                ev_id = sanitize_symbol(ev.get("id", ""))
                if ev_id:
                    self.significant_events.add(ev_id)
                    
    def generate_module(self) -> str:
        """Generate ASP rules for the domain."""
        lines = [
            "% Domain-Specific ASP Module",
            "% Generated: " + datetime.now().isoformat(),
            "",
            "% === CHARACTERS ===",
        ]
        
        for char in sorted(self.characters):
            lines.append(f"character({char}).")
            
        lines.append("")
        lines.append("% === LOCATIONS ===")
        for loc in sorted(self.locations):
            lines.append(f"location({loc}).")
            
        lines.append("")
        lines.append("% === RELATIONSHIPS ===")
        for c1, c2, rel in self.relationships:
            lines.append(f"relationship({c1}, {c2}, {rel}).")
            
        lines.append("")
        lines.append("% === SIGNIFICANT EVENTS ===")
        for ev in sorted(self.significant_events):
            lines.append(f"significant_event({ev}).")
            
        # Add relationship inference rules
        lines.extend([
            "",
            "% === RELATIONSHIP INFERENCE ===",
            "loves(X, Y) :- relationship(X, Y, loves).",
            "loves(X, Y) :- relationship(X, Y, romantic_partner).",
            "hates(X, Y) :- relationship(X, Y, hates).",
            "hates(X, Y) :- relationship(X, Y, enemy).",
            "fears(X, Y) :- relationship(X, Y, fears).",
            "trusts(X, Y) :- relationship(X, Y, trusts).",
            "trusts(X, Y) :- relationship(X, Y, friend).",
        ])
        
        return "\n".join(lines)


# =============================================================================
# EXPERIMENT RUNNER
# =============================================================================

class BaselineExperiment:
    """
    Runs narrative evaluation experiment with baseline filtering.
    
    1. Analyze original books -> baseline signatures (false positives)
    2. Analyze modified books -> detect errors
    3. Filter test errors using baseline
    4. K-fold cross-validation
    """
    
    def __init__(self, exp_dir: Path, config: Dict, logger: Logger):
        self.exp_dir = exp_dir
        self.config = config
        self.logger = logger
        
        self.llm_base_url = config.get("llm_base_url", "http://localhost:8080/v1")
        self.llm_model = config.get("llm_model", "auto")
        self.llm_timeout = config.get("llm_timeout", 600)
        
        # Results storage
        self.baseline_llm: Dict[str, Dict] = {}
        self.baseline_logic: Dict[str, Dict] = {}
        self.test_llm: Dict[str, Dict] = {}
        self.test_logic: Dict[str, Dict] = {}
        
        # Baseline signatures for filtering
        self.baseline_llm_sigs: Set[str] = set()
        self.baseline_logic_sigs: Set[str] = set()
        
        # Story data
        self.original_stories: Dict[str, Dict] = {}
        self.modified_stories: Dict[str, Dict] = {}
        self.structured_data: Dict[str, Dict] = {}
        
        # Domain generator
        self.domain_gen = DomainGenerator()
        
    def resolve_model(self) -> str:
        """Resolve model name from server."""
        if self.llm_model != "auto":
            return self.llm_model
            
        try:
            url = self.llm_base_url.rstrip("/") + "/models"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get("data"):
                    self.llm_model = data["data"][0]["id"]
                    return self.llm_model
        except Exception as e:
            self.logger.warning(f"Failed to resolve model: {e}")
            
        self.llm_model = "unknown"
        return self.llm_model
        
    def load_stories(self, books_dir: Path, max_chapters: int) -> Dict[str, Dict]:
        """Load stories from book directories."""
        stories = {}
        
        if not books_dir.exists():
            self.logger.error(f"Books directory not found: {books_dir}")
            return stories
            
        for book_dir in sorted(books_dir.iterdir()):
            if not book_dir.is_dir():
                continue
                
            book_name = book_dir.name
            chapter_files = sorted(book_dir.glob("*.txt"))[:max_chapters]
            
            for chapter_file in chapter_files:
                chapter_num = chapter_file.stem
                title = f"{book_name}_Chapter_{chapter_num}"
                content = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                stories[title] = {
                    "content": content,
                    "book": book_name,
                    "chapter": chapter_num,
                    "file_path": str(chapter_file),
                }
                
        return stories
        
    def call_llm(self, prompt: str, purpose: str, system_prompt: str = None, 
                 max_tokens: int = 8192) -> Tuple[str, float]:
        """
        Make a FRESH LLM API call with no context carryover.
        
        Each call creates a new, independent request - no conversation history.
        Temperature is set to 0 for deterministic, reproducible results.
        """
        start_time = time.time()
        
        if system_prompt is None:
            system_prompt = "You are a narrative consistency analyzer. Return only valid JSON."
        
        url = self.llm_base_url.rstrip("/") + "/chat/completions"
        
        # CRITICAL: Each call is independent - fresh messages array, temperature=0
        payload = {
            "model": self.llm_model,
            "temperature": 0,  # Deterministic output
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            
            with urllib.request.urlopen(req, timeout=self.llm_timeout) as resp:
                body = resp.read().decode("utf-8")
                
            elapsed = time.time() - start_time
            obj = json.loads(body)
            content = obj["choices"][0]["message"]["content"]
            
            self.logger.log_llm_call({
                "purpose": purpose,
                "model": self.llm_model,
                "prompt_length": len(prompt),
                "response_length": len(content),
                "elapsed_seconds": elapsed,
                "status": "success",
            })
            
            return content, elapsed
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.log_llm_call({
                "purpose": purpose,
                "model": self.llm_model,
                "elapsed_seconds": elapsed,
                "status": "error",
                "error": str(e),
            })
            raise
            
    def run_llm_lint(self, title: str, content: str) -> Dict:
        """Run LLM-based linting - each story is an independent call."""
        start_time = time.time()
        
        prompt = LLM_LINT_PROMPT.format(story=content.strip())
        
        try:
            response, api_elapsed = self.call_llm(prompt, f"llm_lint:{title}")
            
            # Extract JSON
            raw_json = extract_json(response)
            if raw_json is None:
                raw_json = extract_json(strip_think(response))
            if raw_json is None:
                return self._empty_result(title, "JSON extraction failed")
                
            result = json.loads(raw_json)
            result = self._normalize_result(result, title)
            
            elapsed = time.time() - start_time
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "model": self.llm_model,
                "timestamp": datetime.now().isoformat(),
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM lint failed for {title}: {e}")
            return self._empty_result(title, str(e))
    
    def _load_asp_rules(self) -> str:
        """Load the general.lp and base.lp rules for context."""
        rules_text = ""
        
        general_path = REPO_ROOT / "rules" / "general.lp"
        base_path = REPO_ROOT / "rules" / "base.lp"
        
        if general_path.exists():
            rules_text += f"=== GENERAL.LP RULES ===\n{general_path.read_text()}\n\n"
        if base_path.exists():
            rules_text += f"=== BASE.LP RULES ===\n{base_path.read_text()}\n\n"
            
        return rules_text
    
    def _build_structure_prompt(self, story_content: str) -> str:
        """
        Build the story structuring prompt with ASP rules context.
        
        The prompt includes the general.lp and base.lp rules so the LLM
        generates JSON that is compatible with our Clingo rules.
        """
        asp_rules = self._load_asp_rules()
        
        prompt = f"""You are a semantic parser that converts narrative text into structured JSON for logic-based analysis.

The JSON you produce will be converted to ASP (Answer Set Programming) facts and processed by Clingo.
Below are the ASP rules that will be used. Your JSON MUST produce facts compatible with these rules.

{asp_rules}

=== OUTPUT JSON SCHEMA ===

Your JSON must have this structure:
{{
  "entities": {{
    "characters": [{{"id": "lowercase_name", "name": "Original Name"}}],
    "objects": [{{"id": "lowercase_id", "type": "object_type", "name": "Name"}}],
    "locations": [{{"id": "lowercase_id", "name": "Location Name"}}]
  }},
  "events": [
    {{
      "id": "e1",
      "type": "action_verb",  // e.g., "eat", "walk", "speak", "kill", "open"
      "agent": "character_id",
      "patient": "object_or_character_id",  // can be null
      "location": "location_id",
      "time": {{"start": "t1", "end": "t1"}},
      "description": "Brief description of what happens",
      "requires_focus": true/false
    }}
  ],
  "time_order": ["t1", "t2", "t3"],  // chronological order of time points
  "fluents": [
    {{"property": "alive", "entity": "character_id", "start": "t1", "end": "t5"}}
  ],
  "traits": [
    {{"character": "character_id", "trait": "trait_name"}}  // e.g., blind, deaf, mute
  ],
  "character_relations": [
    {{"character1": "id1", "character2": "id2", "relation": "loves/hates/fears/trusts"}}
  ]
}}

=== IMPORTANT RULES ===

1. All IDs must be lowercase with underscores (no spaces, no special chars)
2. Event types should be simple verbs: eat, walk, run, speak, kill, die, open, close, take, give, etc.
3. Time points should be sequential: t1, t2, t3...
4. Include ALL events from the story, even minor ones
5. For each event, include a "description" field with the actual story fragment

=== STORY TO ANALYZE ===

{story_content}

Return ONLY the JSON, no explanations."""
        
        return prompt
            
    def run_logic_lint(self, title: str, content: str) -> Dict:
        """
        Run logic-based linting using Clingo.
        
        Each story is structured in an independent LLM call (no context carryover).
        The structuring prompt includes ASP rules for compatibility.
        """
        start_time = time.time()
        
        try:
            # Build prompt with ASP rules context
            prompt = self._build_structure_prompt(content)
            
            # Make independent LLM call for structuring
            response, _ = self.call_llm(
                prompt, 
                f"structure:{title}",
                system_prompt="You are a semantic parser. Output only valid JSON.",
                max_tokens=16384
            )
            
            # Extract JSON from response
            raw_json = extract_json(response)
            if raw_json is None:
                raw_json = extract_json(strip_think(response))
            if raw_json is None:
                self.logger.error(f"Failed to extract JSON for {title}")
                return self._empty_result(title, "JSON extraction failed")
            
            structured_data = json.loads(raw_json)
            
            # Apply defaults for missing fields
            structured_data.setdefault("entities", {"characters": [], "objects": [], "locations": []})
            structured_data.setdefault("events", [])
            structured_data.setdefault("fluents", [])
            structured_data.setdefault("traits", [])
            structured_data.setdefault("character_relations", [])
            
            self.structured_data[title] = structured_data
            self.domain_gen.add_story_data(structured_data, title)
            
            # Save structured data
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
            struct_dir = self.exp_dir / "structured_json"
            struct_dir.mkdir(exist_ok=True)
            (struct_dir / f"{safe_title}.json").write_text(
                json.dumps(structured_data, indent=2, ensure_ascii=False)
            )
            
            # Convert to ASP and run Clingo
            asp_facts = json_to_asp(structured_data)
            
            # Save ASP facts
            asp_dir = self.exp_dir / "asp_facts"
            asp_dir.mkdir(exist_ok=True)
            (asp_dir / f"{safe_title}.lp").write_text(asp_facts)
            
            # Run Clingo
            violations = self._run_clingo(asp_facts, title)
            
            # Categorize violations WITH story fragments
            result = self._categorize_violations(violations, structured_data, content)
            
            elapsed = time.time() - start_time
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat(),
                "events_count": len(structured_data.get("events", [])),
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Logic lint failed for {title}: {e}\n{traceback.format_exc()}")
            return self._empty_result(title, str(e))
            
    def _run_clingo(self, asp_facts: str, title: str) -> List[Tuple]:
        """Run Clingo solver."""
        import clingo
        
        violations = []
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(asp_facts)
            facts_path = f.name
            
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load rules
            general_path = REPO_ROOT / "rules" / "general.lp"
            if general_path.exists():
                ctl.load(str(general_path))
            else:
                base_path = REPO_ROOT / "rules" / "base.lp"
                if base_path.exists():
                    ctl.load(str(base_path))
                    
            # Load domain module
            domain_path = self.exp_dir / "domain_module.lp"
            if domain_path.exists():
                ctl.load(str(domain_path))
                
            ctl.load(facts_path)
            ctl.ground([("base", [])])
            
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "violation":
                            parts = tuple(str(arg) for arg in atom.arguments)
                            violations.append(parts)
                            
        finally:
            os.unlink(facts_path)
            
        return violations
    
    def _find_story_fragment(self, story_content: str, search_terms: List[str], context_chars: int = 200) -> str:
        """
        Find and extract a story fragment containing the search terms.
        Returns the fragment with surrounding context.
        """
        story_lower = story_content.lower()
        
        for term in search_terms:
            term_lower = term.lower().replace('"', '').replace("_", " ")
            if len(term_lower) < 2:
                continue
                
            pos = story_lower.find(term_lower)
            if pos != -1:
                # Extract fragment with context
                start = max(0, pos - context_chars // 2)
                end = min(len(story_content), pos + len(term_lower) + context_chars // 2)
                
                # Try to start/end at sentence boundaries
                if start > 0:
                    # Find previous sentence end
                    for i in range(start, max(0, start - 50), -1):
                        if story_content[i] in '.!?':
                            start = i + 1
                            break
                            
                if end < len(story_content):
                    # Find next sentence end
                    for i in range(end, min(len(story_content), end + 50)):
                        if story_content[i] in '.!?':
                            end = i + 1
                            break
                
                fragment = story_content[start:end].strip()
                if start > 0:
                    fragment = "..." + fragment
                if end < len(story_content):
                    fragment = fragment + "..."
                    
                return fragment
                
        return ""
        
    def _categorize_violations(self, violations: List[Tuple], structured_data: Dict, 
                               story_content: str) -> Dict:
        """
        Categorize Clingo violations by error category.
        
        IMPORTANT: Each error includes the actual story fragment for traceability.
        """
        errors = []
        category_counts = {cat: 0 for cat in ERROR_CATEGORIES}
        
        # Build event lookup with descriptions
        event_lookup = {}
        for ev in structured_data.get("events", []):
            ev_id = sanitize_symbol(ev.get("id", ""))
            event_lookup[ev_id] = ev
            
        # Build character/object lookups for finding fragments
        entity_names = []
        for char in structured_data.get("entities", {}).get("characters", []):
            entity_names.append(char.get("name", char.get("id", "")))
        for obj in structured_data.get("entities", {}).get("objects", []):
            entity_names.append(obj.get("name", obj.get("id", "")))
            
        for i, v in enumerate(violations):
            if len(v) >= 4:
                category, vtype, event, detail = v[0].lower(), v[1], v[2], v[3]
            elif len(v) >= 2:
                vtype, event = v[0], v[1]
                detail = v[2] if len(v) > 2 else ""
                category = self._infer_category(vtype)
            else:
                continue
                
            if category not in ERROR_CATEGORIES:
                category = self._infer_category(vtype)
                
            if category in category_counts:
                category_counts[category] += 1
            
            # Get event info
            event_clean = event.replace('"', '')
            ev_info = event_lookup.get(event_clean, {})
            
            # Get event description if available
            ev_description = ev_info.get("description", "")
            ev_type = ev_info.get("type", "unknown")
            ev_agent = ev_info.get("agent", "unknown")
            ev_patient = ev_info.get("patient", "")
            
            # Build search terms for finding story fragment
            search_terms = [
                ev_description,
                ev_agent,
                ev_patient,
                str(detail).replace('"', ''),
                event_clean,
            ]
            search_terms = [t for t in search_terms if t and len(t) > 2]
            
            # Find actual story fragment
            story_fragment = self._find_story_fragment(story_content, search_terms)
            
            # If no fragment found from search, use event description
            if not story_fragment and ev_description:
                story_fragment = ev_description
                
            # Build detailed description
            description_parts = [f"Violation: {vtype}"]
            if ev_type != "unknown":
                description_parts.append(f"Event type: {ev_type}")
            if ev_agent != "unknown":
                description_parts.append(f"Agent: {ev_agent}")
            if ev_patient:
                description_parts.append(f"Patient: {ev_patient}")
            if detail:
                description_parts.append(f"Detail: {detail}")
                
            errors.append({
                "id": f"logic_{i+1}",
                "category": category,
                "type": str(vtype),
                "event_id": str(event),
                "detail": str(detail),
                "description": " | ".join(description_parts),
                "story_fragment": story_fragment,
                "event_info": {
                    "type": ev_type,
                    "agent": ev_agent,
                    "patient": ev_patient,
                    "description": ev_description,
                },
            })
            
        return {
            "error_count": len(errors),
            "errors": errors,
            "summary": {"by_category": category_counts},
        }
        
    def _infer_category(self, vtype: str) -> str:
        """Infer category from violation type."""
        vtype = str(vtype).lower()
        
        if vtype in {"ubiquity", "proximity_required", "teleportation"}:
            return "location"
        if vtype in {"circular_time", "negative_duration", "overlap"}:
            return "temporal"
        if vtype in {"chekhov_gun", "uncaused_event", "precondition"}:
            return "causality"
        if vtype in {"harm_loved", "help_enemy", "emotion_mismatch"}:
            return "emotional"
        return "coherence"
        
    def _empty_result(self, title: str, error: str) -> Dict:
        return {
            "story_title": title,
            "error_count": 0,
            "errors": [],
            "summary": {"by_category": {cat: 0 for cat in ERROR_CATEGORIES}},
            "_meta": {"error": error},
        }
        
    def _normalize_result(self, result: Dict, title: str) -> Dict:
        """Normalize LLM result structure."""
        result.setdefault("story_title", title)
        result.setdefault("errors", [])
        result["error_count"] = len(result.get("errors", []))
        
        by_category = {cat: 0 for cat in ERROR_CATEGORIES}
        
        for i, err in enumerate(result.get("errors", [])):
            err.setdefault("id", f"err_{i+1}")
            err.setdefault("category", "coherence")
            err.setdefault("description", "")
            err.setdefault("story_fragment", "")
            err.setdefault("conflicting_fragments", [])
            
            cat = err["category"].lower()
            if cat not in ERROR_CATEGORIES:
                cat = "coherence"
            err["category"] = cat
            by_category[cat] += 1
            
        result["summary"] = {"by_category": by_category}
        return result
        
    def analyze_books(self, stories: Dict, phase: str, output_subdir: str) -> Tuple[Dict, Dict]:
        """Analyze a set of books and return LLM and logic results."""
        llm_results = {}
        logic_results = {}
        
        output_dir = self.exp_dir / output_subdir
        (output_dir / "llm_results").mkdir(parents=True, exist_ok=True)
        (output_dir / "logic_results").mkdir(parents=True, exist_ok=True)
        
        for i, (title, story_data) in enumerate(stories.items(), 1):
            self.logger.info(f"  [{phase}] [{i}/{len(stories)}] {title}")
            
            content = story_data["content"]
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
            
            # LLM lint
            llm_result = self.run_llm_lint(title, content)
            llm_results[title] = llm_result
            (output_dir / "llm_results" / f"{safe_title}.json").write_text(
                json.dumps(llm_result, indent=2, ensure_ascii=False)
            )
            
            llm_count = llm_result.get("error_count", 0)
            
            # Logic lint
            logic_result = self.run_logic_lint(title, content)
            logic_results[title] = logic_result
            (output_dir / "logic_results" / f"{safe_title}.json").write_text(
                json.dumps(logic_result, indent=2, ensure_ascii=False)
            )
            
            logic_count = logic_result.get("error_count", 0)
            
            self.logger.info(f"    LLM: {llm_count} errors, Logic: {logic_count} errors")
            
        return llm_results, logic_results
        
    def build_baseline_signatures(self, llm_results: Dict, logic_results: Dict) -> Tuple[Set[str], Set[str]]:
        """Build signature sets from baseline results."""
        llm_sigs = set()
        logic_sigs = set()
        
        for results in llm_results.values():
            for err in results.get("errors", []):
                llm_sigs.add(compute_error_signature(err))
                
        for results in logic_results.values():
            for err in results.get("errors", []):
                logic_sigs.add(compute_error_signature(err))
                
        return llm_sigs, logic_sigs
        
    def filter_by_baseline(self, results: Dict, baseline_sigs: Set[str]) -> Dict:
        """Filter errors that appear in baseline (false positives)."""
        filtered = {}
        
        for title, result in results.items():
            filtered_errors = []
            filtered_count = 0
            
            for err in result.get("errors", []):
                sig = compute_error_signature(err)
                if sig not in baseline_sigs:
                    filtered_errors.append(err)
                else:
                    filtered_count += 1
                    
            # Rebuild result with filtered errors
            filtered_result = dict(result)
            filtered_result["errors"] = filtered_errors
            filtered_result["error_count"] = len(filtered_errors)
            filtered_result["_filtered_count"] = filtered_count
            
            # Recalculate category counts
            by_category = {cat: 0 for cat in ERROR_CATEGORIES}
            for err in filtered_errors:
                cat = err.get("category", "coherence")
                if cat in by_category:
                    by_category[cat] += 1
            filtered_result["summary"] = {"by_category": by_category}
            
            filtered[title] = filtered_result
            
        return filtered
        
    def run_kfold(self, books: List[str], k: int) -> Dict:
        """Run k-fold cross-validation."""
        from itertools import combinations
        
        results = {
            "k": k,
            "folds": [],
            "aggregate": {
                "llm_true_positives": 0,
                "logic_true_positives": 0,
                "llm_filtered": 0,
                "logic_filtered": 0,
            }
        }
        
        if k >= len(books):
            # Leave-one-out or all-but-one
            fold_size = 1
        else:
            fold_size = len(books) // k
            
        # Generate folds
        if k == 1:
            # Special case: all books for both train and test
            folds = [(books, books)]
        else:
            folds = []
            for i in range(k):
                test_start = i * fold_size
                test_end = test_start + fold_size if i < k - 1 else len(books)
                test_books = books[test_start:test_end]
                train_books = [b for b in books if b not in test_books]
                folds.append((train_books, test_books))
                
        for fold_idx, (train_books, test_books) in enumerate(folds):
            self.logger.info(f"  Fold {fold_idx + 1}/{len(folds)}: Train={train_books}, Test={test_books}")
            
            # Build baseline from train books (original)
            train_llm_sigs = set()
            train_logic_sigs = set()
            
            for title, result in self.baseline_llm.items():
                book = title.split("_Chapter_")[0]
                if book in train_books:
                    for err in result.get("errors", []):
                        train_llm_sigs.add(compute_error_signature(err))
                        
            for title, result in self.baseline_logic.items():
                book = title.split("_Chapter_")[0]
                if book in train_books:
                    for err in result.get("errors", []):
                        train_logic_sigs.add(compute_error_signature(err))
                        
            # Filter test results
            test_llm_tp = 0
            test_logic_tp = 0
            test_llm_filtered = 0
            test_logic_filtered = 0
            
            for title, result in self.test_llm.items():
                book = title.split("_Chapter_")[0]
                if book in test_books:
                    for err in result.get("errors", []):
                        sig = compute_error_signature(err)
                        if sig not in train_llm_sigs:
                            test_llm_tp += 1
                        else:
                            test_llm_filtered += 1
                            
            for title, result in self.test_logic.items():
                book = title.split("_Chapter_")[0]
                if book in test_books:
                    for err in result.get("errors", []):
                        sig = compute_error_signature(err)
                        if sig not in train_logic_sigs:
                            test_logic_tp += 1
                        else:
                            test_logic_filtered += 1
                            
            fold_result = {
                "fold": fold_idx + 1,
                "train_books": train_books,
                "test_books": test_books,
                "llm_true_positives": test_llm_tp,
                "logic_true_positives": test_logic_tp,
                "llm_filtered": test_llm_filtered,
                "logic_filtered": test_logic_filtered,
            }
            
            results["folds"].append(fold_result)
            results["aggregate"]["llm_true_positives"] += test_llm_tp
            results["aggregate"]["logic_true_positives"] += test_logic_tp
            results["aggregate"]["llm_filtered"] += test_llm_filtered
            results["aggregate"]["logic_filtered"] += test_logic_filtered
            
        # Average
        n_folds = len(folds)
        results["average"] = {
            "llm_true_positives": results["aggregate"]["llm_true_positives"] / n_folds,
            "logic_true_positives": results["aggregate"]["logic_true_positives"] / n_folds,
        }
        
        return results
        
    def run(self, original_dir: Path, modified_dir: Path, max_chapters: int, k_values: List[int]) -> Dict:
        """Run the complete experiment."""
        self.logger.info("=" * 70)
        self.logger.info("NARRATIVE EVALUATION EXPERIMENT WITH BASELINE FILTERING")
        self.logger.info("=" * 70)
        
        # Resolve model
        self.resolve_model()
        self.logger.info(f"LLM Model: {self.llm_model}")
        
        # Load stories
        self.logger.info(f"\nLoading stories (max {max_chapters} chapters per book)...")
        self.original_stories = self.load_stories(original_dir, max_chapters)
        self.modified_stories = self.load_stories(modified_dir, max_chapters)
        
        self.logger.info(f"  Original: {len(self.original_stories)} chapters")
        self.logger.info(f"  Modified: {len(self.modified_stories)} chapters")
        
        # Get book list
        books = sorted(set(s["book"] for s in self.original_stories.values()))
        self.logger.info(f"  Books: {books}")
        
        # Save stories
        stories_dir = self.exp_dir / "stories"
        stories_dir.mkdir(exist_ok=True)
        for title, data in {**self.original_stories, **self.modified_stories}.items():
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
            (stories_dir / f"{safe_title}.txt").write_text(data["content"])
            
        # Phase 1: Baseline from original books
        self.logger.info("\n" + "=" * 70)
        self.logger.info("PHASE 1: Establishing baseline from ORIGINAL books")
        self.logger.info("=" * 70)
        
        self.baseline_llm, self.baseline_logic = self.analyze_books(
            self.original_stories, "BASELINE", "baseline"
        )
        
        # Build baseline signatures
        self.baseline_llm_sigs, self.baseline_logic_sigs = self.build_baseline_signatures(
            self.baseline_llm, self.baseline_logic
        )
        
        self.logger.info(f"\nBaseline signatures: LLM={len(self.baseline_llm_sigs)}, Logic={len(self.baseline_logic_sigs)}")
        
        # Save baseline signatures
        (self.exp_dir / "baseline" / "signatures.json").write_text(json.dumps({
            "llm_signatures": list(self.baseline_llm_sigs),
            "logic_signatures": list(self.baseline_logic_sigs),
        }, indent=2))
        
        # Generate domain module
        domain_module = self.domain_gen.generate_module()
        (self.exp_dir / "domain_module.lp").write_text(domain_module)
        self.logger.info(f"Domain module generated: {len(domain_module)} bytes")
        
        # Phase 2: Test on modified books
        self.logger.info("\n" + "=" * 70)
        self.logger.info("PHASE 2: Testing on MODIFIED books")
        self.logger.info("=" * 70)
        
        self.test_llm, self.test_logic = self.analyze_books(
            self.modified_stories, "TEST", "test"
        )
        
        # Filter test results
        filtered_llm = self.filter_by_baseline(self.test_llm, self.baseline_llm_sigs)
        filtered_logic = self.filter_by_baseline(self.test_logic, self.baseline_logic_sigs)
        
        # Save filtered results
        (self.exp_dir / "test" / "filtered_llm.json").write_text(
            json.dumps(filtered_llm, indent=2, ensure_ascii=False)
        )
        (self.exp_dir / "test" / "filtered_logic.json").write_text(
            json.dumps(filtered_logic, indent=2, ensure_ascii=False)
        )
        
        # Calculate totals
        total_llm_tp = sum(r.get("error_count", 0) for r in filtered_llm.values())
        total_logic_tp = sum(r.get("error_count", 0) for r in filtered_logic.values())
        total_llm_filtered = sum(r.get("_filtered_count", 0) for r in filtered_llm.values())
        total_logic_filtered = sum(r.get("_filtered_count", 0) for r in filtered_logic.values())
        
        self.logger.info(f"\nTest results (after baseline filtering):")
        self.logger.info(f"  LLM: {total_llm_tp} true positives ({total_llm_filtered} filtered)")
        self.logger.info(f"  Logic: {total_logic_tp} true positives ({total_logic_filtered} filtered)")
        
        # Phase 3: K-fold cross-validation
        self.logger.info("\n" + "=" * 70)
        self.logger.info("PHASE 3: K-Fold Cross-Validation")
        self.logger.info("=" * 70)
        
        kfold_results = {}
        kfold_dir = self.exp_dir / "kfold_results"
        kfold_dir.mkdir(exist_ok=True)
        
        for k in k_values:
            self.logger.info(f"\nK={k} cross-validation:")
            kfold_results[f"k{k}"] = self.run_kfold(books, k)
            
            # Save k-fold result
            (kfold_dir / f"kfold_k{k}.json").write_text(
                json.dumps(kfold_results[f"k{k}"], indent=2)
            )
            
            avg = kfold_results[f"k{k}"]["average"]
            self.logger.info(f"  Average: LLM TP={avg['llm_true_positives']:.1f}, Logic TP={avg['logic_true_positives']:.1f}")
            
        # Compile summary
        summary = self._compile_summary(filtered_llm, filtered_logic, kfold_results, books)
        
        return summary
        
    def _compile_summary(self, filtered_llm: Dict, filtered_logic: Dict, 
                         kfold_results: Dict, books: List[str]) -> Dict:
        """Compile experiment summary."""
        # Count by category
        llm_by_cat = {cat: 0 for cat in ERROR_CATEGORIES}
        logic_by_cat = {cat: 0 for cat in ERROR_CATEGORIES}
        
        for result in filtered_llm.values():
            for cat, count in result.get("summary", {}).get("by_category", {}).items():
                if cat in llm_by_cat:
                    llm_by_cat[cat] += count
                    
        for result in filtered_logic.values():
            for cat, count in result.get("summary", {}).get("by_category", {}).items():
                if cat in logic_by_cat:
                    logic_by_cat[cat] += count
                    
        return {
            "experiment_info": {
                "model": self.llm_model,
                "books": books,
                "original_chapters": len(self.original_stories),
                "modified_chapters": len(self.modified_stories),
                "timestamp": datetime.now().isoformat(),
            },
            "baseline": {
                "llm_errors": sum(r.get("error_count", 0) for r in self.baseline_llm.values()),
                "logic_errors": sum(r.get("error_count", 0) for r in self.baseline_logic.values()),
                "llm_signatures": len(self.baseline_llm_sigs),
                "logic_signatures": len(self.baseline_logic_sigs),
            },
            "test_results": {
                "llm_true_positives": sum(r.get("error_count", 0) for r in filtered_llm.values()),
                "logic_true_positives": sum(r.get("error_count", 0) for r in filtered_logic.values()),
                "llm_filtered": sum(r.get("_filtered_count", 0) for r in filtered_llm.values()),
                "logic_filtered": sum(r.get("_filtered_count", 0) for r in filtered_logic.values()),
            },
            "by_category": {
                "llm": llm_by_cat,
                "logic": logic_by_cat,
            },
            "kfold": kfold_results,
        }
        
    def generate_report(self, summary: Dict) -> str:
        """Generate markdown report."""
        lines = [
            "# Narrative Evaluation Experiment Report",
            "",
            "## LLM vs Logic-Based Narrative Consistency Analysis",
            "",
            f"**Model:** {summary['experiment_info']['model']}",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Books:** {', '.join(summary['experiment_info']['books'])}",
            "",
            "---",
            "",
            "## 1. Methodology",
            "",
            "This experiment compares two approaches to narrative error detection:",
            "",
            "1. **LLM-Based Analysis**: Direct semantic analysis using large language models",
            "2. **Logic-Based Analysis**: Formal verification using Answer Set Programming (Clingo)",
            "",
            "### Baseline Filtering",
            "",
            "Errors detected in the **original books** are treated as false positives (baseline).",
            "These are filtered from the **modified books** results to identify true positives.",
            "",
            "---",
            "",
            "## 2. Baseline Results (Original Books)",
            "",
            f"- **Chapters analyzed:** {summary['experiment_info']['original_chapters']}",
            f"- **LLM errors (false positives):** {summary['baseline']['llm_errors']}",
            f"- **Logic errors (false positives):** {summary['baseline']['logic_errors']}",
            f"- **Unique LLM signatures:** {summary['baseline']['llm_signatures']}",
            f"- **Unique Logic signatures:** {summary['baseline']['logic_signatures']}",
            "",
            "---",
            "",
            "## 3. Test Results (Modified Books)",
            "",
            f"- **Chapters analyzed:** {summary['experiment_info']['modified_chapters']}",
            "",
            "### True Positives (Errors detected in modified, not in original)",
            "",
            f"| Method | True Positives | Filtered (FP) |",
            f"|--------|---------------|---------------|",
            f"| LLM    | {summary['test_results']['llm_true_positives']} | {summary['test_results']['llm_filtered']} |",
            f"| Logic  | {summary['test_results']['logic_true_positives']} | {summary['test_results']['logic_filtered']} |",
            "",
            "### Errors by Category",
            "",
            "| Category | LLM | Logic | Total |",
            "|----------|-----|-------|-------|",
        ]
        
        llm_cat = summary["by_category"]["llm"]
        logic_cat = summary["by_category"]["logic"]
        for cat in ERROR_CATEGORIES:
            total = llm_cat.get(cat, 0) + logic_cat.get(cat, 0)
            lines.append(f"| {cat.capitalize()} | {llm_cat.get(cat, 0)} | {logic_cat.get(cat, 0)} | {total} |")
            
        lines.extend([
            "",
            "---",
            "",
            "## 4. K-Fold Cross-Validation",
            "",
        ])
        
        for k_key, k_result in summary.get("kfold", {}).items():
            k = k_result.get("k", "?")
            avg = k_result.get("average", {})
            lines.extend([
                f"### K={k}",
                "",
                f"- **Average LLM True Positives:** {avg.get('llm_true_positives', 0):.1f}",
                f"- **Average Logic True Positives:** {avg.get('logic_true_positives', 0):.1f}",
                "",
            ])
            
        lines.extend([
            "---",
            "",
            "## 5. Category Descriptions",
            "",
        ])
        
        for cat, desc in CATEGORY_DESCRIPTIONS.items():
            lines.append(f"- **{cat.capitalize()}**: {desc}")
            
        return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run narrative evaluation experiment with baseline filtering"
    )
    parser.add_argument("--name", default="baseline_exp",
                        help="Experiment name prefix")
    parser.add_argument("--original-dir", default="original_books",
                        help="Directory with original books (baseline)")
    parser.add_argument("--modified-dir", default="modified_books",
                        help="Directory with modified books (test)")
    parser.add_argument("--chapters-per-book", type=int, default=2,
                        help="Max chapters to process per book")
    parser.add_argument("--k-values", default="1,2,3,4",
                        help="K values for cross-validation (comma-separated)")
    parser.add_argument("--llm-base-url", default="http://localhost:8080/v1",
                        help="LLM API base URL")
    parser.add_argument("--llm-model", default="auto",
                        help="LLM model name (auto to detect)")
    parser.add_argument("--llm-timeout", type=int, default=600,
                        help="LLM timeout in seconds")
    parser.add_argument("--output-dir", default="experiments",
                        help="Output directory")
    
    args = parser.parse_args()
    
    # Parse k values
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    
    # Create experiment directory
    start_time = datetime.now()
    exp_id = uuid.uuid4().hex[:8]
    exp_name = f"{args.name}-{start_time.strftime('%Y%m%d_%H%M%S')}-pending-{exp_id}"
    exp_dir = Path(args.output_dir) / exp_name
    
    # Create directories
    for subdir in ["logs", "stories", "baseline/llm_results", "baseline/logic_results",
                   "test/llm_results", "test/logic_results", "kfold_results"]:
        (exp_dir / subdir).mkdir(parents=True, exist_ok=True)
        
    # Save config
    config = {
        "name": args.name,
        "original_dir": args.original_dir,
        "modified_dir": args.modified_dir,
        "chapters_per_book": args.chapters_per_book,
        "k_values": k_values,
        "llm_base_url": args.llm_base_url,
        "llm_model": args.llm_model,
        "llm_timeout": args.llm_timeout,
        "start_time": start_time.isoformat(),
    }
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2))
    
    # Initialize logger
    logger = Logger(exp_dir)
    logger.info(f"Experiment: {exp_name}")
    logger.info(f"Output: {exp_dir}")
    
    # Run experiment
    experiment = BaselineExperiment(exp_dir, config, logger)
    
    try:
        summary = experiment.run(
            original_dir=REPO_ROOT / args.original_dir,
            modified_dir=REPO_ROOT / args.modified_dir,
            max_chapters=args.chapters_per_book,
            k_values=k_values,
        )
        
        # Save summary
        (exp_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        
        # Generate and save report
        report = experiment.generate_report(summary)
        (exp_dir / "report.md").write_text(report)
        
        # Rename directory with end time
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        final_name = f"{args.name}-{start_time.strftime('%Y%m%d_%H%M%S')}-{end_time.strftime('%Y%m%d_%H%M%S')}-{exp_id}"
        final_dir = exp_dir.parent / final_name
        exp_dir.rename(final_dir)
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("EXPERIMENT COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Output: {final_dir}")
        logger.info(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        logger.info(f"Report: {final_dir / 'report.md'}")
        
        print(f"\nExperiment complete: {final_dir}")
        
    except Exception as e:
        logger.error(f"Experiment failed: {e}\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
