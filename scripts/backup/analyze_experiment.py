#!/usr/bin/env python3
"""
analyze_experiment.py - Analyze existing experiment results with k-fold cross-validation
=========================================================================================

This script takes an existing experiment folder (like narrative_eval_ALL-*) and performs
k-fold cross-validation analysis on the results.

It reads errors from:
- llm_results/*.json (LLM-detected errors)
- logic_results/*.json (Logic-detected errors)

And performs k-fold analysis comparing original vs modified books.

Usage:
    python3 scripts/analyze_experiment.py experiments/narrative_eval_ALL-20260124_190952-pending-4d3d305d
"""

import argparse
import json
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Set

# =============================================================================
# CONFIGURATION
# =============================================================================

CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]
BOOKS = ["Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight", "Goosebumps"]

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def log(msg: str, level: str = "INFO"):
    """Print timestamped log message."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", file=sys.stderr)


def compute_error_signature(error: Dict) -> str:
    """Compute signature for error deduplication."""
    category = error.get("category", "unknown").lower()
    desc = error.get("description", "")[:200].lower()
    content = f"{category}:{desc}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def categorize_errors(errors: List[Dict]) -> Dict[str, int]:
    """Count errors by category."""
    counts = {cat: 0 for cat in CATEGORIES}
    for err in errors:
        cat = err.get("category", "coherence").lower()
        if cat in counts:
            counts[cat] += 1
    return counts


def extract_book_from_filename(filename: str) -> str:
    """Extract book name from chapter filename."""
    # Filenames like "Goosebumps_Chapter_000.json", "Harry_Potter_Chapter_001.json"
    name = filename.replace(".json", "").replace(".txt", "")
    
    # Try to match book patterns
    for book in BOOKS:
        book_pattern = book.replace(" ", "_")
        if name.startswith(book_pattern):
            return book
        # Also try without underscores
        if name.lower().startswith(book.lower().replace(" ", "")):
            return book
    
    # Fallback: extract before _Chapter_ or first underscore
    if "_Chapter_" in name:
        return name.split("_Chapter_")[0].replace("_", " ")
    if "_" in name:
        return name.rsplit("_", 1)[0].replace("_", " ")
    
    return name


def extract_chapter_from_filename(filename: str) -> str:
    """Extract chapter ID from filename."""
    name = filename.replace(".json", "").replace(".txt", "")
    
    # Match patterns like "Chapter_000", "_000", etc.
    match = re.search(r'Chapter_(\d+)', name)
    if match:
        return match.group(1)
    
    match = re.search(r'_(\d+)$', name)
    if match:
        return match.group(1)
    
    return "000"


# =============================================================================
# LOAD EXPERIMENT RESULTS
# =============================================================================

def load_experiment_results(exp_dir: Path) -> Dict[str, Any]:
    """Load all results from an experiment directory."""
    llm_dir = exp_dir / "llm_results"
    logic_dir = exp_dir / "logic_results"
    
    results = {
        "llm": {},
        "logic": {},
        "books": set(),
        "chapters": []
    }
    
    # Load LLM results
    if llm_dir.exists():
        for f in sorted(llm_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                book = extract_book_from_filename(f.name)
                chapter = extract_chapter_from_filename(f.name)
                key = f"{book}/{chapter}"
                
                results["llm"][key] = {
                    "filename": f.name,
                    "book": book,
                    "chapter": chapter,
                    "error_count": data.get("error_count", 0),
                    "errors": data.get("errors", []),
                    "title": data.get("story_title", f.stem),
                    "meta": data.get("_meta", {})
                }
                results["books"].add(book)
                
            except Exception as e:
                log(f"Failed to load {f}: {e}", "ERROR")
    
    # Load Logic results  
    if logic_dir.exists():
        for f in sorted(logic_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                book = extract_book_from_filename(f.name)
                chapter = extract_chapter_from_filename(f.name)
                key = f"{book}/{chapter}"
                
                results["logic"][key] = {
                    "filename": f.name,
                    "book": book,
                    "chapter": chapter,
                    "error_count": data.get("error_count", 0),
                    "errors": data.get("errors", []),
                    "meta": data.get("_meta", {})
                }
                results["books"].add(book)
                
            except Exception as e:
                log(f"Failed to load {f}: {e}", "ERROR")
    
    results["books"] = sorted(results["books"])
    
    # Build chapter list
    all_keys = set(results["llm"].keys()) | set(results["logic"].keys())
    for key in sorted(all_keys):
        parts = key.split("/")
        results["chapters"].append({
            "key": key,
            "book": parts[0] if len(parts) > 0 else "Unknown",
            "chapter": parts[1] if len(parts) > 1 else "000"
        })
    
    return results


# =============================================================================
# K-FOLD ANALYSIS
# =============================================================================

def run_kfold_analysis(
    results: Dict,
    k: int,
    original_books: List[str],
    modified_books: List[str]
) -> Dict[str, Any]:
    """
    Run k-fold cross-validation analysis.
    
    Since we can't re-run the experiment, we simulate k-fold by:
    - Using original book results as "baseline" (false positives)
    - Using modified book results as "test" (true + false positives)
    - Filtering test results using baseline signatures
    """
    books = sorted(set(original_books) & set(modified_books))
    n_books = len(books)
    fold_size = max(1, n_books // k) if k > 0 else n_books
    
    fold_results = []
    
    for fold_idx in range(k):
        # Split books
        test_start = fold_idx * fold_size
        test_end = min(test_start + fold_size, n_books)
        test_books = books[test_start:test_end]
        train_books = books[:test_start] + books[test_end:]
        
        if not train_books:
            train_books = [b for b in books if b not in test_books]
            if not train_books:
                train_books = test_books
        
        # Collect baseline signatures from train books (original)
        baseline_sigs_llm = set()
        baseline_sigs_logic = set()
        baseline_llm_total = 0
        baseline_logic_total = 0
        
        for key, data in results["llm"].items():
            if data["book"] in train_books:
                for err in data.get("errors", []):
                    sig = compute_error_signature(err)
                    baseline_sigs_llm.add(sig)
                    baseline_llm_total += 1
        
        for key, data in results["logic"].items():
            if data["book"] in train_books:
                for err in data.get("errors", []):
                    sig = compute_error_signature(err)
                    baseline_sigs_logic.add(sig)
                    baseline_logic_total += 1
        
        # Process test books (modified) - filter using baseline
        test_chapters = []
        llm_tp_total = 0
        logic_tp_total = 0
        
        for key, data in results["llm"].items():
            if data["book"] in test_books:
                errors = data.get("errors", [])
                tp = [e for e in errors if compute_error_signature(e) not in baseline_sigs_llm]
                fp = len(errors) - len(tp)
                
                llm_tp_total += len(tp)
                
                # Get corresponding logic data
                logic_data = results["logic"].get(key, {})
                logic_errors = logic_data.get("errors", [])
                logic_tp = [e for e in logic_errors if compute_error_signature(e) not in baseline_sigs_logic]
                logic_fp = len(logic_errors) - len(logic_tp)
                
                logic_tp_total += len(logic_tp)
                
                test_chapters.append({
                    "key": key,
                    "book": data["book"],
                    "chapter": data["chapter"],
                    "title": data.get("title", ""),
                    "llm": {
                        "total": len(errors),
                        "true_positives": len(tp),
                        "false_positives": fp,
                        "errors": tp,
                        "by_category": categorize_errors(tp)
                    },
                    "logic": {
                        "total": len(logic_errors),
                        "true_positives": len(logic_tp),
                        "false_positives": logic_fp,
                        "errors": logic_tp,
                        "by_category": categorize_errors(logic_tp)
                    }
                })
        
        fold_results.append({
            "fold": fold_idx + 1,
            "k": k,
            "train_books": train_books,
            "test_books": test_books,
            "baseline": {
                "llm_signatures": len(baseline_sigs_llm),
                "logic_signatures": len(baseline_sigs_logic),
                "llm_total_errors": baseline_llm_total,
                "logic_total_errors": baseline_logic_total
            },
            "test": {
                "llm_true_positives": llm_tp_total,
                "logic_true_positives": logic_tp_total,
                "chapters": test_chapters
            }
        })
    
    # Aggregate
    llm_totals = [f["test"]["llm_true_positives"] for f in fold_results]
    logic_totals = [f["test"]["logic_true_positives"] for f in fold_results]
    
    return {
        "k": k,
        "fold_results": fold_results,
        "aggregate": {
            "llm_mean": sum(llm_totals) / len(llm_totals) if llm_totals else 0,
            "llm_total": sum(llm_totals),
            "logic_mean": sum(logic_totals) / len(logic_totals) if logic_totals else 0,
            "logic_total": sum(logic_totals)
        }
    }


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report(analysis: Dict, output_dir: Path) -> str:
    """Generate comprehensive markdown report."""
    r = []
    r.append("# Narrative Evaluation Analysis Report\n")
    r.append(f"**Generated:** {datetime.now().isoformat()}\n")
    r.append(f"**Source:** {analysis.get('source_experiment', 'Unknown')}\n")
    
    # Summary
    r.append("\n## Summary\n")
    r.append(f"- Books analyzed: {', '.join(analysis.get('books', []))}\n")
    r.append(f"- Total chapters: {analysis.get('total_chapters', 0)}\n")
    r.append(f"- Total LLM errors: {analysis.get('total_llm_errors', 0)}\n")
    r.append(f"- Total Logic errors: {analysis.get('total_logic_errors', 0)}\n")
    
    # K-fold results
    r.append("\n## K-Fold Cross-Validation Results\n")
    
    for k_result in analysis.get("k_fold_results", []):
        k = k_result["k"]
        agg = k_result.get("aggregate", {})
        
        r.append(f"\n### K={k}\n")
        r.append(f"- **LLM True Positives (Total):** {agg.get('llm_total', 0)}\n")
        r.append(f"- **LLM True Positives (Mean):** {agg.get('llm_mean', 0):.2f}\n")
        r.append(f"- **Logic True Positives (Total):** {agg.get('logic_total', 0)}\n")
        r.append(f"- **Logic True Positives (Mean):** {agg.get('logic_mean', 0):.2f}\n")
        
        r.append("\n| Fold | Train | Test | Baseline LLM | Baseline Logic | LLM TP | Logic TP |\n")
        r.append("|------|-------|------|--------------|----------------|--------|----------|\n")
        
        for fold in k_result.get("fold_results", []):
            train = ", ".join(b[:10] for b in fold["train_books"])
            test = ", ".join(b[:10] for b in fold["test_books"])
            bl = fold["baseline"]
            t = fold["test"]
            r.append(f"| {fold['fold']} | {train} | {test} | {bl['llm_total_errors']} | {bl['logic_total_errors']} | {t['llm_true_positives']} | {t['logic_true_positives']} |\n")
    
    # Category breakdown
    r.append("\n## Errors by Category\n")
    
    llm_cats = {cat: 0 for cat in CATEGORIES}
    logic_cats = {cat: 0 for cat in CATEGORIES}
    
    for k_result in analysis.get("k_fold_results", []):
        for fold in k_result.get("fold_results", []):
            for ch in fold.get("test", {}).get("chapters", []):
                for cat in CATEGORIES:
                    llm_cats[cat] += ch["llm"]["by_category"].get(cat, 0)
                    logic_cats[cat] += ch["logic"]["by_category"].get(cat, 0)
    
    r.append("| Category | LLM TP | Logic TP | Total |\n")
    r.append("|----------|--------|----------|-------|\n")
    for cat in CATEGORIES:
        total = llm_cats[cat] + logic_cats[cat]
        r.append(f"| {cat.capitalize()} | {llm_cats[cat]} | {logic_cats[cat]} | {total} |\n")
    
    # Sample errors
    r.append("\n## Sample Errors\n")
    
    sample_count = 0
    max_samples = 20
    
    for k_result in analysis.get("k_fold_results", []):
        if sample_count >= max_samples:
            break
        for fold in k_result.get("fold_results", []):
            if sample_count >= max_samples:
                break
            for ch in fold.get("test", {}).get("chapters", []):
                if sample_count >= max_samples:
                    break
                
                for err in ch["llm"]["errors"][:2]:
                    if sample_count >= max_samples:
                        break
                    r.append(f"\n### {ch['book']} / Chapter {ch['chapter']} (LLM - {err.get('category', 'unknown')})\n")
                    r.append(f"**Description:** {err.get('description', 'No description')[:500]}\n\n")
                    if err.get("story_fragment"):
                        r.append(f"**Fragment:** {err['story_fragment'][:300]}...\n\n")
                    sample_count += 1
                
                for err in ch["logic"]["errors"][:2]:
                    if sample_count >= max_samples:
                        break
                    r.append(f"\n### {ch['book']} / Chapter {ch['chapter']} (Logic - {err.get('category', 'unknown')})\n")
                    r.append(f"**Type:** {err.get('type', 'unknown')}\n")
                    r.append(f"**Description:** {err.get('description', 'No description')[:500]}\n\n")
                    sample_count += 1
    
    return "".join(r)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Analyze existing experiment results")
    parser.add_argument("experiment_dir", help="Path to experiment directory")
    parser.add_argument("--k-values", default="1,2,3,4", help="K values for cross-validation")
    parser.add_argument("--output", default=None, help="Output directory (default: same as input)")
    
    args = parser.parse_args()
    
    exp_dir = Path(args.experiment_dir)
    if not exp_dir.exists():
        print(f"Error: Directory not found: {exp_dir}", file=sys.stderr)
        sys.exit(1)
    
    output_dir = Path(args.output) if args.output else exp_dir
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    
    log(f"Analyzing experiment: {exp_dir}")
    log(f"K values: {k_values}")
    
    # Load results
    log("Loading experiment results...")
    results = load_experiment_results(exp_dir)
    
    log(f"Found {len(results['llm'])} LLM results")
    log(f"Found {len(results['logic'])} Logic results")
    log(f"Books: {results['books']}")
    
    # Count total errors
    total_llm = sum(d["error_count"] for d in results["llm"].values())
    total_logic = sum(d["error_count"] for d in results["logic"].values())
    
    log(f"Total LLM errors: {total_llm}")
    log(f"Total Logic errors: {total_logic}")
    
    # Run k-fold analysis
    log("Running k-fold analysis...")
    k_fold_results = []
    
    for k in k_values:
        log(f"  K={k}...")
        k_result = run_kfold_analysis(
            results=results,
            k=k,
            original_books=results["books"],
            modified_books=results["books"]
        )
        k_fold_results.append(k_result)
        
        agg = k_result["aggregate"]
        log(f"    LLM TP total: {agg['llm_total']}, mean: {agg['llm_mean']:.2f}")
        log(f"    Logic TP total: {agg['logic_total']}, mean: {agg['logic_mean']:.2f}")
    
    # Build analysis result
    analysis = {
        "source_experiment": str(exp_dir),
        "analysis_time": datetime.now().isoformat(),
        "books": results["books"],
        "total_chapters": len(results["chapters"]),
        "total_llm_errors": total_llm,
        "total_logic_errors": total_logic,
        "k_fold_results": k_fold_results
    }
    
    # Generate report
    log("Generating report...")
    report = generate_report(analysis, output_dir)
    
    # Save outputs
    report_path = output_dir / "kfold_analysis_report.md"
    report_path.write_text(report, encoding="utf-8")
    log(f"Report saved to: {report_path}")
    
    results_path = output_dir / "kfold_analysis_results.json"
    results_path.write_text(json.dumps(analysis, indent=2, default=str), encoding="utf-8")
    log(f"Results saved to: {results_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Source: {exp_dir}")
    print(f"Total LLM errors: {total_llm}")
    print(f"Total Logic errors: {total_logic}")
    print()
    print("K-Fold Results:")
    for k_result in k_fold_results:
        k = k_result["k"]
        agg = k_result["aggregate"]
        print(f"  K={k}: LLM TP={agg['llm_total']}, Logic TP={agg['logic_total']}")
    print()
    print(f"Report: {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
