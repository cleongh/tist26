#!/usr/bin/env python3
# =============================================================================
# run_pilot_experiment.py - Execute the Narrative Evaluation Pilot Experiment
# =============================================================================
# CONVERTED FROM BASH TO PYTHON
#
# This script runs the full pilot experiment comparing LLM-based and logic-based
# narrative evaluation. It:
#
# 1. Tests clingo is available
# 2. Runs the Gemma 3 12B model experiment
# 3. Runs the R1 Distill Qwen model experiment
# 4. Generates comprehensive reports
#
# Usage:
#   python3 scripts/run_pilot_experiment.py
#
# Output:
#   experiments/pilot_<timestamp>_<uuid>/
#     - config.json
#     - log.txt
#     - stories/
#     - results/
#     - report.md
#     - summary.json
#
# =============================================================================

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent

os.chdir(REPO_ROOT)

def print_banner(text):
    print("=" * 46)
    print(text)
    print("=" * 46)

def check_dependency(module_name):
    """Check if a Python module is available."""
    try:
        mod = __import__(module_name)
        version = getattr(mod, '__version__', 'available')
        print(f"  ✓ {module_name}: {version}")
        return True
    except ImportError as e:
        print(f"  ✗ {module_name}: NOT found ({e})")
        return False

def check_file(path, name):
    """Check if a file exists."""
    if Path(path).exists():
        print(f"  ✓ {name} found")
        return True
    else:
        print(f"  ✗ {name} NOT found")
        return False

def count_files(directory):
    """Count files in a directory."""
    d = Path(directory)
    if d.exists():
        return len(list(d.iterdir()))
    return 0

def main():
    print_banner("NARRATIVE EVALUATION PILOT EXPERIMENT")
    print(f"Start time: {datetime.now().isoformat()}")
    print()

    # Check dependencies
    print("Checking dependencies...")
    deps_ok = True
    deps_ok &= check_dependency("clingo")
    deps_ok &= check_dependency("json")
    
    if not deps_ok:
        print("\nMissing dependencies. Please install required packages.")
        sys.exit(1)

    # Check LLM scripts
    scripts_ok = True
    scripts_ok &= check_file("/home/cleon/programas/gemma.sh", "Gemma script")
    scripts_ok &= check_file("/home/cleon/programas/r1_distill_qwen.sh", "R1 Distill Qwen script")
    
    if not scripts_ok:
        print("\nMissing LLM model scripts.")
        sys.exit(1)

    # Check books
    print()
    print("Available books:")
    original_count = count_files(REPO_ROOT / "original_books")
    modified_count = count_files(REPO_ROOT / "modified_books")
    print(f"  Original: {original_count} books")
    print(f"  Modified: {modified_count} books")
    print()

    # Run experiment
    print("Starting experiment runner...")
    print("This will:")
    print("  - Process 2 chapters per book")
    print("  - Run k-fold cross-validation (k=1,2,3,4)")
    print("  - Compare Gemma 3 12B and R1 Distill Qwen")
    print()

    # Call the experiment script
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "pilot_kfold_experiment.py"),
        "--chapters-per-book", "2",
        "--timeout", "600",
        "--k-values", "1,2,3,4",
        "--models", "gemma:/home/cleon/programas/gemma.sh,r1_qwen:/home/cleon/programas/r1_distill_qwen.sh",
        "--server-wait", "45"
    ]
    
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    
    print()
    print_banner("EXPERIMENT COMPLETE")
    print(f"End time: {datetime.now().isoformat()}")
    
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
