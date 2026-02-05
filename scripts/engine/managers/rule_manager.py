"""
Rule Manager - Projects story-specific rules into ASP gated by active universe.

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
"""

import logging
from pathlib import Path
from typing import List, Optional, Set, Tuple, TYPE_CHECKING

from ..domain import ProjectedRule, RuleProjectionResult, RuleLayer
from ..preprocessors import AspConverter

if TYPE_CHECKING:
    from ..active_universe import ActiveUniverseResult
    from ..registries import RuleRegistry

logger = logging.getLogger(__name__)


# Module-level converter instance for entity extraction
_asp_converter = AspConverter()


class RuleManager:
    """
    Manages rule projection into ASP context filtered by active universe.
    
    Provides:
        - Rule projection by active universe
        - Story rule filtering
        - Learned rule filtering
        - Combined rule content generation
    
    Does NOT:
        - Modify rule content
        - Store rules (handled by RuleRegistry)
        - Interpret or reason about rules
    """
    
    def __init__(self):
        """Initialize the RuleManager."""
        pass
    
    @staticmethod
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
    
    @staticmethod
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
        result = RuleProjectionResult()
        
        # Get active story-layer rules
        story_rules = rule_registry.get_active_rules(layer=RuleLayer.STORY)
        result.total_story_rules = len(story_rules)
        
        logger.debug(f"Projecting {len(story_rules)} story rules with active universe")
        
        for rule in story_rules:
            content = RuleManager._get_rule_content(rule)
            if content is None:
                continue
            
            # Extract entities from rule content
            entities = _asp_converter.extract_entities_from_rule(content)
            
            # Check if rule should be included
            is_in, reason = RuleManager.is_rule_in_universe(entities, active_universe)
            
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
    
    @staticmethod
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
        result = RuleProjectionResult()
        
        # Get active learned-layer rules
        learned_rules = rule_registry.get_active_rules(layer=RuleLayer.LEARNED)
        result.total_learned_rules = len(learned_rules)
        
        logger.debug(f"Projecting {len(learned_rules)} learned rules with active universe")
        
        for rule in learned_rules:
            content = RuleManager._get_rule_content(rule)
            if content is None:
                continue
            
            # Extract entities from rule content
            entities = _asp_converter.extract_entities_from_rule(content)
            
            # Check if rule should be included
            is_in, reason = RuleManager.is_rule_in_universe(entities, active_universe)
            
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
    
    @staticmethod
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
                content = RuleManager._get_rule_content(rule)
                if content is None:
                    continue
                
                # Extract entities and check universe membership
                entities = _asp_converter.extract_entities_from_rule(content)
                is_in, reason = RuleManager.is_rule_in_universe(entities, active_universe)
                
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
    
    @staticmethod
    def get_projected_rules_content(
        rule_registry: 'RuleRegistry',
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Get projected story rules as ASP content.
        
        Args:
            rule_registry: The RuleRegistry containing all rules
            active_universe: The active entity universe (None = no filtering)
            
        Returns:
            ASP content string of projected story rules
        """
        result = RuleManager.project_story_rules(rule_registry, active_universe)
        return result.get_projected_content(layer_filter='STORY')
    
    @staticmethod
    def get_projected_learned_rules_content(
        rule_registry: 'RuleRegistry',
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Get projected learned rules as ASP content.
        
        Phase 8.11.1: Learned rules are now filtered by active universe.
        
        Args:
            rule_registry: The RuleRegistry containing all rules
            active_universe: The active entity universe (None = no filtering)
            
        Returns:
            ASP content string of projected learned rules
        """
        result = RuleManager.project_learned_rules(rule_registry, active_universe)
        return result.get_projected_content(layer_filter='LEARNED')
    
    @staticmethod
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
        lines = [_asp_converter.rule_header_to_asp("=== ALL PROJECTED RULES (Phase 8.11.1) ===")]
        
        # Universal rules (always included if active - not entity-filtered)
        # Universal rules apply regardless of which entities are active
        universal_rules = [r for r in rule_registry.get_active_rules(layer=RuleLayer.UNIVERSAL) if not r.is_file]
        if universal_rules:
            lines.extend(_asp_converter.combined_rules_to_asp(universal_rules, "UNIVERSAL"))
        
        # Learned rules (filtered by active universe - Phase 8.11.1)
        learned_result = RuleManager.project_learned_rules(rule_registry, active_universe)
        lines.append(_asp_converter.rule_header_to_asp("--- LEARNED RULES (filtered by active universe) ---"))
        lines.append(learned_result.get_projected_content(asp_converter=_asp_converter))
        
        # Story rules (filtered by active universe)
        story_result = RuleManager.project_story_rules(rule_registry, active_universe)
        lines.append(_asp_converter.rule_header_to_asp("--- STORY RULES (filtered by active universe) ---"))
        lines.append(story_result.get_projected_content(asp_converter=_asp_converter))
        
        return "\n".join(lines)
    
    @staticmethod
    def _get_rule_content(rule) -> Optional[str]:
        """
        Get rule content from file or directly.
        
        Args:
            rule: Rule object with content or file path
            
        Returns:
            Rule content string or None if failed
        """
        if rule.is_file:
            try:
                return Path(rule.content).read_text()
            except Exception as e:
                logger.warning(f"Could not read rule file {rule.content}: {e}")
                return None
        else:
            return rule.content
