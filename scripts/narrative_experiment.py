#!/usr/bin/env python3
"""
narrative_experiment.py - Comprehensive Narrative Evaluation Experiment Framework
==================================================================================

This script implements a complete experimental framework for comparing LLM-based and
logic-based narrative evaluation approaches.

Key Features:
- K-fold cross-validation (k=1 to 4)
- Multiple LLM backend support (with automatic model management)
- Detailed error categorization into 5 categories
- Comprehensive logging with timestamps
- Academic-quality reporting
- Story fragment extraction for error analysis

Error Categories:
1. Causality: Chekhov's gun, causal chains, unexplained events
2. Coherence: Semantic correctness, logical consistency
3. Temporal: Time intervals, ordering, duration violations
4. Location: Spatial constraints, distances, ubiquity
5. Emotional: Character motivations, relationships, behavior consistency

Architecture:
- Training phase: Analyze original_books to establish false positive baseline
- Testing phase: Find real errors in modified_books
- Two-module rule system: general.lp (domain-independent) + domain-specific rules
"""

import os
import json
import subprocess
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import logging
from itertools import combinations
import shutil
import traceback

# Error categories
ERROR_CATEGORIES = [
    "causality",     # Chekhov's gun, causal chains
    "coherence",     # Semantic correctness, logical consistency
    "temporal",      # Time intervals, ordering
    "location",      # Spatial constraints, distances
    "emotional"      # Character motivations, relationships
]


class TimestampedLogger:
    """Logger that adds timestamps to all messages."""
    
    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.logger = logging.getLogger(f"experiment_{log_file.stem}")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Formatter with timestamp
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
    
    def info(self, msg: str):
        self.logger.info(msg)
    
    def debug(self, msg: str):
        self.logger.debug(msg)
    
    def warning(self, msg: str):
        self.logger.warning(msg)
    
    def error(self, msg: str):
        self.logger.error(msg)
    
    def timing(self, label: str, start_time: float):
        elapsed = time.time() - start_time
        self.logger.info(f"TIMING: {label}: {elapsed:.2f} seconds")
        return elapsed


