"""
Logging utilities for the narrative experiment.

This module provides a simple logging system that writes to both console
and a log file. Logs are APPENDED across all steps of a single experiment run.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Global log file handle (set by main when experiment starts)
_console_log_file: Optional[Path] = None
_initialized: bool = False


def set_console_log_file(file_path: Path, append: bool = True):
    """
    Set the file path for console logging.
    
    Args:
        file_path: Path to the log file
        append: If True, append to existing file. If False, clear the file.
                Default is True to preserve logs across experiment steps.
    """
    global _console_log_file, _initialized
    
    # If already pointing to same file, don't reinitialize
    if _console_log_file == file_path and _initialized:
        return
    
    _console_log_file = file_path
    _initialized = True
    
    # Create parent directories
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Determine file mode
    if append and file_path.exists():
        # Append mode - add separator for new run
        mode = "a"
        header = f"\n{'=' * 60}\n=== Experiment Run Resumed: {datetime.now().isoformat()} ===\n{'=' * 60}\n\n"
    else:
        # New file or forced overwrite
        mode = "w"
        header = f"{'=' * 60}\n=== Experiment Log Started: {datetime.now().isoformat()} ===\n{'=' * 60}\n\n"
    
    with open(file_path, mode) as f:
        f.write(header)


def log_step_start(step_name: str):
    """
    Log a step start separator.
    
    Args:
        step_name: Name of the step being started
    """
    separator = f"\n{'=' * 60}\n===== START STEP: {step_name} =====\n{'=' * 60}"
    log(separator, level="STEP")


def log_step_end(step_name: str):
    """
    Log a step end separator.
    
    Args:
        step_name: Name of the step being ended
    """
    separator = f"{'=' * 60}\n===== END STEP: {step_name} =====\n{'=' * 60}\n"
    log(separator, level="STEP")


def log(msg: str, level: str = "INFO"):
    """Log a message with timestamp to console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {msg}"
    print(log_line, file=sys.stderr)
    
    # Also write to file if configured
    if _console_log_file:
        try:
            with open(_console_log_file, "a") as f:
                f.write(log_line + "\n")
        except Exception:
            pass  # Don't fail on log write errors


def reset_logging():
    """
    Reset the logging state. Used for testing.
    """
    global _console_log_file, _initialized
    _console_log_file = None
    _initialized = False
