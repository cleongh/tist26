#!/usr/bin/env python3
"""
run_narrative_experiment.py - Chapter-by-Chapter Narrative Evaluation Experiment
=================================================================================

This script implements a two-step research experiment comparing LLM-based vs
Logic-based narrative evaluation. Each chapter is processed SEPARATELY.

STEP 1: LLM-Only Evaluation
───────────────────────────
- Process each chapter file separately
- Send each chapter to LLM on port 8080
- Collect errors for each chapter
- Save results to step1_llm_results.json

(External: Restart LLM server between steps if needed)

STEP 2: Logic-Based Evaluation (ILASP + Clingo)
───────────────────────────────────────────────
- Process each chapter file separately
- Use LLM to structure chapter into JSON
- Use ILASP to learn rules incrementally (per story)
- Use Clingo to detect violations
- Save results to step2_logic_results.json

OUTPUT:
───────
- step1_llm_results.json     - Errors from LLM-only evaluation
- step2_logic_results.json   - Errors from Logic-based evaluation
- experiment_summary.json    - Comparison of both steps

USAGE:
──────
    # Step 1: LLM-only evaluation
    python scripts/run_narrative_experiment.py --step 1 --experiment-name "my_exp"
    
    # (Restart LLM server externally if needed)
    
    # Step 2: Logic-based evaluation
    python scripts/run_narrative_experiment.py --step 2 --experiment-name "my_exp"
    
    # Generate comparison summary
    python scripts/run_narrative_experiment.py --summarize --experiment-name "my_exp"

Author: Research Project - Narrative Evaluation
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# PATHS AND CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
SOURCE_ORIGINAL_BOOKS = REPO_ROOT / "original_books"
SOURCE_MODIFIED_BOOKS = REPO_ROOT / "modified_books"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
RULES_DIR = REPO_ROOT / "rules"
ERRORS_CHECKLIST_DIR = REPO_ROOT / "errors_checklist"

# Add script dir and repo root to path for imports
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT))  # For engine module imports

# =============================================================================
# API CONFIGURATION
# =============================================================================
# Set these environment variables before running:
#   export GEMINI_API_KEY="your-gemini-api-key"
#   export OPENAI_API_KEY="your-openai-api-key"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Default models for each API provider
DEFAULT_MODELS = {
    "local": "auto",
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o",
}

# API mode: "local" | "gemini" | "openai"
API_MODE = "local"

# =============================================================================
# CHARACTER ID NORMALIZATION
# =============================================================================
# Map character aliases to canonical IDs to ensure consistency across chapters.
# Characters may be referred to differently (e.g., "uncle_vernon" vs "mr_dursley").
# This mapping ensures rules established for one ID apply to all aliases.

CHAR_ALIASES = {
    # Harry Potter character aliases
    'uncle_vernon': 'vernon_dursley',
    'vernon': 'vernon_dursley',
    'mr_dursley': 'vernon_dursley',
    'aunt_petunia': 'petunia_dursley',
    'petunia': 'petunia_dursley',
    'mrs_dursley': 'petunia_dursley',
    'dudley': 'dudley_dursley',
    'harry': 'harry_potter',
    'potter': 'harry_potter',
    'ron': 'ron_weasley',
    'hermione': 'hermione_granger',
    'dumbledore': 'albus_dumbledore',
    'professor_dumbledore': 'albus_dumbledore',
    'snape': 'severus_snape',
    'professor_snape': 'severus_snape',
    'mcgonagall': 'minerva_mcgonagall',
    'professor_mcgonagall': 'minerva_mcgonagall',
    'hagrid': 'rubeus_hagrid',
    'voldemort': 'lord_voldemort',
    'you_know_who': 'lord_voldemort',
    'he_who_must_not_be_named': 'lord_voldemort',
    'the_dark_lord': 'lord_voldemort',
    
    # Generic family relation aliases (less specific)
    'uncle': 'uncle',  # Keep as-is if no specific match
    'aunt': 'aunt',
    'mother': 'mother',
    'father': 'father',
}

def normalize_character_id(char_id: str) -> str:
    """
    Normalize a character ID to its canonical form.
    This ensures that 'uncle_vernon' and 'mr_dursley' both map to 'vernon_dursley'.
    """
    if not char_id:
        return char_id
    char_lower = char_id.lower().strip()
    return CHAR_ALIASES.get(char_lower, char_lower)


# Stories to process
STORIES = [
    "Harry Potter",
    "The Hunger Games",
    "The Lord of the Rings",
    "Twilight",
    "Goosebumps",
]

# Error categories
ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]

# Required fields for structured chapter JSON
REQUIRED_STRUCTURE_FIELDS = {
    "entities": dict,
    "events": list,
}

REQUIRED_ENTITY_FIELDS = {
    "characters": list,
    "locations": list,
}


# =============================================================================
# JSON VALIDATION AND REPAIR
# =============================================================================

def repair_json(text: str) -> str:
    """
    Attempt to repair common JSON formatting issues from LLM output.
    Returns the repaired JSON string.
    """
    import re
    
    # Remove markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
    
    # Extract just the JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return text
    text = match.group()
    
    # Fix common issues:
    # 1. Missing commas between array elements (e.g., } { -> }, {)
    text = re.sub(r'\}\s*\{', '}, {', text)
    text = re.sub(r'\]\s*\[', '], [', text)
    
    # 2. Missing commas after closing braces/brackets before keys
    text = re.sub(r'\}\s*"', '}, "', text)
    text = re.sub(r'\]\s*"', '], "', text)
    
    # 3. Missing commas after string values before keys ("value" "key" -> "value", "key")
    text = re.sub(r'"\s+"', '", "', text)
    
    # 4. Missing commas after values before opening braces/brackets
    text = re.sub(r'"\s*\{', '", {', text)
    text = re.sub(r'"\s*\[', '", [', text)
    
    # 5. Trailing commas before closing braces/brackets
    text = re.sub(r',\s*\}', '}', text)
    text = re.sub(r',\s*\]', ']', text)
    
    # 6. Single quotes to double quotes (for keys/values)
    text = re.sub(r"(?<=[{\[,:])\s*'([^']*?)'\s*(?=[,}\]:])", r'"\1"', text)
    
    # 7. Remove any control characters that might break parsing
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    
    # 8. Fix missing comma after number before quote: 123 "key" -> 123, "key"
    text = re.sub(r'(\d)\s+"', r'\1, "', text)
    
    # 9. Fix missing comma after true/false/null before quote
    text = re.sub(r'(true|false|null)\s+"', r'\1, "', text)
    
    return text


def validate_structure_json(data: Dict) -> Tuple[bool, List[str]]:
    """
    Validate that the parsed JSON has all required fields for chapter structure.
    Returns (is_valid, list_of_missing_fields).
    """
    missing = []
    
    # Check top-level fields
    if "entities" not in data:
        missing.append("entities")
    elif not isinstance(data["entities"], dict):
        missing.append("entities (wrong type)")
    else:
        # Check entities subfields
        entities = data["entities"]
        if "characters" not in entities:
            missing.append("entities.characters")
        elif not isinstance(entities.get("characters"), list):
            missing.append("entities.characters (wrong type)")
            
        if "locations" not in entities:
            missing.append("entities.locations")
        elif not isinstance(entities.get("locations"), list):
            missing.append("entities.locations (wrong type)")
    
    if "events" not in data:
        missing.append("events")
    elif not isinstance(data["events"], list):
        missing.append("events (wrong type)")
    
    return len(missing) == 0, missing


def parse_and_validate_structure_json(response_text: str, max_retries: int = 0) -> Tuple[Dict, bool, str]:
    """
    Parse LLM response, repair if needed, and validate structure.
    Returns (parsed_data, is_valid, error_message).
    
    If parsing fails after repair, returns empty structure with is_valid=False.
    """
    # First, try to repair the JSON
    repaired = repair_json(response_text)
    
    # Try to parse
    try:
        data = json.loads(repaired)
    except json.JSONDecodeError as e:
        return {"entities": {"characters": [], "locations": []}, "events": []}, False, f"JSON parse error: {e}"
    
    # Validate structure
    is_valid, missing = validate_structure_json(data)
    if not is_valid:
        return data, False, f"Missing fields: {', '.join(missing)}"
    
    # Ensure all required substructures exist with correct types
    if "entities" not in data:
        data["entities"] = {}
    if "characters" not in data["entities"]:
        data["entities"]["characters"] = []
    if "locations" not in data["entities"]:
        data["entities"]["locations"] = []
    if "events" not in data:
        data["events"] = []
    
    return data, True, ""


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ChapterError:
    """An error detected in a specific chapter."""
    chapter_file: str
    category: str
    error_type: str
    description: str
    story_fragment: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ChapterResult:
    """Result of evaluating a single chapter."""
    story_name: str
    variant: str  # "original" or "modified"
    chapter_file: str
    chapter_number: int
    errors: List[ChapterError] = field(default_factory=list)
    duration_seconds: float = 0.0
    success: bool = True
    error_message: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "story_name": self.story_name,
            "variant": self.variant,
            "chapter_file": self.chapter_file,
            "chapter_number": self.chapter_number,
            "error_count": len(self.errors),
            "errors": [e.to_dict() for e in self.errors],
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass 
class StepResults:
    """Results from one step of the experiment."""
    step: int
    approach: str  # "llm" or "logic"
    timestamp: str
    chapters_processed: int = 0
    total_errors: int = 0
    results: List[ChapterResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "step": self.step,
            "approach": self.approach,
            "timestamp": self.timestamp,
            "chapters_processed": self.chapters_processed,
            "total_errors": self.total_errors,
            "results": [r.to_dict() for r in self.results],
        }


# =============================================================================
# LLM PROMPT
# =============================================================================

# System message for JSON-only output
LLM_SYSTEM_MESSAGE = """You are a narrative error detector. You analyze story chapters and return ONLY valid JSON.

CRITICAL RULES:
- Output ONLY a JSON object, nothing else
- Never continue or extend the story
- Never echo back the input
- Always include a brief summary of the chapter (2-3 sentences covering key events, characters, and locations)
- If no errors found, return: {"error_count": 0, "errors": [], "chapter_summary": "..."}
- If errors found, return: {"error_count": N, "errors": [...], "chapter_summary": "..."}"""

# User prompt: chapter FIRST, then instructions
LLM_LINT_PROMPT = """---BEGIN CHAPTER---
{chapter_text}
---END CHAPTER---
{previous_summaries_section}
Analyze the chapter above for narrative consistency errors. Consider both within-chapter inconsistencies and contradictions with previous chapters (if summaries are provided above).

ERROR CATEGORIES:
- causality: unexplained effects, missing causes
- coherence: logical impossibilities, contradictions
- temporal: wrong event order, time paradoxes  
- location: impossible travel, characters in two places
- emotional: actions contradicting established relationships
- cross_chapter: contradictions with events/facts from previous chapters

For each error found, include the exact quote from the chapter that contains the error.

Respond with JSON only:
{{"error_count": N, "errors": [{{"category": "causality|coherence|temporal|location|emotional|cross_chapter", "description": "brief description of the error", "error_text": "exact quote from chapter with the error"}}], "chapter_summary": "A brief 2-3 sentence summary of key events, characters introduced, and important facts established in this chapter"}}"""


# =============================================================================
# LOGGING
# =============================================================================

# Global log file handle (set by main when experiment starts)
_console_log_file = None

def set_console_log_file(file_path: Path):
    """Set the file path for console logging."""
    global _console_log_file
    _console_log_file = file_path
    # Create/clear the file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        f.write(f"=== Experiment Log Started: {datetime.now().isoformat()} ===\n\n")

def log(msg: str, level: str = "INFO"):
    """Log a message with timestamp to console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {msg}"
    print(log_line, file=sys.stderr)
    
    # Also write to file if configured
    if _console_log_file:
        try:
            with open(_console_log_file, "a") as f:
                f.write(log_line + "\n")
        except Exception:
            pass  # Don't fail on log write errors


# =============================================================================
# API CLIENTS (Gemini and OpenAI)
# =============================================================================

class GeminiAPIClient:
    """Client for Google Gemini API."""
    
    def __init__(self, model: str = "gemini-2.0-flash", temperature: float = 0.0, api_delay: float = 0.0):
        self.model = model
        self.temperature = temperature
        self.api_delay = api_delay
        self._client = None
        self._last_call_time = 0
        
    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                if not GEMINI_API_KEY:
                    raise ValueError("GEMINI_API_KEY environment variable not set")
                genai.configure(api_key=GEMINI_API_KEY)
                self._client = genai.GenerativeModel(self.model)
            except ImportError:
                raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
        return self._client
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
        """Make a Gemini API call and return the response text."""
        import google.generativeai as genai
        
        # Rate limiting delay
        if self.api_delay > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.api_delay:
                time.sleep(self.api_delay - elapsed)
        
        client = self._get_client()
        
        system_prompt = "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."
        full_prompt = f"{system_prompt}\n\n{prompt}"
        
        generation_config = genai.GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=max_tokens,
        )
        
        response = client.generate_content(
            full_prompt,
            generation_config=generation_config,
        )
        
        self._last_call_time = time.time()
        return response.text
    
    def check_server(self) -> bool:
        """Check if Gemini API is available."""
        try:
            self._get_client()
            return True
        except Exception as e:
            log(f"Gemini API check failed: {e}", "ERROR")
            return False


class OpenAIAPIClient:
    """Client for OpenAI API."""
    
    def __init__(self, model: str = "gpt-4o", temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self._client = None
        
    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                if not OPENAI_API_KEY:
                    raise ValueError("OPENAI_API_KEY environment variable not set")
                self._client = OpenAI(api_key=OPENAI_API_KEY)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
        """Make an OpenAI API call and return the response text."""
        client = self._get_client()
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."},
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content
    
    def check_server(self) -> bool:
        """Check if OpenAI API is available."""
        try:
            self._get_client()
            return True
        except Exception as e:
            log(f"OpenAI API check failed: {e}", "ERROR")
            return False


class LocalLLMClient:
    """Client for local LLM server (llamafile, llama.cpp, etc.)."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
        """Make a local LLM call and return the response text."""
        import urllib.request
        
        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "repetition_penalty": 1.1,
        }
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
    
    def check_server(self) -> bool:
        """Check if local LLM server is available."""
        import urllib.request
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False


def create_api_client(api_mode: str, api_model: str = None, base_url: str = "http://localhost:8080/v1", api_delay: float = 0.0):
    """Factory function to create the appropriate API client."""
    if api_mode == "gemini":
        model = api_model or DEFAULT_MODELS["gemini"]
        log(f"Using Gemini API with model: {model}", "INFO")
        if api_delay > 0:
            log(f"Rate limit delay: {api_delay}s between API calls", "INFO")
        return GeminiAPIClient(model=model, api_delay=api_delay)
    elif api_mode == "openai":
        model = api_model or DEFAULT_MODELS["openai"]
        log(f"Using OpenAI API with model: {model}", "INFO")
        return OpenAIAPIClient(model=model)
    else:  # local
        log(f"Using local LLM at: {base_url}", "INFO")
        return LocalLLMClient(base_url=base_url)


# =============================================================================
# LLM CLIENT
# =============================================================================

class LLMClient:
    """Simple LLM client for chapter evaluation."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0, log_file: Path = None,
                 api_mode: str = "local", api_model: str = None, api_delay: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.log_file = log_file
        self.api_mode = api_mode
        self.api_model = api_model
        # Create the appropriate API client
        self.api_client = create_api_client(api_mode, api_model, base_url, api_delay)
        
        # Initialize log file with empty list
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "w") as f:
                f.write("")  # Clear/create file
    
    def _log_interaction(self, story: str, variant: str, chapter: str, prompt: str, response: str, errors: List[Dict], duration: float):
        """Log a prompt/response interaction to the log file."""
        if not self.log_file:
            return
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "story": story,
            "variant": variant,
            "chapter": chapter,
            "duration_seconds": duration,
            "prompt_length": len(prompt),
            "response_length": len(response),
            "errors_detected": len(errors),
            "prompt": prompt,
            "response": response,
            "parsed_errors": errors,
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def check_server(self) -> bool:
        """Check if LLM server is available."""
        return self.api_client.check_server()
    
    def evaluate_chapter(self, chapter_text: str, story: str = "", variant: str = "", chapter_name: str = "", 
                          previous_summaries: List[str] = None) -> Tuple[List[Dict], float, str, str, str]:
        """
        Evaluate a single chapter for narrative errors.
        
        Args:
            chapter_text: The text of the chapter to evaluate
            story: Name of the story
            variant: "original" or "modified"
            chapter_name: Name of the chapter file
            previous_summaries: List of summaries from previous chapters for context
        
        Returns:
            Tuple of (list of error dicts, duration in seconds, prompt, response, chapter_summary)
        """
        start_time = time.time()
        
        # Build previous summaries section
        if previous_summaries:
            summaries_text = "\n---PREVIOUS CHAPTER SUMMARIES---\n"
            for i, summary in enumerate(previous_summaries):
                summaries_text += f"Chapter {i + 1}: {summary}\n"
            summaries_text += "---END PREVIOUS SUMMARIES---\n\n"
        else:
            summaries_text = "\n"
        
        prompt = LLM_LINT_PROMPT.format(chapter_text=chapter_text, previous_summaries_section=summaries_text)
        
        response_text = ""
        try:
            # Prepend system message to prompt for API clients
            full_prompt = f"{LLM_SYSTEM_MESSAGE}\n\n{prompt}"
            response_text = self.api_client.extract(full_prompt, max_tokens=1500, timeout=180)
        except Exception as e:
            log(f"LLM request failed: {e}", "ERROR")
            return [], time.time() - start_time, prompt, str(e), ""
        
        duration = time.time() - start_time
        
        # Parse response (now also extracts summary)
        errors, chapter_summary = self._parse_response(response_text)
        
        # Log interaction
        self._log_interaction(story, variant, chapter_name, prompt, response_text, errors, duration)
        
        return errors, duration, prompt, response_text, chapter_summary
    
    def _parse_response(self, response: str) -> Tuple[List[Dict], str]:
        """Parse LLM response into error list and chapter summary.
        
        Returns:
            Tuple of (list of error dicts, chapter summary string)
        """
        # Clean response
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        
        # Find JSON
        start = response.find('{')
        end = response.rfind('}')
        if start == -1 or end == -1:
            log(f"No JSON found in response (length={len(response)})", "WARN")
            log(f"Response preview: {response[:200]}...", "DEBUG")
            return [], ""
        
        try:
            data = json.loads(response[start:end + 1])
            errors = data.get("errors", [])
            chapter_summary = data.get("chapter_summary", "")
            error_count = data.get("error_count", len(errors))
            if error_count > 0:
                log(f"    LLM reported {error_count} errors", "DEBUG")
            if chapter_summary:
                log(f"    Summary: {chapter_summary[:80]}...", "DEBUG")
            return errors, chapter_summary
        except json.JSONDecodeError as e:
            log(f"JSON parse error: {e}", "WARN")
            log(f"JSON preview: {response[start:start+200]}...", "DEBUG")
            return [], ""


