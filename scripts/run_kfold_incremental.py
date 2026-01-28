#!/usr/bin/env python3
"""
run_kfold_incremental.py - K-Fold Cross-Validation for Incremental Mode
========================================================================

This script implements the experiment workflow for the INCREMENTAL mode:

1. BASELINE TRAINING: Run incremental linter on original_books to collect false positives
2. TESTING: Run incremental linter on modified_books to detect true errors
3. FILTERING: Remove false positives from test results
4. K-FOLD: Repeat with different train/test book splits (k=1,2,3,4)

This version compares TWO approaches per story:
- LLM Direct: Ask LLM to find inconsistencies in each chapter directly
- ILASP Incremental: Learn rules chapter-by-chapter, check later chapters

The script assumes an LLM server is already running on port 8080.

Usage:
    python3 scripts/run_kfold_incremental.py --model-name "gemma"
    
    # With specific local model
    python3 scripts/run_kfold_incremental.py --model-name "gemma" --local-llm gemma-3-12b
"""

import argparse
import json
import os
import sys
import subprocess
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
CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional", 
              "dead_agent", "ubiquity", "temporal_anomaly", "contradiction", "unknown"]

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
# INCREMENTAL STORY LINTING (Directory-based)
# =============================================================================

def run_incremental_lint(
    story_dir: Path,
    base_url: str,
    timeout: int = 900,
    local_llm: str = None,
    local_llm_port: int = 8080,
) -> Dict[str, Any]:
    """
    Run story_lint.py in incremental mode on a directory of chapters.
    
    This calls story_lint.py with --mode incremental which:
    1. Processes chapters in order (000.txt, 001.txt, etc.)
    2. Runs both LLM direct linting and ILASP learning on each chapter
    3. Returns comparison of both approaches
    
    Returns dict with:
        - success: bool
        - llm_errors: list of LLM-detected errors
        - ilasp_errors: list of ILASP-detected errors
        - chapters: per-chapter breakdown
        - comparison: summary comparing both approaches
        - duration_seconds: float
        - stderr: captured stderr for debugging
    """
    start_time = datetime.now()
    
    # Build command
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "story_lint.py"),
        "--mode", "incremental",
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
    ]
    
    # Add local LLM options if specified
    if local_llm:
        cmd.extend(["--local-llm", local_llm])
        cmd.extend(["--local-llm-port", str(local_llm_port)])
    
    # Add the story directory path
    cmd.append(str(story_dir))
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * 3,
            cwd=str(REPO_ROOT)
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Parse stdout as JSON
        output = None
        try:
            if result.stdout.strip():
                output = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
        
        if output is None:
            output = {}
        
        # Ensure structure exists for incremental mode
        if "llm_errors" not in output:
            output["llm_errors"] = []
        if "ilasp_errors" not in output:
            output["ilasp_errors"] = []
        if "chapters" not in output:
            output["chapters"] = []
        if "comparison" not in output:
            output["comparison"] = {}
        
        # Determine success
        output["success"] = result.returncode == 0 or len(output["llm_errors"]) > 0 or len(output["ilasp_errors"]) > 0
        output["duration_seconds"] = duration
        output["stderr"] = result.stderr[:5000] if result.stderr else ""
        output["returncode"] = result.returncode
        
        return output
            
    except subprocess.TimeoutExpired:
        return {
            "success": False, 
            "error": "Timeout", 
            "duration_seconds": timeout * 3,
            "llm_errors": [],
            "ilasp_errors": [],
            "chapters": [],
            "comparison": {}
        }
    except Exception as e:
        return {
            "success": False, 
            "error": str(e), 
            "duration_seconds": 0,
            "llm_errors": [],
            "ilasp_errors": [],
            "chapters": [],
            "comparison": {}
        }

# =============================================================================
# ERROR EXTRACTION AND NORMALIZATION
# =============================================================================

