#!/usr/bin/env python3
"""
incremental_linter.py - Main CLI for Incremental Narrative Consistency Checking
================================================================================

This is the main entry point for running incremental narrative consistency experiments.

KEY PRINCIPLE: COMPLETE ISOLATION
─────────────────────────────────

Each experiment runs in TOTAL ISOLATION:
    
    $ python incremental_linter.py run-story original_books/Goosebumps/
    → Fresh LLM session
    → Fresh ILASP/Clingo state
    → Processes chapters 000.txt, 001.txt, ...
    → Reports: 0 errors (consistent story)
    
    $ python incremental_linter.py run-story modified_books/Goosebumps/
    → COMPLETELY NEW fresh LLM session
    → COMPLETELY NEW fresh ILASP/Clingo state
    → Knows NOTHING from the original experiment
    → Processes chapters, finds INTERNAL inconsistencies
    → Reports: N errors (based on self-contradictions)

COMMANDS:
─────────

    run-story <story_dir>
        Process all .txt chapter files in a directory
        
    run-all <base_dir>
        Process all story directories under a base path
        
    compare <original_dir> <modified_dir>
        Run both, then compare error counts

USAGE:
──────

    # Single story experiment
    python incremental_linter.py run-story original_books/Goosebumps/
    
    # Run all original books
    python incremental_linter.py run-all original_books/
    
    # Compare original vs modified
    python incremental_linter.py compare original_books/Goosebumps/ modified_books/Goosebumps/

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from ilasp_learner import ILASPLearner, StoryKnowledge

# Default output directory
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parent / "experiment_results"


# Available local models
LOCAL_MODELS = ["mistral-7b", "gemma-3-12b", "deepseek-r1-7b"]


class ExperimentConfig:
    """Configuration for an experiment run."""
    
    def __init__(
        self,
        story_dir: Path,
        experiment_id: Optional[str] = None,
        output_dir: Optional[Path] = None,
        llm_model: str = "mistral-7b",
        llm_provider: str = "local",
        llm_port: int = 8080,
        verbose: bool = True,
    ):
        self.story_dir = Path(story_dir).resolve()
        self.experiment_id = experiment_id or self._generate_experiment_id()
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.llm_model = llm_model
        self.llm_provider = llm_provider
        self.llm_port = llm_port
        self.verbose = verbose
        
        # Validate story directory
        if not self.story_dir.is_dir():
            raise ValueError(f"Story directory does not exist: {self.story_dir}")
    
    def _generate_experiment_id(self) -> str:
        """Generate unique experiment ID."""
        story_name = self.story_dir.name
        parent_name = self.story_dir.parent.name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{parent_name}_{story_name}_{timestamp}"


class IncrementalLinter:
    """
    Main linter class that orchestrates incremental narrative checking.
    
    IMPORTANT: Each instance represents ONE ISOLATED EXPERIMENT.
    The LLM server is started FRESH for each experiment and killed after.
    """
    
    def __init__(self, config: ExperimentConfig):
        """Initialize a FRESH linter for one experiment."""
        self.config = config
        
        # FRESH LLM server (started fresh, killed after experiment)
        self.llm_server = None
        self._owns_server = False  # Whether we started the server
        
        # FRESH ILASP learner (clean state)
        self.learner = ILASPLearner(
            experiment_id=config.experiment_id,
            verbose=config.verbose,
        )
        
        # Results for this experiment only
        self.results = {
            "experiment_id": config.experiment_id,
            "story_dir": str(config.story_dir),
            "start_time": None,
            "end_time": None,
            "chapters": [],
            "total_violations": 0,
            "violations_by_category": {},
        }
    
    def log(self, msg: str) -> None:
        """Log message if verbose."""
        if self.config.verbose:
            print(f"[Linter:{self.config.experiment_id}] {msg}", file=sys.stderr)
    
    def run(self) -> Dict[str, Any]:
        """Run the complete experiment with FRESH LLM server."""
        self.results["start_time"] = datetime.now().isoformat()
        
        # Start FRESH LLM server for this experiment
        self._start_fresh_llm_server()
        
        try:
            return self._run_experiment()
        finally:
            # ALWAYS kill the server after experiment (ensures clean state)
            self._stop_llm_server()
    
    def _run_experiment(self) -> Dict[str, Any]:
        """Internal experiment execution."""
        # Get all chapter files (sorted)
        chapter_files = self._get_chapter_files()
        
        if not chapter_files:
            self.log(f"No chapter files found in {self.config.story_dir}")
            self.results["end_time"] = datetime.now().isoformat()
            return self.results
        
        self.log(f"Found {len(chapter_files)} chapters to process")
        
        # Process each chapter
        for i, chapter_path in enumerate(chapter_files):
            chapter_num = i + 1
            self.log(f"\n{'='*60}")
            self.log(f"Processing chapter {chapter_num}: {chapter_path.name}")
            
            chapter_result = self._process_chapter(chapter_path, chapter_num)
            self.results["chapters"].append(chapter_result)
            
            # Accumulate violations
            for violation in chapter_result.get("violations", []):
                self.results["total_violations"] += 1
                category = violation.get("category", "unknown")
                self.results["violations_by_category"][category] = \
                    self.results["violations_by_category"].get(category, 0) + 1
        
        self.results["end_time"] = datetime.now().isoformat()
        
        # Print summary
        self._print_summary()
        
        # Save results
        self._save_results()
        
        return self.results
    
    def _get_chapter_files(self) -> List[Path]:
        """Get all chapter files sorted by name."""
        files = []
        for ext in (".txt", ".md"):
            files.extend(self.config.story_dir.glob(f"*{ext}"))
        
        # Sort by filename (expects 000.txt, 001.txt, ... format)
        return sorted(files, key=lambda p: p.stem)
    
    def _process_chapter(
        self,
        chapter_path: Path,
        chapter_num: int,
    ) -> Dict[str, Any]:
        """Process a single chapter through the pipeline."""
        result = {
            "chapter_num": chapter_num,
            "file": chapter_path.name,
            "violations": [],
            "entities_found": 0,
            "events_found": 0,
        }
        
        # Step 1: Read chapter text
        try:
            text = chapter_path.read_text(encoding="utf-8")
        except Exception as e:
            self.log(f"  Error reading file: {e}")
            result["error"] = str(e)
            return result
        
        # Step 2: Structure text using LLM
        structured = self._structure_with_llm(text, chapter_num)
        
        if not structured:
            self.log(f"  Failed to structure chapter")
            result["error"] = "LLM structuring failed"
            return result
        
        result["entities_found"] = len(structured.get("entities", {}).get("characters", []))
        result["events_found"] = len(structured.get("events", []))
        
        # Step 3: Process with learner (check + learn)
        violations = self.learner.process_chapter(
            structured_json=structured,
            chapter_num=chapter_num,
            chapter_text=text,
        )
        
        result["violations"] = violations
        
        return result
    
    def _structure_with_llm(self, text: str, chapter_num: int) -> Optional[Dict]:
        """Structure narrative text using LLM."""
        if self.llm_server is None or not self.llm_server.is_running():
            # Fallback to simple structuring
            return self._simple_structure(text, chapter_num)
        
        try:
            structured = self.llm_server.structure_narrative(text)
            return structured
        except Exception as e:
            self.log(f"  LLM error: {e}")
            return self._simple_structure(text, chapter_num)
    
    def _start_fresh_llm_server(self) -> None:
        """Start a FRESH LLM server for this experiment."""
        if self.config.llm_provider != "local":
            self.log(f"Using external LLM provider: {self.config.llm_provider}")
            return
        
        try:
            from llm_server import LlamafileServer
            
            self.log(f"Starting FRESH LLM server: {self.config.llm_model}")
            self.llm_server = LlamafileServer(
                model=self.config.llm_model,
                port=self.config.llm_port,
                verbose=self.config.verbose,
                auto_start=True,
            )
            self._owns_server = True
            self.log(f"LLM server ready at port {self.config.llm_port}")
        except Exception as e:
            self.log(f"Could not start LLM server: {e}")
            self.log("Will use fallback text structuring")
            self.llm_server = None
    
    def _stop_llm_server(self) -> None:
        """Stop the LLM server (ensures clean state for next experiment)."""
        if self._owns_server and self.llm_server is not None:
            self.log("Stopping LLM server (cleaning state)...")
            try:
                self.llm_server.stop()
            except Exception as e:
                self.log(f"Error stopping server: {e}")
            self.llm_server = None
            self._owns_server = False
    
    def _simple_structure(self, text: str, chapter_num: int) -> Dict:
        """Simple fallback structuring when LLM is not available."""
        import re
        
        # Basic extraction
        entities = {
            "characters": [],
            "objects": [],
            "locations": [],
        }
        events = []
        
        # Find quoted speech -> characters
        speakers = set()
        for match in re.finditer(r'"[^"]+"\s*(?:said|asked|replied|shouted)\s+(\w+)', text, re.I):
            speakers.add(match.group(1))
        for match in re.finditer(r'(\w+)\s+(?:said|asked|replied|shouted)\s*"', text, re.I):
            speakers.add(match.group(1))
        
        for i, speaker in enumerate(speakers):
            entities["characters"].append({
                "id": f"char_{speaker.lower()}",
                "name": speaker,
            })
        
        # Find action verbs -> events
        action_patterns = [
            (r'(\w+)\s+(walked|ran|went|moved|entered|left)', "move"),
            (r'(\w+)\s+(took|grabbed|picked up|acquired)', "take"),
            (r'(\w+)\s+(gave|handed|passed)', "give"),
            (r'(\w+)\s+(died|was killed|perished)', "die"),
        ]
        
        event_num = 1
        for pattern, event_type in action_patterns:
            for match in re.finditer(pattern, text, re.I):
                events.append({
                    "id": f"e{event_num}",
                    "type": event_type,
                    "agent": match.group(1).lower(),
                })
                event_num += 1
        
        return {
            "entities": entities,
            "events": events,
            "relationships": [],
            "traits": [],
            "fluents": [],
        }
    
    def _print_summary(self) -> None:
        """Print experiment summary."""
        print("\n" + "="*60)
        print(f"EXPERIMENT SUMMARY: {self.config.experiment_id}")
        print("="*60)
        print(f"Story: {self.config.story_dir}")
        print(f"Chapters processed: {len(self.results['chapters'])}")
        print(f"Total violations: {self.results['total_violations']}")
        
        if self.results["violations_by_category"]:
            print("\nViolations by category:")
            for category, count in sorted(self.results["violations_by_category"].items()):
                print(f"  {category}: {count}")
        
        knowledge = self.learner.get_summary()
        print(f"\nKnowledge accumulated:")
        print(f"  Characters: {knowledge['characters']}")
        print(f"  Alive: {knowledge['alive_characters']}, Dead: {knowledge['dead_characters']}")
        print(f"  Objects: {knowledge['objects']}")
        print(f"  Locations: {knowledge['locations']}")
        print(f"  Relationships: {knowledge['relationships']}")
        print(f"  Learned rules: {knowledge['learned_rules']}")
        print("="*60)
    
    def _save_results(self) -> None:
        """Save experiment results to JSON."""
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = self.config.output_dir / f"{self.config.experiment_id}.json"
        
        with open(output_path, "w") as f:
            json.dump(self.results, f, indent=2)
        
        self.log(f"Results saved to: {output_path}")


def run_story_experiment(
    story_dir: str,
    experiment_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    llm_model: str = "mistral-7b",
    llm_provider: str = "local",
    llm_port: int = 8080,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Run a single story experiment with COMPLETE ISOLATION.
    
    Each experiment gets a FRESH LLM server that is killed after.
    
    Args:
        story_dir: Path to directory containing chapter .txt files
        experiment_id: Optional ID for this experiment
        output_dir: Where to save results
        llm_model: LLM model (mistral-7b, gemma-3-12b, deepseek-r1-7b)
        llm_provider: 'local' for llamafile, or 'gemini'/'openai'
        llm_port: Port for local LLM server
        verbose: Print progress
        
    Returns:
        Experiment results dictionary
    """
    config = ExperimentConfig(
        story_dir=story_dir,
        experiment_id=experiment_id,
        output_dir=Path(output_dir) if output_dir else None,
        llm_model=llm_model,
        llm_provider=llm_provider,
        llm_port=llm_port,
        verbose=verbose,
    )
    
    # Create FRESH linter (isolated state)
    linter = IncrementalLinter(config)
    
    # Run experiment
    return linter.run()