# =============================================================================
# LOGIC-BASED EVALUATOR
# =============================================================================

class LogicEvaluator:
    """Logic-based evaluator using ILASP and Clingo."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0, log_file: Path = None,
                 api_mode: str = "local", api_model: str = None, api_delay: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.api_mode = api_mode
        self.api_model = api_model
        # Create the appropriate API client
        self.api_client = create_api_client(api_mode, api_model, base_url, api_delay)
        # Load multiple rule files for comprehensive checking
        self.rule_files = [
            RULES_DIR / "simple_narrative.lp",  # Works with basic extracted facts
            RULES_DIR / "story_rules.lp",       # Dynamic story rules for contradiction detection
            # RULES_DIR / "general.lp",         # Disabled: requires timestamps we don't extract
        ]
        self.mode_declarations = RULES_DIR / "ilasp_mode_declarations.las"
        self.log_file = log_file
        
        # Accumulated knowledge for incremental learning
        self.accumulated_facts: List[str] = []
        self.learned_rules: List[str] = []
        self.chapter_violations_history: List[Dict] = []  # Track violations for ILASP
        
        # Cross-chapter state tracking
        self.dead_characters: set = set()  # Track dead characters permanently
        self.character_emotions: Dict[str, str] = {}  # Track last known emotion per character
        self.established_traits: Dict[str, str] = {}  # Track established character traits
        
        # NEW: Global event ID system (continuous across chapters)
        self.next_event_id: int = 1  # Start from 1, e0 reserved for initial state
        
        # NEW: Event log with source text (for error regeneration)
        self.event_log: List[Dict] = []  # [{id, type, agent, patient, location, source_text, chapter}]
        
        # NEW: Dynamic story rules (modified by events)
        self.story_rules: List[Dict] = []  # [{type, subject, predicate, object, established_by, valid}]
        
        # NEW: Event log file path (set during experiment)
        self.event_log_file: Path = None
        
        # Initialize log file
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "w") as f:
                f.write("")
    
    def _log_interaction(self, story: str, variant: str, chapter: str, step: str, prompt: str, response: str, data: Dict, duration: float):
        """Log a processing step to the log file."""
        if not self.log_file:
            return
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "story": story,
            "variant": variant,
            "chapter": chapter,
            "step": step,
            "duration_seconds": duration,
            "prompt": prompt,
            "response": response,
            "data": data,
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    
    def reset(self):
        """Reset accumulated knowledge (for new story/variant)."""
        self.accumulated_facts = []
        self.learned_rules = []
        self.chapter_violations_history = []  # Track violations for ILASP learning
        self.dead_characters = set()
        self.character_emotions = {}
        self.established_traits = {}
        self.relationships: Dict[Tuple[str, str], str] = {}  # Track relationships between characters
        
        # NEW: Reset global event tracking
        self.next_event_id = 1  # Reset to 1, e0 reserved for initial state
        self.event_log = []
        self.story_rules = []
    
    def _log_events_to_file(self, events: List[Dict], chapter_num: int):
        """Log events with source text to file for debugging."""
        if not self.event_log_file:
            return
        
        for event in events:
            entry = {
                "chapter": chapter_num,
                "event_id": event.get('global_id'),
                "type": event.get('type'),
                "agent": event.get('agent'),
                "patient": event.get('patient'),
                "location": event.get('location'),
                "source_text": event.get('source_text', ''),
            }
            with open(self.event_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
    
    def _assign_global_event_ids(self, events: List[Dict], chapter_num: int) -> List[Dict]:
        """
        Assign continuous global IDs to events and log them.
        Event IDs are continuous across all chapters (e1, e2, ..., eN).
        """
        for event in events:
            event['global_id'] = f"e{self.next_event_id}"
            event['chapter'] = chapter_num
            self.next_event_id += 1
            
            # Add to event log for debugging/analysis
            self.event_log.append({
                'id': event['global_id'],
                'type': event.get('type'),
                'agent': event.get('agent'),
                'patient': event.get('patient'),
                'location': event.get('location'),
                'source_text': event.get('source_text', ''),
                'chapter': chapter_num
            })
        
        return events
    
    def _initialize_story_rules(self, initial_rules: List[Dict], relationships: List[Dict],
                                  character_locations: List[Dict] = None,
                                  character_possessions: List[Dict] = None,
                                  temporal_constraints: List[Dict] = None):
        """
        Initialize story rules from first chapter extraction.
        Called once at the start of a story to establish baseline rules.
        
        Handles:
        - Relationship rules (X hates/loves Y)
        - Trait rules (X is cruel/kind)
        - Location rules (X is at location Y)
        - Possession rules (X has item Y)
        - Temporal constraints (event A must precede event B)
        """
        character_locations = character_locations or []
        character_possessions = character_possessions or []
        temporal_constraints = temporal_constraints or []
        
        # Process explicit initial_rules from LLM
        for rule in initial_rules:
            subject = rule.get('subject', '')
            predicate = rule.get('predicate', '')
            obj = rule.get('object', '')
            
            if subject and predicate:
                rule_type = 'trait' if obj == 'true' else 'relationship'
                self.story_rules.append({
                    'type': rule_type,
                    'subject': subject,
                    'predicate': predicate,
                    'object': obj if obj != 'true' else None,
                    'established_by': 'e0',  # Initial state (before any events)
                    'valid': True
                })
                log(f"    Initial rule: {subject} {predicate} {obj}", "DEBUG")
        
        # Also convert extracted relationships to rules
        for rel in relationships:
            from_char = rel.get('from', '')
            to_char = rel.get('to', '')
            rel_type = rel.get('type', '')
            
            if from_char and to_char and rel_type:
                # Map relationship types to rule predicates
                predicate_map = {
                    'hostile': 'hates',
                    'friendly': 'friendly',
                    'family': 'family',
                    'love': 'loves',
                    'fear': 'fears'
                }
                predicate = predicate_map.get(rel_type, rel_type)
                
                self.story_rules.append({
                    'type': 'relationship',
                    'subject': from_char,
                    'predicate': predicate,
                    'object': to_char,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Relationship rule: {from_char} {predicate} {to_char}", "DEBUG")
        
        # Process character locations
        for loc_rule in character_locations:
            char = loc_rule.get('character', '')
            location = loc_rule.get('location', '')
            
            if char and location:
                self.story_rules.append({
                    'type': 'location',
                    'subject': char,
                    'predicate': 'at',
                    'object': location,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Location rule: {char} at {location}", "DEBUG")
        
        # Process character possessions
        for poss_rule in character_possessions:
            char = poss_rule.get('character', '')
            item = poss_rule.get('item', '')
            
            if char and item:
                self.story_rules.append({
                    'type': 'possession',
                    'subject': char,
                    'predicate': 'has',
                    'object': item,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Possession rule: {char} has {item}", "DEBUG")
        
        # Process temporal constraints
        for temp_rule in temporal_constraints:
            first_type = temp_rule.get('first_event_type', '')
            second_type = temp_rule.get('second_event_type', '')
            
            if first_type and second_type:
                self.story_rules.append({
                    'type': 'temporal',
                    'subject': first_type,
                    'predicate': 'must_precede',
                    'object': second_type,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Temporal rule: {first_type} must_precede {second_type}", "DEBUG")
        
        log(f"  Initialized {len(self.story_rules)} story rules", "INFO")
    
    def _update_rules_from_events(self, events: List[Dict]):
        """
        Update story rules based on modifier events.
        Events like 'forgive', 'betray', etc. can modify existing relationship rules.
        """
        # Modifiers that change negative relationships to positive
        positive_modifiers = {
            'forgive', 'forgives', 'reconcile', 'reconciles', 'apologize', 'apologizes',
            'befriend', 'befriends', 'accept', 'accepts', 'save', 'saves', 'rescue', 'rescues'
        }
        
        # Modifiers that change positive relationships to negative
        negative_modifiers = {
            'betray', 'betrays', 'attack', 'attacks', 'insult', 'insults',
            'abandon', 'abandons', 'deceive', 'deceives', 'hurt', 'hurts',
            'reject', 'rejects', 'steal_from', 'steals_from'
        }
        
        for event in events:
            event_type = event.get('type', '').lower()
            agent = event.get('agent')
            patient = event.get('patient')
            event_id = event.get('global_id')
            
            if not agent or not patient:
                continue
            
            # Check if this event modifies an existing rule
            if event_type in positive_modifiers:
                self._modify_rule(agent, patient, 'friendly', event_id)
                log(f"    Event {event_id} ({event_type}): {agent} → {patient} now friendly", "DEBUG")
            elif event_type in negative_modifiers:
                self._modify_rule(agent, patient, 'hostile', event_id)
                log(f"    Event {event_id} ({event_type}): {agent} → {patient} now hostile", "DEBUG")
    
    def _modify_rule(self, subject: str, obj: str, new_predicate: str, event_id: str):
        """
        Modify an existing rule or create a new one.
        Invalidates the old rule and creates a new rule with the updated predicate.
        """
        def sanitize(v):
            if not v: return "unknown"
            s = str(v).lower()
            s = re.sub(r'[^a-z0-9_]', '_', s)
            s = re.sub(r'_+', '_', s).strip('_')
            return s or "unknown"
        
        subject = sanitize(subject)
        obj = sanitize(obj)
        
        # Find and invalidate existing rule
        for rule in self.story_rules:
            if (rule['type'] == 'relationship' and 
                rule['subject'] == subject and 
                rule['object'] == obj and
                rule['valid']):
                rule['valid'] = False
                log(f"    Invalidated rule: {subject} {rule['predicate']} {obj} (by {event_id})", "DEBUG")
        
        # Create new rule
        self.story_rules.append({
            'type': 'relationship',
            'subject': subject,
            'predicate': new_predicate,
            'object': obj,
            'established_by': event_id,
            'valid': True
        })

    def _accumulate_cross_chapter_state(self, facts: str) -> List[str]:
        """
        Extract and accumulate important cross-chapter state from current facts.
        Returns list of state facts to include in Clingo program.
        """
        state_facts = []
        
        for line in facts.split('\n'):
            line = line.strip()
            
            # Track death events permanently
            if line.startswith('is_dead('):
                match = re.match(r'is_dead\(([^)]+)\)\.', line)
                if match:
                    char = match.group(1)
                    self.dead_characters.add(char)
            
            # Track current emotions to become previous emotions
            if line.startswith('character_emotion('):
                match = re.match(r'character_emotion\(([^,]+),\s*([^)]+)\)\.', line)
                if match:
                    char, emotion = match.group(1), match.group(2)
                    self.character_emotions[char] = emotion
                    # Strong emotions become established traits
                    if emotion in ['nasty', 'kind', 'hostile', 'friendly', 'cruel', 'warm', 'cold']:
                        if char not in self.established_traits:
                            self.established_traits[char] = emotion
            
            # Track relationships permanently (they don't usually change)
            if line.startswith('relationship('):
                match = re.match(r'relationship\(([^,]+),\s*([^,]+),\s*([^)]+)\)\.', line)
                if match:
                    char1, char2, rel_type = match.group(1), match.group(2), match.group(3)
                    self.relationships[(char1, char2)] = rel_type
        
        # Generate state facts for Clingo
        for char in self.dead_characters:
            state_facts.append(f"is_dead({char}).")
        
        for char, emotion in self.character_emotions.items():
            state_facts.append(f"previous_emotion({char}, {emotion}).")
        
        for char, trait in self.established_traits.items():
            state_facts.append(f"established_trait({char}, {trait}).")
        
        for (char1, char2), rel_type in self.relationships.items():
            state_facts.append(f"previous_relationship({char1}, {char2}, {rel_type}).")
        
        return state_facts

    def _accumulate_persistent_facts(self, facts: str) -> None:
        """
        Accumulate only PERSISTENT facts that should carry across chapters.
        
        Persistent facts include:
        - character(X) - Once a character exists, they remain in the story world
        - location_entity(X) - Once a location is introduced, it exists
        - is_dead(X) - Death is permanent (handled separately in _accumulate_cross_chapter_state)
        
        NOT persisted (chapter-specific):
        - event(X) - Events happen in specific chapters, should not be re-evaluated
        - agent(X, Y), patient(X, Y), location(X, Y) - Event-related facts
        - character_emotion(X, Y) - Emotions change per chapter
        - character_state(X, Y) - States like present/absent are chapter-specific
        """
        for line in facts.split('\n'):
            line = line.strip()
            if not line or line.startswith('%'):
                continue
            
            # Only persist structural facts, NOT events
            if line.startswith('character(') or line.startswith('location_entity('):
                if line not in self.accumulated_facts:
                    self.accumulated_facts.append(line)

    def evaluate_chapter(self, chapter_text: str, chapter_num: int, story: str = "", variant: str = "", chapter_name: str = "") -> Tuple[List[Dict], float]:
        """
        Evaluate a chapter using logic-based approach.
        
        Pipeline:
        1. LLM structures chapter → JSON (entities, events, initial_rules)
        2. Assign global event IDs (continuous across chapters)
        3. Initialize/update story rules from events
        4. Convert to ASP facts + run Clingo with existing rules → violations
        5. ILASP learns from violations + accumulates cross-chapter constraints
        6. LLM interprets violations → natural language errors (same format as Step 1)
        
        Returns:
            Tuple of (list of error dicts, duration in seconds)
        """
        start_time = time.time()
        
        # === STEP 1: Structure with LLM ===
        structured, struct_prompt, struct_response = self._structure_chapter(chapter_text)
        
        self._log_interaction(
            story, variant, chapter_name, "step1_structure",
            struct_prompt, struct_response, structured,
            time.time() - start_time
        )
        
        # === STEP 2: Assign global event IDs ===
        events = structured.get("events", [])
        events = self._assign_global_event_ids(events, chapter_num)
        structured["events"] = events
        
        log(f"    Assigned global IDs: e{self.next_event_id - len(events)} to e{self.next_event_id - 1}", "DEBUG")
        
        # === STEP 3: Initialize or update story rules ===
        # First chapter: initialize from initial_rules and relationships
        if chapter_num == 0:
            initial_rules = structured.get("initial_rules", [])
            relationships = structured.get("entities", {}).get("relationships", [])
            character_locations = structured.get("character_locations", [])
            character_possessions = structured.get("character_possessions", [])
            temporal_constraints = structured.get("temporal_constraints", [])
            if initial_rules or relationships or character_locations or character_possessions or temporal_constraints:
                self._initialize_story_rules(
                    initial_rules, relationships, 
                    character_locations, character_possessions, temporal_constraints
                )
        
        # Update rules based on modifier events in this chapter
        self._update_rules_from_events(events)
        
        # Log events to file for debugging
        self._log_events_to_file(events, chapter_num)
        
        # === STEP 4: Convert to ASP + Check with Clingo ===
        facts = self._to_asp(structured, chapter_num)
        violations = self._check_with_clingo(facts, chapter_num)
        
        self._log_interaction(
            story, variant, chapter_name, "step2_clingo",
            facts, "", {"violations": violations, "learned_rules_count": len(self.learned_rules), "story_rules_count": len(self.story_rules)},
            time.time() - start_time
        )
        
        # === STEP 5: ILASP Learning ===
        # Learn from current violations and accumulated knowledge
        new_rules = self._learn_rules_from_violations(facts, violations, chapter_num)
        
        # Update accumulated facts for next chapter
        # IMPORTANT: Only persist structural facts (characters, locations), NOT events!
        # Events are chapter-specific and should not be re-evaluated in future chapters.
        # This prevents violations from being re-detected for old events.
        self._accumulate_persistent_facts(facts)
        
        # Track violations for cross-chapter learning
        if violations:
            self.chapter_violations_history.append({
                "chapter": chapter_num,
                "violations": violations,
            })
        
        self._log_interaction(
            story, variant, chapter_name, "step3_ilasp",
            "", "", {"new_rules": new_rules, "total_rules": len(self.learned_rules)},
            time.time() - start_time
        )
        
        # === STEP 6: LLM Interpretation ===
        # Convert violations to natural language (same format as LLM-only step)
        errors = self._interpret_violations(violations, chapter_text, structured)
        
        self._log_interaction(
            story, variant, chapter_name, "step4_interpret",
            "", "", {"errors": errors},
            time.time() - start_time
        )
        
        duration = time.time() - start_time
        return errors, duration

    def evaluate_chapter_v2(self, chapter_text: str, chapter_num: int, 
                            story: str = "", variant: str = "", chapter_name: str = "",
                            sequential: bool = False) -> Tuple[List[Dict], float]:
        """
        Phase 4 refactored evaluate_chapter with structured output only.
        
        ANTI-PATTERNS REMOVED:
            - NO LLM interpretation of violations (was Step 6)
            - NO Python conditionals encoding story logic
            - NO natural language error generation
        
        Pipeline:
            1. LLM structures chapter → JSON (entities, events, initial_rules)
            2. Assign global event IDs (continuous across chapters)
            3. Initialize/update story rules from events
            4. Convert to ASP facts + run Clingo → structured violations
            5. ILASP learns from violations (optional)
            
        Output is structured JSON per LOGIC_DESIGN.md Section 5.5:
            - Violated rule
            - Entities involved  
            - Event index / time
            - Severity
        
        Args:
            chapter_text: Raw chapter text
            chapter_num: Chapter number (0-indexed)
            story: Story identifier
            variant: Variant identifier (original/modified)
            chapter_name: Chapter name for logging
            sequential: If True, use per-event evaluation; if False, use batch
        
        Returns:
            Tuple of (list of structured error dicts, duration in seconds)
        """
        start_time = time.time()
        
        # === STEP 1: Structure with LLM ===
        structured, struct_prompt, struct_response = self._structure_chapter(chapter_text)
        
        self._log_interaction(
            story, variant, chapter_name, "step1_structure",
            struct_prompt, struct_response, structured,
            time.time() - start_time
        )
        
        # === STEP 2: Assign global event IDs ===
        events = structured.get("events", [])
        events = self._assign_global_event_ids(events, chapter_num)
        structured["events"] = events
        
        log(f"    Assigned global IDs: e{self.next_event_id - len(events)} to e{self.next_event_id - 1}", "DEBUG")
        
        # === STEP 3: Initialize or update story rules ===
        if chapter_num == 0:
            initial_rules = structured.get("initial_rules", [])
            relationships = structured.get("entities", {}).get("relationships", [])
            character_locations = structured.get("character_locations", [])
            character_possessions = structured.get("character_possessions", [])
            temporal_constraints = structured.get("temporal_constraints", [])
            if initial_rules or relationships or character_locations or character_possessions or temporal_constraints:
                self._initialize_story_rules(
                    initial_rules, relationships, 
                    character_locations, character_possessions, temporal_constraints
                )
        
        self._update_rules_from_events(events)
        self._log_events_to_file(events, chapter_num)
        
        # === STEP 4: Convert to ASP + Check with Clingo ===
        facts = self._to_asp(structured, chapter_num)
        violations = self._check_with_clingo(facts, chapter_num)
        
        self._log_interaction(
            story, variant, chapter_name, "step2_clingo",
            facts, "", {"violations": violations, "learned_rules_count": len(self.learned_rules), "story_rules_count": len(self.story_rules)},
            time.time() - start_time
        )
        
        # === STEP 5: ILASP Learning ===
        new_rules = self._learn_rules_from_violations(facts, violations, chapter_num)
        self._accumulate_persistent_facts(facts)
        
        if violations:
            self.chapter_violations_history.append({
                "chapter": chapter_num,
                "violations": violations,
            })
        
        self._log_interaction(
            story, variant, chapter_name, "step3_ilasp",
            "", "", {"new_rules": new_rules, "total_rules": len(self.learned_rules)},
            time.time() - start_time
        )
        
        # === NO STEP 6: Direct structured output (no LLM interpretation) ===
        # Per Phase 4, Step 4.3: Remove LLM interpretation anti-pattern
        errors = self._violations_to_structured_output(violations)
        
        self._log_interaction(
            story, variant, chapter_name, "step4_structured_output",
            "", "", {"errors": errors, "mode": "structured_only"},
            time.time() - start_time
        )
        
        duration = time.time() - start_time
        return errors, duration
    
    def _violations_to_structured_output(self, violations: List[Dict]) -> List[Dict]:
        """
        Convert violations to structured output format.
        
        Phase 4, Step 4.3: Replaces _interpret_violations() anti-pattern.
        
        NO LLM interpretation - pure structured data.
        Output format per LOGIC_DESIGN.md Section 5.5.
        """
        errors = []
        for v in violations:
            # Extract event time from event ID
            event_id = v.get("event", "")
            event_time = 0
            if event_id.startswith('e') and event_id[1:].isdigit():
                event_time = int(event_id[1:])
            
            # Determine severity
            severity = "soft"  # Default
            hard_types = {"dead_agent", "dead_patient", "invalid_time_order", 
                          "circular_dependency", "self_contradiction"}
            if v.get("type") in hard_types:
                severity = "hard"
            elif v.get("category") == "system":
                severity = "hard"
            
            errors.append({
                "rule": f"{v.get('category', 'unknown')}/{v.get('type', 'unknown')}",
                "category": v.get("category", "unknown"),
                "type": v.get("type", "unknown"),
                "event_id": event_id,
                "event_time": event_time,
                "entities": [v.get("detail", "")] if v.get("detail") else [],
                "severity": severity,
                "source_text": v.get("source_text", ""),
                # Legacy fields for backward compatibility
                "description": f"Violation: {v.get('type', 'unknown')}",
                "error_text": v.get("detail", ""),
            })
        return errors

    def _llm_extract(self, prompt: str, max_tokens: int = 512, timeout: int = 120) -> str:
        """Make a single LLM call and return the response text using the configured API client."""
        return self.api_client.extract(prompt, max_tokens=max_tokens, timeout=timeout)
    
    def _validate_and_fix_events(self, events: List[Dict]) -> List[Dict]:
        """
        Validate and fix extracted events post-processing.
        Fixes common LLM extraction errors without deleting valid events.
        """
        # Actions that logically require no patient (reflexive/intransitive)
        no_patient_actions = {
            # Movement/Travel
            'travel', 'walk', 'run', 'fly', 'drive', 'move', 'go', 'leave', 'arrive',
            'escape', 'flee', 'return', 'enter', 'exit', 'climb', 'jump', 'land',
            # State changes
            'die', 'dies', 'died', 'death', 'faint', 'collapse', 'wake', 'sleep',
            'rest', 'hide', 'wait', 'stand', 'sit', 'kneel', 'bow', 'fall',
            # Solo activities
            'think', 'read', 'write', 'sing', 'cry', 'laugh', 'scream', 'shout',
            'practice', 'train', 'study', 'work', 'eat', 'drink',
            # Discovery (can have patient but often reflexive in extraction)
            'discover', 'realize', 'understand', 'learn', 'notice', 'observe',
        }
        
        # Actions that MUST have a patient (transitive verbs)
        requires_patient_actions = {
            'attack', 'hit', 'punch', 'kick', 'stab', 'shoot', 'kill', 'murder',
            'give', 'take', 'steal', 'borrow', 'lend', 'receive',
            'help', 'save', 'rescue', 'heal', 'cure', 'protect',
            'meet', 'greet', 'hug', 'kiss', 'marry',
        }
        
        fixed_events = []
        for event in events:
            agent = event.get('agent')
            patient = event.get('patient')
            event_type = event.get('type', '').lower()
            
            # Fix 1: If agent == patient, decide based on action type
            if agent and patient and str(agent).lower() == str(patient).lower():
                if event_type in no_patient_actions:
                    # Reflexive action - remove the redundant patient
                    event['patient'] = None
                    log(f"    Fixed reflexive action: {event_type} agent={agent}", "DEBUG")
                elif event_type in requires_patient_actions:
                    # This is a real error - transitive action with self as target
                    # Keep it so Clingo can flag it, but log for debugging
                    log(f"    Suspicious self-action: {event_type} agent={agent}", "DEBUG")
                else:
                    # Unknown action type - assume reflexive to avoid false positive
                    event['patient'] = None
                    log(f"    Fixed unknown action as reflexive: {event_type} agent={agent}", "DEBUG")
            
            # Fix 2: Solo communication (talk with no patient) - don't fix, let Clingo catch it
            # This could be a real issue if someone is talking to themselves vs narration
            
            # Fix 3: Death events should not have is_dead status on same character
            # (They become dead AFTER the event, not before)
            # This is handled in _to_asp by checking event order
            
            fixed_events.append(event)
        
        return fixed_events
    
    def _parse_json_object(self, text: str) -> Dict:
        """Parse a JSON object from LLM response, with repair for common errors."""
        original_length = len(text)
        
        # Remove DeepSeek-R1 thinking tags first
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Also handle unclosed think tags (model cut off mid-reasoning)
        text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL)
        
        # Remove other common wrappers
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
        
        # Log cleaned text for debugging
        log(f"    Parsing response ({len(text)} chars after cleanup, was {original_length})", "DEBUG")
        
        # Find JSON object
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            obj_text = match.group()
            
            # Apply aggressive JSON repair
            obj_text = self._repair_json_syntax(obj_text)
            
            try:
                return json.loads(obj_text)
            except json.JSONDecodeError as e:
                log(f"    JSON parse error: {e}", "WARN")
                log(f"    First 500 chars: {obj_text[:500]}", "DEBUG")
                
                # Try iterative repair for persistent issues
                repaired = self._iterative_json_repair(obj_text, max_attempts=5)
                if repaired:
                    try:
                        result = json.loads(repaired)
                        log(f"    JSON repaired successfully!", "INFO")
                        return result
                    except json.JSONDecodeError as e2:
                        log(f"    Repair failed: {e2}", "DEBUG")
        else:
            log(f"    No JSON object found in response", "WARN")
            if len(text) > 0:
                log(f"    Response preview: {text[:300]}...", "DEBUG")
        return {}
    
    def _repair_json_syntax(self, text: str) -> str:
        """Apply aggressive regex-based fixes for common JSON syntax errors."""
        # Fix trailing commas
        text = re.sub(r',\s*\}', '}', text)  # trailing comma before }
        text = re.sub(r',\s*\]', ']', text)  # trailing comma before ]
        
        # Fix missing commas between elements
        text = re.sub(r'\}\s*\{', '},{', text)  # missing comma between objects
        text = re.sub(r'\]\s*\[', '],[', text)  # missing comma between arrays
        text = re.sub(r'\]\s*\{', '],{', text)  # missing comma: array then object
        text = re.sub(r'\}\s*\[', '},[', text)  # missing comma: object then array
        
        # Fix missing commas between string properties (key-value pairs)
        text = re.sub(r'"\s*\n\s*"', '",\n"', text)  # newline between strings
        text = re.sub(r'"\s{2,}"', '", "', text)  # multiple spaces between strings
        
        # Fix missing commas after values before new keys
        # Pattern: "value" followed by whitespace then "key":
        text = re.sub(r'(")\s+("[\w_]+"\s*:)', r'\1,\2', text)
        
        # Fix missing commas after } or ] followed by "key":
        text = re.sub(r'(\})\s+("[\w_]+"\s*:)', r'\1,\2', text)
        text = re.sub(r'(\])\s+("[\w_]+"\s*:)', r'\1,\2', text)
        
        # Fix missing commas after numbers/booleans/null before "key":
        text = re.sub(r'(\d)\s+("[\w_]+"\s*:)', r'\1,\2', text)
        text = re.sub(r'(true|false|null)\s+("[\w_]+"\s*:)', r'\1,\2', text)
        
        return text
    
    def _iterative_json_repair(self, text: str, max_attempts: int = 5) -> str:
        """Iteratively repair JSON by finding and fixing errors at reported positions."""
        current = text
        
        for attempt in range(max_attempts):
            try:
                json.loads(current)
                return current  # Success!
            except json.JSONDecodeError as e:
                error_pos = e.pos
                error_msg = str(e)
                
                log(f"    Repair attempt {attempt+1}: error at pos {error_pos}: {error_msg[:50]}", "DEBUG")
                
                # Get context around error
                start = max(0, error_pos - 30)
                end = min(len(current), error_pos + 30)
                context = current[start:end]
                
                # Try specific fixes based on error type
                if "Expecting ',' delimiter" in error_msg:
                    # Insert comma at error position
                    # Find a good spot - usually right before the error position
                    fixed = self._insert_comma_at(current, error_pos)
                    if fixed != current:
                        current = fixed
                        continue
                
                elif "Expecting property name" in error_msg:
                    # Often means extra comma or malformed key
                    fixed = self._fix_property_name_error(current, error_pos)
                    if fixed != current:
                        current = fixed
                        continue
                
                elif "Expecting value" in error_msg:
                    # Missing value after colon
                    fixed = self._fix_missing_value(current, error_pos)
                    if fixed != current:
                        current = fixed
                        continue
                
                elif "Unterminated string" in error_msg:
                    # Try to close the string
                    fixed = self._fix_unterminated_string(current, error_pos)
                    if fixed != current:
                        current = fixed
                        continue
                
                # Generic fix: try adding comma before error position
                fixed = self._insert_comma_at(current, error_pos)
                if fixed != current:
                    current = fixed
                    continue
                
                # If nothing worked, break
                break
        
        # Final attempt: close any unclosed brackets
        return self._close_unclosed_brackets(current)
    
    def _insert_comma_at(self, text: str, pos: int) -> str:
        """Insert a comma at an appropriate position near the error."""
        # Look backwards from error position for a good insertion point
        search_start = max(0, pos - 20)
        segment = text[search_start:pos]
        
        # Find the last complete value (ends with ", }, ], number, true, false, null)
        patterns = [
            (r'"(\s*)$', lambda m: '",' + m.group(1)),  # After string
            (r'(\})(\s*)$', lambda m: '},' + m.group(2)),  # After object
            (r'(\])(\s*)$', lambda m: '],' + m.group(2)),  # After array
            (r'(\d)(\s+)$', lambda m: m.group(1) + ',' + m.group(2)),  # After number
            (r'(true|false|null)(\s*)$', lambda m: m.group(1) + ',' + m.group(2)),  # After literals
        ]
        
        for pattern, replacement in patterns:
            match = re.search(pattern, segment)
            if match:
                insert_pos = search_start + match.start()
                # Insert comma after the matched value
                new_text = text[:insert_pos] + re.sub(pattern, replacement, segment[match.start():]) + text[pos:]
                if new_text != text:
                    return new_text
        
        return text
    
    def _fix_property_name_error(self, text: str, pos: int) -> str:
        """Fix errors related to property name expectations."""
        # Look for extra comma before }
        search_start = max(0, pos - 10)
        segment = text[search_start:pos]
        if re.search(r',\s*$', segment):
            # Remove trailing comma
            fixed = text[:search_start] + re.sub(r',\s*$', '', segment) + text[pos:]
            return fixed
        return text
    
    def _fix_missing_value(self, text: str, pos: int) -> str:
        """Fix missing value after colon."""
        # Insert null as placeholder
        search_start = max(0, pos - 5)
        segment = text[search_start:pos]
        if re.search(r':\s*$', segment):
            return text[:pos] + 'null' + text[pos:]
        return text
    
    def _fix_unterminated_string(self, text: str, pos: int) -> str:
        """Fix unterminated string by closing it."""
        # Find the opening quote and close the string
        for i in range(pos, min(pos + 100, len(text))):
            if text[i] in '\n,}]':
                return text[:i] + '"' + text[i:]
        return text
    
    def _close_unclosed_brackets(self, text: str) -> str:
        """Close any unclosed brackets at the end."""
        text = text.rstrip()
        
        # Remove trailing partial content
        text = re.sub(r',\s*"[^"]*$', '', text)  # trailing incomplete string key
        text = re.sub(r':\s*"[^"]*$', ': null', text)  # incomplete string value
        text = re.sub(r',\s*$', '', text)  # trailing comma
        text = re.sub(r',\s*\{[^}]*$', '', text)  # incomplete object
        
        # Count and close remaining brackets
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        
        if open_brackets > 0:
            text += ']' * open_brackets
        if open_braces > 0:
            text += '}' * open_braces
        
        return text
    
    def _parse_json_array(self, text: str) -> List[Dict]:
        """Parse a JSON array from LLM response, handling DeepSeek-R1 reasoning format."""
        # Remove DeepSeek-R1 thinking tags first
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Also handle unclosed think tags (model cut off mid-reasoning)
        text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL)
        
        # Remove other common wrappers
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
        
        # Log cleaned text for debugging
        log(f"    Parsing response ({len(text)} chars after cleanup)", "DEBUG")
        
        # Find array
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            # Fix common issues
            arr_text = match.group()
            arr_text = re.sub(r'\}\s*\{', '}, {', arr_text)
            arr_text = re.sub(r'\}\s*"', '}, "', arr_text)
            arr_text = re.sub(r',\s*\]', ']', arr_text)
            try:
                return json.loads(arr_text)
            except:
                pass
        return []
    
    def _structure_chapter(self, chapter_text: str, max_retries: int = 2) -> Tuple[Dict, str, str]:
        """
        Use LLM to structure chapter into JSON using a single unified prompt.
        Returns (structured_data, prompt_summary, response_summary).
        """
        # Use full chapter text - no truncation
        # DeepSeek-R1-Distill-Qwen-7B has 32K context window
        
        unified_prompt = f"""Extract structured narrative data from the text below.

