"""
Logging utilities for the narrative experiment.
"""

import sys
from datetime import datetime
from pathlib import Path

# Global log file handle (set by main when experiment starts)
_console_log_file = None


def set_console_log_file(file_path: Path):
    """Set the file path for console logging."""
    global _console_log_file
    _console_log_file = file_path
    # Create/clear the file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        f.write(f"=== Experiment Log Started: {datetime.now().isoformat()} ===\n\n")


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
