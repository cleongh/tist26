"""
Rule Projector - Projects story-specific rules into ASP gated by active universe.

Phase 8.11: Ensures story-specific rules are included in ASP only when:
1. At least one entity referenced by the rule is in the active ASP universe
2. The rule has not been deactivated
3. Rule priority ordering is preserved (story > learned > universal)

Per LOGIC_DESIGN.md Section 3.1:
- Story-Specific Rules override all others
- Learned Rules are inferred via ILASP
- Universal Rules are default assumptions
- Contradicted rules are deactivated but retained

Per LOGIC_DESIGN.md Section 8:
- Python orchestrates; ASP reasons
- No rule interpretation or modification in Python
- This projector only FILTERS, never changes rule content

Entity Extraction:
- Parses ASP rule content to extract entity references
- Uses regex patterns for common fact forms:
  - story_exception(type, entity)
  - is_ghost(entity)
  - relationship_rule(subj, pred, obj, event)
  - trait_rule(subj, trait, event)
  - Entity constants in facts
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult
    from .rule_registry import Rule, RuleRegistry, RuleLayer

logger = logging.getLogger(__name__)


# Regex patterns for extracting entity references from ASP rules
# These patterns match common entity-referencing facts in story rules
ENTITY_PATTERNS = [
    # story_exception(violation_type, entity).
    re.compile(r'story_exception\s*\(\s*\w+\s*,\s*(\w+)\s*\)'),
    # is_ghost(entity). or is_vampire(entity). etc.
    re.compile(r'is_\w+\s*\(\s*(\w+)\s*\)'),
    # can_fly(entity). or can_use_magic(entity). etc.
    re.compile(r'can_\w+\s*\(\s*(\w+)\s*\)'),
    # has_trait(entity, trait). or has_ability(entity, ability). etc.
    re.compile(r'has_\w+\s*\(\s*(\w+)\s*\)'),
    # typically_friendly(entity1, entity2). or typically_hostile(entity1, entity2).
    re.compile(r'typically_\w+\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)'),
    # relationship_rule(subject, predicate, object, event).
    re.compile(r'relationship_rule\s*\(\s*(\w+)\s*,\s*\w+\s*,\s*(\w+)\s*,'),
    # trait_rule(subject, trait, event).
    re.compile(r'trait_rule\s*\(\s*(\w+)\s*,'),
    # location_rule(subject, location, event).
    re.compile(r'location_rule\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # possession_rule(subject, item, event).
    re.compile(r'possession_rule\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # character(entity). or location(entity). or item(entity).
    re.compile(r'(?:character|location|item)\s*\(\s*(\w+)\s*\)'),
    # trait(entity, trait).
    re.compile(r'trait\s*\(\s*(\w+)\s*,'),
    # is_dead(entity).
    re.compile(r'is_dead\s*\(\s*(\w+)\s*\)'),
    # present(entity, location, time).
    re.compile(r'present\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # relationship(char1, char2, type, ...).
    re.compile(r'relationship\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # Generic single-argument fact: predicate(entity).
    # This catches patterns like can_fly(entity), typically_friendly(entity), etc.
    re.compile(r'(\w+)\s*\(\s*(\w+)\s*\)\.'),
    # Generic two-argument fact: predicate(entity1, entity2).
    # This catches patterns like typically_friendly(char1, char2), etc.
    re.compile(r'(\w+)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\.'),
]

# Reserved ASP keywords and built-ins that are NOT entities
RESERVED_WORDS = frozenset({
    # ASP keywords
    'not', 'true', 'false', 
    # Common predicates (these are predicate names, not entities)
    'violation', 'story_override', 'story_exception',
    'is_ghost', 'is_dead', 'is_alive', 'is_vampire',
    'can_fly', 'can_use_magic', 'can_teleport',
    'has_trait', 'has_ability', 'has_power',
    'gravity_applies', 'cannot_fly',
    'character', 'location', 'item', 'trait', 'present',
    'relationship', 'relationship_rule', 'trait_rule',
    'location_rule', 'possession_rule', 'temporal_rule',
    'friends_help_friends', 'typically_friendly',
    # Categories
    'causality', 'coherence', 'temporal', 'emotional',
    # Variables (uppercase single letters)
    'x', 'y', 'z', 'c', 'e', 'd', 't', 'l',
    # Generic placeholders
    'entity', 'category', 'type', 'time', 'event', 'unknown',
    # Generic nouns that are not entities
    'object', 'human', 'person', 'thing',
})


@dataclass
class ProjectedRule:
    """
    A story-specific rule projected into the current ASP context.
    
    Attributes:
        rule_id: Unique rule identifier (from RuleRegistry)
        content: ASP rule content
        layer: Rule layer (STORY, LEARNED, UNIVERSAL)
        entities_referenced: Set of entities found in the rule
        is_active: Whether the rule passed the universe filter
        filtered_reason: Why the rule was filtered (if applicable)
    """
    rule_id: str
    content: str
    layer: str  # Store as string to avoid circular imports
    entities_referenced: Set[str] = field(default_factory=set)
    is_active: bool = True
    filtered_reason: str = ""
    
    def to_dict(self) -> Dict:
        """Serialize for diagnostics."""
        return {
            "rule_id": self.rule_id,
            "layer": self.layer,
            "entities_referenced": sorted(self.entities_referenced),
            "is_active": self.is_active,
            "filtered_reason": self.filtered_reason,
        }


@dataclass
class RuleProjectionResult:
    """
    Result of rule projection.
    
    Attributes:
        projected_rules: Rules that passed the active universe filter
        filtered_rules: Rules that were filtered out
        total_story_rules: Total story rules in registry
        total_learned_rules: Total learned rules in registry (Phase 8.11.1)
    """
    projected_rules: List[ProjectedRule] = field(default_factory=list)
    filtered_rules: List[ProjectedRule] = field(default_factory=list)
    total_story_rules: int = 0
    total_learned_rules: int = 0  # Phase 8.11.1: Learned rule tracking
    
    @property
    def projected_count(self) -> int:
        return len(self.projected_rules)
    
    @property
    def filtered_count(self) -> int:
        return len(self.filtered_rules)
    
    def get_projected_content(self, layer_filter: Optional[str] = None) -> str:
        """
        Get combined content of all projected rules.
        
        Args:
            layer_filter: Optional layer to filter by ('STORY', 'LEARNED', None for all)
        
        Returns ASP rules ready for Clingo.
        """
        if layer_filter:
            rules = [r for r in self.projected_rules if r.layer == layer_filter]
            header = f"% === PROJECTED {layer_filter} RULES (Phase 8.11) ==="
        else:
            rules = self.projected_rules
            header = "% === PROJECTED RULES (Phase 8.11) ==="
        
        lines = [header]
        for pr in rules:
            lines.append(f"% Rule: {pr.rule_id}")
            lines.append(pr.content)
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        """Serialize for diagnostics."""
        return {
            "total_story_rules": self.total_story_rules,
            "total_learned_rules": self.total_learned_rules,
            "projected_count": self.projected_count,
            "filtered_count": self.filtered_count,
            "projected": [r.to_dict() for r in self.projected_rules],
            "filtered": [r.to_dict() for r in self.filtered_rules],
        }


def extract_entities_from_rule(rule_content: str) -> Set[str]:
    """
    Extract entity references from ASP rule content.
    
    This is a heuristic extraction that identifies likely entity constants
    in ASP facts and rules. It:
    1. Applies regex patterns for known fact formats
    2. Filters out reserved words and built-ins
    3. Filters out variables (uppercase first letter)
    4. Filters out numeric literals
    
    Args:
        rule_content: ASP rule content string
        
    Returns:
        Set of entity identifiers found in the rule
    """
    entities: Set[str] = set()
    
    # Apply each pattern to extract entities
    for pattern in ENTITY_PATTERNS:
        for match in pattern.finditer(rule_content):
            for group in match.groups():
                if group:
                    entities.add(group)
    
    # Filter out reserved words, variables, and numbers
    filtered = set()
    for entity in entities:
        # Skip reserved words
        if entity.lower() in RESERVED_WORDS:
            continue
        # Skip single-letter variables (usually uppercase)
        if len(entity) == 1:
            continue
        # Skip numeric literals
        if entity.isdigit():
            continue
        # Skip things that look like variables (start with uppercase)
        # In ASP, constants are lowercase, variables are uppercase
        if entity[0].isupper():
            continue
        # Skip common event patterns (e0, e1, e123, etc.)
        if re.match(r'^e\d+$', entity):
            continue
        filtered.add(entity)
    
    return filtered


def is_rule_in_universe(
    entities_referenced: Set[str],
    active_universe: Optional['ActiveUniverseResult'],
) -> Tuple[bool, str]:
    """
    Check if at least one entity in the rule is in the active universe.
    
    Per requirement: A story-specific rule must be included IFF at least
    one entity referenced by the rule is in the active ASP universe.
    
    Args:
        entities_referenced: Entities found in the rule
        active_universe: The active entity universe
        
    Returns:
        Tuple of (is_in_universe, reason if filtered)
    """
    if active_universe is None:
        return True, ""
    
    if not entities_referenced:
        # No entities found - include by default (generic rules)
        return True, ""
    
    all_entities = active_universe.all_entities
    
    # Check if at least one entity is in the active universe
    for entity in entities_referenced:
        if entity in all_entities:
            return True, ""
    
    # No overlap - filter this rule
    return False, f"no_entities_in_universe: {sorted(entities_referenced)}"


def project_story_rules(
    rule_registry: 'RuleRegistry',
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> RuleProjectionResult:
    """
    Project story-specific rules from the registry into the ASP context.
    
    Only rules with at least one entity in the active universe are included.
    
    Args:
        rule_registry: The RuleRegistry containing all rules
        active_universe: The active entity universe (None = no filtering)
        
    Returns:
        RuleProjectionResult with projected and filtered rules
    """
    from .rule_registry import RuleLayer
    
    result = RuleProjectionResult()
    
    # Get active story-layer rules
    story_rules = rule_registry.get_active_rules(layer=RuleLayer.STORY)
    result.total_story_rules = len(story_rules)
    
    logger.debug(f"Projecting {len(story_rules)} story rules with active universe")
    
    for rule in story_rules:
        # Get rule content (from file or directly)
        if rule.is_file:
            try:
                from pathlib import Path
                content = Path(rule.content).read_text()
            except Exception as e:
                logger.warning(f"Could not read rule file {rule.content}: {e}")
                continue
        else:
            content = rule.content
        
        # Extract entities from rule content
        entities = extract_entities_from_rule(content)
        
        # Check if rule should be included
        is_in, reason = is_rule_in_universe(entities, active_universe)
        
        projected = ProjectedRule(
            rule_id=rule.id,
            content=content,
            layer=rule.layer.name,
            entities_referenced=entities,
            is_active=is_in,
            filtered_reason=reason,
        )
        
        if is_in:
            result.projected_rules.append(projected)
            logger.debug(f"Rule {rule.id} projected: entities={entities}")
        else:
            result.filtered_rules.append(projected)
            logger.debug(f"Rule {rule.id} filtered: {reason}")
    
    logger.info(
        f"Rule projection: {result.projected_count} projected, "
        f"{result.filtered_count} filtered out of {result.total_story_rules}"
    )
    
    return result


def project_learned_rules(
    rule_registry: 'RuleRegistry',
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> RuleProjectionResult:
    """
    Project learned rules from the registry into the ASP context.
    
    Phase 8.11.1: Learned rules are now filtered by active universe,
    using the same logic as story rules.
    
    Only rules with at least one entity in the active universe are included.
    Rules with no identifiable entities are included by default (generic rules).
    
    Note: This does NOT modify the learned rules storage or history.
    It only filters what gets passed to ASP for this evaluation.
    
    Args:
        rule_registry: The RuleRegistry containing all rules
        active_universe: The active entity universe (None = no filtering)
        
    Returns:
        RuleProjectionResult with projected and filtered learned rules
    """
    from .rule_registry import RuleLayer
    
    result = RuleProjectionResult()
    
    # Get active learned-layer rules
    learned_rules = rule_registry.get_active_rules(layer=RuleLayer.LEARNED)
    result.total_learned_rules = len(learned_rules)
    
    logger.debug(f"Projecting {len(learned_rules)} learned rules with active universe")
    
    for rule in learned_rules:
        # Get rule content (from file or directly)
        if rule.is_file:
            try:
                from pathlib import Path
                content = Path(rule.content).read_text()
            except Exception as e:
                logger.warning(f"Could not read rule file {rule.content}: {e}")
                continue
        else:
            content = rule.content
        
        # Extract entities from rule content
        entities = extract_entities_from_rule(content)
        
        # Check if rule should be included
        is_in, reason = is_rule_in_universe(entities, active_universe)
        
        projected = ProjectedRule(
            rule_id=rule.id,
            content=content,
            layer=rule.layer.name,
            entities_referenced=entities,
            is_active=is_in,
            filtered_reason=reason,
        )
        
        if is_in:
            result.projected_rules.append(projected)
            logger.debug(f"Learned rule {rule.id} projected: entities={entities}")
        else:
            result.filtered_rules.append(projected)
            logger.debug(f"Learned rule {rule.id} filtered: {reason}")
    
    logger.info(
        f"Learned rule projection: {result.projected_count} projected, "
        f"{result.filtered_count} filtered out of {result.total_learned_rules}"
    )
    
    return result


def project_rules(
    rule_registry: 'RuleRegistry',
    active_universe: Optional['ActiveUniverseResult'] = None,
    layers: Optional[List[str]] = None,
) -> RuleProjectionResult:
    """
    Project rules from specified layers, filtered by active universe.
    
    This is the unified projection function that handles both story and
    learned rules with the same filtering logic.
    
    Args:
        rule_registry: The RuleRegistry containing all rules
        active_universe: The active entity universe (None = no filtering)
        layers: List of layer names to project ('STORY', 'LEARNED').
                If None, defaults to ['STORY', 'LEARNED'].
        
    Returns:
        RuleProjectionResult with projected and filtered rules from all layers
    """
    from .rule_registry import RuleLayer
    
    if layers is None:
        layers = ['STORY', 'LEARNED']
    
    result = RuleProjectionResult()
    
    for layer_name in layers:
        try:
            layer = RuleLayer[layer_name]
        except KeyError:
            logger.warning(f"Unknown layer: {layer_name}")
            continue
        
        rules = rule_registry.get_active_rules(layer=layer)
        
        if layer == RuleLayer.STORY:
            result.total_story_rules = len(rules)
        elif layer == RuleLayer.LEARNED:
            result.total_learned_rules = len(rules)
        
        for rule in rules:
            # Get rule content
            if rule.is_file:
                try:
                    from pathlib import Path
                    content = Path(rule.content).read_text()
                except Exception as e:
                    logger.warning(f"Could not read rule file {rule.content}: {e}")
                    continue
            else:
                content = rule.content
            
            # Extract entities and check universe membership
            entities = extract_entities_from_rule(content)
            is_in, reason = is_rule_in_universe(entities, active_universe)
            
            projected = ProjectedRule(
                rule_id=rule.id,
                content=content,
                layer=rule.layer.name,
                entities_referenced=entities,
                is_active=is_in,
                filtered_reason=reason,
            )
            
            if is_in:
                result.projected_rules.append(projected)
            else:
                result.filtered_rules.append(projected)
    
    logger.info(
        f"Rule projection: {result.projected_count} projected, "
        f"{result.filtered_count} filtered "
        f"(story={result.total_story_rules}, learned={result.total_learned_rules})"
    )
    
    return result


def get_projected_rules_content(
    rule_registry: 'RuleRegistry',
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> str:
    """
    Convenience function to get projected story rules as ASP content.
    
    Args:
        rule_registry: The RuleRegistry containing all rules
        active_universe: The active entity universe (None = no filtering)
        
    Returns:
        ASP content string of projected story rules
    """
    result = project_story_rules(rule_registry, active_universe)
    return result.get_projected_content(layer_filter='STORY')


def get_projected_learned_rules_content(
    rule_registry: 'RuleRegistry',
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> str:
    """
    Convenience function to get projected learned rules as ASP content.
    
    Phase 8.11.1: Learned rules are now filtered by active universe.
    
    Args:
        rule_registry: The RuleRegistry containing all rules
        active_universe: The active entity universe (None = no filtering)
        
    Returns:
        ASP content string of projected learned rules
    """
    result = project_learned_rules(rule_registry, active_universe)
    return result.get_projected_content(layer_filter='LEARNED')


def get_all_projected_rules_content(
    rule_registry: 'RuleRegistry',
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> str:
    """
    Get content of ALL projected rules (story + learned + universal).
    
    Phase 8.11.1 Update:
    - Story rules: filtered by active universe
    - Learned rules: filtered by active universe (NEW)
    - Universal rules: included if active (not entity-filtered)
    
    This preserves the priority order: story > learned > universal.
    
    Args:
        rule_registry: The RuleRegistry containing all rules
        active_universe: The active entity universe (None = no filtering)
        
    Returns:
        Combined ASP content string
    """
    from .rule_registry import RuleLayer
    
    lines = ["% === ALL PROJECTED RULES (Phase 8.11.1) ==="]
    
    # Universal rules (always included if active - not entity-filtered)
    # Universal rules apply regardless of which entities are active
    lines.append("\n% --- UNIVERSAL RULES ---")
    for rule in rule_registry.get_active_rules(layer=RuleLayer.UNIVERSAL):
        if not rule.is_file:
            lines.append(f"% Rule: {rule.id}")
            lines.append(rule.content)
    
    # Learned rules (filtered by active universe - Phase 8.11.1)
    lines.append("\n% --- LEARNED RULES (filtered by active universe) ---")
    learned_result = project_learned_rules(rule_registry, active_universe)
    for pr in learned_result.projected_rules:
        lines.append(f"% Rule: {pr.rule_id}")
        lines.append(pr.content)
    
    # Story rules (filtered by active universe)
    lines.append("\n% --- STORY RULES (filtered by active universe) ---")
    story_result = project_story_rules(rule_registry, active_universe)
    for pr in story_result.projected_rules:
        lines.append(f"% Rule: {pr.rule_id}")
        lines.append(pr.content)
    
    return "\n".join(lines)
