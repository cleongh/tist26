#!/usr/bin/env python3
"""
run_narrative_experiment.py - Comprehensive Narrative Evaluation Experiment Runner
==================================================================================

This script orchestrates a research experiment comparing LLM-based and logic-based 
narrative evaluation approaches. It implements:

1. K-fold cross-validation across 5 books
2. Comparison of multiple LLM models (Gemma 3, R1 Distill Qwen)
3. False positive filtering using original books as baseline
4. Categorized error detection:
   - Causality (Chekhov's gun, unexplained effects)
   - Basic Coherence (semantic correctness)
   - Temporal Order (time interval violations)
   - Location Correctness (spatial constraints)
   - Emotional Relations (character behavior consistency)

Output Format
-------------
Experiment folder: `narrative_eval-{start_timestamp}-{end_timestamp}-{uuid}`
Contents:
- stories/: Individual story text files
- results/: Per-story JSON results
- logs/: Detailed execution logs with timestamps
- report.md: Academic-focused markdown report
- summary.json: Aggregated statistics

Usage
-----
python scripts/run_narrative_experiment.py \\
    --models gemma,r1 \\
    --k-values 1,2,3,4 \\
    --chapters-per-book 1 \\
    --output-dir experiments

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

# Error categories for classification
ERROR_CATEGORIES = [
    "causality",      # Chekhov's gun, unexplained effects, missing causes
    "coherence",      # Semantic correctness, logical consistency  
    "temporal",       # Time intervals, durations, ordering violations
    "location",       # Spatial constraints, distances, ubiquity
    "emotional"       # Character motivations, relationships, behavior
]

# Model configurations
MODEL_CONFIGS = {
    "gemma": {
        "name": "Gemma 3 12B Instruct",
        "script": "/home/cleon/programas/gemma.sh",
        "llamafile": "/home/cleon/programas/32-google_gemma-3-12b-it-Q4_K_M.llamafile",
        "base_url": "http://localhost:8080/v1",
        "startup_wait": 60,  # seconds to wait for model to load
    },
    "r1": {
        "name": "R1 Distill Qwen 14B",
        "script": "/home/cleon/programas/r1_distill_qwen.sh",
        "llamafile": "/home/cleon/programas/40-DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.llamafile",
        "base_url": "http://localhost:8080/v1",
        "startup_wait": 60,
    }
}


class ExperimentLogger:
    """Logger that writes to both file and stderr with timestamps."""
    
    def __init__(self, log_dir: Path, name: str = "experiment"):
        self.log_dir = log_dir
        self.log_file = log_dir / f"{name}.log"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._file = open(self.log_file, "a")
        
    def log(self, msg: str, level: str = "INFO"):
        """Log message with timestamp."""
        timestamp = datetime.now().isoformat()
        formatted = f"[{timestamp}] [{level}] {msg}"
        self._file.write(formatted + "\n")
        self._file.flush()
        sys.stderr.write(formatted + "\n")
        
    def info(self, msg: str):
        self.log(msg, "INFO")
        
    def error(self, msg: str):
        self.log(msg, "ERROR")
        
    def debug(self, msg: str):
        self.log(msg, "DEBUG")
        
    def close(self):
        self._file.close()


class ModelManager:
    """Manages starting and stopping local LLM models."""
    
    def __init__(self, logger: ExperimentLogger):
        self.logger = logger
        self.current_process: Optional[subprocess.Popen] = None
        self.current_model: Optional[str] = None
        
    def start_model(self, model_key: str) -> bool:
        """Start a model server and wait for it to be ready."""
        if model_key not in MODEL_CONFIGS:
            self.logger.error(f"Unknown model: {model_key}")
            return False
            
        config = MODEL_CONFIGS[model_key]
        
        # Stop any currently running model first
        if self.current_process:
            self.stop_current_model()
            
        self.logger.info(f"Starting model: {config['name']}")
        
        # Start the llamafile server
        try:
            cmd = [
                config["llamafile"],
                "--server", "--nobrowser",
                "--temp", "0",
                "--gpu", "nvidia",
                "-ngl", "99999"
            ]
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group for clean shutdown
            )
            self.current_model = model_key
            
            # Wait for server to be ready
            self.logger.info(f"Waiting {config['startup_wait']}s for model to load...")
            time.sleep(config["startup_wait"])
            
            # Check if model is responding
            if self._check_model_ready(config["base_url"]):
                self.logger.info(f"Model {config['name']} is ready")
                return True
            else:
                self.logger.error(f"Model {config['name']} failed to start")
                self.stop_current_model()
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start model: {e}")
            return False
            
    def _check_model_ready(self, base_url: str, timeout: int = 30) -> bool:
        """Check if the model server is responding."""
        import urllib.request
        import urllib.error
        
        models_url = base_url.rstrip("/") + "/models"
        
        for attempt in range(3):
            try:
                req = urllib.request.Request(models_url)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, urllib.error.HTTPError):
                time.sleep(5)
                
        return False
        
    def stop_current_model(self):
        """Stop the currently running model."""
        if self.current_process:
            self.logger.info(f"Stopping model: {self.current_model}")
            try:
                # Kill the entire process group
                os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                self.current_process.wait(timeout=10)
            except Exception as e:
                self.logger.error(f"Error stopping model: {e}")
                try:
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                except:
                    pass
            self.current_process = None
            self.current_model = None
            # Give system time to free VRAM
            time.sleep(5)


class StoryLinter:
    """Wrapper for story_lint.py with enhanced error extraction."""
    
    def __init__(self, logger: ExperimentLogger, base_url: str = "http://localhost:8080/v1"):
        self.logger = logger
        self.base_url = base_url
        self.script_path = SCRIPT_DIR / "story_lint.py"
        
    def lint_story(self, story_path: Path, mode: str = "both") -> Dict[str, Any]:
        """
        Run linting on a story file and return categorized results.
        
        Args:
            story_path: Path to the story text file
            mode: Lint mode ("llm", "logic", "both")
            
        Returns:
            Dictionary with categorized errors and metadata
        """
        start_time = datetime.now()
        self.logger.info(f"Linting story: {story_path.name}")
        
        # Read story content for fragment extraction
        story_text = story_path.read_text()
        
        try:
            # Import and use story_lint directly for better control
            from story_lint import llm_lint, logic_lint
            import argparse
            
            # Create args namespace
            args = argparse.Namespace(
                llm_model="auto",
                llm_base_url=self.base_url,
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
                struct_base_url=self.base_url,
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
            
            results = {
                "story_file": str(story_path),
                "story_title": story_path.stem,
                "start_time": start_time.isoformat(),
                "mode": mode,
                "errors": [],
                "llm_raw": None,
                "logic_raw": None,
            }
            
            # Run LLM linting
            if mode in ("llm", "both"):
                try:
                    llm_result = llm_lint(story_text, args)
                    results["llm_raw"] = llm_result
                    
                    # Categorize LLM errors
                    for err in llm_result.get("errors", []):
                        categorized = self._categorize_error(
                            err, story_text, "llm"
                        )
                        results["errors"].append(categorized)
                        
                except Exception as e:
                    self.logger.error(f"LLM lint failed: {e}")
                    results["llm_error"] = str(e)
                    
            # Run logic linting
            if mode in ("logic", "both"):
                try:
                    logic_result = logic_lint(story_text, args)
                    results["logic_raw"] = logic_result
                    
                    # Categorize logic errors
                    for err in logic_result.get("errors", []):
                        categorized = self._categorize_error(
                            err, story_text, "logic"
                        )
                        results["errors"].append(categorized)
                        
                except Exception as e:
                    self.logger.error(f"Logic lint failed: {e}")
                    results["logic_error"] = str(e)
                    
            end_time = datetime.now()
            results["end_time"] = end_time.isoformat()
            results["duration_seconds"] = (end_time - start_time).total_seconds()
            results["error_count"] = len(results["errors"])
            
            # Count by category
            results["errors_by_category"] = defaultdict(int)
            for err in results["errors"]:
                results["errors_by_category"][err["category"]] += 1
            results["errors_by_category"] = dict(results["errors_by_category"])
            
            return results
            
        except Exception as e:
            self.logger.error(f"Lint failed for {story_path}: {e}")
            return {
                "story_file": str(story_path),
                "story_title": story_path.stem,
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "error": str(e),
                "errors": [],
                "error_count": 0,
            }
            
    def _categorize_error(self, error: Dict, story_text: str, source: str) -> Dict:
        """
        Categorize an error and extract relevant story fragments.
        
        Args:
            error: Raw error from linter
            story_text: Full story text for fragment extraction
            source: "llm" or "logic"
            
        Returns:
            Enhanced error dict with category and fragments
        """
        description = error.get("description", "").lower()
        error_id = error.get("id", "unknown")
        
        # Determine category based on keywords
        category = "coherence"  # default
        
        if any(kw in description for kw in ["cause", "chekhov", "unexplained", "effect", "precondition"]):
            category = "causality"
        elif any(kw in description for kw in ["time", "temporal", "before", "after", "duration", "order", "simultaneous"]):
            category = "temporal"
        elif any(kw in description for kw in ["location", "place", "ubiquity", "distance", "travel", "spatial"]):
            category = "location"
        elif any(kw in description for kw in ["emotion", "love", "hate", "fear", "trust", "relationship", "feeling", "motivation"]):
            category = "emotional"
        elif any(kw in description for kw in ["dead", "alive", "edible", "physical", "impossible"]):
            category = "coherence"
            
        # For logic errors, check violation type
        if source == "logic" and "violation(" in description:
            if any(vt in description for vt in ["causality", "chekhov", "uncaused", "precondition"]):
                category = "causality"
            elif any(vt in description for vt in ["temporal", "circular_time", "negative_duration", "order"]):
                category = "temporal"
            elif any(vt in description for vt in ["location", "ubiquity", "proximity", "travel"]):
                category = "location"
            elif any(vt in description for vt in ["emotional", "harm_loved", "help_enemy", "approach_feared"]):
                category = "emotional"
            elif any(vt in description for vt in ["coherence", "dead_agent", "non_edible", "physical"]):
                category = "coherence"
                
        # Extract story fragments (simplified - look for keywords in description)
        fragments = self._extract_fragments(description, story_text)
        
        return {
            "id": error_id,
            "source": source,
            "category": category,
            "description": error.get("description", ""),
            "story_fragments": fragments,
            "raw_error": error,
        }
        
    def _extract_fragments(self, description: str, story_text: str, context_chars: int = 200) -> List[Dict]:
        """
        Extract relevant story fragments based on error description.
        
        Args:
            description: Error description to search for keywords
            story_text: Full story text
            context_chars: Characters of context around matches
            
        Returns:
            List of fragment dicts with text and position
        """
        fragments = []
        
        # Extract potential keywords (names, objects, locations)
        # Look for capitalized words and quoted text
        import re
        
        # Find quoted strings in description
        quoted = re.findall(r'"([^"]+)"', description)
        quoted.extend(re.findall(r"'([^']+)'", description))
        
        # Find capitalized words (potential names)
        caps = re.findall(r'\b([A-Z][a-z]+)\b', description)
        
        # Search for each keyword in story
        searched = set()
        for keyword in quoted + caps:
            if keyword.lower() in searched or len(keyword) < 3:
                continue
            searched.add(keyword.lower())
            
            # Find all occurrences
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            for match in pattern.finditer(story_text):
                start = max(0, match.start() - context_chars)
                end = min(len(story_text), match.end() + context_chars)
                
                # Find sentence boundaries
                while start > 0 and story_text[start] not in '.!?\n':
                    start -= 1
                while end < len(story_text) and story_text[end] not in '.!?\n':
                    end += 1
                    
                fragment_text = story_text[start:end].strip()
                if fragment_text and len(fragment_text) > 20:
                    fragments.append({
                        "text": fragment_text,
                        "start_pos": start,
                        "end_pos": end,
                        "keyword": keyword
                    })
                    
                # Only keep first few occurrences per keyword
                if len([f for f in fragments if f["keyword"] == keyword]) >= 2:
                    break
                    
        # Limit total fragments
        return fragments[:5]


class NarrativeExperiment:
    """Main experiment orchestrator."""
    
    def __init__(self, 
                 output_dir: Path,
                 models: List[str],
                 k_values: List[int],
                 chapters_per_book: int = 1):
        """
        Initialize experiment.
        
        Args:
            output_dir: Base directory for experiment output
            models: List of model keys to test ("gemma", "r1")
            k_values: List of k values for cross-validation
            chapters_per_book: Number of chapters per book (pilot = 1)
        """
        self.start_time = datetime.now()
        self.experiment_id = str(uuid.uuid4())[:8]
        
        # Create experiment folder with timestamps
        self.start_timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.experiment_name = f"narrative_eval-{self.start_timestamp}"
        self.experiment_dir = output_dir / self.experiment_name
        
        # Create subdirectories
        self.experiment_dir.mkdir(parents=True, exist_ok=True)
        (self.experiment_dir / "stories").mkdir(exist_ok=True)
        (self.experiment_dir / "results").mkdir(exist_ok=True)
        (self.experiment_dir / "logs").mkdir(exist_ok=True)
        
        # Initialize logger
        self.logger = ExperimentLogger(
            self.experiment_dir / "logs",
            "experiment"
        )
        
        # Store config
        self.models = models
        self.k_values = k_values
        self.chapters_per_book = chapters_per_book
        
        # Initialize managers
        self.model_manager = ModelManager(self.logger)
        
        # Data paths
        self.original_books_dir = REPO_ROOT / "original_books"
        self.modified_books_dir = REPO_ROOT / "modified_books"
        
        # Results storage
        self.all_results: Dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "start_time": self.start_time.isoformat(),
            "config": {
                "models": models,
                "k_values": k_values,
                "chapters_per_book": chapters_per_book,
            },
            "books": [],
            "model_results": {},
            "fold_results": {},
            "aggregated_results": {},
        }
        
        self.logger.info(f"Initialized experiment: {self.experiment_name}")
        self.logger.info(f"Models: {models}")
        self.logger.info(f"K-values: {k_values}")
        self.logger.info(f"Chapters per book: {chapters_per_book}")
        
    def discover_books(self) -> List[Dict]:
        """Discover available books and their chapters."""
        books = []
        
        for book_dir in sorted(self.original_books_dir.iterdir()):
            if book_dir.is_dir():
                # Get chapters (sorted numerically)
                original_chapters = sorted(book_dir.glob("*.txt"))
                modified_dir = self.modified_books_dir / book_dir.name
                modified_chapters = sorted(modified_dir.glob("*.txt")) if modified_dir.exists() else []
                
                books.append({
                    "name": book_dir.name,
                    "original_dir": str(book_dir),
                    "modified_dir": str(modified_dir) if modified_dir.exists() else None,
                    "original_chapters": [str(c) for c in original_chapters[:self.chapters_per_book]],
                    "modified_chapters": [str(c) for c in modified_chapters[:self.chapters_per_book]],
                })
                
        self.logger.info(f"Discovered {len(books)} books")
        for book in books:
            self.logger.info(f"  - {book['name']}: {len(book['original_chapters'])} chapters")
            
        self.all_results["books"] = books
        return books
        
    def run_baseline(self, books: List[Dict], model_key: str) -> Dict[str, List[Dict]]:
        """
        Run linting on original books to identify false positives.
        
        Args:
            books: List of book configurations
            model_key: Model to use
            
        Returns:
            Dict mapping book names to list of baseline errors
        """
        self.logger.info(f"Running baseline on original books with {model_key}")
        baseline = {}
        
        linter = StoryLinter(self.logger, MODEL_CONFIGS[model_key]["base_url"])
        
        for book in books:
            book_name = book["name"]
            baseline[book_name] = []
            
            for chapter_path in book["original_chapters"]:
                chapter = Path(chapter_path)
                
                # Copy to stories folder
                dest = self.experiment_dir / "stories" / f"{book_name}_original_{chapter.name}"
                shutil.copy2(chapter, dest)
                
                # Lint
                result = linter.lint_story(chapter)
                baseline[book_name].append(result)
                
                # Save result
                result_path = self.experiment_dir / "results" / f"baseline_{book_name}_{chapter.stem}_{model_key}.json"
                result_path.write_text(json.dumps(result, indent=2, default=str))
                
        return baseline
        
    def run_test(self, books: List[Dict], model_key: str, test_indices: List[int]) -> Dict[str, List[Dict]]:
        """
        Run linting on modified books (test set).
        
        Args:
            books: List of book configurations  
            model_key: Model to use
            test_indices: Indices of books in test set
            
        Returns:
            Dict mapping book names to list of test errors
        """
        self.logger.info(f"Running test on modified books with {model_key}")
        test_results = {}
        
        linter = StoryLinter(self.logger, MODEL_CONFIGS[model_key]["base_url"])
        
        for idx in test_indices:
            book = books[idx]
            book_name = book["name"]
            test_results[book_name] = []
            
            for chapter_path in book["modified_chapters"]:
                if not chapter_path:
                    continue
                chapter = Path(chapter_path)
                
                # Copy to stories folder
                dest = self.experiment_dir / "stories" / f"{book_name}_modified_{chapter.name}"
                shutil.copy2(chapter, dest)
                
                # Lint
                result = linter.lint_story(chapter)
                test_results[book_name].append(result)
                
                # Save result
                result_path = self.experiment_dir / "results" / f"test_{book_name}_{chapter.stem}_{model_key}.json"
                result_path.write_text(json.dumps(result, indent=2, default=str))
                
        return test_results
        
    def filter_false_positives(self, 
                               test_errors: List[Dict],
                               baseline_errors: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Filter out false positives from test errors.
        
        An error in test is considered a false positive if a similar error
        appears in the baseline (original text).
        
        Returns:
            Tuple of (filtered_errors, false_positives)
        """
        # Build signature set from baseline errors
        baseline_signatures = set()
        for result in baseline_errors:
            for err in result.get("errors", []):
                # Create signature from category + keywords in description
                sig = self._error_signature(err)
                baseline_signatures.add(sig)
                
        filtered = []
        false_positives = []
        
        for result in test_errors:
            for err in result.get("errors", []):
                sig = self._error_signature(err)
                if sig in baseline_signatures:
                    false_positives.append(err)
                else:
                    filtered.append(err)
                    
        return filtered, false_positives
        
    def _error_signature(self, error: Dict) -> str:
        """Create a signature for error matching."""
        category = error.get("category", "unknown")
        description = error.get("description", "").lower()
        # Extract key words for signature
        import re
        words = re.findall(r'\b\w{4,}\b', description)
        key_words = sorted(set(words[:5]))
        return f"{category}:{':'.join(key_words)}"
        
    def run_kfold(self, books: List[Dict], model_key: str, k: int) -> Dict:
        """
        Run k-fold cross-validation.
        
        Args:
            books: List of book configurations
            model_key: Model to use
            k: Number of folds (k books in test, n-k in training)
            
        Returns:
            Dict with fold results
        """
        from itertools import combinations
        
        n_books = len(books)
        if k > n_books:
            self.logger.error(f"k={k} > n_books={n_books}")
            return {}
            
        fold_results = {
            "k": k,
            "model": model_key,
            "folds": [],
            "aggregated": {
                "total_errors_found": 0,
                "total_false_positives": 0,
                "errors_by_category": defaultdict(int),
                "errors_by_source": {"llm": 0, "logic": 0},
            }
        }
        
        # Generate all k-combinations for test sets
        test_combinations = list(combinations(range(n_books), k))
        
        for fold_idx, test_indices in enumerate(test_combinations):
            train_indices = [i for i in range(n_books) if i not in test_indices]
            
            self.logger.info(f"Fold {fold_idx + 1}/{len(test_combinations)}: "
                           f"Test={[books[i]['name'] for i in test_indices]}, "
                           f"Train={[books[i]['name'] for i in train_indices]}")
            
            # Run baseline on training set
            baseline_results = {}
            for idx in train_indices:
                book = books[idx]
                result = self.run_baseline([book], model_key)
                baseline_results.update(result)
                
            # Run test
            test_results = self.run_test(books, model_key, list(test_indices))
            
            # Filter false positives for each test book
            fold_data = {
                "fold_idx": fold_idx,
                "test_books": [books[i]["name"] for i in test_indices],
                "train_books": [books[i]["name"] for i in train_indices],
                "results": {},
            }
            
            for book_name, book_results in test_results.items():
                # Get combined baseline errors from training books
                all_baseline = []
                for train_name, train_results in baseline_results.items():
                    all_baseline.extend(train_results)
                    
                filtered, fps = self.filter_false_positives(book_results, all_baseline)
                
                fold_data["results"][book_name] = {
                    "total_errors": len(filtered) + len(fps),
                    "filtered_errors": len(filtered),
                    "false_positives": len(fps),
                    "filtered_list": filtered,
                    "false_positive_list": fps,
                }
                
                # Update aggregated
                fold_results["aggregated"]["total_errors_found"] += len(filtered)
                fold_results["aggregated"]["total_false_positives"] += len(fps)
                
                for err in filtered:
                    fold_results["aggregated"]["errors_by_category"][err.get("category", "unknown")] += 1
                    fold_results["aggregated"]["errors_by_source"][err.get("source", "unknown")] += 1
                    
            fold_results["folds"].append(fold_data)
            
        # Convert defaultdict to dict for JSON serialization
        fold_results["aggregated"]["errors_by_category"] = dict(
            fold_results["aggregated"]["errors_by_category"]
        )
        
        return fold_results
        
    def run(self) -> Dict:
        """Run the complete experiment."""
        self.logger.info("=" * 60)
        self.logger.info("STARTING NARRATIVE EVALUATION EXPERIMENT")
        self.logger.info("=" * 60)
        
        # Discover books
        books = self.discover_books()
        
        # Run for each model
        for model_key in self.models:
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Testing model: {MODEL_CONFIGS[model_key]['name']}")
            self.logger.info(f"{'='*60}")
            
            # Start model
            if not self.model_manager.start_model(model_key):
                self.logger.error(f"Failed to start model {model_key}, skipping")
                continue
                
            model_start_time = datetime.now()
            
            self.all_results["model_results"][model_key] = {
                "model_name": MODEL_CONFIGS[model_key]["name"],
                "start_time": model_start_time.isoformat(),
                "k_fold_results": {},
            }
            
            # Run k-fold for each k value
            for k in self.k_values:
                self.logger.info(f"\nRunning {k}-fold cross-validation")
                
                fold_results = self.run_kfold(books, model_key, k)
                self.all_results["model_results"][model_key]["k_fold_results"][str(k)] = fold_results
                
                # Save intermediate results
                self._save_results()
                
            model_end_time = datetime.now()
            self.all_results["model_results"][model_key]["end_time"] = model_end_time.isoformat()
            self.all_results["model_results"][model_key]["duration_seconds"] = (
                model_end_time - model_start_time
            ).total_seconds()
            
            # Stop model to free VRAM
            self.model_manager.stop_current_model()
            
        # Finalize
        self.end_time = datetime.now()
        self.all_results["end_time"] = self.end_time.isoformat()
        self.all_results["total_duration_seconds"] = (
            self.end_time - self.start_time
        ).total_seconds()
        
        # Rename experiment folder with end timestamp
        end_timestamp = self.end_time.strftime("%Y%m%d_%H%M%S")
        new_name = f"narrative_eval-{self.start_timestamp}-{end_timestamp}-{self.experiment_id}"
        new_dir = self.experiment_dir.parent / new_name
        
        self._save_results()
        self._generate_report()
        
        # Rename directory
        try:
            self.experiment_dir.rename(new_dir)
            self.experiment_dir = new_dir
            self.logger.info(f"Renamed experiment folder to: {new_name}")
        except Exception as e:
            self.logger.error(f"Could not rename folder: {e}")
            
        self.logger.info("\n" + "=" * 60)
        self.logger.info("EXPERIMENT COMPLETED")
        self.logger.info(f"Total duration: {self.all_results['total_duration_seconds']:.2f} seconds")
        self.logger.info(f"Results saved to: {self.experiment_dir}")
        self.logger.info("=" * 60)
        
        self.logger.close()
        return self.all_results
        
    def _save_results(self):
        """Save current results to JSON."""
        results_path = self.experiment_dir / "summary.json"
        results_path.write_text(json.dumps(self.all_results, indent=2, default=str))
        
    def _generate_report(self):
        """Generate markdown report for academic paper."""
        report_path = self.experiment_dir / "report.md"
        
        report = []
        report.append("# Narrative Evaluation Experiment Report")
        report.append("")
        report.append(f"**Experiment ID:** {self.experiment_id}")
        report.append(f"**Start Time:** {self.start_time.isoformat()}")
        report.append(f"**End Time:** {self.end_time.isoformat()}")
        report.append(f"**Total Duration:** {self.all_results['total_duration_seconds']:.2f} seconds")
        report.append("")
        
        # Configuration
        report.append("## 1. Experiment Configuration")
        report.append("")
        report.append(f"- **Models tested:** {', '.join([MODEL_CONFIGS[m]['name'] for m in self.models])}")
        report.append(f"- **K-fold values:** {self.k_values}")
        report.append(f"- **Chapters per book:** {self.chapters_per_book}")
        report.append(f"- **Books analyzed:** {len(self.all_results['books'])}")
        report.append("")
        
        # Books table
        report.append("### Books in Dataset")
        report.append("")
        report.append("| Book | Original Chapters | Modified Chapters |")
        report.append("|------|------------------|-------------------|")
        for book in self.all_results["books"]:
            report.append(f"| {book['name']} | {len(book['original_chapters'])} | {len(book['modified_chapters'])} |")
        report.append("")
        
        # Error categories
        report.append("## 2. Error Categories")
        report.append("")
        report.append("The linter detects errors in 5 categories:")
        report.append("")
        report.append("1. **Causality** - Chekhov's gun violations, unexplained effects, missing causes")
        report.append("2. **Coherence** - Semantic incorrectness, logical inconsistencies")
        report.append("3. **Temporal** - Time interval violations, ordering errors")
        report.append("4. **Location** - Spatial constraint violations, ubiquity errors")
        report.append("5. **Emotional** - Character behavior inconsistent with relationships")
        report.append("")
        
        # Results per model
        report.append("## 3. Results by Model")
        report.append("")
        
        for model_key, model_results in self.all_results.get("model_results", {}).items():
            model_name = MODEL_CONFIGS.get(model_key, {}).get("name", model_key)
            report.append(f"### 3.{self.models.index(model_key)+1}. {model_name}")
            report.append("")
            
            duration = model_results.get("duration_seconds", 0)
            report.append(f"**Processing time:** {duration:.2f} seconds")
            report.append("")
            
            # K-fold results table
            report.append("#### Results by K-fold")
            report.append("")
            report.append("| K | Total Errors | False Positives | True Errors |")
            report.append("|---|--------------|-----------------|-------------|")
            
            for k_str, k_results in model_results.get("k_fold_results", {}).items():
                agg = k_results.get("aggregated", {})
                total = agg.get("total_errors_found", 0) + agg.get("total_false_positives", 0)
                fps = agg.get("total_false_positives", 0)
                true_errors = agg.get("total_errors_found", 0)
                report.append(f"| {k_str} | {total} | {fps} | {true_errors} |")
                
            report.append("")
            
            # Category breakdown for k=1 (or first k)
            if model_results.get("k_fold_results"):
                first_k = list(model_results["k_fold_results"].keys())[0]
                agg = model_results["k_fold_results"][first_k].get("aggregated", {})
                cats = agg.get("errors_by_category", {})
                
                if cats:
                    report.append(f"#### Errors by Category (k={first_k})")
                    report.append("")
                    report.append("| Category | Count |")
                    report.append("|----------|-------|")
                    for cat in ERROR_CATEGORIES:
                        count = cats.get(cat, 0)
                        report.append(f"| {cat.capitalize()} | {count} |")
                    report.append("")
                    
                # Source breakdown
                sources = agg.get("errors_by_source", {})
                if sources:
                    report.append("#### Errors by Detection Method")
                    report.append("")
                    report.append("| Method | Count |")
                    report.append("|--------|-------|")
                    for source, count in sources.items():
                        method_name = "LLM Direct" if source == "llm" else "Logic (ASP)"
                        report.append(f"| {method_name} | {count} |")
                    report.append("")
                    
        # Comparative analysis
        report.append("## 4. Comparative Analysis")
        report.append("")
        
        if len(self.models) > 1:
            report.append("### Model Comparison")
            report.append("")
            report.append("| Metric | " + " | ".join([MODEL_CONFIGS[m]["name"] for m in self.models]) + " |")
            report.append("|--------|" + "|".join(["------" for _ in self.models]) + "|")
            
            # Compare total errors across models
            row = ["Total Errors Found"]
            for model_key in self.models:
                model_results = self.all_results.get("model_results", {}).get(model_key, {})
                total = 0
                for k_results in model_results.get("k_fold_results", {}).values():
                    total += k_results.get("aggregated", {}).get("total_errors_found", 0)
                row.append(str(total))
            report.append("| " + " | ".join(row) + " |")
            
            # Compare false positives
            row = ["False Positives"]
            for model_key in self.models:
                model_results = self.all_results.get("model_results", {}).get(model_key, {})
                total = 0
                for k_results in model_results.get("k_fold_results", {}).values():
                    total += k_results.get("aggregated", {}).get("total_false_positives", 0)
                row.append(str(total))
            report.append("| " + " | ".join(row) + " |")
            
            # Compare processing time
            row = ["Processing Time (s)"]
            for model_key in self.models:
                model_results = self.all_results.get("model_results", {}).get(model_key, {})
                duration = model_results.get("duration_seconds", 0)
                row.append(f"{duration:.1f}")
            report.append("| " + " | ".join(row) + " |")
            
            report.append("")
            
        # Methodology notes
        report.append("## 5. Methodology")
        report.append("")
        report.append("### 5.1 Approach")
        report.append("")
        report.append("This experiment compares two approaches to narrative consistency checking:")
        report.append("")
        report.append("1. **LLM Direct Linting**: The story is provided to an LLM with a prompt asking it to identify inconsistencies. This approach leverages the LLM's world knowledge and contextual understanding.")
        report.append("")
        report.append("2. **Logic-Based Linting (ASP)**: The story is first converted to structured JSON by an LLM, then transformed into Answer Set Programming (ASP) facts. The Clingo solver applies formal rules to detect violations.")
        report.append("")
        report.append("### 5.2 Cross-Validation")
        report.append("")
        report.append("K-fold cross-validation is used to evaluate generalization:")
        report.append("")
        report.append("- Original books serve as training/baseline (errors found are considered false positives)")
        report.append("- Modified books serve as test set (known injected errors)")
        report.append("- Errors found in test that don't match baseline patterns are counted as true positives")
        report.append("")
        report.append("### 5.3 Error Categories")
        report.append("")
        report.append("Errors are classified into 5 categories based on keyword matching and violation types from the ASP rules.")
        report.append("")
        
        # Conclusions
        report.append("## 6. Conclusions")
        report.append("")
        report.append("*Analysis to be completed based on full experiment results.*")
        report.append("")
        
        # Write report
        report_path.write_text("\n".join(report))
        self.logger.info(f"Generated report: {report_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run narrative evaluation experiment",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--models",
        default="gemma,r1",
        help="Comma-separated list of models to test (gemma, r1)"
    )
    parser.add_argument(
        "--k-values",
        default="1,2,3,4",
        help="Comma-separated list of k values for cross-validation"
    )
    parser.add_argument(
        "--chapters-per-book",
        type=int,
        default=1,
        help="Number of chapters per book (pilot = 1)"
    )
    parser.add_argument(
        "--output-dir",
        default="experiments",
        help="Base directory for experiment output"
    )
    
    args = parser.parse_args()
    
    # Parse arguments
    models = [m.strip() for m in args.models.split(",")]
    k_values = [int(k.strip()) for k in args.k_values.split(",")]
    output_dir = REPO_ROOT / args.output_dir
    
    # Create and run experiment
    experiment = NarrativeExperiment(
        output_dir=output_dir,
        models=models,
        k_values=k_values,
        chapters_per_book=args.chapters_per_book
    )
    
    results = experiment.run()
    
    # Print summary to stdout
    print(json.dumps({
        "experiment_dir": str(experiment.experiment_dir),
        "total_duration_seconds": results["total_duration_seconds"],
        "models_tested": len(models),
    }, indent=2))


if __name__ == "__main__":
    main()
