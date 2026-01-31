"""
Advanced JSON parsing with iterative repair for LLM output.
"""

import json
import re
from typing import Dict, List

from ..state.logging import log


def repair_json_syntax(text: str) -> str:
    """Apply aggressive regex-based fixes for common JSON syntax errors."""
    # Fix trailing commas
    text = re.sub(r',\s*\}', '}', text)  # trailing comma before }
    text = re.sub(r',\s*\]', ']', text)  # trailing comma before ]
    
    # Fix missing commas between elements
    text = re.sub(r'\}\s*\{', '},{', text)  # missing comma between objects
    text = re.sub(r'\]\s*\[', '],[', text)  # missing comma between arrays
    text = re.sub(r'\]\s*\{', '],{', text)  # missing comma: array then object
    text = re.sub(r'\}\s*\[', '},[', text)  # missing comma: object then array
    
    # Fix missing commas between string properties (key-value pairs)
    text = re.sub(r'"\s*\n\s*"', '",\n"', text)  # newline between strings
    text = re.sub(r'"\s{2,}"', '", "', text)  # multiple spaces between strings
    
    # Fix missing commas after values before new keys
    # Pattern: "value" followed by whitespace then "key":
    text = re.sub(r'(")\s+("[\w_]+"\s*:)', r'\1,\2', text)
    
    # Fix missing commas after } or ] followed by "key":
    text = re.sub(r'(\})\s+("[\w_]+"\s*:)', r'\1,\2', text)
    text = re.sub(r'(\])\s+("[\w_]+"\s*:)', r'\1,\2', text)
    
    # Fix missing commas after numbers/booleans/null before "key":
    text = re.sub(r'(\d)\s+("[\w_]+"\s*:)', r'\1,\2', text)
    text = re.sub(r'(true|false|null)\s+("[\w_]+"\s*:)', r'\1,\2', text)
    
    return text


def _insert_comma_at(text: str, pos: int) -> str:
    """Insert a comma at an appropriate position near the error."""
    # Look backwards from error position for a good insertion point
    search_start = max(0, pos - 20)
    segment = text[search_start:pos]
    
    # Find the last complete value (ends with ", }, ], number, true, false, null)
    patterns = [
        (r'"(\s*)$', lambda m: '",' + m.group(1)),  # After string
        (r'(\})(\s*)$', lambda m: '},' + m.group(2)),  # After object
        (r'(\])(\s*)$', lambda m: '],' + m.group(2)),  # After array
        (r'(\d)(\s+)$', lambda m: m.group(1) + ',' + m.group(2)),  # After number
        (r'(true|false|null)(\s*)$', lambda m: m.group(1) + ',' + m.group(2)),  # After literals
    ]
    
    for pattern, replacement in patterns:
        match = re.search(pattern, segment)
        if match:
            insert_pos = search_start + match.start()
            # Insert comma after the matched value
            new_text = text[:insert_pos] + re.sub(pattern, replacement, segment[match.start():]) + text[pos:]
            if new_text != text:
                return new_text
    
    return text


def _fix_property_name_error(text: str, pos: int) -> str:
    """Fix errors related to property name expectations."""
    # Look for extra comma before }
    search_start = max(0, pos - 10)
    segment = text[search_start:pos]
    if re.search(r',\s*$', segment):
        # Remove trailing comma
        fixed = text[:search_start] + re.sub(r',\s*$', '', segment) + text[pos:]
        return fixed
    return text


def _fix_missing_value(text: str, pos: int) -> str:
    """Fix missing value after colon."""
    # Insert null as placeholder
    search_start = max(0, pos - 5)
    segment = text[search_start:pos]
    if re.search(r':\s*$', segment):
        return text[:pos] + 'null' + text[pos:]
    return text


def _fix_unterminated_string(text: str, pos: int) -> str:
    """Fix unterminated string by closing it."""
    # Find the opening quote and close the string
    for i in range(pos, min(pos + 100, len(text))):
        if text[i] in '\n,}]':
            return text[:i] + '"' + text[i:]
    return text


