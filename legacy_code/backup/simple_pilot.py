#!/usr/bin/env python3
"""
simple_pilot.py - Simple Pilot Experiment Runner
=================================================

A streamlined version of the experiment that:
1. Starts a model server manually (you need to do this before running)
2. Processes chapters from each book
3. Generates reports

Usage:
    # First, start your model server manually:
    $ /home/cleon/programas/gemma.sh &
    
    # Wait for it to start (~30 seconds), then run:
    $ python3 scripts/simple_pilot.py --model-name "gemma_3_12b"
    
    # When done, kill the server and start the next one:
    $ pkill -f llamafile
    $ /home/cleon/programas/r1_distill_qwen.sh &
    
    # Then run again:
    $ python3 scripts/simple_pilot.py --model-name "r1_distill_qwen"
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Configuration
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
ORIGINAL_BOOKS_DIR = REPO_ROOT / "original_books"
MODIFIED_BOOKS_DIR = REPO_ROOT / "modified_books"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]
BOOKS = ["Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight", "Goosebumps"]


def log(message: str, log_file: Path = None):
    """Log with timestamp."""
    timestamp = datetime.now().isoformat()
    formatted = f"[{timestamp}] {message}"
    print(formatted, file=sys.stderr)
    if log_file:
        with open(log_file, "a") as f:
            f.write(formatted + "\n")


def load_chapters(book_dir: Path, max_chapters: int = 2) -> List[Tuple[str, str, str]]:
    """Load chapters from a book directory."""
    chapters = []
    files = sorted(book_dir.glob("*.txt"))[:max_chapters]
    
    for f in files:
        chapter_id = f.stem
        text = f.read_text(encoding="utf-8", errors="replace")
        lines = text.strip().split('\n')
        title = lines[0].strip() if lines else chapter_id
        chapters.append((chapter_id, title, text))
    
    return chapters


def run_lint(story_text: str, timeout: int = 600) -> Dict[str, Any]:
    """Run story_lint.py on a story."""
    import tempfile
    
    start = datetime.now()
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(story_text)
        story_path = f.name
    
    try:
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "story_lint.py"),
            "--mode", "both",
            "--llm-model", "auto",
            "--llm-base-url", "http://localhost:8080/v1",
            "--llm-no-auth",
            "--struct-model", "auto", 
            "--struct-base-url", "http://localhost:8080/v1",
            "--struct-no-auth",
            "--llm-timeout", str(timeout),
            "--struct-timeout", str(timeout),
            story_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * 3,
            cwd=str(REPO_ROOT)
        )
        
        end = datetime.now()
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr[:1000],
                "duration": (end - start).total_seconds()
            }
        
        try:
            output = json.loads(result.stdout)
            output["success"] = True
            output["duration"] = (end - start).total_seconds()
            return output
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "JSON parse error",
                "stdout": result.stdout[:1000],
                "duration": (end - start).total_seconds()
            }
            
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout", "duration": timeout * 3}
    finally:
        os.unlink(story_path)


def extract_errors(result: Dict, source: str) -> List[Dict]:
    """Extract errors from lint result."""
    errors = []
    
    if not result.get("success"):
        return errors
    
    key = f"{source}_lint"
    if key not in result:
        return errors
    
    for err in result[key].get("errors", []):
        category = err.get("category", "coherence").lower()
        if category not in ERROR_CATEGORIES:
            category = "coherence"
        
        errors.append({
            "source": source,
            "category": category,
            "description": err.get("description", ""),
            "story_fragments": err.get("story_fragments", []),
            "raw": err
        })
    
    return errors


def categorize_counts(errors: List[Dict]) -> Dict[str, int]:
    """Count errors by category."""
    counts = {cat: 0 for cat in ERROR_CATEGORIES}
    for err in errors:
        cat = err.get("category", "coherence")
        if cat in counts:
            counts[cat] += 1
    return counts


def run_experiment(
    model_name: str,
    chapters_per_book: int,
    k_values: List[int],
    timeout: int,
    log_file: Path
) -> Dict[str, Any]:
    """Run the full experiment."""
    
    log(f"Starting experiment with model: {model_name}", log_file)
    experiment_start = datetime.now()
    
    results = {
        "model": model_name,
        "start_time": experiment_start.isoformat(),
        "chapters_per_book": chapters_per_book,
        "k_values": k_values,
        "k_fold_results": []
    }
    
    for k in k_values:
        log(f"\n=== K-Fold: k={k} ===", log_file)
        k_result = {"k": k, "folds": []}
        
        n_books = len(BOOKS)
        fold_size = max(1, n_books // k) if k > 0 else n_books
        
        for fold_idx in range(k):
            log(f"\n--- Fold {fold_idx + 1}/{k} ---", log_file)
            fold_start = datetime.now()
            
            # Split books
            test_start = fold_idx * fold_size
            test_end = min(test_start + fold_size, n_books)
            test_books = BOOKS[test_start:test_end]
            train_books = BOOKS[:test_start] + BOOKS[test_end:]
            if not train_books:
                train_books = test_books
            
            log(f"Train: {train_books}", log_file)
            log(f"Test: {test_books}", log_file)
            
            # Phase 1: Baseline (original books)
            log("Phase 1: Collecting baseline from original books...", log_file)
            baseline_errors = []
            
            for book in train_books:
                book_dir = ORIGINAL_BOOKS_DIR / book
                if not book_dir.exists():
                    log(f"  SKIP: {book} not found", log_file)
                    continue
                
                chapters = load_chapters(book_dir, chapters_per_book)
                for ch_id, ch_title, ch_text in chapters:
                    log(f"  Baseline: {book}/{ch_id}", log_file)
                    result = run_lint(ch_text, timeout)
                    baseline_errors.extend(extract_errors(result, "llm"))
                    baseline_errors.extend(extract_errors(result, "logic"))
            
            baseline_sigs = set(f"{e['category']}:{e['description'][:50]}" for e in baseline_errors)
            log(f"  Baseline: {len(baseline_sigs)} unique error signatures", log_file)
            
            # Phase 2: Test (modified books)
            log("Phase 2: Testing on modified books...", log_file)
            test_results = []
            
            for book in test_books:
                book_dir = MODIFIED_BOOKS_DIR / book
                if not book_dir.exists():
                    log(f"  SKIP: {book} not found", log_file)
                    continue
                
                chapters = load_chapters(book_dir, chapters_per_book)
                for ch_id, ch_title, ch_text in chapters:
                    log(f"  Testing: {book}/{ch_id}", log_file)
                    ch_start = datetime.now()
                    
                    result = run_lint(ch_text, timeout)
                    
                    llm_errors = extract_errors(result, "llm")
                    logic_errors = extract_errors(result, "logic")
                    
                    # Filter false positives
                    llm_tp = [e for e in llm_errors 
                             if f"{e['category']}:{e['description'][:50]}" not in baseline_sigs]
                    logic_tp = [e for e in logic_errors 
                               if f"{e['category']}:{e['description'][:50]}" not in baseline_sigs]
                    
                    ch_result = {
                        "book": book,
                        "chapter_id": ch_id,
                        "chapter_title": ch_title,
                        "duration": (datetime.now() - ch_start).total_seconds(),
                        "llm_errors": len(llm_tp),
                        "logic_errors": len(logic_tp),
                        "llm_by_category": categorize_counts(llm_tp),
                        "logic_by_category": categorize_counts(logic_tp),
                        "llm_details": llm_tp,
                        "logic_details": logic_tp,
                        "raw_result": result
                    }
                    test_results.append(ch_result)
                    
                    log(f"    LLM: {len(llm_tp)} errors, Logic: {len(logic_tp)} errors", log_file)
            
            fold_end = datetime.now()
            
            # Aggregate fold results
            fold_llm_total = sum(r["llm_errors"] for r in test_results)
            fold_logic_total = sum(r["logic_errors"] for r in test_results)
            
            fold_result = {
                "fold": fold_idx + 1,
                "train_books": train_books,
                "test_books": test_books,
                "duration": (fold_end - fold_start).total_seconds(),
                "llm_total": fold_llm_total,
                "logic_total": fold_logic_total,
                "test_results": test_results
            }
            k_result["folds"].append(fold_result)
            
            log(f"Fold {fold_idx + 1} complete: LLM={fold_llm_total}, Logic={fold_logic_total}", log_file)
        
        # Aggregate k results
        k_result["llm_mean"] = sum(f["llm_total"] for f in k_result["folds"]) / len(k_result["folds"]) if k_result["folds"] else 0
        k_result["logic_mean"] = sum(f["logic_total"] for f in k_result["folds"]) / len(k_result["folds"]) if k_result["folds"] else 0
        
        results["k_fold_results"].append(k_result)
    
    experiment_end = datetime.now()
    results["end_time"] = experiment_end.isoformat()
    results["total_duration"] = (experiment_end - experiment_start).total_seconds()
    
    return results


def generate_report(results: Dict, output_dir: Path) -> str:
    """Generate markdown report."""
    
    report = []
    report.append("# Narrative Evaluation Pilot Experiment Report\n")
    report.append(f"\n**Model**: {results['model']}\n")
    report.append(f"**Generated**: {datetime.now().isoformat()}\n")
    report.append(f"**Start Time**: {results['start_time']}\n")
    report.append(f"**End Time**: {results['end_time']}\n")
    report.append(f"**Total Duration**: {results['total_duration']:.2f} seconds\n")
    
    report.append("\n## Error Categories\n")
    report.append("| Category | Description |\n")
    report.append("|----------|-------------|\n")
    report.append("| Causality | Chekhov's gun, causal chains |\n")
    report.append("| Coherence | Semantic correctness |\n")
    report.append("| Temporal | Time ordering violations |\n")
    report.append("| Location | Spatial constraints |\n")
    report.append("| Emotional | Character behavior |\n")
    
    report.append("\n## Results by K-Fold\n")
    
    for k_result in results["k_fold_results"]:
        k = k_result["k"]
        report.append(f"\n### K={k} Cross-Validation\n")
        report.append(f"- **LLM Mean Errors**: {k_result['llm_mean']:.2f}\n")
        report.append(f"- **Logic Mean Errors**: {k_result['logic_mean']:.2f}\n")
        
        report.append("\n| Fold | LLM | Logic | Duration (s) |\n")
        report.append("|------|-----|-------|-------------|\n")
        
        for fold in k_result["folds"]:
            report.append(f"| {fold['fold']} | {fold['llm_total']} | {fold['logic_total']} | {fold['duration']:.1f} |\n")
    
    # Category breakdown
    report.append("\n## Errors by Category\n")
    
    llm_cats = {cat: 0 for cat in ERROR_CATEGORIES}
    logic_cats = {cat: 0 for cat in ERROR_CATEGORIES}
    
    for k_result in results["k_fold_results"]:
        for fold in k_result["folds"]:
            for test in fold["test_results"]:
                for cat in ERROR_CATEGORIES:
                    llm_cats[cat] += test["llm_by_category"].get(cat, 0)
                    logic_cats[cat] += test["logic_by_category"].get(cat, 0)
    
    report.append("\n| Category | LLM | Logic |\n")
    report.append("|----------|-----|-------|\n")
    for cat in ERROR_CATEGORIES:
        report.append(f"| {cat.capitalize()} | {llm_cats[cat]} | {logic_cats[cat]} |\n")
    
    # Sample errors
    report.append("\n## Sample Errors\n")
    
    sample_count = 0
    for k_result in results["k_fold_results"]:
        for fold in k_result["folds"]:
            for test in fold["test_results"]:
                for err in test["llm_details"][:2]:
                    if sample_count >= 10:
                        break
                    report.append(f"\n### Error {sample_count + 1} (LLM - {err['category']})\n")
                    report.append(f"**Book**: {test['book']}, **Chapter**: {test['chapter_id']}\n\n")
                    report.append(f"**Description**: {err['description']}\n\n")
                    if err.get("story_fragments"):
                        report.append("**Story Fragment**:\n")
                        for frag in err["story_fragments"][:1]:
                            report.append(f"> {frag[:300]}...\n\n")
                    sample_count += 1
                
                for err in test["logic_details"][:2]:
                    if sample_count >= 10:
                        break
                    report.append(f"\n### Error {sample_count + 1} (Logic - {err['category']})\n")
                    report.append(f"**Book**: {test['book']}, **Chapter**: {test['chapter_id']}\n\n")
                    report.append(f"**Description**: {err['description']}\n\n")
                    sample_count += 1
    
    return "".join(report)


def main():
    parser = argparse.ArgumentParser(description="Simple pilot experiment")
    parser.add_argument("--model-name", required=True, help="Name for this model run")
    parser.add_argument("--chapters-per-book", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--k-values", default="1,2,3,4")
    
    args = parser.parse_args()
    
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    
    # Create experiment directory
    exp_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    exp_dir = EXPERIMENTS_DIR / f"pilot_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = exp_dir / "log.txt"
    
    log(f"Experiment directory: {exp_dir}", log_file)
    log(f"Model: {args.model_name}", log_file)
    log(f"K values: {k_values}", log_file)
    
    # Run experiment
    results = run_experiment(
        model_name=args.model_name,
        chapters_per_book=args.chapters_per_book,
        k_values=k_values,
        timeout=args.timeout,
        log_file=log_file
    )
    
    # Save results
    (exp_dir / "summary.json").write_text(json.dumps(results, indent=2))
    
    # Generate report
    report_text = generate_report(results, exp_dir)
    (exp_dir / "report.md").write_text(report_text)
    
    # Rename with end time
    end_time = datetime.now()
    final_name = f"pilot_{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
    final_dir = EXPERIMENTS_DIR / final_name
    
    try:
        exp_dir.rename(final_dir)
        log(f"Results saved to: {final_dir}", log_file)
    except:
        log(f"Results saved to: {exp_dir}", log_file)
    
    print(f"\n\nExperiment complete!")
    print(f"Results: {final_dir if final_dir.exists() else exp_dir}")


if __name__ == "__main__":
    main()
