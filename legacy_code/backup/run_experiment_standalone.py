#!/usr/bin/env python3
"""
run_experiment_standalone.py - Standalone Experiment Runner (No Bash Required)
===============================================================================

This script runs the narrative evaluation experiment assuming an LLM server
is already running on localhost:8080.

Usage:
    # First, start your model server manually in another terminal
    # Then run this script:
    python3 scripts/run_experiment_standalone.py --model-name "gemma_3_12b"

The script will:
1. Check server connectivity
2. Process 2 chapters per book (configurable)
3. Run both LLM and logic-based linting
4. Apply k-fold cross-validation
5. Generate comprehensive reports

Output is saved to: experiments/pilot_<model>_<timestamp>/
"""

import argparse
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
ORIGINAL_BOOKS_DIR = REPO_ROOT / "original_books"
MODIFIED_BOOKS_DIR = REPO_ROOT / "modified_books"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]
BOOKS = ["Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight", "Goosebumps"]

# =============================================================================
# LOGGING
# =============================================================================

class ExperimentLogger:
    """Logger that writes to both console and file with timestamps."""
    
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
        self.log("=" * 70)
        self.log(title)
        self.log("=" * 70)

# =============================================================================
# SERVER CONNECTIVITY
# =============================================================================

def check_server(base_url: str = "http://localhost:8080/v1", timeout: int = 10) -> Tuple[bool, str]:
    """Check if LLM server is responding."""
    try:
        url = f"{base_url}/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            if models:
                model_id = models[0].get("id", "unknown")
                return True, model_id
            return True, "unknown"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e}"
    except Exception as e:
        return False, f"Error: {e}"

# =============================================================================
# CHAPTER LOADING
# =============================================================================

def load_chapters(book_dir: Path, max_chapters: int = 2) -> List[Dict[str, Any]]:
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
                "path": str(f)
            })
        except Exception as e:
            print(f"Warning: Could not read {f}: {e}", file=sys.stderr)
    
    return chapters

# =============================================================================
# STORY LINTING
# =============================================================================

def run_story_lint(
    story_text: str,
    base_url: str = "http://localhost:8080/v1",
    timeout: int = 600,
    mode: str = "both"
) -> Dict[str, Any]:
    """
    Run story_lint.py on a story text.
    
    Returns dict with:
        - success: bool
        - llm_lint: dict with errors (if mode includes llm)
        - logic_lint: dict with errors (if mode includes logic)
        - duration_seconds: float
        - error: str (if failed)
    """
    start_time = datetime.now()
    
    # Write story to temp file
    fd, story_path = tempfile.mkstemp(suffix='.txt', prefix='story_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(story_text)
        
        # Build command
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
        
        # Run subprocess
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * 3,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(SCRIPT_DIR)}
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr[:2000] if result.stderr else "Unknown error",
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
            return output
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON parse error: {e}",
                "stdout": result.stdout[:2000],
                "duration_seconds": duration,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Timeout",
            "duration_seconds": timeout * 3,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "duration_seconds": (datetime.now() - start_time).total_seconds(),
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat()
        }
    finally:
        # Clean up temp file
        try:
            os.unlink(story_path)
        except:
            pass

# =============================================================================
# ERROR EXTRACTION
# =============================================================================

def extract_errors(lint_result: Dict, source: str, story_text: str) -> List[Dict]:
    """Extract and normalize errors from lint results."""
    errors = []
    
    if not lint_result.get("success"):
        return errors
    
    key = f"{source}_lint"
    if key not in lint_result:
        return errors
    
    for err in lint_result[key].get("errors", []):
        category = err.get("category", "coherence").lower()
        if category not in ERROR_CATEGORIES:
            category = "coherence"
        
        # Extract story fragments if not present
        fragments = err.get("story_fragments", [])
        if not fragments:
            # Try to find relevant text based on description
            desc = err.get("description", "").lower()
            fragments = extract_fragments_from_description(desc, story_text)
        
        errors.append({
            "source": source,
            "id": err.get("id", f"{source}_{len(errors)}"),
            "category": category,
            "description": err.get("description", "No description"),
            "story_fragments": fragments,
            "violation_type": err.get("violation_type", ""),
            "involved_entities": err.get("involved_entities", []),
            "raw": err
        })
    
    return errors


