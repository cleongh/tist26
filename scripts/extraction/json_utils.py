"""
Deterministic JSON Validation and Repair Utility.

This module provides pure-Python JSON parsing with automatic repair
of common LLM output issues. It is designed to be:
- Deterministic: Same input always produces same output
- Safe: Only fixes syntax, never modifies semantic content
- Debuggable: Logs raw failures for inspection

Common issues fixed:
- Keys with trailing colons: "id:" → "id"
- Single quotes → double quotes  
- Trailing commas before } or ]
- JavaScript-style comments (// and /* */)
- Unquoted string values in some cases

This module does NOT:
- Add missing fields
- Change field values
- Infer or hallucinate data
- Use LLM to fix JSON
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..state.logging import log


# Directory for failed LLM output logs
FAILED_OUTPUTS_DIR = Path(__file__).parent.parent.parent / "experiments" / "failed_llm_outputs"


class JSONParseError(Exception):
    """Raised when JSON parsing fails after all repair attempts."""
    
    def __init__(self, message: str, raw_output: str, phase: str):
        super().__init__(message)
        self.raw_output = raw_output
        self.phase = phase


def _remove_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    # Remove ```json ... ``` blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    return text


def _remove_think_tags(text: str) -> str:
    """Remove <think>...</think> tags from LLM output."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)


def _remove_js_comments(text: str) -> str:
    """Remove JavaScript-style comments."""
    # Remove // line comments (but not inside strings)
    # This is a simplified approach - we remove lines starting with //
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Remove // comments at end of line (simple heuristic)
        # Be careful not to remove // inside strings
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        # Remove trailing // comments (rough heuristic)
        if '//' in line and '"' not in line.split('//')[-1]:
            line = line.split('//')[0]
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)
    
    # Remove /* */ block comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text


def _fix_key_colons(text: str) -> str:
    """
    Fix keys with embedded colons like "id:" → "id".
    
    Pattern: "key:" : value → "key": value
    This handles cases where LLM outputs "id:" as the key name.
    """
    # Match "key:" followed by optional whitespace and : 
    # Replace "key:": with "key":
    text = re.sub(r'"([^"]+):"\s*:', r'"\1":', text)
    return text


def _fix_single_quotes(text: str) -> str:
    """
    Convert single quotes to double quotes for JSON keys and string values.
    
    This is a heuristic approach that handles common cases.
    """
    # First, let's try to identify if this looks like single-quoted JSON
    # Check if there are more single quotes than double quotes in key positions
    
    # Simple approach: replace 'key': with "key":
    # and : 'value' with : "value"
    
    # Replace single-quoted keys: 'key': → "key":
    text = re.sub(r"'([^']+)'\s*:", r'"\1":', text)
    
    # Replace single-quoted string values after : or , or [
    # Be careful not to break contractions inside already double-quoted strings
    text = re.sub(r":\s*'([^']*)'", r': "\1"', text)
    text = re.sub(r",\s*'([^']*)'", r', "\1"', text)
    text = re.sub(r"\[\s*'([^']*)'", r'["\1"', text)
    
    return text


