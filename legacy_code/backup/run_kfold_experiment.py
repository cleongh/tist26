#!/usr/bin/env python3
"""
run_kfold_experiment.py - K-Fold Cross-Validation Experiment Runner
====================================================================

This script implements the full experiment workflow:

1. BASELINE TRAINING: Run linter on original_books to collect false positives
2. TESTING: Run linter on modified_books to detect true errors
3. FILTERING: Remove false positives from test results
4. K-FOLD: Repeat with different train/test book splits (k=1,2,3,4)

The script assumes an LLM server is already running on port 8080.

Usage:
    python3 scripts/run_kfold_experiment.py --model-name "gemma"
"""

import argparse
import json
import os
import sys
import subprocess
import tempfile
import uuid
import hashlib
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Set

# =============================================================================
# PATHS AND CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
ORIGINAL_BOOKS = REPO_ROOT / "original_books"
MODIFIED_BOOKS = REPO_ROOT / "modified_books"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

BOOKS = ["Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight", "Goosebumps"]
CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]

# =============================================================================
# LOGGING
# =============================================================================

class Logger:
    """Logger with timestamps that writes to both console and file."""
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.start_time = datetime.now()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().isoformat()
        elapsed = (datetime.now() - self.start_time).total_seconds()
        formatted = f"[{timestamp}] [{level}] [+{elapsed:.1f}s] {message}"
        print(formatted, file=sys.stderr)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    
    def info(self, msg: str): self.log(msg, "INFO")
    def error(self, msg: str): self.log(msg, "ERROR")
    def warn(self, msg: str): self.log(msg, "WARN")
    
    def section(self, title: str):
        sep = "=" * 70
        self.log(sep)
        self.log(title)
        self.log(sep)

# =============================================================================
# SERVER CHECK
# =============================================================================

def check_server(base_url: str, timeout: int = 10) -> Tuple[bool, str]:
    """Check if LLM server is responding."""
    try:
        url = f"{base_url}/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            if models:
                return True, models[0].get("id", "unknown")
            return True, "unknown"
    except Exception as e:
        return False, str(e)

# =============================================================================
# CHAPTER LOADING
# =============================================================================

def load_chapters(book_dir: Path, max_chapters: int = 2) -> List[Dict]:
    """Load chapters from a book directory."""
    chapters = []
    if not book_dir.exists():
        return chapters
    
    files = sorted(book_dir.glob("*.txt"))[:max_chapters]
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            lines = text.strip().split('\n')
            title = lines[0].strip()[:100] if lines else f.stem
            chapters.append({
                "id": f.stem,
                "title": title,
                "text": text,
                "path": str(f),
                "filename": f.name
            })
        except Exception as e:
            print(f"Warning: Could not read {f}: {e}", file=sys.stderr)
    
    return chapters

# =============================================================================
# STORY LINTING
# =============================================================================

