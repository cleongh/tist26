#!/usr/bin/env python3
"""
run_ilasp_kfold_experiment.py - K-Fold Experiment with ILASP and Guidance
==========================================================================

This script implements a k-fold cross-validation experiment comparing:
1. LLM-based evaluation (using guidance library)
2. Logic-based evaluation (using ILASP)

Key differences from the original experiment:
- Uses ILASP for inductive logic programming (not just Clingo)
- Uses guidance library for constrained LLM output
- Temperature = 0 for deterministic results
- Targets "modified, one chapter only" subfolder

EXPERIMENT DESIGN:
------------------
1. CALIBRATION: Process original chapters to identify false positives
2. TESTING: Process modified chapters to detect actual errors
3. K-FOLD: Aggregate results using k=1 to 4 folds
4. COMPARISON: Compare guidance-LLM vs ILASP approaches

ERROR CATEGORIES (5 types):
---------------------------
1. CAUSALITY - Chekhov's gun violations, unexplained effects
2. COHERENCE - Semantic errors, dead agents acting
3. TEMPORAL - Time ordering violations
4. LOCATION - Ubiquity, impossible travel
5. EMOTIONAL - Relationship-behavior mismatches

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

# Import our ILASP evaluator module
from ilasp_evaluator import (
    ilasp_lint,
    guidance_llm_lint,
    ILASPEvaluator,
    GuidanceLLM,
    StoryStructure,
    ERROR_CATEGORIES,
    GUIDANCE_AVAILABLE,
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Default paths
REPO_ROOT = SCRIPT_DIR.parent
ONE_CHAPTER_DIR = REPO_ROOT / "modified, one chapter only"
ORIGINAL_BOOKS_DIR = ONE_CHAPTER_DIR / "original_books"
MODIFIED_BOOKS_DIR = ONE_CHAPTER_DIR / "modified_books"

# Book metadata matching the "one chapter only" structure
BOOK_METADATA = {
    "Goosebumps": {
        "full_title": "Goosebumps: Welcome to Dead House",
        "author": "R.L. Stine",
        "chapter_file": "029.txt"
    },
    "Harry Potter": {
        "full_title": "Harry Potter and the Prisoner of Azkaban",
        "author": "J.K. Rowling",
        "chapter_file": "055.txt"
    },
    "The Hunger Games": {
        "full_title": "The Hunger Games",
        "author": "Suzanne Collins",
        "chapter_file": "035.txt"
    },
    "The Lord of the Rings": {
        "full_title": "The Lord of the Rings: The Fellowship of the Ring",
        "author": "J.R.R. Tolkien",
        "chapter_file": "016.txt"
    },
    "Twilight": {
        "full_title": "Twilight",
        "author": "Stephenie Meyer",
        "chapter_file": "051.txt"
    }
}


# =============================================================================
# LOGGING
# =============================================================================

class Logger:
    """Simple timestamped logger."""
    
    def __init__(self, log_file: Optional[Path] = None):
        self.log_file = log_file
        self.start_time = datetime.now()
        
    def log(self, msg: str, level: str = "INFO"):
        now = datetime.now()
        elapsed = (now - self.start_time).total_seconds()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] [{level}] [{elapsed:.1f}s] {msg}"
        
        print(formatted, file=sys.stderr)
        
        if self.log_file:
            with open(self.log_file, "a") as f:
                f.write(formatted + "\n")
                
    def info(self, msg: str):
        self.log(msg, "INFO")
        
    def warn(self, msg: str):
        self.log(msg, "WARN")
        
    def error(self, msg: str):
        self.log(msg, "ERROR")
        
    def section(self, title: str):
        self.log("=" * 60)
        self.log(title)
        self.log("=" * 60)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ChapterResult:
    """Result for a single chapter evaluation."""
    
    def __init__(self, book_name: str, chapter_file: str, is_modified: bool):
        self.book_name = book_name
        self.chapter_file = chapter_file
        self.is_modified = is_modified
        self.story_text = ""
        self.story_path = ""
        
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # Results from each approach
        self.llm_result: Dict[str, Any] = {}
        self.ilasp_result: Dict[str, Any] = {}
        
        # Errors by category
        self.llm_errors: Dict[str, List[Dict]] = {cat: [] for cat in ERROR_CATEGORIES}
        self.ilasp_errors: Dict[str, List[Dict]] = {cat: [] for cat in ERROR_CATEGORIES}
        
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "book_name": self.book_name,
            "chapter_file": self.chapter_file,
            "is_modified": self.is_modified,
            "story_path": self.story_path,
            "story_length": len(self.story_text),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds(),
            "llm_result": self.llm_result,
            "ilasp_result": self.ilasp_result,
            "llm_errors": self.llm_errors,
            "ilasp_errors": self.ilasp_errors,
            "llm_total": sum(len(v) for v in self.llm_errors.values()),
            "ilasp_total": sum(len(v) for v in self.ilasp_errors.values()),
        }


def categorize_error(error: Dict[str, Any]) -> str:
    """Determine error category."""
    if "category" in error:
        cat = error["category"].lower()
        if cat in ERROR_CATEGORIES:
            return cat
    
    # Infer from content
    desc = str(error.get("description", "")).lower()
    vtype = str(error.get("violation_type", "")).lower()
    
    if any(kw in desc or kw in vtype for kw in ["cause", "chekhov", "effect"]):
        return "causality"
    if any(kw in desc or kw in vtype for kw in ["time", "temporal", "duration", "order"]):
        return "temporal"
    if any(kw in desc or kw in vtype for kw in ["location", "ubiquity", "place", "travel"]):
        return "location"
    if any(kw in desc or kw in vtype for kw in ["emotion", "feel", "love", "hate", "relationship"]):
        return "emotional"
    
    return "coherence"


def generate_kfold_splits(books: List[str], k: int) -> List[Tuple[List[str], List[str]]]:
    """Generate k-fold cross-validation splits."""
    if k <= 0 or k > len(books):
        k = len(books)
    
    n = len(books)
    fold_size = n // k
    remainder = n % k
    
    splits = []
    indices = list(range(n))
    
    start = 0
    for i in range(k):
        size = fold_size + (1 if i < remainder else 0)
        test_indices = indices[start:start + size]
        train_indices = indices[:start] + indices[start + size:]
        
        test_books = [books[j] for j in test_indices]
        train_books = [books[j] for j in train_indices]
        
        splits.append((train_books, test_books))
        start += size
    
    return splits


# =============================================================================
# EXPERIMENT RUNNER
# =============================================================================

class ILASPExperiment:
    """
    K-fold experiment comparing guidance-LLM vs ILASP evaluation.
    """
    
    def __init__(self, args, logger: Logger):
        self.args = args
        self.logger = logger
        self.start_time = datetime.now()
        self.experiment_id = str(uuid.uuid4())[:8]
        
        # Paths - use "modified, one chapter only" subdirectories
        self.original_books_dir = ORIGINAL_BOOKS_DIR
        self.modified_books_dir = MODIFIED_BOOKS_DIR
        
        if not self.original_books_dir.exists():
            raise FileNotFoundError(f"Original books directory not found: {self.original_books_dir}")
        if not self.modified_books_dir.exists():
            raise FileNotFoundError(f"Modified books directory not found: {self.modified_books_dir}")
        
        # Results storage
        self.original_results: List[ChapterResult] = []
        self.modified_results: List[ChapterResult] = []
        self.kfold_results: Dict[int, Dict] = {}
        
        # Create output directory
        self.output_dir = self._create_output_dir()
        
        # Initialize evaluators
        self.llm = None
        self.ilasp = None
        self._init_evaluators()
        
    def _create_output_dir(self) -> Path:
        """Create experiment output directory."""
        start_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        dir_name = f"ilasp_kfold-{start_str}-pending-{self.experiment_id}"
        output_dir = REPO_ROOT / "experiments" / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        (output_dir / "results").mkdir(exist_ok=True)
        (output_dir / "logs").mkdir(exist_ok=True)
        
        self.logger.log_file = output_dir / "logs" / "experiment.log"
        self.logger.info(f"Created output directory: {output_dir}")
        
        return output_dir
    
    def _finalize_output_dir(self):
        """Rename directory with end timestamp."""
        end_time = datetime.now()
        start_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        end_str = end_time.strftime("%Y%m%d_%H%M%S")
        
        new_name = f"ilasp_kfold-{start_str}-{end_str}-{self.experiment_id}"
        new_path = self.output_dir.parent / new_name
        
        try:
            self.output_dir.rename(new_path)
            self.output_dir = new_path
            self.logger.log_file = new_path / "logs" / "experiment.log"
        except Exception as e:
            self.logger.warn(f"Could not rename directory: {e}")
    
    def _init_evaluators(self):
        """Initialize LLM and ILASP evaluators."""
        self.logger.info("Initializing evaluators...")
        
        # Check guidance availability
        if not GUIDANCE_AVAILABLE:
            self.logger.warn("Guidance library not available - LLM evaluation may be limited")
        
        self.logger.info(f"LLM base URL: {self.args.llm_base_url}")
        self.logger.info(f"LLM model: {self.args.llm_model}")
        self.logger.info(f"Temperature: {self.args.temperature}")
        
        # Check ILASP binary
        ilasp_path = Path(self.args.ilasp_binary)
        if ilasp_path.exists():
            self.logger.info(f"ILASP binary: {ilasp_path}")
        else:
            self.logger.warn(f"ILASP binary not found at {ilasp_path}")
    
    def _get_books(self) -> List[str]:
        """Get list of available books."""
        books = []
        for book_dir in self.original_books_dir.iterdir():
            if book_dir.is_dir() and book_dir.name in BOOK_METADATA:
                books.append(book_dir.name)
        return sorted(books)
    
    def _load_chapter(self, book_name: str, is_modified: bool) -> Tuple[str, str]:
        """
        Load chapter text.
        
        Uses separate directories for original and modified:
        - Original: original_books/BookName/NNN.txt
        - Modified: modified_books/BookName/NNN.txt
        """
        if is_modified:
            book_dir = self.modified_books_dir / book_name
        else:
            book_dir = self.original_books_dir / book_name
        
        # Find chapter file
        chapter_files = list(book_dir.glob("*.txt"))
        if not chapter_files:
            raise FileNotFoundError(f"No chapter files in {book_dir}")
        
        chapter_file = chapter_files[0]
        story_text = chapter_file.read_text(encoding="utf-8", errors="replace")
        
        return story_text, str(chapter_file)
    
    def process_chapter(self, book_name: str, is_modified: bool) -> ChapterResult:
        """Process a single chapter through both evaluation approaches."""
        result = ChapterResult(
            book_name=book_name,
            chapter_file=BOOK_METADATA.get(book_name, {}).get("chapter_file", "unknown"),
            is_modified=is_modified
        )
        result.start_time = datetime.now()
        
        version = "modified" if is_modified else "original"
        self.logger.section(f"Processing: {book_name} ({version})")
        
        try:
            # Load chapter
            story_text, story_path = self._load_chapter(book_name, is_modified)
            
            # Truncate if needed
            max_len = self.args.max_story_length
            if max_len and len(story_text) > max_len:
                self.logger.warn(f"Truncating story from {len(story_text)} to {max_len} chars")
                story_text = story_text[:max_len] + "\n\n[...truncated...]"
            
            result.story_text = story_text
            result.story_path = story_path
            self.logger.info(f"Loaded: {story_path} ({len(story_text)} chars)")
            
            # Run LLM-based evaluation (guidance)
            self.logger.info("Running LLM evaluation (guidance)...")
            llm_start = datetime.now()
            try:
                result.llm_result = guidance_llm_lint(
                    story_text,
                    llm_base_url=self.args.llm_base_url,
                    llm_model=self.args.llm_model,
                    temperature=self.args.temperature,
                    verbose=True,
                )
                self.logger.info(f"LLM found {result.llm_result.get('error_count', 0)} errors")
            except Exception as e:
                self.logger.error(f"LLM evaluation failed: {e}")
                result.llm_result = {"error_count": 0, "errors": [], "error": str(e)}
            
            llm_duration = (datetime.now() - llm_start).total_seconds()
            self.logger.info(f"LLM evaluation took {llm_duration:.1f}s")
            
            # Run ILASP-based evaluation
            self.logger.info("Running ILASP evaluation...")
            ilasp_start = datetime.now()
            try:
                result.ilasp_result = ilasp_lint(
                    story_text,
                    llm_base_url=self.args.llm_base_url,
                    llm_model=self.args.llm_model,
                    temperature=self.args.temperature,
                    ilasp_binary=Path(self.args.ilasp_binary),
                    verbose=True,
                )
                self.logger.info(f"ILASP found {result.ilasp_result.get('error_count', 0)} errors")
            except Exception as e:
                self.logger.error(f"ILASP evaluation failed: {e}")
                result.ilasp_result = {"error_count": 0, "errors": [], "error": str(e)}
            
            ilasp_duration = (datetime.now() - ilasp_start).total_seconds()
            self.logger.info(f"ILASP evaluation took {ilasp_duration:.1f}s")
            
            # Categorize errors
            for error in result.llm_result.get("errors", []):
                cat = categorize_error(error)
                error["category"] = cat
                result.llm_errors[cat].append(error)
            
            for error in result.ilasp_result.get("errors", []):
                cat = categorize_error(error)
                error["category"] = cat
                result.ilasp_errors[cat].append(error)
            
            self.logger.info(f"LLM by category: {dict((k, len(v)) for k, v in result.llm_errors.items())}")
            self.logger.info(f"ILASP by category: {dict((k, len(v)) for k, v in result.ilasp_errors.items())}")
            
        except Exception as e:
            self.logger.error(f"Failed to process {book_name}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        result.end_time = datetime.now()
        self.logger.info(f"Completed {book_name} in {result.duration_seconds():.1f}s")
        
        # Save individual result
        result_file = self.output_dir / "results" / f"{book_name.replace(' ', '_')}_{version}.json"
        result_file.write_text(json.dumps(result.to_dict(), indent=2))
        
        return result
    
    def run_calibration(self, books: List[str]) -> Dict[str, Dict]:
        """Run calibration on original books."""
        self.logger.section("CALIBRATION: Processing Original Chapters")
        
        fp_counts = {cat: {"llm": 0, "ilasp": 0} for cat in ERROR_CATEGORIES}
        
        for book in books:
            result = self.process_chapter(book, is_modified=False)
            self.original_results.append(result)
            
            for cat in ERROR_CATEGORIES:
                fp_counts[cat]["llm"] += len(result.llm_errors[cat])
                fp_counts[cat]["ilasp"] += len(result.ilasp_errors[cat])
        
        self.logger.info(f"Calibration complete. False positives: {fp_counts}")
        return fp_counts
    
    def run_testing(self, books: List[str]) -> Dict[str, Dict]:
        """Run testing on modified books."""
        self.logger.section("TESTING: Processing Modified Chapters")
        
        error_counts = {cat: {"llm": 0, "ilasp": 0} for cat in ERROR_CATEGORIES}
        
        for book in books:
            result = self.process_chapter(book, is_modified=True)
            self.modified_results.append(result)
            
            for cat in ERROR_CATEGORIES:
                error_counts[cat]["llm"] += len(result.llm_errors[cat])
                error_counts[cat]["ilasp"] += len(result.ilasp_errors[cat])
        
        self.logger.info(f"Testing complete. Detected errors: {error_counts}")
        return error_counts
    
    def run_kfold(self):
        """Run k-fold cross-validation analysis."""
        books = self._get_books()
        self.logger.section(f"K-FOLD EXPERIMENT: {len(books)} books")
        self.logger.info(f"Books: {books}")
        
        # Process all chapters
        self.run_calibration(books)
        self.run_testing(books)
        
        # K-fold analysis for k = 1 to 4
        for k in range(1, min(5, len(books) + 1)):
            self.logger.section(f"K-FOLD ANALYSIS: k={k}")
            
            splits = generate_kfold_splits(books, k)
            fold_results = []
            
            for fold_idx, (train_books, test_books) in enumerate(splits):
                self.logger.info(f"Fold {fold_idx + 1}/{k}: Test={test_books}")
                
                # Calculate metrics for this fold
                test_errors = {cat: {"llm": 0, "ilasp": 0} for cat in ERROR_CATEGORIES}
                test_fp = {cat: {"llm": 0, "ilasp": 0} for cat in ERROR_CATEGORIES}
                
                for result in self.modified_results:
                    if result.book_name in test_books:
                        for cat in ERROR_CATEGORIES:
                            test_errors[cat]["llm"] += len(result.llm_errors[cat])
                            test_errors[cat]["ilasp"] += len(result.ilasp_errors[cat])
                
                for result in self.original_results:
                    if result.book_name in test_books:
                        for cat in ERROR_CATEGORIES:
                            test_fp[cat]["llm"] += len(result.llm_errors[cat])
                            test_fp[cat]["ilasp"] += len(result.ilasp_errors[cat])
                
                # Net errors = detected - false positives
                net_errors = {cat: {
                    "llm": max(0, test_errors[cat]["llm"] - test_fp[cat]["llm"]),
                    "ilasp": max(0, test_errors[cat]["ilasp"] - test_fp[cat]["ilasp"])
                } for cat in ERROR_CATEGORIES}
                
                fold_results.append({
                    "fold": fold_idx + 1,
                    "test_books": test_books,
                    "test_errors": test_errors,
                    "test_fp": test_fp,
                    "net_errors": net_errors,
                })
            
            # Average across folds
            avg_net = {cat: {"llm": 0.0, "ilasp": 0.0} for cat in ERROR_CATEGORIES}
            for fold in fold_results:
                for cat in ERROR_CATEGORIES:
                    avg_net[cat]["llm"] += fold["net_errors"][cat]["llm"] / len(fold_results)
                    avg_net[cat]["ilasp"] += fold["net_errors"][cat]["ilasp"] / len(fold_results)
            
            self.kfold_results[k] = {
                "k": k,
                "folds": fold_results,
                "average_net_errors": avg_net,
                "total_avg_llm": sum(avg_net[cat]["llm"] for cat in ERROR_CATEGORIES),
                "total_avg_ilasp": sum(avg_net[cat]["ilasp"] for cat in ERROR_CATEGORIES),
            }
            
            self.logger.info(f"k={k} average net: LLM={self.kfold_results[k]['total_avg_llm']:.2f}, "
                           f"ILASP={self.kfold_results[k]['total_avg_ilasp']:.2f}")
    
    def generate_report(self) -> str:
        """Generate markdown report."""
        report = []
        report.append("# ILASP K-Fold Cross-Validation Experiment Report")
        report.append("")
        report.append(f"**Experiment ID:** {self.experiment_id}")
        report.append(f"**Start Time:** {self.start_time.isoformat()}")
        report.append(f"**End Time:** {datetime.now().isoformat()}")
        report.append(f"**Duration:** {(datetime.now() - self.start_time).total_seconds():.1f}s")
        report.append("")
        
        report.append("## Summary")
        report.append("")
        report.append("This experiment compares two narrative consistency evaluation approaches:")
        report.append("1. **LLM-based (guidance)**: Direct analysis using constrained LLM generation")
        report.append("2. **ILASP-based**: Logic evaluation using Inductive Learning of Answer Set Programs")
        report.append("")
        
        report.append("## Configuration")
        report.append("")
        report.append(f"- **LLM Model:** {self.args.llm_model}")
        report.append(f"- **LLM Base URL:** {self.args.llm_base_url}")
        report.append(f"- **Temperature:** {self.args.temperature}")
        report.append(f"- **ILASP Binary:** {self.args.ilasp_binary}")
        report.append("")
        
        report.append("## Dataset")
        report.append("")
        report.append("| Book | Author | Chapter |")
        report.append("|------|--------|---------|")
        for book_name, meta in BOOK_METADATA.items():
            if any(r.book_name == book_name for r in self.original_results):
                report.append(f"| {meta['full_title']} | {meta['author']} | {meta['chapter_file']} |")
        report.append("")
        
        report.append("## Calibration Results (False Positives)")
        report.append("")
        report.append("| Book | " + " | ".join(f"{cat.title()}" for cat in ERROR_CATEGORIES) + " | Total |")
        report.append("|------|" + "|".join(["---"] * (len(ERROR_CATEGORIES) + 1)) + "|")
        
        for result in self.original_results:
            row = f"| {result.book_name} |"
            llm_total, ilasp_total = 0, 0
            for cat in ERROR_CATEGORIES:
                llm = len(result.llm_errors[cat])
                ilasp = len(result.ilasp_errors[cat])
                row += f" {llm}/{ilasp} |"
                llm_total += llm
                ilasp_total += ilasp
            row += f" {llm_total}/{ilasp_total} |"
            report.append(row)
        report.append("")
        report.append("_(Format: LLM/ILASP)_")
        report.append("")
        
        report.append("## Testing Results (Modified Chapters)")
        report.append("")
        report.append("| Book | " + " | ".join(f"{cat.title()}" for cat in ERROR_CATEGORIES) + " | Total |")
        report.append("|------|" + "|".join(["---"] * (len(ERROR_CATEGORIES) + 1)) + "|")
        
        for result in self.modified_results:
            row = f"| {result.book_name} |"
            llm_total, ilasp_total = 0, 0
            for cat in ERROR_CATEGORIES:
                llm = len(result.llm_errors[cat])
                ilasp = len(result.ilasp_errors[cat])
                row += f" {llm}/{ilasp} |"
                llm_total += llm
                ilasp_total += ilasp
            row += f" {llm_total}/{ilasp_total} |"
            report.append(row)
        report.append("")
        
        report.append("## K-Fold Cross-Validation Results")
        report.append("")
        
        for k, kresult in self.kfold_results.items():
            report.append(f"### k={k}")
            report.append("")
            report.append("| Category | LLM Avg | ILASP Avg | Difference |")
            report.append("|----------|---------|-----------|------------|")
            
            avg = kresult["average_net_errors"]
            for cat in ERROR_CATEGORIES:
                llm = avg[cat]["llm"]
                ilasp = avg[cat]["ilasp"]
                diff = llm - ilasp
                report.append(f"| {cat.title()} | {llm:.2f} | {ilasp:.2f} | {diff:+.2f} |")
            
            report.append(f"| **Total** | **{kresult['total_avg_llm']:.2f}** | "
                         f"**{kresult['total_avg_ilasp']:.2f}** | "
                         f"**{kresult['total_avg_llm'] - kresult['total_avg_ilasp']:+.2f}** |")
            report.append("")
        
        report.append("## Conclusions")
        report.append("")
        
        # Calculate overall stats
        total_llm_fp = sum(sum(len(r.llm_errors[c]) for c in ERROR_CATEGORIES) for r in self.original_results)
        total_ilasp_fp = sum(sum(len(r.ilasp_errors[c]) for c in ERROR_CATEGORIES) for r in self.original_results)
        total_llm_det = sum(sum(len(r.llm_errors[c]) for c in ERROR_CATEGORIES) for r in self.modified_results)
        total_ilasp_det = sum(sum(len(r.ilasp_errors[c]) for c in ERROR_CATEGORIES) for r in self.modified_results)
        
        report.append(f"1. **False Positives:** LLM={total_llm_fp}, ILASP={total_ilasp_fp}")
        report.append(f"2. **Detected Errors:** LLM={total_llm_det}, ILASP={total_ilasp_det}")
        report.append(f"3. **Net Detection:** LLM={total_llm_det - total_llm_fp}, ILASP={total_ilasp_det - total_ilasp_fp}")
        report.append("")
        
        return "\n".join(report)
    
    def save_results(self):
        """Save all results."""
        self.logger.section("SAVING RESULTS")
        
        # All results JSON
        all_results = {
            "experiment_id": self.experiment_id,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "configuration": {
                "llm_model": self.args.llm_model,
                "llm_base_url": self.args.llm_base_url,
                "temperature": self.args.temperature,
                "ilasp_binary": self.args.ilasp_binary,
            },
            "original_results": [r.to_dict() for r in self.original_results],
            "modified_results": [r.to_dict() for r in self.modified_results],
            "kfold_results": self.kfold_results,
        }
        
        results_file = self.output_dir / "results" / "all_results.json"
        results_file.write_text(json.dumps(all_results, indent=2))
        self.logger.info(f"Saved: {results_file}")
        
        # Report
        report = self.generate_report()
        report_file = self.output_dir / "REPORT.md"
        report_file.write_text(report)
        self.logger.info(f"Saved: {report_file}")
        
        # Finalize directory
        self._finalize_output_dir()
        
        return self.output_dir


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="K-fold experiment comparing guidance-LLM vs ILASP evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("LLM_BASE_URL", "http://localhost:8080/v1"),
        help="LLM API base URL (default: http://localhost:8080/v1)"
    )
    parser.add_argument(
        "--llm-model",
        default="local-model",
        help="LLM model name (default: local-model)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature (default: 0.0 for deterministic)"
    )
    parser.add_argument(
        "--ilasp-binary",
        default=str(Path.home() / ".local" / "bin" / "ilasp"),
        help="Path to ILASP binary"
    )
    parser.add_argument(
        "--max-story-length",
        type=int,
        default=None,
        help="Maximum story length (default: no limit)"
    )
    
    args = parser.parse_args()
    
    # Initialize
    logger = Logger()
    logger.section("ILASP K-FOLD CROSS-VALIDATION EXPERIMENT")
    logger.info(f"Configuration: {vars(args)}")
    
    # Run experiment
    experiment = ILASPExperiment(args, logger)
    
    try:
        experiment.run_kfold()
        output_dir = experiment.save_results()
        
        logger.section("EXPERIMENT COMPLETE")
        logger.info(f"Results: {output_dir}")
        
        print(f"\n✓ Experiment complete!")
        print(f"  Results: {output_dir}")
        print(f"  Report: {output_dir / 'REPORT.md'}")
        
    except KeyboardInterrupt:
        logger.warn("Interrupted by user")
        experiment.save_results()
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            experiment.save_results()
        except:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