def _close_unclosed_brackets(text: str) -> str:
    """Close any unclosed brackets at the end."""
    text = text.rstrip()
    
    # Remove trailing partial content
    text = re.sub(r',\s*"[^"]*$', '', text)  # trailing incomplete string key
    text = re.sub(r':\s*"[^"]*$', ': null', text)  # incomplete string value
    text = re.sub(r',\s*$', '', text)  # trailing comma
    text = re.sub(r',\s*\{[^}]*$', '', text)  # incomplete object
    
    # Count and close remaining brackets
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    
    if open_brackets > 0:
        text += ']' * open_brackets
    if open_braces > 0:
        text += '}' * open_braces
    
    return text


def iterative_json_repair(text: str, max_attempts: int = 5) -> str:
    """Iteratively repair JSON by finding and fixing errors at reported positions."""
    current = text
    
    for attempt in range(max_attempts):
        try:
            json.loads(current)
            return current  # Success!
        except json.JSONDecodeError as e:
            error_pos = e.pos
            error_msg = str(e)
            
            log(f"    Repair attempt {attempt+1}: error at pos {error_pos}: {error_msg[:50]}", "DEBUG")
            
            # Try specific fixes based on error type
            if "Expecting ',' delimiter" in error_msg:
                # Insert comma at error position
                fixed = _insert_comma_at(current, error_pos)
                if fixed != current:
                    current = fixed
                    continue
            
            elif "Expecting property name" in error_msg:
                # Often means extra comma or malformed key
                fixed = _fix_property_name_error(current, error_pos)
                if fixed != current:
                    current = fixed
                    continue
            
            elif "Expecting value" in error_msg:
                # Missing value after colon
                fixed = _fix_missing_value(current, error_pos)
                if fixed != current:
                    current = fixed
                    continue
            
            elif "Unterminated string" in error_msg:
                # Try to close the string
                fixed = _fix_unterminated_string(current, error_pos)
                if fixed != current:
                    current = fixed
                    continue
            
            # Generic fix: try adding comma before error position
            fixed = _insert_comma_at(current, error_pos)
            if fixed != current:
                current = fixed
                continue
            
            # If nothing worked, break
            break
    
    # Final attempt: close any unclosed brackets
    return _close_unclosed_brackets(current)


def parse_json_object(text: str) -> Dict:
    """Parse a JSON object from LLM response, with repair for common errors."""
    original_length = len(text)
    
    # Remove DeepSeek-R1 thinking tags first
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Also handle unclosed think tags (model cut off mid-reasoning)
    text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL)
    
    # Remove other common wrappers
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
    
    # Log cleaned text for debugging
    log(f"    Parsing response ({len(text)} chars after cleanup, was {original_length})", "DEBUG")
    
    # Find JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        obj_text = match.group()
        
        # Apply aggressive JSON repair
        obj_text = repair_json_syntax(obj_text)
        
        try:
            return json.loads(obj_text)
        except json.JSONDecodeError as e:
            log(f"    JSON parse error: {e}", "WARN")
            log(f"    First 500 chars: {obj_text[:500]}", "DEBUG")
            
            # Try iterative repair for persistent issues
            repaired = iterative_json_repair(obj_text, max_attempts=5)
            if repaired:
                try:
                    result = json.loads(repaired)
                    log(f"    JSON repaired successfully!", "INFO")
                    return result
                except json.JSONDecodeError as e2:
                    log(f"    Repair failed: {e2}", "DEBUG")
    else:
        log(f"    No JSON object found in response", "WARN")
        if len(text) > 0:
            log(f"    Response preview: {text[:300]}...", "DEBUG")
    return {}


def parse_json_array(text: str) -> List[Dict]:
    """Parse a JSON array from LLM response, handling DeepSeek-R1 reasoning format."""
    # Remove DeepSeek-R1 thinking tags first
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Also handle unclosed think tags (model cut off mid-reasoning)
    text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL)
    
    # Remove other common wrappers
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
    
    # Log cleaned text for debugging
    log(f"    Parsing response ({len(text)} chars after cleanup)", "DEBUG")
    
    # Find array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        # Fix common issues
        arr_text = match.group()
        arr_text = re.sub(r'\}\s*\{', '}, {', arr_text)
        arr_text = re.sub(r'\}\s*"', '}, "', arr_text)
        arr_text = re.sub(r',\s*\]', ']', arr_text)
        try:
            return json.loads(arr_text)
        except:
            pass
    return []