def run_story_lint(
    story_text: str,
    base_url: str,
    timeout: int = 600,
    mode: str = "both"
) -> Dict[str, Any]:
    """
    Run story_lint.py on story text and return parsed results.
    
    Returns dict with:
        - success: bool
        - llm_lint: dict with error_count and errors list
        - logic_lint: dict with error_count and errors list
        - duration_seconds: float
        - stderr: captured stderr for debugging
    """
    start_time = datetime.now()
    
    fd, story_path = tempfile.mkstemp(suffix='.txt', prefix='story_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(story_text)
        
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "story_lint.py"),
            "--mode", mode,
            "--llm-model", "auto",
            "--llm-base-url", base_url,
            "--llm-no-auth",
            "--struct-model", "auto",
            "--struct-base-url", base_url,
            "--struct-no-auth",
            "--llm-timeout", str(timeout),
            "--struct-timeout", str(timeout),
            "--llm-max-tokens", "4096",
            "--struct-max-tokens", "8192",
            story_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * 3,
            cwd=str(REPO_ROOT)
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Always try to parse stdout as JSON, regardless of return code
        # story_lint.py may return 0 even with partial failures
        output = None
        try:
            if result.stdout.strip():
                output = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
        
        if output is None:
            output = {}
        
        # Ensure structure exists
        if "llm_lint" not in output:
            output["llm_lint"] = {"error_count": 0, "errors": []}
        if "logic_lint" not in output:
            output["logic_lint"] = {"error_count": 0, "errors": []}
        
        # Determine success: we have at least some errors OR no parsing errors occurred
        has_llm_errors = output["llm_lint"].get("error_count", 0) > 0
        has_logic_errors = output["logic_lint"].get("error_count", 0) > 0
        
        output["success"] = result.returncode == 0 or has_llm_errors or has_logic_errors
        output["duration_seconds"] = duration
        output["stderr"] = result.stderr[:3000] if result.stderr else ""
        output["returncode"] = result.returncode
        
        return output
            
    except subprocess.TimeoutExpired:
        return {
            "success": False, 
            "error": "Timeout", 
            "duration_seconds": timeout * 3,
            "llm_lint": {"error_count": 0, "errors": []},
            "logic_lint": {"error_count": 0, "errors": []}
        }
    except Exception as e:
        return {
            "success": False, 
            "error": str(e), 
            "duration_seconds": 0,
            "llm_lint": {"error_count": 0, "errors": []},
            "logic_lint": {"error_count": 0, "errors": []}
        }
    finally:
        try:
            os.unlink(story_path)
        except:
            pass

# =============================================================================
# ERROR EXTRACTION AND NORMALIZATION
# =============================================================================

def extract_errors(lint_result: Dict, source: str, story_text: str, book: str, chapter_id: str) -> List[Dict]:
    """
    Extract and normalize errors from lint result.
    
    The lint result has structure:
    {
        "llm_lint": {"error_count": N, "errors": [...]},
        "logic_lint": {"error_count": N, "errors": [...]}
    }
    """
    errors = []
    
    # Get the correct nested structure
    key = f"{source}_lint"
    if key not in lint_result:
        return errors
    
    lint_data = lint_result[key]
    if not isinstance(lint_data, dict):
        return errors
    
    error_list = lint_data.get("errors", [])
    if not isinstance(error_list, list):
        return errors
    
    for idx, err in enumerate(error_list):
        if not isinstance(err, dict):
            continue
            
        # Normalize category
        category = str(err.get("category", "coherence")).lower()
        if category not in CATEGORIES:
            category = "coherence"
        
        # Get description
        description = err.get("description", "")
        if not description:
            description = err.get("id", f"Error {idx}")
        
        # Extract story fragments
        fragments = err.get("story_fragments", [])
        if not fragments:
            fragments = extract_fragments_from_description(description, story_text)
        
        errors.append({
            "source": source,
            "id": err.get("id", f"{source}_{idx}"),
            "category": category,
            "description": description,
            "story_fragments": fragments,
            "violation_type": err.get("violation_type", ""),
            "involved_entities": err.get("involved_entities", []),
            "book": book,
            "chapter_id": chapter_id,
            "raw": err
        })
    
    return errors


def extract_fragments_from_description(description: str, story_text: str, context_chars: int = 150) -> List[str]:
    """Extract story fragments mentioned in error description."""
    import re
    fragments = []
    
    # Find quoted strings in description
    quoted = re.findall(r"'([^']+)'", description)
    quoted.extend(re.findall(r'"([^"]+)"', description))
    
    story_lower = story_text.lower()
    for term in quoted[:3]:
        if len(term) < 3:
            continue
        pos = story_lower.find(term.lower())
        if pos != -1:
            start = max(0, pos - context_chars)
            end = min(len(story_text), pos + len(term) + context_chars)
            fragment = story_text[start:end].strip()
            if start > 0:
                fragment = "..." + fragment
            if end < len(story_text):
                fragment = fragment + "..."
            fragments.append(fragment)
    
    return fragments[:2]


