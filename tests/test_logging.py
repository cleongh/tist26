"""
Tests for the logging module.

Validates that:
1. Logs are appended across multiple calls to set_console_log_file
2. Step separators are logged correctly
3. Handlers are not duplicated
4. Logging is idempotent
"""

import pytest
import tempfile
from pathlib import Path

from scripts.state.logging import (
    set_console_log_file,
    log,
    log_step_start,
    log_step_end,
    reset_logging,
)


class TestLogging:
    """Tests for logging module."""

    def test_log_file_append_mode(self, tmp_path: Path):
        """Logs should be appended across multiple set_console_log_file calls."""
        reset_logging()
        log_file = tmp_path / "test_log.txt"
        
        # First call - creates file with header
        set_console_log_file(log_file)
        log("First message")
        
        # Read and verify first message exists
        content = log_file.read_text()
        assert "First message" in content
        assert "Experiment Log Started" in content
        
        # Reset and call again - should append, not overwrite
        reset_logging()
        set_console_log_file(log_file, append=True)
        log("Second message")
        
        content = log_file.read_text()
        assert "First message" in content  # First message preserved
        assert "Second message" in content  # Second message appended
        assert "Experiment Run Resumed" in content  # Append header added

    def test_log_file_idempotent_setup(self, tmp_path: Path):
        """Multiple calls to set_console_log_file with same path should be idempotent."""
        reset_logging()
        log_file = tmp_path / "test_log.txt"
        
        # First call
        set_console_log_file(log_file)
        log("Message 1")
        
        # Second call to same file - should not add new header
        set_console_log_file(log_file)
        log("Message 2")
        
        content = log_file.read_text()
        # Should only have one header, not two
        assert content.count("Experiment Log Started") == 1
        assert "Message 1" in content
        assert "Message 2" in content

    def test_step_separators(self, tmp_path: Path):
        """Step start/end separators should be logged correctly."""
        reset_logging()
        log_file = tmp_path / "test_log.txt"
        set_console_log_file(log_file)
        
        log_step_start("TEST_STEP")
        log("Inside step")
        log_step_end("TEST_STEP")
        
        content = log_file.read_text()
        assert "===== START STEP: TEST_STEP =====" in content
        assert "===== END STEP: TEST_STEP =====" in content
        assert "Inside step" in content

    def test_log_levels(self, tmp_path: Path):
        """Different log levels should be correctly formatted."""
        reset_logging()
        log_file = tmp_path / "test_log.txt"
        set_console_log_file(log_file)
        
        log("Info message", level="INFO")
        log("Warning message", level="WARNING")
        log("Error message", level="ERROR")
        log("Debug message", level="DEBUG")
        
        content = log_file.read_text()
        assert "[INFO] Info message" in content
        assert "[WARNING] Warning message" in content
        assert "[ERROR] Error message" in content
        assert "[DEBUG] Debug message" in content

    def test_log_file_does_not_exist_creates_parent_dirs(self, tmp_path: Path):
        """Logging should create parent directories if they don't exist."""
        reset_logging()
        log_file = tmp_path / "nested" / "deep" / "test_log.txt"
        
        set_console_log_file(log_file)
        log("Test message")
        
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

    def test_log_without_file_configured(self, capsys):
        """Logging should still work to stderr even without file configured."""
        reset_logging()
        
        log("Console only message")
        
        captured = capsys.readouterr()
        assert "Console only message" in captured.err

    def test_force_overwrite_mode(self, tmp_path: Path):
        """Setting append=False should clear the file."""
        reset_logging()
        log_file = tmp_path / "test_log.txt"
        
        # First call
        set_console_log_file(log_file)
        log("First message")
        
        # Reset and force overwrite
        reset_logging()
        set_console_log_file(log_file, append=False)
        log("Second message")
        
        content = log_file.read_text()
        assert "First message" not in content  # First message cleared
        assert "Second message" in content  # Only second message exists

    def test_step_log_level(self, tmp_path: Path):
        """Step separators should use STEP log level."""
        reset_logging()
        log_file = tmp_path / "test_log.txt"
        set_console_log_file(log_file)
        
        log_step_start("MY_STEP")
        
        content = log_file.read_text()
        assert "[STEP]" in content