def extract_errors_incremental(lint_result: Dict, source: str, book: str) -> List[Dict]:
    """
    Extract and normalize errors from incremental lint result.
    
    Args:
        lint_result: Result from run_incremental_lint
        source: "llm" or "ilasp"
        book: Book name for tagging
    
    Returns:
        List of normalized error dicts
    """
    errors = []
    
    key = f"{source}_errors"
    if key not in lint_result:
        return errors
    
    error_list = lint_result[key]
    if not isinstance(error_list, list):
        return errors
    
    for idx, err in enumerate(error_list):
        if not isinstance(err, dict):
            continue
            
        # Normalize category
        category = str(err.get("category", "unknown")).lower()
        if category not in CATEGORIES:
            category = "coherence"
        
        # Get description
        description = err.get("description", "")
        if not description:
            description = err.get("id", f"Error {idx}")
        
        errors.append({
            "source": source,
            "id": err.get("id", f"{source}_{idx}"),
            "category": category,
            "description": description,
            "chapter": err.get("chapter", 0),
            "chapter_file": err.get("chapter_file", ""),
            "severity": err.get("severity", "medium"),
            "book": book,
            "raw": err
        })
    
    return errors


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
        cat = err.get("category", "unknown")
        if cat in counts:
            counts[cat] += 1
        else:
            counts["unknown"] = counts.get("unknown", 0) + 1
    return counts

# =============================================================================
# K-FOLD CROSS VALIDATION FOR INCREMENTAL MODE
# =============================================================================