def run_all_stories(
    base_dir: str,
    output_dir: Optional[str] = None,
    llm_model: str = "mistral-7b",
    llm_provider: str = "local",
    llm_port: int = 8080,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run experiments on all story directories under a base path.
    
    Each story gets a COMPLETELY ISOLATED experiment with fresh LLM.
    """
    base_path = Path(base_dir).resolve()
    results = []
    
    # Find story directories (those containing .txt files)
    story_dirs = []
    for subdir in sorted(base_path.iterdir()):
        if subdir.is_dir():
            if list(subdir.glob("*.txt")):
                story_dirs.append(subdir)
    
    print(f"Found {len(story_dirs)} story directories")
    
    for story_dir in story_dirs:
        print(f"\n{'#'*60}")
        print(f"# Starting experiment: {story_dir.name}")
        print(f"{'#'*60}")
        
        result = run_story_experiment(
            story_dir=str(story_dir),
            output_dir=output_dir,
            llm_model=llm_model,
            llm_provider=llm_provider,
            llm_port=llm_port,
            verbose=verbose,
        )
        results.append(result)
    
    return results


def compare_experiments(
    original_dir: str,
    modified_dir: str,
    output_dir: Optional[str] = None,
    llm_model: str = "mistral-7b",
    llm_provider: str = "local",
    llm_port: int = 8080,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Run TWO COMPLETELY ISOLATED experiments and compare results.
    
    Each experiment gets a FRESH LLM server that is killed after.
    The modified experiment knows NOTHING about the original.
    It must detect errors based on INTERNAL inconsistencies only.
    """
    print("="*60)
    print("COMPARISON EXPERIMENT")
    print("="*60)
    print(f"Original: {original_dir}")
    print(f"Modified: {modified_dir}")
    print("="*60)
    
    # Run original (ISOLATED)
    print("\n>>> RUNNING ORIGINAL (isolated experiment)")
    original_result = run_story_experiment(
        story_dir=original_dir,
        experiment_id=f"original_{Path(original_dir).name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        output_dir=output_dir,
        llm_model=llm_model,
        llm_provider=llm_provider,
        llm_port=llm_port,
        verbose=verbose,
    )
    
    # Run modified (COMPLETELY FRESH - ISOLATED)
    print("\n>>> RUNNING MODIFIED (isolated experiment - NO knowledge from original)")
    modified_result = run_story_experiment(
        story_dir=modified_dir,
        experiment_id=f"modified_{Path(modified_dir).name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        output_dir=output_dir,
        llm_model=llm_model,
        llm_provider=llm_provider,
        llm_port=llm_port,
        verbose=verbose,
    )
    
    # Comparison summary
    comparison = {
        "original": {
            "story_dir": original_dir,
            "chapters": len(original_result["chapters"]),
            "violations": original_result["total_violations"],
            "by_category": original_result["violations_by_category"],
        },
        "modified": {
            "story_dir": modified_dir,
            "chapters": len(modified_result["chapters"]),
            "violations": modified_result["total_violations"],
            "by_category": modified_result["violations_by_category"],
        },
        "detection_success": modified_result["total_violations"] > original_result["total_violations"],
        "additional_violations_found": modified_result["total_violations"] - original_result["total_violations"],
    }
    
    print("\n" + "="*60)
    print("COMPARISON RESULTS")
    print("="*60)
    print(f"Original violations: {comparison['original']['violations']}")
    print(f"Modified violations: {comparison['modified']['violations']}")
    print(f"Additional violations detected: {comparison['additional_violations_found']}")
    print(f"Detection success: {'YES' if comparison['detection_success'] else 'NO'}")
    print("="*60)
    
    return comparison


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Incremental Narrative Consistency Checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a single story experiment
  python incremental_linter.py run-story original_books/Goosebumps/
  
  # Run all stories in a directory
  python incremental_linter.py run-all original_books/
  
  # Compare original vs modified
  python incremental_linter.py compare original_books/Goosebumps/ modified_books/Goosebumps/
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # run-story command
    run_story_parser = subparsers.add_parser(
        "run-story",
        help="Run experiment on a single story directory",
    )
    run_story_parser.add_argument(
        "story_dir",
        help="Directory containing chapter .txt files",
    )
    run_story_parser.add_argument(
        "--experiment-id",
        help="Custom experiment ID",
    )
    run_story_parser.add_argument(
        "--output-dir",
        help="Output directory for results",
    )
    run_story_parser.add_argument(
        "--llm-model",
        default="mistral-7b",
        choices=["mistral-7b", "gemma-3-12b", "deepseek-r1-7b"],
        help="Local LLM model to use",
    )
    run_story_parser.add_argument(
        "--llm-provider",
        default="local",
        choices=["local", "gemini", "openai"],
        help="LLM provider (local = llamafile)",
    )
    run_story_parser.add_argument(
        "--llm-port",
        type=int,
        default=8080,
        help="Port for local LLM server",
    )
    run_story_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output",
    )
    
    # run-all command
    run_all_parser = subparsers.add_parser(
        "run-all",
        help="Run experiments on all story directories",
    )
    run_all_parser.add_argument(
        "base_dir",
        help="Base directory containing story subdirectories",
    )
    run_all_parser.add_argument(
        "--output-dir",
        help="Output directory for results",
    )
    run_all_parser.add_argument(
        "--llm-model",
        default="mistral-7b",
        choices=["mistral-7b", "gemma-3-12b", "deepseek-r1-7b"],
        help="Local LLM model to use",
    )
    run_all_parser.add_argument(
        "--llm-provider",
        default="local",
        choices=["local", "gemini", "openai"],
        help="LLM provider (local = llamafile)",
    )
    run_all_parser.add_argument(
        "--llm-port",
        type=int,
        default=8080,
        help="Port for local LLM server",
    )
    run_all_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output",
    )
    
    # compare command
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare original vs modified story experiments",
    )
    compare_parser.add_argument(
        "original_dir",
        help="Original story directory",
    )
    compare_parser.add_argument(
        "modified_dir",
        help="Modified story directory",
    )
    compare_parser.add_argument(
        "--output-dir",
        help="Output directory for results",
    )
    compare_parser.add_argument(
        "--llm-model",
        default="mistral-7b",
        choices=["mistral-7b", "gemma-3-12b", "deepseek-r1-7b"],
        help="Local LLM model to use",
    )
    compare_parser.add_argument(
        "--llm-provider",
        default="local",
        choices=["local", "gemini", "openai"],
        help="LLM provider (local = llamafile)",
    )
    compare_parser.add_argument(
        "--llm-port",
        type=int,
        default=8080,
        help="Port for local LLM server",
    )
    compare_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output",
    )
    
    args = parser.parse_args()
    
    if args.command == "run-story":
        result = run_story_experiment(
            story_dir=args.story_dir,
            experiment_id=args.experiment_id,
            output_dir=args.output_dir,
            llm_model=args.llm_model,
            llm_provider=args.llm_provider,
            llm_port=args.llm_port,
            verbose=not args.quiet,
        )
        sys.exit(0 if result["total_violations"] == 0 else 1)
    
    elif args.command == "run-all":
        results = run_all_stories(
            base_dir=args.base_dir,
            output_dir=args.output_dir,
            llm_model=args.llm_model,
            llm_provider=args.llm_provider,
            llm_port=args.llm_port,
            verbose=not args.quiet,
        )
        total_violations = sum(r["total_violations"] for r in results)
        sys.exit(0 if total_violations == 0 else 1)
    
    elif args.command == "compare":
        comparison = compare_experiments(
            original_dir=args.original_dir,
            modified_dir=args.modified_dir,
            output_dir=args.output_dir,
            llm_model=args.llm_model,
            llm_provider=args.llm_provider,
            llm_port=args.llm_port,
            verbose=not args.quiet,
        )
        # Exit 0 if modified has more violations (detection success)
        sys.exit(0 if comparison["detection_success"] else 1)


if __name__ == "__main__":
    main()
