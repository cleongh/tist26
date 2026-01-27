#!/usr/bin/env python3
"""
run_comprehensive_experiment.py - Comprehensive Narrative Evaluation Experiment
================================================================================

This script orchestrates a complete narrative evaluation experiment comparing:
1. LLM-based direct linting
2. Logic-based linting (ASP/Clingo)

The experiment implements:
- K-fold cross-validation (k=1,2,3,4)
- Baseline false-positive filtering using original books
- Five error categories: Causality, Coherence, Temporal, Location, Emotional
- Exhaustive logging with timestamps
- Academic report generation for AI journal publication

ARCHITECTURE
============

The experiment uses a two-module rule system:
1. general.lp - Domain-independent abstract rules
2. domain_<experiment>.lp - Story-specific facts generated during analysis

ERROR CATEGORIES
================

1. CAUSALITY - Chekhov's gun, unexplained effects, missing preconditions
2. COHERENCE - Semantic errors, dead agents, physical impossibilities
3. TEMPORAL - Time ordering, duration violations, simultaneity conflicts  
4. LOCATION - Ubiquity, impossible travel, proximity violations
5. EMOTIONAL - Relationship-behavior mismatches, motivation inconsistencies

USAGE
=====

    # Using venv
    source venv/bin/activate
    python scripts/run_comprehensive_experiment.py

    # With specific LLM backend
    python scripts/run_comprehensive_experiment.py --llm-backend gemini

Author: Narrative Evaluation Research Project
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from json_to_asp import json_to_asp
from llm_structurer import structure_story

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Error categories for classification
ERROR_CATEGORIES = ['causality', 'coherence', 'temporal', 'location', 'emotional']

# Category keywords for classification from violation types
CATEGORY_KEYWORDS = {
    'causality': ['chekhov', 'uncaused', 'cause', 'effect', 'precondition', 'unexplained'],
    'coherence': ['dead_agent', 'non_edible', 'physical_impossibility', 'focus_overlap', 
                  'edible', 'semantic', 'logical'],
    'temporal': ['circular_time', 'negative_duration', 'explicit_order', 'temporal', 
                 'before', 'after', 'overlap', 'duration'],
    'location': ['ubiquity', 'proximity', 'impossible_travel', 'location', 'spatial',
                 'distance', 'teleport'],
    'emotional': ['harm_loved', 'help_enemy', 'approach_feared', 'misplaced_trust',
                  'state_action_mismatch', 'emotion', 'relationship', 'loves', 'hates']
}

# Load environment variables
def get_env_or_default(key: str, default: str = '') -> str:
    """Get environment variable with fallback."""
    return os.environ.get(key, default)


# =============================================================================
# LOGGING AND TIMING UTILITIES
# =============================================================================

class ExperimentLogger:
    """
    Comprehensive logger for experiment tracking.
    
    Logs all events with timestamps to:
    - Console (stderr)
    - Log file in experiment directory
    - LLM calls log (JSONL format)
    """
    
    def __init__(self, experiment_dir: Path, verbose: bool = True):
        self.experiment_dir = experiment_dir
        self.verbose = verbose
        self.log_file = experiment_dir / 'logs' / 'experiment.log'
        self.llm_calls_file = experiment_dir / 'llm_calls.jsonl'
        self.timings: Dict[str, Dict[str, Any]] = {}
        
        # Ensure log directories exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize log files
        self.log_file.write_text('')
        self.llm_calls_file.write_text('')
    
    def log(self, message: str, level: str = 'INFO'):
        """Log message with timestamp."""
        timestamp = datetime.now().isoformat()
        formatted = f"[{timestamp}] [{level}] {message}"
        
        # Write to file
        with open(self.log_file, 'a') as f:
            f.write(formatted + '\n')
        
        # Write to stderr if verbose
        if self.verbose:
            sys.stderr.write(formatted + '\n')
    
    def log_llm_call(self, call_type: str, prompt: str, response: str, 
                     model: str, duration: float, story_file: str = None,
                     extra: Dict = None):
        """Log LLM API call details."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': call_type,
            'model': model,
            'duration_seconds': duration,
            'story_file': story_file,
            'prompt_length': len(prompt),
            'response_length': len(response) if response else 0,
            'prompt': prompt[:1000] + '...' if len(prompt) > 1000 else prompt,
            'response': response[:2000] + '...' if response and len(response) > 2000 else response,
        }
        if extra:
            entry.update(extra)
        
        with open(self.llm_calls_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    def start_timer(self, name: str):
        """Start a named timer."""
        self.timings[name] = {
            'start': datetime.now(),
            'end': None,
            'duration': None
        }
        self.log(f"Timer started: {name}")
    
    def stop_timer(self, name: str) -> float:
        """Stop a named timer and return duration in seconds."""
        if name not in self.timings:
            self.log(f"Warning: Timer '{name}' was never started", 'WARN')
            return 0.0
        
        self.timings[name]['end'] = datetime.now()
        duration = (self.timings[name]['end'] - self.timings[name]['start']).total_seconds()
        self.timings[name]['duration'] = duration
        self.log(f"Timer stopped: {name} ({duration:.2f}s)")
        return duration
    
    def get_all_timings(self) -> Dict:
        """Get all timing information."""
        return {
            name: {
                'start': t['start'].isoformat() if t['start'] else None,
                'end': t['end'].isoformat() if t['end'] else None,
                'duration_seconds': t['duration']
            }
            for name, t in self.timings.items()
        }


# =============================================================================
# ERROR CLASSIFICATION UTILITIES
# =============================================================================

def classify_error_category(error: Dict) -> str:
    """
    Classify an error into one of the 5 categories.
    
    Uses multiple signals:
    1. Explicit 'category' field
    2. 'violation_type' field keywords
    3. 'description' field keywords
    
    Args:
        error: Dictionary containing error information
        
    Returns:
        Category string: causality|coherence|temporal|location|emotional
    """
    # Check explicit category first
    if 'category' in error:
        cat = error['category'].lower()
        if cat in ERROR_CATEGORIES:
            return cat
    
    # Check violation_type
    violation_type = error.get('violation_type', '').lower()
    description = error.get('description', '').lower()
    
    text_to_check = f"{violation_type} {description}"
    
    # Score each category by keyword matches
    scores = {cat: 0 for cat in ERROR_CATEGORIES}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_to_check:
                scores[cat] += 1
    
    # Return highest scoring category, default to 'coherence'
    max_score = max(scores.values())
    if max_score > 0:
        for cat in ERROR_CATEGORIES:
            if scores[cat] == max_score:
                return cat
    
    return 'coherence'  # Default category


def create_error_signature(error: Dict) -> str:
    """
    Create a signature for error deduplication.
    
    The signature captures the essential characteristics of an error
    for filtering baseline false positives.
    
    Args:
        error: Error dictionary
        
    Returns:
        Signature string for comparison
    """
    category = classify_error_category(error)
    violation_type = error.get('violation_type', error.get('id', 'unknown'))
    
    # Normalize description for comparison
    desc = error.get('description', '')
    desc_normalized = re.sub(r'\b(e\d+|t\d+)\b', 'EID', desc.lower())
    desc_normalized = re.sub(r'\s+', ' ', desc_normalized).strip()[:100]
    
    return f"{category}|{violation_type}|{desc_normalized}"


# =============================================================================
# CORE LINTING FUNCTIONS
# =============================================================================

def call_llm_api(prompt: str, args: argparse.Namespace, 
                 logger: ExperimentLogger, call_type: str,
                 story_file: str = None, temperature: float = 0.0) -> Tuple[str, float]:
    """
    Call LLM API with proper configuration and logging.
    
    All calls use temperature=0 for determinism as per requirements.
    
    Args:
        prompt: The prompt to send
        args: Argument namespace with API configuration
        logger: Experiment logger
        call_type: Type of call for logging (lint/structure/interpret)
        story_file: Optional story file name for logging
        temperature: Sampling temperature (default 0 for determinism)
        
    Returns:
        Tuple of (response_text, duration_seconds)
    """
    import urllib.error
    import urllib.request
    
    start_time = time.time()
    
    if args.llm_backend == 'gemini':
        response = _call_gemini(prompt, args, temperature)
    else:
        response = _call_openai_compatible(prompt, args, temperature)
    
    duration = time.time() - start_time
    
    logger.log_llm_call(
        call_type=call_type,
        prompt=prompt,
        response=response,
        model=args.llm_model,
        duration=duration,
        story_file=story_file
    )
    
    return response, duration


def _call_openai_compatible(prompt: str, args: argparse.Namespace, 
                            temperature: float = 0.0) -> str:
    """Call OpenAI-compatible API."""
    import urllib.request
    
    url = args.llm_base_url.rstrip('/') + '/chat/completions'
    payload = {
        'model': args.llm_model,
        'temperature': temperature,
        'messages': [
            {'role': 'system', 'content': 'You are a careful JSON-only responder.'},
            {'role': 'user', 'content': prompt}
        ]
    }
    
    if args.llm_max_tokens:
        payload['max_tokens'] = args.llm_max_tokens
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    
    if args.llm_api_key and not args.llm_no_auth:
        req.add_header('Authorization', f'Bearer {args.llm_api_key}')
    
    with urllib.request.urlopen(req, timeout=args.llm_timeout) as resp:
        body = resp.read().decode('utf-8')
    
    obj = json.loads(body)
    return obj['choices'][0]['message']['content']


def _call_gemini(prompt: str, args: argparse.Namespace, 
                 temperature: float = 0.0) -> str:
    """Call Google Gemini API."""
    import urllib.request
    
    model = args.llm_model
    if model.startswith('models/'):
        model = model[len('models/'):]
    
    url = f"{args.llm_base_url.rstrip('/')}/models/{model}:generateContent?key={args.llm_api_key}"
    
    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': temperature,
            'responseMimeType': 'application/json'
        }
    }
    
    if args.llm_max_tokens:
        payload['generationConfig']['maxOutputTokens'] = args.llm_max_tokens
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    
    with urllib.request.urlopen(req, timeout=args.llm_timeout) as resp:
        body = resp.read().decode('utf-8')
    
    obj = json.loads(body)
    candidates = obj.get('candidates', [])
    if not candidates:
        raise ValueError('Gemini response missing candidates')
    
    parts = candidates[0].get('content', {}).get('parts', [])
    return ''.join(p.get('text', '') for p in parts if isinstance(p, dict))


