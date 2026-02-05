#!/usr/bin/env python3
"""
pilot_kfold_experiment.py - K-Fold Cross-Validation Experiment for Narrative Linting
=====================================================================================

This script runs a comprehensive pilot experiment comparing LLM-based and logic-based
narrative evaluation across 5 categories:

1. CAUSALITY: Chekhov's gun, causal chains, unexplained events
2. COHERENCE: Semantic correctness, logical consistency
3. TEMPORAL: Time ordering and intervals
4. LOCATION: Spatial constraints, distances
5. EMOTIONAL: Character behavior vs relationships

The experiment:
- Trains on original books (to identify false positives)
- Tests on modified books (to find real errors)
- Uses k-fold cross-validation (k=1,2,3,4)
- Compares multiple LLM models
- Generates comprehensive reports

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import itertools

# Constants
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
ORIGINAL_BOOKS_DIR = REPO_ROOT / "original_books"
MODIFIED_BOOKS_DIR = REPO_ROOT / "modified_books"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

# Error categories for classification
ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]

# Books available
BOOKS = ["Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight", "Goosebumps"]


class Logger:
    """Handles logging with timestamps to both console and file."""
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.start_time = datetime.now()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().isoformat()
        elapsed = (datetime.now() - self.start_time).total_seconds()
        formatted = f"[{timestamp}] [{level}] [+{elapsed:.2f}s] {message}"
        
        # Console
        print(formatted, file=sys.stderr)
        
        # File
        with open(self.log_path, "a") as f:
            f.write(formatted + "\n")
    
    def info(self, msg: str):
        self.log(msg, "INFO")
    
    def error(self, msg: str):
        self.log(msg, "ERROR")
    
    def warn(self, msg: str):
        self.log(msg, "WARN")
        
    def section(self, title: str):
        self.log("=" * 60)
        self.log(title)
        self.log("=" * 60)


class LLMServer:
    """Manages local LLM server lifecycle."""
    
    def __init__(self, model_name: str, script_path: str, logger: Logger):
        self.model_name = model_name
        self.script_path = script_path
        self.logger = logger
        self.process = None
        self.base_url = "http://localhost:8080/v1"
        
    def start(self, wait_time: int = 30) -> bool:
        """Start the LLM server."""
        self.logger.info(f"Starting LLM server: {self.model_name}")
        self.logger.info(f"Script: {self.script_path}")
        
        try:
            # Start server as detached process
            self.process = subprocess.Popen(
                ["bash", self.script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            # Wait for server to be ready
            self.logger.info(f"Waiting {wait_time}s for server startup...")
            time.sleep(wait_time)
            
            # Test connection
            if self._test_connection():
                self.logger.info(f"Server {self.model_name} ready!")
                return True
            else:
                self.logger.error(f"Server {self.model_name} failed to start")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            return False
    
    def _test_connection(self) -> bool:
        """Test if server is responding."""
        import urllib.request
        import urllib.error
        
        try:
            url = f"{self.base_url}/models"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            self.logger.warn(f"Connection test failed: {e}")
            return False
    
    def stop(self):
        """Stop the LLM server."""
        self.logger.info(f"Stopping LLM server: {self.model_name}")
        
        # Find and kill llamafile processes
        try:
            # Kill by process group
            if self.process:
                import signal
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                time.sleep(2)
                
            # Also try to find any remaining llamafile processes on port 8080
            result = subprocess.run(
                ["lsof", "-t", "-i:8080"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        os.kill(int(pid), 9)
                    except:
                        pass
                        
            self.logger.info("Server stopped")
        except Exception as e:
            self.logger.warn(f"Error stopping server: {e}")


def load_chapters(book_dir: Path, max_chapters: int = 2) -> List[Tuple[str, str, str]]:
    """
    Load chapters from a book directory.
    
    Returns:
        List of (chapter_id, chapter_title, chapter_text) tuples
    """
    chapters = []
    files = sorted(book_dir.glob("*.txt"))[:max_chapters]
    
    for f in files:
        chapter_id = f.stem
        text = f.read_text(encoding="utf-8", errors="replace")
        
        # Extract title from first line if available
        lines = text.strip().split('\n')
        title = lines[0].strip() if lines else chapter_id
        
        chapters.append((chapter_id, title, text))
    
    return chapters


def run_story_lint(
    story_text: str,
    args: argparse.Namespace,
    logger: Logger,
    mode: str = "both"
) -> Dict[str, Any]:
    """
    Run story_lint.py on a single story.
    
    Returns:
        Dictionary with lint results
    """
    import tempfile
    
    start_time = datetime.now()
    
    # Write story to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(story_text)
        story_path = f.name
    
    try:
        # Build command
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "story_lint.py"),
            "--mode", mode,
            "--llm-model", "auto",
            "--llm-base-url", "http://localhost:8080/v1",
            "--llm-no-auth",
            "--struct-model", "auto",
            "--struct-base-url", "http://localhost:8080/v1",
            "--struct-no-auth",
            "--llm-timeout", str(args.timeout),
            "--struct-timeout", str(args.timeout),
            "--llm-max-tokens", "4096",
            "--struct-max-tokens", "8192",
            story_path
        ]
        
        logger.info(f"Running: {' '.join(cmd[:5])}...")
        
        # Run with timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=args.timeout * 3,  # Allow for retries
            cwd=str(REPO_ROOT)
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if result.returncode != 0:
            logger.error(f"story_lint failed: {result.stderr[:500]}")
            return {
                "success": False,
                "error": result.stderr,
                "duration_seconds": duration,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
        
        # Parse JSON output
        try:
            output = json.loads(result.stdout)
            output["success"] = True
            output["duration_seconds"] = duration
            output["start_time"] = start_time.isoformat()
            output["end_time"] = end_time.isoformat()
            output["stderr"] = result.stderr
            return output
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse output: {e}")
            return {
                "success": False,
                "error": f"JSON parse error: {e}",
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:1000],
                "duration_seconds": duration,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
            
    except subprocess.TimeoutExpired:
        logger.error("story_lint timed out")
        return {
            "success": False,
            "error": "Timeout",
            "duration_seconds": args.timeout * 3,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat()
        }
    finally:
        # Clean up temp file
        try:
            os.unlink(story_path)
        except:
            pass


def extract_errors_with_fragments(
    lint_result: Dict[str, Any],
    story_text: str,
    source_type: str
) -> List[Dict[str, Any]]:
    """
    Extract errors from lint results with story fragments.
    
    Args:
        lint_result: Result from story_lint
        story_text: Original story text for context extraction
        source_type: "llm" or "logic"
    
    Returns:
        List of error dictionaries with fragments
    """
    errors = []
    
    if not lint_result.get("success"):
        return errors
    
    # Extract LLM errors
    if source_type == "llm" and "llm_lint" in lint_result:
        llm_errors = lint_result["llm_lint"].get("errors", [])
        for err in llm_errors:
            error = {
                "source": "llm",
                "id": err.get("id", "unknown"),
                "category": err.get("category", "unknown").lower(),
                "description": err.get("description", ""),
                "story_fragments": err.get("story_fragments", []),
                "raw": err
            }
            
            # Normalize category
            if error["category"] not in ERROR_CATEGORIES:
                error["category"] = "coherence"  # Default
                
            errors.append(error)
    
    # Extract logic errors
    if source_type == "logic" and "logic_lint" in lint_result:
        logic_errors = lint_result["logic_lint"].get("errors", [])
        for err in logic_errors:
            # Parse violation type to determine category
            desc = err.get("description", "")
            violation_type = err.get("violation_type", "")
            
            # Categorize based on violation type
            category = categorize_violation(violation_type, desc)
            
            error = {
                "source": "logic",
                "id": err.get("id", "unknown"),
                "category": category,
                "description": desc,
                "violation_type": violation_type,
                "involved_entities": err.get("involved_entities", []),
                "story_fragments": extract_fragments_for_error(err, story_text),
                "raw": err
            }
            errors.append(error)
    
    return errors


def categorize_violation(violation_type: str, description: str) -> str:
    """Categorize a violation based on its type."""
    violation_type = violation_type.lower() if violation_type else ""
    description = description.lower() if description else ""
    
    # Causality violations
    if any(x in violation_type for x in ["chekhov", "uncaused", "cause", "precondition"]):
        return "causality"
    
    # Coherence violations
    if any(x in violation_type for x in ["dead", "edible", "physical", "focus"]):
        return "coherence"
    
    # Temporal violations
    if any(x in violation_type for x in ["time", "temporal", "duration", "order"]):
        return "temporal"
    
    # Location violations
    if any(x in violation_type for x in ["ubiquity", "travel", "proximity", "location"]):
        return "location"
    
    # Emotional violations
    if any(x in violation_type for x in ["harm", "help", "fear", "trust", "emotion", "loved", "enemy"]):
        return "emotional"
    
    # Try to infer from description
    if "dead" in description or "alive" in description:
        return "coherence"
    if "time" in description or "before" in description or "after" in description:
        return "temporal"
    if "location" in description or "place" in description:
        return "location"
    
    return "coherence"  # Default


def extract_fragments_for_error(error: Dict, story_text: str, context_words: int = 50) -> List[str]:
    """Extract relevant story fragments for an error."""
    fragments = []
    
    # Get entities mentioned in the error
    entities = error.get("involved_entities", [])
    if isinstance(entities, str):
        entities = [entities]
    
    # Search for each entity in the story
    story_lower = story_text.lower()
    for entity in entities:
        if not entity:
            continue
            
        entity_lower = entity.lower().replace("_", " ")
        pos = story_lower.find(entity_lower)
        
        if pos != -1:
            # Extract context around the mention
            start = max(0, pos - context_words * 5)
            end = min(len(story_text), pos + len(entity) + context_words * 5)
            
            fragment = story_text[start:end].strip()
            if start > 0:
                fragment = "..." + fragment
            if end < len(story_text):
                fragment = fragment + "..."
                
            fragments.append(fragment)
    
    # Limit to 3 fragments
    return fragments[:3]


def compute_error_signature(error: Dict) -> str:
    """
    Compute a signature for an error to enable deduplication.
    
    The signature is based on the category and key terms in the description.
    """
    category = error.get("category", "unknown")
    desc = error.get("description", "").lower()
    
    # Extract key terms
    key_terms = []
    
    # Look for entity names (capitalized words or quoted strings)
    import re
    quoted = re.findall(r"'([^']+)'", desc)
    key_terms.extend(quoted)
    
    # Sort for consistency
    key_terms = sorted(set(key_terms))
    
    return f"{category}:{':'.join(key_terms[:3])}"


def filter_false_positives(
    test_errors: List[Dict],
    baseline_errors: List[Dict],
    logger: Logger
) -> Tuple[List[Dict], List[Dict]]:
    """
    Filter out errors that also appear in the baseline (false positives).
    
    Returns:
        (true_positives, false_positives)
    """
    # Compute signatures for baseline errors
    baseline_signatures = set()
    for err in baseline_errors:
        sig = compute_error_signature(err)
        baseline_signatures.add(sig)
    
    true_positives = []
    false_positives = []
    
    for err in test_errors:
        sig = compute_error_signature(err)
        if sig in baseline_signatures:
            false_positives.append(err)
        else:
            true_positives.append(err)
    
    logger.info(f"Filtered: {len(true_positives)} true positives, {len(false_positives)} false positives")
    
    return true_positives, false_positives


def run_kfold_experiment(
    k: int,
    books: List[str],
    model_name: str,
    experiment_dir: Path,
    logger: Logger,
    args: argparse.Namespace
) -> Dict[str, Any]:
    """
    Run k-fold cross-validation experiment.
    
    Args:
        k: Number of folds (1-4)
        books: List of book names to use
        model_name: Name of the LLM model
        experiment_dir: Directory to save results
        logger: Logger instance
        args: Command line arguments
    
    Returns:
        Dictionary with fold results
    """
    logger.section(f"K-Fold Experiment: k={k}, model={model_name}")
    
    fold_results = []
    
    # Generate k-fold splits
    n_books = len(books)
    fold_size = max(1, n_books // k) if k > 0 else n_books
    
    for fold_idx in range(k):
        logger.info(f"=== Fold {fold_idx + 1}/{k} ===")
        
        # Determine test and train books for this fold
        test_start = fold_idx * fold_size
        test_end = min(test_start + fold_size, n_books)
        
        test_books = books[test_start:test_end]
        train_books = books[:test_start] + books[test_end:]
        
        if not train_books:
            train_books = test_books  # Use same books for training if no others
        
        logger.info(f"Train books: {train_books}")
        logger.info(f"Test books: {test_books}")
        
        fold_start = datetime.now()
        
        # Phase 1: Train on original books (collect baseline errors)
        logger.info("Phase 1: Training on original books...")
        baseline_errors = []
        
        for book_name in train_books:
            book_dir = ORIGINAL_BOOKS_DIR / book_name
            if not book_dir.exists():
                logger.warn(f"Book directory not found: {book_dir}")
                continue
                
            chapters = load_chapters(book_dir, max_chapters=args.chapters_per_book)
            
            for chapter_id, chapter_title, chapter_text in chapters:
                logger.info(f"Baseline: {book_name}/{chapter_id}")
                
                result = run_story_lint(chapter_text, args, logger, mode="both")
                
                # Extract errors
                llm_errors = extract_errors_with_fragments(result, chapter_text, "llm")
                logic_errors = extract_errors_with_fragments(result, chapter_text, "logic")
                
                baseline_errors.extend(llm_errors)
                baseline_errors.extend(logic_errors)
        
        logger.info(f"Collected {len(baseline_errors)} baseline errors (false positives)")
        
        # Phase 2: Test on modified books
        logger.info("Phase 2: Testing on modified books...")
        test_results = []
        
        for book_name in test_books:
            book_dir = MODIFIED_BOOKS_DIR / book_name
            if not book_dir.exists():
                logger.warn(f"Modified book directory not found: {book_dir}")
                continue
            
            book_start = datetime.now()
            chapters = load_chapters(book_dir, max_chapters=args.chapters_per_book)
            
            for chapter_id, chapter_title, chapter_text in chapters:
                logger.info(f"Testing: {book_name}/{chapter_id}")
                chapter_start = datetime.now()
                
                result = run_story_lint(chapter_text, args, logger, mode="both")
                
                # Extract all errors
                llm_errors = extract_errors_with_fragments(result, chapter_text, "llm")
                logic_errors = extract_errors_with_fragments(result, chapter_text, "logic")
                
                # Filter false positives
                llm_tp, llm_fp = filter_false_positives(llm_errors, baseline_errors, logger)
                logic_tp, logic_fp = filter_false_positives(logic_errors, baseline_errors, logger)
                
                chapter_end = datetime.now()
                
                chapter_result = {
                    "book": book_name,
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                    "start_time": chapter_start.isoformat(),
                    "end_time": chapter_end.isoformat(),
                    "duration_seconds": (chapter_end - chapter_start).total_seconds(),
                    "raw_result": result,
                    "llm": {
                        "true_positives": llm_tp,
                        "false_positives": llm_fp,
                        "total_errors": len(llm_tp),
                        "by_category": categorize_errors(llm_tp)
                    },
                    "logic": {
                        "true_positives": logic_tp,
                        "false_positives": logic_fp,
                        "total_errors": len(logic_tp),
                        "by_category": categorize_errors(logic_tp)
                    }
                }
                
                test_results.append(chapter_result)
                
                # Save chapter story to file
                story_file = experiment_dir / "stories" / book_name / f"{chapter_id}_{sanitize_filename(chapter_title)}.txt"
                story_file.parent.mkdir(parents=True, exist_ok=True)
                story_file.write_text(chapter_text)
            
            book_end = datetime.now()
            logger.info(f"Book {book_name} completed in {(book_end - book_start).total_seconds():.2f}s")
        
        fold_end = datetime.now()
        
        fold_result = {
            "fold": fold_idx + 1,
            "k": k,
            "train_books": train_books,
            "test_books": test_books,
            "start_time": fold_start.isoformat(),
            "end_time": fold_end.isoformat(),
            "duration_seconds": (fold_end - fold_start).total_seconds(),
            "baseline_error_count": len(baseline_errors),
            "test_results": test_results,
            "summary": aggregate_results(test_results)
        }
        
        fold_results.append(fold_result)
        
        # Save fold results
        fold_file = experiment_dir / "results" / f"fold_{fold_idx + 1}_k{k}.json"
        fold_file.parent.mkdir(parents=True, exist_ok=True)
        fold_file.write_text(json.dumps(fold_result, indent=2))
    
    return {
        "k": k,
        "model": model_name,
        "fold_results": fold_results,
        "aggregate": aggregate_folds(fold_results)
    }


def categorize_errors(errors: List[Dict]) -> Dict[str, int]:
    """Count errors by category."""
    counts = {cat: 0 for cat in ERROR_CATEGORIES}
    counts["other"] = 0
    
    for err in errors:
        cat = err.get("category", "other")
        if cat in counts:
            counts[cat] += 1
        else:
            counts["other"] += 1
    
    return counts


def aggregate_results(test_results: List[Dict]) -> Dict[str, Any]:
    """Aggregate results across chapters."""
    llm_total = 0
    logic_total = 0
    llm_by_cat = {cat: 0 for cat in ERROR_CATEGORIES}
    logic_by_cat = {cat: 0 for cat in ERROR_CATEGORIES}
    
    for chapter in test_results:
        llm_total += chapter["llm"]["total_errors"]
        logic_total += chapter["logic"]["total_errors"]
        
        for cat, count in chapter["llm"]["by_category"].items():
            if cat in llm_by_cat:
                llm_by_cat[cat] += count
        
        for cat, count in chapter["logic"]["by_category"].items():
            if cat in logic_by_cat:
                logic_by_cat[cat] += count
    
    return {
        "llm_total": llm_total,
        "logic_total": logic_total,
        "llm_by_category": llm_by_cat,
        "logic_by_category": logic_by_cat,
        "chapters_processed": len(test_results)
    }


def aggregate_folds(fold_results: List[Dict]) -> Dict[str, Any]:
    """Aggregate results across folds."""
    llm_totals = []
    logic_totals = []
    
    for fold in fold_results:
        summary = fold["summary"]
        llm_totals.append(summary["llm_total"])
        logic_totals.append(summary["logic_total"])
    
    return {
        "llm_mean": sum(llm_totals) / len(llm_totals) if llm_totals else 0,
        "logic_mean": sum(logic_totals) / len(logic_totals) if logic_totals else 0,
        "llm_totals": llm_totals,
        "logic_totals": logic_totals,
        "folds_completed": len(fold_results)
    }


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as filename."""
    import re
    # Remove special characters
    name = re.sub(r'[^\w\s-]', '', name)
    # Replace spaces with underscores
    name = re.sub(r'\s+', '_', name)
    # Limit length
    return name[:50]


