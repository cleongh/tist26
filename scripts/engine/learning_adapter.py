"""
Learning Adapter - ILASP Integration

Responsibilities:
    - Interface with ILASP for rule learning
    - Generate learning tasks from violations
    - Integrate learned rules into the registry
    - Version and scope learned rules per story

Per LOGIC_DESIGN.md Section 5 (Step 4):
    Rule Learning (ILASP):
        - Observe repeated violations or exceptions
        - Learn new rules and conditional exceptions
        - Learned rules are scoped to the story and versioned

Per LOGIC_DESIGN.md Section 3.1:
    Learned Rules are priority layer 2 (between story and universal).

Phase 3 Refactoring (Step 3.5):
    - Move _learn_rules_from_violations() from LogicEvaluator
    - Scope learned rules to story and version properly
    - Generate proper positive/negative examples
"""

from typing import Dict, List, Any, Optional, Tuple, TYPE_CHECKING
from pathlib import Path
import subprocess
import tempfile
import os
import json
from datetime import datetime

from .domain import LearningTask, LearnedRule, RuleLayer
from .preprocessors import AspConverter

if TYPE_CHECKING:
    from .registries import RuleRegistry

# Module-level converter instance
_asp_converter = AspConverter()


class LearningAdapter:
    """
    Integrates ILASP for inductive rule learning.
    
    Workflow:
        1. Observe violations across chapters
        2. Identify patterns (repeated violations, exceptions)
        3. Generate ILASP learning tasks
        4. Run ILASP to learn new rules
        5. Add learned rules to registry (LEARNED layer)
    
    Per LOGIC_DESIGN.md:
        - New rules emerge via ILASP, not Python heuristics
        - Learned rules are scoped to the story and versioned
        - Learned rules have priority between story and universal
    
    Extracted from LogicEvaluator (Phase 3, Step 3.5):
        - _learn_rules_from_violations() → learn_rules_from_violations()
        - learned_rules tracking → learned_rules list
        - chapter_violations_history → violation_history
    
    Does NOT:
        - Make heuristic rule decisions in Python
        - Bypass ILASP for rule generation
        - Modify learned rules after creation
    """
    
    def __init__(self, rule_registry: 'RuleRegistry', 
                 ilasp_path: str = "ILASP",
                 mode_declarations_path: Path = None):
        from .registries import RuleRegistry
        
        self.rule_registry = rule_registry
        self.ilasp_path = ilasp_path
        self.mode_declarations_path = mode_declarations_path
        
        # Track learned rules
        self.learned_rules: List[LearnedRule] = []
        self.learned_rules_content: List[str] = []  # For Clingo integration
        self._rule_counter = 0
        self._version_counter: Dict[str, int] = {}  # story_id -> version
        
        # Violation history for pattern detection (from LogicEvaluator.chapter_violations_history)
        self.violation_history: List[Dict[str, Any]] = []
        
        # Accumulated facts for learning background (from LogicEvaluator.accumulated_facts)
        self.accumulated_facts: List[str] = []
        
        # ILASP availability
        self._ilasp_available: Optional[bool] = None
    
    def set_accumulated_facts(self, facts: List[str]) -> None:
        """Set accumulated facts from StateManager."""
        self.accumulated_facts = facts.copy()
    
    def check_ilasp_available(self) -> bool:
        """Check if ILASP is available."""
        if self._ilasp_available is not None:
            return self._ilasp_available
        
        try:
            result = subprocess.run(
                [self.ilasp_path, "--version"],
                capture_output=True,
                timeout=5
            )
            self._ilasp_available = result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            self._ilasp_available = False
        
        return self._ilasp_available
    
    def _get_mode_declarations(self) -> str:
        """Load mode declarations for hypothesis space."""
        if self.mode_declarations_path and self.mode_declarations_path.exists():
            return self.mode_declarations_path.read_text()
        
        # Default minimal mode declarations
        return _asp_converter.ilasp_mode_declarations_to_asp()
    
    def learn_rules_from_violations(self, current_facts: str, 
                                     violations: List[Dict[str, Any]], 
                                     chapter_num: int,
                                     story_id: str = "") -> List[str]:
        """
        Use ILASP to learn rules from detected violations and accumulated knowledge.
        
        Extracted from LogicEvaluator._learn_rules_from_violations()
        
        Creates proper positive/negative examples for ILASP:
        - Positive examples: patterns that SHOULD trigger violations
        - Negative examples: patterns that should NOT trigger violations
        
        Args:
            current_facts: ASP facts for current chapter
            violations: List of violation dicts from Clingo
            chapter_num: Current chapter number
            story_id: Identifier for the story
        
        Returns:
            List of newly learned rule content strings
        """
        new_rules = []
        
        # Build the ILASP learning task
        task_lines = [
            f"% ILASP Learning Task - Generated from Chapter {chapter_num}",
            "% Learning from accumulated narrative knowledge",
            "",
        ]
        
        # Include mode declarations for hypothesis space
        task_lines.append(self._get_mode_declarations())
        
        # === BACKGROUND KNOWLEDGE ===
        task_lines.append("\n% === BACKGROUND KNOWLEDGE ===")
        task_lines.append("% Accumulated facts from previous chapters:")
        task_lines.extend(self.accumulated_facts)
        task_lines.append("")
        task_lines.append("% Current chapter facts:")
        task_lines.extend(current_facts.split('\n'))
        task_lines.append("")
        
        # Include previously learned rules
        if self.learned_rules_content:
            task_lines.append("% Previously learned rules:")
            task_lines.extend(self.learned_rules_content)
            task_lines.append("")
        
        # === EXAMPLES ===
        task_lines.append("\n% === EXAMPLES ===")
        
        # Positive examples: violations we detected
        for i, v in enumerate(violations):
            category = v.get("category", "unknown")
            vtype = v.get("type", "unknown")
            event = v.get("event", "none")
            detail = v.get("detail", "none")
            task_lines.append(_asp_converter.ilasp_violation_example_to_asp(
                chapter_num, i, category, vtype, event, detail
            ))
        
        # Negative examples: things that are NOT violations
        task_lines.append("")
        task_lines.append("% Negative examples: valid patterns that should NOT be violations")
        for fact in self.accumulated_facts:
            if fact.startswith("character("):
                char = fact.replace("character(", "").replace(").", "").strip()
                if char:
                    task_lines.append(_asp_converter.ilasp_character_negative_example_to_asp(char))
        
        # === CROSS-CHAPTER CONSTRAINTS ===
        task_lines.append("")
        task_lines.append("% === CROSS-CHAPTER CONSTRAINTS ===")
        task_lines.append("% Characters seen persist across chapters")
        task_lines.append("% Locations seen persist across chapters")
        
        task = "\n".join(task_lines)
        
        # Write to temp file and run ILASP
        with tempfile.NamedTemporaryFile(mode="w", suffix=".las", delete=False) as f:
            f.write(task)
            task_path = f.name
        
        try:
            result = subprocess.run(
                [self.ilasp_path, task_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("%") and line not in self.learned_rules_content:
                        self.learned_rules_content.append(line)
                        new_rules.append(line)
                        
                        # Add to rule registry
                        self.rule_registry.add_learned_rule(line, f"ILASP chapter {chapter_num}")
                        
                        # Track in learned rules
                        version = self._version_counter.get(story_id, 0) + 1
                        self._version_counter[story_id] = version
                        
                        self.learned_rules.append(LearnedRule(
                            id=f"learned_{story_id}_{chapter_num}_{len(self.learned_rules)}",
                            content=line,
                            story_id=story_id,
                            chapter=chapter_num,
                            version=version,
                            source_task_id=f"task_{chapter_num}",
                            timestamp=datetime.now().isoformat(),
                        ))
                        
        except subprocess.TimeoutExpired:
            pass  # ILASP timed out
        except FileNotFoundError:
            pass  # ILASP not found
        except Exception:
            pass  # Other error
        finally:
            try:
                os.unlink(task_path)
            except:
                pass
        
        # Record violations for pattern tracking
        if violations:
            self.violation_history.append({
                "chapter": chapter_num,
                "violations": violations,
                "story_id": story_id,
            })
        
        return new_rules
    
    def observe_violation(self, violation: Dict[str, Any], 
                          story_id: str, chapter: int) -> None:
        """
        Record a violation for pattern learning.
        
        Violations are accumulated to identify repeated patterns
        that should be learned as new rules.
        """
        self.violation_history.append({
            "violation": violation,
            "story_id": story_id,
            "chapter": chapter,
            "timestamp": datetime.now().isoformat(),
        })
    
    def observe_violations(self, violations: List[Dict[str, Any]], 
                           story_id: str, chapter: int) -> None:
        """Record multiple violations."""
        for v in violations:
            self.observe_violation(v, story_id, chapter)
    
    def identify_patterns(self, min_occurrences: int = 2) -> List[Dict[str, Any]]:
        """
        Identify repeated violation patterns suitable for learning.
        
        Patterns are identified by:
            - Same violation type appearing multiple times
            - Similar entity relationships in violations
        
        Returns list of pattern descriptions for learning tasks.
        """
        patterns = []
        
        # Group by violation type
        by_type: Dict[str, List[Dict]] = {}
        for entry in self.violation_history:
            vtype = entry["violation"].get("type", "unknown")
            if vtype not in by_type:
                by_type[vtype] = []
            by_type[vtype].append(entry)
        
        # Find repeated patterns
        for vtype, entries in by_type.items():
            if len(entries) >= min_occurrences:
                patterns.append({
                    "type": "repeated_violation",
                    "violation_type": vtype,
                    "occurrences": len(entries),
                    "entries": entries,
                })
        
        return patterns
    
    def create_learning_task(self, pattern: Dict[str, Any], 
                             background_facts: str,
                             story_id: str, chapter: int) -> LearningTask:
        """
        Create an ILASP learning task from a violation pattern.
        
        Args:
            pattern: Pattern description from identify_patterns
            background_facts: Current ASP facts to use as background
            story_id: Current story identifier
            chapter: Current chapter number
        
        Returns:
            LearningTask ready for ILASP execution
        """
        task_id = f"task_{story_id}_{chapter}_{self._rule_counter}"
        self._rule_counter += 1
        
        # Generate positive examples from pattern
        positive_examples = []
        for entry in pattern.get("entries", []):
            v = entry["violation"]
            category = v.get("category", "unknown")
            vtype = v.get("type", "unknown")
            event = v.get("event", "none")
            detail = v.get("detail", "none")
            positive_examples.append(f"violation({category}, {vtype}, {event}, {detail})")
        
        # Negative examples: known valid patterns that shouldn't be violations
        negative_examples = []
        # (These would be derived from non-violations in the same context)
        
        return LearningTask(
            id=task_id,
            background_knowledge=background_facts,
            positive_examples=positive_examples,
            negative_examples=negative_examples,
            mode_declarations=self._get_mode_declarations(),
            story_id=story_id,
            chapter=chapter,
        )
    
    def run_ilasp(self, task: LearningTask, timeout: int = 60) -> Tuple[bool, List[str]]:
        """
        Run ILASP on a learning task.
        
        Args:
            task: The learning task to run
            timeout: Maximum time in seconds
        
        Returns:
            Tuple of (success, list of learned rule strings)
        """
        if not self.check_ilasp_available():
            return False, ["ILASP not available"]
        
        # Write task to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".las", delete=False) as f:
            f.write(task.to_ilasp_format())
            task_path = f.name
        
        try:
            result = subprocess.run(
                [self.ilasp_path, task_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode != 0:
                return False, [f"ILASP error: {result.stderr}"]
            
            # Parse learned rules from output
            learned = self._parse_ilasp_output(result.stdout)
            return True, learned
            
        except subprocess.TimeoutExpired:
            return False, ["ILASP timeout"]
        except Exception as e:
            return False, [f"ILASP exception: {str(e)}"]
        finally:
            os.unlink(task_path)
    
    def _parse_ilasp_output(self, output: str) -> List[str]:
        """Parse ILASP output to extract learned rules."""
        rules = []
        
        for line in output.strip().split("\n"):
            line = line.strip()
            # ILASP outputs rules as ASP syntax
            if line and not line.startswith("%") and (":-" in line or line.endswith(".")):
                rules.append(line)
        
        return rules
    
    def learn_from_violations(self, background_facts: str,
                              story_id: str, chapter: int,
                              min_pattern_occurrences: int = 2) -> List[LearnedRule]:
        """
        Full learning workflow: patterns -> tasks -> ILASP -> rules.
        
        Args:
            background_facts: Current ASP facts
            story_id: Current story
            chapter: Current chapter
            min_pattern_occurrences: Minimum occurrences to consider a pattern
        
        Returns:
            List of newly learned rules
        """
        new_rules = []
        
        # Identify patterns
        patterns = self.identify_patterns(min_occurrences=min_pattern_occurrences)
        
        for pattern in patterns:
            # Create learning task
            task = self.create_learning_task(
                pattern, background_facts, story_id, chapter
            )
            
            # Run ILASP
            success, learned_content = self.run_ilasp(task)
            
            if success and learned_content:
                # Create learned rule
                version = self._version_counter.get(story_id, 0) + 1
                self._version_counter[story_id] = version
                
                for content in learned_content:
                    rule = LearnedRule(
                        id=f"learned_{story_id}_{version}_{len(new_rules)}",
                        content=content,
                        story_id=story_id,
                        chapter=chapter,
                        version=version,
                        source_task_id=task.id,
                        timestamp=datetime.now().isoformat(),
                    )
                    
                    # Add to registry
                    self.rule_registry.add_rule(
                        rule_id=rule.id,
                        layer=RuleLayer.LEARNED,
                        content=content,
                        source=f"ILASP from {task.id}",
                    )
                    
                    self.learned_rules.append(rule)
                    new_rules.append(rule)
        
        return new_rules
    
    def get_learned_rules_for_story(self, story_id: str) -> List[LearnedRule]:
        """Get all learned rules for a specific story."""
        return [r for r in self.learned_rules if r.story_id == story_id]
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """Get summary of all learning activity."""
        by_story = {}
        for rule in self.learned_rules:
            if rule.story_id not in by_story:
                by_story[rule.story_id] = []
            by_story[rule.story_id].append(rule.id)
        
        return {
            "total_learned_rules": len(self.learned_rules),
            "total_violations_observed": len(self.violation_history),
            "ilasp_available": self.check_ilasp_available(),
            "by_story": by_story,
            "rules": [
                {
                    "id": r.id,
                    "story": r.story_id,
                    "chapter": r.chapter,
                    "version": r.version,
                    "content": r.content,
                }
                for r in self.learned_rules
            ]
        }
    
    def reset(self) -> None:
        """Reset adapter for a new story."""
        self.learned_rules = []
        self.violation_history = []
        self._rule_counter = 0
    
    def reset_story(self, story_id: str) -> None:
        """Reset learning for a specific story."""
        self.learned_rules = [r for r in self.learned_rules if r.story_id != story_id]
        self.violation_history = [v for v in self.violation_history if v["story_id"] != story_id]
        if story_id in self._version_counter:
            del self._version_counter[story_id]
    
    def save(self, path: Path) -> None:
        """Save learning state to file."""
        with open(path, 'w') as f:
            json.dump(self.get_learning_summary(), f, indent=2)
    
    def load(self, path: Path) -> None:
        """Load learning state from file."""
        with open(path) as f:
            data = json.load(f)
        
        self.learned_rules = [
            LearnedRule(
                id=r["id"],
                content=r["content"],
                story_id=r["story"],
                chapter=r["chapter"],
                version=r["version"],
                source_task_id="",
            )
            for r in data.get("rules", [])
        ]
