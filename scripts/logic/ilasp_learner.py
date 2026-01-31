"""
ILASP rule learning utilities.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

from ..state.config import RULES_DIR
from ..state.logging import log


def learn_rules_from_violations(
    current_facts: str, 
    violations: List[Dict], 
    chapter_num: int,
    accumulated_facts: List[str] = None,
    learned_rules: List[str] = None,
    mode_declarations_path: Path = None
) -> List[str]:
    """
    Use ILASP to learn rules from detected violations and accumulated knowledge.
    
    This creates proper positive/negative examples for ILASP:
    - Positive examples: patterns that SHOULD trigger violations
    - Negative examples: patterns that should NOT trigger violations
    
    Args:
        current_facts: ASP facts for current chapter
        violations: List of violation dicts
        chapter_num: Current chapter number
        accumulated_facts: Facts accumulated from previous chapters
        learned_rules: Previously learned rules
        mode_declarations_path: Path to ILASP mode declarations
        
    Returns:
        List of newly learned rules
    """
    accumulated_facts = accumulated_facts or []
    learned_rules = learned_rules or []
    mode_declarations_path = mode_declarations_path or RULES_DIR / "ilasp_mode_declarations.las"
    
    new_rules = []
    
    # Build the ILASP learning task
    task_lines = [
        "% ILASP Learning Task - Generated from Chapter " + str(chapter_num),
        "% Learning from accumulated narrative knowledge",
        "",
    ]
    
    # Include mode declarations for hypothesis space
    if mode_declarations_path.exists():
        task_lines.append(mode_declarations_path.read_text())
    
    # === BACKGROUND KNOWLEDGE ===
    task_lines.append("\n% === BACKGROUND KNOWLEDGE ===")
    task_lines.append("% Accumulated facts from previous chapters:")
    task_lines.extend(accumulated_facts)
    task_lines.append("")
    task_lines.append("% Current chapter facts:")
    task_lines.extend(current_facts.split('\n'))
    task_lines.append("")
    
    # Include previously learned rules
    if learned_rules:
        task_lines.append("% Previously learned rules:")
        task_lines.extend(learned_rules)
        task_lines.append("")
    
    # === EXAMPLES ===
    task_lines.append("\n% === EXAMPLES ===")
    
    # Positive examples: violations we detected
    for i, v in enumerate(violations):
        category = v.get("category", "unknown")
        vtype = v.get("type", "unknown")
        event = v.get("event", "none")
        detail = v.get("detail", "none")
        task_lines.append(f"#pos(v{chapter_num}_{i}, {{violation({category}, {vtype}, {event}, {detail})}}, {{}}).")
    
    # Negative examples: valid patterns
    task_lines.append("")
    task_lines.append("% Negative examples: valid patterns that should NOT be violations")
    for fact in accumulated_facts:
        if fact.startswith("character("):
            char = fact.replace("character(", "").replace(").", "").strip()
            if char:
                task_lines.append(f"#neg(neg_char_{char}, {{violation(coherence, unknown_agent, _, {char})}}, {{}}).")
    
    # === CROSS-CHAPTER CONSTRAINTS ===
    task_lines.append("")
    task_lines.append("% === CROSS-CHAPTER CONSTRAINTS ===")
    task_lines.append("% Characters seen persist across chapters")
    task_lines.append("% Locations seen persist across chapters")
    
    # Build the full task
    task = "\n".join(task_lines)
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".las", delete=False) as f:
        f.write(task)
        task_path = f.name
    
    try:
        result = subprocess.run(
            ["ILASP", task_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("%") and line not in learned_rules:
                    new_rules.append(line)
                    log(f"ILASP learned: {line}", "INFO")
        elif result.stderr:
            log(f"ILASP stderr: {result.stderr[:200]}", "DEBUG")
                    
    except subprocess.TimeoutExpired:
        log("ILASP learning timed out", "WARN")
    except FileNotFoundError:
        log("ILASP not found in PATH", "WARN")
    except Exception as e:
        log(f"ILASP error: {e}", "WARN")
    finally:
        try:
            os.unlink(task_path)
        except:
            pass
    
    return new_rules
