#!/usr/bin/env python3
"""
run_experiments_sequential.py (converted from bash)
Run 10-chapter and all-chapter experiments sequentially.
"""

import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
os.chdir(REPO_ROOT)

LOG_FILE = REPO_ROOT / "experiments" / "sequential_experiments.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    """Log to both console and file."""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def is_running(pattern: str) -> bool:
    """Check if a process matching pattern is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    log("===== SEQUENTIAL EXPERIMENT RUNNER =====")
    
    # Check if 10-chapter experiment is still running
    while is_running("narrative_eval_10ch"):
        log("Waiting for 10-chapter experiment to complete...")
        time.sleep(300)  # Check every 5 minutes
    
    log("10-chapter experiment completed or not running")
    
    # Start the ALL chapters experiment
    log("Starting ALL chapters experiment...")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "run_comprehensive_experiment.py"),
            "--max-chapters", "999",
            "--name", "narrative_eval_ALL",
            "--llm-timeout", "1800"
        ],
        cwd=str(REPO_ROOT)
    )
    
    log("ALL chapters experiment completed")
    
    # Generate reports for both experiments
    log("Generating academic reports...")
    
    exp_base = REPO_ROOT / "experiments"
    for pattern in ["narrative_eval_10ch-*", "narrative_eval_ALL-*"]:
        for exp_dir in exp_base.glob(pattern):
            if exp_dir.is_dir():
                log(f"Generating report for: {exp_dir}")
                
                # Run logic lint
                try:
                    subprocess.run(
                        [sys.executable, str(SCRIPT_DIR / "run_logic_lint_only.py"), str(exp_dir)],
                        cwd=str(REPO_ROOT)
                    )
                except Exception as e:
                    log(f"Logic lint error: {e}")
                
                # Generate academic report
                try:
                    subprocess.run(
                        [sys.executable, str(SCRIPT_DIR / "generate_academic_report.py"), str(exp_dir)],
                        cwd=str(REPO_ROOT)
                    )
                except Exception as e:
                    log(f"Report generation error: {e}")
    
    log("===== ALL EXPERIMENTS COMPLETE =====")


if __name__ == "__main__":
    main()