def run_kfold_incremental(
    k: int,
    books: List[str],
    base_url: str,
    timeout: int,
    experiment_dir: Path,
    logger: Logger,
    local_llm: str = None,
    local_llm_port: int = 8080,
) -> Dict[str, Any]:
    """
    Run k-fold cross-validation experiment using incremental mode.
    
    For each fold:
    1. Split books into train (for baseline) and test sets
    2. Run incremental linter on train books (original) to collect false positive signatures
    3. Run incremental linter on test books (modified) to detect errors
    4. Filter out false positives from test results
    5. Compare LLM vs ILASP performance
    """
    
    logger.section(f"K-FOLD CROSS-VALIDATION (INCREMENTAL MODE): k={k}")
    
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
        # PHASE 1: BASELINE - Collect false positives from ORIGINAL
        # ============================================
        logger.info("PHASE 1: Collecting baseline from ORIGINAL books (incremental mode)...")
        baseline_errors_llm = []
        baseline_errors_ilasp = []
        baseline_results = []
        
        for book_name in train_books:
            book_dir = ORIGINAL_BOOKS / book_name
            
            if not book_dir.exists():
                logger.warn(f"  Book directory not found: {book_dir}")
                continue
            
            logger.info(f"  Baseline: {book_name}")
            
            result = run_incremental_lint(
                book_dir, base_url, timeout, local_llm, local_llm_port
            )
            
            # Log counts
            llm_count = len(result.get("llm_errors", []))
            ilasp_count = len(result.get("ilasp_errors", []))
            logger.info(f"    Counts: LLM={llm_count}, ILASP={ilasp_count}, success={result.get('success')}")
            
            # If there's stderr, log first 300 chars for debugging
            if result.get("stderr"):
                stderr_preview = result["stderr"][:300].replace('\n', ' ')
                logger.info(f"    stderr preview: {stderr_preview}")
            
            # Extract errors from ORIGINAL (these are false positives)
            llm_errs = extract_errors_incremental(result, "llm", book_name)
            ilasp_errs = extract_errors_incremental(result, "ilasp", book_name)
            
            baseline_errors_llm.extend(llm_errs)
            baseline_errors_ilasp.extend(ilasp_errs)
            
            baseline_results.append({
                "book": book_name,
                "llm_error_count": len(llm_errs),
                "ilasp_error_count": len(ilasp_errs),
                "chapters_processed": len(result.get("chapters", [])),
                "duration": result.get("duration_seconds", 0),
                "success": result.get("success", False)
            })
            
            logger.info(f"    Extracted {len(llm_errs)} LLM, {len(ilasp_errs)} ILASP false positives")
        
        # Compute baseline signatures (these represent false positive patterns)
        baseline_sigs_llm = set(compute_error_signature(e) for e in baseline_errors_llm)
        baseline_sigs_ilasp = set(compute_error_signature(e) for e in baseline_errors_ilasp)
        
        logger.info(f"Baseline complete: {len(baseline_sigs_llm)} LLM sigs, {len(baseline_sigs_ilasp)} ILASP sigs")
        
        # ============================================
        # PHASE 2: TEST - Detect errors in MODIFIED
        # ============================================
        logger.info("PHASE 2: Testing on MODIFIED books (incremental mode)...")
        test_results = []
        
        for book_name in test_books:
            book_dir = MODIFIED_BOOKS / book_name
            
            if not book_dir.exists():
                logger.warn(f"  Modified book directory not found: {book_dir}")
                continue
            
            logger.info(f"  Testing: {book_name}")
            book_start = datetime.now()
            
            result = run_incremental_lint(
                book_dir, base_url, timeout, local_llm, local_llm_port
            )
            
            # Log counts
            llm_count = len(result.get("llm_errors", []))
            ilasp_count = len(result.get("ilasp_errors", []))
            logger.info(f"    Counts: LLM={llm_count}, ILASP={ilasp_count}, success={result.get('success')}")
            
            # If there's stderr, log first 300 chars for debugging
            if result.get("stderr"):
                stderr_preview = result["stderr"][:300].replace('\n', ' ')
                logger.info(f"    stderr preview: {stderr_preview}")
            
            # Extract ALL errors from modified books
            llm_errs = extract_errors_incremental(result, "llm", book_name)
            ilasp_errs = extract_errors_incremental(result, "ilasp", book_name)
            
            logger.info(f"    Extracted: LLM={len(llm_errs)}, ILASP={len(ilasp_errs)}")
            
            # Filter: true positives are errors NOT in baseline
            llm_tp = [e for e in llm_errs if compute_error_signature(e) not in baseline_sigs_llm]
            llm_fp = [e for e in llm_errs if compute_error_signature(e) in baseline_sigs_llm]
            ilasp_tp = [e for e in ilasp_errs if compute_error_signature(e) not in baseline_sigs_ilasp]
            ilasp_fp = [e for e in ilasp_errs if compute_error_signature(e) in baseline_sigs_ilasp]
            
            book_end = datetime.now()
            
            book_result = {
                "book": book_name,
                "start_time": book_start.isoformat(),
                "end_time": book_end.isoformat(),
                "duration_seconds": (book_end - book_start).total_seconds(),
                "success": result.get("success", False),
                "chapters_processed": len(result.get("chapters", [])),
                "llm": {
                    "total_detected": len(llm_errs),
                    "true_positives": llm_tp,
                    "false_positives_filtered": len(llm_fp),
                    "true_positive_count": len(llm_tp),
                    "by_category": categorize_errors(llm_tp)
                },
                "ilasp": {
                    "total_detected": len(ilasp_errs),
                    "true_positives": ilasp_tp,
                    "false_positives_filtered": len(ilasp_fp),
                    "true_positive_count": len(ilasp_tp),
                    "by_category": categorize_errors(ilasp_tp)
                },
                "comparison": result.get("comparison", {}),
                "raw_result": result
            }
            
            test_results.append(book_result)
            
            logger.info(f"    Final: LLM {len(llm_tp)} TP ({len(llm_fp)} filtered), ILASP {len(ilasp_tp)} TP ({len(ilasp_fp)} filtered)")
        
        fold_end = datetime.now()
        
        # Aggregate fold results
        fold_llm_tp = sum(r["llm"]["true_positive_count"] for r in test_results)
        fold_ilasp_tp = sum(r["ilasp"]["true_positive_count"] for r in test_results)
        
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
                "ilasp_false_positive_signatures": len(baseline_sigs_ilasp),
                "results": baseline_results
            },
            "test": {
                "llm_true_positives": fold_llm_tp,
                "ilasp_true_positives": fold_ilasp_tp,
                "results": test_results
            }
        }
        
        fold_results.append(fold_result)
        logger.info(f"Fold {fold_idx + 1} complete: LLM TP={fold_llm_tp}, ILASP TP={fold_ilasp_tp}")
        
        # Save fold results
        fold_file = experiment_dir / "results" / f"fold_{fold_idx + 1}_k{k}.json"
        fold_file.parent.mkdir(parents=True, exist_ok=True)
        fold_file.write_text(json.dumps(fold_result, indent=2, default=str), encoding="utf-8")
    
    # Aggregate across folds
    llm_totals = [f["test"]["llm_true_positives"] for f in fold_results]
    ilasp_totals = [f["test"]["ilasp_true_positives"] for f in fold_results]
    
    return {
        "k": k,
        "fold_results": fold_results,
        "aggregate": {
            "llm_mean": sum(llm_totals) / len(llm_totals) if llm_totals else 0,
            "llm_total": sum(llm_totals),
            "ilasp_mean": sum(ilasp_totals) / len(ilasp_totals) if ilasp_totals else 0,
            "ilasp_total": sum(ilasp_totals),
            "folds_completed": len(fold_results)
        }
    }

# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report(experiment_dir: Path, results: Dict, logger: Logger) -> str:
    """Generate comprehensive markdown report for incremental mode experiment."""
    
    logger.info("Generating markdown report...")
    
    r = []
    r.append("# Incremental Mode Experiment Report\n")
    r.append("## LLM Direct Linting vs ILASP Incremental Learning\n\n")
    r.append(f"**Generated:** {datetime.now().isoformat()}\n")
    r.append(f"**Model:** {results.get('model_name', 'Unknown')}\n")
    r.append(f"**Server Model:** {results.get('server_model', 'Unknown')}\n")
    r.append(f"**Start:** {results.get('start_time', 'N/A')}\n")
    r.append(f"**End:** {results.get('end_time', 'N/A')}\n")
    r.append(f"**Duration:** {results.get('total_duration_seconds', 0):.2f} seconds\n")
    
    # Methodology
    r.append("\n## 1. Methodology\n")
    r.append("This experiment compares two approaches to narrative evaluation using **incremental mode**:\n\n")
    r.append("### LLM Direct Linting\n")
    r.append("- Each chapter is analyzed independently by the LLM\n")
    r.append("- LLM directly looks for inconsistencies, contradictions, errors\n")
    r.append("- No accumulated knowledge between chapters\n\n")
    r.append("### ILASP Incremental Learning\n")
    r.append("- Chapter 1: Learn entities, events, relationships (no checking)\n")
    r.append("- Chapter 2+: Check against accumulated knowledge, then learn\n")
    r.append("- Uses ASP (Answer Set Programming) rules learned from story patterns\n")
    r.append("- Detects: Dead agents speaking, ubiquity violations, temporal anomalies\n\n")
    
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
    r.append("| Dead Agent | Dead character appears/speaks/acts |\n")
    r.append("| Ubiquity | Character in two places simultaneously |\n")
    r.append("| Temporal Anomaly | Event order violations |\n")
    r.append("| Contradiction | Direct logical contradiction |\n")
    
    # Configuration
    config = results.get("config", {})
    r.append("\n## 3. Configuration\n")
    r.append(f"- **Mode:** Incremental (chapter-by-chapter)\n")
    r.append(f"- **K values tested:** {config.get('k_values', 'N/A')}\n")
    r.append(f"- **Books:** {', '.join(config.get('books', BOOKS))}\n")
    r.append(f"- **Timeout:** {config.get('timeout', 'N/A')} seconds\n")
    if config.get('local_llm'):
        r.append(f"- **Local LLM:** {config.get('local_llm')}\n")
    
    # K-fold results summary
    r.append("\n## 4. K-Fold Results Summary\n")
    
    for k_result in results.get("k_fold_results", []):
        k = k_result["k"]
        agg = k_result.get("aggregate", {})
        
        r.append(f"\n### K={k}\n")
        r.append(f"- **LLM True Positives (Total):** {agg.get('llm_total', 0)}\n")
        r.append(f"- **LLM True Positives (Mean per fold):** {agg.get('llm_mean', 0):.2f}\n")
        r.append(f"- **ILASP True Positives (Total):** {agg.get('ilasp_total', 0)}\n")
        r.append(f"- **ILASP True Positives (Mean per fold):** {agg.get('ilasp_mean', 0):.2f}\n")
        
        r.append("\n| Fold | Train Books | Test Books | Baseline FP | LLM TP | ILASP TP | Duration |\n")
        r.append("|------|-------------|------------|-------------|--------|----------|----------|\n")
        
        for fold in k_result.get("fold_results", []):
            train = ", ".join(b[:12] for b in fold.get("train_books", []))
            test = ", ".join(b[:12] for b in fold.get("test_books", []))
            baseline_fp = fold["baseline"]["llm_false_positive_signatures"] + fold["baseline"]["ilasp_false_positive_signatures"]
            llm_tp = fold["test"]["llm_true_positives"]
            ilasp_tp = fold["test"]["ilasp_true_positives"]
            duration = fold["duration_seconds"]
            r.append(f"| {fold['fold']} | {train} | {test} | {baseline_fp} | {llm_tp} | {ilasp_tp} | {duration:.1f}s |\n")
    
    # Category breakdown
    r.append("\n## 5. Errors by Category (All Folds Combined)\n")
    
    llm_cats = {cat: 0 for cat in CATEGORIES}
    ilasp_cats = {cat: 0 for cat in CATEGORIES}
    
    for k_result in results.get("k_fold_results", []):
        for fold in k_result.get("fold_results", []):
            for test in fold.get("test", {}).get("results", []):
                for cat in CATEGORIES:
                    llm_cats[cat] += test["llm"]["by_category"].get(cat, 0)
                    ilasp_cats[cat] += test["ilasp"]["by_category"].get(cat, 0)
    
    r.append("\n| Category | LLM True Positives | ILASP True Positives | Total |\n")
    r.append("|----------|--------------------|--------------------|-------|\n")
    for cat in CATEGORIES:
        total = llm_cats[cat] + ilasp_cats[cat]
        if total > 0:  # Only show categories with errors
            r.append(f"| {cat.capitalize()} | {llm_cats[cat]} | {ilasp_cats[cat]} | {total} |\n")
    
    r.append(f"\n**Grand Total:** LLM={sum(llm_cats.values())}, ILASP={sum(ilasp_cats.values())}\n")
    
    # Sample errors
    r.append("\n## 6. Sample Errors\n")
    
    sample_count = 0
    max_samples = 15
    
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
                    
                    r.append(f"\n### Error {sample_count + 1}: {err.get('category', 'unknown').upper()} (LLM)\n")
                    r.append(f"**Book:** {test['book']}\n")
                    r.append(f"**Chapter:** {err.get('chapter', 'N/A')}\n\n")
                    r.append(f"**Description:** {err.get('description', 'N/A')}\n\n")
                    sample_count += 1
                
                # ILASP true positives
                for err in test["ilasp"].get("true_positives", [])[:2]:
                    if sample_count >= max_samples:
                        break
                    
                    r.append(f"\n### Error {sample_count + 1}: {err.get('category', 'unknown').upper()} (ILASP)\n")
                    r.append(f"**Book:** {test['book']}\n")
                    r.append(f"**Chapter:** {err.get('chapter', 'N/A')}\n\n")
                    r.append(f"**Description:** {err.get('description', 'N/A')}\n\n")
                    sample_count += 1
    
    # Analysis
    r.append("\n## 7. Analysis: LLM vs ILASP\n")
    
    r.append("\n### Comparison of Approaches\n")
    r.append("| Aspect | LLM Direct | ILASP Incremental |\n")
    r.append("|--------|-----------|-------------------|\n")
    r.append("| Strengths | Contextual understanding, subtle errors | Logical consistency, no hallucination |\n")
    r.append("| Weaknesses | May hallucinate, inconsistent | Limited to encoded rules |\n")
    r.append("| Knowledge | Per-chapter (no accumulation) | Accumulates across chapters |\n")
    r.append("| Best for | Emotional, coherence | Dead agents, ubiquity, temporal |\n")
    
    total_llm = sum(llm_cats.values())
    total_ilasp = sum(ilasp_cats.values())
    
    r.append("\n### Key Findings\n")
    r.append(f"- **Total LLM true positive errors:** {total_llm}\n")
    r.append(f"- **Total ILASP true positive errors:** {total_ilasp}\n")
    if total_llm > 0 and total_ilasp > 0:
        r.append(f"- **LLM/ILASP ratio:** {total_llm/total_ilasp:.2f}\n")
    
    winner = "LLM" if total_llm > total_ilasp else ("ILASP" if total_ilasp > total_llm else "Tie")
    r.append(f"- **Better performer:** {winner}\n")
    
    # Timing
    r.append("\n## 8. Timing Statistics\n")
    
    total_books = 0
    total_time = 0
    
    for k_result in results.get("k_fold_results", []):
        for fold in k_result.get("fold_results", []):
            for test in fold.get("test", {}).get("results", []):
                total_books += 1
                total_time += test.get("duration_seconds", 0)
    
    r.append(f"- **Total test books processed:** {total_books}\n")
    r.append(f"- **Total processing time:** {total_time:.2f} seconds\n")
    if total_books > 0:
        r.append(f"- **Average time per book:** {total_time/total_books:.2f} seconds\n")
    
    # Conclusion
    r.append("\n## 9. Conclusion\n")
    r.append("This experiment demonstrates the incremental narrative evaluation approach, ")
    r.append("comparing direct LLM analysis against ILASP's incremental learning.\n\n")
    r.append("**LLM Direct** excels at catching contextual issues that require natural language ")
    r.append("understanding, but may hallucinate errors.\n\n")
    r.append("**ILASP Incremental** provides sound logical reasoning based on accumulated ")
    r.append("knowledge, catching structural violations like dead agents speaking or ubiquity errors.\n\n")
    r.append("The combination of both approaches provides comprehensive coverage.\n")
    
    r.append("\n---\n")
    r.append(f"*Report generated at {datetime.now().isoformat()}*\n")
    
    return "".join(r)

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run k-fold cross-validation for incremental mode (LLM vs ILASP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with external LLM server
  python3 scripts/run_kfold_incremental.py --model-name "gemma"
  
  # With specific local llamafile model
  python3 scripts/run_kfold_incremental.py --model-name "gemma" --local-llm gemma-3-12b
  
  # Single k-value for quick testing
  python3 scripts/run_kfold_incremental.py --model-name "test" --k-values "1"
  
  # Specific books only
  python3 scripts/run_kfold_incremental.py --model-name "test" --books "Harry Potter,Goosebumps"
        """
    )
    
    parser.add_argument("--model-name", required=True, help="Model name for output directory")
    parser.add_argument("--base-url", default="http://localhost:8080/v1", help="LLM server URL")
    parser.add_argument("--k-values", default="1,2,3,4", help="Comma-separated k values")
    parser.add_argument("--timeout", type=int, default=900, help="Timeout per book (seconds)")
    parser.add_argument("--books", default=None, help="Comma-separated book names")
    parser.add_argument("--local-llm", default=None, 
                        help="Local llamafile model (mistral-7b, gemma-3-12b, deepseek-r1-7b)")
    parser.add_argument("--local-llm-port", type=int, default=8080, help="Local LLM server port")
    
    args = parser.parse_args()
    
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    books = [b.strip() for b in args.books.split(",")] if args.books else BOOKS
    
    # Create experiment directory
    exp_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    exp_name = f"incremental_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}"
    exp_dir = EXPERIMENTS_DIR / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize logger
    logger = Logger(exp_dir / "log.txt")
    
    logger.section("INCREMENTAL MODE K-FOLD EXPERIMENT")
    logger.info(f"Experiment: {exp_name}")
    logger.info(f"Output: {exp_dir}")
    logger.info(f"K values: {k_values}")
    logger.info(f"Books: {books}")
    logger.info(f"Mode: incremental (LLM vs ILASP comparison)")
    if args.local_llm:
        logger.info(f"Local LLM: {args.local_llm}")
    
    # Check server (unless using local llamafile that will be started by story_lint)
    if not args.local_llm:
        logger.info("Checking LLM server...")
        ok, server_model = check_server(args.base_url)
        if not ok:
            logger.error(f"Server not available at {args.base_url}")
            logger.error("Please start the LLM server first, or use --local-llm")
            sys.exit(1)
        logger.info(f"Server OK: {server_model}")
    else:
        server_model = args.local_llm
        logger.info(f"Will use local llamafile: {args.local_llm}")
    
    # Save config
    config = {
        "experiment_id": exp_id,
        "model_name": args.model_name,
        "server_model": server_model,
        "start_time": start_time.isoformat(),
        "base_url": args.base_url,
        "k_values": k_values,
        "timeout": args.timeout,
        "books": books,
        "local_llm": args.local_llm,
        "local_llm_port": args.local_llm_port,
        "mode": "incremental",
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
        k_result = run_kfold_incremental(
            k=k,
            books=books,
            base_url=args.base_url,
            timeout=args.timeout,
            experiment_dir=exp_dir,
            logger=logger,
            local_llm=args.local_llm,
            local_llm_port=args.local_llm_port,
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
    final_name = f"incremental_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
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
    print("INCREMENTAL MODE EXPERIMENT COMPLETE")
    print(f"{'='*70}")
    print(f"Output: {output_dir}")
    print(f"Duration: {results['total_duration_seconds']:.2f} seconds")
    print()
    print("K-Fold Results Summary (LLM vs ILASP):")
    for k_result in results["k_fold_results"]:
        k = k_result["k"]
        agg = k_result["aggregate"]
        print(f"  k={k}: LLM TP={agg['llm_total']}, ILASP TP={agg['ilasp_total']}")
    print()
    print("Files:")
    print("  - results.json (complete data)")
    print("  - report.md (markdown report)")
    print("  - log.txt (execution log)")
    print("  - results/ (per-fold JSON files)")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
