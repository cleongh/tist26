#!/usr/bin/env python3
"""
pilot_experiment.py - Simplified Pilot Experiment for Narrative Evaluation
==========================================================================

This script runs a simplified pilot experiment comparing LLM-based and 
logic-based narrative evaluation. It's designed to work with a single
model at a time (must be started manually) and produces comprehensive reports.

Usage:
1. Start the model server manually (e.g., run gemma.sh or r1_distill_qwen.sh)
2. Run: python scripts/pilot_experiment.py --model-name "Gemma 3 12B"
3. Stop the model, start the other, repeat

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

# Error categories
ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]


def log(msg: str, level: str = "INFO") -> None:
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}", file=sys.stderr)


def categorize_error(error: Dict, source: str) -> str:
    """Determine error category from description."""
    description = error.get("description", "").lower()
    
    # Check for explicit category in LLM response
    if "category" in error:
        cat = error["category"].lower()
        if cat in ERROR_CATEGORIES:
            return cat
            
    # Infer from description keywords
    if any(kw in description for kw in ["cause", "chekhov", "unexplained", "effect", "precondition"]):
        return "causality"
    elif any(kw in description for kw in ["time", "temporal", "before", "after", "duration", "order", "simultaneous"]):
        return "temporal"
    elif any(kw in description for kw in ["location", "place", "ubiquity", "distance", "travel", "spatial", "teleport"]):
        return "location"
    elif any(kw in description for kw in ["emotion", "love", "hate", "fear", "trust", "relationship", "feeling"]):
        return "emotional"
    else:
        return "coherence"


def extract_story_fragments(description: str, story_text: str) -> List[Dict]:
    """Extract relevant story fragments for an error."""
    import re
    fragments = []
    
    # Find quoted text in description
    quoted = re.findall(r'"([^"]{10,})"', description)
    quoted.extend(re.findall(r"'([^']{10,})'", description))
    
    # Find capitalized names
    names = re.findall(r'\b([A-Z][a-z]{2,})\b', description)
    
    # Search for each in story
    for term in quoted[:3]:
        # Direct quote search
        idx = story_text.find(term)
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(story_text), idx + len(term) + 100)
            fragments.append({
                "text": story_text[start:end],
                "match": term,
                "position": idx
            })
            
    for name in names[:2]:
        pattern = re.compile(f".{{0,100}}{re.escape(name)}.{{0,100}}", re.IGNORECASE)
        match = pattern.search(story_text)
        if match:
            fragments.append({
                "text": match.group(0),
                "match": name,
                "position": match.start()
            })
            
    return fragments[:5]


def run_lint(story_text: str, story_path: Path, args) -> Dict:
    """Run both LLM and logic linting on a story."""
    from story_lint import llm_lint, logic_lint
    import argparse as ap
    
    start_time = datetime.now()
    log(f"Processing: {story_path.name}")
    
    # Create args namespace for linting functions
    lint_args = ap.Namespace(
        llm_model="auto",
        llm_base_url="http://localhost:8080/v1",
        llm_api_key="",
        llm_no_auth=True,
        llm_backend="openai",
        llm_temperature=0.0,
        llm_timeout=600,
        llm_max_tokens=4096,
        llm_retries=3,
        llm_backoff=5,
        llm_thinking_budget=0,
        struct_model="auto",
        struct_base_url="http://localhost:8080/v1",
        struct_api_key="",
        struct_no_auth=True,
        struct_backend="openai",
        struct_timeout=600,
        struct_max_tokens=8192,
        struct_retries=5,
        struct_backoff=30,
        struct_thinking_budget=0,
        include_candidates=False,
        mock=False,
        mock_llm=False,
        no_interpret=False,
    )
    
    result = {
        "story_file": str(story_path),
        "story_title": story_path.stem,
        "book": story_path.parent.name,
        "start_time": start_time.isoformat(),
        "llm_errors": [],
        "logic_errors": [],
        "all_errors": [],
        "errors_by_category": {cat: 0 for cat in ERROR_CATEGORIES},
        "errors_by_source": {"llm": 0, "logic": 0},
    }
    
    # Run LLM linting
    try:
        log("  Running LLM lint...")
        llm_start = datetime.now()
        llm_result = llm_lint(story_text, lint_args)
        llm_duration = (datetime.now() - llm_start).total_seconds()
        
        result["llm_raw"] = llm_result
        result["llm_duration_seconds"] = llm_duration
        
        for err in llm_result.get("errors", []):
            category = categorize_error(err, "llm")
            fragments = extract_story_fragments(err.get("description", ""), story_text)
            
            enhanced_error = {
                "id": err.get("id"),
                "source": "llm",
                "category": category,
                "description": err.get("description", ""),
                "story_fragments": err.get("story_fragments", []) or fragments,
                "raw": err,
            }
            result["llm_errors"].append(enhanced_error)
            result["all_errors"].append(enhanced_error)
            result["errors_by_category"][category] += 1
            result["errors_by_source"]["llm"] += 1
            
        log(f"  LLM found {len(result['llm_errors'])} errors in {llm_duration:.1f}s")
        
    except Exception as e:
        log(f"  LLM lint failed: {e}", "ERROR")
        result["llm_error"] = str(e)
        
    # Run logic linting
    try:
        log("  Running logic lint...")
        logic_start = datetime.now()
        logic_result = logic_lint(story_text, lint_args)
        logic_duration = (datetime.now() - logic_start).total_seconds()
        
        result["logic_raw"] = logic_result
        result["logic_duration_seconds"] = logic_duration
        
        for err in logic_result.get("errors", []):
            category = categorize_error(err, "logic")
            fragments = extract_story_fragments(err.get("description", ""), story_text)
            
            enhanced_error = {
                "id": err.get("id"),
                "source": "logic",
                "category": category,
                "description": err.get("description", ""),
                "story_fragments": fragments,
                "raw": err,
            }
            result["logic_errors"].append(enhanced_error)
            result["all_errors"].append(enhanced_error)
            result["errors_by_category"][category] += 1
            result["errors_by_source"]["logic"] += 1
            
        log(f"  Logic found {len(result['logic_errors'])} errors in {logic_duration:.1f}s")
        
    except Exception as e:
        log(f"  Logic lint failed: {e}", "ERROR")
        result["logic_error"] = str(e)
        
    end_time = datetime.now()
    result["end_time"] = end_time.isoformat()
    result["duration_seconds"] = (end_time - start_time).total_seconds()
    result["total_errors"] = len(result["all_errors"])
    
    return result


def filter_false_positives(test_errors: List[Dict], baseline_errors: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Filter false positives based on baseline errors."""
    
    def error_signature(err: Dict) -> str:
        """Create signature for matching."""
        cat = err.get("category", "unknown")
        desc = err.get("description", "").lower()
        # Extract key terms
        import re
        terms = sorted(set(re.findall(r'\b\w{4,}\b', desc)[:5]))
        return f"{cat}:{':'.join(terms)}"
    
    baseline_sigs = {error_signature(e) for result in baseline_errors for e in result.get("all_errors", [])}
    
    filtered = []
    fps = []
    
    for err in test_errors:
        sig = error_signature(err)
        if sig in baseline_sigs:
            fps.append(err)
        else:
            filtered.append(err)
            
    return filtered, fps


