#!/usr/bin/env python3
"""
run_comprehensive_experiment.py - Enhanced Narrative Evaluation Experiment
============================================================================

# Ensure user site-packages are in path for clingo
import sys
import site
site.ENABLE_USER_SITE = True
if site.getusersitepackages() not in sys.path:
    sys.path.insert(0, site.getusersitepackages())

This script runs a comprehensive experiment comparing LLM-based vs Logic-based 
(Clingo) narrative evaluation across 5 error categories:

1. CAUSALITY - Chekhov's gun, cause-effect chains, unmotivated actions
2. COHERENCE - Semantic correctness, physical impossibility, state contradictions
3. TEMPORAL  - Time intervals, ordering violations, impossible durations
4. LOCATION  - Spatial constraints, ubiquity, teleportation
5. EMOTIONAL - Character motivations, relationship consistency, behavioral coherence

ARCHITECTURE:
- General rules module (rules/general.lp): Domain-independent abstract rules
- Domain-specific module: Generated per experiment based on story analysis

OUTPUT STRUCTURE:
experiments/<name>-<start>-<end>-<uuid>/
├── config.json           # Experiment configuration
├── stories/              # Each story chapter as individual file
├── llm_results/          # LLM lint JSON per story with detailed errors
├── logic_results/        # Logic lint JSON per story
├── structured_json/      # Structured story JSON
├── asp_facts/            # Generated ASP facts
├── domain_module.lp      # Generated domain-specific rules
├── llm_call_log.jsonl    # All LLM calls with timestamps (JSON lines)
├── logs/                 # Timestamped execution logs
├── report.md             # Comprehensive markdown report for academic paper
└── summary.json          # Machine-readable summary

Author: Research Project - Narrative Evaluation Comparison
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import urllib.request
import urllib.error

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from json_to_asp import json_to_asp, sanitize_symbol
from llm_structurer import structure_story, extract_json, strip_think

# =============================================================================
# CONSTANTS
# =============================================================================

ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]

CATEGORY_DESCRIPTIONS = {
    "causality": "Violations of cause-effect relationships (Chekhov's gun, missing causes, unmotivated actions)",
    "coherence": "Semantic and logical inconsistencies (physical impossibility, dead agents, state contradictions)",
    "temporal": "Time-related violations (impossible ordering, duration errors, overlapping conflicts)",
    "location": "Spatial violations (ubiquity, impossible reach, teleportation without travel)",
    "emotional": "Character motivation and relationship violations (harming loved ones, helping enemies)",
}

# Enhanced LLM lint prompt with detailed category analysis
LLM_LINT_PROMPT = """You are a narrative consistency analyzer for academic research.
Analyze this story CAREFULLY for errors in 5 categories. Be thorough but precise - only report actual errors.

## ERROR CATEGORIES

### 1. CAUSALITY (cause-effect violations)
- **Chekhov's gun**: Significant objects/elements introduced but never used narratively
- **Missing cause**: Major events without adequate explanation or buildup
- **Broken chain**: Effects without causes, or causes without effects
- **Unmotivated action**: Characters act without clear motivation

### 2. COHERENCE (semantic/logical violations)
- **Physical impossibility**: Actions impossible given physical constraints
- **Dead agent**: Character acts after being killed
- **State contradiction**: Entity in contradictory state (door both open and closed)
- **Type violation**: Wrong category (eating non-food, reading unreadable objects)

### 3. TEMPORAL (time-related violations)
- **Impossible order**: Events in wrong sequence given story logic
- **Duration violation**: Action takes impossible time (instant long-distance travel)
- **Overlap conflict**: Character doing incompatible simultaneous activities
- **Anachronism**: Time reference inconsistency

### 4. LOCATION (spatial violations)
- **Ubiquity**: Character in two places simultaneously
- **Impossible reach**: Interacting with distant objects without being there
- **Teleportation**: Instant movement between distant locations without travel
- **Containment**: Being inside something impossible

### 5. EMOTIONAL (relationship/motivation violations)
- **Harm loved**: Hurting someone loved without justification or character arc
- **Help enemy**: Helping someone hated without strategic motivation
- **Trust betrayer**: Trusting someone proven untrustworthy without redemption arc
- **Emotion mismatch**: Behavior contradicts established emotional state

## REQUIREMENTS FOR EACH ERROR

For EVERY error, you MUST provide:
1. **category**: One of [causality, coherence, temporal, location, emotional]
2. **type**: Specific violation type (e.g., "chekhov_gun", "ubiquity", "dead_agent")
3. **description**: Clear, detailed explanation of why this is an error
4. **story_fragment**: The EXACT verbatim text from the story showing the error
5. **conflicting_fragments**: Other verbatim quotes that conflict (if applicable, use [])
6. **severity**: low (minor issue) | medium (noticeable problem) | high (major inconsistency)

## IMPORTANT GUIDELINES

- ONLY report actual narrative errors, not stylistic choices
- Quote EXACT text from the story - do not paraphrase
- Consider fantasy/magic rules as stated in the story's world
- If time/location is fuzzy but plausible, don't report it as an error
- Focus on verifiable inconsistencies that a reader would notice

Return ONLY valid JSON (no markdown, no explanation):
{{
  "story_title": "extracted or inferred title",
  "error_count": integer,
  "errors": [
    {{
      "id": "err_1",
      "category": "causality|coherence|temporal|location|emotional",
      "type": "specific_type_snake_case",
      "description": "Detailed explanation of the error",
      "story_fragment": "exact verbatim quote from story",
      "conflicting_fragments": ["other quote 1", "other quote 2"],
      "severity": "low|medium|high"
    }}
  ],
  "summary": {{
    "by_category": {{
      "causality": 0,
      "coherence": 0,
      "temporal": 0,
      "location": 0,
      "emotional": 0
    }},
    "by_severity": {{
      "low": 0,
      "medium": 0,
      "high": 0
    }}
  }},
  "analysis_notes": "Brief note about the story's overall consistency quality"
}}

If NO errors found, return {{"story_title": "...", "error_count": 0, "errors": [], "summary": {{...all zeros...}}, "analysis_notes": "Story appears consistent"}}

