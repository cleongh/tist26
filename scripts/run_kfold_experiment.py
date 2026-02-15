#!/usr/bin/env python3
"""
run_kfold_experiment.py - K-Fold Cross-Validation Experiment for Narrative Evaluation
=======================================================================================

This script implements a comprehensive experiment comparing LLM-based and logic-based
narrative evaluation approaches. It uses k-fold cross-validation to assess the
performance of both methods across different book chapters.

EXPERIMENT DESIGN:
------------------
1. CALIBRATION PHASE: Process original books (error-free) to identify false positives
2. TESTING PHASE: Process modified books (with injected errors) 
3. CROSS-VALIDATION: Use k-fold (k=1 to 4) to aggregate results
4. COMPARISON: Compare LLM-based vs logic-based linting accuracy

ERROR CATEGORIES (5 types):
---------------------------
1. CAUSALITY - Chekhov's gun violations, unexplained effects, missing causes
2. COHERENCE - Semantic errors, dead agents acting, physical impossibilities  
3. TEMPORAL - Time ordering violations, impossible durations
4. LOCATION - Ubiquity (two places at once), impossible travel
5. EMOTIONAL - Relationship-behavior mismatches, emotional inconsistencies

OUTPUT:
-------
- Experiment folder with timestamp and unique ID
- JSON files with detailed error data including story fragments
- Markdown report suitable for academic publication
- Comprehensive logs with timestamps

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import hashlib
import itertools
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from story_lint import (
    llm_lint, logic_lint, log,
    resolve_model_id_openai, infer_no_auth
)
from domain_generator import DomainGenerator, generate_domain_from_stories


# =============================================================================
# CONFIGURATION
# =============================================================================

# Error categories as defined in the research
ERROR_CATEGORIES = [
    "causality",   # Chekhov's gun, unexplained effects
    "coherence",   # Semantic correctness, logical consistency
    "temporal",    # Time intervals, ordering
    "location",    # Spatial constraints, distances
    "emotional"    # Character motivations, relationships
]

# Book metadata for better reporting
BOOK_METADATA = {
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
    },
    "Goosebumps": {
        "full_title": "Goosebumps: Welcome to Dead House",
        "author": "R.L. Stine",
        "chapter_file": "029.txt"
    }
}


# =============================================================================
# LOGGING UTILITIES
# =============================================================================

class TimestampedLogger:
    """Logger that adds timestamps to all messages and writes to file."""
    
    def __init__(self, log_file: Optional[Path] = None):
        self.log_file = log_file
        self.start_time = datetime.now()
        
    def log(self, msg: str, level: str = "INFO"):
        """Log message with timestamp."""
        now = datetime.now()
        elapsed = (now - self.start_time).total_seconds()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        formatted = f"[{timestamp}] [{level}] [{elapsed:.2f}s] {msg}"
        
        # Write to stderr
        sys.stderr.write(formatted + "\n")
        sys.stderr.flush()
        
        # Write to file if configured
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
        """Log a section header."""
        self.log("=" * 60)
        self.log(title)
        self.log("=" * 60)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ExperimentResult:
    """Container for experiment results with rich metadata."""
    
    def __init__(self, book_name: str, chapter_file: str, is_modified: bool):
        self.book_name = book_name
        self.chapter_file = chapter_file
        self.is_modified = is_modified
        self.story_text = ""
        self.story_path = ""
        
        # Timing
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # Results
        self.llm_result: Dict[str, Any] = {}
        self.logic_result: Dict[str, Any] = {}
        
        # Categorized errors
        self.llm_errors_by_category: Dict[str, List[Dict]] = {cat: [] for cat in ERROR_CATEGORIES}
        self.logic_errors_by_category: Dict[str, List[Dict]] = {cat: [] for cat in ERROR_CATEGORIES}
        
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
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
            "logic_result": self.logic_result,
            "llm_errors_by_category": self.llm_errors_by_category,
            "logic_errors_by_category": self.logic_errors_by_category,
            "llm_total_errors": sum(len(v) for v in self.llm_errors_by_category.values()),
            "logic_total_errors": sum(len(v) for v in self.logic_errors_by_category.values()),
        }


# =============================================================================
# ERROR CATEGORIZATION
# =============================================================================

def categorize_error(error: Dict[str, Any]) -> str:
    """
    Determine the category of an error based on its content.
    
    Args:
        error: Error dictionary from linter output
        
    Returns:
        Category string: causality, coherence, temporal, location, or emotional
    """
    # First check if category is explicitly set
    if "category" in error:
        cat = error["category"].lower()
        if cat in ERROR_CATEGORIES:
            return cat
            
    # Infer from violation_type if present
    vtype = error.get("violation_type", "").lower()
    desc = error.get("description", "").lower()
    
    # Causality indicators
    if any(kw in vtype or kw in desc for kw in [
        "chekhov", "cause", "effect", "precondition", "uncaused", "unexplained"
    ]):
        return "causality"
        
    # Coherence indicators
    if any(kw in vtype or kw in desc for kw in [
        "dead", "edible", "physical", "focus", "semantic", "impossible", "inconsisten"
    ]):
        return "coherence"
        
    # Temporal indicators
    if any(kw in vtype or kw in desc for kw in [
        "time", "temporal", "duration", "order", "before", "after", "simultaneous"
    ]):
        return "temporal"
        
    # Location indicators
    if any(kw in vtype or kw in desc for kw in [
        "location", "ubiquity", "proximity", "travel", "place", "distance", "where"
    ]):
        return "location"
        
    # Emotional indicators
    if any(kw in vtype or kw in desc for kw in [
        "emotion", "love", "hate", "fear", "trust", "relationship", "motivat", "feel"
    ]):
        return "emotional"
        
    # Default to coherence for unclassified errors
    return "coherence"


def extract_story_fragments(error: Dict[str, Any], story_text: str) -> List[str]:
    """
    Extract or verify story fragments for an error.
    
    If fragments are already present, verify them. Otherwise, try to find
    relevant passages based on entities mentioned.
    
    Args:
        error: Error dictionary
        story_text: Full story text
        
    Returns:
        List of story fragments (quotes)
    """
    fragments = error.get("story_fragments", [])
    
    # If fragments exist, verify they're actually in the story
    verified = []
    for frag in fragments:
        if isinstance(frag, str) and len(frag) > 10:
            # Check if fragment exists in story (allowing for minor differences)
            frag_clean = frag.strip().replace("\n", " ")
            if frag_clean[:50] in story_text or frag_clean[-50:] in story_text:
                verified.append(frag)
            else:
                # Try to find a similar passage
                words = frag_clean.split()[:5]
                if words:
                    search_str = " ".join(words)
                    idx = story_text.find(search_str)
                    if idx >= 0:
                        # Extract surrounding context
                        start = max(0, idx - 50)
                        end = min(len(story_text), idx + len(frag_clean) + 50)
                        verified.append(story_text[start:end].strip())
                        
    # If no fragments found, try to extract based on entities
    if not verified:
        entities = error.get("involved_entities", [])
        desc = error.get("description", "")
        
        # Try to find passages mentioning the entities
        for entity in entities:
            if isinstance(entity, str) and len(entity) > 2:
                idx = story_text.lower().find(entity.lower())
                if idx >= 0:
                    # Extract surrounding context (200 chars)
                    start = max(0, idx - 100)
                    end = min(len(story_text), idx + 100)
                    context = story_text[start:end].strip()
                    if context not in verified:
                        verified.append(f"...{context}...")
                        
    return verified if verified else ["(No story fragment could be extracted)"]


def enrich_error(error: Dict[str, Any], story_text: str, error_source: str) -> Dict[str, Any]:
    """
    Enrich an error with additional metadata for reporting.
    
    Args:
        error: Original error dictionary
        story_text: Full story text for fragment extraction
        error_source: "llm" or "logic"
        
    Returns:
        Enriched error dictionary
    """
    enriched = dict(error)
    
    # Ensure category is set
    enriched["category"] = categorize_error(error)
    
    # Ensure story fragments are present
    enriched["story_fragments"] = extract_story_fragments(error, story_text)
    
    # Add source
    enriched["source"] = error_source
    
    # Ensure description exists
    if "description" not in enriched:
        enriched["description"] = str(error)
        
    return enriched


# =============================================================================
# K-FOLD CROSS VALIDATION
# =============================================================================

def generate_kfold_splits(books: List[str], k: int) -> List[Tuple[List[str], List[str]]]:
    """
    Generate k-fold cross-validation splits.
    
    Args:
        books: List of book names
        k: Number of folds
        
    Returns:
        List of (train_books, test_books) tuples
    """
    if k <= 0 or k > len(books):
        k = len(books)
        
    n = len(books)
    fold_size = n // k
    remainder = n % k
    
    splits = []
    indices = list(range(n))
    
    start = 0
    for i in range(k):
        # Handle remainder by giving one extra to first folds
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

class NarrativeExperiment:
    """
    Main experiment class for comparing narrative evaluation approaches.
    """
    
    def __init__(self, args, logger: TimestampedLogger):
        self.args = args
        self.logger = logger
        self.start_time = datetime.now()
        self.experiment_id = str(uuid.uuid4())[:8]
        
        # Paths
        self.repo_root = SCRIPT_DIR.parent
        self.original_books_dir = self.repo_root / "original_books"
        self.modified_books_dir = self.repo_root / "modified_books"
        
        # Results storage
        self.original_results: List[ExperimentResult] = []
        self.modified_results: List[ExperimentResult] = []
        self.kfold_results: Dict[int, Dict] = {}  # k -> aggregated results
        
        # Domain generator for logic-based linting
        self.domain_generator = DomainGenerator()
        
        # Create experiment output directory
        self.output_dir = self._create_output_dir()
        
    def _create_output_dir(self) -> Path:
        """Create timestamped experiment directory."""
        start_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        dir_name = f"kfold_narrative_eval-{start_str}-pending-{self.experiment_id}"
        output_dir = self.repo_root / "experiments" / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (output_dir / "original_stories").mkdir(exist_ok=True)
        (output_dir / "modified_stories").mkdir(exist_ok=True)
        (output_dir / "results").mkdir(exist_ok=True)
        (output_dir / "logs").mkdir(exist_ok=True)
        
        # Update logger to write to this directory
        self.logger.log_file = output_dir / "logs" / "experiment.log"
        
        self.logger.info(f"Created experiment directory: {output_dir}")
        return output_dir
        
    def _finalize_output_dir(self):
        """Rename directory with end timestamp."""
        end_time = datetime.now()
        start_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        end_str = end_time.strftime("%Y%m%d_%H%M%S")
        
        new_name = f"kfold_narrative_eval-{start_str}-{end_str}-{self.experiment_id}"
        new_path = self.output_dir.parent / new_name
        
        try:
            old_path = self.output_dir
            self.output_dir.rename(new_path)
            self.output_dir = new_path
            # Update logger's log file path to the new location
            self.logger.log_file = new_path / "logs" / "experiment.log"
            self.logger.info(f"Finalized experiment directory: {new_path}")
        except Exception as e:
            # Print to stderr since logging might fail
            print(f"Warning: Could not rename directory from {old_path} to {new_path}: {e}", file=sys.stderr)
            
    def _get_books(self) -> List[str]:
        """Get list of available books."""
        books = []
        for book_dir in self.original_books_dir.iterdir():
            if book_dir.is_dir() and book_dir.name in BOOK_METADATA:
                books.append(book_dir.name)
        return sorted(books)
        
    def _load_story(self, book_name: str, is_modified: bool) -> Tuple[str, str]:
        """
        Load story text for a book.
        
        Args:
            book_name: Name of the book directory
            is_modified: Whether to load from modified_books
            
        Returns:
            Tuple of (story_text, story_path)
        """
        base_dir = self.modified_books_dir if is_modified else self.original_books_dir
        book_dir = base_dir / book_name
        
        # Find the chapter file
        chapter_files = list(book_dir.glob("*.txt"))
        if not chapter_files:
            raise FileNotFoundError(f"No chapter files found in {book_dir}")
            
        # Use first chapter for pilot (as specified)
        chapter_file = chapter_files[0]
        story_text = chapter_file.read_text(encoding="utf-8", errors="replace")
        
        return story_text, str(chapter_file)
        
    def _create_args_namespace(self):
        """Create args namespace for story_lint functions."""
        class Args:
            pass
        
        args = Args()
        args.llm_model = self.args.llm_model
        args.llm_base_url = self.args.llm_base_url
        args.llm_api_key = self.args.llm_api_key
        args.llm_no_auth = self.args.llm_no_auth
        args.llm_backend = self.args.llm_backend
        args.llm_temperature = 0.0
        args.llm_timeout = self.args.llm_timeout
        args.llm_max_tokens = self.args.llm_max_tokens
        args.llm_retries = self.args.llm_retries
        args.llm_backoff = self.args.llm_backoff
        args.llm_thinking_budget = 0
        
        args.struct_model = self.args.llm_model
        args.struct_base_url = self.args.llm_base_url
        args.struct_api_key = self.args.llm_api_key
        args.struct_no_auth = self.args.llm_no_auth
        args.struct_backend = self.args.llm_backend
        args.struct_timeout = self.args.llm_timeout
        args.struct_max_tokens = self.args.struct_max_tokens
        args.struct_retries = self.args.llm_retries
        args.struct_backoff = self.args.llm_backoff
        args.struct_thinking_budget = 0
        
        args.include_candidates = False
        args.mock = False
        args.mock_llm = False
        args.no_interpret = False
        
        return args
        
    def process_story(self, book_name: str, is_modified: bool) -> ExperimentResult:
        """
        Process a single story through both linting approaches.
        
        Args:
            book_name: Name of the book
            is_modified: Whether to use modified version
            
        Returns:
            ExperimentResult with all data
        """
        result = ExperimentResult(
            book_name=book_name,
            chapter_file=BOOK_METADATA.get(book_name, {}).get("chapter_file", "unknown"),
            is_modified=is_modified
        )
        result.start_time = datetime.now()
        
        version = "modified" if is_modified else "original"
        self.logger.section(f"Processing: {book_name} ({version})")
        
        # Get max story length from args (None = no limit)
        max_story_length = getattr(self.args, 'max_story_length', None)
        
        try:
            # Load story
            story_text, story_path = self._load_story(book_name, is_modified)
            
            # Truncate long stories if limit specified
            if max_story_length and len(story_text) > max_story_length:
                self.logger.warn(f"Story too long ({len(story_text)} chars), truncating to {max_story_length}")
                story_text = story_text[:max_story_length] + "\n\n[... Story truncated ...]"
            
            result.story_text = story_text
            result.story_path = story_path
            self.logger.info(f"Loaded story: {story_path} ({len(story_text)} chars)")
            
            # Save story copy to experiment directory
            story_output_dir = self.output_dir / (f"{version}_stories")
            story_output_file = story_output_dir / f"{book_name.replace(' ', '_')}.txt"
            story_output_file.write_text(story_text)
            self.logger.info(f"Saved story copy to: {story_output_file}")
            
            # Create args for linting
            lint_args = self._create_args_namespace()
            
            # Run LLM linting
            self.logger.info("Starting LLM-based linting...")
            llm_start = datetime.now()
            try:
                result.llm_result = llm_lint(story_text, lint_args)
                self.logger.info(f"LLM linting complete: {result.llm_result.get('error_count', 0)} errors found")
            except (Exception, SystemExit) as e:
                self.logger.error(f"LLM linting failed: {e}")
                result.llm_result = {"error_count": 0, "errors": [], "error": str(e)}
            llm_duration = (datetime.now() - llm_start).total_seconds()
            self.logger.info(f"LLM linting took {llm_duration:.2f}s")
            
            # Run logic-based linting
            self.logger.info("Starting logic-based linting...")
            logic_start = datetime.now()
            try:
                result.logic_result = logic_lint(story_text, lint_args)
                self.logger.info(f"Logic linting complete: {result.logic_result.get('error_count', 0)} errors found")
            except (Exception, SystemExit) as e:
                self.logger.error(f"Logic linting failed: {e}")
                result.logic_result = {"error_count": 0, "errors": [], "error": str(e)}
            logic_duration = (datetime.now() - logic_start).total_seconds()
            self.logger.info(f"Logic linting took {logic_duration:.2f}s")
            
            # Categorize and enrich errors
            for error in result.llm_result.get("errors", []):
                enriched = enrich_error(error, story_text, "llm")
                category = enriched["category"]
                result.llm_errors_by_category[category].append(enriched)
                
            for error in result.logic_result.get("errors", []):
                enriched = enrich_error(error, story_text, "logic")
                category = enriched["category"]
                result.logic_errors_by_category[category].append(enriched)
                
            self.logger.info(f"Categorized errors - LLM: {dict((k, len(v)) for k, v in result.llm_errors_by_category.items())}")
            self.logger.info(f"Categorized errors - Logic: {dict((k, len(v)) for k, v in result.logic_errors_by_category.items())}")
            
        except Exception as e:
            self.logger.error(f"Failed to process {book_name}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
        result.end_time = datetime.now()
        self.logger.info(f"Completed {book_name} in {result.duration_seconds():.2f}s")
        
        # Save individual result
        result_file = self.output_dir / "results" / f"{book_name.replace(' ', '_')}_{version}.json"
        result_file.write_text(json.dumps(result.to_dict(), indent=2))
        self.logger.info(f"Saved result to: {result_file}")
        
        return result
        
    def run_calibration(self, books: List[str]) -> Dict[str, int]:
        """
        Run calibration phase on original books.
        
        Errors found here are false positives that should be filtered out
        when analyzing modified books.
        
        Returns:
            Dictionary of false positive counts by category
        """
        self.logger.section("CALIBRATION PHASE: Processing Original Books")
        
        false_positives = {cat: {"llm": 0, "logic": 0} for cat in ERROR_CATEGORIES}
        
        for book in books:
            result = self.process_story(book, is_modified=False)
            self.original_results.append(result)
            
            # Count false positives by category
            for cat in ERROR_CATEGORIES:
                false_positives[cat]["llm"] += len(result.llm_errors_by_category[cat])
                false_positives[cat]["logic"] += len(result.logic_errors_by_category[cat])
                
        self.logger.info(f"Calibration complete. False positives: {false_positives}")
        return false_positives
        
    def run_testing(self, books: List[str]) -> Dict[str, int]:
        """
        Run testing phase on modified books.
        
        Returns:
            Dictionary of error counts by category
        """
        self.logger.section("TESTING PHASE: Processing Modified Books")
        
        detected_errors = {cat: {"llm": 0, "logic": 0} for cat in ERROR_CATEGORIES}
        
        for book in books:
            result = self.process_story(book, is_modified=True)
            self.modified_results.append(result)
            
            # Count detected errors by category
            for cat in ERROR_CATEGORIES:
                detected_errors[cat]["llm"] += len(result.llm_errors_by_category[cat])
                detected_errors[cat]["logic"] += len(result.logic_errors_by_category[cat])
                
        self.logger.info(f"Testing complete. Detected errors: {detected_errors}")
        return detected_errors
        
    def run_kfold_experiment(self):
        """
        Run the full k-fold cross-validation experiment.
        """
        books = self._get_books()
        self.logger.section(f"K-FOLD EXPERIMENT: {len(books)} books")
        self.logger.info(f"Books: {books}")
        
        # Process all originals first (calibration)
        self.run_calibration(books)
        
        # Process all modified (testing)
        self.run_testing(books)
        
        # Run k-fold analysis for k = 1 to 4
        for k in range(1, min(5, len(books) + 1)):
            self.logger.section(f"K-FOLD ANALYSIS: k={k}")
            
            splits = generate_kfold_splits(books, k)
            fold_results = []
            
            for fold_idx, (train_books, test_books) in enumerate(splits):
                self.logger.info(f"Fold {fold_idx + 1}/{k}: Train={train_books}, Test={test_books}")
                
                # Get calibration data from train books
                train_fp = {cat: {"llm": 0, "logic": 0} for cat in ERROR_CATEGORIES}
                for result in self.original_results:
                    if result.book_name in train_books:
                        for cat in ERROR_CATEGORIES:
                            train_fp[cat]["llm"] += len(result.llm_errors_by_category[cat])
                            train_fp[cat]["logic"] += len(result.logic_errors_by_category[cat])
                            
                # Get test results from test books
                test_errors = {cat: {"llm": 0, "logic": 0} for cat in ERROR_CATEGORIES}
                test_original_fp = {cat: {"llm": 0, "logic": 0} for cat in ERROR_CATEGORIES}
                
                for result in self.modified_results:
                    if result.book_name in test_books:
                        for cat in ERROR_CATEGORIES:
                            test_errors[cat]["llm"] += len(result.llm_errors_by_category[cat])
                            test_errors[cat]["logic"] += len(result.logic_errors_by_category[cat])
                            
                # Get false positives from test books' originals
                for result in self.original_results:
                    if result.book_name in test_books:
                        for cat in ERROR_CATEGORIES:
                            test_original_fp[cat]["llm"] += len(result.llm_errors_by_category[cat])
                            test_original_fp[cat]["logic"] += len(result.logic_errors_by_category[cat])
                            
                # Calculate net errors (detected - false positives from same books)
                net_errors = {cat: {
                    "llm": max(0, test_errors[cat]["llm"] - test_original_fp[cat]["llm"]),
                    "logic": max(0, test_errors[cat]["logic"] - test_original_fp[cat]["logic"])
                } for cat in ERROR_CATEGORIES}
                
                fold_results.append({
                    "fold": fold_idx + 1,
                    "train_books": train_books,
                    "test_books": test_books,
                    "train_false_positives": train_fp,
                    "test_errors_raw": test_errors,
                    "test_original_fp": test_original_fp,
                    "net_errors": net_errors
                })
                
            # Aggregate fold results
            avg_net_errors = {cat: {"llm": 0.0, "logic": 0.0} for cat in ERROR_CATEGORIES}
            for fold in fold_results:
                for cat in ERROR_CATEGORIES:
                    avg_net_errors[cat]["llm"] += fold["net_errors"][cat]["llm"] / len(fold_results)
                    avg_net_errors[cat]["logic"] += fold["net_errors"][cat]["logic"] / len(fold_results)
                    
            self.kfold_results[k] = {
                "k": k,
                "num_folds": len(fold_results),
                "folds": fold_results,
                "average_net_errors": avg_net_errors,
                "total_avg_llm": sum(avg_net_errors[cat]["llm"] for cat in ERROR_CATEGORIES),
                "total_avg_logic": sum(avg_net_errors[cat]["logic"] for cat in ERROR_CATEGORIES)
            }
            
            self.logger.info(f"k={k} Average net errors: {avg_net_errors}")
            
    def generate_report(self) -> str:
        """
        Generate comprehensive markdown report for academic publication.
        """
        self.logger.section("GENERATING ACADEMIC REPORT")
        
        report = []
        report.append("# Narrative Evaluation Experiment Report")
        report.append("")
        report.append(f"**Experiment ID:** {self.experiment_id}")
        report.append(f"**Start Time:** {self.start_time.isoformat()}")
        report.append(f"**End Time:** {datetime.now().isoformat()}")
        report.append(f"**Total Duration:** {(datetime.now() - self.start_time).total_seconds():.2f} seconds")
        report.append("")
        
        # Executive Summary
        report.append("## Executive Summary")
        report.append("")
        report.append("This experiment compares two approaches to narrative consistency evaluation:")
        report.append("1. **LLM-based evaluation**: Direct analysis using a Large Language Model")
        report.append("2. **Logic-based evaluation**: Formal reasoning using Answer Set Programming (Clingo)")
        report.append("")
        report.append("### Error Categories Evaluated")
        report.append("")
        report.append("| Category | Description |")
        report.append("|----------|-------------|")
        report.append("| Causality | Chekhov's gun violations, unexplained effects, missing causes |")
        report.append("| Coherence | Semantic errors, physical impossibilities, dead agents acting |")
        report.append("| Temporal | Time ordering violations, impossible durations |")
        report.append("| Location | Ubiquity (two places at once), impossible travel |")
        report.append("| Emotional | Relationship-behavior mismatches, motivation inconsistencies |")
        report.append("")
        
        # Methodology
        report.append("## Methodology")
        report.append("")
        report.append("### Dataset")
        report.append("")
        report.append("| Book | Author | Chapter |")
        report.append("|------|--------|---------|")
        for book_name, meta in BOOK_METADATA.items():
            if any(r.book_name == book_name for r in self.original_results):
                report.append(f"| {meta['full_title']} | {meta['author']} | {meta['chapter_file']} |")
        report.append("")
        
        report.append("### Experimental Design")
        report.append("")
        report.append("1. **Calibration Phase**: Original (error-free) versions processed to identify false positives")
        report.append("2. **Testing Phase**: Modified versions (with injected errors) processed")
        report.append("3. **Cross-Validation**: K-fold analysis (k=1 to 4) for robust results")
        report.append("")
        
        # Calibration Results
        report.append("## Calibration Results (False Positives)")
        report.append("")
        report.append("Errors detected in original (error-free) stories represent false positives.")
        report.append("")
        
        report.append("### False Positives by Book and Category")
        report.append("")
        
        # Create table header
        header = "| Book | " + " | ".join(f"{cat.title()} (LLM/Logic)" for cat in ERROR_CATEGORIES) + " | Total |"
        separator = "|------|" + "|".join(["--------"] * (len(ERROR_CATEGORIES) + 1)) + "|"
        report.append(header)
        report.append(separator)
        
        for result in self.original_results:
            row = f"| {result.book_name} |"
            llm_total = 0
            logic_total = 0
            for cat in ERROR_CATEGORIES:
                llm_count = len(result.llm_errors_by_category[cat])
                logic_count = len(result.logic_errors_by_category[cat])
                row += f" {llm_count}/{logic_count} |"
                llm_total += llm_count
                logic_total += logic_count
            row += f" {llm_total}/{logic_total} |"
            report.append(row)
        report.append("")
        
        # Testing Results
        report.append("## Testing Results (Modified Books)")
        report.append("")
        report.append("Errors detected in modified stories (containing injected errors).")
        report.append("")
        
        report.append("### Detected Errors by Book and Category")
        report.append("")
        report.append(header)
        report.append(separator)
        
        for result in self.modified_results:
            row = f"| {result.book_name} |"
            llm_total = 0
            logic_total = 0
            for cat in ERROR_CATEGORIES:
                llm_count = len(result.llm_errors_by_category[cat])
                logic_count = len(result.logic_errors_by_category[cat])
                row += f" {llm_count}/{logic_count} |"
                llm_total += llm_count
                logic_total += logic_count
            row += f" {llm_total}/{logic_total} |"
            report.append(row)
        report.append("")
        
        # K-Fold Results
        report.append("## K-Fold Cross-Validation Results")
        report.append("")
        
        for k, kresult in self.kfold_results.items():
            report.append(f"### k={k} ({kresult['num_folds']} folds)")
            report.append("")
            
            report.append("#### Average Net Errors by Category")
            report.append("")
            report.append("| Category | LLM | Logic | Difference |")
            report.append("|----------|-----|-------|------------|")
            
            avg = kresult["average_net_errors"]
            for cat in ERROR_CATEGORIES:
                llm_val = avg[cat]["llm"]
                logic_val = avg[cat]["logic"]
                diff = llm_val - logic_val
                report.append(f"| {cat.title()} | {llm_val:.2f} | {logic_val:.2f} | {diff:+.2f} |")
                
            total_llm = kresult["total_avg_llm"]
            total_logic = kresult["total_avg_logic"]
            report.append(f"| **Total** | **{total_llm:.2f}** | **{total_logic:.2f}** | **{total_llm - total_logic:+.2f}** |")
            report.append("")
            
            # Individual fold details
            report.append("#### Fold Details")
            report.append("")
            for fold in kresult["folds"]:
                report.append(f"**Fold {fold['fold']}:** Test books: {', '.join(fold['test_books'])}")
                report.append("")
        
        # Detailed Error Analysis
        report.append("## Detailed Error Analysis")
        report.append("")
        
        for result in self.modified_results:
            report.append(f"### {result.book_name} (Modified)")
            report.append("")
            
            report.append("#### LLM-Detected Errors")
            report.append("")
            
            all_llm_errors = []
            for cat, errors in result.llm_errors_by_category.items():
                all_llm_errors.extend(errors)
                
            if all_llm_errors:
                for i, error in enumerate(all_llm_errors, 1):
                    report.append(f"**Error {i}** [{error.get('category', 'unknown')}]")
                    report.append("")
                    report.append(f"- **Description:** {error.get('description', 'N/A')}")
                    fragments = error.get('story_fragments', [])
                    if fragments:
                        report.append(f"- **Story Fragment:**")
                        for frag in fragments[:2]:
                            report.append(f"  > {frag[:200]}{'...' if len(frag) > 200 else ''}")
                    report.append("")
            else:
                report.append("_No errors detected by LLM._")
                report.append("")
                
            report.append("#### Logic-Detected Errors")
            report.append("")
            
            all_logic_errors = []
            for cat, errors in result.logic_errors_by_category.items():
                all_logic_errors.extend(errors)
                
            if all_logic_errors:
                for i, error in enumerate(all_logic_errors, 1):
                    report.append(f"**Error {i}** [{error.get('category', 'unknown')}]")
                    report.append("")
                    report.append(f"- **Description:** {error.get('description', 'N/A')}")
                    report.append(f"- **Violation Type:** {error.get('violation_type', 'N/A')}")
                    fragments = error.get('story_fragments', [])
                    if fragments:
                        report.append(f"- **Story Fragment:**")
                        for frag in fragments[:2]:
                            report.append(f"  > {frag[:200]}{'...' if len(frag) > 200 else ''}")
                    report.append("")
            else:
                report.append("_No errors detected by logic linter._")
                report.append("")
        
        # Timing Analysis
        report.append("## Timing Analysis")
        report.append("")
        report.append("### Processing Time by Book")
        report.append("")
        report.append("| Book | Version | Duration (s) |")
        report.append("|------|---------|--------------|")
        
        for result in self.original_results:
            report.append(f"| {result.book_name} | Original | {result.duration_seconds():.2f} |")
        for result in self.modified_results:
            report.append(f"| {result.book_name} | Modified | {result.duration_seconds():.2f} |")
            
        total_time = sum(r.duration_seconds() for r in self.original_results + self.modified_results)
        report.append(f"| **Total** | - | **{total_time:.2f}** |")
        report.append("")
        
        # Conclusions
        report.append("## Conclusions")
        report.append("")
        report.append("### Key Findings")
        report.append("")
        
        # Calculate summary statistics
        total_llm_fp = sum(sum(len(r.llm_errors_by_category[c]) for c in ERROR_CATEGORIES) for r in self.original_results)
        total_logic_fp = sum(sum(len(r.logic_errors_by_category[c]) for c in ERROR_CATEGORIES) for r in self.original_results)
        total_llm_detected = sum(sum(len(r.llm_errors_by_category[c]) for c in ERROR_CATEGORIES) for r in self.modified_results)
        total_logic_detected = sum(sum(len(r.logic_errors_by_category[c]) for c in ERROR_CATEGORIES) for r in self.modified_results)
        
        report.append(f"1. **False Positive Rate:** LLM produced {total_llm_fp} false positives vs Logic's {total_logic_fp}")
        report.append(f"2. **Detection Rate:** LLM detected {total_llm_detected} potential errors vs Logic's {total_logic_detected}")
        report.append(f"3. **Net Detection:** LLM net = {total_llm_detected - total_llm_fp}, Logic net = {total_logic_detected - total_logic_fp}")
        report.append("")
        
        report.append("### Recommendations")
        report.append("")
        report.append("- Further analysis needed with larger sample sizes")
        report.append("- Consider hybrid approaches combining LLM flexibility with logic rigor")
        report.append("- Category-specific tuning may improve detection rates")
        report.append("")
        
        # Appendix: Configuration
        report.append("## Appendix: Experiment Configuration")
        report.append("")
        report.append("```json")
        config = {
            "llm_model": self.args.llm_model,
            "llm_base_url": self.args.llm_base_url,
            "llm_backend": self.args.llm_backend,
            "llm_timeout": self.args.llm_timeout,
            "llm_max_tokens": self.args.llm_max_tokens,
            "struct_max_tokens": self.args.struct_max_tokens
        }
        report.append(json.dumps(config, indent=2))
        report.append("```")
        report.append("")
        
        return "\n".join(report)
        
    def save_results(self):
        """Save all experiment results."""
        self.logger.section("SAVING EXPERIMENT RESULTS")
        
        # Save comprehensive JSON results
        all_results = {
            "experiment_id": self.experiment_id,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "configuration": {
                "llm_model": self.args.llm_model,
                "llm_base_url": self.args.llm_base_url,
                "llm_backend": self.args.llm_backend,
                "books_processed": [r.book_name for r in self.original_results]
            },
            "original_results": [r.to_dict() for r in self.original_results],
            "modified_results": [r.to_dict() for r in self.modified_results],
            "kfold_results": self.kfold_results
        }
        
        results_file = self.output_dir / "results" / "all_results.json"
        results_file.write_text(json.dumps(all_results, indent=2))
        self.logger.info(f"Saved comprehensive results to: {results_file}")
        
        # Save k-fold specific results
        for k, kresult in self.kfold_results.items():
            kfold_file = self.output_dir / "results" / f"kfold_k{k}_results.json"
            kfold_file.write_text(json.dumps(kresult, indent=2))
            self.logger.info(f"Saved k={k} results to: {kfold_file}")
            
        # Generate and save report
        report = self.generate_report()
        report_file = self.output_dir / "report.md"
        report_file.write_text(report)
        self.logger.info(f"Saved markdown report to: {report_file}")
        
        # Finalize directory name with end timestamp
        self._finalize_output_dir()
        
        return self.output_dir


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run k-fold cross-validation experiment for narrative evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--llm-model", 
        default="auto",
        help="LLM model ID or 'auto' to detect (default: auto)"
    )
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("LLM_BASE_URL", "http://localhost:8080/v1"),
        help="LLM API base URL (default: http://localhost:8080/v1)"
    )
    parser.add_argument(
        "--llm-api-key",
        default=os.environ.get("LLM_API_KEY", ""),
        help="LLM API key"
    )
    parser.add_argument(
        "--llm-no-auth",
        action="store_true",
        help="Skip authorization header"
    )
    parser.add_argument(
        "--llm-backend",
        choices=["openai", "gemini", "guidance"],
        default="openai",
        help="LLM backend type (default: openai)"
    )
    parser.add_argument(
        "--llm-timeout",
        type=int,
        default=600,
        help="LLM timeout in seconds (default: 600)"
    )
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=4096,
        help="LLM max output tokens (default: 4096)"
    )
    parser.add_argument(
        "--struct-max-tokens",
        type=int,
        default=8192,
        help="Structurer max output tokens (default: 8192)"
    )
    parser.add_argument(
        "--llm-retries",
        type=int,
        default=3,
        help="LLM retry count (default: 3)"
    )
    parser.add_argument(
        "--llm-backoff",
        type=int,
        default=5,
        help="LLM backoff seconds (default: 5)"
    )
    parser.add_argument(
        "--max-story-length",
        type=int,
        default=None,
        help="Maximum story length in characters (default: no limit)"
    )
    
    args = parser.parse_args()
    
    # Initialize logger
    logger = TimestampedLogger()
    logger.section("NARRATIVE EVALUATION EXPERIMENT")
    logger.info(f"Configuration: {vars(args)}")
    
    # Auto-detect no-auth for local servers
    args.llm_no_auth = infer_no_auth(args.llm_base_url, args.llm_no_auth)
    logger.info(f"No-auth mode: {args.llm_no_auth}")
    
    # Resolve model ID if auto
    if args.llm_model == "auto":
        args.llm_model = resolve_model_id_openai(
            args.llm_base_url, "auto", args.llm_api_key, args.llm_no_auth, args.llm_timeout
        )
        logger.info(f"Resolved model: {args.llm_model}")
    
    # Create and run experiment
    experiment = NarrativeExperiment(args, logger)
    
    try:
        experiment.run_kfold_experiment()
        output_dir = experiment.save_results()
        
        logger.section("EXPERIMENT COMPLETE")
        logger.info(f"Results saved to: {output_dir}")
        
        print(f"\n✓ Experiment complete!")
        print(f"  Results: {output_dir}")
        print(f"  Report: {output_dir / 'report.md'}")
         
    except KeyboardInterrupt:
        logger.warn("Experiment interrupted by user")
        experiment.save_results()
        sys.exit(1)
    except Exception as e:
        logger.error(f"Experiment failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        experiment.save_results()
        sys.exit(1)


if __name__ == "__main__":
    main()