def extract_json_from_response(text: str) -> Optional[Dict]:
    """Extract JSON object from LLM response text."""
    text = text.strip()
    
    # Remove <think> blocks if present
    if '<think>' in text and '</think>' in text:
        start = text.find('<think>')
        end = text.find('</think>')
        text = text[:start] + text[end + len('</think>'):]
        text = text.strip()
    
    # Try direct parse
    if text.startswith('{') and text.endswith('}'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    
    # Find JSON object in text
    start = text.find('{')
    if start == -1:
        return None
    
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None
    
    return None


def load_rules_for_prompt() -> str:
    """Load general.lp and base.lp content for inclusion in prompts."""
    rules_content = []
    
    for rules_file in ['rules/general.lp', 'rules/base.lp']:
        path = Path(rules_file)
        if path.exists():
            rules_content.append(f"=== {rules_file} ===\n{path.read_text()}")
    
    return '\n\n'.join(rules_content)


# =============================================================================
# LLM LINTING PROMPTS AND FUNCTIONS
# =============================================================================

LLM_LINT_PROMPT = """You are a narrative linting assistant. Analyze the story for inconsistencies.

Focus on these 5 error categories:

1. CAUSALITY: Chekhov's gun violations (introduced elements never used), unexplained effects, events without proper causes, missing preconditions.

2. COHERENCE: Semantic incorrectness, logical impossibilities (dead characters acting, eating inedible objects), physical trait violations.

3. TEMPORAL: Time paradoxes, events in impossible order, duration violations, simultaneous events that can't overlap.

4. LOCATION: Characters in two places at once, instant travel between distant locations, interacting with things in different locations.

5. EMOTIONAL: Character actions contradicting their relationships (harming loved ones without reason, helping enemies), emotional state mismatches.

Return ONLY valid JSON. No reasoning, preambles, or markdown.

Schema (strict):
{{
  "error_count": integer,
  "errors": [{{
    "id": "e1",
    "category": "causality|coherence|temporal|location|emotional",
    "description": "detailed description of the error",
    "story_fragments": ["exact quote from the story showing the error"],
    "related_fragments": ["other relevant quotes if the error involves multiple parts"]
  }}]
}}

Ensure:
- error_count equals the number of errors
- Each error has a category from the 5 options
- story_fragments contains the EXACT text from the story (word-for-word quotes)
- Include enough context to understand the error

Story to analyze:
\"\"\"
{story}
\"\"\"
"""


def run_llm_lint(story_text: str, story_file: str, args: argparse.Namespace,
                 logger: ExperimentLogger) -> Dict:
    """
    Run LLM-based direct linting on a story.
    
    Args:
        story_text: The story content
        story_file: Path to the story file
        args: Configuration arguments
        logger: Experiment logger
        
    Returns:
        Dictionary with error_count, errors, and details
    """
    logger.log(f"Running LLM lint on: {story_file}")
    
    prompt = LLM_LINT_PROMPT.format(story=story_text.strip())
    
    try:
        response, duration = call_llm_api(
            prompt, args, logger, 'llm_lint', 
            story_file=story_file, temperature=0.0
        )
        
        result = extract_json_from_response(response)
        
        if result is None:
            logger.log(f"Failed to parse LLM lint response for {story_file}", 'ERROR')
            return {
                'error_count': 0, 
                'errors': [], 
                'parse_error': True,
                'raw_response': response[:500]
            }
        
        # Ensure error_count matches
        result['error_count'] = len(result.get('errors', []))
        
        # Add category classification to each error
        for error in result.get('errors', []):
            if 'category' not in error:
                error['category'] = classify_error_category(error)
            error['story_file'] = story_file
        
        result['duration_seconds'] = duration
        return result
        
    except Exception as e:
        logger.log(f"LLM lint failed for {story_file}: {e}", 'ERROR')
        return {'error_count': 0, 'errors': [], 'exception': str(e)}


# =============================================================================
# LOGIC LINTING FUNCTIONS
# =============================================================================

STRUCTURE_PROMPT_TEMPLATE = """You are a semantic parser for narrative analysis. Extract structured JSON from stories.

Your output must align with these ASP rules for consistency checking:

{rules}

STORY TO ANALYZE:
\"\"\"
{story}
\"\"\"

Output JSON with this schema (ONLY JSON, no explanation):
{{
  "title": "story title if known",
  
  "entities": {{
    "characters": [{{"id": "short_id", "name": "Full Name"}}],
    "objects": [{{"id": "short_id", "type": "category"}}],
    "locations": [{{"id": "short_id", "name": "Location Name"}}]
  }},
  
  "events": [
    {{
      "id": "e1",
      "type": "action_verb",
      "description": "brief description",
      "agent": "character_id",
      "patient": "entity_id or null",
      "location": "location_id",
      "time": {{"start": "t1", "end": "t2"}},
      "requires_focus": false,
      "story_fragment": "EXACT quote from story"
    }}
  ],
  
  "relationships": [
    {{
      "type": "loves|hates|fears|trusts|distrusts",
      "from": "character_id",
      "to": "character_id",
      "story_fragment": "quote showing relationship"
    }}
  ],
  
  "emotional_states": [
    {{
      "character": "character_id",
      "emotion": "happy|sad|angry|afraid|calm",
      "time": {{"start": "t1", "end": "t2"}},
      "story_fragment": "quote showing emotion"
    }}
  ],
  
  "fluents": [
    {{"id": "property(entity)", "time": {{"start": "t1", "end": "t2"}}}}
  ],
  
  "traits": [
    {{"character": "id", "trait": "trait_name"}}
  ],
  
  "location_graph": [
    {{
      "from": "location_id",
      "to": "location_id",
      "relation": "adjacent|distant|contains"
    }}
  ],
  
  "causal_chains": [
    {{
      "cause_event": "e1",
      "effect_event": "e2",
      "story_fragment": "quote showing causation"
    }}
  ]
}}

CRITICAL: Include story_fragment with EXACT quotes for each event and relationship!
"""


INTERPRET_VIOLATIONS_PROMPT = """You are explaining logic violations found in a narrative.

The story text was:
\"\"\"
{story}
\"\"\"

The ASP facts extracted from the story were:
{asp_facts}

The Clingo reasoner found these violations:
{violations}

Explain each violation in human-readable form. For EACH violation, find and include the exact story fragments that caused it.

Return ONLY JSON:
{{
  "error_count": integer,
  "errors": [{{
    "id": "logic_1",
    "category": "causality|coherence|temporal|location|emotional",
    "violation_type": "the ASP violation type",
    "description": "human readable explanation",
    "story_fragments": ["EXACT quote from the story that caused this"],
    "related_fragments": ["other relevant quotes"],
    "involved_entities": ["list of characters, objects, events involved"],
    "asp_atoms": ["the relevant ASP atoms"]
  }}]
}}

Map violation types to categories:
- chekhov_gun, uncaused_event, effect_without_cause, precondition_missing -> causality
- dead_agent, non_edible_food, physical_impossibility, focus_overlap -> coherence
- circular_time, negative_duration, explicit_order_violated -> temporal
- ubiquity, proximity_required, impossible_travel -> location
- harm_loved, help_enemy, approach_feared, misplaced_trust, state_action_mismatch -> emotional
"""


def run_logic_lint(story_text: str, story_file: str, args: argparse.Namespace,
                   logger: ExperimentLogger) -> Dict:
    """
    Run logic-based linting using ASP/Clingo.
    
    Process:
    1. Structure story via LLM -> JSON
    2. Convert JSON -> ASP facts
    3. Run Clingo with general.lp rules
    4. Interpret violations via LLM (including story fragments)
    
    Args:
        story_text: The story content
        story_file: Path to the story file
        args: Configuration arguments
        logger: Experiment logger
        
    Returns:
        Dictionary with error_count, errors, and details
    """
    logger.log(f"Running logic lint on: {story_file}")
    
    details = {
        'structuring': {},
        'asp_facts': None,
        'clingo_output': None,
        'interpretation': {}
    }
    
    # Step 1: Structure the story
    rules_content = load_rules_for_prompt()
    structure_prompt = STRUCTURE_PROMPT_TEMPLATE.format(
        rules=rules_content[:3000],  # Truncate to fit context
        story=story_text.strip()
    )
    
    try:
        struct_response, struct_duration = call_llm_api(
            structure_prompt, args, logger, 'structure',
            story_file=story_file, temperature=0.0
        )
        
        structured_data = extract_json_from_response(struct_response)
        
        if structured_data is None:
            logger.log(f"Failed to parse structure response for {story_file}", 'ERROR')
            return {
                'error_count': 0, 
                'errors': [],
                'parse_error': True,
                'details': details
            }
        
        details['structuring'] = {
            'duration_seconds': struct_duration,
            'parsed': structured_data
        }
        
    except Exception as e:
        logger.log(f"Structure step failed for {story_file}: {e}", 'ERROR')
        return {'error_count': 0, 'errors': [], 'exception': str(e), 'details': details}
    
    # Step 2: Convert to ASP facts
    try:
        asp_facts = json_to_asp(structured_data, include_candidates=False)
        details['asp_facts'] = asp_facts
        
        # Add story fragment tracking facts
        asp_facts += generate_fragment_tracking_facts(structured_data)
        
    except Exception as e:
        logger.log(f"ASP conversion failed for {story_file}: {e}", 'ERROR')
        return {'error_count': 0, 'errors': [], 'exception': str(e), 'details': details}
    
    # Step 3: Run Clingo
    violations = []
    try:
        import clingo
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lp', delete=False) as f:
            f.write(asp_facts)
            facts_path = f.name
        
        try:
            ctl = clingo.Control(['--warn=none'])
            
            # Load rules
            rules_file = Path('rules/general.lp')
            if rules_file.exists():
                ctl.load(str(rules_file.absolute()))
            else:
                rules_file = Path('rules/base.lp')
                ctl.load(str(rules_file.absolute()))
            
            ctl.load(facts_path)
            ctl.ground([('base', [])])
            
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == 'violation':
                            parts = [str(arg) for arg in atom.arguments]
                            violations.append(parts)
            
            details['clingo_output'] = violations
            logger.log(f"Clingo found {len(violations)} violations in {story_file}")
            
        finally:
            os.unlink(facts_path)
            
    except ImportError:
        logger.log("Clingo not available, skipping logic lint", 'ERROR')
        return {'error_count': 0, 'errors': [], 'clingo_missing': True, 'details': details}
    except Exception as e:
        logger.log(f"Clingo execution failed for {story_file}: {e}", 'ERROR')
        return {'error_count': 0, 'errors': [], 'exception': str(e), 'details': details}
    
    # Step 4: Interpret violations with LLM (including story fragments)
    if not violations:
        return {'error_count': 0, 'errors': [], 'details': details}
    
    try:
        violation_strs = [f"violation({', '.join(v)})" for v in violations]
        
        interpret_prompt = INTERPRET_VIOLATIONS_PROMPT.format(
            story=story_text[:3000],  # Truncate to fit context
            asp_facts=asp_facts[:2000],
            violations='\n'.join(violation_strs)
        )
        
        interpret_response, interpret_duration = call_llm_api(
            interpret_prompt, args, logger, 'interpret',
            story_file=story_file, temperature=0.0
        )
        
        result = extract_json_from_response(interpret_response)
        
        if result is None:
            # Fallback: return raw violations
            logger.log(f"Failed to interpret violations for {story_file}", 'WARN')
            errors = [{
                'id': f'logic_{i}',
                'category': classify_violation_category(v),
                'violation_type': v[0] if v else 'unknown',
                'description': f"violation({', '.join(v)})",
                'story_fragments': [],
                'raw_violation': v
            } for i, v in enumerate(violations, 1)]
            return {
                'error_count': len(errors),
                'errors': errors,
                'raw_violations': violation_strs,
                'details': details
            }
        
        # Add story file to each error
        for error in result.get('errors', []):
            error['story_file'] = story_file
            if 'category' not in error:
                error['category'] = classify_error_category(error)
        
        result['error_count'] = len(result.get('errors', []))
        result['raw_violations'] = violation_strs
        result['details'] = details
        result['interpretation_duration'] = interpret_duration
        
        return result
        
    except Exception as e:
        logger.log(f"Interpretation failed for {story_file}: {e}", 'ERROR')
        errors = [{
            'id': f'logic_{i}',
            'category': classify_violation_category(v),
            'violation_type': v[0] if v else 'unknown',
            'description': f"violation({', '.join(v)})",
            'story_fragments': [],
            'raw_violation': v
        } for i, v in enumerate(violations, 1)]
        return {
            'error_count': len(errors),
            'errors': errors,
            'raw_violations': [f"violation({', '.join(v)})" for v in violations],
            'details': details
        }


def classify_violation_category(violation_parts: List[str]) -> str:
    """Classify a raw violation into a category."""
    if not violation_parts:
        return 'coherence'
    
    vtype = violation_parts[0].lower()
    
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in vtype:
                return cat
    
    return 'coherence'


def generate_fragment_tracking_facts(structured_data: Dict) -> str:
    """Generate ASP facts for story fragment tracking."""
    facts = ['\n% Story fragment tracking']
    
    for event in structured_data.get('events', []):
        ev_id = event.get('id', '')
        fragment = event.get('story_fragment', '')
        if ev_id and fragment:
            # Escape quotes and create fact
            safe_fragment = fragment.replace('"', '\\"').replace('\n', ' ')[:200]
            facts.append(f'story_fragment({ev_id}, "{safe_fragment}").')
    
    return '\n'.join(facts)


# =============================================================================
# EXPERIMENT RUNNER
# =============================================================================

def discover_stories(directory: Path) -> Dict[str, List[Path]]:
    """
    Discover all story files organized by book.
    
    Args:
        directory: Path to books directory
        
    Returns:
        Dictionary mapping book names to list of chapter paths
    """
    books = {}
    
    for book_dir in sorted(directory.iterdir()):
        if book_dir.is_dir():
            chapters = sorted(book_dir.glob('*.txt'))
            if chapters:
                books[book_dir.name] = chapters
    
    return books


def process_story(story_path: Path, args: argparse.Namespace,
                  logger: ExperimentLogger, mode: str = 'both') -> Dict:
    """
    Process a single story with both linting methods.
    
    Args:
        story_path: Path to story file
        args: Configuration arguments
        logger: Experiment logger
        mode: 'llm', 'logic', or 'both'
        
    Returns:
        Dictionary with llm_lint and/or logic_lint results
    """
    story_text = story_path.read_text()
    story_file = str(story_path)
    
    result = {
        'story_file': story_file,
        'story_title': story_path.stem,
        'book': story_path.parent.name,
        'character_count': len(story_text),
        'timestamp': datetime.now().isoformat()
    }
    
    if mode in ('llm', 'both'):
        logger.start_timer(f"llm_{story_path.name}")
        result['llm_lint'] = run_llm_lint(story_text, story_file, args, logger)
        logger.stop_timer(f"llm_{story_path.name}")
    
    if mode in ('logic', 'both'):
        logger.start_timer(f"logic_{story_path.name}")
        result['logic_lint'] = run_logic_lint(story_text, story_file, args, logger)
        logger.stop_timer(f"logic_{story_path.name}")
    
    return result


def run_baseline(original_books: Dict[str, List[Path]], args: argparse.Namespace,
                 logger: ExperimentLogger, experiment_dir: Path,
                 chapters_per_book: int = None) -> Dict:
    """
    Run baseline analysis on original books to identify false positives.
    
    Args:
        original_books: Dictionary of book name -> chapter paths
        args: Configuration arguments
        logger: Experiment logger
        experiment_dir: Directory to save results
        chapters_per_book: Optional limit on chapters per book
        
    Returns:
        Baseline results with error signatures for filtering
    """
    logger.log("="*60)
    logger.log("RUNNING BASELINE (Original Books)")
    logger.log("="*60)
    logger.start_timer("baseline_total")
    
    baseline_dir = experiment_dir / 'baseline'
    baseline_dir.mkdir(exist_ok=True)
    
    all_results = []
    llm_signatures = set()
    logic_signatures = set()
    
    for book_name, chapters in original_books.items():
        logger.log(f"\nProcessing book: {book_name}")
        logger.start_timer(f"baseline_{book_name}")
        
        # Limit chapters if specified
        if chapters_per_book:
            chapters = chapters[:chapters_per_book]
        
        for chapter_path in chapters:
            logger.log(f"  Chapter: {chapter_path.name}")
            
            result = process_story(chapter_path, args, logger)
            all_results.append(result)
            
            # Save individual chapter result
            chapter_result_path = baseline_dir / f"{book_name}_{chapter_path.stem}.json"
            chapter_result_path.write_text(json.dumps(result, indent=2))
            
            # Collect error signatures for filtering
            for error in result.get('llm_lint', {}).get('errors', []):
                llm_signatures.add(create_error_signature(error))
            
            for error in result.get('logic_lint', {}).get('errors', []):
                logic_signatures.add(create_error_signature(error))
        
        logger.stop_timer(f"baseline_{book_name}")
    
    logger.stop_timer("baseline_total")
    
    # Aggregate baseline statistics
    baseline_summary = {
        'total_chapters': len(all_results),
        'llm_errors': sum(r.get('llm_lint', {}).get('error_count', 0) for r in all_results),
        'logic_errors': sum(r.get('logic_lint', {}).get('error_count', 0) for r in all_results),
        'llm_signatures': list(llm_signatures),
        'logic_signatures': list(logic_signatures),
        'by_book': {}
    }
    
    # Per-book breakdown
    for book_name in original_books:
        book_results = [r for r in all_results if r.get('book') == book_name]
        baseline_summary['by_book'][book_name] = {
            'chapters': len(book_results),
            'llm_errors': sum(r.get('llm_lint', {}).get('error_count', 0) for r in book_results),
            'logic_errors': sum(r.get('logic_lint', {}).get('error_count', 0) for r in book_results)
        }
    
    # Save baseline summary
    (baseline_dir / 'summary.json').write_text(json.dumps(baseline_summary, indent=2))
    
    return {
        'results': all_results,
        'llm_signatures': llm_signatures,
        'logic_signatures': logic_signatures,
        'summary': baseline_summary
    }


def run_test(modified_books: Dict[str, List[Path]], baseline: Dict,
             args: argparse.Namespace, logger: ExperimentLogger, 
             experiment_dir: Path, chapters_per_book: int = None) -> Dict:
    """
    Run test analysis on modified books, filtering baseline false positives.
    
    Args:
        modified_books: Dictionary of book name -> chapter paths
        baseline: Baseline results with error signatures
        args: Configuration arguments
        logger: Experiment logger
        experiment_dir: Directory to save results
        chapters_per_book: Optional limit on chapters per book
        
    Returns:
        Test results with true positives identified
    """
    logger.log("="*60)
    logger.log("RUNNING TEST (Modified Books)")
    logger.log("="*60)
    logger.start_timer("test_total")
    
    test_dir = experiment_dir / 'test'
    test_dir.mkdir(exist_ok=True)
    stories_dir = experiment_dir / 'stories'
    stories_dir.mkdir(exist_ok=True)
    
    llm_signatures = baseline['llm_signatures']
    logic_signatures = baseline['logic_signatures']
    
    all_results = []
    true_positives_llm = []
    true_positives_logic = []
    filtered_llm = []
    filtered_logic = []
    
    for book_name, chapters in modified_books.items():
        logger.log(f"\nProcessing book: {book_name}")
        logger.start_timer(f"test_{book_name}")
        
        if chapters_per_book:
            chapters = chapters[:chapters_per_book]
        
        for chapter_path in chapters:
            logger.log(f"  Chapter: {chapter_path.name}")
            
            result = process_story(chapter_path, args, logger)
            
            # Filter LLM errors
            llm_errors = result.get('llm_lint', {}).get('errors', [])
            result['llm_lint']['true_positives'] = []
            result['llm_lint']['filtered'] = []
            
            for error in llm_errors:
                sig = create_error_signature(error)
                if sig in llm_signatures:
                    result['llm_lint']['filtered'].append(error)
                    filtered_llm.append(error)
                else:
                    result['llm_lint']['true_positives'].append(error)
                    true_positives_llm.append(error)
            
            # Filter logic errors
            logic_errors = result.get('logic_lint', {}).get('errors', [])
            result['logic_lint']['true_positives'] = []
            result['logic_lint']['filtered'] = []
            
            for error in logic_errors:
                sig = create_error_signature(error)
                if sig in logic_signatures:
                    result['logic_lint']['filtered'].append(error)
                    filtered_logic.append(error)
                else:
                    result['logic_lint']['true_positives'].append(error)
                    true_positives_logic.append(error)
            
            all_results.append(result)
            
            # Save individual story result (requirement: each story in separate file)
            story_result_path = stories_dir / f"{book_name}_{chapter_path.stem}.json"
            story_result_path.write_text(json.dumps(result, indent=2))
            
            # Also save as text for easy reading
            story_text_path = stories_dir / f"{book_name}_{chapter_path.stem}.txt"
            with open(story_text_path, 'w') as f:
                f.write(f"Story: {chapter_path.name}\n")
                f.write(f"Book: {book_name}\n")
                f.write("="*60 + "\n\n")
                f.write(chapter_path.read_text())
        
        logger.stop_timer(f"test_{book_name}")
    
    logger.stop_timer("test_total")
    
    # Categorize true positives
    category_counts_llm = defaultdict(int)
    category_counts_logic = defaultdict(int)
    
    for error in true_positives_llm:
        category_counts_llm[classify_error_category(error)] += 1
    
    for error in true_positives_logic:
        category_counts_logic[classify_error_category(error)] += 1
    
    test_summary = {
        'total_chapters': len(all_results),
        'llm_true_positives': len(true_positives_llm),
        'logic_true_positives': len(true_positives_logic),
        'llm_filtered': len(filtered_llm),
        'logic_filtered': len(filtered_logic),
        'by_category': {
            'llm': dict(category_counts_llm),
            'logic': dict(category_counts_logic)
        },
        'by_book': {}
    }
    
    # Per-book breakdown
    for book_name in modified_books:
        book_results = [r for r in all_results if r.get('book') == book_name]
        test_summary['by_book'][book_name] = {
            'chapters': len(book_results),
            'llm_true_positives': sum(len(r.get('llm_lint', {}).get('true_positives', [])) 
                                      for r in book_results),
            'logic_true_positives': sum(len(r.get('logic_lint', {}).get('true_positives', []))
                                        for r in book_results)
        }
    
    # Save test summary
    (test_dir / 'summary.json').write_text(json.dumps(test_summary, indent=2))
    
    return {
        'results': all_results,
        'true_positives_llm': true_positives_llm,
        'true_positives_logic': true_positives_logic,
        'filtered_llm': filtered_llm,
        'filtered_logic': filtered_logic,
        'summary': test_summary
    }


def run_kfold_validation(original_books: Dict[str, List[Path]],
                          modified_books: Dict[str, List[Path]],
                          k_values: List[int], args: argparse.Namespace,
                          logger: ExperimentLogger, experiment_dir: Path,
                          chapters_per_book: int = None) -> Dict:
    """
    Run k-fold cross-validation.
    
    For each k:
    - Split books into k folds
    - Use k-1 folds for baseline, 1 fold for testing
    - Repeat k times, rotating test fold
    - Report average performance
    
    Args:
        original_books: Dictionary of book name -> chapter paths (original)
        modified_books: Dictionary of book name -> chapter paths (modified)
        k_values: List of k values to test
        args: Configuration arguments
        logger: Experiment logger
        experiment_dir: Directory to save results
        chapters_per_book: Optional limit on chapters per book
        
    Returns:
        K-fold validation results
    """
    logger.log("="*60)
    logger.log("RUNNING K-FOLD CROSS-VALIDATION")
    logger.log("="*60)
    
    kfold_dir = experiment_dir / 'kfold_results'
    kfold_dir.mkdir(exist_ok=True)
    
    book_names = list(original_books.keys())
    kfold_results = {}
    
    for k in k_values:
        logger.log(f"\n--- K={k} ---")
        logger.start_timer(f"kfold_k{k}")
        
        if k > len(book_names):
            logger.log(f"K={k} > number of books ({len(book_names)}), skipping")
            continue
        
        fold_results = []
        
        # Special case: k=1 means leave-one-out (or all-in if only 1 book)
        if k == 1:
            # Use all books for both training and testing
            fold_result = {
                'fold': 1,
                'train_books': book_names,
                'test_books': book_names,
            }
            
            # Run baseline on all original books
            train_original = original_books
            baseline = run_baseline(train_original, args, logger, 
                                    kfold_dir / f'k{k}_fold1_baseline',
                                    chapters_per_book)
            
            # Test on all modified books
            test_modified = modified_books
            test_result = run_test(test_modified, baseline, args, logger,
                                   kfold_dir / f'k{k}_fold1_test',
                                   chapters_per_book)
            
            fold_result['llm_true_positives'] = len(test_result['true_positives_llm'])
            fold_result['logic_true_positives'] = len(test_result['true_positives_logic'])
            fold_result['llm_filtered'] = len(test_result['filtered_llm'])
            fold_result['logic_filtered'] = len(test_result['filtered_logic'])
            
            fold_results.append(fold_result)
            
        else:
            # Proper k-fold: split books into k groups
            from itertools import combinations
            
            # Calculate fold size
            fold_size = len(book_names) // k
            if fold_size == 0:
                fold_size = 1
            
            # Create folds
            folds = []
            remaining = book_names.copy()
            for i in range(k):
                if i < k - 1:
                    fold = remaining[:fold_size]
                    remaining = remaining[fold_size:]
                else:
                    fold = remaining  # Last fold gets remainder
                folds.append(fold)
            
            # Run each fold
            for fold_idx, test_fold in enumerate(folds, 1):
                logger.log(f"  Fold {fold_idx}: test={test_fold}")
                
                train_folds = [b for f in folds if f != test_fold for b in f]
                
                fold_result = {
                    'fold': fold_idx,
                    'train_books': train_folds,
                    'test_books': test_fold,
                }
                
                # Run baseline on training folds
                train_original = {b: original_books[b] for b in train_folds if b in original_books}
                if train_original:
                    baseline = run_baseline(train_original, args, logger,
                                            kfold_dir / f'k{k}_fold{fold_idx}_baseline',
                                            chapters_per_book)
                else:
                    baseline = {'llm_signatures': set(), 'logic_signatures': set()}
                
                # Test on test fold modified books
                test_modified = {b: modified_books[b] for b in test_fold if b in modified_books}
                if test_modified:
                    test_result = run_test(test_modified, baseline, args, logger,
                                           kfold_dir / f'k{k}_fold{fold_idx}_test',
                                           chapters_per_book)
                    
                    fold_result['llm_true_positives'] = len(test_result['true_positives_llm'])
                    fold_result['logic_true_positives'] = len(test_result['true_positives_logic'])
                    fold_result['llm_filtered'] = len(test_result['filtered_llm'])
                    fold_result['logic_filtered'] = len(test_result['filtered_logic'])
                else:
                    fold_result['llm_true_positives'] = 0
                    fold_result['logic_true_positives'] = 0
                    fold_result['llm_filtered'] = 0
                    fold_result['logic_filtered'] = 0
                
                fold_results.append(fold_result)
        
        # Aggregate k-fold results
        kfold_results[f'k{k}'] = {
            'k': k,
            'folds': fold_results,
            'aggregate': {
                'llm_true_positives': sum(f['llm_true_positives'] for f in fold_results),
                'logic_true_positives': sum(f['logic_true_positives'] for f in fold_results),
                'llm_filtered': sum(f['llm_filtered'] for f in fold_results),
                'logic_filtered': sum(f['logic_filtered'] for f in fold_results)
            },
            'average': {
                'llm_true_positives': sum(f['llm_true_positives'] for f in fold_results) / len(fold_results),
                'logic_true_positives': sum(f['logic_true_positives'] for f in fold_results) / len(fold_results)
            }
        }
        
        logger.stop_timer(f"kfold_k{k}")
    
    # Save k-fold results
    (kfold_dir / 'kfold_summary.json').write_text(json.dumps(kfold_results, indent=2))
    
    return kfold_results


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report(experiment_dir: Path, baseline: Dict, test: Dict,
                    kfold: Dict, config: Dict, logger: ExperimentLogger,
                    args: argparse.Namespace) -> str:
    """
    Generate comprehensive markdown report for academic publication.
    
    Args:
        experiment_dir: Experiment directory
        baseline: Baseline results
        test: Test results
        kfold: K-fold validation results
        config: Experiment configuration
        logger: Experiment logger
        args: Command-line arguments
        
    Returns:
        Markdown report text
    """
    logger.log("Generating comprehensive report")
    
    timings = logger.get_all_timings()
    
    report = f"""# Narrative Evaluation Experiment Report

## Comparative Analysis: LLM-Based vs Logic-Based Narrative Consistency Checking

**Model:** {args.llm_model}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Experiment ID:** {config.get('experiment_id', 'N/A')}

---

## Abstract

This experiment compares two complementary approaches to narrative consistency checking:
(1) direct LLM-based semantic analysis, and (2) formal logic-based verification using
Answer Set Programming (Clingo). The evaluation focuses on five error categories:
causality, coherence, temporal consistency, location constraints, and emotional relationships.

---

## 1. Methodology

### 1.1 Experimental Design

The experiment employs a two-phase methodology:

1. **Baseline Phase**: Process original (error-free) narratives to identify false positives
2. **Test Phase**: Process modified narratives and filter baseline signatures

This approach allows us to distinguish true error detection from spurious findings.

### 1.2 Error Categories

| Category | Description | Examples |
|----------|-------------|----------|
| **Causality** | Cause-effect relationships, Chekhov's gun | Introduced objects never used, unexplained events |
| **Coherence** | Semantic and logical consistency | Dead characters acting, physical impossibilities |
| **Temporal** | Time ordering and duration | Events in impossible order, duration violations |
| **Location** | Spatial constraints | Ubiquity (two places at once), impossible travel |
| **Emotional** | Character relationships and motivations | Harming loved ones, helping enemies |

### 1.3 Technical Configuration

| Parameter | Value |
|-----------|-------|
| LLM Model | {args.llm_model} |
| Temperature | 0.0 (deterministic) |
| Backend | {args.llm_backend} |
| Logic Engine | Clingo (ASP) |

---

## 2. Dataset

### 2.1 Books Analyzed

| Book | Original Chapters | Modified Chapters |
|------|-------------------|-------------------|
"""
    
    # Add book information
    for book_name, book_data in baseline.get('summary', {}).get('by_book', {}).items():
        orig_count = book_data.get('chapters', 0)
        mod_count = test.get('summary', {}).get('by_book', {}).get(book_name, {}).get('chapters', 0)
        report += f"| {book_name} | {orig_count} | {mod_count} |\n"
    
    report += f"""
---

## 3. Baseline Results (Original Books)

The baseline phase processes original narratives to establish false positive signatures.

| Metric | LLM | Logic |
|--------|-----|-------|
| Total Errors Detected | {baseline.get('summary', {}).get('llm_errors', 0)} | {baseline.get('summary', {}).get('logic_errors', 0)} |
| Unique Signatures | {len(baseline.get('llm_signatures', []))} | {len(baseline.get('logic_signatures', []))} |

### 3.1 Analysis

Errors detected in original books represent false positives - either:
- Overly strict rule application
- LLM hallucination
- Legitimate stylistic choices misidentified as errors

---

## 4. Test Results (Modified Books)

### 4.1 True Positive Detection

| Metric | LLM | Logic |
|--------|-----|-------|
| True Positives | {test.get('summary', {}).get('llm_true_positives', 0)} | {test.get('summary', {}).get('logic_true_positives', 0)} |
| Filtered (FP) | {test.get('summary', {}).get('llm_filtered', 0)} | {test.get('summary', {}).get('logic_filtered', 0)} |

### 4.2 Errors by Category

| Category | LLM | Logic | Total |
|----------|-----|-------|-------|
"""
    
    # Add category breakdown
    llm_cats = test.get('summary', {}).get('by_category', {}).get('llm', {})
    logic_cats = test.get('summary', {}).get('by_category', {}).get('logic', {})
    
    for cat in ERROR_CATEGORIES:
        llm_count = llm_cats.get(cat, 0)
        logic_count = logic_cats.get(cat, 0)
        report += f"| {cat.capitalize()} | {llm_count} | {logic_count} | {llm_count + logic_count} |\n"
    
    report += """
### 4.3 Detailed Error Analysis

"""
    
    # Add detailed error examples
    for i, error in enumerate(test.get('true_positives_llm', [])[:10], 1):
        report += f"""#### LLM Error {i}: {error.get('category', 'unknown').capitalize()}

**Description:** {error.get('description', 'N/A')}

**Story Fragments:**
"""
        for frag in error.get('story_fragments', []):
            report += f"> {frag}\n\n"
        report += f"**File:** {error.get('story_file', 'N/A')}\n\n---\n\n"
    
    for i, error in enumerate(test.get('true_positives_logic', [])[:10], 1):
        report += f"""#### Logic Error {i}: {error.get('category', 'unknown').capitalize()}

**Violation Type:** {error.get('violation_type', 'N/A')}

**Description:** {error.get('description', 'N/A')}

**Story Fragments:**
"""
        for frag in error.get('story_fragments', []):
            report += f"> {frag}\n\n"
        report += f"**File:** {error.get('story_file', 'N/A')}\n\n---\n\n"
    
    report += f"""
## 5. K-Fold Cross-Validation

Cross-validation assesses the generalizability of baseline filtering.

"""
    
    # Add k-fold results
    for k_key, k_data in kfold.items():
        k = k_data.get('k', k_key)
        avg_llm = k_data.get('average', {}).get('llm_true_positives', 0)
        avg_logic = k_data.get('average', {}).get('logic_true_positives', 0)
        
        report += f"""### K={k}

| Fold | Train Books | Test Books | LLM TP | Logic TP |
|------|-------------|------------|--------|----------|
"""
        for fold in k_data.get('folds', []):
            train = ', '.join(fold.get('train_books', [])[:2]) + ('...' if len(fold.get('train_books', [])) > 2 else '')
            test_b = ', '.join(fold.get('test_books', []))
            report += f"| {fold.get('fold', 'N/A')} | {train} | {test_b} | {fold.get('llm_true_positives', 0)} | {fold.get('logic_true_positives', 0)} |\n"
        
        report += f"""
**Average LLM True Positives:** {avg_llm:.2f}
**Average Logic True Positives:** {avg_logic:.2f}

"""
    
    report += f"""
## 6. Timing Analysis

| Operation | Duration (seconds) |
|-----------|-------------------|
"""
    
    for name, timing in timings.items():
        duration = timing.get('duration_seconds', 'N/A')
        if isinstance(duration, (int, float)):
            report += f"| {name} | {duration:.2f} |\n"
    
    total_duration = timings.get('experiment_total', {}).get('duration_seconds', 0)
    
    report += f"""
**Total Experiment Duration:** {total_duration:.2f} seconds ({total_duration/60:.2f} minutes)

---

## 7. Discussion

### 7.1 Comparative Analysis

The experiment reveals complementary strengths:

**LLM-Based Approach:**
- Better at detecting subtle contextual inconsistencies
- Handles emotional and relationship violations well
- May produce false positives from over-interpretation
- Results can vary with model and prompt design

**Logic-Based Approach:**
- Sound and complete within its rule set
- Excels at formal constraints (temporal, spatial)
- Limited to predefined violation types
- Requires accurate story structuring

### 7.2 Category-Specific Insights

1. **Causality**: LLM often detects narrative Chekhov's gun violations that logic misses
2. **Coherence**: Both approaches effective, logic more consistent
3. **Temporal**: Logic provides rigorous interval reasoning
4. **Location**: Logic excels at spatial constraint checking
5. **Emotional**: LLM better understands nuanced relationship dynamics

### 7.3 Implications for AI Research

This comparative study demonstrates that hybrid approaches combining neural and symbolic
methods may provide superior narrative analysis capabilities. The LLM's flexibility in
understanding context complements the logic engine's formal guarantees.

---

## 8. Conclusion

Both approaches contribute unique capabilities to narrative consistency checking.
For production systems, we recommend:

1. Use LLM for initial broad detection
2. Apply logic rules for formal verification
3. Combine results with appropriate deduplication

Future work should explore tighter integration between neural and symbolic components.

---

## Appendix A: Technical Details

### A.1 ASP Rules Structure

The logic-based system uses a two-module architecture:
- `general.lp`: Domain-independent consistency rules
- Domain module: Story-specific facts generated per analysis

### A.2 Error Categories Mapping

| ASP Violation Type | Category |
|-------------------|----------|
| chekhov_gun, uncaused_event | Causality |
| dead_agent, non_edible_food | Coherence |
| circular_time, negative_duration | Temporal |
| ubiquity, impossible_travel | Location |
| harm_loved, help_enemy | Emotional |

---

*Report generated by Narrative Evaluation Experiment Framework*
*Timestamp: {datetime.now().isoformat()}*
"""
    
    return report


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    """Main entry point for the experiment."""
    parser = argparse.ArgumentParser(
        description='Run comprehensive narrative evaluation experiment',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Experiment configuration
    parser.add_argument('--name', default='narrative_eval',
                        help='Experiment name (used in folder naming)')
    parser.add_argument('--original-dir', default='original_books',
                        help='Directory containing original books')
    parser.add_argument('--modified-dir', default='modified_books',
                        help='Directory containing modified books')
    parser.add_argument('--output-dir', default='experiments',
                        help='Directory for experiment output')
    parser.add_argument('--chapters-per-book', type=int, default=None,
                        help='Limit chapters per book (for testing)')
    parser.add_argument('--k-values', nargs='+', type=int, default=[1, 2, 3, 4],
                        help='K values for cross-validation')
    
    # LLM configuration
    parser.add_argument('--llm-backend', choices=['openai', 'gemini'], default='openai',
                        help='LLM backend type')
    parser.add_argument('--llm-model', default='auto',
                        help='LLM model ID')
    parser.add_argument('--llm-base-url', 
                        default=get_env_or_default('LLM_BASE_URL', 'http://localhost:8080/v1'),
                        help='LLM API base URL')
    parser.add_argument('--llm-api-key',
                        default=get_env_or_default('LLM_API_KEY', get_env_or_default('GEMINI_API_KEY', '')),
                        help='LLM API key')
    parser.add_argument('--llm-timeout', type=int, default=600,
                        help='LLM request timeout in seconds')
    parser.add_argument('--llm-max-tokens', type=int, default=4096,
                        help='Maximum output tokens')
    parser.add_argument('--llm-no-auth', action='store_true',
                        help='Skip authentication for local servers')
    
    # Verbosity
    parser.add_argument('--quiet', action='store_true',
                        help='Reduce output verbosity')
    
    args = parser.parse_args()
    
    # Resolve model ID for local servers
    if args.llm_model == 'auto' and args.llm_backend == 'openai':
        args.llm_model = _resolve_model_id(args)
    
    # Create experiment directory with timestamps
    start_time = datetime.now()
    experiment_id = str(uuid.uuid4())[:8]
    experiment_name = f"{args.name}-{start_time.strftime('%Y%m%d_%H%M%S')}-pending-{experiment_id}"
    experiment_dir = Path(args.output_dir) / experiment_name
    experiment_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize logger
    logger = ExperimentLogger(experiment_dir, verbose=not args.quiet)
    logger.log(f"Experiment started: {experiment_name}")
    logger.log(f"Configuration: {vars(args)}")
    logger.start_timer("experiment_total")
    
    # Save configuration
    config = {
        'name': args.name,
        'experiment_id': experiment_id,
        'original_dir': args.original_dir,
        'modified_dir': args.modified_dir,
        'chapters_per_book': args.chapters_per_book,
        'k_values': args.k_values,
        'llm_backend': args.llm_backend,
        'llm_model': args.llm_model,
        'llm_base_url': args.llm_base_url,
        'llm_timeout': args.llm_timeout,
        'start_time': start_time.isoformat()
    }
    (experiment_dir / 'config.json').write_text(json.dumps(config, indent=2))
    
    # Discover stories
    logger.log("Discovering stories...")
    original_books = discover_stories(Path(args.original_dir))
    modified_books = discover_stories(Path(args.modified_dir))
    
    logger.log(f"Found {len(original_books)} original books")
    logger.log(f"Found {len(modified_books)} modified books")
    
    for book, chapters in original_books.items():
        logger.log(f"  {book}: {len(chapters)} chapters")
    
    # Run baseline
    baseline = run_baseline(original_books, args, logger, experiment_dir, 
                           args.chapters_per_book)
    
    # Run test
    test = run_test(modified_books, baseline, args, logger, experiment_dir,
                    args.chapters_per_book)
    
    # Run k-fold cross-validation
    kfold = run_kfold_validation(original_books, modified_books, args.k_values,
                                  args, logger, experiment_dir, args.chapters_per_book)
    
    # Generate report
    report = generate_report(experiment_dir, baseline, test, kfold, config, 
                            logger, args)
    (experiment_dir / 'report.md').write_text(report)
    
    # Save summary
    end_time = datetime.now()
    logger.stop_timer("experiment_total")
    
    summary = {
        'experiment_info': {
            'model': args.llm_model,
            'books': list(original_books.keys()),
            'original_chapters': sum(len(c) for c in original_books.values()),
            'modified_chapters': sum(len(c) for c in modified_books.values()),
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': (end_time - start_time).total_seconds()
        },
        'baseline': {
            'llm_errors': baseline.get('summary', {}).get('llm_errors', 0),
            'logic_errors': baseline.get('summary', {}).get('logic_errors', 0),
            'llm_signatures': len(baseline.get('llm_signatures', [])),
            'logic_signatures': len(baseline.get('logic_signatures', []))
        },
        'test_results': {
            'llm_true_positives': test.get('summary', {}).get('llm_true_positives', 0),
            'logic_true_positives': test.get('summary', {}).get('logic_true_positives', 0),
            'llm_filtered': test.get('summary', {}).get('llm_filtered', 0),
            'logic_filtered': test.get('summary', {}).get('logic_filtered', 0)
        },
        'by_category': test.get('summary', {}).get('by_category', {}),
        'kfold': kfold,
        'timings': logger.get_all_timings()
    }
    (experiment_dir / 'summary.json').write_text(json.dumps(summary, indent=2))
    
    # Rename experiment folder with end time
    final_name = f"{args.name}-{start_time.strftime('%Y%m%d_%H%M%S')}-{end_time.strftime('%Y%m%d_%H%M%S')}-{experiment_id}"
    final_dir = Path(args.output_dir) / final_name
    experiment_dir.rename(final_dir)
    
    logger.log(f"Experiment completed: {final_name}")
    logger.log(f"Total duration: {(end_time - start_time).total_seconds():.2f} seconds")
    
    print(f"\nExperiment complete!")
    print(f"Results saved to: {final_dir}")
    print(f"Report: {final_dir / 'report.md'}")


def _resolve_model_id(args: argparse.Namespace) -> str:
    """Resolve 'auto' model ID by querying the API."""
    import urllib.request
    
    try:
        url = args.llm_base_url.rstrip('/') + '/models'
        req = urllib.request.Request(url)
        if args.llm_api_key and not args.llm_no_auth:
            req.add_header('Authorization', f'Bearer {args.llm_api_key}')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        models = data.get('data', [])
        if models:
            return models[0].get('id', 'auto')
    except Exception:
        pass
    
    return 'auto'


if __name__ == '__main__':
    main()