Story to analyze:
\"\"\"
{story}
\"\"\"
"""


# =============================================================================
# LOGGING UTILITIES
# =============================================================================

class ExperimentLogger:
    """
    Comprehensive logger for experiment tracking.
    
    Logs to:
    - stderr for console output
    - experiment log file
    - LLM call log (JSON lines format)
    """
    
    def __init__(self, exp_dir: Path):
        self.exp_dir = exp_dir
        self.log_file = exp_dir / "logs" / "experiment.log"
        self.llm_log_file = exp_dir / "llm_call_log.jsonl"
        self.start_time = datetime.now()
        
    def log(self, msg: str, level: str = "INFO") -> None:
        """Log message to console and file."""
        timestamp = datetime.now().isoformat()
        formatted = f"[{timestamp}] [{level}] {msg}"
        sys.stderr.write(formatted + "\n")
        sys.stderr.flush()
        with open(self.log_file, "a") as f:
            f.write(formatted + "\n")
            
    def log_llm_call(self, call_data: Dict) -> None:
        """Log LLM API call details to JSON lines file."""
        call_data["timestamp"] = datetime.now().isoformat()
        call_data["elapsed_since_start"] = (datetime.now() - self.start_time).total_seconds()
        with open(self.llm_log_file, "a") as f:
            f.write(json.dumps(call_data) + "\n")
            
    def info(self, msg: str) -> None:
        self.log(msg, "INFO")
        
    def error(self, msg: str) -> None:
        self.log(msg, "ERROR")
        
    def warning(self, msg: str) -> None:
        self.log(msg, "WARNING")


# =============================================================================
# DOMAIN GENERATOR (Enhanced)
# =============================================================================

class EnhancedDomainGenerator:
    """
    Generates domain-specific ASP rules from analyzed stories.
    
    Extracts:
    - Character relationships (loves, hates, fears, trusts)
    - Location geography and distances
    - Emotional states over time
    - Significant events that need causation
    - Initial events (story starters)
    - Custom causal rules
    """
    
    def __init__(self, logger: ExperimentLogger):
        self.logger = logger
        self.locations: set = set()
        self.characters: set = set()
        self.relationships: List[Tuple[str, str, str]] = []
        self.emotional_states: List[Tuple[str, str, str]] = []
        self.location_distances: List[Tuple[str, str]] = []
        self.significant_events: set = set()
        self.initial_events: set = set()
        self.decorative_objects: set = set()
        self.all_events: set = set()
        
    def add_story_data(self, structured_data: Dict[str, Any], story_name: str) -> None:
        """Process structured story data and extract domain knowledge."""
        self.logger.info(f"Extracting domain knowledge from: {story_name}")
        
        entities = structured_data.get("entities", {})
        
        # Extract characters
        for ch in entities.get("characters", []):
            char_id = sanitize_symbol(ch.get("id", ""))
            if char_id:
                self.characters.add(char_id)
                
        # Extract locations
        for loc in entities.get("locations", []):
            loc_id = sanitize_symbol(loc.get("id", ""))
            if loc_id:
                self.locations.add(loc_id)
                
        # Extract relationships
        for rel in structured_data.get("relationships", []):
            rel_type = sanitize_symbol(rel.get("type", ""))
            from_char = sanitize_symbol(rel.get("from", ""))
            to_char = sanitize_symbol(rel.get("to", ""))
            if rel_type and from_char and to_char:
                self.relationships.append((rel_type, from_char, to_char))
                
        # Mark first event as initial (doesn't need prior cause)
        events = structured_data.get("events", [])
        for i, ev in enumerate(events):
            ev_id = sanitize_symbol(ev.get("id", ""))
            if ev_id:
                self.all_events.add(ev_id)
                if i == 0:
                    self.initial_events.add(ev_id)
                    
        # Extract emotional states from fluents
        for fl in structured_data.get("fluents", []):
            fl_id = fl.get("id", "")
            emotions = ["happy", "sad", "angry", "afraid", "calm", "excited", 
                       "jealous", "anxious", "joyful", "depressed"]
            for emotion in emotions:
                if emotion in fl_id.lower():
                    import re
                    match = re.match(r"(\w+)\((\w+)\)", fl_id)
                    if match:
                        char = sanitize_symbol(match.group(2))
                        time_info = fl.get("time", {})
                        start = sanitize_symbol(time_info.get("start", "t0"))
                        self.emotional_states.append((char, emotion, start))
                    break
                    
    def generate_asp(self) -> str:
        """Generate the complete domain-specific ASP module."""
        lines = []
        
        lines.append("% " + "=" * 77)
        lines.append("% DOMAIN-SPECIFIC MODULE (Auto-generated for this experiment)")
        lines.append("% " + "=" * 77)
        lines.append("%")
        lines.append("% This file contains domain-specific facts and rules extracted from")
        lines.append("% the stories being analyzed. Used with rules/general.lp.")
        lines.append("%")
        lines.append(f"% Generated: {datetime.now().isoformat()}")
        lines.append(f"% Characters: {len(self.characters)}")
        lines.append(f"% Locations: {len(self.locations)}")
        lines.append(f"% Relationships: {len(self.relationships)}")
        lines.append(f"% Events: {len(self.all_events)}")
        lines.append("% " + "=" * 77)
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
            
        # Initial events (don't require prior cause)
        if self.initial_events:
            lines.append("% ----- Initial Events (story starters) -----")
            for event in sorted(self.initial_events):
                lines.append(f"initial_event({event}).")
            lines.append("")
            
        # Location distances (locations in different stories are distant by default)
        if len(self.locations) > 1:
            lines.append("% ----- Location Distance Defaults -----")
            lines.append("% Different named locations are assumed distant unless specified")
            locs = sorted(self.locations)
            for i, loc1 in enumerate(locs):
                for loc2 in locs[i+1:]:
                    # Only mark truly different locations as distant
                    if loc1 != loc2 and not (loc1 in loc2 or loc2 in loc1):
                        lines.append(f"% distant({loc1}, {loc2}).  % Uncomment if needed")
            lines.append("")
            
        # Default causal rules (common-sense)
        lines.append("% ----- Default Causal Rules -----")
        lines.append("% Standard cause-effect relationships for common actions")
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
        lines.append("% Life/death")
        lines.append("causes(kill, pos, dead, patient).")
        lines.append("causes(die, pos, dead, agent).")
        lines.append("")
        lines.append("% Sleep/wake")
        lines.append("causes(sleep, pos, asleep, agent).")
        lines.append("causes(wake, neg, asleep, agent).")
        lines.append("precondition(wake, pos, asleep, agent).")
        lines.append("")
        lines.append("% Possession")
        lines.append("causes(take, pos, has, agent).")
        lines.append("causes(give, neg, has, agent).")
        lines.append("causes(receive, pos, has, agent).")
        lines.append("causes(drop, neg, has, agent).")
        lines.append("")
        
        lines.append("% " + "=" * 77)
        lines.append("% END OF DOMAIN MODULE")
        lines.append("% " + "=" * 77)
        
        return "\n".join(lines) + "\n"


# =============================================================================
# EXPERIMENT RUNNER
# =============================================================================

class ComprehensiveExperimentRunner:
    """
    Main experiment runner class.
    
    Orchestrates:
    1. Story loading and organization
    2. LLM-based linting with detailed error categorization
    3. Logic-based linting with Clingo
    4. Domain module generation
    5. Report generation for academic paper
    """
    
    def __init__(
        self,
        exp_dir: Path,
        llm_base_url: str = "http://localhost:8080/v1",
        llm_timeout: int = 600,
        llm_model: str = "auto",
    ):
        self.exp_dir = exp_dir
        self.llm_base_url = llm_base_url
        self.llm_timeout = llm_timeout
        self.llm_model = llm_model
        
        # Create logger
        self.logger = ExperimentLogger(exp_dir)
        
        # Domain generator
        self.domain_gen = EnhancedDomainGenerator(self.logger)
        
        # Results storage
        self.stories: Dict[str, Dict[str, Any]] = {}  # {title: {content, source_file, book}}
        self.llm_results: Dict[str, Dict] = {}
        self.logic_results: Dict[str, Dict] = {}
        self.structured_data: Dict[str, Dict] = {}
        
        # Timing
        self.story_timings: Dict[str, Dict] = {}
        
        # Resolve model
        self._resolve_model()
        
    def _resolve_model(self) -> None:
        """Resolve auto model ID."""
        if self.llm_model == "auto":
            try:
                url = self.llm_base_url.rstrip("/") + "/models"
                with urllib.request.urlopen(url, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = data.get("data", [])
                    if models:
                        self.llm_model = models[0].get("id", "auto")
                        self.logger.info(f"Resolved model: {self.llm_model}")
            except Exception as e:
                self.logger.warning(f"Could not resolve model: {e}")
                
    def load_stories_from_directory(self, books_dir: Path, max_chapters_per_book: int = 3) -> None:
        """
        Load stories from processed_books directory structure.
        
        Each subdirectory is a book, each file is a chapter.
        """
        self.logger.info(f"Loading stories from: {books_dir}")
        
        for book_dir in sorted(books_dir.iterdir()):
            if not book_dir.is_dir():
                continue
                
            book_name = book_dir.name
            chapter_files = sorted(book_dir.glob("*.txt"))
            
            # Limit chapters per book for reasonable experiment size
            for i, chapter_file in enumerate(chapter_files[:max_chapters_per_book]):
                chapter_num = chapter_file.stem
                title = f"{book_name}_Chapter_{chapter_num}"
                content = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                # Skip very short chapters
                if len(content.strip()) < 500:
                    self.logger.warning(f"Skipping short chapter: {title} ({len(content)} chars)")
                    continue
                    
                # Truncate very long chapters to avoid LLM context limits
                if len(content) > 15000:
                    content = content[:15000] + "\n\n[... chapter truncated for analysis ...]"
                    
                self.stories[title] = {
                    "content": content,
                    "source_file": str(chapter_file),
                    "book": book_name,
                    "chapter": chapter_num,
                    "original_length": len(chapter_file.read_text(encoding="utf-8", errors="replace")),
                }
                
                # Save story to experiment folder
                safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
                story_path = self.exp_dir / "stories" / f"{safe_title}.txt"
                story_path.write_text(content, encoding="utf-8")
                
        self.logger.info(f"Loaded {len(self.stories)} story chapters from {len(set(s['book'] for s in self.stories.values()))} books")
        
    def call_llm(self, prompt: str, purpose: str, max_tokens: int = 4096) -> Tuple[str, float]:
        """Call LLM API with logging."""
        start_time = time.time()
        
        url = self.llm_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.llm_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": "You are a narrative consistency analyzer. Return only valid JSON."},
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
            
            # Log the call
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
                "prompt_length": len(prompt),
                "elapsed_seconds": elapsed,
                "status": "error",
                "error": str(e),
            })
            raise
            
    def run_llm_lint(self, title: str, content: str) -> Dict[str, Any]:
        """Run LLM-based linting with detailed error categorization."""
        self.logger.info(f"Running LLM lint on: {title}")
        start_time = time.time()
        
        prompt = LLM_LINT_PROMPT.format(story=content.strip())
        
        try:
            response, api_elapsed = self.call_llm(prompt, f"llm_lint:{title}", max_tokens=8192)
            
            # Extract JSON
            raw_json = extract_json(response)
            if raw_json is None:
                raw_json = extract_json(strip_think(response))
            if raw_json is None:
                self.logger.error(f"Failed to extract JSON for {title}")
                return self._empty_llm_result(title, "JSON extraction failed")
                
            result = json.loads(raw_json)
            
            # Validate and normalize
            result = self._normalize_llm_result(result, title)
            
            elapsed = time.time() - start_time
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "api_elapsed_seconds": api_elapsed,
                "timestamp": datetime.now().isoformat(),
                "model": self.llm_model,
                "story_length": len(content),
            }
            
            self.logger.info(f"LLM lint completed for {title}: {result.get('error_count', 0)} errors in {elapsed:.1f}s")
            return result
            
        except Exception as e:
            self.logger.error(f"LLM lint failed for {title}: {e}")
            return self._empty_llm_result(title, str(e))
            
    def _empty_llm_result(self, title: str, error: str) -> Dict:
        """Return empty result structure for failed LLM lint."""
        return {
            "story_title": title,
            "error_count": 0,
            "errors": [],
            "summary": {
                "by_category": {cat: 0 for cat in ERROR_CATEGORIES},
                "by_severity": {"low": 0, "medium": 0, "high": 0},
            },
            "analysis_notes": f"Analysis failed: {error}",
            "_meta": {"error": error},
        }
        
    def _normalize_llm_result(self, result: Dict, title: str) -> Dict:
        """Normalize and validate LLM result structure."""
        # Ensure all required fields exist
        result.setdefault("story_title", title)
        result.setdefault("errors", [])
        result.setdefault("error_count", len(result.get("errors", [])))
        
        # Recalculate counts from actual errors
        errors = result.get("errors", [])
        result["error_count"] = len(errors)
        
        # Build summary
        by_category = {cat: 0 for cat in ERROR_CATEGORIES}
        by_severity = {"low": 0, "medium": 0, "high": 0}
        
        for i, err in enumerate(errors):
            # Normalize error structure
            err.setdefault("id", f"err_{i+1}")
            err.setdefault("category", "coherence")
            err.setdefault("type", "unknown")
            err.setdefault("description", "No description")
            err.setdefault("story_fragment", "")
            err.setdefault("conflicting_fragments", [])
            err.setdefault("severity", "medium")
            
            # Normalize category
            cat = err["category"].lower()
            if cat not in ERROR_CATEGORIES:
                cat = "coherence"
            err["category"] = cat
            by_category[cat] += 1
            
            # Normalize severity
            sev = err["severity"].lower()
            if sev not in by_severity:
                sev = "medium"
            err["severity"] = sev
            by_severity[sev] += 1
            
        result["summary"] = {
            "by_category": by_category,
            "by_severity": by_severity,
        }
        
        return result
        
    def run_logic_lint(self, title: str, content: str) -> Dict[str, Any]:
        """Run logic-based linting using Clingo."""
        self.logger.info(f"Running Logic lint on: {title}")
        start_time = time.time()
        
        try:
            # Step 1: Structure the story
            struct_start = time.time()
            
            # Use simpler prompt for structuring
            struct_prompt_path = "prompts/structure_prompt.txt"
            if not (REPO_ROOT / struct_prompt_path).exists():
                struct_prompt_path = "prompts/structure_prompt_documented.txt"
                
            struct_result = structure_story(
                content,
                prompt_path=struct_prompt_path,
                model=self.llm_model,
                base_url=self.llm_base_url,
                timeout=self.llm_timeout,
                max_tokens=16384,
                return_details=True,
            )
            
            structured_data = struct_result["parsed"]
            self.structured_data[title] = structured_data
            struct_elapsed = time.time() - struct_start
            
            # Log structuring call
            self.logger.log_llm_call({
                "purpose": f"structure:{title}",
                "model": self.llm_model,
                "elapsed_seconds": struct_elapsed,
                "status": "success",
            })
            
            # Save structured JSON
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
            json_path = self.exp_dir / "structured_json" / f"{safe_title}.json"
            json_path.write_text(json.dumps(structured_data, indent=2))
            
            # Add to domain generator
            self.domain_gen.add_story_data(structured_data, title)
            
            # Step 2: Convert to ASP facts
            asp_facts = json_to_asp(structured_data)
            facts_path = self.exp_dir / "asp_facts" / f"{safe_title}.lp"
            facts_path.write_text(asp_facts)
            
            # Step 3: Run Clingo
            violations = self._run_clingo(asp_facts, title)
            
            # Step 4: Categorize violations
            result = self._categorize_logic_violations(violations, structured_data)
            
            elapsed = time.time() - start_time
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "structuring_seconds": struct_elapsed,
                "timestamp": datetime.now().isoformat(),
                "asp_facts_lines": len(asp_facts.split("\n")),
                "events_count": len(structured_data.get("events", [])),
                "characters_count": len(structured_data.get("entities", {}).get("characters", [])),
            }
            
            self.logger.info(f"Logic lint completed for {title}: {result.get('error_count', 0)} violations in {elapsed:.1f}s")
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"Logic lint failed for {title}: {e}\n{traceback.format_exc()}")
            return {
                "error_count": 0,
                "errors": [],
                "summary": {"by_category": {cat: 0 for cat in ERROR_CATEGORIES}},
                "_meta": {"error": str(e), "elapsed_seconds": elapsed},
            }
            
    def _run_clingo(self, asp_facts: str, title: str) -> List[Tuple]:
        """Run Clingo solver and return violations."""
        import clingo
        
        violations = []
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(asp_facts)
            facts_path = f.name
            
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load general rules
            general_path = REPO_ROOT / "rules" / "general.lp"
            if general_path.exists():
                ctl.load(str(general_path))
            else:
                # Fall back to base.lp
                base_path = REPO_ROOT / "rules" / "base.lp"
                if base_path.exists():
                    ctl.load(str(base_path))
                    
            # Load domain module if generated
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
                            
        except Exception as e:
            self.logger.error(f"Clingo failed for {title}: {e}")
            
        finally:
            os.unlink(facts_path)
            
        return violations
        
    def _categorize_logic_violations(self, violations: List[Tuple], 
                                      structured_data: Dict) -> Dict[str, Any]:
        """Categorize violations by error category."""
        errors = []
        category_counts = {cat: 0 for cat in ERROR_CATEGORIES}
        
        # Build event lookup for descriptions
        event_lookup = {}
        for ev in structured_data.get("events", []):
            ev_id = sanitize_symbol(ev.get("id", ""))
            event_lookup[ev_id] = ev
            
        for i, v in enumerate(violations):
            # Parse violation format
            if len(v) >= 4:
                category = v[0].lower()
                vtype = v[1]
                event = v[2]
                detail = v[3]
            elif len(v) >= 2:
                vtype = v[0]
                event = v[1]
                detail = v[2] if len(v) > 2 else ""
                category = self._infer_category(vtype)
            else:
                continue
                
            # Normalize category
            if category not in ERROR_CATEGORIES:
                category = self._infer_category(vtype)
                
            if category in category_counts:
                category_counts[category] += 1
                
            # Get event details for description
            ev_info = event_lookup.get(event.replace('"', ''), {})
            ev_type = ev_info.get("type", "unknown")
            ev_agent = ev_info.get("agent", "unknown")
            
            description = f"Violation: {vtype}"
            if ev_type != "unknown":
                description += f" - Event '{ev_type}' by {ev_agent}"
            if detail:
                description += f" ({detail})"
                
            errors.append({
                "id": f"logic_{i+1}",
                "category": category,
                "type": str(vtype),
                "event": str(event),
                "detail": str(detail),
                "description": description,
                "event_info": ev_info,
            })
            
        return {
            "error_count": len(errors),
            "errors": errors,
            "summary": {"by_category": category_counts},
            "raw_violations": [list(v) for v in violations],
        }
        
    def _infer_category(self, vtype: str) -> str:
        """Infer error category from violation type."""
        vtype = str(vtype).lower()
        
        location_types = {"ubiquity", "proximity_required", "impossible_travel", "teleportation"}
        temporal_types = {"circular_time", "negative_duration", "explicit_order_violated", "overlap"}
        causality_types = {"chekhov_gun", "uncaused_event", "effect_without_cause", 
                          "precondition_missing", "precondition_not_met", "precondition_violated"}
        emotional_types = {"harm_loved", "help_enemy", "approach_feared", "misplaced_trust", 
                          "state_action_mismatch"}
        coherence_types = {"dead_agent", "non_edible_food", "physical_impossibility", 
                          "focus_overlap"}
        
        if vtype in location_types:
            return "location"
        if vtype in temporal_types:
            return "temporal"
        if vtype in causality_types:
            return "causality"
        if vtype in emotional_types:
            return "emotional"
        if vtype in coherence_types:
            return "coherence"
            
        return "coherence"
        
    def generate_domain_module(self) -> None:
        """Generate domain-specific ASP module from all structured stories."""
        self.logger.info("Generating domain-specific ASP module...")
        
        asp_content = self.domain_gen.generate_asp()
        domain_path = self.exp_dir / "domain_module.lp"
        domain_path.write_text(asp_content)
        
        self.logger.info(f"Domain module generated: {len(asp_content)} bytes")
        
    def run_experiment(self) -> Dict[str, Any]:
        """Run the complete experiment."""
        self.logger.info("=" * 60)
        self.logger.info("STARTING NARRATIVE EVALUATION EXPERIMENT")
        self.logger.info("=" * 60)
        self.logger.info(f"Stories to process: {len(self.stories)}")
        self.logger.info(f"LLM model: {self.llm_model}")
        self.logger.info(f"LLM endpoint: {self.llm_base_url}")
        
        # Phase 1: Structure all stories and generate domain module
        self.logger.info("")
        self.logger.info("PHASE 1: Structuring stories and building domain knowledge")
        self.logger.info("-" * 60)
        
        for i, (title, story_data) in enumerate(self.stories.items(), 1):
            self.logger.info(f"[{i}/{len(self.stories)}] Structuring: {title}")
            try:
                struct_prompt_path = "prompts/structure_prompt.txt"
                if not (REPO_ROOT / struct_prompt_path).exists():
                    struct_prompt_path = "prompts/structure_prompt_documented.txt"
                    
                struct_result = structure_story(
                    story_data["content"],
                    prompt_path=struct_prompt_path,
                    model=self.llm_model,
                    base_url=self.llm_base_url,
                    timeout=self.llm_timeout,
                    max_tokens=16384,
                    return_details=True,
                )
                
                self.structured_data[title] = struct_result["parsed"]
                self.domain_gen.add_story_data(struct_result["parsed"], title)
                
                # Save
                safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
                json_path = self.exp_dir / "structured_json" / f"{safe_title}.json"
                json_path.write_text(json.dumps(struct_result["parsed"], indent=2))
                
                # Save ASP facts
                asp_facts = json_to_asp(struct_result["parsed"])
                facts_path = self.exp_dir / "asp_facts" / f"{safe_title}.lp"
                facts_path.write_text(asp_facts)
                
            except Exception as e:
                self.logger.error(f"Failed to structure {title}: {e}")
                
        # Generate domain module
        self.generate_domain_module()
        
        # Phase 2: Run both linters
        self.logger.info("")
        self.logger.info("PHASE 2: Running linters (LLM and Logic)")
        self.logger.info("-" * 60)
        
        for i, (title, story_data) in enumerate(self.stories.items(), 1):
            self.logger.info(f"[{i}/{len(self.stories)}] Analyzing: {title}")
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
            
            story_start = time.time()
            
            # LLM lint
            llm_result = self.run_llm_lint(title, story_data["content"])
            self.llm_results[title] = llm_result
            llm_path = self.exp_dir / "llm_results" / f"{safe_title}.json"
            llm_path.write_text(json.dumps(llm_result, indent=2, ensure_ascii=False))
            
            # Logic lint
            logic_result = self._run_logic_lint_from_structured(title)
            self.logic_results[title] = logic_result
            logic_path = self.exp_dir / "logic_results" / f"{safe_title}.json"
            logic_path.write_text(json.dumps(logic_result, indent=2, ensure_ascii=False))
            
            story_elapsed = time.time() - story_start
            self.story_timings[title] = {
                "total_seconds": story_elapsed,
                "llm_errors": llm_result.get("error_count", 0),
                "logic_errors": logic_result.get("error_count", 0),
            }
            
        return self._compile_summary()
        
    def _run_logic_lint_from_structured(self, title: str) -> Dict[str, Any]:
        """Run logic lint using pre-structured data."""
        start_time = time.time()
        
        if title not in self.structured_data:
            return {
                "error_count": 0,
                "errors": [],
                "summary": {"by_category": {cat: 0 for cat in ERROR_CATEGORIES}},
                "_meta": {"error": "No structured data available"},
            }
            
        try:
            structured_data = self.structured_data[title]
            asp_facts = json_to_asp(structured_data)
            violations = self._run_clingo(asp_facts, title)
            result = self._categorize_logic_violations(violations, structured_data)
            
            elapsed = time.time() - start_time
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat(),
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Logic lint failed for {title}: {e}")
            return {
                "error_count": 0,
                "errors": [],
                "summary": {"by_category": {cat: 0 for cat in ERROR_CATEGORIES}},
                "_meta": {"error": str(e)},
            }
            
    def _compile_summary(self) -> Dict[str, Any]:
        """Compile experiment summary."""
        # Calculate timing statistics
        total_time = sum(t.get("total_seconds", 0) for t in self.story_timings.values())
        avg_time = total_time / max(1, len(self.story_timings))
        
        # Per-book timing
        book_timings: Dict[str, Dict] = {}
        for title, timing in self.story_timings.items():
            book = self.stories.get(title, {}).get("book", "unknown")
            if book not in book_timings:
                book_timings[book] = {"total_seconds": 0, "chapters": 0, "llm_errors": 0, "logic_errors": 0}
            book_timings[book]["total_seconds"] += timing.get("total_seconds", 0)
            book_timings[book]["chapters"] += 1
            book_timings[book]["llm_errors"] += timing.get("llm_errors", 0)
            book_timings[book]["logic_errors"] += timing.get("logic_errors", 0)
            
        summary = {
            "experiment_info": {
                "total_stories": len(self.stories),
                "chapters_per_book": len(self.stories) // max(1, len(set(s["book"] for s in self.stories.values()))),
                "books_analyzed": list(set(s["book"] for s in self.stories.values())),
                "llm_model": self.llm_model,
                "timestamp": datetime.now().isoformat(),
            },
            "timing": {
                "total_experiment_seconds": total_time,
                "average_per_story_seconds": avg_time,
                "per_book": book_timings,
            },
            "totals": {
                "llm_total_errors": sum(r.get("error_count", 0) for r in self.llm_results.values()),
                "logic_total_errors": sum(r.get("error_count", 0) for r in self.logic_results.values()),
            },
            "by_category": {
                "llm": {cat: 0 for cat in ERROR_CATEGORIES},
                "logic": {cat: 0 for cat in ERROR_CATEGORIES},
            },
            "per_story": {},
        }
        
        for title in self.stories:
            llm_r = self.llm_results.get(title, {})
            logic_r = self.logic_results.get(title, {})
            
            summary["per_story"][title] = {
                "book": self.stories[title].get("book", "unknown"),
                "chapter": self.stories[title].get("chapter", "unknown"),
                "llm_errors": llm_r.get("error_count", 0),
                "logic_errors": logic_r.get("error_count", 0),
                "timing": self.story_timings.get(title, {}),
            }
            
            # Aggregate by category
            llm_summary = llm_r.get("summary", {}).get("by_category", {})
            for cat in ERROR_CATEGORIES:
                summary["by_category"]["llm"][cat] += llm_summary.get(cat, 0)
                
            logic_summary = logic_r.get("summary", {}).get("by_category", {})
            for cat in ERROR_CATEGORIES:
                summary["by_category"]["logic"][cat] += logic_summary.get(cat, 0)
                
        return summary
        
    def generate_report(self, summary: Dict) -> str:
        """Generate comprehensive markdown report for academic paper."""
        lines = []
        
        # Title and metadata
        lines.append("# Narrative Evaluation Experiment Report")
        lines.append("")
        lines.append("## Comparing LLM-Based vs Logic-Based Narrative Consistency Analysis")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**LLM Model:** {self.llm_model}")
        lines.append(f"**Stories Analyzed:** {len(self.stories)}")
        lines.append(f"**Books Covered:** {', '.join(summary['experiment_info']['books_analyzed'])}")
        lines.append(f"**Chapters per Book:** {summary['experiment_info'].get('chapters_per_book', 'N/A')}")
        lines.append("")
        
        # Timing information
        timing = summary.get("timing", {})
        lines.append("### Timing Information")
        lines.append("")
        lines.append(f"- **Total Experiment Time:** {timing.get('total_experiment_seconds', 0):.1f} seconds ({timing.get('total_experiment_seconds', 0)/60:.1f} minutes)")
        lines.append(f"- **Average per Story:** {timing.get('average_per_story_seconds', 0):.1f} seconds")
        lines.append("")
        
        # Per-book timing
        book_timing = timing.get("per_book", {})
        if book_timing:
            lines.append("**Timing by Book:**")
            lines.append("")
            lines.append("| Book | Chapters | Time (s) | Avg/Chapter (s) | LLM Errors | Logic Errors |")
            lines.append("|------|----------|----------|-----------------|------------|--------------|")
            for book, bt in sorted(book_timing.items()):
                chapters = bt.get("chapters", 1)
                total = bt.get("total_seconds", 0)
                avg = total / max(1, chapters)
                llm_err = bt.get("llm_errors", 0)
                logic_err = bt.get("logic_errors", 0)
                lines.append(f"| {book} | {chapters} | {total:.1f} | {avg:.1f} | {llm_err} | {logic_err} |")
            lines.append("")
        
        # Executive Summary
        lines.append("---")
        lines.append("")
        lines.append("## 1. Executive Summary")
        lines.append("")
        lines.append("This experiment compares two approaches to detecting narrative inconsistencies:")
        lines.append("")
        lines.append("1. **LLM-Based Analysis**: Direct semantic analysis using large language models")
        lines.append("2. **Logic-Based Analysis**: Formal verification using Answer Set Programming (Clingo)")
        lines.append("")
        lines.append("### Overall Results")
        lines.append("")
        lines.append("| Metric | LLM Linter | Logic Linter |")
        lines.append("|--------|------------|--------------|")
        lines.append(f"| **Total Errors Detected** | {summary['totals']['llm_total_errors']} | {summary['totals']['logic_total_errors']} |")
        lines.append(f"| **Average per Story** | {summary['totals']['llm_total_errors']/max(1,len(self.stories)):.2f} | {summary['totals']['logic_total_errors']/max(1,len(self.stories)):.2f} |")
        lines.append("")
        
        # Category breakdown
        lines.append("---")
        lines.append("")
        lines.append("## 2. Errors by Category")
        lines.append("")
        lines.append("The five error categories analyzed:")
        lines.append("")
        for cat, desc in CATEGORY_DESCRIPTIONS.items():
            lines.append(f"- **{cat.title()}**: {desc}")
        lines.append("")
        lines.append("### Category Comparison Table")
        lines.append("")
        lines.append("| Category | LLM Errors | Logic Errors | Description |")
        lines.append("|----------|------------|--------------|-------------|")
        for cat in ERROR_CATEGORIES:
            llm_count = summary["by_category"]["llm"].get(cat, 0)
            logic_count = summary["by_category"]["logic"].get(cat, 0)
            desc = CATEGORY_DESCRIPTIONS.get(cat, "")[:50] + "..."
            lines.append(f"| **{cat.title()}** | {llm_count} | {logic_count} | {desc} |")
        lines.append("")
        
        # Analysis insights
        lines.append("### Analysis Insights")
        lines.append("")
        
        llm_cats = summary["by_category"]["llm"]
        logic_cats = summary["by_category"]["logic"]
        
        llm_strengths = [c for c in ERROR_CATEGORIES if llm_cats.get(c, 0) > logic_cats.get(c, 0)]
        logic_strengths = [c for c in ERROR_CATEGORIES if logic_cats.get(c, 0) > llm_cats.get(c, 0)]
        
        if llm_strengths:
            lines.append(f"**LLM excels at detecting**: {', '.join(llm_strengths)}")
            lines.append("")
        if logic_strengths:
            lines.append(f"**Logic-based approach excels at detecting**: {', '.join(logic_strengths)}")
            lines.append("")
            
        # Per-story detailed results
        lines.append("---")
        lines.append("")
        lines.append("## 3. Detailed Results by Story")
        lines.append("")
        
        # Group by book
        by_book: Dict[str, List[str]] = {}
        for title in self.stories:
            book = self.stories[title].get("book", "Unknown")
            by_book.setdefault(book, []).append(title)
            
        for book, titles in sorted(by_book.items()):
            lines.append(f"### {book}")
            lines.append("")
            
            for title in sorted(titles):
                llm_r = self.llm_results.get(title, {})
                logic_r = self.logic_results.get(title, {})
                
                lines.append(f"#### {title}")
                lines.append("")
                lines.append(f"- **Source File**: `{self.stories[title].get('source_file', 'unknown')}`")
                lines.append(f"- **LLM Errors**: {llm_r.get('error_count', 0)}")
                lines.append(f"- **Logic Errors**: {logic_r.get('error_count', 0)}")
                lines.append("")
                
                # LLM errors detail
                llm_errors = llm_r.get("errors", [])
                if llm_errors:
                    lines.append("**LLM-Detected Errors:**")
                    lines.append("")
                    for err in llm_errors[:10]:  # Limit to first 10
                        cat = err.get("category", "unknown").upper()
                        etype = err.get("type", "unknown")
                        desc = err.get("description", "No description")
                        frag = err.get("story_fragment", "")
                        severity = err.get("severity", "medium")
                        
                        lines.append(f"- **[{cat}][{severity.upper()}]** `{etype}`")
                        lines.append(f"  - {desc}")
                        if frag:
                            frag_preview = frag[:200].replace("\n", " ")
                            if len(frag) > 200:
                                frag_preview += "..."
                            lines.append(f"  - Fragment: *\"{frag_preview}\"*")
                    if len(llm_errors) > 10:
                        lines.append(f"  - ... and {len(llm_errors) - 10} more errors")
                    lines.append("")
                    
                # Logic errors detail
                logic_errors = logic_r.get("errors", [])
                if logic_errors:
                    lines.append("**Logic-Detected Errors:**")
                    lines.append("")
                    for err in logic_errors[:10]:  # Limit to first 10
                        cat = err.get("category", "unknown").upper()
                        vtype = err.get("type", "unknown")
                        desc = err.get("description", "No description")
                        
                        lines.append(f"- **[{cat}]** `{vtype}`")
                        lines.append(f"  - {desc}")
                    if len(logic_errors) > 10:
                        lines.append(f"  - ... and {len(logic_errors) - 10} more violations")
                    lines.append("")
                    
        # Methodology section
        lines.append("---")
        lines.append("")
        lines.append("## 4. Methodology")
        lines.append("")
        lines.append("### 4.1 LLM-Based Linting")
        lines.append("")
        lines.append("The LLM-based approach uses a large language model to directly analyze narrative text.")
        lines.append("The model is prompted to identify inconsistencies across five categories:")
        lines.append("causality, coherence, temporal, location, and emotional.")
        lines.append("")
        lines.append("**Advantages:**")
        lines.append("- Can understand context and nuance")
        lines.append("- Catches subtle semantic issues")
        lines.append("- No formal knowledge representation required")
        lines.append("")
        lines.append("**Limitations:**")
        lines.append("- May hallucinate non-existent errors")
        lines.append("- Non-deterministic results")
        lines.append("- Depends on model quality and prompt engineering")
        lines.append("")
        lines.append("### 4.2 Logic-Based Linting")
        lines.append("")
        lines.append("The logic-based approach uses Answer Set Programming (ASP) with the Clingo solver.")
        lines.append("Stories are first converted to structured JSON by an LLM, then to ASP facts.")
        lines.append("The Clingo reasoner applies formal consistency rules to detect violations.")
        lines.append("")
        lines.append("**Architecture:**")
        lines.append("1. Story → LLM → Structured JSON (characters, events, fluents)")
        lines.append("2. JSON → ASP Facts (predicates like `event(e1)`, `agent(e1, alice)`)")
        lines.append("3. Facts + Rules → Clingo → Violations")
        lines.append("")
        lines.append("**Advantages:**")
        lines.append("- Sound and complete within defined rules")
        lines.append("- Deterministic results")
        lines.append("- Explainable reasoning")
        lines.append("")
        lines.append("**Limitations:**")
        lines.append("- Depends on story structuring quality")
        lines.append("- Cannot catch errors outside rule coverage")
        lines.append("- Requires maintenance of rule base")
        lines.append("")
        
        # Error categories detail
        lines.append("### 4.3 Error Categories")
        lines.append("")
        for cat, desc in CATEGORY_DESCRIPTIONS.items():
            lines.append(f"**{cat.title()}**: {desc}")
            lines.append("")
            
        # Conclusions
        lines.append("---")
        lines.append("")
        lines.append("## 5. Observations and Conclusions")
        lines.append("")
        
        total_llm = summary['totals']['llm_total_errors']
        total_logic = summary['totals']['logic_total_errors']
        
        if total_llm > total_logic:
            lines.append(f"The LLM-based approach detected {total_llm - total_logic} more errors overall,")
            lines.append("suggesting it may be more sensitive to subtle narrative issues or may have")
            lines.append("higher false-positive rates that require manual verification.")
        elif total_logic > total_llm:
            lines.append(f"The Logic-based approach detected {total_logic - total_llm} more errors overall,")
            lines.append("suggesting the formal rules capture violations that the LLM misses.")
        else:
            lines.append("Both approaches detected similar numbers of errors overall.")
            
        lines.append("")
        lines.append("### Key Findings")
        lines.append("")
        lines.append("1. **Complementary Approaches**: Each method catches errors the other misses")
        lines.append("2. **Category Specialization**: Different methods excel at different error types")
        lines.append("3. **Hybrid Potential**: Combining both approaches could maximize coverage")
        lines.append("")
        
        # Appendix: Technical details
        lines.append("---")
        lines.append("")
        lines.append("## Appendix A: Technical Configuration")
        lines.append("")
        lines.append(f"- **LLM Model**: {self.llm_model}")
        lines.append(f"- **LLM Endpoint**: {self.llm_base_url}")
        lines.append(f"- **Timeout**: {self.llm_timeout}s")
        lines.append(f"- **Total Stories**: {len(self.stories)}")
        lines.append(f"- **Experiment Directory**: {self.exp_dir}")
        lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def create_experiment_folder(name: str, base_dir: Path) -> Tuple[Path, str, datetime]:
    """Create experiment folder with timestamp and UUID."""
    start_time = datetime.now()
    exp_uuid = str(uuid.uuid4())[:8]
    folder_name = f"{name}-{start_time.strftime('%Y%m%d_%H%M%S')}-pending-{exp_uuid}"
    exp_dir = base_dir / folder_name
    
    # Create subdirectories
    (exp_dir / "stories").mkdir(parents=True)
    (exp_dir / "llm_results").mkdir()
    (exp_dir / "logic_results").mkdir()
    (exp_dir / "structured_json").mkdir()
    (exp_dir / "asp_facts").mkdir()
    (exp_dir / "logs").mkdir()
    
    return exp_dir, exp_uuid, start_time


def finalize_experiment_folder(exp_dir: Path, start_time: datetime) -> Path:
    """Rename folder with end timestamp."""
    end_time = datetime.now()
    old_name = exp_dir.name
    new_name = old_name.replace("-pending-", f"-{end_time.strftime('%Y%m%d_%H%M%S')}-")
    new_dir = exp_dir.parent / new_name
    exp_dir.rename(new_dir)
    return new_dir


def main():
    parser = argparse.ArgumentParser(
        description="Run comprehensive narrative evaluation experiment"
    )
    parser.add_argument(
        "--name", 
        default="narrative_eval",
        help="Experiment name prefix"
    )
    parser.add_argument(
        "--books-dir", 
        type=Path, 
        default=REPO_ROOT / "processed_books",
        help="Directory containing book subdirectories"
    )
    parser.add_argument(
        "--output-dir", 
        type=Path, 
        default=REPO_ROOT / "experiments",
        help="Output directory for experiment"
    )
    parser.add_argument(
        "--llm-base-url", 
        default="http://localhost:8080/v1",
        help="LLM API base URL"
    )
    parser.add_argument(
        "--llm-timeout", 
        type=int, 
        default=600,
        help="LLM API timeout in seconds"
    )
    parser.add_argument(
        "--llm-model", 
        default="auto",
        help="LLM model name (auto to detect)"
    )
    parser.add_argument(
        "--max-chapters-per-book", 
        type=int, 
        default=2,
        help="Maximum chapters to process per book"
    )
    
    args = parser.parse_args()
    
    # Create experiment folder
    args.output_dir.mkdir(parents=True, exist_ok=True)
    exp_dir, exp_uuid, start_time = create_experiment_folder(args.name, args.output_dir)
    
    print(f"Experiment started: {exp_dir}")
    print(f"Start time: {start_time.isoformat()}")
    
    # Save config
    config = {
        "name": args.name,
        "uuid": exp_uuid,
        "start_time": start_time.isoformat(),
        "books_dir": str(args.books_dir),
        "llm_base_url": args.llm_base_url,
        "llm_timeout": args.llm_timeout,
        "llm_model": args.llm_model,
        "max_chapters_per_book": args.max_chapters_per_book,
    }
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2))
    
    # Initialize runner
    runner = ComprehensiveExperimentRunner(
        exp_dir,
        llm_base_url=args.llm_base_url,
        llm_timeout=args.llm_timeout,
        llm_model=args.llm_model,
    )
    
    # Load stories
    runner.load_stories_from_directory(args.books_dir, args.max_chapters_per_book)
    
    if not runner.stories:
        print("No stories found to process!")
        return
        
    # Run experiment
    try:
        summary = runner.run_experiment()
        
        # Save summary
        summary_path = exp_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        
        # Generate and save report
        report = runner.generate_report(summary)
        report_path = exp_dir / "report.md"
        report_path.write_text(report, encoding="utf-8")
        
        # Finalize folder name with end time
        end_time = datetime.now()
        config["end_time"] = end_time.isoformat()
        config["duration_seconds"] = (end_time - start_time).total_seconds()
        (exp_dir / "config.json").write_text(json.dumps(config, indent=2))
        
        final_dir = finalize_experiment_folder(exp_dir, start_time)
        
        print("")
        print("=" * 60)
        print("EXPERIMENT COMPLETE")
        print("=" * 60)
        print(f"Output directory: {final_dir}")
        print(f"Report: {final_dir / 'report.md'}")
        print(f"Summary: {final_dir / 'summary.json'}")
        print(f"Duration: {config['duration_seconds']:.1f} seconds")
        print(f"LLM errors: {summary['totals']['llm_total_errors']}")
        print(f"Logic errors: {summary['totals']['logic_total_errors']}")
        
    except KeyboardInterrupt:
        print("\nExperiment interrupted by user")
        # Still save partial results
        final_dir = finalize_experiment_folder(exp_dir, start_time)
        print(f"Partial results saved to: {final_dir}")
        
    except Exception as e:
        print(f"\nExperiment failed: {e}")
        traceback.print_exc()
        final_dir = finalize_experiment_folder(exp_dir, start_time)
        print(f"Partial results saved to: {final_dir}")


if __name__ == "__main__":
    main()
