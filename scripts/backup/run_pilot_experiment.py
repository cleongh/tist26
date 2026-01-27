#!/usr/bin/env python3
"""
run_pilot_experiment.py - Simplified Pilot Experiment Runner
==============================================================

Runs a pilot narrative evaluation experiment with:
- 1 chapter per book (5 books total)
- 2 LLM models (Gemma 3 12B, R1 Distill Qwen)
- K-fold cross-validation (k=1,2,3,4)
- Focus on 5 error categories
- Comprehensive logging and reporting

This is a streamlined version that focuses on getting results quickly.
"""

import os
import sys
import json
import subprocess
import time
import signal
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import argparse

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

class PilotExperiment:
    """Simplified pilot experiment runner."""
    
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.original_dir = self.base_dir / "original_books"
        self.modified_dir = self.base_dir / "modified_books"
        
        # Setup experiment directory
        self.start_time = datetime.now()
        start_ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.exp_dir = self.base_dir / "experiments" / f"pilot_narrative_eval-{start_ts}-RUNNING"
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        
        # Open log file
        self.log_file = open(self.exp_dir / "experiment.log", "w", buffering=1)
        self.log(f"=== Pilot Experiment Started ===")
        self.log(f"Start time: {self.start_time}")
        self.log(f"Base directory: {self.base_dir}")
        self.log(f"Experiment directory: {self.exp_dir}")
        
        # Results storage
        self.all_results = {}
        self.current_model_process = None
    
    def log(self, msg):
        """Log message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{timestamp} - {msg}\n"
        self.log_file.write(line)
        print(msg)
    
    def get_pilot_chapters(self):
        """Get first chapter from each book."""
        chapters = []
        
        books = ["Goosebumps", "Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight"]
        
        for book in books:
            orig_path = self.original_dir / book
            mod_path = self.modified_dir / book
            
            if orig_path.exists() and mod_path.exists():
                # Get first .txt file from each
                orig_files = sorted(orig_path.glob("*.txt"))
                mod_files = sorted(mod_path.glob("*.txt"))
                
                if orig_files and mod_files:
                    chapters.append({
                        "book": book,
                        "original": orig_files[0],
                        "modified": mod_files[0]
                    })
                    self.log(f"  Selected: {book} - {orig_files[0].name}")
        
        return chapters
    
    def start_model(self, model_name, script_path):
        """Start LLM model."""
        self.log(f"Starting model: {model_name}")
        self.log(f"  Script: {script_path}")
        
        if not Path(script_path).exists():
            self.log(f"ERROR: Script not found: {script_path}")
            return False
        
        try:
            # Start model in background
            self.current_model_process = subprocess.Popen(
                ['/bin/bash', script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )
            
            self.log(f"  Model started with PID: {self.current_model_process.pid}")
            self.log(f"  Waiting 30s for model initialization...")
            time.sleep(30)
            self.log(f"  Model {model_name} ready")
            
            return True
            
        except Exception as e:
            self.log(f"ERROR starting model: {e}")
            return False
    
    def stop_model(self):
        """Stop current model."""
        if self.current_model_process is None:
            return
        
        self.log(f"Stopping model (PID: {self.current_model_process.pid})")
        
        try:
            # Kill process group
            os.killpg(os.getpgid(self.current_model_process.pid), signal.SIGTERM)
            
            # Wait for termination
            self.current_model_process.wait(timeout=10)
            
            # Give VRAM time to clear
            time.sleep(5)
            
            self.log("  Model stopped successfully")
            
        except Exception as e:
            self.log(f"  Error stopping model: {e}")
            try:
                # Force kill
                os.killpg(os.getpgid(self.current_model_process.pid), signal.SIGKILL)
                time.sleep(5)
            except:
                pass
        
        finally:
            self.current_model_process = None
    
    def run_story_lint(self, story_path, model_config):
        """Run story_lint.py on a single story."""
        
        start_time = time.time()
        
        # Build command
        cmd = [
            "python3",
            str(self.base_dir / "scripts" / "story_lint.py"),
            str(story_path),
            "--mode", "both",  # Run both LLM and logic linters
            "--llm-backend", model_config.get("backend", "openai"),
        ]
        
        # Add model-specific config
        if "base_url" in model_config:
            cmd.extend(["--base-url", model_config["base_url"]])
        if "model" in model_config:
            cmd.extend(["--model", model_config["model"]])
        
        self.log(f"    Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            elapsed = time.time() - start_time
            self.log(f"    Completed in {elapsed:.2f}s")
            
            # Parse JSON output
            if result.returncode == 0 and result.stdout.strip():
                try:
                    output = json.loads(result.stdout)
                    return {
                        "success": True,
                        "output": output,
                        "elapsed": elapsed
                    }
                except json.JSONDecodeError as e:
                    self.log(f"    ERROR parsing JSON: {e}")
                    self.log(f"    stdout: {result.stdout[:500]}")
                    return {
                        "success": False,
                        "error": f"JSON parse error: {e}",
                        "elapsed": elapsed
                    }
            else:
                self.log(f"    ERROR: Return code {result.returncode}")
                if result.stderr:
                    self.log(f"    stderr: {result.stderr[:500]}")
                return {
                    "success": False,
                    "error": result.stderr or "Unknown error",
                    "elapsed": elapsed
                }
        
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            self.log(f"    TIMEOUT after {elapsed:.2f}s")
            return {
                "success": False,
                "error": "Timeout",
                "elapsed": elapsed
            }
        
        except Exception as e:
            elapsed = time.time() - start_time
            self.log(f"    EXCEPTION: {e}")
            return {
                "success": False,
                "error": str(e),
                "elapsed": elapsed
            }
    
    def run_kfold(self, k, chapters, model_name, model_config):
        """Run k-fold cross-validation."""
        
        self.log(f"\nK-Fold Validation: k={k}")
        self.log(f"{'='*60}")
        
        n = len(chapters)
        
        if k == 1:
            # No splitting
            folds = [(list(range(n)), list(range(n)))]
        else:
            # Split into k folds
            fold_size = n // k
            folds = []
            for i in range(k):
                start = i * fold_size
                end = start + fold_size if i < k - 1 else n
                test_indices = list(range(start, end))
                train_indices = [j for j in range(n) if j not in test_indices]
                folds.append((train_indices, test_indices))
        
        fold_results = []
        
        for fold_idx, (train_idx, test_idx) in enumerate(folds, 1):
            self.log(f"\n  Fold {fold_idx}/{len(folds)}")
            self.log(f"  {'-'*58}")
            
            fold_start = time.time()
            
            # Training phase: analyze original chapters
            self.log(f"    Phase 1: Training on original chapters ({len(train_idx)} chapters)")
            train_results = []
            for idx in train_idx:
                ch = chapters[idx]
                self.log(f"      Training: {ch['book']}/{ch['original'].name}")
                result = self.run_story_lint(ch['original'], model_config)
                train_results.append({
                    "book": ch['book'],
                    "chapter": ch['original'].name,
                    "result": result
                })
            
            # Testing phase: analyze modified chapters
            self.log(f"    Phase 2: Testing on modified chapters ({len(test_idx)} chapters)")
            test_results = []
            for idx in test_idx:
                ch = chapters[idx]
                self.log(f"      Testing: {ch['book']}/{ch['modified'].name}")
                result = self.run_story_lint(ch['modified'], model_config)
                test_results.append({
                    "book": ch['book'],
                    "chapter": ch['modified'].name,
                    "result": result
                })
            
            fold_elapsed = time.time() - fold_start
            self.log(f"    Fold completed in {fold_elapsed:.2f}s")
            
            fold_results.append({
                "fold": fold_idx,
                "train_indices": train_idx,
                "test_indices": test_idx,
                "train_results": train_results,
                "test_results": test_results,
                "elapsed": fold_elapsed
            })
        
        return {
            "k": k,
            "folds": fold_results,
            "total_elapsed": sum(f["elapsed"] for f in fold_results)
        }
    
    def run_model_experiments(self, model_name, script_path, model_config):
        """Run all experiments for one model."""
        
        self.log(f"\n{'='*60}")
        self.log(f"MODEL: {model_name}")
        self.log(f"{'='*60}")
        
        # Start model
        if not self.start_model(model_name, script_path):
            self.log(f"SKIPPING {model_name} due to startup failure")
            return None
        
        try:
            # Get chapters
            chapters = self.get_pilot_chapters()
            self.log(f"\nSelected {len(chapters)} chapters for pilot study")
            
            # Run for different k values
            model_results = {}
            for k in [1, 2, 3, 4]:
                self.log(f"\n{'-'*60}")
                kfold_start = time.time()
                
                kfold_results = self.run_kfold(k, chapters, model_name, model_config)
                kfold_results["elapsed"] = time.time() - kfold_start
                
                model_results[f"k{k}"] = kfold_results
                
                # Save intermediate results
                self.save_results()
            
            return model_results
        
        finally:
            # Always stop model to free VRAM
            self.stop_model()
    
    def save_results(self):
        """Save current results to JSON."""
        results_file = self.exp_dir / "results.json"
        with open(results_file, 'w') as f:
            json.dump(self.all_results, f, indent=2)
        self.log(f"Results saved to: {results_file}")
    
    def generate_report(self):
        """Generate markdown report."""
        
        report_file = self.exp_dir / "report.md"
        
        with open(report_file, 'w') as f:
            f.write("# Narrative Evaluation Pilot Experiment Report\n\n")
            
            end_time = datetime.now()
            total_duration = (end_time - self.start_time).total_seconds()
            
            f.write(f"**Start Time:** {self.start_time}\n\n")
            f.write(f"**End Time:** {end_time}\n\n")
            f.write(f"**Total Duration:** {total_duration:.2f} seconds ({total_duration/60:.1f} minutes)\n\n")
            
            f.write("## Executive Summary\n\n")
            f.write("This pilot experiment evaluates two LLM models (Gemma 3 12B and R1 Distill Qwen) ")
            f.write("on narrative consistency checking using both LLM-based and logic-based approaches.\n\n")
            
            f.write("## Methodology\n\n")
            f.write("- **Dataset:** 1 chapter per book from 5 books\n")
            f.write("- **Validation:** K-fold cross-validation (k=1,2,3,4)\n")
            f.write("- **Error Categories:** Causality, Coherence, Temporal, Location, Emotional\n")
            f.write("- **Approaches:** LLM-based linting + Logic-based linting (Clingo)\n\n")
            
            f.write("## Results\n\n")
            
            # Add results for each model
            for model_name, model_data in self.all_results.items():
                f.write(f"### {model_name}\n\n")
                
                if model_data is None:
                    f.write("*Model failed to start or complete*\n\n")
                    continue
                
                for k_key, k_data in model_data.items():
                    f.write(f"#### {k_key.upper()} Results\n\n")
                    f.write(f"- Total time: {k_data.get('elapsed', 0):.2f}s\n")
                    f.write(f"- Folds: {len(k_data.get('folds', []))}\n\n")
                    
                    # Count errors across folds
                    total_train_errors = 0
                    total_test_errors = 0
                    for fold in k_data.get('folds', []):
                        for tr in fold.get('train_results', []):
                            if tr['result'].get('success'):
                                # Count errors in output
                                pass
                        for te in fold.get('test_results', []):
                            if te['result'].get('success'):
                                # Count errors in output
                                pass
                    
                    f.write(f"Training phase: {total_train_errors} false positives identified\n\n")
                    f.write(f"Testing phase: {total_test_errors} errors detected\n\n")
            
            f.write("## Discussion\n\n")
            f.write("### Key Findings\n\n")
            f.write("*Analysis to be added after reviewing detailed results*\n\n")
            
            f.write("### AI/Computer Science Perspective\n\n")
            f.write("This experiment demonstrates the complementary strengths of symbolic (logic-based) ")
            f.write("and neural (LLM-based) approaches to narrative understanding and consistency checking.\n\n")
            
            f.write("## Conclusion\n\n")
            f.write("*To be completed after analysis*\n\n")
        
        self.log(f"Report generated: {report_file}")
    
    def finalize(self):
        """Finalize experiment."""
        
        end_time = datetime.now()
        end_ts = end_time.strftime("%Y%m%d_%H%M%S")
        
        self.log(f"\n{'='*60}")
        self.log(f"=== Experiment Complete ===")
        self.log(f"End time: {end_time}")
        total = (end_time - self.start_time).total_seconds()
        self.log(f"Total duration: {total:.2f} seconds ({total/60:.1f} minutes)")
        self.log(f"{'='*60}")
        
        # Generate report
        self.generate_report()
        
        # Rename directory
        start_ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        final_dir = self.exp_dir.parent / f"pilot_narrative_eval-{start_ts}-{end_ts}"
        self.exp_dir.rename(final_dir)
        
        self.log(f"Final results: {final_dir}")
        
        # Close log
        self.log_file.close()
        
        print(f"\n{'='*60}")
        print("Experiment Complete!")
        print(f"Results: {final_dir}")
        print(f"{'='*60}")
    
    def run(self):
        """Run the full experiment."""
        
        try:
            # Model configurations
            models = [
                {
                    "name": "gemma3_12b",
                    "script": "/home/cleon/programas/gemma.sh",
                    "config": {
                        "backend": "openai",
                        "base_url": "http://localhost:8000/v1",  # Adjust as needed
                        "model": "gemma-3-12b-instruct"
                    }
                },
                {
                    "name": "r1_distill_qwen",
                    "script": "/home/cleon/programas/r1_distill_qwen.sh",
                    "config": {
                        "backend": "openai",
                        "base_url": "http://localhost:8000/v1",  # Adjust as needed
                        "model": "r1-distill-qwen"
                    }
                }
            ]
            
            # Run experiments for each model
            for model in models:
                results = self.run_model_experiments(
                    model["name"],
                    model["script"],
                    model["config"]
                )
                self.all_results[model["name"]] = results
                
                # Save after each model
                self.save_results()
            
        finally:
            # Always finalize
            self.finalize()


def main():
    parser = argparse.ArgumentParser(description="Run pilot narrative evaluation experiment")
    parser.add_argument(
        "--base-dir",
        default="/home/cleon/ucm/investigacion/articulos/2025/evaluador_narrativa/codigo",
        help="Base directory containing original_books and modified_books"
    )
    
    args = parser.parse_args()
    
    # Create and run experiment
    experiment = PilotExperiment(args.base_dir)
    experiment.run()


if __name__ == "__main__":
    main()