def compute_error_signature(error: Dict) -> str:
    """
    Compute a signature for error deduplication.
    Used to identify the same type of error across different runs.
    """
    category = error.get("category", "unknown")
    desc = error.get("description", "")[:200].lower()
    # Create a hash of the key parts
    content = f"{category}:{desc}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def categorize_errors(errors: List[Dict]) -> Dict[str, int]:
    """Count errors by category."""
    counts = {cat: 0 for cat in CATEGORIES}
    for err in errors:
        cat = err.get("category", "coherence")
        if cat in counts:
            counts[cat] += 1
    return counts

# =============================================================================
# K-FOLD CROSS VALIDATION
# =============================================================================

def run_kfold_experiment(
    k: int,
    books: List[str],
    base_url: str,
    chapters_per_book: int,
    timeout: int,
    experiment_dir: Path,
    logger: Logger
) -> Dict[str, Any]:
    """
    Run k-fold cross-validation experiment.
    
    For each fold:
    1. Split books into train (for baseline) and test sets
    2. Run linter on train books (original) to collect false positive signatures
    3. Run linter on test books (modified) to detect errors
    4. Filter out false positives from test results
    """
    
    logger.section(f"K-FOLD CROSS-VALIDATION: k={k}")
    
    fold_results = []
    n_books = len(books)
    fold_size = max(1, n_books // k) if k > 0 else n_books
    
    for fold_idx in range(k):
        logger.info(f"=== FOLD {fold_idx + 1}/{k} ===")
        fold_start = datetime.now()
        
        # Split books: test set is fold_idx portion, train is everything else
        test_start = fold_idx * fold_size
        test_end = min(test_start + fold_size, n_books)
        test_books = books[test_start:test_end]
        train_books = books[:test_start] + books[test_end:]
        
        # Edge case: if no train books, use all for training (leave-one-out style)
        if not train_books:
            train_books = [b for b in books if b not in test_books]
            if not train_books:
                train_books = test_books  # Fallback
        
        logger.info(f"Train books (for baseline): {train_books}")
        logger.info(f"Test books (for evaluation): {test_books}")
        
        # ============================================
        # PHASE 1: BASELINE - Collect false positives
        # ============================================
        logger.info("PHASE 1: Collecting baseline from ORIGINAL books...")
        baseline_errors_llm = []
        baseline_errors_logic = []
        baseline_results = []
        
        for book_name in train_books:
            book_dir = ORIGINAL_BOOKS / book_name
            chapters = load_chapters(book_dir, chapters_per_book)
            
            for chapter in chapters:
                logger.info(f"  Baseline: {book_name}/{chapter['id']}")
                
                result = run_story_lint(chapter["text"], base_url, timeout)
                
                # Log raw counts from story_lint output
                llm_raw = result.get("llm_lint", {}).get("error_count", 0)
                logic_raw = result.get("logic_lint", {}).get("error_count", 0)
                logger.info(f"    Raw counts: LLM={llm_raw}, Logic={logic_raw}, success={result.get('success')}")
                
                # If there's stderr, log first 200 chars for debugging
                if result.get("stderr"):
                    stderr_preview = result["stderr"][:200].replace('\n', ' ')
                    logger.info(f"    stderr preview: {stderr_preview}")
                
                # Extract errors from ORIGINAL (these are false positives)
                llm_errs = extract_errors(result, "llm", chapter["text"], book_name, chapter["id"])
                logic_errs = extract_errors(result, "logic", chapter["text"], book_name, chapter["id"])
                
                baseline_errors_llm.extend(llm_errs)
                baseline_errors_logic.extend(logic_errs)
                
                baseline_results.append({
                    "book": book_name,
                    "chapter": chapter["id"],
                    "llm_error_count": len(llm_errs),
                    "logic_error_count": len(logic_errs),
                    "llm_raw_count": llm_raw,
                    "logic_raw_count": logic_raw,
                    "duration": result.get("duration_seconds", 0),
                    "success": result.get("success", False)
                })
                
                logger.info(f"    Extracted {len(llm_errs)} LLM, {len(logic_errs)} logic false positives")
        
        # Compute baseline signatures (these represent false positive patterns)
        baseline_sigs_llm = set(compute_error_signature(e) for e in baseline_errors_llm)
        baseline_sigs_logic = set(compute_error_signature(e) for e in baseline_errors_logic)
        
        logger.info(f"Baseline complete: {len(baseline_sigs_llm)} LLM sigs, {len(baseline_sigs_logic)} logic sigs")
        
        # ============================================
        # PHASE 2: TEST - Detect errors in modified
        # ============================================
        logger.info("PHASE 2: Testing on MODIFIED books...")
        test_results = []
        
        for book_name in test_books:
            book_dir = MODIFIED_BOOKS / book_name
            chapters = load_chapters(book_dir, chapters_per_book)
            
            if not chapters:
                logger.warn(f"  No chapters found for {book_name}")
                continue
            
            for chapter in chapters:
                logger.info(f"  Testing: {book_name}/{chapter['id']}")
                ch_start = datetime.now()
                
                result = run_story_lint(chapter["text"], base_url, timeout)
                
                # Log raw counts from story_lint output
                llm_raw = result.get("llm_lint", {}).get("error_count", 0)
                logic_raw = result.get("logic_lint", {}).get("error_count", 0)
                logger.info(f"    Raw counts: LLM={llm_raw}, Logic={logic_raw}, success={result.get('success')}")
                
                # If there's stderr, log first 200 chars for debugging
                if result.get("stderr"):
                    stderr_preview = result["stderr"][:200].replace('\n', ' ')
                    logger.info(f"    stderr preview: {stderr_preview}")
                
                # Extract ALL errors from modified books
                llm_errs = extract_errors(result, "llm", chapter["text"], book_name, chapter["id"])
                logic_errs = extract_errors(result, "logic", chapter["text"], book_name, chapter["id"])
                
                logger.info(f"    Extracted: LLM={len(llm_errs)}, Logic={len(logic_errs)}")
                
                # Filter: true positives are errors NOT in baseline
                llm_tp = [e for e in llm_errs if compute_error_signature(e) not in baseline_sigs_llm]
                llm_fp = [e for e in llm_errs if compute_error_signature(e) in baseline_sigs_llm]
                logic_tp = [e for e in logic_errs if compute_error_signature(e) not in baseline_sigs_logic]
                logic_fp = [e for e in logic_errs if compute_error_signature(e) in baseline_sigs_logic]
                
                ch_end = datetime.now()
                
                chapter_result = {
                    "book": book_name,
                    "chapter_id": chapter["id"],
                    "chapter_title": chapter["title"],
                    "chapter_filename": chapter["filename"],
                    "start_time": ch_start.isoformat(),
                    "end_time": ch_end.isoformat(),
                    "duration_seconds": (ch_end - ch_start).total_seconds(),
                    "success": result.get("success", False),
                    "llm": {
                        "raw_count": llm_raw,
                        "total_detected": len(llm_errs),
                        "true_positives": llm_tp,
                        "false_positives_filtered": len(llm_fp),
                        "true_positive_count": len(llm_tp),
                        "by_category": categorize_errors(llm_tp)
                    },
                    "logic": {
                        "raw_count": logic_raw,
                        "total_detected": len(logic_errs),
                        "true_positives": logic_tp,
                        "false_positives_filtered": len(logic_fp),
                        "true_positive_count": len(logic_tp),
                        "by_category": categorize_errors(logic_tp)
                    },
                    "raw_result": result
                }
                
                test_results.append(chapter_result)
                
                logger.info(f"    Final: LLM {len(llm_tp)} TP ({len(llm_fp)} filtered), Logic {len(logic_tp)} TP ({len(logic_fp)} filtered)")
                
                # Save chapter text for reference
                story_dir = experiment_dir / "stories" / book_name
                story_dir.mkdir(parents=True, exist_ok=True)
                (story_dir / f"{chapter['id']}.txt").write_text(chapter["text"], encoding="utf-8")
        
        fold_end = datetime.now()
        
        # Aggregate fold results
        fold_llm_tp = sum(r["llm"]["true_positive_count"] for r in test_results)
        fold_logic_tp = sum(r["logic"]["true_positive_count"] for r in test_results)
        
        fold_result = {
            "fold": fold_idx + 1,
            "k": k,
            "train_books": train_books,
            "test_books": test_books,
            "start_time": fold_start.isoformat(),
            "end_time": fold_end.isoformat(),
            "duration_seconds": (fold_end - fold_start).total_seconds(),
            "baseline": {
                "llm_false_positive_signatures": len(baseline_sigs_llm),
                "logic_false_positive_signatures": len(baseline_sigs_logic),
                "results": baseline_results
            },
            "test": {
                "llm_true_positives": fold_llm_tp,
                "logic_true_positives": fold_logic_tp,
                "results": test_results
            }
        }
        
        fold_results.append(fold_result)
        logger.info(f"Fold {fold_idx + 1} complete: LLM TP={fold_llm_tp}, Logic TP={fold_logic_tp}")
        
        # Save fold results
        fold_file = experiment_dir / "results" / f"fold_{fold_idx + 1}_k{k}.json"
        fold_file.parent.mkdir(parents=True, exist_ok=True)
        fold_file.write_text(json.dumps(fold_result, indent=2, default=str), encoding="utf-8")
    
    # Aggregate across folds
    llm_totals = [f["test"]["llm_true_positives"] for f in fold_results]
    logic_totals = [f["test"]["logic_true_positives"] for f in fold_results]
    
    return {
        "k": k,
        "fold_results": fold_results,
        "aggregate": {
            "llm_mean": sum(llm_totals) / len(llm_totals) if llm_totals else 0,
            "llm_total": sum(llm_totals),
            "logic_mean": sum(logic_totals) / len(logic_totals) if logic_totals else 0,
            "logic_total": sum(logic_totals),
            "folds_completed": len(fold_results)
        }
    }

# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report(experiment_dir: Path, results: Dict, logger: Logger) -> str:
    """Generate comprehensive markdown report."""
    
    logger.info("Generating markdown report...")
    
    r = []
    r.append("# Narrative Evaluation Experiment Report\n")
    r.append(f"**Generated:** {datetime.now().isoformat()}\n")
    r.append(f"**Model:** {results.get('model_name', 'Unknown')}\n")
    r.append(f"**Server Model:** {results.get('server_model', 'Unknown')}\n")
    r.append(f"**Start:** {results.get('start_time', 'N/A')}\n")
    r.append(f"**End:** {results.get('end_time', 'N/A')}\n")
    r.append(f"**Duration:** {results.get('total_duration_seconds', 0):.2f} seconds\n")
    
    # Methodology
    r.append("\n## 1. Methodology\n")
    r.append("This experiment compares two approaches to narrative evaluation:\n")
    r.append("- **LLM-based**: Direct analysis using Large Language Models\n")
    r.append("- **Logic-based**: Translation to ASP (Clingo) for formal reasoning\n\n")
    
    r.append("### Baseline Training (False Positive Detection)\n")
    r.append("The linter is first run on **original books** (without intentional errors).\n")
    r.append("Any errors detected are considered false positives and their signatures are recorded.\n")
    r.append("When testing on **modified books**, errors matching these signatures are filtered out.\n\n")
    
    r.append("### K-Fold Cross-Validation\n")
    r.append("Books are split into train/test sets for each fold:\n")
    r.append("- Train set: Used for baseline (original books)\n")
    r.append("- Test set: Evaluated for true errors (modified books)\n")
    
    # Error Categories
    r.append("\n## 2. Error Categories\n")
    r.append("| Category | Description |\n")
    r.append("|----------|-------------|\n")
    r.append("| Causality | Chekhov's gun, causal chains, unexplained events |\n")
    r.append("| Coherence | Semantic correctness, logical consistency |\n")
    r.append("| Temporal | Time ordering, duration violations |\n")
    r.append("| Location | Spatial constraints, proximity errors |\n")
    r.append("| Emotional | Character behavior vs relationships |\n")
    
    # Configuration
    config = results.get("config", {})
    r.append("\n## 3. Configuration\n")
    r.append(f"- **Chapters per Book:** {config.get('chapters_per_book', 'N/A')}\n")
    r.append(f"- **K values tested:** {config.get('k_values', 'N/A')}\n")
    r.append(f"- **Books:** {', '.join(config.get('books', BOOKS))}\n")
    r.append(f"- **Timeout:** {config.get('timeout', 'N/A')} seconds\n")
    
    # K-fold results summary
    r.append("\n## 4. K-Fold Results Summary\n")
    
    for k_result in results.get("k_fold_results", []):
        k = k_result["k"]
        agg = k_result.get("aggregate", {})
        
        r.append(f"\n### K={k}\n")
        r.append(f"- **LLM True Positives (Total):** {agg.get('llm_total', 0)}\n")
        r.append(f"- **LLM True Positives (Mean per fold):** {agg.get('llm_mean', 0):.2f}\n")
        r.append(f"- **Logic True Positives (Total):** {agg.get('logic_total', 0)}\n")
        r.append(f"- **Logic True Positives (Mean per fold):** {agg.get('logic_mean', 0):.2f}\n")
        
        r.append("\n| Fold | Train Books | Test Books | Baseline FP | LLM TP | Logic TP | Duration |\n")
        r.append("|------|-------------|------------|-------------|--------|----------|----------|\n")
        
        for fold in k_result.get("fold_results", []):
            train = ", ".join(b[:12] for b in fold.get("train_books", []))
            test = ", ".join(b[:12] for b in fold.get("test_books", []))
            baseline_fp = fold["baseline"]["llm_false_positive_signatures"] + fold["baseline"]["logic_false_positive_signatures"]
            llm_tp = fold["test"]["llm_true_positives"]
            logic_tp = fold["test"]["logic_true_positives"]
            duration = fold["duration_seconds"]
            r.append(f"| {fold['fold']} | {train} | {test} | {baseline_fp} | {llm_tp} | {logic_tp} | {duration:.1f}s |\n")
    
    # Category breakdown
    r.append("\n## 5. Errors by Category (All Folds Combined)\n")
    
    llm_cats = {cat: 0 for cat in CATEGORIES}
    logic_cats = {cat: 0 for cat in CATEGORIES}
    
    for k_result in results.get("k_fold_results", []):
        for fold in k_result.get("fold_results", []):
            for test in fold.get("test", {}).get("results", []):
                for cat in CATEGORIES:
                    llm_cats[cat] += test["llm"]["by_category"].get(cat, 0)
                    logic_cats[cat] += test["logic"]["by_category"].get(cat, 0)
    
    r.append("\n| Category | LLM True Positives | Logic True Positives | Total |\n")
    r.append("|----------|--------------------|--------------------|-------|\n")
    for cat in CATEGORIES:
        total = llm_cats[cat] + logic_cats[cat]
        r.append(f"| {cat.capitalize()} | {llm_cats[cat]} | {logic_cats[cat]} | {total} |\n")
    
    r.append(f"\n**Grand Total:** LLM={sum(llm_cats.values())}, Logic={sum(logic_cats.values())}\n")
    
    # Sample errors with fragments
    r.append("\n## 6. Sample Errors with Story Fragments\n")
    r.append("Below are representative errors showing the story text that triggered detection:\n")
    
    sample_count = 0
    max_samples = 20
    
    for k_result in results.get("k_fold_results", []):
        if sample_count >= max_samples:
            break
        for fold in k_result.get("fold_results", []):
            if sample_count >= max_samples:
                break
            for test in fold.get("test", {}).get("results", []):
                if sample_count >= max_samples:
                    break
                
                # LLM true positives
                for err in test["llm"].get("true_positives", [])[:2]:
                    if sample_count >= max_samples:
                        break
                    
                    r.append(f"\n### Error {sample_count + 1}: {err['category'].upper()} (LLM)\n")
                    r.append(f"**Book:** {test['book']}\n")
                    r.append(f"**Chapter:** {test['chapter_id']} ({test.get('chapter_filename', '')})\n\n")
                    r.append(f"**Description:** {err['description']}\n\n")
                    
                    if err.get("story_fragments"):
                        r.append("**Relevant Story Fragments:**\n")
                        for frag in err["story_fragments"][:2]:
                            r.append(f"> {frag[:500]}{'...' if len(frag) > 500 else ''}\n\n")
                    
                    sample_count += 1
                
                # Logic true positives
                for err in test["logic"].get("true_positives", [])[:2]:
                    if sample_count >= max_samples:
                        break
                    
                    r.append(f"\n### Error {sample_count + 1}: {err['category'].upper()} (Logic)\n")
                    r.append(f"**Book:** {test['book']}\n")
                    r.append(f"**Chapter:** {test['chapter_id']} ({test.get('chapter_filename', '')})\n\n")
                    r.append(f"**Description:** {err['description']}\n\n")
                    
                    if err.get("violation_type"):
                        r.append(f"**Violation Type:** {err['violation_type']}\n\n")
                    
                    if err.get("story_fragments"):
                        r.append("**Relevant Story Fragments:**\n")
                        for frag in err["story_fragments"][:2]:
                            r.append(f"> {frag[:500]}{'...' if len(frag) > 500 else ''}\n\n")
                    
                    sample_count += 1
    
    # Analysis
    r.append("\n## 7. Analysis\n")
    
    r.append("\n### Comparison of Approaches\n")
    r.append("| Aspect | LLM-Based | Logic-Based |\n")
    r.append("|--------|-----------|-------------|\n")
    r.append("| Strengths | Contextual understanding, subtle errors | Formal consistency, sound reasoning |\n")
    r.append("| Weaknesses | May hallucinate, variable results | Limited to encoded rules |\n")
    r.append("| Best for | Emotional, coherence errors | Temporal, location errors |\n")
    
    total_llm = sum(llm_cats.values())
    total_logic = sum(logic_cats.values())
    
    r.append("\n### Key Findings\n")
    r.append(f"- **Total LLM true positive errors:** {total_llm}\n")
    r.append(f"- **Total Logic true positive errors:** {total_logic}\n")
    if total_llm > 0 and total_logic > 0:
        r.append(f"- **LLM/Logic ratio:** {total_llm/total_logic:.2f}\n")
    
    # Timing
    r.append("\n## 8. Timing Statistics\n")
    
    total_chapters = 0
    total_time = 0
    
    for k_result in results.get("k_fold_results", []):
        for fold in k_result.get("fold_results", []):
            for test in fold.get("test", {}).get("results", []):
                total_chapters += 1
                total_time += test.get("duration_seconds", 0)
    
    r.append(f"- **Total test chapters processed:** {total_chapters}\n")
    r.append(f"- **Total processing time:** {total_time:.2f} seconds\n")
    if total_chapters > 0:
        r.append(f"- **Average time per chapter:** {total_time/total_chapters:.2f} seconds\n")
    
    # Conclusion
    r.append("\n## 9. Conclusion\n")
    r.append("This experiment demonstrates the complementary nature of LLM-based and ")
    r.append("logic-based narrative evaluation. The baseline training on original books ")
    r.append("effectively filters false positives, allowing identification of genuine ")
    r.append("errors introduced in the modified books.\n\n")
    r.append("The k-fold cross-validation provides robust estimates of error detection ")
    r.append("performance across different book combinations.\n")
    
    r.append("\n---\n")
    r.append(f"*Report generated at {datetime.now().isoformat()}*\n")
    
    return "".join(r)

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run k-fold cross-validation narrative evaluation experiment",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--model-name", required=True, help="Model name for output directory")
    parser.add_argument("--base-url", default="http://localhost:8080/v1", help="LLM server URL")
    parser.add_argument("--chapters-per-book", type=int, default=2, help="Chapters per book")
    parser.add_argument("--k-values", default="1,2,3,4", help="Comma-separated k values")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout per call (seconds)")
    parser.add_argument("--books", default=None, help="Comma-separated book names")
    
    args = parser.parse_args()
    
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    books = [b.strip() for b in args.books.split(",")] if args.books else BOOKS
    
    # Create experiment directory
    exp_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    exp_name = f"kfold_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}"
    exp_dir = EXPERIMENTS_DIR / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize logger
    logger = Logger(exp_dir / "log.txt")
    
    logger.section("NARRATIVE EVALUATION K-FOLD EXPERIMENT")
    logger.info(f"Experiment: {exp_name}")
    logger.info(f"Output: {exp_dir}")
    logger.info(f"K values: {k_values}")
    logger.info(f"Chapters per book: {args.chapters_per_book}")
    logger.info(f"Books: {books}")
    
    # Check server
    logger.info("Checking LLM server...")
    ok, server_model = check_server(args.base_url)
    if not ok:
        logger.error(f"Server not available at {args.base_url}")
        logger.error("Please start the LLM server first.")
        sys.exit(1)
    logger.info(f"Server OK: {server_model}")
    
    # Save config
    config = {
        "experiment_id": exp_id,
        "model_name": args.model_name,
        "server_model": server_model,
        "start_time": start_time.isoformat(),
        "base_url": args.base_url,
        "k_values": k_values,
        "chapters_per_book": args.chapters_per_book,
        "timeout": args.timeout,
        "books": books
    }
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2))
    
    # Initialize results
    results = {
        "config": config,
        "model_name": args.model_name,
        "server_model": server_model,
        "start_time": start_time.isoformat(),
        "k_fold_results": []
    }
    
    # Run k-fold experiments
    for k in k_values:
        k_result = run_kfold_experiment(
            k=k,
            books=books,
            base_url=args.base_url,
            chapters_per_book=args.chapters_per_book,
            timeout=args.timeout,
            experiment_dir=exp_dir,
            logger=logger
        )
        results["k_fold_results"].append(k_result)
    
    # Finalize
    end_time = datetime.now()
    results["end_time"] = end_time.isoformat()
    results["total_duration_seconds"] = (end_time - start_time).total_seconds()
    
    # Save results
    (exp_dir / "results.json").write_text(json.dumps(results, indent=2, default=str))
    
    # Generate report
    report = generate_report(exp_dir, results, logger)
    (exp_dir / "report.md").write_text(report)
    
    # Rename with end time
    final_name = f"kfold_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
    final_dir = EXPERIMENTS_DIR / final_name
    try:
        exp_dir.rename(final_dir)
        output_dir = final_dir
    except:
        output_dir = exp_dir
    
    logger.section("EXPERIMENT COMPLETE")
    logger.info(f"Duration: {results['total_duration_seconds']:.2f} seconds")
    logger.info(f"Output: {output_dir}")
    
    # Print summary
    print(f"\n{'='*70}")
    print("EXPERIMENT COMPLETE")
    print(f"{'='*70}")
    print(f"Output: {output_dir}")
    print(f"Duration: {results['total_duration_seconds']:.2f} seconds")
    print()
    print("K-Fold Results Summary:")
    for k_result in results["k_fold_results"]:
        k = k_result["k"]
        agg = k_result["aggregate"]
        print(f"  k={k}: LLM TP={agg['llm_total']}, Logic TP={agg['logic_total']}")
    print()
    print("Files:")
    print("  - results.json (complete data)")
    print("  - report.md (markdown report)")
    print("  - log.txt (execution log)")
    print("  - results/ (per-fold JSON files)")
    print("  - stories/ (chapter texts)")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