def _fix_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ]."""
    # Remove comma followed by whitespace and } or ]
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    return text


def _fix_unquoted_values(text: str) -> str:
    """
    Attempt to fix obviously unquoted string values.
    
    This is very conservative - only fixes clear patterns.
    """
    # Fix unquoted null, true, false (already valid JSON, but ensure lowercase)
    text = re.sub(r':\s*None\b', ': null', text)
    text = re.sub(r':\s*True\b', ': true', text)
    text = re.sub(r':\s*False\b', ': false', text)
    return text


def _extract_json_object(text: str) -> Optional[str]:
    """
    Extract the largest JSON object or array from text.
    
    Returns the extracted JSON string or None if not found.
    """
    # Find the first { or [
    obj_start = text.find('{')
    arr_start = text.find('[')
    
    if obj_start == -1 and arr_start == -1:
        return None
    
    # Determine which comes first
    if obj_start == -1:
        start = arr_start
        open_char, close_char = '[', ']'
    elif arr_start == -1:
        start = obj_start
        open_char, close_char = '{', '}'
    else:
        if obj_start < arr_start:
            start = obj_start
            open_char, close_char = '{', '}'
        else:
            start = arr_start
            open_char, close_char = '[', ']'
    
    # Find matching closing bracket
    depth = 0
    in_string = False
    escape_next = False
    
    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\' and in_string:
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    
    # If we got here, brackets are unbalanced
    # Return everything from start to end as a best effort
    return text[start:]


def repair_json(raw_output: str) -> str:
    """
    Apply all JSON repair transformations.
    
    This is a pure function that applies deterministic transformations
    to fix common JSON syntax issues from LLM output.
    
    Args:
        raw_output: Raw text from LLM
        
    Returns:
        Cleaned JSON string (may still be invalid)
    """
    text = raw_output
    
    # Step 1: Remove wrapper content
    text = _remove_markdown_fences(text)
    text = _remove_think_tags(text)
    
    # Step 2: Remove comments
    text = _remove_js_comments(text)
    
    # Step 3: Extract JSON object/array
    extracted = _extract_json_object(text)
    if extracted:
        text = extracted
    
    # Step 4: Fix syntax issues
    text = _fix_key_colons(text)
    text = _fix_single_quotes(text)
    text = _fix_trailing_commas(text)
    text = _fix_unquoted_values(text)
    
    return text.strip()


def _log_failed_output(raw_output: str, phase: str, error: str) -> Path:
    """
    Log raw LLM output to disk for debugging.
    
    Args:
        raw_output: The raw LLM output that failed to parse
        phase: The extraction phase name
        error: The error message
        
    Returns:
        Path to the log file
    """
    FAILED_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Sanitize phase name for filename
    safe_phase = phase.replace("/", "_").replace(" ", "_")
    log_file = FAILED_OUTPUTS_DIR / f"{safe_phase}.txt"
    
    content = f"""=== JSON Parse Failure ===
Phase: {phase}
Error: {error}

=== Raw LLM Output ===
{raw_output}

=== After Repair Attempt ===
{repair_json(raw_output)}
"""
    
    log_file.write_text(content, encoding="utf-8")
    return log_file


def parse_llm_json(
    raw_output: str,
    phase: str,
    default: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Parse JSON from LLM output with automatic repair.
    
    This is the main entry point for parsing LLM JSON output.
    It attempts repair transformations and returns a safe default
    on failure, never raising an exception.
    
    Args:
        raw_output: Raw text from LLM
        phase: Name of extraction phase (for logging)
        default: Default value to return on failure (default: empty dict)
        
    Returns:
        Tuple of (parsed_dict, success_bool)
        - On success: (parsed_data, True)
        - On failure: (default or {}, False)
    """
    if default is None:
        default = {}
    
    if not raw_output or not raw_output.strip():
        log(f"[{phase}] Empty LLM output", "WARN")
        return default, False
    
    # Step 1: Try parsing raw output directly (fast path)
    try:
        # Quick extraction of JSON from common wrappers
        cleaned = _remove_markdown_fences(raw_output)
        cleaned = _remove_think_tags(cleaned)
        
        # Try to find JSON object
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result, True
    except json.JSONDecodeError:
        pass  # Fall through to repair
    
    # Step 2: Apply full repair pipeline
    try:
        repaired = repair_json(raw_output)
        result = json.loads(repaired)
        
        # Ensure we return a dict
        if isinstance(result, dict):
            log(f"[{phase}] JSON repaired successfully", "DEBUG")
            return result, True
        elif isinstance(result, list):
            # Some phases might return arrays - wrap in expected structure
            log(f"[{phase}] JSON parsed as array, wrapping", "DEBUG")
            return {"items": result}, True
        else:
            log(f"[{phase}] Unexpected JSON type: {type(result)}", "WARN")
            return default, False
            
    except json.JSONDecodeError as e:
        # Step 3: Log failure and return default
        error_msg = f"JSON parse failed: {e}"
        log(f"[{phase}] {error_msg}", "WARN")
        
        log_file = _log_failed_output(raw_output, phase, str(e))
        log(f"[{phase}] Raw output logged to: {log_file}", "DEBUG")
        
        return default, False


def parse_llm_json_strict(
    raw_output: str,
    phase: str,
) -> Dict[str, Any]:
    """
    Parse JSON from LLM output with automatic repair (strict mode).
    
    Unlike parse_llm_json(), this raises JSONParseError on failure.
    Use this when you need to explicitly handle failures.
    
    Args:
        raw_output: Raw text from LLM
        phase: Name of extraction phase (for logging)
        
    Returns:
        Parsed dict
        
    Raises:
        JSONParseError: If parsing fails after repair attempts
    """
    result, success = parse_llm_json(raw_output, phase)
    
    if not success:
        raise JSONParseError(
            f"Failed to parse JSON in phase '{phase}'",
            raw_output,
            phase,
        )
    
    return result
