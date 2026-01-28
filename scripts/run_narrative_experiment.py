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

# Add script dir to path for imports
sys.path.insert(0, str(SCRIPT_DIR))

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

LLM_LINT_PROMPT = """Find narrative errors in this chapter.

ERROR CATEGORIES:
1. CAUSALITY - unexplained effects, missing causes
2. COHERENCE - logical impossibilities (dead acting, wrong traits)
3. TEMPORAL - wrong event order, time paradoxes
4. LOCATION - characters in two places, impossible travel
5. EMOTIONAL - actions contradicting relationships

Respond ONLY with JSON:
{{"error_count": N, "errors": [{{"category": "causality|coherence|temporal|location|emotional", "description": "what's wrong"}}]}}

If no errors: {{"error_count": 0, "errors": []}}

CHAPTER:
{chapter_text}
"""


# =============================================================================
# LOGGING
# =============================================================================

def log(msg: str, level: str = "INFO"):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}", file=sys.stderr)


# =============================================================================
# LLM CLIENT
# =============================================================================

class LLMClient:
    """Simple LLM client for chapter evaluation."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0, log_file: Path = None):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.log_file = log_file
        
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
        import urllib.request
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False
    
    def evaluate_chapter(self, chapter_text: str, story: str = "", variant: str = "", chapter_name: str = "") -> Tuple[List[Dict], float, str, str]:
        """
        Evaluate a single chapter for narrative errors.
        
        Returns:
            Tuple of (list of error dicts, duration in seconds, prompt, response)
        """
        import urllib.request
        
        start_time = time.time()
        
        prompt = LLM_LINT_PROMPT.format(chapter_text=chapter_text)
        
        payload = {
            "model": "auto",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": 2048,
        }
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        
        response_text = ""
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
                response_text = data["choices"][0]["message"]["content"]
        except Exception as e:
            log(f"LLM request failed: {e}", "ERROR")
            return [], time.time() - start_time, prompt, str(e)
        
        duration = time.time() - start_time
        
        # Parse response
        errors = self._parse_response(response_text)
        
        # Log interaction
        self._log_interaction(story, variant, chapter_name, prompt, response_text, errors, duration)
        
        return errors, duration, prompt, response_text
    
    def _parse_response(self, response: str) -> List[Dict]:
        """Parse LLM response into error list."""
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
            return []
        
        try:
            data = json.loads(response[start:end + 1])
            errors = data.get("errors", [])
            error_count = data.get("error_count", len(errors))
            if error_count > 0:
                log(f"    LLM reported {error_count} errors", "DEBUG")
            return errors
        except json.JSONDecodeError as e:
            log(f"JSON parse error: {e}", "WARN")
            log(f"JSON preview: {response[start:start+200]}...", "DEBUG")
            return []


# =============================================================================
# LOGIC-BASED EVALUATOR
# =============================================================================

class LogicEvaluator:
    """Logic-based evaluator using ILASP and Clingo."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0, log_file: Path = None):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.general_rules = RULES_DIR / "general.lp"
        self.mode_declarations = RULES_DIR / "ilasp_mode_declarations.las"
        self.log_file = log_file
        
        # Accumulated knowledge for incremental learning
        self.accumulated_facts: List[str] = []
        self.learned_rules: List[str] = []
        
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
        """Reset accumulated knowledge (for new story)."""
        self.accumulated_facts = []
        self.learned_rules = []
    
    def evaluate_chapter(self, chapter_text: str, chapter_num: int, story: str = "", variant: str = "", chapter_name: str = "") -> Tuple[List[Dict], float]:
        """
        Evaluate a chapter using logic-based approach.
        
        Steps:
        1. Structure chapter with LLM
        2. Convert to ASP facts
        3. Learn rules with ILASP (if not first chapter)
        4. Check with Clingo
        
        Returns:
            Tuple of (list of error dicts, duration in seconds)
        """
        start_time = time.time()
        
        # Step 1: Structure with LLM
        structured, struct_prompt, struct_response = self._structure_chapter(chapter_text)
        
        # Log structuring step
        self._log_interaction(
            story, variant, chapter_name, "structure",
            struct_prompt, struct_response, structured,
            time.time() - start_time
        )
        
        # Step 2: Convert to ASP
        facts = self._to_asp(structured, chapter_num)
        
        # Step 3: Learn rules with ILASP (incremental)
        if chapter_num > 0 and self.accumulated_facts:
            self._learn_rules(chapter_num)
        
        # Step 4: Check with Clingo
        violations = self._check_with_clingo(facts, chapter_num)
        
        # Update accumulated facts
        self.accumulated_facts.extend(facts.split('\n'))
        
        duration = time.time() - start_time
        
        # Convert violations to error format
        errors = []
        for v in violations:
            errors.append({
                "category": v.get("category", "unknown"),
                "error_type": v.get("type", "unknown"),
                "description": v.get("description", str(v)),
                "story_fragment": "",
            })
        
        return errors, duration
    
    def _structure_chapter(self, chapter_text: str) -> Tuple[Dict, str, str]:
        """Use LLM to structure chapter into JSON. Returns (structured_data, prompt, response)."""
        import urllib.request
        
        prompt = f"""Structure this story chapter into JSON:
- entities: {{characters: [{{id, name}}], objects: [{{id, type}}], locations: [{{id, name}}]}}
- events: [{{id, type, agent, patient, location}}]
- relationships: [{{type, from, to}}]

Chapter:
\"\"\"
{chapter_text[:15000]}
\"\"\"

Output ONLY valid JSON."""
        
        payload = {
            "model": "auto",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": 2048,
            "repetition_penalty": 1.2,
            "frequency_penalty": 0.5,
        }
        
        response_text = ""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
                response_text = data["choices"][0]["message"]["content"]
            
            # Parse JSON
            cleaned = re.sub(r'```json\s*', '', response_text)
            cleaned = re.sub(r'```\s*', '', cleaned)
            
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                return json.loads(match.group()), prompt, response_text
                
        except Exception as e:
            log(f"Structuring failed: {e}", "ERROR")
        
        return {"entities": {}, "events": [], "relationships": []}, prompt, response_text
    
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
        
        entities = data.get("entities", {})
        for char in entities.get("characters", []):
            cid = sanitize(char.get("id", char.get("name", "")))
            if cid and cid != "unknown":
                lines.append(f"character({cid}).")
        
        for obj in entities.get("objects", []):
            oid = sanitize(obj.get("id", obj.get("name", "")))
            if oid and oid != "unknown":
                lines.append(f"object({oid}).")
        
        for loc in entities.get("locations", []):
            lid = sanitize(loc.get("id", loc.get("name", "")))
            if lid and lid != "unknown":
                lines.append(f"location_entity({lid}).")
        
        for i, event in enumerate(data.get("events", [])):
            eid = sanitize(event.get("id", f"e{chapter_num}_{i+1}"))
            lines.append(f"event({eid}).")
            if event.get("type"):
                lines.append(f"event_type({eid}, {sanitize(event['type'])}).")
            if event.get("agent"):
                lines.append(f"agent({eid}, {sanitize(event['agent'])}).")
            if event.get("patient"):
                lines.append(f"patient({eid}, {sanitize(event['patient'])}).")
            if event.get("location"):
                lines.append(f"location({eid}, {sanitize(event['location'])}).")
        
        return "\n".join(lines)
    
    def _learn_rules(self, chapter_num: int):
        """Use ILASP to learn rules from accumulated facts."""
        task_lines = [
            "% ILASP Learning Task",
            "",
        ]
        
        # Include mode declarations
        if self.mode_declarations.exists():
            task_lines.append(self.mode_declarations.read_text())
        
        task_lines.append("\n% === BACKGROUND KNOWLEDGE ===\n")
        task_lines.extend(self.accumulated_facts)
        
        task_lines.append("\n% === EXAMPLES ===")
        task_lines.append("#pos({}, {violation(_,_,_,_)}).")
        
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
                        
        except Exception as e:
            log(f"ILASP error: {e}", "WARN")
        finally:
            os.unlink(task_path)
    
    def _check_with_clingo(self, facts: str, chapter_num: int) -> List[Dict]:
        """Use Clingo to find violations."""
        violations = []
        
        try:
            import clingo
        except ImportError:
            log("Clingo not available", "WARN")
            return []
        
        # Combine all knowledge
        program_parts = [facts]
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
            
            if self.general_rules.exists():
                ctl.load(str(self.general_rules))
            
            ctl.load(facts_path)
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
                                "description": f"Violation: {parts[1] if len(parts) > 1 else 'unknown'}",
                            })
                            
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