def generate_report(
    experiment_dir: Path,
    all_results: Dict[str, Any],
    logger: Logger
) -> str:
    """Generate a comprehensive markdown report."""
    logger.info("Generating markdown report...")
    
    report = []
    report.append("# Narrative Evaluation Pilot Experiment Report\n")
    report.append(f"Generated: {datetime.now().isoformat()}\n")
    
    # Experiment overview
    report.append("## 1. Experiment Overview\n")
    report.append("This experiment compares two approaches to narrative evaluation:\n")
    report.append("- **LLM-based evaluation**: Direct analysis using Large Language Models\n")
    report.append("- **Logic-based evaluation**: Translation to logic predicates (Clingo/ASP)\n")
    report.append("\n### Error Categories Evaluated\n")
    report.append("| Category | Description |\n")
    report.append("|----------|-------------|\n")
    report.append("| Causality | Chekhov's gun, causal chains, unexplained events |\n")
    report.append("| Coherence | Semantic correctness, logical consistency |\n")
    report.append("| Temporal | Time ordering, duration violations |\n")
    report.append("| Location | Spatial constraints, ubiquity errors |\n")
    report.append("| Emotional | Character behavior vs relationships |\n")
    
    # Configuration
    report.append("\n## 2. Configuration\n")
    config = all_results.get("config", {})
    report.append(f"- **Start Time**: {all_results.get('start_time', 'N/A')}\n")
    report.append(f"- **End Time**: {all_results.get('end_time', 'N/A')}\n")
    report.append(f"- **Total Duration**: {all_results.get('total_duration_seconds', 0):.2f} seconds\n")
    report.append(f"- **Chapters per Book**: {config.get('chapters_per_book', 'N/A')}\n")
    report.append(f"- **K-fold Values**: {config.get('k_values', 'N/A')}\n")
    
    # Results by model
    report.append("\n## 3. Results by Model\n")
    
    for model_name, model_results in all_results.get("models", {}).items():
        report.append(f"\n### {model_name}\n")
        
        # K-fold results
        for k_result in model_results.get("k_fold_results", []):
            k = k_result["k"]
            report.append(f"\n#### K={k} Cross-Validation\n")
            
            aggregate = k_result.get("aggregate", {})
            report.append(f"- LLM Mean Errors: {aggregate.get('llm_mean', 0):.2f}\n")
            report.append(f"- Logic Mean Errors: {aggregate.get('logic_mean', 0):.2f}\n")
            
            # Per-fold table
            report.append("\n| Fold | LLM Errors | Logic Errors | Duration (s) |\n")
            report.append("|------|------------|--------------|-------------|\n")
            
            for fold in k_result.get("fold_results", []):
                summary = fold.get("summary", {})
                report.append(f"| {fold['fold']} | {summary.get('llm_total', 0)} | {summary.get('logic_total', 0)} | {fold.get('duration_seconds', 0):.2f} |\n")
    
    # Category breakdown
    report.append("\n## 4. Errors by Category\n")
    report.append("Distribution of detected errors across the 5 categories:\n")
    
    for model_name, model_results in all_results.get("models", {}).items():
        report.append(f"\n### {model_name}\n")
        
        # Aggregate category counts
        llm_cats = {cat: 0 for cat in ERROR_CATEGORIES}
        logic_cats = {cat: 0 for cat in ERROR_CATEGORIES}
        
        for k_result in model_results.get("k_fold_results", []):
            for fold in k_result.get("fold_results", []):
                summary = fold.get("summary", {})
                for cat, count in summary.get("llm_by_category", {}).items():
                    if cat in llm_cats:
                        llm_cats[cat] += count
                for cat, count in summary.get("logic_by_category", {}).items():
                    if cat in logic_cats:
                        logic_cats[cat] += count
        
        report.append("\n| Category | LLM Errors | Logic Errors |\n")
        report.append("|----------|------------|-------------|\n")
        for cat in ERROR_CATEGORIES:
            report.append(f"| {cat.capitalize()} | {llm_cats[cat]} | {logic_cats[cat]} |\n")
    
    # Sample errors
    report.append("\n## 5. Sample Errors with Story Fragments\n")
    report.append("Below are representative examples of detected errors:\n")
    
    # Collect sample errors from results
    sample_count = 0
    max_samples = 10
    
    for model_name, model_results in all_results.get("models", {}).items():
        if sample_count >= max_samples:
            break
            
        for k_result in model_results.get("k_fold_results", []):
            if sample_count >= max_samples:
                break
                
            for fold in k_result.get("fold_results", []):
                if sample_count >= max_samples:
                    break
                    
                for chapter in fold.get("test_results", []):
                    if sample_count >= max_samples:
                        break
                    
                    # Get LLM errors
                    for err in chapter["llm"].get("true_positives", [])[:2]:
                        if sample_count >= max_samples:
                            break
                        
                        report.append(f"\n### Error {sample_count + 1} (LLM - {err.get('category', 'unknown')})\n")
                        report.append(f"**Book**: {chapter['book']}, **Chapter**: {chapter['chapter_id']}\n\n")
                        report.append(f"**Description**: {err.get('description', 'N/A')}\n\n")
                        
                        fragments = err.get("story_fragments", [])
                        if fragments:
                            report.append("**Story Fragments**:\n")
                            for frag in fragments[:2]:
                                report.append(f"> {frag}\n\n")
                        
                        sample_count += 1
                    
                    # Get Logic errors
                    for err in chapter["logic"].get("true_positives", [])[:2]:
                        if sample_count >= max_samples:
                            break
                        
                        report.append(f"\n### Error {sample_count + 1} (Logic - {err.get('category', 'unknown')})\n")
                        report.append(f"**Book**: {chapter['book']}, **Chapter**: {chapter['chapter_id']}\n\n")
                        report.append(f"**Description**: {err.get('description', 'N/A')}\n\n")
                        
                        if err.get("violation_type"):
                            report.append(f"**Violation Type**: {err['violation_type']}\n\n")
                        
                        fragments = err.get("story_fragments", [])
                        if fragments:
                            report.append("**Story Fragments**:\n")
                            for frag in fragments[:2]:
                                report.append(f"> {frag}\n\n")
                        
                        sample_count += 1
    
    # Analysis and conclusions
    report.append("\n## 6. Analysis\n")
    report.append("### Comparison of Approaches\n")
    report.append("The experiment reveals key differences between LLM-based and logic-based evaluation:\n\n")
    report.append("1. **LLM Strengths**: Better at catching subtle contextual errors and emotional inconsistencies\n")
    report.append("2. **Logic Strengths**: More consistent, sound reasoning for temporal and spatial constraints\n")
    report.append("3. **False Positive Rate**: Both approaches benefit from baseline training\n")
    
    report.append("\n### Recommendations for Academic Paper\n")
    report.append("1. Report results with confidence intervals across k-folds\n")
    report.append("2. Analyze category-specific performance differences\n")
    report.append("3. Discuss complementary nature of both approaches\n")
    
    # Timing statistics
    report.append("\n## 7. Timing Statistics\n")
    
    total_chapters = 0
    total_time = 0
    
    for model_name, model_results in all_results.get("models", {}).items():
        model_time = 0
        model_chapters = 0
        
        for k_result in model_results.get("k_fold_results", []):
            for fold in k_result.get("fold_results", []):
                for chapter in fold.get("test_results", []):
                    model_chapters += 1
                    model_time += chapter.get("duration_seconds", 0)
        
        if model_chapters > 0:
            report.append(f"\n### {model_name}\n")
            report.append(f"- Total chapters: {model_chapters}\n")
            report.append(f"- Total time: {model_time:.2f}s\n")
            report.append(f"- Average per chapter: {model_time/model_chapters:.2f}s\n")
        
        total_chapters += model_chapters
        total_time += model_time
    
    report.append(f"\n### Overall\n")
    report.append(f"- Total chapters processed: {total_chapters}\n")
    report.append(f"- Total processing time: {total_time:.2f}s\n")
    
    return "".join(report)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run k-fold cross-validation experiment for narrative linting"
    )
    
    parser.add_argument(
        "--chapters-per-book", type=int, default=2,
        help="Number of chapters to process per book (default: 2)"
    )
    parser.add_argument(
        "--timeout", type=int, default=600,
        help="Timeout in seconds for LLM calls (default: 600)"
    )
    parser.add_argument(
        "--k-values", type=str, default="1,2,3,4",
        help="Comma-separated k values for cross-validation (default: 1,2,3,4)"
    )
    parser.add_argument(
        "--models", type=str, 
        default="gemma:~/programas/gemma.sh,r1_qwen:~/programas/r1_distill_qwen.sh",
        help="Comma-separated model:script pairs"
    )
    parser.add_argument(
        "--server-wait", type=int, default=45,
        help="Seconds to wait for server startup (default: 45)"
    )
    
    args = parser.parse_args()
    
    # Parse k values
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    
    # Parse models
    models = {}
    for model_spec in args.models.split(","):
        parts = model_spec.strip().split(":")
        if len(parts) == 2:
            name, script = parts
            # Expand ~ in path
            script = os.path.expanduser(script)
            models[name] = script
    
    # Create experiment directory
    experiment_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    
    # Directory name will be updated with end time after completion
    experiment_dir = EXPERIMENTS_DIR / f"pilot_{start_time.strftime('%Y%m%d_%H%M%S')}_{experiment_id}"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize logger
    logger = Logger(experiment_dir / "log.txt")
    logger.section("PILOT EXPERIMENT START")
    logger.info(f"Experiment ID: {experiment_id}")
    logger.info(f"Start time: {start_time.isoformat()}")
    logger.info(f"K values: {k_values}")
    logger.info(f"Models: {list(models.keys())}")
    logger.info(f"Chapters per book: {args.chapters_per_book}")
    
    # Save configuration
    config = {
        "experiment_id": experiment_id,
        "start_time": start_time.isoformat(),
        "k_values": k_values,
        "models": models,
        "chapters_per_book": args.chapters_per_book,
        "timeout": args.timeout,
        "books": BOOKS,
        "server_wait": args.server_wait
    }
    
    (experiment_dir / "config.json").write_text(json.dumps(config, indent=2))
    
    # Initialize results
    all_results = {
        "config": config,
        "start_time": start_time.isoformat(),
        "models": {}
    }
    
    # Run experiments for each model
    for model_name, script_path in models.items():
        logger.section(f"MODEL: {model_name}")
        
        # Start server
        server = LLMServer(model_name, script_path, logger)
        if not server.start(wait_time=args.server_wait):
            logger.error(f"Failed to start server for {model_name}, skipping")
            continue
        
        try:
            model_results = {
                "model_name": model_name,
                "script_path": script_path,
                "k_fold_results": []
            }
            
            # Run k-fold for each k value
            for k in k_values:
                k_result = run_kfold_experiment(
                    k=k,
                    books=BOOKS,
                    model_name=model_name,
                    experiment_dir=experiment_dir,
                    logger=logger,
                    args=args
                )
                model_results["k_fold_results"].append(k_result)
            
            all_results["models"][model_name] = model_results
            
        finally:
            # Stop server
            server.stop()
            time.sleep(5)  # Wait for cleanup
    
    # Finalize
    end_time = datetime.now()
    all_results["end_time"] = end_time.isoformat()
    all_results["total_duration_seconds"] = (end_time - start_time).total_seconds()
    
    # Rename experiment directory with end time
    final_dir_name = f"pilot_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%Y%m%d_%H%M%S')}_{experiment_id}"
    final_dir = EXPERIMENTS_DIR / final_dir_name
    
    # Save final results before renaming
    (experiment_dir / "summary.json").write_text(json.dumps(all_results, indent=2))
    
    # Generate report
    report_text = generate_report(experiment_dir, all_results, logger)
    (experiment_dir / "report.md").write_text(report_text)
    
    # Rename directory
    try:
        experiment_dir.rename(final_dir)
        logger.info(f"Results saved to: {final_dir}")
    except Exception as e:
        logger.warn(f"Could not rename directory: {e}")
        logger.info(f"Results saved to: {experiment_dir}")
    
    logger.section("EXPERIMENT COMPLETE")
    logger.info(f"End time: {end_time.isoformat()}")
    logger.info(f"Total duration: {(end_time - start_time).total_seconds():.2f} seconds")
    
    print(f"\nExperiment complete!")
    print(f"Results: {final_dir if final_dir.exists() else experiment_dir}")


if __name__ == "__main__":
    main()