class PilotExperiment:
    """Runs a pilot experiment with a single model."""
    
    def __init__(self, model_name: str, output_dir: Path, chapters_per_book: int = 1):
        self.model_name = model_name
        self.chapters_per_book = chapters_per_book
        
        self.start_time = datetime.now()
        self.experiment_id = str(uuid.uuid4())[:8]
        self.start_timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        # Create experiment directory
        self.exp_dir = output_dir / f"pilot_{self.start_timestamp}_{self.experiment_id}"
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        (self.exp_dir / "stories").mkdir(exist_ok=True)
        (self.exp_dir / "results").mkdir(exist_ok=True)
        
        # Data paths
        self.original_dir = REPO_ROOT / "original_books"
        self.modified_dir = REPO_ROOT / "modified_books"
        
        self.results = {
            "experiment_id": self.experiment_id,
            "model_name": model_name,
            "start_time": self.start_time.isoformat(),
            "chapters_per_book": chapters_per_book,
            "books": [],
            "baseline_results": {},
            "test_results": {},
            "fold_results": {},
        }
        
        log(f"Initialized pilot experiment: {self.exp_dir.name}")
        log(f"Model: {model_name}, Chapters per book: {chapters_per_book}")
        
    def discover_books(self) -> List[Dict]:
        """Find all books and their chapters."""
        books = []
        
        for book_dir in sorted(self.original_dir.iterdir()):
            if book_dir.is_dir():
                original = sorted(book_dir.glob("*.txt"))[:self.chapters_per_book]
                modified_dir = self.modified_dir / book_dir.name
                modified = sorted(modified_dir.glob("*.txt"))[:self.chapters_per_book] if modified_dir.exists() else []
                
                books.append({
                    "name": book_dir.name,
                    "original_chapters": [str(c) for c in original],
                    "modified_chapters": [str(c) for c in modified],
                })
                
        self.results["books"] = books
        log(f"Found {len(books)} books")
        return books
        
    def process_book(self, book: Dict, book_type: str) -> List[Dict]:
        """Process all chapters of a book."""
        chapters = book["original_chapters"] if book_type == "original" else book["modified_chapters"]
        results = []
        
        for chapter_path in chapters:
            chapter = Path(chapter_path)
            if not chapter.exists():
                continue
                
            # Copy to experiment folder
            dest = self.exp_dir / "stories" / f"{book['name']}_{book_type}_{chapter.name}"
            shutil.copy2(chapter, dest)
            
            # Process
            story_text = chapter.read_text()
            result = run_lint(story_text, chapter, None)
            result["book"] = book["name"]
            result["book_type"] = book_type
            results.append(result)
            
            # Save individual result
            result_file = self.exp_dir / "results" / f"{book['name']}_{book_type}_{chapter.stem}.json"
            result_file.write_text(json.dumps(result, indent=2, default=str))
            
        return results
        
    def run_kfold(self, books: List[Dict], k: int) -> Dict:
        """Run k-fold cross-validation."""
        from itertools import combinations
        
        n = len(books)
        if k > n:
            return {"error": f"k={k} > n_books={n}"}
            
        fold_results = {
            "k": k,
            "folds": [],
            "aggregated": {
                "total_true_errors": 0,
                "total_false_positives": 0,
                "by_category": {cat: 0 for cat in ERROR_CATEGORIES},
                "by_source": {"llm": 0, "logic": 0},
            }
        }
        
        test_combos = list(combinations(range(n), k))
        
        for fold_idx, test_indices in enumerate(test_combos):
            train_indices = [i for i in range(n) if i not in test_indices]
            
            log(f"Fold {fold_idx+1}/{len(test_combos)}: test={[books[i]['name'] for i in test_indices]}")
            
            # Get baseline from training books
            baseline_errors = []
            for idx in train_indices:
                book = books[idx]
                key = f"{book['name']}_original"
                if key in self.results["baseline_results"]:
                    baseline_errors.extend(self.results["baseline_results"][key])
                    
            # Get test errors
            test_errors = []
            for idx in test_indices:
                book = books[idx]
                key = f"{book['name']}_modified"
                if key in self.results["test_results"]:
                    for result in self.results["test_results"][key]:
                        test_errors.extend(result.get("all_errors", []))
                        
            # Filter false positives
            true_errors, fps = filter_false_positives(test_errors, baseline_errors)
            
            fold_data = {
                "fold_idx": fold_idx,
                "test_books": [books[i]["name"] for i in test_indices],
                "train_books": [books[i]["name"] for i in train_indices],
                "true_errors": len(true_errors),
                "false_positives": len(fps),
                "true_error_list": true_errors,
            }
            fold_results["folds"].append(fold_data)
            
            # Update aggregated
            fold_results["aggregated"]["total_true_errors"] += len(true_errors)
            fold_results["aggregated"]["total_false_positives"] += len(fps)
            
            for err in true_errors:
                cat = err.get("category", "coherence")
                if cat in fold_results["aggregated"]["by_category"]:
                    fold_results["aggregated"]["by_category"][cat] += 1
                src = err.get("source", "llm")
                if src in fold_results["aggregated"]["by_source"]:
                    fold_results["aggregated"]["by_source"][src] += 1
                    
        return fold_results
        
    def run(self) -> Dict:
        """Run the full pilot experiment."""
        log("=" * 60)
        log("STARTING PILOT EXPERIMENT")
        log("=" * 60)
        
        books = self.discover_books()
        
        # Phase 1: Process original books (baseline)
        log("\n--- Phase 1: Processing Original Books (Baseline) ---")
        for book in books:
            log(f"\nProcessing {book['name']} (original)...")
            results = self.process_book(book, "original")
            self.results["baseline_results"][f"{book['name']}_original"] = results
            
        # Phase 2: Process modified books (test)
        log("\n--- Phase 2: Processing Modified Books (Test) ---")
        for book in books:
            log(f"\nProcessing {book['name']} (modified)...")
            results = self.process_book(book, "modified")
            self.results["test_results"][f"{book['name']}_modified"] = results
            
        # Phase 3: K-fold cross-validation
        log("\n--- Phase 3: K-Fold Cross-Validation ---")
        for k in [1, 2, 3, 4]:
            if k <= len(books):
                log(f"\nRunning {k}-fold cross-validation...")
                self.results["fold_results"][str(k)] = self.run_kfold(books, k)
                
        # Finalize
        self.end_time = datetime.now()
        self.results["end_time"] = self.end_time.isoformat()
        self.results["duration_seconds"] = (self.end_time - self.start_time).total_seconds()
        
        # Rename folder with end timestamp
        end_ts = self.end_time.strftime("%Y%m%d_%H%M%S")
        new_name = f"pilot_{self.start_timestamp}-{end_ts}_{self.experiment_id}"
        new_dir = self.exp_dir.parent / new_name
        
        # Save results before rename
        self._save_results()
        self._generate_report()
        
        try:
            self.exp_dir.rename(new_dir)
            self.exp_dir = new_dir
        except Exception as e:
            log(f"Could not rename folder: {e}", "ERROR")
            
        log("\n" + "=" * 60)
        log("EXPERIMENT COMPLETED")
        log(f"Duration: {self.results['duration_seconds']:.2f} seconds")
        log(f"Results: {self.exp_dir}")
        log("=" * 60)
        
        return self.results
        
    def _save_results(self):
        """Save summary results."""
        summary_path = self.exp_dir / "summary.json"
        summary_path.write_text(json.dumps(self.results, indent=2, default=str))
        
    def _generate_report(self):
        """Generate markdown report."""
        report = []
        report.append("# Pilot Experiment Report: Narrative Evaluation")
        report.append("")
        report.append(f"**Experiment ID:** {self.experiment_id}")
        report.append(f"**Model:** {self.model_name}")
        report.append(f"**Start:** {self.start_time.isoformat()}")
        report.append(f"**End:** {self.end_time.isoformat()}")
        report.append(f"**Duration:** {self.results['duration_seconds']:.2f} seconds")
        report.append("")
        
        # Configuration
        report.append("## Configuration")
        report.append("")
        report.append(f"- Chapters per book: {self.chapters_per_book}")
        report.append(f"- Books analyzed: {len(self.results['books'])}")
        report.append("")
        
        # Books table
        report.append("### Books")
        report.append("")
        report.append("| Book | Original Chapters | Modified Chapters |")
        report.append("|------|-------------------|-------------------|")
        for book in self.results["books"]:
            report.append(f"| {book['name']} | {len(book['original_chapters'])} | {len(book['modified_chapters'])} |")
        report.append("")
        
        # Error Categories
        report.append("## Error Categories")
        report.append("")
        report.append("1. **Causality** - Chekhov's gun violations, unexplained effects")
        report.append("2. **Coherence** - Semantic errors, physical impossibilities")
        report.append("3. **Temporal** - Time ordering violations, duration errors")
        report.append("4. **Location** - Ubiquity, impossible travel")
        report.append("5. **Emotional** - Relationship-behavior mismatches")
        report.append("")
        
        # K-fold Results
        report.append("## K-Fold Cross-Validation Results")
        report.append("")
        
        for k_str, k_results in self.results.get("fold_results", {}).items():
            if "error" in k_results:
                continue
                
            agg = k_results.get("aggregated", {})
            report.append(f"### K = {k_str}")
            report.append("")
            report.append(f"- **True Errors Found:** {agg.get('total_true_errors', 0)}")
            report.append(f"- **False Positives Filtered:** {agg.get('total_false_positives', 0)}")
            report.append("")
            
            # By category
            cats = agg.get("by_category", {})
            if cats:
                report.append("**By Category:**")
                report.append("")
                report.append("| Category | Count |")
                report.append("|----------|-------|")
                for cat in ERROR_CATEGORIES:
                    report.append(f"| {cat.capitalize()} | {cats.get(cat, 0)} |")
                report.append("")
                
            # By source
            sources = agg.get("by_source", {})
            if sources:
                report.append("**By Detection Method:**")
                report.append("")
                report.append("| Method | Count |")
                report.append("|--------|-------|")
                report.append(f"| LLM Direct | {sources.get('llm', 0)} |")
                report.append(f"| Logic (ASP) | {sources.get('logic', 0)} |")
                report.append("")
                
        # Detailed error examples
        report.append("## Sample Errors")
        report.append("")
        
        # Get some example errors from test results
        error_examples = []
        for key, results in self.results.get("test_results", {}).items():
            for result in results:
                for err in result.get("all_errors", [])[:2]:  # First 2 per result
                    error_examples.append({
                        "book": result.get("book", "Unknown"),
                        "error": err
                    })
                    
        for i, example in enumerate(error_examples[:10], 1):
            err = example["error"]
            report.append(f"### Error {i}: {err.get('category', 'unknown').capitalize()}")
            report.append("")
            report.append(f"- **Book:** {example['book']}")
            report.append(f"- **Source:** {err.get('source', 'unknown')}")
            report.append(f"- **Description:** {err.get('description', 'N/A')}")
            
            fragments = err.get("story_fragments", [])
            if fragments:
                report.append(f"- **Story Fragment:**")
                report.append(f"  > {fragments[0].get('text', '')[:200]}...")
            report.append("")
            
        # Methodology
        report.append("## Methodology")
        report.append("")
        report.append("### Approach")
        report.append("")
        report.append("This experiment compares two approaches:")
        report.append("")
        report.append("1. **LLM Direct Linting**: Story text is provided to an LLM which identifies inconsistencies using world knowledge and contextual understanding.")
        report.append("")
        report.append("2. **Logic-Based Linting (ASP)**: Story is converted to structured JSON, then to Answer Set Programming facts. Clingo solver applies formal rules.")
        report.append("")
        report.append("### Cross-Validation")
        report.append("")
        report.append("- Original books establish baseline (errors = false positives)")
        report.append("- Modified books contain injected errors (test set)")
        report.append("- Errors in test matching baseline patterns are filtered as false positives")
        report.append("")
        
        # Write report
        report_path = self.exp_dir / "report.md"
        report_path.write_text("\n".join(report))
        log(f"Report saved: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Run pilot narrative evaluation experiment")
    parser.add_argument("--model-name", default="Unknown Model", help="Name of the model being tested")
    parser.add_argument("--chapters-per-book", type=int, default=1, help="Chapters to process per book")
    parser.add_argument("--output-dir", default="experiments", help="Output directory")
    
    args = parser.parse_args()
    
    output_dir = REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    experiment = PilotExperiment(
        model_name=args.model_name,
        output_dir=output_dir,
        chapters_per_book=args.chapters_per_book
    )
    
    results = experiment.run()
    
    # Print summary
    print(json.dumps({
        "experiment_dir": str(experiment.exp_dir),
        "duration_seconds": results["duration_seconds"],
        "total_books": len(results["books"]),
    }, indent=2))


if __name__ == "__main__":
    main()