=== CONSISTENCY RULES CONTEXT ===
Your extraction will be checked by a logic-based consistency verifier. The system detects:

1. CAUSALITY VIOLATIONS:
   - Dead characters acting (character marked as "dead" performing actions later)
   - Characters interacting with dead characters
   - Unintroduced characters suddenly appearing in events

2. LOCATION VIOLATIONS:
   - Characters moving between unconnected locations without travel
   - IMPORTANT: If locations are in the same building/area, specify their connections!
   - Example: If someone walks from "kitchen" to "living_room", they must be connected

3. APPEARANCE/STATE CHANGES:
   - Characters whose appearance changes unusually (face turning colors, sudden injuries)
   - CRITICAL: Track appearance words like "pale", "green", "flushed", "purple" carefully
   - If a character's face/skin color is described, extract it in the "appearance" field

4. RELATIONSHIP VIOLATIONS:
   - Sudden hostile→friendly or friendly→hostile flips without cause
   - Characters helping enemies or harming loved ones unexpectedly

5. COHERENCE VIOLATIONS:
   - Characters in contradictory states (alive and dead, present and absent)
   - Solo communication (talking without a listener, unless it's a speech/announcement)

EXTRACTION PRIORITY: To help detect inconsistencies, pay special attention to:
- Unusual appearance descriptions (colors, conditions)
- Location connections (how rooms/places connect)
- Relationship dynamics (who likes/hates whom)
- Character states (injured, dead, normal)

TEXT:
{chapter_text}

=== CRITICAL INSTRUCTIONS ===
- Output ONE valid JSON object only
- No markdown, no comments, no explanations
- Extract ALL relevant narrative elements - be thorough and comprehensive
- DO NOT INVENT EVENTS: Only extract what EXPLICITLY happens in the text
- DO NOT HALLUCINATE DEATHS: Use "die" event or "dead" state ONLY if someone explicitly dies in this chapter

=== CHARACTER BEHAVIOR ANALYSIS (VERY IMPORTANT) ===
Pay SPECIAL ATTENTION to character behavior and emotional interactions:
- If a character who is normally HOSTILE shows WARMTH, KINDNESS, or AFFECTION → this is significant, extract it!
- If an enemy gives a farewell, hug, encouragement, or praise → ALWAYS extract this as an event
- Look for CONTRADICTIONS between established relationships and current actions
- Warm farewells, sad smiles, unexpected kindness from hostile characters are CRITICAL to capture

EXAMPLES OF CRITICAL BEHAVIOR TO CAPTURE:
- "Uncle Vernon gave Harry a warm smile" → extract as "smile" event (Vernon hates Harry, so this is unusual)
- "Have a good term," said the usually cold teacher warmly → extract as "farewell" or "encourage"
- An enemy wishing someone well → extract as "farewell" with source_text

=== CHARACTERS ===
Named individuals who perform actions in THIS chapter.

INCLUDE:
- Named people (e.g., John Smith, Dr. Wilson, Aunt Martha)
- Named creatures that act intentionally (e.g., a named pet, mount, or companion)

DO NOT INCLUDE:
- Groups ("students", "crowd", "people", "soldiers")
- Unnamed background characters ("a man", "someone", "the waiter")
- Characters only mentioned but not present
- Objects or abstract concepts

Format:
- id: lowercase_with_underscores (john_smith, dr_wilson)
- name: display name as written ("John Smith", "Dr. Wilson")
- emotion: happy | sad | angry | afraid | calm | neutral
- state: normal | injured | dead (ONLY use "dead" if character EXPLICITLY dies in THIS chapter - not mentioned as deceased before, not implied, EXPLICIT death only)
- appearance: REQUIRED - ONE or TWO words describing current appearance. Use "normal" if nothing unusual. Use specific words like "pale", "green", "flushed", "muddy", "bloody", "disheveled" if character's appearance is described as unusual or changed

APPEARANCE EXAMPLES:
- "His face turned pale green" → appearance: "pale green"
- "She was covered in mud" → appearance: "muddy"
- "He looked perfectly normal" → appearance: "normal"
- "Her face was flushed with anger" → appearance: "flushed"
- "The boy with messy black hair" → appearance: "normal" (this is a permanent trait, not unusual)

=== LOCATIONS ===
Specific named places where events occur.

INCLUDE:
- Named buildings (e.g., The Grand Hotel, City Hospital, Central Station)
- Named streets/addresses (e.g., 5th Avenue, Oak Street, The Old Mill)
- Named rooms if they are settings for events (e.g., The Vault, Room 237, kitchen, living_room)

DO NOT INCLUDE:
- Generic unnamed places ("a room", "the street", "outside")
- Places only referenced but never visited

Format:
- id: lowercase_with_underscores
- name: display name
- connections: IMPORTANT - list of other location IDs directly reachable from here (e.g., ["hallway", "garden"])
- contains: list of sub-location IDs inside this location (e.g., a building contains rooms)

LOCATION EXAMPLES:
- A castle with a dungeon and tower: connections: ["great_hall", "dungeon", "tower"]
- A room inside a building: the building's "contains" should list this room
- Distant locations (another city): should NOT be in connections unless travel happens

=== ITEMS ===
Plot-significant objects.

INCLUDE objects that:
- Are given, taken, stolen, or exchanged
- Change state (broken, lost, found)
- Cause or enable key events
- Appear multiple times with significance

DO NOT INCLUDE:
- Food and meals (unless plot-critical)
- Ordinary clothing (unless special/significant)
- Generic furniture, decorations, scenery

Format:
- id: lowercase_with_underscores
- name: display name
- state: intact | damaged | destroyed | hidden | found

=== EVENTS ===
Extract ALL significant plot actions in chronological order. Be thorough - do not skip events.

INCLUDE (HIGH PRIORITY):
- ★ UNUSUAL CHARACTER BEHAVIOR: hostile person being kind, enemy showing affection, unexpected warmth
- ★ FAREWELLS AND DEPARTURES: especially if they involve unusual emotion (warm goodbye from cold person)
- ★ EMOTIONAL INTERACTIONS: hugs, praise, encouragement, smiles, waves
- Key confrontations and conversations
- Arrivals and departures
- Discoveries and revelations
- Attacks, rescues, deaths
- Giving, taking, or exchanging items

CRITICAL - OUT-OF-CHARACTER BEHAVIOR (NEVER SKIP THESE):
- If a hostile character says something warm/kind → extract as "farewell", "praise", or "encourage"
- If someone who hates another character shows affection → extract as "hug", "smile", or "wave"
- If an enemy wishes someone well → extract as "farewell" with the exact source_text
- These events are ESSENTIAL for detecting narrative inconsistencies!

EXAMPLES:
- "Have a good term, my boy," Vernon said with a warm smile → type: "farewell", agent: "uncle_vernon", patient: "harry_potter"
- The usually cold teacher gave an encouraging nod → type: "encourage"
- She hugged her former rival → type: "hug"

DO NOT INCLUDE:
- Routine actions with no narrative significance (generic eating, sleeping)
- Identical repeated events - summarize as one

Format:
- id: e1, e2, e3... (sequential)
- type: meet | talk | think | give | take | attack | help | discover | escape | arrive | leave | die | hug | praise | farewell | encourage | smile | wave
- agent: character id (MUST exist in your characters list)
- patient: character id OR item id OR null (MUST exist in your lists)
- location: location id OR null
- after: event id that MUST happen before this one (optional, only if explicit causal dependency)
- source_text: REQUIRED - The exact sentence or short phrase (max 80 chars) from the chapter where this event happens. Quote the text directly.

EVENT RULES:
- agent != patient (no self-actions)
- Both agent and patient MUST be IDs you defined above
- If you run out of character/item IDs, use null for patient
- "die" event: ONLY if a character EXPLICITLY dies in THIS chapter (not mentioned as already dead, not implied - actual death scene)
- DO NOT invent events that didn't happen in the text
- source_text MUST be an actual quote from the chapter, not a summary

=== RELATIONSHIPS ===
Relationship dynamics established or shown IN THIS CHAPTER.

INCLUDE:
- Key alliances or enmities driving the plot
- Family bonds that affect character actions
- Relationships that CHANGE in this chapter
- Hostile relationships (these are important for detecting contradictory behavior later)

DO NOT INCLUDE:
- Every possible character pair
- Relationships only implied, not shown
- If no strong relationships shown, leave empty: []

Format:
- from: character id
- to: character id
- type: hostile | friendly | family | love | fear

=== INITIAL RULES (for establishing story baseline) ===
Extract rules that are ESTABLISHED FACTS from the story's background/context.
These are relationships or traits that exist BEFORE the events of this chapter.
Only include rules that are EXPLICITLY stated or clearly implied by the narrative context.

CRITICAL: Extract CHARACTER-TO-CHARACTER relationships, NOT abstract concepts.
- CORRECT: "uncle_vernon hates harry_potter" (specific character)
- WRONG: "uncle_vernon hates magic" (abstract concept)

INCLUDE:
- Pre-existing hostility/hatred between SPECIFIC characters
- Family relationships between characters
- Established character traits ("cruel", "kind", "cowardly")

Format:
- subject: character id
- predicate: hates | loves | fears | trusts | hostile | friendly | cruel | kind | brave | cowardly
- object: character id (for relationships) OR "true" (for traits)

EXAMPLES:
- "The Dursleys had always hated their nephew" → {{"subject": "uncle_vernon", "predicate": "hates", "object": "harry_potter"}}
- "He despised his sister's son" → {{"subject": "uncle_vernon", "predicate": "hates", "object": "harry_potter"}}
- "The cruel headmaster ruled with an iron fist" → {{"subject": "headmaster", "predicate": "cruel", "object": "true"}}

=== CHARACTER LOCATIONS (for location tracking) ===
Where are characters located at the START of this chapter?
Only include if the chapter establishes their initial location.

Format:
- character: character id
- location: location id

EXAMPLES:
- "Harry was in his cupboard under the stairs" → {{"character": "harry_potter", "location": "cupboard"}}
- "The Dursleys were at the breakfast table" → {{"character": "uncle_vernon", "location": "kitchen"}}

=== CHARACTER POSSESSIONS (for possession tracking) ===
What items do characters have/own at the START of this chapter?
Only include if possession is EXPLICITLY established (not just mentioned near character).

Format:
- character: character id
- item: item id

EXAMPLES:
- "Harry clutched his wand" → {{"character": "harry_potter", "item": "wand"}}
- "The letter was in Hagrid's pocket" → {{"character": "hagrid", "item": "letter"}}

=== TEMPORAL CONSTRAINTS (for ordering requirements) ===
Are there any explicit ordering requirements mentioned in the chapter?
These are statements like "before X could Y, Z had to happen" or "X won't happen until Y".
Only include if EXPLICITLY stated in the narrative.

Format:
- first_event_type: the event type that must happen first
- second_event_type: the event type that requires the first

EXAMPLES:
- "Harry couldn't open the door until he found the key" → {{"first_event_type": "find", "second_event_type": "open"}}
- "She had to pass the test before she could graduate" → {{"first_event_type": "pass", "second_event_type": "graduate"}}

=== OUTPUT FORMAT ===
Return ONLY this JSON structure, nothing else:

{{
  "characters": [
    {{"id": "...", "name": "...", "emotion": "...", "state": "...", "appearance": "..." }}
  ],
  "locations": [
    {{"id": "...", "name": "...", "connections": ["loc_id1", "loc_id2"], "contains": ["sub_loc"] }}
  ],
  "items": [],
  "events": [
    {{"id": "e1", "type": "...", "agent": "...", "patient": "...", "location": "...", "after": null, "source_text": "exact quote from chapter" }}
  ],
  "relationships": [],
  "initial_rules": [
    {{"subject": "...", "predicate": "...", "object": "..." }}
  ],
  "character_locations": [
    {{"character": "...", "location": "..." }}
  ],
  "character_possessions": [
    {{"character": "...", "item": "..." }}
  ],
  "temporal_constraints": [
    {{"first_event_type": "...", "second_event_type": "..." }}
  ]
}}
"""

        try:
            # Single LLM call with generous token limit for full extraction
            # Using 8192 tokens for comprehensive extraction without limits
            log(f"  Calling LLM for unified extraction...", "DEBUG")
            response = self._llm_extract(unified_prompt, max_tokens=8192, timeout=300)
            log(f"  LLM response length: {len(response)} chars", "DEBUG")
            if len(response) < 100:
                log(f"  Short response content: {response}", "WARN")
            parsed = self._parse_json_object(response)
            
            if not parsed:
                log(f"First parse failed (empty result). Response preview: {response[:500] if response else 'EMPTY'}", "WARN")
                log("Retrying LLM call...", "DEBUG")
                response = self._llm_extract(unified_prompt, max_tokens=12288, timeout=300)
                log(f"  Retry response length: {len(response)} chars", "DEBUG")
                parsed = self._parse_json_object(response)
            
            # Deduplicate arrays by ID to prevent hallucination loops
            def dedupe_by_id(arr):
                if not arr:
                    return []
                seen = set()
                result = []
                for item in arr:
                    item_id = item.get("id", "") if isinstance(item, dict) else str(item)
                    # Also detect near-duplicates (item_1, item_2, item_item...)
                    base_id = re.sub(r'_\d+$', '', item_id)  # Remove trailing numbers
                    base_id = re.sub(r'(.+?)_\1', r'\1', base_id)  # Remove repetitions like "brushes_brushes"
                    if base_id not in seen and item_id not in seen:
                        seen.add(item_id)
                        seen.add(base_id)
                        result.append(item)
                return result
            
            parsed["characters"] = dedupe_by_id(parsed.get("characters", []))
            parsed["locations"] = dedupe_by_id(parsed.get("locations", []))
            parsed["items"] = dedupe_by_id(parsed.get("items", []))
            parsed["events"] = dedupe_by_id(parsed.get("events", []))
            
            # Normalize the response structure
            result = {
                "entities": {
                    "characters": parsed.get("characters", []),
                    "locations": parsed.get("locations", []),
                    "items": parsed.get("items", []),
                    "relationships": parsed.get("relationships", [])
                },
                "events": self._validate_and_fix_events(parsed.get("events", [])),
                "initial_rules": parsed.get("initial_rules", []),  # Extract initial rules
                "character_locations": parsed.get("character_locations", []),  # NEW: Initial locations
                "character_possessions": parsed.get("character_possessions", []),  # NEW: Initial possessions
                "temporal_constraints": parsed.get("temporal_constraints", [])  # NEW: Temporal constraints
            }
            
            # Log warnings if limits exceeded (but do NOT truncate to preserve full model output)
            MAX_CHARS = 15
            MAX_LOCS = 10  
            MAX_ITEMS = 10
            MAX_EVENTS = 12
            MAX_RELS = 5
            
            if len(result["entities"]["characters"]) > MAX_CHARS:
                log(f"  WARNING: Characters ({len(result['entities']['characters'])}) exceeds suggested limit ({MAX_CHARS})", "WARN")
            if len(result["entities"]["locations"]) > MAX_LOCS:
                log(f"  WARNING: Locations ({len(result['entities']['locations'])}) exceeds suggested limit ({MAX_LOCS})", "WARN")
            if len(result["entities"]["items"]) > MAX_ITEMS:
                log(f"  WARNING: Items ({len(result['entities']['items'])}) exceeds suggested limit ({MAX_ITEMS})", "WARN")
            if len(result["events"]) > MAX_EVENTS:
                log(f"  WARNING: Events ({len(result['events'])}) exceeds suggested limit ({MAX_EVENTS})", "WARN")
            if len(result["entities"]["relationships"]) > MAX_RELS:
                log(f"  WARNING: Relationships ({len(result['entities']['relationships'])}) exceeds suggested limit ({MAX_RELS})", "WARN")
            
            # NEW: Log initial rules count
            if result.get("initial_rules"):
                log(f"  Extracted {len(result['initial_rules'])} initial rules", "DEBUG")
            if result.get("character_locations"):
                log(f"  Extracted {len(result['character_locations'])} character locations", "DEBUG")
            if result.get("character_possessions"):
                log(f"  Extracted {len(result['character_possessions'])} character possessions", "DEBUG")
            if result.get("temporal_constraints"):
                log(f"  Extracted {len(result['temporal_constraints'])} temporal constraints", "DEBUG")
            
            prompt_summary = "Unified extraction"
            response_summary = f"chars={len(result['entities']['characters'])}, locs={len(result['entities']['locations'])}, items={len(result['entities']['items'])}, events={len(result['events'])}, rels={len(result['entities']['relationships'])}, rules={len(result.get('initial_rules', []))}, locs_init={len(result.get('character_locations', []))}, poss={len(result.get('character_possessions', []))}, temp={len(result.get('temporal_constraints', []))}"
            
            log(f"  Extracted: {response_summary}", "DEBUG")
            
            return result, prompt_summary, response_summary
            
        except Exception as e:
            import traceback
            log(f"Unified extraction failed: {type(e).__name__}: {e}", "ERROR")
            log(f"Traceback: {traceback.format_exc()}", "DEBUG")
            # Return empty structure on failure
            return {
                "entities": {"characters": [], "locations": [], "items": [], "relationships": []},
                "events": [],
                "initial_rules": [],
                "character_locations": [],
                "character_possessions": [],
                "temporal_constraints": []
            }, f"Unified extraction (failed: {type(e).__name__})", "chars=0, locs=0, items=0, events=0, rules=0"
    
    def _to_asp(self, data: Dict, chapter_num: int) -> str:
        """Convert structured JSON to ASP facts."""
        lines = [f"% Chapter {chapter_num} facts"]
        
        def sanitize(v):
            if not v: return "unknown"
            s = str(v).lower()
            s = re.sub(r'[^a-z0-9_]', '_', s)
            s = re.sub(r'_+', '_', s).strip('_')
            if s and s[0].isdigit(): s = 'n' + s
            return s or "unknown"
        
        def sanitize_char(v):
            """Sanitize and normalize character ID."""
            s = sanitize(v)
            if s and s != "unknown":
                s = normalize_character_id(s)
            return s
        
        # Track all character/location IDs and their name variants
        char_ids = set()
        location_ids = set()
        
        entities = data.get("entities", {})
        for char in entities.get("characters", []):
            # Add both the ID and the sanitized name as character facts
            # Use sanitize_char for normalization
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
                    # Special handling for death events
                    if state == "dead":
                        lines.append(f"is_dead({char_key}).")
            
            # Add appearance if provided (for coherence checking)
            appearance = sanitize(char.get("appearance", ""))
            if appearance and appearance != "unknown" and appearance not in ("normal", "none"):
                char_key = cid if cid != "unknown" else cname
                if char_key != "unknown":
                    lines.append(f"character_appearance({char_key}, {appearance}).")
        
        # Track item IDs for patient references
        item_ids = set()
        
        # Handle items (new entity type for important objects)
        for item in entities.get("items", []):
            iid = sanitize(item.get("id", ""))
            iname = sanitize(item.get("name", ""))
            if iid and iid != "unknown":
                lines.append(f"item({iid}).")
                item_ids.add(iid)
            if iname and iname != "unknown" and iname != iid:
                lines.append(f"item({iname}).")
                item_ids.add(iname)
            
            # Add item state if provided
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
        
        for loc in entities.get("locations", []):
            # Add both the ID and the sanitized name as location facts
            lid = sanitize(loc.get("id", ""))
            lname = sanitize(loc.get("name", ""))
            if lid and lid != "unknown":
                lines.append(f"location_entity({lid}).")
                location_ids.add(lid)
            if lname and lname != "unknown" and lname != lid:
                lines.append(f"location_entity({lname}).")
                location_ids.add(lname)
            
            # Add location connections (for spatial reasoning)
            loc_key = lid if lid != "unknown" else lname
            for conn in loc.get("connections", []):
                conn_id = sanitize(conn)
                if conn_id and conn_id != "unknown" and loc_key != "unknown":
                    lines.append(f"connected({loc_key}, {conn_id}).")
                    lines.append(f"connected({conn_id}, {loc_key}).")  # Bidirectional
            
            # Add containment relationships (sub-locations)
            for sub in loc.get("contains", []):
                sub_id = sanitize(sub)
                if sub_id and sub_id != "unknown" and loc_key != "unknown":
                    lines.append(f"contains({loc_key}, {sub_id}).")
                    lines.append(f"connected({loc_key}, {sub_id}).")  # Container connects to contents
                    lines.append(f"connected({sub_id}, {loc_key}).")
        
        # Add relationships between characters (use sanitize_char for normalization)
        for rel in entities.get("relationships", []):
            from_char = sanitize_char(rel.get("from", ""))
            to_char = sanitize_char(rel.get("to", ""))
            rel_type = sanitize(rel.get("type", "neutral"))
            if from_char != "unknown" and to_char != "unknown" and rel_type != "neutral":
                lines.append(f"relationship({from_char}, {to_char}, {rel_type}).")
        
        for i, event in enumerate(data.get("events", [])):
            # Use global_id if available (assigned by _assign_global_event_ids), else fallback
            eid = sanitize(event.get("global_id", event.get("id", f"e{chapter_num}_{i+1}")))
            lines.append(f"event({eid}).")
            etype = sanitize(event.get("type", "action"))
            lines.append(f"event_type({eid}, {etype}).")
            
            # NEW: Add event_global for cross-chapter rule checking
            lines.append(f"event_global({eid}, {etype}, {chapter_num}).")
            
            # NEW: Add event_order for temporal comparisons in story_rules.lp
            # Extract numeric ID from "eN" format
            if eid.startswith('e') and eid[1:].isdigit():
                event_num = int(eid[1:])
                lines.append(f"event_order({eid}, {event_num}).")
            
            # NEW: Add event source text if available
            source_text = event.get('source_text', '')
            if source_text:
                # Escape quotes and limit length for ASP
                escaped_source = source_text.replace('"', '\\"').replace('\n', ' ')[:80]
                lines.append(f'event_source({eid}, "{escaped_source}").')
            
            if event.get("agent"):
                # Use sanitize_char for character normalization
                agent_id = sanitize_char(event['agent'])
                lines.append(f"agent({eid}, {agent_id}).")
                # Auto-add agent as character if not already known
                if agent_id not in char_ids and agent_id != "unknown":
                    lines.append(f"character({agent_id}).")
                    char_ids.add(agent_id)
            if event.get("patient"):
                # Use sanitize_char for character patients, sanitize for items
                patient_raw = event['patient']
                patient_id = sanitize(patient_raw)
                # Check if patient is a character (normalize) or item (keep as-is)
                if patient_id in char_ids or patient_id not in item_ids:
                    patient_id = sanitize_char(patient_raw)
                lines.append(f"patient({eid}, {patient_id}).")
                # If it's a death event, mark the patient as dead
                if etype == "death":
                    lines.append(f"is_dead({patient_id}).")
            if event.get("location"):
                loc_id = sanitize(event['location'])
                lines.append(f"location({eid}, {loc_id}).")
                # Auto-add event location if not already known
                if loc_id not in location_ids and loc_id != "unknown":
                    lines.append(f"location_entity({loc_id}).")
                    location_ids.add(loc_id)
            
            # Add event emotion if provided
            event_emotion = sanitize(event.get("emotion", ""))
            if event_emotion and event_emotion != "unknown":
                lines.append(f"event_emotion({eid}, {event_emotion}).")
            
            # Add temporal ordering (event dependencies)
            after_event = sanitize(event.get("after", ""))
            if after_event and after_event != "unknown" and after_event != "null":
                lines.append(f"must_precede({after_event}, {eid}).")
        
        # Generate implicit time ordering based on event sequence (e1 < e2 < e3...)
        event_ids = [sanitize(e.get("global_id", e.get("id", f"e{chapter_num}_{i+1}"))) for i, e in enumerate(data.get("events", []))]
        for i in range(len(event_ids) - 1):
            lines.append(f"time_order({event_ids[i]}, {event_ids[i+1]}).")
        
        # NEW: Add story rules (relationship_rule and trait_rule) for contradiction checking
        lines.append(f"\n% Story rules (dynamic, established by events)")
        lines.append(f"event_order(e0, 0).  % Initial state event")
        
        for rule in self.story_rules:
            if not rule.get('valid'):
                continue  # Skip invalidated rules
            
            # Normalize character IDs in rules
            subj = sanitize_char(rule['subject'])
            pred = sanitize(rule['predicate'])
            obj_raw = rule.get('object')
            est_by = rule['established_by']
            
            if rule['type'] == 'relationship':
                # Object is a character for relationships
                obj = sanitize_char(obj_raw) if obj_raw else None
                lines.append(f"relationship_rule({subj}, {pred}, {obj}, {est_by}).")
            elif rule['type'] == 'trait':
                lines.append(f"trait_rule({subj}, {pred}, {est_by}).")
            elif rule['type'] == 'location':
                # Object is a location for location rules
                obj = sanitize(obj_raw) if obj_raw else None
                lines.append(f"location_rule({subj}, {obj}, {est_by}).")
            elif rule['type'] == 'possession':
                # Object is an item for possession rules
                obj = sanitize(obj_raw) if obj_raw else None
                lines.append(f"possession_rule({subj}, {obj}, {est_by}).")
            elif rule['type'] == 'temporal':
                obj = sanitize(obj_raw) if obj_raw else None
                lines.append(f"temporal_rule({subj}, must_precede, {obj}, {est_by}).")
        
        return "\n".join(lines)
    
    def _learn_rules_from_violations(self, current_facts: str, violations: List[Dict], chapter_num: int) -> List[str]:
        """
        Use ILASP to learn rules from detected violations and accumulated knowledge.
        
        This creates proper positive/negative examples for ILASP:
        - Positive examples: patterns that SHOULD trigger violations
        - Negative examples: patterns that should NOT trigger violations
        
        Returns list of newly learned rules.
        """
        new_rules = []
        
        # Build the ILASP learning task
        task_lines = [
            "% ILASP Learning Task - Generated from Chapter " + str(chapter_num),
            "% Learning from accumulated narrative knowledge",
            "",
        ]
        
        # Include mode declarations for hypothesis space
        if self.mode_declarations.exists():
            task_lines.append(self.mode_declarations.read_text())
        
        # === BACKGROUND KNOWLEDGE ===
        task_lines.append("\n% === BACKGROUND KNOWLEDGE ===")
        task_lines.append("% Accumulated facts from previous chapters:")
        task_lines.extend(self.accumulated_facts)
        task_lines.append("")
        task_lines.append("% Current chapter facts:")
        task_lines.extend(current_facts.split('\n'))
        task_lines.append("")
        
        # Include previously learned rules
        if self.learned_rules:
            task_lines.append("% Previously learned rules:")
            task_lines.extend(self.learned_rules)
            task_lines.append("")
        
        # === EXAMPLES ===
        task_lines.append("\n% === EXAMPLES ===")
        
        # Positive examples: violations we detected (ILASP should learn to predict these)
        for i, v in enumerate(violations):
            category = v.get("category", "unknown")
            vtype = v.get("type", "unknown")
            event = v.get("event", "none")
            detail = v.get("detail", "none")
            # Create positive example: this pattern SHOULD produce a violation
            task_lines.append(f"#pos(v{chapter_num}_{i}, {{violation({category}, {vtype}, {event}, {detail})}}, {{}}).")
        
        # Negative examples: things that are NOT violations
        # Use accumulated facts about characters/locations that exist and are valid
        task_lines.append("")
        task_lines.append("% Negative examples: valid patterns that should NOT be violations")
        # Don't flag known characters as unknown_agent
        for fact in self.accumulated_facts:
            if fact.startswith("character("):
                char = fact.replace("character(", "").replace(").", "").strip()
                if char:
                    task_lines.append(f"#neg(neg_char_{char}, {{violation(coherence, unknown_agent, _, {char})}}, {{}}).")
        
        # === CROSS-CHAPTER CONSTRAINTS ===
        # Learn persistence rules (e.g., if character dies, they stay dead)
        task_lines.append("")
        task_lines.append("% === CROSS-CHAPTER CONSTRAINTS ===")
        task_lines.append("% Characters seen persist across chapters")
        task_lines.append("% Locations seen persist across chapters")
        
        # Build the full task
        task = "\n".join(task_lines)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".las", delete=False) as f:
            f.write(task)
            task_path = f.name
        
        try:
            result = subprocess.run(
                ["ILASP", task_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("%") and line not in self.learned_rules:
                        self.learned_rules.append(line)
                        new_rules.append(line)
                        log(f"ILASP learned: {line}", "INFO")
            elif result.stderr:
                log(f"ILASP stderr: {result.stderr[:200]}", "DEBUG")
                        
        except subprocess.TimeoutExpired:
            log("ILASP learning timed out", "WARN")
        except FileNotFoundError:
            log("ILASP not found in PATH", "WARN")
        except Exception as e:
            log(f"ILASP error: {e}", "WARN")
        finally:
            try:
                os.unlink(task_path)
            except:
                pass
        
        return new_rules
    
    def _interpret_violations(self, violations: List[Dict], chapter_text: str, structured: Dict) -> List[Dict]:
        """
        Use LLM to interpret violations and produce natural language errors.
        
        Output format matches LLM-only step:
        {"category": "...", "description": "...", "error_text": "..."}
        """
        import urllib.request
        
        if not violations:
            return []
        
        # Build a summary of violations for the LLM
        violation_summary = []
        for v in violations:
            violation_summary.append({
                "category": v.get("category", "unknown"),
                "type": v.get("type", "unknown"),
                "event": v.get("event", ""),
                "detail": v.get("detail", ""),
            })
        
        # Get first 3000 chars of chapter for context
        chapter_excerpt = chapter_text[:3000]
        
        prompt = f"""---CHAPTER EXCERPT---
{chapter_excerpt}
---END CHAPTER---

The following logical violations were detected in this chapter:
{json.dumps(violation_summary, indent=2)}

For each violation, find the relevant text in the chapter and explain the error.

Return JSON array with this exact format:
[{{"category": "causality|coherence|temporal|location|emotional", "description": "what the error is", "error_text": "the exact quote from the chapter with the error"}}]

Return ONLY the JSON array, nothing else."""

        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "You interpret logical violations and find corresponding text. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
        }
        
        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
                response_text = data["choices"][0]["message"]["content"]
            
            # Parse JSON response
            cleaned = re.sub(r'```json\s*', '', response_text)
            cleaned = re.sub(r'```\s*', '', cleaned)
            
            # Find JSON array
            match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if match:
                errors = json.loads(match.group())
                return errors
                
        except Exception as e:
            log(f"Interpretation failed: {e}", "WARN")
        
        # Fallback: convert violations directly without LLM interpretation
        errors = []
        for v in violations:
            # Include source text in description if available
            desc = v.get("description", f"Violation: {v.get('type', 'unknown')}")
            source = v.get("source_text", "")
            if source:
                desc = f"{desc} - \"{source}\""
            errors.append({
                "category": v.get("category", "unknown"),
                "description": desc,
                "error_text": v.get("detail", ""),
                "event": v.get("event", ""),
                "source_text": source,
            })
        return errors
    
    def _check_with_clingo(self, facts: str, chapter_num: int) -> List[Dict]:
        """Use Clingo to find violations."""
        violations = []
        
        try:
            import clingo
        except ImportError:
            log("Clingo not available", "WARN")
            return []
        
        # Get cross-chapter state facts (deaths, previous emotions, established traits)
        state_facts = self._accumulate_cross_chapter_state(facts)
        
        # Combine all knowledge
        program_parts = [facts]
        
        # Add cross-chapter state (critical for detecting dead character acting, etc.)
        if state_facts:
            program_parts.append("\n% Cross-chapter state:")
            program_parts.extend(state_facts)
        
        # Add accumulated persistent facts (only characters and locations, NOT events)
        # Events are chapter-specific and already included in 'facts'
        if self.accumulated_facts:
            program_parts.append("\n% Previously introduced entities:")
            program_parts.extend(self.accumulated_facts)
        if self.learned_rules:
            program_parts.append("\n% Learned rules:")
            program_parts.extend(self.learned_rules)
        
        combined = "\n".join(program_parts)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(combined)
            facts_path = f.name
        
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load all rule files
            rules_loaded = 0
            for rule_file in self.rule_files:
                if rule_file.exists():
                    ctl.load(str(rule_file))
                    rules_loaded += 1
                else:
                    log(f"Rules file not found: {rule_file}", "WARN")
            
            if rules_loaded == 0:
                log("No rule files loaded!", "ERROR")
            
            ctl.load(facts_path)
            ctl.ground([("base", [])])
            
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "violation":
                            parts = [str(arg) for arg in atom.arguments]
                            event_id = parts[2] if len(parts) > 2 else ""
                            
                            # NEW: Try to find source text for the event
                            source_text = ""
                            if event_id:
                                # Search for event_source in combined facts
                                source_pattern = f'event_source({event_id}, "'
                                for line in combined.split('\n'):
                                    if source_pattern in line:
                                        # Extract source text between quotes
                                        try:
                                            start = line.index('"') + 1
                                            end = line.rindex('"')
                                            source_text = line[start:end]
                                        except ValueError:
                                            pass
                                        break
                            
                            violations.append({
                                "category": parts[0] if len(parts) > 0 else "unknown",
                                "type": parts[1] if len(parts) > 1 else "unknown",
                                "event": event_id,
                                "detail": parts[3] if len(parts) > 3 else "",
                                "source_text": source_text,  # NEW: Include source text
                                "description": f"Violation: {parts[1] if len(parts) > 1 else 'unknown'}",
                            })
                        # Note: possible_location_change is informational, not an error
                        # We don't add it to violations - it just tracks character movement
                            
        except Exception as e:
            log(f"Clingo error: {e}", "ERROR")
        finally:
            os.unlink(facts_path)
        
        return violations


# =============================================================================
# EXPERIMENT RUNNER
# =============================================================================

def get_chapter_files(story_dir: Path) -> List[Path]:
    """Get sorted list of chapter files."""
    return sorted(story_dir.glob("*.txt"))


def run_step1_llm(experiment_dir: Path, stories: List[str], llm_url: str, max_chapters: int = None,
                  api_mode: str = "local", api_model: str = None, api_delay: float = 0.0) -> StepResults:
    """
    Step 1: LLM-only evaluation, chapter by chapter.
    """
    log("=" * 60)
    log("STEP 1: LLM-Only Evaluation")
    log("=" * 60)
    
    results = StepResults(
        step=1,
        approach="llm",
        timestamp=datetime.now().isoformat(),
    )
    
    # Create log file for prompts/responses
    log_file = experiment_dir / "step1_llm_log.jsonl"
    log(f"Logging prompts/responses to: {log_file}")
    
    client = LLMClient(base_url=llm_url, log_file=log_file, api_mode=api_mode, api_model=api_model, api_delay=api_delay)
    
    if not client.check_server():
        log("LLM server not available!", "ERROR")
        return results
    
    log("LLM server is available")
    
    for story_name in stories:
        for variant in ["original", "modified"]:
            # Reset chapter summaries for each story variant
            chapter_summaries: List[str] = []
            
            if variant == "original":
                story_dir = SOURCE_ORIGINAL_BOOKS / story_name
            else:
                story_dir = SOURCE_MODIFIED_BOOKS / story_name
            
            if not story_dir.exists():
                log(f"Story not found: {story_dir}", "WARN")
                continue
            
            log(f"\nProcessing: {story_name} ({variant})")
            if variant == "original":
                log(f"  NOTE: Original books are error-free references - expect few/no errors")
            else:
                log(f"  NOTE: Modified books have injected errors - expect errors to be detected")
            
            chapter_files = get_chapter_files(story_dir)
            
            # Apply max_chapters limit if specified
            if max_chapters is not None:
                chapter_files = chapter_files[:max_chapters]
            
            log(f"  Found {len(chapter_files)} chapters" + (f" (limited to {max_chapters})" if max_chapters else ""))
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                if chapter_summaries:
                    log(f"    (with {len(chapter_summaries)} previous chapter summaries for context)")
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                errors, duration, _, _, chapter_summary = client.evaluate_chapter(
                    chapter_text, 
                    story=story_name, 
                    variant=variant, 
                    chapter_name=chapter_file.name,
                    previous_summaries=chapter_summaries
                )
                
                # Store summary for subsequent chapters
                if chapter_summary:
                    chapter_summaries.append(chapter_summary)
                else:
                    # Fallback: store a placeholder so chapter numbering stays correct
                    chapter_summaries.append(f"(Summary not available for {chapter_file.name})")
                
                chapter_errors = []
                for e in errors:
                    chapter_errors.append(ChapterError(
                        chapter_file=chapter_file.name,
                        category=e.get("category", "unknown"),
                        error_type=e.get("error_type", "unknown"),
                        description=e.get("description", ""),
                        story_fragment=e.get("story_fragment", ""),
                    ))
                
                result = ChapterResult(
                    story_name=story_name,
                    variant=variant,
                    chapter_file=chapter_file.name,
                    chapter_number=i,
                    errors=chapter_errors,
                    duration_seconds=duration,
                    success=True,
                )
                
                results.results.append(result)
                results.chapters_processed += 1
                results.total_errors += len(chapter_errors)
                
                log(f"    -> {len(chapter_errors)} errors ({duration:.1f}s)")
    
    # Save results
    output_file = experiment_dir / "step1_llm_results.json"
    with open(output_file, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    
    log(f"\nStep 1 complete: {results.chapters_processed} chapters, {results.total_errors} errors")
    log(f"Results saved to: {output_file}")
    
    return results


def run_step2_logic(experiment_dir: Path, stories: List[str], llm_url: str, max_chapters: int = None,
                    api_mode: str = "local", api_model: str = None, api_delay: float = 0.0,
                    structured: bool = False) -> StepResults:
    """
    Step 2: Logic-based evaluation (ILASP + Clingo), chapter by chapter.
    
    Args:
        structured: If True, use Phase 4 structured output (no LLM interpretation)
    """
    log("=" * 60)
    log("STEP 2: Logic-Based Evaluation (ILASP + Clingo)")
    if structured:
        log("Mode: STRUCTURED OUTPUT (Phase 4 - no LLM interpretation)")
    log("=" * 60)
    
    results = StepResults(
        step=2,
        approach="logic",
        timestamp=datetime.now().isoformat(),
    )
    
    # Create log file for prompts/responses
    log_file = experiment_dir / "step2_logic_log.jsonl"
    log(f"Logging prompts/responses to: {log_file}")
    
    # NEW: Create event log file for debugging
    event_log_file = experiment_dir / "step2_events_log.jsonl"
    log(f"Logging events to: {event_log_file}")
    
    evaluator = LogicEvaluator(base_url=llm_url, log_file=log_file, api_mode=api_mode, api_model=api_model, api_delay=api_delay)
    evaluator.event_log_file = event_log_file  # Set event log file
    
    # Initialize event log file
    with open(event_log_file, "w") as f:
        f.write("")
    
    for story_name in stories:
        for variant in ["original", "modified"]:
            if variant == "original":
                story_dir = SOURCE_ORIGINAL_BOOKS / story_name
            else:
                story_dir = SOURCE_MODIFIED_BOOKS / story_name
            
            if not story_dir.exists():
                log(f"Story not found: {story_dir}", "WARN")
                continue
            
            log(f"\nProcessing: {story_name} ({variant})")
            
            # Reset evaluator for new story (clean state)
            evaluator.reset()
            
            chapter_files = get_chapter_files(story_dir)
            
            # Apply max_chapters limit if specified
            if max_chapters is not None:
                chapter_files = chapter_files[:max_chapters]
            
            log(f"  Found {len(chapter_files)} chapters" + (f" (limited to {max_chapters})" if max_chapters else ""))
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                # Use Phase 4 structured output if --structured flag is passed
                if structured:
                    errors, duration = evaluator.evaluate_chapter_v2(
                        chapter_text, i,
                        story=story_name,
                        variant=variant,
                        chapter_name=chapter_file.name
                    )
                else:
                    errors, duration = evaluator.evaluate_chapter(
                        chapter_text, i,
                        story=story_name,
                        variant=variant,
                        chapter_name=chapter_file.name
                    )
                
                chapter_errors = []
                for e in errors:
                    chapter_errors.append(ChapterError(
                        chapter_file=chapter_file.name,
                        category=e.get("category", "unknown"),
                        error_type=e.get("error_type", "unknown"),
                        description=e.get("description", ""),
                        story_fragment=e.get("story_fragment", ""),
                    ))
                
                result = ChapterResult(
                    story_name=story_name,
                    variant=variant,
                    chapter_file=chapter_file.name,
                    chapter_number=i,
                    errors=chapter_errors,
                    duration_seconds=duration,
                    success=True,
                )
                
                results.results.append(result)
                results.chapters_processed += 1
                results.total_errors += len(chapter_errors)
                
                log(f"    -> {len(chapter_errors)} errors ({duration:.1f}s)")
    
    # Save results
    output_file = experiment_dir / "step2_logic_results.json"
    with open(output_file, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    
    log(f"\nStep 2 complete: {results.chapters_processed} chapters, {results.total_errors} errors")
    log(f"Results saved to: {output_file}")
    
    return results


# =============================================================================
# DEBUG MODE: Use existing extractions without LLM calls
# =============================================================================

def run_step2_debug(experiment_dir: Path, stories: List[str]) -> None:
    """
    Debug mode: Load existing extractions from step2_extractions.jsonl and run
    them through the Logic Engine without calling any LLM.
    
    This mode is for debugging and analyzing how the engine processes
    previously extracted data. It logs detailed debug information to console
    and to debug_engine.jsonl.
    
    No LLM calls are made. All data comes from existing step2_extractions.jsonl.
    
    Args:
        experiment_dir: Path to the experiment directory with existing extractions
        stories: List of story names to process
    """
    from engine import (
        StateManager, 
        RuleRegistry, 
        EventExecutor, 
        FinalAnalyzer,
        AliasResolver,
        ItemTracker,
    )
    
    log("=" * 60)
    log("DEBUG MODE: Logic Engine Analysis (No LLM)")
    log("=" * 60)
    log("This mode loads existing extractions and runs them through the engine")
    log("for detailed debugging. No LLM calls will be made.")
    log("=" * 60)
    
    # Check for existing extractions file
    extraction_file = experiment_dir / "step2_extractions.jsonl"
    if not extraction_file.exists():
        log(f"ERROR: No extractions file found at {extraction_file}", "ERROR")
        log("Run step 2 with an LLM first to generate extractions.")
        return
    
    # Load all extractions
    log(f"\nLoading extractions from: {extraction_file}")
    extractions = []
    with open(extraction_file, "r") as f:
        for line in f:
            if line.strip():
                extractions.append(json.loads(line))
    
    log(f"Loaded {len(extractions)} chapter extractions")
    
    # Group by story/variant
    extraction_groups: Dict[Tuple[str, str], List[Dict]] = {}
    for ext in extractions:
        key = (ext["story"], ext["variant"])
        if key not in extraction_groups:
            extraction_groups[key] = []
        extraction_groups[key].append(ext)
    
    # Sort each group by chapter number
    for key in extraction_groups:
        extraction_groups[key].sort(key=lambda x: x["chapter"])
    
    log(f"Found {len(extraction_groups)} story/variant combinations")
    
    # Create debug output file
    debug_file = experiment_dir / "debug_engine.jsonl"
    debug_txt_file = experiment_dir / "debug_engine.txt"
    
    # Initialize output files
    with open(debug_file, "w") as f:
        f.write("")
    with open(debug_txt_file, "w") as f:
        f.write(f"DEBUG ENGINE LOG - {datetime.now().isoformat()}\n")
        f.write("=" * 80 + "\n\n")
    
    def debug_log(message: str, entry: Dict = None):
        """Log to console and files."""
        log(message)
        with open(debug_txt_file, "a") as f:
            f.write(message + "\n")
        if entry:
            with open(debug_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
    
    # Filter by requested stories
    for (story_name, variant), chapter_extractions in extraction_groups.items():
        if stories and story_name not in stories:
            debug_log(f"Skipping {story_name} ({variant}) - not in requested stories")
            continue
        
        debug_log(f"\n{'='*60}")
        debug_log(f"PROCESSING: {story_name} ({variant})")
        debug_log(f"{'='*60}")
        
        # Initialize engine modules for this story
        state_manager = StateManager()
        rule_registry = RuleRegistry(RULES_DIR)
        rule_registry.load_legacy_rules()
        
        alias_resolver = AliasResolver()
        item_tracker = ItemTracker()
        event_executor = EventExecutor(state_manager, rule_registry)
        final_analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker, alias_resolver)
        
        story_violations = []
        all_events = []
        
        for ext in chapter_extractions:
            chapter_num = ext["chapter"]
            chapter_file = ext["chapter_file"]
            structured = ext.get("extraction", {})
            
            debug_log(f"\n--- Chapter {chapter_num}: {chapter_file} ---")
            
            # Log what we're feeding to the engine
            entities = structured.get("entities", {})
            events = structured.get("events", [])
            initial_rules = structured.get("initial_rules", [])
            
            debug_entry = {
                "type": "chapter_input",
                "story": story_name,
                "variant": variant,
                "chapter": chapter_num,
                "chapter_file": chapter_file,
                "timestamp": datetime.now().isoformat(),
                "input": {
                    "characters": len(entities.get("characters", [])),
                    "locations": len(entities.get("locations", [])),
                    "items": len(entities.get("items", [])),
                    "relationships": len(entities.get("relationships", [])),
                    "events": len(events),
                    "initial_rules": len(initial_rules),
                },
                "entities": entities,
                "events": events,
                "initial_rules": initial_rules,
            }
            debug_log(f"  Input: {debug_entry['input']}", debug_entry)
            
            # Log characters
            for char in entities.get("characters", []):
                debug_log(f"    Character: {char.get('id')} ({char.get('name')}) aliases={char.get('aliases', [])}")
            
            # Log items with relevance
            for item in entities.get("items", []):
                debug_log(f"    Item: {item.get('id')} ({item.get('name')}) relevance={item.get('relevance', 'unknown')}")
            
            # Log relationships
            for rel in entities.get("relationships", []):
                debug_log(f"    Relationship: {rel.get('from')} -> {rel.get('to')} ({rel.get('type')})")
            
            # Log events
            for event in events:
                debug_log(f"    Event: {event.get('id')} {event.get('type')} agent={event.get('agent')} patient={event.get('patient')}")
                debug_log(f"           source: {event.get('source_text', '')[:60]}...")
            
            # Normalize aliases
            structured, alias_conflicts = alias_resolver.normalize_extraction(structured, chapter_num)
            
            if alias_conflicts:
                for conflict in alias_conflicts:
                    conflict_entry = {
                        "type": "alias_conflict",
                        "story": story_name,
                        "variant": variant,
                        "chapter": chapter_num,
                        "conflict": conflict.to_dict(),
                    }
                    debug_log(f"  [ALIAS CONFLICT] {conflict.alias} -> {conflict.canonical_ids}", conflict_entry)
            
            # Process items
            structured = item_tracker.process_extraction(structured, chapter_num)
            
            # Log item tracker state
            item_stats = item_tracker.get_statistics()
            debug_log(f"  Item Tracker: {item_stats['active_items']} active, {item_stats['suppressed_items']} suppressed")
            
            # Run the engine evaluation
            debug_log(f"\n  Running EventExecutor.evaluate_chapter_structured()...")
            eval_result = event_executor.evaluate_chapter_structured(structured, chapter_num)
            
            # Log events with global IDs
            for event in structured.get("events", []):
                all_events.append({
                    "chapter": chapter_num,
                    "global_id": event.get("global_id"),
                    "local_id": event.get("id"),
                    "type": event.get("type"),
                    "agent": event.get("agent"),
                    "patient": event.get("patient"),
                    "location": event.get("location"),
                })
                debug_log(f"    Event {event.get('global_id')} (was {event.get('id')}): {event.get('type')}")
            
            # Log ASP facts generated
            asp_lines = [line for line in eval_result.asp_facts.split('\n') if line.strip()]
            debug_log(f"\n  ASP Facts Generated ({len(asp_lines)} lines):")
            for fact in asp_lines[:20]:  # First 20 facts
                debug_log(f"    {fact}")
            if len(asp_lines) > 20:
                debug_log(f"    ... and {len(asp_lines) - 20} more facts")
            
            # Log violations
            debug_log(f"\n  Violations Detected: {len(eval_result.violations)}")
            for v in eval_result.violations:
                violation_entry = {
                    "type": "violation",
                    "story": story_name,
                    "variant": variant,
                    "chapter": chapter_num,
                    "violation": v.to_dict(),
                }
                debug_log(f"    [VIOLATION] {v.category}/{v.violation_type}: {v.rule}", violation_entry)
                debug_log(f"                entities: {v.entities}")
                debug_log(f"                event: {v.event_id}")
                debug_log(f"                source: {v.source_text}")
                story_violations.append(v.to_dict())
            
            # Record for final analysis
            final_analyzer.record_chapter_evaluation(
                chapter_num=chapter_num,
                events=structured.get("events", []),
                violations=[v.to_dict() for v in eval_result.violations],
                entities=structured.get("entities", {}),
            )
            
            # Log state after this chapter
            debug_log(f"\n  State after chapter {chapter_num}:")
            alias_stats_ch = alias_resolver.get_statistics()
            debug_log(f"    Characters known: {alias_stats_ch['total_canonical_ids']}")
            
            chapter_output = {
                "type": "chapter_output",
                "story": story_name,
                "variant": variant,
                "chapter": chapter_num,
                "asp_facts_count": len(eval_result.asp_facts),
                "violations_count": len(eval_result.violations),
                "events_processed": len(structured.get("events", [])),
            }
            debug_log("", chapter_output)
        
        # Run final analysis
        debug_log(f"\n{'='*40}")
        debug_log(f"FINAL ANALYSIS: {story_name} ({variant})")
        debug_log(f"{'='*40}")
        
        story_id = f"{story_name}_{variant}"
        final_result = final_analyzer.analyze(story_id, len(chapter_extractions))
        
        # Log final analysis results
        debug_log(f"\nTotal events processed: {len(all_events)}")
        debug_log(f"Total violations: {len(story_violations)}")
        debug_log(f"Loose ends: {len(final_result.loose_ends)}")
        debug_log(f"Long-range inconsistencies: {len(final_result.long_range_inconsistencies)}")
        
        for le in final_result.loose_ends:
            le_entry = {
                "type": "loose_end",
                "story": story_name,
                "variant": variant,
                "loose_end": le.to_dict() if hasattr(le, 'to_dict') else str(le),
            }
            debug_log(f"  [LOOSE END] {le_entry['loose_end']}", le_entry)
        
        for lri in final_result.long_range_inconsistencies:
            lri_entry = {
                "type": "long_range_inconsistency",
                "story": story_name,
                "variant": variant,
                "inconsistency": lri.to_dict() if hasattr(lri, 'to_dict') else str(lri),
            }
            debug_log(f"  [LONG-RANGE] {lri_entry['inconsistency']}", lri_entry)
        
        # Log all violations for this story
        debug_log(f"\n--- All Violations Summary ---")
        violation_by_type = {}
        for v in story_violations:
            vtype = v.get("violation_type", "unknown")
            if vtype not in violation_by_type:
                violation_by_type[vtype] = []
            violation_by_type[vtype].append(v)
        
        for vtype, violations in sorted(violation_by_type.items()):
            debug_log(f"  {vtype}: {len(violations)}")
            for v in violations[:5]:  # First 5 of each type
                debug_log(f"    - ch{v.get('chapter', '?')}: {v.get('rule', 'unknown')}")
            if len(violations) > 5:
                debug_log(f"    ... and {len(violations) - 5} more")
        
        final_summary = {
            "type": "story_summary",
            "story": story_name,
            "variant": variant,
            "chapters_processed": len(chapter_extractions),
            "total_events": len(all_events),
            "total_violations": len(story_violations),
            "violations_by_type": {k: len(v) for k, v in violation_by_type.items()},
            "loose_ends": len(final_result.loose_ends),
            "long_range_inconsistencies": len(final_result.long_range_inconsistencies),
        }
        debug_log("", final_summary)
        
        # Log alias resolver stats
        alias_stats = alias_resolver.get_statistics()
        debug_log(f"\nAlias Resolver: {alias_stats['total_canonical_ids']} characters, "
                  f"{alias_stats['total_aliases']} aliases, "
                  f"{alias_stats['conflicts_detected']} conflicts")
        
        # Log item tracker stats  
        item_stats = item_tracker.get_statistics()
        debug_log(f"Item Tracker: {item_stats['total_items']} total, "
                  f"{item_stats['active_items']} active, "
                  f"{item_stats['suppressed_items']} suppressed, "
                  f"{item_stats['causal_items']} causal, "
                  f"{item_stats['latent_items']} latent")
    
    debug_log(f"\n{'='*60}")
    debug_log(f"DEBUG MODE COMPLETE")
    debug_log(f"{'='*60}")
    debug_log(f"Debug JSONL output: {debug_file}")
    debug_log(f"Debug text output: {debug_txt_file}")
    log(f"\nDebug files written:")
    log(f"  - {debug_file}")
    log(f"  - {debug_txt_file}")


# =============================================================================
# PHASE 5: ENGINE-BASED EVALUATION (Step 5.3)
# =============================================================================

def run_step2_engine(experiment_dir: Path, stories: List[str], llm_url: str, 
                     max_chapters: int = None, api_mode: str = "local", 
                     api_model: str = None, api_delay: float = 0.0) -> StepResults:
    """
    Step 2 using the new engine modules (Phase 5).
    
    Uses:
        - StateManager for world state
        - RuleRegistry for rule management
        - EventExecutor for event processing
        - FinalAnalyzer for final chapter analysis
        - LearningAdapter for ILASP integration
    
    Maintains backward-compatible result format while using new pipeline.
    """
    from engine import (
        StateManager, 
        RuleRegistry, 
        EventExecutor, 
        FinalAnalyzer,
        LearningAdapter,
        AliasResolver,
        build_continuity_context,
        ItemTracker,
    )
    
    log("=" * 60)
    log("STEP 2: Logic-Based Evaluation (Engine Modules - Phase 5)")
    log("=" * 60)
    
    results = StepResults(
        step=2,
        approach="logic_engine",  # Mark as using new engine
        timestamp=datetime.now().isoformat(),
    )
    
    # Create log files
    log_file = experiment_dir / "step2_engine_log.jsonl"
    event_log_file = experiment_dir / "step2_events_log.jsonl"
    extraction_log_file = experiment_dir / "step2_extractions.jsonl"
    alias_conflicts_file = experiment_dir / "step2_alias_conflicts.jsonl"
    item_stats_file = experiment_dir / "step2_item_stats.jsonl"
    final_analysis_file = experiment_dir / "step2_final_analysis.json"
    
    log(f"Logging to: {log_file}")
    log(f"Extractions log: {extraction_log_file}")
    log(f"Events log: {event_log_file}")
    log(f"Alias conflicts log: {alias_conflicts_file}")
    log(f"Item stats log: {item_stats_file}")
    
    # Initialize API client for LLM extraction
    api_client = create_api_client(api_mode, api_model, llm_url, api_delay)
    
    # Initialize log files
    with open(event_log_file, "w") as f:
        f.write("")
    with open(extraction_log_file, "w") as f:
        f.write("")
    with open(alias_conflicts_file, "w") as f:
        f.write("")
    with open(item_stats_file, "w") as f:
        f.write("")
    
    for story_name in stories:
        for variant in ["original", "modified"]:
            if variant == "original":
                story_dir = SOURCE_ORIGINAL_BOOKS / story_name
            else:
                story_dir = SOURCE_MODIFIED_BOOKS / story_name
            
            if not story_dir.exists():
                log(f"Story not found: {story_dir}", "WARN")
                continue
            
            log(f"\nProcessing: {story_name} ({variant})")
            
            # Initialize engine modules for this story
            state_manager = StateManager()
            rule_registry = RuleRegistry(RULES_DIR)
            rule_registry.load_legacy_rules()  # Load default rules
            
            alias_resolver = AliasResolver()  # Phase 2: Canonical identity resolution
            item_tracker = ItemTracker()  # Phase 4: Item lifecycle tracking
            event_executor = EventExecutor(state_manager, rule_registry)
            final_analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker, alias_resolver)  # Phase 7: Full diagnostics
            learning_adapter = LearningAdapter(rule_registry)
            
            chapter_files = get_chapter_files(story_dir)
            
            if max_chapters is not None:
                chapter_files = chapter_files[:max_chapters]
            
            log(f"  Found {len(chapter_files)} chapters" + (f" (limited to {max_chapters})" if max_chapters else ""))
            
            story_violations: List[Dict] = []
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                start_time = time.time()
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                # Phase 3: Build continuity context from accumulated state
                continuity_context = build_continuity_context(
                    state_manager, alias_resolver, i
                )
                
                # Step 1: Structure chapter with LLM (with continuity context)
                structured = _structure_chapter_standalone(
                    chapter_text, 
                    api_client,
                    known_characters_json=continuity_context.to_characters_json(),
                    known_relationships_json=continuity_context.to_relationships_json(),
                    known_character_states_json=continuity_context.to_character_states_json(),
                )
                
                # Log LLM extraction to file (include context for debugging)
                extraction_entry = {
                    "story": story_name,
                    "variant": variant,
                    "chapter": i,
                    "chapter_file": chapter_file.name,
                    "timestamp": datetime.now().isoformat(),
                    "continuity_context": continuity_context.to_dict(),
                    "extraction": structured,
                }
                with open(extraction_log_file, "a") as f:
                    f.write(json.dumps(extraction_entry) + "\n")
                
                # Phase 2: Normalize aliases to canonical IDs before sending to logic engine
                structured, alias_conflicts = alias_resolver.normalize_extraction(structured, i)
                
                # Log any alias conflicts detected
                for conflict in alias_conflicts:
                    conflict_entry = {
                        "story": story_name,
                        "variant": variant,
                        "chapter": i,
                        "chapter_file": chapter_file.name,
                        "timestamp": datetime.now().isoformat(),
                        "conflict": conflict.to_dict(),
                    }
                    with open(alias_conflicts_file, "a") as f:
                        f.write(json.dumps(conflict_entry) + "\n")
                    log(f"    [ALIAS CONFLICT] '{conflict.alias}' -> {conflict.canonical_ids}", "WARN")
                
                # Phase 4: Process items and filter background items
                structured = item_tracker.process_extraction(structured, i)
                
                # Log item stats for this chapter
                item_stats = item_tracker.get_statistics()
                item_stats_entry = {
                    "story": story_name,
                    "variant": variant,
                    "chapter": i,
                    "chapter_file": chapter_file.name,
                    "timestamp": datetime.now().isoformat(),
                    "stats": item_stats,
                }
                with open(item_stats_file, "a") as f:
                    f.write(json.dumps(item_stats_entry) + "\n")
                
                # Step 2: Evaluate using EventExecutor
                eval_result = event_executor.evaluate_chapter_structured(
                    structured, i
                )
                
                # Log events to events file (after global IDs assigned by EventExecutor)
                for event in structured.get("events", []):
                    event_entry = {
                        "story": story_name,
                        "variant": variant,
                        "chapter": i,
                        "chapter_file": chapter_file.name,
                        "event": event,
                    }
                    with open(event_log_file, "a") as f:
                        f.write(json.dumps(event_entry) + "\n")
                
                # Step 3: Record for final analysis
                final_analyzer.record_chapter_evaluation(
                    chapter_num=i,
                    events=structured.get("events", []),
                    violations=[v.to_dict() for v in eval_result.violations],
                    entities=structured.get("entities", {}),
                )
                
                # Step 4: ILASP learning (optional)
                if eval_result.violations:
                    learning_adapter.learn_rules_from_violations(
                        current_facts=eval_result.asp_facts,
                        violations=[v.to_dict() for v in eval_result.violations],
                        chapter_num=i,
                        story_id=story_name,
                    )
                
                duration = time.time() - start_time
                
                # Convert to backward-compatible format
                chapter_errors = []
                for v in eval_result.violations:
                    chapter_errors.append(ChapterError(
                        chapter_file=chapter_file.name,
                        category=v.category,
                        error_type=v.violation_type,
                        description=f"{v.rule}: {v.violation_type}",
                        story_fragment=v.source_text or "",
                    ))
                    story_violations.append(v.to_dict())
                
                result = ChapterResult(
                    story_name=story_name,
                    variant=variant,
                    chapter_file=chapter_file.name,
                    chapter_number=i,
                    errors=chapter_errors,
                    duration_seconds=duration,
                    success=True,
                )
                
                results.results.append(result)
                results.chapters_processed += 1
                results.total_errors += len(chapter_errors)
                
                log(f"    -> {len(chapter_errors)} errors ({duration:.1f}s)")
            
            # Run final analysis after all chapters
            story_id = f"{story_name}_{variant}"
            final_result = final_analyzer.analyze(story_id, len(chapter_files))
            
            # Save final analysis for this story
            analysis_output = experiment_dir / f"final_analysis_{story_name.replace(' ', '_').lower()}_{variant}.json"
            with open(analysis_output, "w") as f:
                f.write(final_result.to_json())
            
            log(f"  Final analysis: {len(final_result.loose_ends)} loose ends, "
                f"{len(final_result.long_range_inconsistencies)} long-range issues")
            
            # Log alias resolver statistics
            alias_stats = alias_resolver.get_statistics()
            log(f"  Alias resolver: {alias_stats['total_canonical_ids']} characters, "
                f"{alias_stats['total_aliases']} aliases, "
                f"{alias_stats['conflicts_detected']} conflicts")
            
            # Log item tracker statistics
            item_stats = item_tracker.get_statistics()
            log(f"  Item tracker: {item_stats['total_items']} items, "
                f"{item_stats['active_items']} active, "
                f"{item_stats['suppressed_items']} suppressed, "
                f"{item_stats['causal_items']} causal, "
                f"{item_stats['latent_items']} latent")
            
            # Reset for next story
            final_analyzer.reset()
    
    # Save results
    output_file = experiment_dir / "step2_engine_results.json"
    with open(output_file, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    
    log(f"\nStep 2 (Engine) complete: {results.chapters_processed} chapters, {results.total_errors} errors")
    log(f"Results saved to: {output_file}")
    
    return results


def _structure_chapter_standalone(
    chapter_text: str, 
    api_client,
    known_characters_json: str = "(No characters established yet)",
    known_relationships_json: str = "(No relationships established yet)",
    known_character_states_json: str = "(No character states established yet)",
) -> Dict[str, Any]:
    """
    Structure a chapter using LLM extraction.
    
    Standalone version for use with engine modules.
    Uses the comprehensive extraction prompt with relationship and behavior detection.
    
    Phase 3: Accepts continuity context parameters for prompt injection.
    
    Args:
        chapter_text: The chapter text to extract from
        api_client: API client for LLM calls
        known_characters_json: JSON string of known characters and aliases
        known_relationships_json: JSON string of known relationships
        known_character_states_json: JSON string of known character states
        
    Returns:
        Extracted structured data as dict
    """
    # Use the comprehensive prompt that includes relationship contradiction detection
    prompt = f"""Extract structured narrative data from the text below.

=== CONTINUITY CONTEXT (AUTHORITATIVE) ===
The following facts are TRUE before this chapter begins.
You MUST treat them as ground truth.
Do NOT reinterpret, soften, or restate them unless the chapter EXPLICITLY changes them.

KNOWN CHARACTERS:
{known_characters_json}

KNOWN RELATIONSHIPS:
{known_relationships_json}

KNOWN CHARACTER STATES:
{known_character_states_json}

IDENTITY RULES:
- Each character has ONE canonical id.
- If the text uses a title, nickname, or alternate name, map it to the canonical id.
- DO NOT create a new character if an alias matches a known character.
- Use the canonical id in ALL outputs.

=== CONSISTENCY RULES CONTEXT ===
Your extraction will be checked by a logic-based consistency verifier. The system detects:

1. RELATIONSHIP VIOLATIONS:
   - Sudden hostile→friendly or friendly→hostile flips without cause
   - Characters helping enemies or harming loved ones unexpectedly
   - CRITICAL: If someone who hates another shows warmth/kindness, this MUST be extracted

2. COHERENCE VIOLATIONS:
   - Characters in contradictory states
   - Actions that contradict established relationships

TEXT:
{chapter_text}

=== CHARACTER BEHAVIOR ANALYSIS (VERY IMPORTANT) ===
Pay SPECIAL ATTENTION to character behavior and emotional interactions:
- If a character who is normally HOSTILE shows WARMTH, KINDNESS, or AFFECTION → this is significant!
- If an enemy gives a farewell, hug, encouragement, or praise → ALWAYS extract this as an event
- Look for CONTRADICTIONS between established relationships and current actions
- Populate "aliases" ONLY if the chapter introduces a new way to refer to an existing character

If hostility, warmth, or affection is described for a GROUP
(e.g., "the family", "the guards", "his classmates"):

- Extract the relationship for EACH named individual in that group.
- Do not collapse group behavior into a single representative character.
Example:
"The group despised Alex" →
  member_1 -> alex (hostile)
  member_2 -> alex (hostile)
  member_3 -> alex (hostile)

EXAMPLES OF CRITICAL BEHAVIOR TO CAPTURE:
- "Uncle Vernon gave Harry a warm smile" → event type: "farewell" or "praise"
- "Have a good term," said the usually cold teacher warmly → event type: "farewell"
- An enemy wishing someone well → MUST be extracted as "farewell" event
- 
=== ITEM EXTRACTION RULES (CRITICAL) ===

ONLY extract an item if AT LEAST ONE of the following is true:
1. The item is carried, given, taken, used, lost, discovered, or destroyed
2. The item affects an event or a character's behavior
3. The item is mentioned with clear narrative emphasis (focus, repetition, or consequence)
4. The item is likely to persist across scenes or chapters
5. The item enables or blocks future actions (keys, weapons, letters, tools, artifacts)

DO NOT extract items that are:
- Ordinary background objects (chairs, tables, doors, food, clothing)
- Mentioned only as scenery or setting flavor
- Not interacted with by any character
- Immediately irrelevant and never referred to again in the chapter

=== OUTPUT FORMAT ===
Return ONLY this JSON structure:

{{
  "entities": {{
    "characters": [{{"id": "name_in_snake_case", "name": "Full Name", "aliases": [], "state": "normal/dead", "emotion": "emotion", "appearance": "normal/unusual"}}],
    "locations": [{{"id": "location_id", "name": "Location Name", "connections": []}}],
    "items": [{{"id": "item_id", "name": "Item Name", "state": "intact", "relevance": "causal|latent"}}],
    "relationships": [{{"from": "char_id", "to": "char_id", "type": "hostile/friendly/family/love/fear"}}]
  }},
  "events": [
    {{
      "id": "e1",
      "type": "meet|talk|give|take|attack|help|discover|arrive|leave|die|hug|praise|farewell|encourage|smile|wave",
      "agent": "character_id",
      "patient": "character_id_or_null",
      "location": "location_id_or_null",
      "source_text": "exact quote from text (max 80 chars)"
    }}
  ],
  "initial_rules": [
    {{"subject": "char_id", "predicate": "hates|loves|hostile|friendly", "object": "char_id"}}
  ]
}}

CRITICAL RULES:
- Extract ALL farewell/praise/encourage events, especially from hostile characters
- Include initial_rules ONLY for relationships EXPLICITLY stated or MODIFIED in this chapter
- DO NOT restate known relationships from the continuity context
- source_text MUST be an actual quote from the chapter
- Use relevance="causal" if the item participates in an event in this chapter
- Use relevance="latent" if the item is extracted under the CHEKHOV RULE
- Treat this chapter as a DELTA over the continuity context:
  - DO NOT restate unchanged relationships or states
  - ONLY extract new events, changes, or contradictions introduced in this chapter

Return ONLY valid JSON, no markdown or explanations."""

    try:
        response = api_client.extract(prompt, max_tokens=8192, timeout=180)
        
        # Parse JSON response
        import re
        cleaned = re.sub(r'```json\s*', '', response)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
        
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        log(f"Structure extraction failed: {e}", "WARN")
    
    return {"entities": {}, "events": [], "initial_rules": []}


# =============================================================================
# GROUND TRUTH COMPARISON
# =============================================================================

def load_ground_truth(story_name: str) -> List[Dict[str, Any]]:
    """
    Load ground truth errors from the errors_checklist CSV file for a story.
    Returns a list of dicts with: chunk, chapter, error_type, description, sentence
    """
    # Map story name to CSV filename
    csv_mapping = {
        "Harry Potter": "harry_potter_errors.csv",
        "The Hunger Games": "hunger_games_errors.csv",
        "The Lord of the Rings": "the_lord_of_the_rings_errors.csv",
        "Twilight": "twilight_errors.csv",
        "Goosebumps": "goosebumps_errors.csv",
    }
    
    csv_file = csv_mapping.get(story_name)
    if not csv_file:
        return []
    
    csv_path = ERRORS_CHECKLIST_DIR / csv_file
    if not csv_path.exists():
        return []
    
    ground_truth = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ground_truth.append({
                "chunk": int(row.get("Chunk", 0)),
                "chapter": row.get("Chapter", ""),
                "error_type": row.get("Error Type", ""),
                "description": row.get("Error description", ""),
                "sentence": row.get("Error sentence", ""),
            })
    
    return ground_truth


def _map_error_type_to_category(error_type: str) -> str:
    """Map ground truth error types to our category system."""
    mapping = {
        "Basic Coherence": "coherence",
        "Emotional Relations": "emotional",
        "Location correctness": "location",
        "Temporal Order": "temporal",
        "Causality": "causality",
    }
    return mapping.get(error_type, "unknown")


def compare_with_ground_truth(
    results: List[Dict[str, Any]], 
    story_name: str,
    variant: str = "modified"
) -> Dict[str, Any]:
    """
    Compare detected errors against ground truth for a story.
    
    Returns a dict with:
    - total_ground_truth: Total errors in ground truth for processed chapters
    - total_detected: Total errors detected
    - true_positives: Errors correctly detected (matching chapter)
    - false_positives: Errors detected but not in ground truth
    - false_negatives: Errors in ground truth but not detected
    - precision, recall, f1: Metrics
    - details: Per-chapter breakdown
    """
    if variant != "modified":
        # Ground truth is only for modified stories
        return {"note": "Ground truth comparison only applicable to modified variant"}
    
    ground_truth = load_ground_truth(story_name)
    if not ground_truth:
        return {"note": f"No ground truth found for {story_name}"}
    
    # Get chapters that were processed
    processed_chapters = set()
    detected_by_chapter = {}
    
    for result in results:
        if result.get("story_name") == story_name and result.get("variant") == variant:
            chapter = result.get("chapter_file", "")
            processed_chapters.add(chapter)
            if chapter not in detected_by_chapter:
                detected_by_chapter[chapter] = []
            detected_by_chapter[chapter].extend(result.get("errors", []))
    
    # Filter ground truth to only processed chapters
    gt_in_range = [gt for gt in ground_truth if gt["chapter"] in processed_chapters]
    gt_chapters = {gt["chapter"] for gt in gt_in_range}
    
    # Calculate metrics
    detected_chapters = {ch for ch, errors in detected_by_chapter.items() if errors}
    
    # True positives: chapters where both GT and detection have errors
    true_positive_chapters = gt_chapters & detected_chapters
    
    # False negatives: GT has error but not detected
    false_negative_chapters = gt_chapters - detected_chapters
    
    # False positives: detected error but not in GT
    false_positive_chapters = detected_chapters - gt_chapters
    
    # Build detailed breakdown
    details = []
    for gt in gt_in_range:
        chapter = gt["chapter"]
        detected = detected_by_chapter.get(chapter, [])
        details.append({
            "chapter": chapter,
            "ground_truth_type": gt["error_type"],
            "ground_truth_category": _map_error_type_to_category(gt["error_type"]),
            "ground_truth_description": gt["description"][:100] + "..." if len(gt["description"]) > 100 else gt["description"],
            "detected_count": len(detected),
            "detected_categories": list(set(e.get("category", "unknown") for e in detected)),
            "match": chapter in true_positive_chapters,
        })
    
    # Add false positives (detected but not in GT)
    for chapter in false_positive_chapters:
        detected = detected_by_chapter.get(chapter, [])
        details.append({
            "chapter": chapter,
            "ground_truth_type": None,
            "ground_truth_category": None,
            "ground_truth_description": None,
            "detected_count": len(detected),
            "detected_categories": list(set(e.get("category", "unknown") for e in detected)),
            "match": False,
            "false_positive": True,
        })
    
    # Sort by chapter
    details.sort(key=lambda x: x["chapter"])
    
    # Calculate precision, recall, F1 (chapter-level)
    tp = len(true_positive_chapters)
    fp = len(false_positive_chapters)
    fn = len(false_negative_chapters)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "story": story_name,
        "chapters_processed": len(processed_chapters),
        "ground_truth_errors_in_range": len(gt_in_range),
        "total_detected_errors": sum(len(detected_by_chapter.get(ch, [])) for ch in processed_chapters),
        "chapters_with_gt_errors": len(gt_chapters),
        "chapters_with_detected_errors": len(detected_chapters),
        "true_positive_chapters": len(true_positive_chapters),
        "false_positive_chapters": len(false_positive_chapters),
        "false_negative_chapters": len(false_negative_chapters),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "details": details,
    }


def generate_summary(experiment_dir: Path):
    """Generate comparison summary from both steps."""
    log("=" * 60)
    log("Generating Experiment Summary")
    log("=" * 60)
    
    # Load step 1 results
    step1_file = experiment_dir / "step1_llm_results.json"
    step2_file = experiment_dir / "step2_logic_results.json"
    
    step1_data = {}
    step2_data = {}
    
    if step1_file.exists():
        with open(step1_file) as f:
            step1_data = json.load(f)
        log(f"Loaded Step 1 results: {step1_data.get('total_errors', 0)} errors")
    else:
        log("Step 1 results not found", "WARN")
    
    if step2_file.exists():
        with open(step2_file) as f:
            step2_data = json.load(f)
        log(f"Loaded Step 2 results: {step2_data.get('total_errors', 0)} errors")
    else:
        log("Step 2 results not found", "WARN")
    
    # Build summary
    summary = {
        "experiment_name": experiment_dir.name,
        "generated_at": datetime.now().isoformat(),
        "step1_llm": {
            "approach": "LLM-only",
            "chapters_processed": step1_data.get("chapters_processed", 0),
            "total_errors": step1_data.get("total_errors", 0),
            "timestamp": step1_data.get("timestamp", ""),
        },
        "step2_logic": {
            "approach": "Logic (ILASP + Clingo)",
            "chapters_processed": step2_data.get("chapters_processed", 0),
            "total_errors": step2_data.get("total_errors", 0),
            "timestamp": step2_data.get("timestamp", ""),
        },
        "comparison": {},
    }
    
    # Per-story breakdown
    stories_summary = {}
    
    for result in step1_data.get("results", []):
        key = f"{result['story_name']}_{result['variant']}"
        if key not in stories_summary:
            stories_summary[key] = {"story": result["story_name"], "variant": result["variant"], "llm_errors": 0, "logic_errors": 0}
        stories_summary[key]["llm_errors"] += result.get("error_count", 0)
    
    for result in step2_data.get("results", []):
        key = f"{result['story_name']}_{result['variant']}"
        if key not in stories_summary:
            stories_summary[key] = {"story": result["story_name"], "variant": result["variant"], "llm_errors": 0, "logic_errors": 0}
        stories_summary[key]["logic_errors"] += result.get("error_count", 0)
    
    summary["comparison"]["per_story"] = list(stories_summary.values())
    
    # Category breakdown
    llm_categories = {cat: 0 for cat in ERROR_CATEGORIES}
    logic_categories = {cat: 0 for cat in ERROR_CATEGORIES}
    
    for result in step1_data.get("results", []):
        for error in result.get("errors", []):
            cat = error.get("category", "unknown")
            if cat in llm_categories:
                llm_categories[cat] += 1
    
    for result in step2_data.get("results", []):
        for error in result.get("errors", []):
            cat = error.get("category", "unknown")
            if cat in logic_categories:
                logic_categories[cat] += 1
    
    summary["comparison"]["by_category"] = {
        "llm": llm_categories,
        "logic": logic_categories,
    }
    
    # Ground truth comparison (for modified stories only)
    ground_truth_results = {}
    stories_in_results = set()
    
    for result in step2_data.get("results", []):
        stories_in_results.add(result.get("story_name"))
    
    for story_name in stories_in_results:
        gt_comparison = compare_with_ground_truth(
            step2_data.get("results", []),
            story_name,
            variant="modified"
        )
        if "note" not in gt_comparison:
            ground_truth_results[story_name] = gt_comparison
    
    summary["ground_truth_comparison"] = ground_truth_results
    
    # Save summary
    output_file = experiment_dir / "experiment_summary.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    log(f"\nSummary saved to: {output_file}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("EXPERIMENT SUMMARY")
    print("=" * 60)
    print(f"\nStep 1 (LLM-only):   {summary['step1_llm']['total_errors']} errors")
    print(f"Step 2 (Logic):      {summary['step2_logic']['total_errors']} errors")
    print("\nPer-story breakdown:")
    for s in summary["comparison"]["per_story"]:
        print(f"  {s['story']} ({s['variant']}): LLM={s['llm_errors']}, Logic={s['logic_errors']}")
    
    # Print ground truth comparison
    if ground_truth_results:
        print("\n" + "-" * 60)
        print("GROUND TRUTH COMPARISON (Modified Stories)")
        print("-" * 60)
        for story_name, gt in ground_truth_results.items():
            print(f"\n{story_name}:")
            print(f"  Chapters processed: {gt['chapters_processed']}")
            print(f"  Ground truth errors in range: {gt['ground_truth_errors_in_range']}")
            print(f"  Detected errors: {gt['total_detected_errors']}")
            print(f"  True positive chapters: {gt['true_positive_chapters']}")
            print(f"  False positive chapters: {gt['false_positive_chapters']}")
            print(f"  False negative chapters: {gt['false_negative_chapters']}")
            print(f"  Precision: {gt['precision']:.1%}")
            print(f"  Recall: {gt['recall']:.1%}")
            print(f"  F1 Score: {gt['f1_score']:.1%}")
            
            # Print details for missed detections
            missed = [d for d in gt['details'] if not d.get('match') and d.get('ground_truth_type')]
            if missed:
                print(f"  Missed errors:")
                for m in missed:
                    print(f"    - {m['chapter']}: {m['ground_truth_type']} - {m['ground_truth_description']}")
    
    return summary


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run narrative evaluation experiment (chapter by chapter)"
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="narrative_experiment",
        help="Name for this experiment",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=[1, 2],
        help="Which step to run (1=LLM-only, 2=Logic)",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Generate summary from existing step results",
    )
    parser.add_argument(
        "--llm-url",
        type=str,
        default="http://localhost:8080/v1",
        help="LLM server URL (default: http://localhost:8080/v1)",
    )
    parser.add_argument(
        "--stories",
        type=str,
        nargs="+",
        default=None,
        help="Stories to process (default: all)",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=None,
        help="Maximum number of chapters to process (for testing)",
    )
    parser.add_argument(
        "--api-mode",
        type=str,
        choices=["local", "gemini", "openai", "debug"],
        default="local",
        help="API mode: 'local' for local LLM server, 'gemini' for Google Gemini, 'openai' for OpenAI, 'debug' for using existing extractions without LLM (default: local)",
    )
    parser.add_argument(
        "--api-model",
        type=str,
        default=None,
        help="Model to use (default: auto for local, gemini-2.0-flash for Gemini, gpt-4o for OpenAI)",
    )
    parser.add_argument(
        "--api-delay",
        type=float,
        default=0.0,
        help="Delay in seconds between API calls (helps avoid rate limiting, default: 0)",
    )
    parser.add_argument(
        "--structured",
        action="store_true",
        help="Use Phase 4 structured output pipeline (no LLM interpretation of violations)",
    )
    parser.add_argument(
        "--engine",
        action="store_true",
        help="Use Phase 5 engine modules (StateManager, EventExecutor, etc.) with final analysis",
    )
    
    args = parser.parse_args()
    
    # Validate API keys if using cloud APIs
    if args.api_mode == "gemini" and not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY environment variable not set")
        print("Set it with: export GEMINI_API_KEY='your-api-key'")
        sys.exit(1)
    if args.api_mode == "openai" and not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-api-key'")
        sys.exit(1)
    
    # Create/find experiment directory
    experiment_dir = EXPERIMENTS_DIR / args.experiment_name
    experiment_dir.mkdir(parents=True, exist_ok=True)
    
    # Set up console logging to file
    console_log_file = experiment_dir / "full_console_log.txt"
    set_console_log_file(console_log_file)
    
    stories = args.stories if args.stories else STORIES
    max_chapters = args.max_chapters
    
    # Log API mode
    log(f"API Mode: {args.api_mode}", "INFO")
    if args.api_model:
        log(f"API Model: {args.api_model}", "INFO")
    
    if args.summarize:
        generate_summary(experiment_dir)
    elif args.step == 1:
        run_step1_llm(experiment_dir, stories, args.llm_url, max_chapters, 
                      api_mode=args.api_mode, api_model=args.api_model, api_delay=args.api_delay)
    elif args.step == 2:
        # Debug mode: use existing extractions without LLM
        if args.api_mode == "debug":
            if not getattr(args, 'engine', False):
                print("WARNING: Debug mode requires --engine flag. Adding it automatically.")
            run_step2_debug(experiment_dir, stories)
        # Choose evaluation mode based on flags
        elif getattr(args, 'engine', False):
            # Phase 5: Use new engine modules
            run_step2_engine(experiment_dir, stories, args.llm_url, max_chapters,
                             api_mode=args.api_mode, api_model=args.api_model, api_delay=args.api_delay)
        else:
            # Original or Phase 4 mode
            run_step2_logic(experiment_dir, stories, args.llm_url, max_chapters,
                            api_mode=args.api_mode, api_model=args.api_model, api_delay=args.api_delay,
                            structured=getattr(args, 'structured', False))
    else:
        print("Please specify --step 1, --step 2, or --summarize")
        print("\nUsage:")
        print("  Step 1 (LLM-only):  python run_narrative_experiment.py --step 1 --experiment-name my_exp")
        print("  Step 2 (Logic):     python run_narrative_experiment.py --step 2 --experiment-name my_exp")
        print("  Debug mode:         python run_narrative_experiment.py --step 2 --api-mode debug --experiment-name my_exp --engine")
        print("  Summarize:          python run_narrative_experiment.py --summarize --experiment-name my_exp")
        print("  Limit chapters:     python run_narrative_experiment.py --step 2 --max-chapters 5")
        print("\nAPI options:")
        print("  --api-mode gemini   Use Google Gemini API (requires GEMINI_API_KEY)")
        print("  --api-mode openai   Use OpenAI API (requires OPENAI_API_KEY)")
        print("  --api-mode debug    Use existing extractions without LLM (requires --engine)")
        print("  --api-model MODEL   Specify model (e.g., gemini-2.0-flash, gpt-4o-mini)")
        print("\nPhase 4/5 options:")
        print("  --structured        Use structured output only (no LLM interpretation)")
        print("  --engine            Use Phase 5 engine modules with final analysis")


if __name__ == "__main__":
    main()