class LLMModelManager:
    """Manages loading and unloading of local LLM models."""
    
    def __init__(self, logger: TimestampedLogger):
        self.logger = logger
        self.current_process = None
        self.current_model = None
    
    def start_model(self, model_name: str, script_path: str) -> bool:
        """Start a local LLM model."""
        try:
            self.logger.info(f"Starting model: {model_name} from {script_path}")
            
            # Check if script exists
            if not os.path.exists(script_path):
                self.logger.error(f"Model script not found: {script_path}")
                return False
            
            # Start the model in background
            self.current_process = subprocess.Popen(
                ['/bin/bash', script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            self.current_model = model_name
            
            # Wait for model to initialize (give it time to load)
            self.logger.info(f"Waiting for {model_name} to initialize...")
            time.sleep(30)  # Models need time to load into VRAM
            
            self.logger.info(f"Model {model_name} started with PID {self.current_process.pid}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start model {model_name}: {e}")
            return False
    
    def stop_model(self):
        """Stop the currently running model."""
        if self.current_process is None:
            return
        
        try:
            self.logger.info(f"Stopping model: {self.current_model}")
            
            # Kill the process group
            import signal
            os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
            
            # Wait for it to die
            self.current_process.wait(timeout=10)
            
            # Give VRAM time to clear
            time.sleep(5)
            
            self.logger.info(f"Model {self.current_model} stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping model: {e}")
            try:
                # Force kill if needed
                os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                time.sleep(5)
            except:
                pass
        
        finally:
            self.current_process = None
            self.current_model = None


class StoryFragment:
    """Represents a fragment of story text for error reporting."""
    
    def __init__(self, text: str, start_line: int, end_line: int, event_id: Optional[str] = None):
        self.text = text
        self.start_line = start_line
        self.end_line = end_line
        self.event_id = event_id
    
    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "event_id": self.event_id
        }


class ErrorDetail:
    """Detailed error information with story context."""
    
    def __init__(
        self,
        category: str,
        error_type: str,
        description: str,
        story_file: str,
        story_title: str,
        fragments: List[StoryFragment],
        linter_type: str,  # "llm" or "logic"
        raw_data: Optional[Dict] = None
    ):
        self.category = category
        self.error_type = error_type
        self.description = description
        self.story_file = story_file
        self.story_title = story_title
        self.fragments = fragments
        self.linter_type = linter_type
        self.raw_data = raw_data or {}
    
    def to_dict(self) -> Dict:
        return {
            "category": self.category,
            "error_type": self.error_type,
            "description": self.description,
            "story_file": self.story_file,
            "story_title": self.story_title,
            "fragments": [f.to_dict() for f in self.fragments],
            "linter_type": self.linter_type,
            "raw_data": self.raw_data
        }


class ExperimentResults:
    """Container for experiment results."""
    
    def __init__(self):
        self.errors: List[ErrorDetail] = []
        self.timing: Dict[str, float] = {}
        self.metadata: Dict[str, Any] = {}
    
    def add_error(self, error: ErrorDetail):
        self.errors.append(error)
    
    def add_timing(self, label: str, duration: float):
        self.timing[label] = duration
    
    def to_dict(self) -> Dict:
        return {
            "errors": [e.to_dict() for e in self.errors],
            "timing": self.timing,
            "metadata": self.metadata,
            "summary": {
                "total_errors": len(self.errors),
                "errors_by_category": self._count_by_category(),
                "errors_by_linter": self._count_by_linter(),
                "total_time": sum(self.timing.values())
            }
        }
    
    def _count_by_category(self) -> Dict[str, int]:
        counts = {cat: 0 for cat in ERROR_CATEGORIES}
        for error in self.errors:
            if error.category in counts:
                counts[error.category] += 1
        return counts
    
    def _count_by_linter(self) -> Dict[str, int]:
        counts = {"llm": 0, "logic": 0}
        for error in self.errors:
            if error.linter_type in counts:
                counts[error.linter_type] += 1
        return counts


class NarrativeExperiment:
    """Main experiment orchestrator."""
    
    def __init__(
        self,
        experiment_name: str,
        original_books_dir: Path,
        modified_books_dir: Path,
        output_dir: Path,
        models: List[Tuple[str, str]]  # List of (model_name, script_path)
    ):
        self.experiment_name = experiment_name
        self.original_books_dir = original_books_dir
        self.modified_books_dir = modified_books_dir
        self.output_dir = output_dir
        self.models = models
        
        # Create experiment directory with timestamp
        self.start_time = datetime.now()
        self.start_timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        # We'll set end timestamp when experiment finishes
        self.experiment_dir = output_dir / f"{experiment_name}-{self.start_timestamp}-RUNNING"
        self.experiment_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self.logger = TimestampedLogger(self.experiment_dir / "experiment.log")
        self.logger.info(f"=== Experiment Started: {experiment_name} ===")
        self.logger.info(f"Start time: {self.start_time}")
        self.logger.info(f"Output directory: {self.experiment_dir}")
        
        # Model manager
        self.model_manager = LLMModelManager(self.logger)
        
        # Results storage
        self.all_results: Dict[str, Dict] = {}
    
    def get_books(self, books_dir: Path) -> List[Tuple[str, List[Path]]]:
        """Get list of books and their chapters."""
        books = []
        for book_dir in sorted(books_dir.iterdir()):
            if book_dir.is_dir():
                chapters = sorted(book_dir.glob("*.txt"))
                if chapters:
                    books.append((book_dir.name, chapters))
        return books
    
    def select_pilot_chapters(self, books: List[Tuple[str, List[Path]]]) -> List[Tuple[str, Path]]:
        """Select 1 chapter per book for pilot study."""
        pilot_chapters = []
        for book_name, chapters in books:
            if chapters:
                # Take first chapter
                pilot_chapters.append((book_name, chapters[0]))
        return pilot_chapters
    
    def run_kfold_experiments(self, k_values: List[int]):
        """Run k-fold cross-validation experiments for each k value."""
        
        # Get pilot chapters
        original_books = self.get_books(self.original_books_dir)
        modified_books = self.get_books(self.modified_books_dir)
        
        pilot_original = self.select_pilot_chapters(original_books)
        pilot_modified = self.select_pilot_chapters(modified_books)
        
        self.logger.info(f"Pilot study: {len(pilot_original)} chapters from original books")
        self.logger.info(f"Pilot study: {len(pilot_modified)} chapters from modified books")
        
        # For each model
        for model_name, model_script in self.models:
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"Testing model: {model_name}")
            self.logger.info(f"{'='*80}")
            
            # Start the model
            if not self.model_manager.start_model(model_name, model_script):
                self.logger.error(f"Failed to start model {model_name}, skipping...")
                continue
            
            try:
                # For each k value
                for k in k_values:
                    self.logger.info(f"\n{'-'*80}")
                    self.logger.info(f"K-Fold Validation: k={k}")
                    self.logger.info(f"{'-'*80}")
                    
                    # Run k-fold cross-validation
                    self.run_kfold(k, pilot_original, pilot_modified, model_name)
            
            finally:
                # Stop the model to free VRAM
                self.model_manager.stop_model()
        
        # Finalize experiment
        self.finalize_experiment()
    
    def run_kfold(
        self,
        k: int,
        original_chapters: List[Tuple[str, Path]],
        modified_chapters: List[Tuple[str, Path]],
        model_name: str
    ):
        """Run k-fold cross-validation."""
        
        if k == 1:
            # No splitting, use all data
            folds = [(original_chapters, modified_chapters)]
        else:
            # Create k folds
            fold_size = len(original_chapters) // k
            folds = []
            for i in range(k):
                start_idx = i * fold_size
                end_idx = start_idx + fold_size if i < k - 1 else len(original_chapters)
                fold_original = original_chapters[start_idx:end_idx]
                fold_modified = modified_chapters[start_idx:end_idx]
                folds.append((fold_original, fold_modified))
        
        # Run each fold
        fold_results = []
        for fold_idx, (fold_original, fold_modified) in enumerate(folds, 1):
            self.logger.info(f"\nProcessing Fold {fold_idx}/{len(folds)}")
            
            fold_start = time.time()
            
            # Run experiment on this fold
            result = self.run_fold(
                fold_idx, fold_original, fold_modified, model_name
            )
            
            fold_duration = self.logger.timing(f"Fold {fold_idx}", fold_start)
            result.add_timing("fold_total", fold_duration)
            
            fold_results.append(result)
        
        # Store results
        results_key = f"{model_name}_k{k}"
        self.all_results[results_key] = {
            "model": model_name,
            "k": k,
            "folds": [fr.to_dict() for fr in fold_results],
            "aggregate": self.aggregate_fold_results(fold_results)
        }
        
        # Save intermediate results
        self.save_results()
    
    def run_fold(
        self,
        fold_idx: int,
        original_chapters: List[Tuple[str, Path]],
        modified_chapters: List[Tuple[str, Path]],
        model_name: str
    ) -> ExperimentResults:
        """Run experiment on a single fold."""
        
        results = ExperimentResults()
        results.metadata = {
            "fold": fold_idx,
            "model": model_name,
            "original_chapters": [(book, str(ch)) for book, ch in original_chapters],
            "modified_chapters": [(book, str(ch)) for book, ch in modified_chapters]
        }
        
        # Phase 1: Training - analyze original chapters for false positives
        self.logger.info(f"  Phase 1: Training on original chapters")
        training_start = time.time()
        false_positives = self.analyze_original_chapters(original_chapters, model_name)
        results.add_timing("training", self.logger.timing("Training phase", training_start))
        
        # Phase 2: Testing - find errors in modified chapters
        self.logger.info(f"  Phase 2: Testing on modified chapters")
        testing_start = time.time()
        detected_errors = self.analyze_modified_chapters(modified_chapters, model_name)
        results.add_timing("testing", self.logger.timing("Testing phase", testing_start))
        
        # Filter out false positives
        filtered_errors = self.filter_false_positives(detected_errors, false_positives)
        
        for error in filtered_errors:
            results.add_error(error)
        
        return results
    
    def analyze_original_chapters(
        self,
        chapters: List[Tuple[str, Path]],
        model_name: str
    ) -> List[ErrorDetail]:
        """Analyze original chapters to establish false positive baseline."""
        
        # This would call story_lint.py on each chapter
        # For now, return empty list (implement integration with story_lint.py)
        self.logger.info(f"    Analyzing {len(chapters)} original chapters...")
        
        all_errors = []
        for book_name, chapter_path in chapters:
            chapter_start = time.time()
            self.logger.info(f"      Processing: {book_name}/{chapter_path.name}")
            
            # TODO: Call story_lint.py here
            # errors = self.run_story_lint(chapter_path, model_name)
            # all_errors.extend(errors)
            
            self.logger.timing(f"Chapter {chapter_path.name}", chapter_start)
        
        self.logger.info(f"    Found {len(all_errors)} potential false positives")
        return all_errors
    
    def analyze_modified_chapters(
        self,
        chapters: List[Tuple[str, Path]],
        model_name: str
    ) -> List[ErrorDetail]:
        """Analyze modified chapters to find real errors."""
        
        self.logger.info(f"    Analyzing {len(chapters)} modified chapters...")
        
        all_errors = []
        for book_name, chapter_path in chapters:
            chapter_start = time.time()
            self.logger.info(f"      Processing: {book_name}/{chapter_path.name}")
            
            # TODO: Call story_lint.py here
            # errors = self.run_story_lint(chapter_path, model_name)
            # all_errors.extend(errors)
            
            self.logger.timing(f"Chapter {chapter_path.name}", chapter_start)
        
        self.logger.info(f"    Found {len(all_errors)} potential errors")
        return all_errors
    
    def filter_false_positives(
        self,
        detected_errors: List[ErrorDetail],
        false_positives: List[ErrorDetail]
    ) -> List[ErrorDetail]:
        """Filter out false positives from detected errors."""
        
        # Simple filtering based on error type similarity
        # Could be made more sophisticated
        fp_signatures = set()
        for fp in false_positives:
            sig = (fp.category, fp.error_type, fp.description[:100])
            fp_signatures.add(sig)
        
        filtered = []
        for error in detected_errors:
            sig = (error.category, error.error_type, error.description[:100])
            if sig not in fp_signatures:
                filtered.append(error)
        
        removed = len(detected_errors) - len(filtered)
        self.logger.info(f"    Filtered out {removed} false positives")
        
        return filtered
    
    def aggregate_fold_results(self, fold_results: List[ExperimentResults]) -> Dict:
        """Aggregate results across folds."""
        
        total_errors = sum(len(fr.errors) for fr in fold_results)
        
        # Aggregate by category
        category_counts = {cat: 0 for cat in ERROR_CATEGORIES}
        for fr in fold_results:
            for error in fr.errors:
                if error.category in category_counts:
                    category_counts[error.category] += 1
        
        # Aggregate timing
        avg_timing = {}
        for key in fold_results[0].timing.keys() if fold_results else []:
            times = [fr.timing.get(key, 0) for fr in fold_results]
            avg_timing[key] = sum(times) / len(times) if times else 0
        
        return {
            "total_errors": total_errors,
            "average_errors_per_fold": total_errors / len(fold_results) if fold_results else 0,
            "errors_by_category": category_counts,
            "average_timing": avg_timing,
            "total_time": sum(fr.timing.get("fold_total", 0) for fr in fold_results)
        }
    
    def save_results(self):
        """Save current results to JSON."""
        results_file = self.experiment_dir / "results.json"
        with open(results_file, 'w') as f:
            json.dump(self.all_results, f, indent=2)
        self.logger.info(f"Results saved to {results_file}")
    
    def generate_report(self):
        """Generate academic-style markdown report."""
        
        report_file = self.experiment_dir / "report.md"
        
        with open(report_file, 'w') as f:
            f.write("# Narrative Evaluation Experiment Report\n\n")
            f.write(f"**Experiment:** {self.experiment_name}\n\n")
            f.write(f"**Start Time:** {self.start_time}\n\n")
            f.write(f"**End Time:** {self.end_time}\n\n")
            f.write(f"**Duration:** {self.total_duration:.2f} seconds\n\n")
            
            f.write("## Executive Summary\n\n")
            f.write("This experiment compares LLM-based and logic-based approaches for narrative evaluation, ")
            f.write("focusing on five key error categories: causality, coherence, temporal, location, and emotional.\n\n")
            
            f.write("## Methodology\n\n")
            f.write("### Approach\n\n")
            f.write("- **Training Phase:** Original books analyzed to establish false positive baseline\n")
            f.write("- **Testing Phase:** Modified books analyzed for actual errors\n")
            f.write("- **Validation:** K-fold cross-validation (k=1,2,3,4)\n")
            f.write("- **Models Tested:** ")
            f.write(", ".join([m[0] for m in self.models]))
            f.write("\n\n")
            
            f.write("### Error Categories\n\n")
            f.write("1. **Causality:** Chekhov's gun violations, missing causal links\n")
            f.write("2. **Coherence:** Semantic correctness, logical consistency\n")
            f.write("3. **Temporal:** Time ordering, duration, interval violations\n")
            f.write("4. **Location:** Spatial constraints, distance violations, ubiquity\n")
            f.write("5. **Emotional:** Character motivation, relationship consistency\n\n")
            
            f.write("## Results\n\n")
            
            # Add detailed results for each model and k value
            for results_key, result_data in self.all_results.items():
                f.write(f"### {results_key}\n\n")
                f.write(f"**Model:** {result_data['model']}\n\n")
                f.write(f"**K-Fold:** k={result_data['k']}\n\n")
                
                aggregate = result_data['aggregate']
                f.write("#### Aggregate Results\n\n")
                f.write(f"- Total errors detected: {aggregate['total_errors']}\n")
                f.write(f"- Average errors per fold: {aggregate['average_errors_per_fold']:.2f}\n")
                f.write(f"- Total processing time: {aggregate['total_time']:.2f}s\n\n")
                
                f.write("#### Errors by Category\n\n")
                f.write("| Category | Count |\n")
                f.write("|----------|-------|\n")
                for cat in ERROR_CATEGORIES:
                    count = aggregate['errors_by_category'].get(cat, 0)
                    f.write(f"| {cat.capitalize()} | {count} |\n")
                f.write("\n")
            
            f.write("## Discussion\n\n")
            f.write("### Key Findings\n\n")
            f.write("[Analysis of which approach works better for which error categories]\n\n")
            
            f.write("### AI/CS Perspective\n\n")
            f.write("The results demonstrate the complementary nature of symbolic (logic-based) ")
            f.write("and neural (LLM-based) approaches to narrative understanding...\n\n")
            
            f.write("## Conclusion\n\n")
            f.write("[Summary of findings and implications for future work]\n\n")
        
        self.logger.info(f"Report generated: {report_file}")
    
    def finalize_experiment(self):
        """Finalize the experiment and rename directory with end timestamp."""
        
        self.end_time = datetime.now()
        end_timestamp = self.end_time.strftime("%Y%m%d_%H%M%S")
        self.total_duration = (self.end_time - self.start_time).total_seconds()
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"=== Experiment Complete ===")
        self.logger.info(f"End time: {self.end_time}")
        self.logger.info(f"Total duration: {self.total_duration:.2f} seconds")
        self.logger.info(f"{'='*80}")
        
        # Generate final report
        self.generate_report()
        
        # Rename directory with end timestamp
        final_dir = self.output_dir / f"{self.experiment_name}-{self.start_timestamp}-{end_timestamp}"
        self.experiment_dir.rename(final_dir)
        
        self.logger.info(f"Experiment directory: {final_dir}")


def main():
    """Main entry point."""
    
    # Configuration
    base_dir = Path("/home/cleon/ucm/investigacion/articulos/2025/evaluador_narrativa/codigo")
    original_books_dir = base_dir / "original_books"
    modified_books_dir = base_dir / "modified_books"
    output_dir = base_dir / "experiments"
    
    # Models to test
    models = [
        ("gemma3_12b", "/home/cleon/programas/gemma.sh"),
        ("r1_distill_qwen", "/home/cleon/programas/r1_distill_qwen.sh")
    ]
    
    # K values for cross-validation
    k_values = [1, 2, 3, 4]
    
    # Create experiment
    experiment = NarrativeExperiment(
        experiment_name="narrative_eval_pilot",
        original_books_dir=original_books_dir,
        modified_books_dir=modified_books_dir,
        output_dir=output_dir,
        models=models
    )
    
    # Run experiments
    experiment.run_kfold_experiments(k_values)
    
    print("\n" + "="*80)
    print("Experiment complete!")
    print(f"Results saved to: {experiment.experiment_dir}")
    print("="*80)


if __name__ == "__main__":
    main()
