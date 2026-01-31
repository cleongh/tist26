"""
Rule Registry - Rule Loading, Priorities, Activation

Responsibilities:
    - Load and manage ASP rule files
    - Track rule priorities (story > learned > universal)
    - Track active/deactivated rules
    - Provide rules to Clingo in priority order

Per LOGIC_DESIGN.md Section 3.1:
    Rule Layers (Priority Order):
        1. Story-Specific Rules - override all others
        2. Learned Rules - inferred via ILASP
        3. Universal Rules - default assumptions

    Contradicted rules are deactivated but retained for auditing.

Phase 3 Refactoring (Step 3.3):
    - Move rule loading/management from LogicEvaluator
    - Track active/deactivated rules with provenance
    - Implement priority-based rule resolution
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from pathlib import Path
from enum import Enum
import json
from datetime import datetime


class RuleLayer(Enum):
    """Rule layer priority (higher = more priority)."""
    UNIVERSAL = 1
    LEARNED = 2
    STORY = 3


@dataclass
class Rule:
    """
    Represents a single rule with metadata.
    
    Rules can be individual ASP rules or entire rule files.
    """
    id: str
    layer: RuleLayer
    content: str  # ASP rule content or file path
    is_file: bool = False
    active: bool = True
    overridden_by: Optional[str] = None  # ID of rule that overrides this
    source: str = ""  # Where this rule came from
    description: str = ""  # Human-readable description
    
    def get_priority(self) -> int:
        """Get numeric priority (higher = more important)."""
        return self.layer.value


@dataclass
class RuleOverride:
    """
    Record of a rule being overridden.
    
    Per LOGIC_DESIGN.md: Contradicted rules are deactivated but retained.
    """
    overridden_rule_id: str
    overriding_rule_id: str
    reason: str
    timestamp: str = ""


class RuleRegistry:
    """
    Central registry for all ASP rules.
    
    Manages:
        - Loading rules from files
        - Rule priority ordering
        - Rule activation/deactivation
        - Override tracking for audit
        - Learned rules from ILASP
    
    Does NOT:
        - Evaluate rules (delegated to Clingo)
        - Make logical decisions
        - Interpret rule content
    
    Extracted from LogicEvaluator (Phase 3, Step 3.3):
        - rule_files loading → load_legacy_rules()
        - learned_rules tracking → add_learned_rule()
    """
    
    def __init__(self, rules_dir: Path = None):
        self.rules_dir = rules_dir or Path(__file__).parent.parent / "rules"
        
        # Rule storage by layer
        self.rules: Dict[str, Rule] = {}
        
        # Override history (for auditing)
        self.overrides: List[RuleOverride] = []
        
        # Learned rules (in-memory, from ILASP)
        self.learned_rules_content: List[str] = []
        
        # File-based rules by layer
        self.layer_dirs = {
            RuleLayer.UNIVERSAL: self.rules_dir / "universal",
            RuleLayer.LEARNED: self.rules_dir / "learned",
            RuleLayer.STORY: self.rules_dir / "story",
        }
        
        # Core rules (shared by all layers)
        self.core_file = self.rules_dir / "core.lp"
        
        # Legacy rule files (from LogicEvaluator.rule_files)
        self.legacy_rule_files: List[Path] = []
    
    def load_legacy_rules(self, rule_files: List[Path] = None) -> int:
        """
        Load legacy rule files from LogicEvaluator.
        
        Extracted from LogicEvaluator.rule_files initialization.
        
        Args:
            rule_files: List of rule file paths. If None, uses defaults.
        
        Returns:
            Number of rules loaded.
        """
        if rule_files is None:
            rule_files = [
                self.rules_dir / "simple_narrative.lp",
                self.rules_dir / "story_rules.lp",
            ]
            
            # Also load universal rules for relationship, temporal, location, etc. violations
            universal_dir = self.rules_dir / "universal"
            if universal_dir.exists():
                for lp_file in universal_dir.glob("*.lp"):
                    rule_files.append(lp_file)
        
        count = 0
        for rule_file in rule_files:
            if rule_file.exists():
                self.legacy_rule_files.append(rule_file)
                rule_id = f"legacy:{rule_file.stem}"
                self.rules[rule_id] = Rule(
                    id=rule_id,
                    layer=RuleLayer.UNIVERSAL,
                    content=str(rule_file),
                    is_file=True,
                    source=str(rule_file),
                    description=f"Legacy rule file: {rule_file.name}"
                )
                count += 1
        
        return count
    
    def add_learned_rule(self, rule_content: str, source: str = "ILASP") -> str:
        """
        Add a learned rule from ILASP.
        
        Extracted from LogicEvaluator.learned_rules tracking.
        
        Args:
            rule_content: The ASP rule content
            source: Where this rule came from
        
        Returns:
            The rule ID
        """
        if rule_content not in self.learned_rules_content:
            self.learned_rules_content.append(rule_content)
        
        rule_id = f"learned:{len(self.learned_rules_content)}"
        self.rules[rule_id] = Rule(
            id=rule_id,
            layer=RuleLayer.LEARNED,
            content=rule_content,
            is_file=False,
            source=source,
            description=f"Learned via {source}"
        )
        
        return rule_id
    
    def get_learned_rules_content(self) -> List[str]:
        """Get all learned rules as content strings."""
        return self.learned_rules_content.copy()
    def load_layer(self, layer: RuleLayer) -> int:
        """
        Load all rules from a layer's directory.
        
        Returns number of rules loaded.
        """
        layer_dir = self.layer_dirs.get(layer)
        if not layer_dir or not layer_dir.exists():
            return 0
        
        count = 0
        for rule_file in layer_dir.glob("*.lp"):
            rule_id = f"{layer.name.lower()}:{rule_file.stem}"
            self.rules[rule_id] = Rule(
                id=rule_id,
                layer=layer,
                content=str(rule_file),
                is_file=True,
                source=str(rule_file),
            )
            count += 1
        
        return count
    
    def load_all_layers(self) -> Dict[RuleLayer, int]:
        """
        Load rules from all layers.
        
        Returns dict of layer -> count loaded.
        """
        counts = {}
        for layer in RuleLayer:
            counts[layer] = self.load_layer(layer)
        return counts
    
    def add_rule(self, rule_id: str, layer: RuleLayer, content: str, 
                 source: str = "") -> Rule:
        """
        Add a new rule to the registry.
        
        Args:
            rule_id: Unique identifier for the rule
            layer: Which layer this rule belongs to
            content: ASP rule content (not a file path)
            source: Where this rule came from (for auditing)
        
        Returns:
            The created Rule object
        """
        rule = Rule(
            id=rule_id,
            layer=layer,
            content=content,
            is_file=False,
            source=source,
        )
        self.rules[rule_id] = rule
        return rule
    
    def add_rule_file(self, rule_id: str, layer: RuleLayer, 
                      file_path: Path, source: str = "") -> Rule:
        """
        Add a rule file to the registry.
        
        Args:
            rule_id: Unique identifier for the rule
            layer: Which layer this rule belongs to
            file_path: Path to the .lp file
            source: Where this rule came from
        
        Returns:
            The created Rule object
        """
        rule = Rule(
            id=rule_id,
            layer=layer,
            content=str(file_path),
            is_file=True,
            source=source or str(file_path),
        )
        self.rules[rule_id] = rule
        return rule
    
    def deactivate_rule(self, rule_id: str, overriding_rule_id: str, 
                        reason: str = "") -> bool:
        """
        Deactivate a rule (but retain for auditing).
        
        Per LOGIC_DESIGN.md: Contradicted rules are deactivated but retained.
        
        Args:
            rule_id: ID of rule to deactivate
            overriding_rule_id: ID of rule that overrides this one
            reason: Human-readable reason for override
        
        Returns:
            True if rule was deactivated, False if not found
        """
        if rule_id not in self.rules:
            return False
        
        rule = self.rules[rule_id]
        rule.active = False
        rule.overridden_by = overriding_rule_id
        
        # Record override for audit
        self.overrides.append(RuleOverride(
            overridden_rule_id=rule_id,
            overriding_rule_id=overriding_rule_id,
            reason=reason,
        ))
        
        return True
    
    def reactivate_rule(self, rule_id: str) -> bool:
        """Reactivate a previously deactivated rule."""
        if rule_id not in self.rules:
            return False
        
        rule = self.rules[rule_id]
        rule.active = True
        rule.overridden_by = None
        return True
    
    def get_active_rules(self, layer: RuleLayer = None) -> List[Rule]:
        """
        Get all active rules, optionally filtered by layer.
        
        Returns rules sorted by priority (highest first).
        """
        rules = [r for r in self.rules.values() if r.active]
        
        if layer is not None:
            rules = [r for r in rules if r.layer == layer]
        
        # Sort by priority (highest first)
        return sorted(rules, key=lambda r: r.get_priority(), reverse=True)
    
    def get_active_rule_files(self) -> List[Path]:
        """
        Get paths to all active rule files for Clingo loading.
        
        Returns files in priority order (story rules last, applied last).
        """
        files = []
        
        # Core rules first (if exists)
        if self.core_file.exists():
            files.append(self.core_file)
        
        # Legacy rule files (from LogicEvaluator compatibility)
        for legacy_file in self.legacy_rule_files:
            if legacy_file.exists() and legacy_file not in files:
                files.append(legacy_file)
        
        # Then by layer priority (universal, learned, story)
        for layer in [RuleLayer.UNIVERSAL, RuleLayer.LEARNED, RuleLayer.STORY]:
            for rule in self.get_active_rules(layer):
                if rule.is_file:
                    path = Path(rule.content)
                    if path.exists() and path not in files:
                        files.append(path)
        
        return files
    
    def get_combined_rules_content(self) -> str:
        """
        Get combined content of all active non-file rules.
        
        Used for dynamic rules not stored in files.
        """
        lines = ["% Combined dynamic rules from RuleRegistry"]
        
        for layer in [RuleLayer.UNIVERSAL, RuleLayer.LEARNED, RuleLayer.STORY]:
            layer_rules = [r for r in self.get_active_rules(layer) if not r.is_file]
            if layer_rules:
                lines.append(f"\n% === {layer.name} RULES ===")
                for rule in layer_rules:
                    lines.append(f"% Rule: {rule.id}")
                    lines.append(rule.content)
        
        return "\n".join(lines)
    
    def get_override_history(self) -> List[Dict[str, Any]]:
        """
        Get the full override history for auditing.
        
        Per LOGIC_DESIGN.md Section 6: Audit all active and deactivated rules.
        """
        return [
            {
                "overridden": o.overridden_rule_id,
                "by": o.overriding_rule_id,
                "reason": o.reason,
                "timestamp": o.timestamp,
            }
            for o in self.overrides
        ]
    
    def get_deactivated_rules(self) -> List[Rule]:
        """Get all deactivated rules (for auditing)."""
        return [r for r in self.rules.values() if not r.active]
    
    def audit_summary(self) -> Dict[str, Any]:
        """
        Generate an audit summary of all rules.
        
        Per LOGIC_DESIGN.md Section 6: Final Chapter Analysis includes
        auditing all active and deactivated rules.
        """
        active_by_layer = {}
        for layer in RuleLayer:
            active_by_layer[layer.name] = len([
                r for r in self.rules.values() 
                if r.active and r.layer == layer
            ])
        
        return {
            "total_rules": len(self.rules),
            "active_rules": len([r for r in self.rules.values() if r.active]),
            "deactivated_rules": len([r for r in self.rules.values() if not r.active]),
            "active_by_layer": active_by_layer,
            "override_count": len(self.overrides),
            "overrides": self.get_override_history(),
        }
    
    def reset(self) -> None:
        """Reset registry for a new story."""
        # Keep universal rules, clear learned and story
        to_remove = [
            rid for rid, rule in self.rules.items()
            if rule.layer in (RuleLayer.LEARNED, RuleLayer.STORY)
        ]
        for rid in to_remove:
            del self.rules[rid]
        
        # Reactivate all universal rules
        for rule in self.rules.values():
            rule.active = True
            rule.overridden_by = None
        
        # Clear override history
        self.overrides = []
        
        # Clear learned rules content
        self.learned_rules_content = []
    
    def save(self, path: Path) -> None:
        """Save registry state to file."""
        data = {
            "rules": {
                rid: {
                    "id": r.id,
                    "layer": r.layer.name,
                    "content": r.content,
                    "is_file": r.is_file,
                    "active": r.active,
                    "overridden_by": r.overridden_by,
                    "source": r.source,
                }
                for rid, r in self.rules.items()
            },
            "overrides": self.get_override_history(),
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, path: Path) -> None:
        """Load registry state from file."""
        with open(path) as f:
            data = json.load(f)
        
        self.rules = {}
        for rid, rdata in data.get("rules", {}).items():
            self.rules[rid] = Rule(
                id=rdata["id"],
                layer=RuleLayer[rdata["layer"]],
                content=rdata["content"],
                is_file=rdata["is_file"],
                active=rdata["active"],
                overridden_by=rdata.get("overridden_by"),
                source=rdata.get("source", ""),
            )
        
        self.overrides = [
            RuleOverride(
                overridden_rule_id=o["overridden"],
                overriding_rule_id=o["by"],
                reason=o.get("reason", ""),
                timestamp=o.get("timestamp", ""),
            )
            for o in data.get("overrides", [])
        ]
