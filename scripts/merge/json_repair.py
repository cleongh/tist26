"""
JSON repair utilities for handling LLM output.
"""

import json
import re
from typing import Dict, List, Tuple


def repair_json(text: str) -> str:
    """
    Attempt to repair common JSON formatting issues from LLM output.
    Returns the repaired JSON string.
    """
    # Remove markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = re.sub(r'<end_of_turn>.*$', '', text, flags=re.DOTALL)
    
    # Extract just the JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return text
    text = match.group()
    
    # Fix common issues:
    # 1. Missing commas between array elements (e.g., } { -> }, {)
    text = re.sub(r'\}\s*\{', '}, {', text)
    text = re.sub(r'\]\s*\[', '], [', text)
    
    # 2. Missing commas after closing braces/brackets before keys
    text = re.sub(r'\}\s*"', '}, "', text)
    text = re.sub(r'\]\s*"', '], "', text)
    
    # 3. Missing commas after string values before keys ("value" "key" -> "value", "key")
    text = re.sub(r'"\s+"', '", "', text)
    
    # 4. Missing commas after values before opening braces/brackets
    text = re.sub(r'"\s*\{', '", {', text)
    text = re.sub(r'"\s*\[', '", [', text)
    
    # 5. Trailing commas before closing braces/brackets
    text = re.sub(r',\s*\}', '}', text)
    text = re.sub(r',\s*\]', ']', text)
    
    # 6. Single quotes to double quotes (for keys/values)
    text = re.sub(r"(?<=[{\[,:])\s*'([^']*?)'\s*(?=[,}\]:])", r'"\1"', text)
    
    # 7. Remove any control characters that might break parsing
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    
    # 8. Fix missing comma after number before quote: 123 "key" -> 123, "key"
    text = re.sub(r'(\d)\s+"', r'\1, "', text)
    
    # 9. Fix missing comma after true/false/null before quote
    text = re.sub(r'(true|false|null)\s+"', r'\1, "', text)
    
    return text


def validate_structure_json(data: Dict) -> Tuple[bool, List[str]]:
    """
    Validate that the parsed JSON has all required fields for chapter structure.
    Returns (is_valid, list_of_missing_fields).
    """
    missing = []
    
    # Check top-level fields
    if "entities" not in data:
        missing.append("entities")
    elif not isinstance(data["entities"], dict):
        missing.append("entities (wrong type)")
    else:
        # Check entities subfields
        entities = data["entities"]
        if "characters" not in entities:
            missing.append("entities.characters")
        elif not isinstance(entities.get("characters"), list):
            missing.append("entities.characters (wrong type)")
            
        if "locations" not in entities:
            missing.append("entities.locations")
        elif not isinstance(entities.get("locations"), list):
            missing.append("entities.locations (wrong type)")
    
    if "events" not in data:
        missing.append("events")
    elif not isinstance(data["events"], list):
        missing.append("events (wrong type)")
    
    return len(missing) == 0, missing


def parse_and_validate_structure_json(response_text: str, max_retries: int = 0) -> Tuple[Dict, bool, str]:
    """
    Parse LLM response, repair if needed, and validate structure.
    Returns (parsed_data, is_valid, error_message).
    
    If parsing fails after repair, returns empty structure with is_valid=False.
    """
    # First, try to repair the JSON
    repaired = repair_json(response_text)
    
    # Try to parse
    try:
        data = json.loads(repaired)
    except json.JSONDecodeError as e:
        return {"entities": {"characters": [], "locations": []}, "events": []}, False, f"JSON parse error: {e}"
    
    # Validate structure
    is_valid, missing = validate_structure_json(data)
    if not is_valid:
        return data, False, f"Missing fields: {', '.join(missing)}"
    
    # Ensure all required substructures exist with correct types
    if "entities" not in data:
        data["entities"] = {}
    if "characters" not in data["entities"]:
        data["entities"]["characters"] = []
    if "locations" not in data["entities"]:
        data["entities"]["locations"] = []
    if "events" not in data:
        data["events"] = []
    
    return data, True, ""