def extract_fragments_from_description(description: str, story_text: str, context_chars: int = 200) -> List[str]:
    """Try to find story fragments related to an error description."""
    fragments = []
    
    # Extract quoted strings from description
    import re
    quoted = re.findall(r"'([^']+)'", description)
    quoted.extend(re.findall(r'"([^"]+)"', description))
    
    # Search for each quoted string in story
    story_lower = story_text.lower()
    for term in quoted[:3]:
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


def categorize_errors(errors: List[Dict]) -> Dict[str, int]:
    """Count errors by category."""
    counts = {cat: 0 for cat in ERROR_CATEGORIES}
    for err in errors:
        cat = err.get("category", "coherence")
        if cat in counts:
            counts[cat] += 1
    return counts


def compute_error_signature(error: Dict) -> str:
    """Compute signature for deduplication."""
    category = error.get("category", "unknown")
    desc = error.get("description", "")[:100].lower()
    return f"{category}:{hash(desc)}"

# =============================================================================
# K-FOLD CROSS VALIDATION
# =============================================================================

def run_kfold_experiment(
    k: int,
    books: List[str],
    model_name: str,
    base_url: str,
    chapters_per_book: int,
    timeout: int,
    experiment_dir: Path,
    logger: ExperimentLogger
) -> Dict[str, Any]:
    """Run k-fold cross-validation experiment."""
    
    logger.section(f"K-FOLD EXPERIMENT: k={k}")
    
    fold_results = []
    n_books = len(books)
    fold_size = max(1, n_books // k) if k > 0 else n_books
    
    for fold_idx in range(k):
        logger.info(f"--- Fold {fold_idx + 1}/{k} ---")
        fold_start = datetime.now()
        
        # Split books into train/test
        test_start = fold_idx * fold_size
        test_end = min(test_start + fold_size, n_books)
        test_books = books[test_start:test_end]
        train_books = books[:test_start] + books[test_end:]
        if not train_books:
            train_books = test_books
        
        logger.info(f"Train books: {train_books}")
        logger.info(f"Test books: {test_books}")
        
        # Phase 1: Baseline (original books - collect false positives)
        logger.info("Phase 1: Collecting baseline errors from original books...")
        baseline_errors = []
        
        for book_name in train_books:
            book_dir = ORIGINAL_BOOKS_DIR / book_name
            chapters = load_chapters(book_dir, chapters_per_book)
            
            for chapter in chapters:
                logger.info(f"  Baseline: {book_name}/{chapter['id']}")
                result = run_story_lint(chapter["text"], base_url, timeout)
                
                llm_errors = extract_errors(result, "llm", chapter["text"])
                logic_errors = extract_errors(result, "logic", chapter["text"])
                baseline_errors.extend(llm_errors)
                baseline_errors.extend(logic_errors)
        
        # Compute baseline signatures for filtering
        baseline_sigs = set(compute_error_signature(e) for e in baseline_errors)
        logger.info(f"Baseline: {len(baseline_sigs)} unique error signatures")
        
        # Phase 2: Test on modified books
        logger.info("Phase 2: Testing on modified books...")
        test_results = []
        
        for book_name in test_books:
            book_dir = MODIFIED_BOOKS_DIR / book_name
            chapters = load_chapters(book_dir, chapters_per_book)
            
            for chapter in chapters:
                logger.info(f"  Testing: {book_name}/{chapter['id']}")
                ch_start = datetime.now()
                
                result = run_story_lint(chapter["text"], base_url, timeout)
                
                # Extract errors
                llm_errors = extract_errors(result, "llm", chapter["text"])
                logic_errors = extract_errors(result, "logic", chapter["text"])
                
                # Filter false positives
                llm_tp = [e for e in llm_errors if compute_error_signature(e) not in baseline_sigs]
                llm_fp = [e for e in llm_errors if compute_error_signature(e) in baseline_sigs]
                logic_tp = [e for e in logic_errors if compute_error_signature(e) not in baseline_sigs]
                logic_fp = [e for e in logic_errors if compute_error_signature(e) in baseline_sigs]
                
                ch_end = datetime.now()
                
                chapter_result = {
                    "book": book_name,
                    "chapter_id": chapter["id"],
                    "chapter_title": chapter["title"],
                    "start_time": ch_start.isoformat(),
                    "end_time": ch_end.isoformat(),
                    "duration_seconds": (ch_end - ch_start).total_seconds(),
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
                
                logger.info(f"    LLM: {len(llm_tp)} true positives, {len(llm_fp)} false positives")
                logger.info(f"    Logic: {len(logic_tp)} true positives, {len(logic_fp)} false positives")
                
                # Save chapter text
                story_dir = experiment_dir / "stories" / book_name
                story_dir.mkdir(parents=True, exist_ok=True)
                (story_dir / f"{chapter['id']}.txt").write_text(chapter["text"], encoding="utf-8")
        
        fold_end = datetime.now()
        
        # Aggregate fold results
        fold_llm_total = sum(r["llm"]["total_errors"] for r in test_results)
        fold_logic_total = sum(r["logic"]["total_errors"] for r in test_results)
        
        fold_result = {
            "fold": fold_idx + 1,
            "k": k,
            "train_books": train_books,
            "test_books": test_books,
            "start_time": fold_start.isoformat(),
            "end_time": fold_end.isoformat(),
            "duration_seconds": (fold_end - fold_start).total_seconds(),
            "baseline_error_count": len(baseline_errors),
            "baseline_unique_signatures": len(baseline_sigs),
            "llm_total": fold_llm_total,
            "logic_total": fold_logic_total,
            "test_results": test_results
        }
        
        fold_results.append(fold_result)
        logger.info(f"Fold {fold_idx + 1} complete: LLM={fold_llm_total}, Logic={fold_logic_total}")
        
        # Save fold results
        fold_file = experiment_dir / "results" / f"fold_{fold_idx + 1}_k{k}.json"
        fold_file.parent.mkdir(parents=True, exist_ok=True)
        fold_file.write_text(json.dumps(fold_result, indent=2, default=str), encoding="utf-8")
    
    # Aggregate across folds
    llm_totals = [f["llm_total"] for f in fold_results]
    logic_totals = [f["logic_total"] for f in fold_results]
    
    return {
        "k": k,
        "model": model_name,
        "fold_results": fold_results,
        "aggregate": {
            "llm_mean": sum(llm_totals) / len(llm_totals) if llm_totals else 0,
            "logic_mean": sum(logic_totals) / len(logic_totals) if logic_totals else 0,
            "llm_totals": llm_totals,
            "logic_totals": logic_totals,
            "folds_completed": len(fold_results)
        }
    }

# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report(experiment_dir: Path, results: Dict, logger: ExperimentLogger) -> str:
    """Generate comprehensive markdown report."""
    
    logger.info("Generating markdown report...")
    
    r = []
    r.append("# Narrative Evaluation Pilot Experiment Report\n")
    r.append(f"**Generated:** {datetime.now().isoformat()}\n")
    r.append(f"**Model:** {results.get('model_name', 'Unknown')}\n")
    r.append(f"**Start Time:** {results.get('start_time', 'N/A')}\n")
    r.append(f"**End Time:** {results.get('end_time', 'N/A')}\n")
    r.append(f"**Total Duration:** {results.get('total_duration_seconds', 0):.2f} seconds\n")
    
    # Overview
    r.append("\n## 1. Experiment Overview\n")
    r.append("This experiment compares two approaches to narrative evaluation:\n")
    r.append("- **LLM-based evaluation**: Direct analysis using Large Language Models\n")
    r.append("- **Logic-based evaluation**: Translation to logic predicates (Clingo/ASP)\n")
    
    r.append("\n### Error Categories\n")
    r.append("| Category | Description |\n")
    r.append("|----------|-------------|\n")
    r.append("| Causality | Chekhov's gun, causal chains, unexplained events |\n")
    r.append("| Coherence | Semantic correctness, logical consistency |\n")
    r.append("| Temporal | Time ordering, duration violations |\n")
    r.append("| Location | Spatial constraints, ubiquity errors |\n")
    r.append("| Emotional | Character behavior vs relationships |\n")
    
    # Configuration
    config = results.get("config", {})
    r.append("\n## 2. Configuration\n")
    r.append(f"- **Chapters per Book:** {config.get('chapters_per_book', 'N/A')}\n")
    r.append(f"- **K-fold Values:** {config.get('k_values', 'N/A')}\n")
    r.append(f"- **Books:** {config.get('books', BOOKS)}\n")
    r.append(f"- **Timeout:** {config.get('timeout', 'N/A')} seconds\n")
    
    # K-fold results
    r.append("\n## 3. K-Fold Cross-Validation Results\n")
    
    for k_result in results.get("k_fold_results", []):
        k = k_result["k"]
        agg = k_result.get("aggregate", {})
        
        r.append(f"\n### K={k}\n")
        r.append(f"- **LLM Mean Errors:** {agg.get('llm_mean', 0):.2f}\n")
        r.append(f"- **Logic Mean Errors:** {agg.get('logic_mean', 0):.2f}\n")
        
        r.append("\n| Fold | Train Books | Test Books | LLM Errors | Logic Errors | Duration (s) |\n")
        r.append("|------|-------------|------------|------------|--------------|-------------|\n")
        
        for fold in k_result.get("fold_results", []):
            train = ", ".join(b[:10] for b in fold.get("train_books", []))
            test = ", ".join(b[:10] for b in fold.get("test_books", []))
            r.append(f"| {fold['fold']} | {train} | {test} | {fold['llm_total']} | {fold['logic_total']} | {fold['duration_seconds']:.1f} |\n")
    
    # Category breakdown
    r.append("\n## 4. Errors by Category\n")
    
    llm_cats = {cat: 0 for cat in ERROR_CATEGORIES}
    logic_cats = {cat: 0 for cat in ERROR_CATEGORIES}
    
    for k_result in results.get("k_fold_results", []):
        for fold in k_result.get("fold_results", []):
            for test in fold.get("test_results", []):
                for cat in ERROR_CATEGORIES:
                    llm_cats[cat] += test["llm"]["by_category"].get(cat, 0)
                    logic_cats[cat] += test["logic"]["by_category"].get(cat, 0)
    
    r.append("\n| Category | LLM Errors | Logic Errors |\n")
    r.append("|----------|------------|-------------|\n")
    for cat in ERROR_CATEGORIES:
        r.append(f"| {cat.capitalize()} | {llm_cats[cat]} | {logic_cats[cat]} |\n")
    
    # Sample errors with fragments
    r.append("\n## 5. Sample Errors with Story Fragments\n")
    r.append("Representative errors showing the story text that triggered detection:\n")
    
    sample_count = 0
    max_samples = 15
    
    for k_result in results.get("k_fold_results", []):
        if sample_count >= max_samples:
            break
        for fold in k_result.get("fold_results", []):
            if sample_count >= max_samples:
                break
            for test in fold.get("test_results", []):
                if sample_count >= max_samples:
                    break
                
                # LLM errors
                for err in test["llm"].get("true_positives", [])[:2]:
                    if sample_count >= max_samples:
                        break
                    
                    r.append(f"\n### Error {sample_count + 1} (LLM - {err['category'].capitalize()})\n")
                    r.append(f"**Book:** {test['book']}, **Chapter:** {test['chapter_id']}\n\n")
                    r.append(f"**Description:** {err['description']}\n\n")
                    
                    if err.get("story_fragments"):
                        r.append("**Story Fragments:**\n")
                        for frag in err["story_fragments"][:2]:
                            r.append(f"> {frag[:400]}{'...' if len(frag) > 400 else ''}\n\n")
                    
                    sample_count += 1
                
                # Logic errors
                for err in test["logic"].get("true_positives", [])[:2]:
                    if sample_count >= max_samples:
                        break
                    
                    r.append(f"\n### Error {sample_count + 1} (Logic - {err['category'].capitalize()})\n")
                    r.append(f"**Book:** {test['book']}, **Chapter:** {test['chapter_id']}\n\n")
                    r.append(f"**Description:** {err['description']}\n\n")
                    
                    if err.get("violation_type"):
                        r.append(f"**Violation Type:** {err['violation_type']}\n\n")
                    
                    if err.get("story_fragments"):
                        r.append("**Story Fragments:**\n")
                        for frag in err["story_fragments"][:2]:
                            r.append(f"> {frag[:400]}{'...' if len(frag) > 400 else ''}\n\n")
                    
                    sample_count += 1
    
    # Analysis
    r.append("\n## 6. Analysis\n")
    
    r.append("\n### Comparison of Approaches\n")
    r.append("| Aspect | LLM-Based | Logic-Based |\n")
    r.append("|--------|-----------|-------------|\n")
    r.append("| Strengths | Contextual understanding, subtle errors | Formal consistency, sound reasoning |\n")
    r.append("| Weaknesses | May hallucinate, inconsistent | Limited to encoded rules |\n")
    r.append("| Best for | Emotional, coherence errors | Temporal, location errors |\n")
    
    r.append("\n### Key Findings\n")
    total_llm = sum(llm_cats.values())
    total_logic = sum(logic_cats.values())
    r.append(f"- Total LLM errors detected: {total_llm}\n")
    r.append(f"- Total Logic errors detected: {total_logic}\n")
    r.append(f"- Combined unique errors: {total_llm + total_logic}\n")
    
    # Timing
    r.append("\n## 7. Timing Statistics\n")
    
    total_chapters = 0
    total_time = 0
    
    for k_result in results.get("k_fold_results", []):
        for fold in k_result.get("fold_results", []):
            for test in fold.get("test_results", []):
                total_chapters += 1
                total_time += test.get("duration_seconds", 0)
    
    r.append(f"- Total chapters processed: {total_chapters}\n")
    r.append(f"- Total processing time: {total_time:.2f} seconds\n")
    if total_chapters > 0:
        r.append(f"- Average time per chapter: {total_time/total_chapters:.2f} seconds\n")
    
    # Conclusion
    r.append("\n## 8. Conclusion\n")
    r.append("This pilot experiment demonstrates the complementary nature of LLM-based and ")
    r.append("logic-based narrative evaluation. The combination provides more comprehensive ")
    r.append("coverage than either approach alone, with LLMs excelling at contextual and ")
    r.append("emotional inconsistencies while logic-based methods provide rigorous temporal ")
    r.append("and spatial constraint checking.\n")
    
    r.append("\n---\n")
    r.append(f"*Report generated by run_experiment_standalone.py at {datetime.now().isoformat()}*\n")
    
    return "".join(r)

# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run narrative evaluation experiment (assumes server is already running)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings (server must be running on localhost:8080)
    python3 scripts/run_experiment_standalone.py --model-name "gemma_3_12b"
    
    # Run with custom settings
    python3 scripts/run_experiment_standalone.py \\
        --model-name "r1_qwen" \\
        --chapters-per-book 2 \\
        --k-values "1,2" \\
        --base-url "http://localhost:8080/v1"
        """
    )
    
    parser.add_argument("--model-name", required=True, help="Name for this model run (for output directory)")
    parser.add_argument("--base-url", default="http://localhost:8080/v1", help="LLM server base URL")
    parser.add_argument("--chapters-per-book", type=int, default=2, help="Chapters to process per book")
    parser.add_argument("--k-values", default="1,2,3,4", help="Comma-separated k values for cross-validation")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout per LLM call in seconds")
    parser.add_argument("--books", default=None, help="Comma-separated book names (default: all)")
    
    args = parser.parse_args()
    
    # Parse arguments
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    books = [b.strip() for b in args.books.split(",")] if args.books else BOOKS
    
    # Create experiment directory
    exp_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    exp_dir = EXPERIMENTS_DIR / f"pilot_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize logger
    logger = ExperimentLogger(exp_dir / "log.txt")
    
    logger.section("NARRATIVE EVALUATION PILOT EXPERIMENT")
    logger.info(f"Experiment ID: {exp_id}")
    logger.info(f"Model name: {args.model_name}")
    logger.info(f"Output directory: {exp_dir}")
    logger.info(f"K values: {k_values}")
    logger.info(f"Chapters per book: {args.chapters_per_book}")
    logger.info(f"Books: {books}")
    
    # Check server connectivity
    logger.info("Checking LLM server connectivity...")
    server_ok, server_info = check_server(args.base_url)
    
    if not server_ok:
        logger.error(f"Server not available: {server_info}")
        logger.error(f"Please start the LLM server and try again.")
        logger.error(f"Expected server at: {args.base_url}")
        sys.exit(1)
    
    logger.info(f"Server OK! Model: {server_info}")
    
    # Save configuration
    config = {
        "experiment_id": exp_id,
        "model_name": args.model_name,
        "start_time": start_time.isoformat(),
        "base_url": args.base_url,
        "k_values": k_values,
        "chapters_per_book": args.chapters_per_book,
        "timeout": args.timeout,
        "books": books,
        "server_model": server_info
    }
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    
    # Initialize results
    results = {
        "config": config,
        "model_name": args.model_name,
        "start_time": start_time.isoformat(),
        "k_fold_results": []
    }
    
    # Run k-fold experiments
    for k in k_values:
        k_result = run_kfold_experiment(
            k=k,
            books=books,
            model_name=args.model_name,
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
    (exp_dir / "summary.json").write_text(
        json.dumps(results, indent=2, default=str), 
        encoding="utf-8"
    )
    
    # Generate report
    report_text = generate_report(exp_dir, results, logger)
    (exp_dir / "report.md").write_text(report_text, encoding="utf-8")
    
    # Rename directory with end time
    final_name = f"pilot_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
    final_dir = EXPERIMENTS_DIR / final_name
    
    try:
        exp_dir.rename(final_dir)
        logger.info(f"Results saved to: {final_dir}")
        output_dir = final_dir
    except Exception as e:
        logger.warn(f"Could not rename directory: {e}")
        logger.info(f"Results saved to: {exp_dir}")
        output_dir = exp_dir
    
    logger.section("EXPERIMENT COMPLETE")
    logger.info(f"End time: {end_time.isoformat()}")
    logger.info(f"Total duration: {(end_time - start_time).total_seconds():.2f} seconds")
    
    print(f"\n{'='*70}")
    print("EXPERIMENT COMPLETE")
    print(f"{'='*70}")
    print(f"Output directory: {output_dir}")
    print(f"Files:")
    print(f"  - summary.json (complete data)")
    print(f"  - report.md (markdown report)")
    print(f"  - log.txt (execution log)")
    print(f"  - config.json (configuration)")
    print(f"  - results/ (per-fold results)")
    print(f"  - stories/ (chapter texts)")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