def run_step1_llm(experiment_dir: Path, stories: List[str], llm_url: str) -> StepResults:
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
    
    client = LLMClient(base_url=llm_url, log_file=log_file)
    
    if not client.check_server():
        log("LLM server not available!", "ERROR")
        return results
    
    log("LLM server is available")
    
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
            if variant == "original":
                log(f"  NOTE: Original books are error-free references - expect few/no errors")
            else:
                log(f"  NOTE: Modified books have injected errors - expect errors to be detected")
            
            chapter_files = get_chapter_files(story_dir)
            log(f"  Found {len(chapter_files)} chapters")
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                errors, duration, _, _ = client.evaluate_chapter(
                    chapter_text, 
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
    output_file = experiment_dir / "step1_llm_results.json"
    with open(output_file, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    
    log(f"\nStep 1 complete: {results.chapters_processed} chapters, {results.total_errors} errors")
    log(f"Results saved to: {output_file}")
    
    return results


def run_step2_logic(experiment_dir: Path, stories: List[str], llm_url: str) -> StepResults:
    """
    Step 2: Logic-based evaluation (ILASP + Clingo), chapter by chapter.
    """
    log("=" * 60)
    log("STEP 2: Logic-Based Evaluation (ILASP + Clingo)")
    log("=" * 60)
    
    results = StepResults(
        step=2,
        approach="logic",
        timestamp=datetime.now().isoformat(),
    )
    
    # Create log file for prompts/responses
    log_file = experiment_dir / "step2_logic_log.jsonl"
    log(f"Logging prompts/responses to: {log_file}")
    
    evaluator = LogicEvaluator(base_url=llm_url, log_file=log_file)
    
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
            log(f"  Found {len(chapter_files)} chapters")
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
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
    
    args = parser.parse_args()
    
    # Create/find experiment directory
    experiment_dir = EXPERIMENTS_DIR / args.experiment_name
    experiment_dir.mkdir(parents=True, exist_ok=True)
    
    stories = args.stories if args.stories else STORIES
    
    if args.summarize:
        generate_summary(experiment_dir)
    elif args.step == 1:
        run_step1_llm(experiment_dir, stories, args.llm_url)
    elif args.step == 2:
        run_step2_logic(experiment_dir, stories, args.llm_url)
    else:
        print("Please specify --step 1, --step 2, or --summarize")
        print("\nUsage:")
        print("  Step 1 (LLM-only):  python run_narrative_experiment.py --step 1 --experiment-name my_exp")
        print("  Step 2 (Logic):     python run_narrative_experiment.py --step 2 --experiment-name my_exp")
        print("  Summarize:          python run_narrative_experiment.py --summarize --experiment-name my_exp")


if __name__ == "__main__":
    main()
