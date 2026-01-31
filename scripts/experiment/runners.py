"""
Experiment runner functions.

These functions orchestrate the experiment steps.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from ..state.config import (
    SOURCE_ORIGINAL_BOOKS,
    SOURCE_MODIFIED_BOOKS,
    RULES_DIR,
)
from ..state.data_structures import ChapterError, ChapterResult, StepResults
from ..state.logging import log
from ..extraction.api_clients import create_api_client
from ..extraction.llm_client import LLMClient
from ..extraction.chapter_extractor import structure_chapter_standalone
from ..extraction.lifecycle_tracker import LifecycleTracker
from ..logic.evaluator import LogicEvaluator


def get_chapter_files(story_dir: Path) -> List[Path]:
    """Get sorted list of chapter files."""
    return sorted(story_dir.glob("*.txt"))


def run_step1_llm(experiment_dir: Path, stories: List[str], llm_url: str, max_chapters: int = None,
                  api_mode: str = "local", api_model: str = None, api_delay: float = 0.0) -> StepResults:
    """
    Step 1: LLM-only evaluation, chapter by chapter.
    """
    log("=" * 60)
    log("STEP 1: LLM-Only Evaluation")
    log("=" * 60)
    
    results = StepResults(
        step=1,
        approach="llm",
        timestamp=datetime.now().isoformat(),
    )
    
    # Create log file for prompts/responses
    log_file = experiment_dir / "step1_llm_log.jsonl"
    log(f"Logging prompts/responses to: {log_file}")
    
    client = LLMClient(base_url=llm_url, log_file=log_file, api_mode=api_mode, api_model=api_model, api_delay=api_delay)
    
    if not client.check_server():
        log("LLM server not available!", "ERROR")
        return results
    
    log("LLM server is available")
    
    for story_name in stories:
        for variant in ["original", "modified"]:
            chapter_summaries: List[str] = []
            
            if variant == "original":
                story_dir = SOURCE_ORIGINAL_BOOKS / story_name
            else:
                story_dir = SOURCE_MODIFIED_BOOKS / story_name
            
            if not story_dir.exists():
                log(f"Story not found: {story_dir}", "WARN")
                continue
            
            log(f"\nProcessing: {story_name} ({variant})")
            if variant == "original":
                log(f"  NOTE: Original books are error-free references - expect few/no errors")
            else:
                log(f"  NOTE: Modified books have injected errors - expect errors to be detected")
            
            chapter_files = get_chapter_files(story_dir)
            
            if max_chapters is not None:
                chapter_files = chapter_files[:max_chapters]
            
            log(f"  Found {len(chapter_files)} chapters" + (f" (limited to {max_chapters})" if max_chapters else ""))
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                if chapter_summaries:
                    log(f"    (with {len(chapter_summaries)} previous chapter summaries for context)")
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                errors, duration, _, _, chapter_summary = client.evaluate_chapter(
                    chapter_text, 
                    story=story_name, 
                    variant=variant, 
                    chapter_name=chapter_file.name,
                    previous_summaries=chapter_summaries
                )
                
                if chapter_summary:
                    chapter_summaries.append(chapter_summary)
                else:
                    chapter_summaries.append(f"(Summary not available for {chapter_file.name})")
                
                chapter_errors = []
                for e in errors:
                    chapter_errors.append(ChapterError(
                        chapter_file=chapter_file.name,
                        category=e.get("category", "unknown"),
                        error_type=e.get("error_type", "unknown"),
                        description=e.get("description", ""),
                        story_fragment=e.get("story_fragment", ""),
                    ))
                
                result = ChapterResult(
                    story_name=story_name,
                    variant=variant,
                    chapter_file=chapter_file.name,
                    chapter_number=i,
                    errors=chapter_errors,
                    duration_seconds=duration,
                    success=True,
                )
                
                results.results.append(result)
                results.chapters_processed += 1
                results.total_errors += len(chapter_errors)
                
                log(f"    -> {len(chapter_errors)} errors ({duration:.1f}s)")
    
    # Save results
    output_file = experiment_dir / "step1_llm_results.json"
    with open(output_file, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    
    log(f"\nStep 1 complete: {results.chapters_processed} chapters, {results.total_errors} errors")
    log(f"Results saved to: {output_file}")
    
    return results


def run_step2_logic(experiment_dir: Path, stories: List[str], llm_url: str, max_chapters: int = None,
                    api_mode: str = "local", api_model: str = None, api_delay: float = 0.0,
                    structured: bool = False) -> StepResults:
    """
    Step 2: Logic-based evaluation (ILASP + Clingo), chapter by chapter.
    
    Args:
        structured: If True, use Phase 4 structured output (no LLM interpretation)
    """
    log("=" * 60)
    log("STEP 2: Logic-Based Evaluation (ILASP + Clingo)")
    if structured:
        log("Mode: STRUCTURED OUTPUT (Phase 4 - no LLM interpretation)")
    log("=" * 60)
    
    results = StepResults(
        step=2,
        approach="logic",
        timestamp=datetime.now().isoformat(),
    )
    
    log_file = experiment_dir / "step2_logic_log.jsonl"
    log(f"Logging prompts/responses to: {log_file}")
    
    event_log_file = experiment_dir / "step2_events_log.jsonl"
    log(f"Logging events to: {event_log_file}")
    
    evaluator = LogicEvaluator(base_url=llm_url, log_file=log_file, api_mode=api_mode, api_model=api_model, api_delay=api_delay)
    evaluator.event_log_file = event_log_file
    
    with open(event_log_file, "w") as f:
        f.write("")
    
    for story_name in stories:
        for variant in ["original", "modified"]:
            if variant == "original":
                story_dir = SOURCE_ORIGINAL_BOOKS / story_name
            else:
                story_dir = SOURCE_MODIFIED_BOOKS / story_name
            
            if not story_dir.exists():
                log(f"Story not found: {story_dir}", "WARN")
                continue
            
            log(f"\nProcessing: {story_name} ({variant})")
            
            evaluator.reset()
            
            chapter_files = get_chapter_files(story_dir)
            
            if max_chapters is not None:
                chapter_files = chapter_files[:max_chapters]
            
            log(f"  Found {len(chapter_files)} chapters" + (f" (limited to {max_chapters})" if max_chapters else ""))
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                if structured:
                    errors, duration = evaluator.evaluate_chapter_v2(
                        chapter_text, i,
                        story=story_name,
                        variant=variant,
                        chapter_name=chapter_file.name
                    )
                else:
                    errors, duration = evaluator.evaluate_chapter(
                        chapter_text, i,
                        story=story_name,
                        variant=variant,
                        chapter_name=chapter_file.name
                    )
                
                chapter_errors = []
                for e in errors:
                    chapter_errors.append(ChapterError(
                        chapter_file=chapter_file.name,
                        category=e.get("category", "unknown"),
                        error_type=e.get("error_type", "unknown"),
                        description=e.get("description", ""),
                        story_fragment=e.get("story_fragment", ""),
                    ))
                
                result = ChapterResult(
                    story_name=story_name,
                    variant=variant,
                    chapter_file=chapter_file.name,
                    chapter_number=i,
                    errors=chapter_errors,
                    duration_seconds=duration,
                    success=True,
                )
                
                results.results.append(result)
                results.chapters_processed += 1
                results.total_errors += len(chapter_errors)
                
                log(f"    -> {len(chapter_errors)} errors ({duration:.1f}s)")
    
    output_file = experiment_dir / "step2_logic_results.json"
    with open(output_file, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    
    log(f"\nStep 2 complete: {results.chapters_processed} chapters, {results.total_errors} errors")
    log(f"Results saved to: {output_file}")
    
    return results


def run_step2_debug(experiment_dir: Path, stories: List[str]) -> None:
    """
    Debug mode: Load existing extractions from step2_extractions.jsonl and run
    them through the Logic Engine without calling any LLM.
    """
    from engine import (
        StateManager, 
        RuleRegistry, 
        EventExecutor, 
        FinalAnalyzer,
        AliasResolver,
        ItemTracker,
    )
    
    log("=" * 60)
    log("DEBUG MODE: Logic Engine Analysis (No LLM)")
    log("=" * 60)
    log("This mode loads existing extractions and runs them through the engine")
    log("for detailed debugging. No LLM calls will be made.")
    log("=" * 60)
    
    extraction_file = experiment_dir / "step2_extractions.jsonl"
    if not extraction_file.exists():
        log(f"ERROR: No extractions file found at {extraction_file}", "ERROR")
        log("Run step 2 with an LLM first to generate extractions.")
        return
    
    log(f"\nLoading extractions from: {extraction_file}")
    extractions = []
    with open(extraction_file, "r") as f:
        for line in f:
            if line.strip():
                extractions.append(json.loads(line))
    
    log(f"Loaded {len(extractions)} chapter extractions")
    
    extraction_groups: Dict[Tuple[str, str], List[Dict]] = {}
    for ext in extractions:
        key = (ext["story"], ext["variant"])
        if key not in extraction_groups:
            extraction_groups[key] = []
        extraction_groups[key].append(ext)
    
    for key in extraction_groups:
        extraction_groups[key].sort(key=lambda x: x["chapter"])
    
    log(f"Found {len(extraction_groups)} story/variant combinations")
    
    debug_file = experiment_dir / "debug_engine.jsonl"
    debug_txt_file = experiment_dir / "debug_engine.txt"
    
    with open(debug_file, "w") as f:
        f.write("")
    with open(debug_txt_file, "w") as f:
        f.write(f"DEBUG ENGINE LOG - {datetime.now().isoformat()}\n")
        f.write("=" * 80 + "\n\n")
    
    def debug_log(message: str, entry: Dict = None):
        log(message)
        with open(debug_txt_file, "a") as f:
            f.write(message + "\n")
        if entry:
            with open(debug_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
    
    for (story_name, variant), chapter_extractions in extraction_groups.items():
        if stories and story_name not in stories:
            debug_log(f"Skipping {story_name} ({variant}) - not in requested stories")
            continue
        
        debug_log(f"\n{'='*60}")
        debug_log(f"PROCESSING: {story_name} ({variant})")
        debug_log(f"{'='*60}")
        
        state_manager = StateManager()
        rule_registry = RuleRegistry(RULES_DIR)
        rule_registry.load_legacy_rules()
        
        alias_resolver = AliasResolver()
        item_tracker = ItemTracker()
        event_executor = EventExecutor(state_manager, rule_registry)
        final_analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker, alias_resolver)
        
        story_violations = []
        all_events = []
        
        for ext in chapter_extractions:
            chapter_num = ext["chapter"]
            chapter_file = ext["chapter_file"]
            structured = ext.get("extraction", {})
            
            debug_log(f"\n--- Chapter {chapter_num}: {chapter_file} ---")
            
            entities = structured.get("entities", {})
            events = structured.get("events", [])
            initial_rules = structured.get("initial_rules", [])
            
            debug_entry = {
                "type": "chapter_input",
                "story": story_name,
                "variant": variant,
                "chapter": chapter_num,
                "chapter_file": chapter_file,
                "timestamp": datetime.now().isoformat(),
                "input": {
                    "characters": len(entities.get("characters", [])),
                    "locations": len(entities.get("locations", [])),
                    "items": len(entities.get("items", [])),
                    "relationships": len(entities.get("relationships", [])),
                    "events": len(events),
                    "initial_rules": len(initial_rules),
                },
                "entities": entities,
                "events": events,
                "initial_rules": initial_rules,
            }
            debug_log(f"  Input: {debug_entry['input']}", debug_entry)
            
            for char in entities.get("characters", []):
                debug_log(f"    Character: {char.get('id')} ({char.get('name')}) aliases={char.get('aliases', [])}")
            
            for item in entities.get("items", []):
                debug_log(f"    Item: {item.get('id')} ({item.get('name')}) relevance={item.get('relevance', 'unknown')}")
            
            for rel in entities.get("relationships", []):
                debug_log(f"    Relationship: {rel.get('from')} -> {rel.get('to')} ({rel.get('type')})")
            
            for event in events:
                debug_log(f"    Event: {event.get('id')} {event.get('type')} agent={event.get('agent')} patient={event.get('patient')}")
                debug_log(f"           source: {event.get('source_text', '')[:60]}...")
            
            structured, alias_conflicts = alias_resolver.normalize_extraction(structured, chapter_num)
            
            if alias_conflicts:
                for conflict in alias_conflicts:
                    conflict_entry = {
                        "type": "alias_conflict",
                        "story": story_name,
                        "variant": variant,
                        "chapter": chapter_num,
                        "conflict": conflict.to_dict(),
                    }
                    debug_log(f"  [ALIAS CONFLICT] {conflict.alias} -> {conflict.canonical_ids}", conflict_entry)
            
            structured = item_tracker.process_extraction(structured, chapter_num)
            
            item_stats = item_tracker.get_statistics()
            debug_log(f"  Item Tracker: {item_stats['active_items']} active, {item_stats['suppressed_items']} suppressed")
            
            debug_log(f"\n  Running EventExecutor.evaluate_chapter_structured()...")
            eval_result = event_executor.evaluate_chapter_structured(structured, chapter_num)
            
            for event in structured.get("events", []):
                all_events.append({
                    "chapter": chapter_num,
                    "global_id": event.get("global_id"),
                    "local_id": event.get("id"),
                    "type": event.get("type"),
                    "agent": event.get("agent"),
                    "patient": event.get("patient"),
                    "location": event.get("location"),
                })
                debug_log(f"    Event {event.get('global_id')} (was {event.get('id')}): {event.get('type')}")
            
            asp_lines = [line for line in eval_result.asp_facts.split('\n') if line.strip()]
            debug_log(f"\n  ASP Facts Generated ({len(asp_lines)} lines):")
            for fact in asp_lines[:20]:
                debug_log(f"    {fact}")
            if len(asp_lines) > 20:
                debug_log(f"    ... and {len(asp_lines) - 20} more facts")
            
            debug_log(f"\n  Violations Detected: {len(eval_result.violations)}")
            for v in eval_result.violations:
                violation_entry = {
                    "type": "violation",
                    "story": story_name,
                    "variant": variant,
                    "chapter": chapter_num,
                    "violation": v.to_dict(),
                }
                debug_log(f"    [VIOLATION] {v.category}/{v.violation_type}: {v.rule}", violation_entry)
                debug_log(f"                entities: {v.entities}")
                debug_log(f"                event: {v.event_id}")
                debug_log(f"                source: {v.source_text}")
                story_violations.append(v.to_dict())
            
            final_analyzer.record_chapter_evaluation(
                chapter_num=chapter_num,
                events=structured.get("events", []),
                violations=[v.to_dict() for v in eval_result.violations],
                entities=structured.get("entities", {}),
            )
            
            debug_log(f"\n  State after chapter {chapter_num}:")
            alias_stats_ch = alias_resolver.get_statistics()
            debug_log(f"    Characters known: {alias_stats_ch['total_canonical_ids']}")
            
            chapter_output = {
                "type": "chapter_output",
                "story": story_name,
                "variant": variant,
                "chapter": chapter_num,
                "asp_facts_count": len(eval_result.asp_facts),
                "violations_count": len(eval_result.violations),
                "events_processed": len(structured.get("events", [])),
            }
            debug_log("", chapter_output)
        
        debug_log(f"\n{'='*40}")
        debug_log(f"FINAL ANALYSIS: {story_name} ({variant})")
        debug_log(f"{'='*40}")
        
        story_id = f"{story_name}_{variant}"
        final_result = final_analyzer.analyze(story_id, len(chapter_extractions))
        
        debug_log(f"\nTotal events processed: {len(all_events)}")
        debug_log(f"Total violations: {len(story_violations)}")
        debug_log(f"Loose ends: {len(final_result.loose_ends)}")
        debug_log(f"Long-range inconsistencies: {len(final_result.long_range_inconsistencies)}")
        
        for le in final_result.loose_ends:
            le_entry = {
                "type": "loose_end",
                "story": story_name,
                "variant": variant,
                "loose_end": le.to_dict() if hasattr(le, 'to_dict') else str(le),
            }
            debug_log(f"  [LOOSE END] {le_entry['loose_end']}", le_entry)
        
        for lri in final_result.long_range_inconsistencies:
            lri_entry = {
                "type": "long_range_inconsistency",
                "story": story_name,
                "variant": variant,
                "inconsistency": lri.to_dict() if hasattr(lri, 'to_dict') else str(lri),
            }
            debug_log(f"  [LONG-RANGE] {lri_entry['inconsistency']}", lri_entry)
        
        debug_log(f"\n--- All Violations Summary ---")
        violation_by_type = {}
        for v in story_violations:
            vtype = v.get("violation_type", "unknown")
            if vtype not in violation_by_type:
                violation_by_type[vtype] = []
            violation_by_type[vtype].append(v)
        
        for vtype, violations in sorted(violation_by_type.items()):
            debug_log(f"  {vtype}: {len(violations)}")
            for v in violations[:5]:
                debug_log(f"    - ch{v.get('chapter', '?')}: {v.get('rule', 'unknown')}")
            if len(violations) > 5:
                debug_log(f"    ... and {len(violations) - 5} more")
        
        final_summary = {
            "type": "story_summary",
            "story": story_name,
            "variant": variant,
            "chapters_processed": len(chapter_extractions),
            "total_events": len(all_events),
            "total_violations": len(story_violations),
            "violations_by_type": {k: len(v) for k, v in violation_by_type.items()},
            "loose_ends": len(final_result.loose_ends),
            "long_range_inconsistencies": len(final_result.long_range_inconsistencies),
        }
        debug_log("", final_summary)
        
        alias_stats = alias_resolver.get_statistics()
        debug_log(f"\nAlias Resolver: {alias_stats['total_canonical_ids']} characters, "
                  f"{alias_stats['total_aliases']} aliases, "
                  f"{alias_stats['conflicts_detected']} conflicts")
        
        item_stats = item_tracker.get_statistics()
        debug_log(f"Item Tracker: {item_stats['total_items']} total, "
                  f"{item_stats['active_items']} active, "
                  f"{item_stats['suppressed_items']} suppressed, "
                  f"{item_stats['causal_items']} causal, "
                  f"{item_stats['latent_items']} latent")
    
    debug_log(f"\n{'='*60}")
    debug_log(f"DEBUG MODE COMPLETE")
    debug_log(f"{'='*60}")
    debug_log(f"Debug JSONL output: {debug_file}")
    debug_log(f"Debug text output: {debug_txt_file}")
    log(f"\nDebug files written:")
    log(f"  - {debug_file}")
    log(f"  - {debug_txt_file}")


def run_step2_engine(experiment_dir: Path, stories: List[str], llm_url: str, 
                     max_chapters: int = None, api_mode: str = "local", 
                     api_model: str = None, api_delay: float = 0.0,
                     use_split_extraction: bool = False,
                     llm_timeout: int = 300) -> StepResults:
    """
    Step 2 using the new engine modules (Phase 5).
    
    Args:
        use_split_extraction: If True, use Phase 2 four-function extraction pipeline
        llm_timeout: Timeout for LLM API calls in seconds (default: 300)
    """
    from engine import (
        StateManager, 
        RuleRegistry, 
        EventExecutor, 
        FinalAnalyzer,
        LearningAdapter,
        AliasResolver,
        build_continuity_context,
        ItemTracker,
    )
    
    log("=" * 60)
    log("STEP 2: Logic-Based Evaluation (Engine Modules - Phase 5)")
    if use_split_extraction:
        log("Mode: SPLIT EXTRACTION (Phase 2 - four independent LLM calls)")
    log("=" * 60)
    
    results = StepResults(
        step=2,
        approach="logic_engine",
        timestamp=datetime.now().isoformat(),
    )
    
    log_file = experiment_dir / "step2_engine_log.jsonl"
    event_log_file = experiment_dir / "step2_events_log.jsonl"
    extraction_log_file = experiment_dir / "step2_extractions.jsonl"
    alias_conflicts_file = experiment_dir / "step2_alias_conflicts.jsonl"
    item_stats_file = experiment_dir / "step2_item_stats.jsonl"
    final_analysis_file = experiment_dir / "step2_final_analysis.json"
    
    log(f"Logging to: {log_file}")
    log(f"Extractions log: {extraction_log_file}")
    log(f"Events log: {event_log_file}")
    log(f"Alias conflicts log: {alias_conflicts_file}")
    log(f"Item stats log: {item_stats_file}")
    
    api_client = create_api_client(api_mode, api_model, llm_url, api_delay)
    
    with open(event_log_file, "w") as f:
        f.write("")
    with open(extraction_log_file, "w") as f:
        f.write("")
    with open(alias_conflicts_file, "w") as f:
        f.write("")
    with open(item_stats_file, "w") as f:
        f.write("")
    
    for story_name in stories:
        for variant in ["original", "modified"]:
            if variant == "original":
                story_dir = SOURCE_ORIGINAL_BOOKS / story_name
            else:
                story_dir = SOURCE_MODIFIED_BOOKS / story_name
            
            if not story_dir.exists():
                log(f"Story not found: {story_dir}", "WARN")
                continue
            
            log(f"\nProcessing: {story_name} ({variant})")
            
            state_manager = StateManager()
            rule_registry = RuleRegistry(RULES_DIR)
            rule_registry.load_legacy_rules()
            
            alias_resolver = AliasResolver()
            item_tracker = ItemTracker()
            lifecycle_tracker = LifecycleTracker()  # Phase 6
            event_executor = EventExecutor(state_manager, rule_registry)
            final_analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker, alias_resolver)
            learning_adapter = LearningAdapter(rule_registry)
            
            chapter_files = get_chapter_files(story_dir)
            
            if max_chapters is not None:
                chapter_files = chapter_files[:max_chapters]
            
            log(f"  Found {len(chapter_files)} chapters" + (f" (limited to {max_chapters})" if max_chapters else ""))
            
            story_violations: List[Dict] = []
            
            for i, chapter_file in enumerate(chapter_files):
                log(f"  Chapter {i}: {chapter_file.name}")
                start_time = time.time()
                
                chapter_text = chapter_file.read_text(encoding="utf-8", errors="replace")
                
                continuity_context = build_continuity_context(
                    state_manager, alias_resolver, i
                )
                
                # Collect known entities from AliasResolver and ItemTracker for prompt injection
                known_characters_list = alias_resolver.format_known_characters_list()
                known_locations_list = alias_resolver.format_known_locations_list()
                known_items_with_states = item_tracker.format_known_items_with_states()
                
                structured, entity_registry, rel_normalizer, event_normalizer = structure_chapter_standalone(
                    chapter_text, 
                    api_client,
                    known_characters_json=continuity_context.to_characters_json(),
                    known_relationships_json=continuity_context.to_relationships_json(),
                    known_character_states_json=continuity_context.to_character_states_json(),
                    use_split_extraction=use_split_extraction,
                    use_entity_registry=use_split_extraction,  # Enable registry when using split extraction
                    use_relationship_normalizer=use_split_extraction,  # Enable normalizer when using split extraction
                    use_event_normalizer=use_split_extraction,  # Enable event normalizer when using split extraction
                    timeout=llm_timeout,
                    known_characters_list=known_characters_list,
                    known_locations_list=known_locations_list,
                    known_items_with_states=known_items_with_states,
                )
                
                # Log EntityRegistry warnings if present
                if entity_registry is not None:
                    registry_warnings = entity_registry.get_warnings()
                    if registry_warnings:
                        log(f"    [EntityRegistry] {len(registry_warnings)} warnings generated")
                        for warning in registry_warnings[:5]:  # Show first 5
                            log(f"      - {warning.phase}: {warning.context}", "WARN")
                        if len(registry_warnings) > 5:
                            log(f"      ... and {len(registry_warnings) - 5} more", "WARN")
                
                # Log RelationshipNormalizer groups if present
                if rel_normalizer is not None:
                    groups = rel_normalizer.get_groups()
                    if groups:
                        log(f"    [RelationshipNormalizer] {len(groups)} groups available for expansion")
                
                # Log EventNormalizer item classification if present
                if event_normalizer is not None:
                    causal_items = event_normalizer.get_causal_items()
                    latent_items = event_normalizer.get_latent_items()
                    if causal_items or latent_items:
                        log(f"    [EventNormalizer] Items: {len(causal_items)} causal, {len(latent_items)} latent")
                
                extraction_entry = {
                    "story": story_name,
                    "variant": variant,
                    "chapter": i,
                    "chapter_file": chapter_file.name,
                    "timestamp": datetime.now().isoformat(),
                    "continuity_context": continuity_context.to_dict(),
                    "extraction": structured,
                }
                with open(extraction_log_file, "a") as f:
                    f.write(json.dumps(extraction_entry) + "\n")
                
                structured, alias_conflicts = alias_resolver.normalize_extraction(structured, i)
                
                for conflict in alias_conflicts:
                    conflict_entry = {
                        "story": story_name,
                        "variant": variant,
                        "chapter": i,
                        "chapter_file": chapter_file.name,
                        "timestamp": datetime.now().isoformat(),
                        "conflict": conflict.to_dict(),
                    }
                    with open(alias_conflicts_file, "a") as f:
                        f.write(json.dumps(conflict_entry) + "\n")
                    log(f"    [ALIAS CONFLICT] '{conflict.alias}' -> {conflict.canonical_ids}", "WARN")
                
                structured = item_tracker.process_extraction(structured, i)
                
                # Phase 6: Update lifecycle tracker with chapter extraction
                lifecycle_tracker.process_chapter(i, structured, event_normalizer)
                
                item_stats = item_tracker.get_statistics()
                item_stats_entry = {
                    "story": story_name,
                    "variant": variant,
                    "chapter": i,
                    "chapter_file": chapter_file.name,
                    "timestamp": datetime.now().isoformat(),
                    "stats": item_stats,
                }
                with open(item_stats_file, "a") as f:
                    f.write(json.dumps(item_stats_entry) + "\n")
                
                eval_result = event_executor.evaluate_chapter_structured(
                    structured, i
                )
                
                for event in structured.get("events", []):
                    event_entry = {
                        "story": story_name,
                        "variant": variant,
                        "chapter": i,
                        "chapter_file": chapter_file.name,
                        "event": event,
                    }
                    with open(event_log_file, "a") as f:
                        f.write(json.dumps(event_entry) + "\n")
                
                final_analyzer.record_chapter_evaluation(
                    chapter_num=i,
                    events=structured.get("events", []),
                    violations=[v.to_dict() for v in eval_result.violations],
                    entities=structured.get("entities", {}),
                )
                
                if eval_result.violations:
                    learning_adapter.learn_rules_from_violations(
                        current_facts=eval_result.asp_facts,
                        violations=[v.to_dict() for v in eval_result.violations],
                        chapter_num=i,
                        story_id=story_name,
                    )
                
                duration = time.time() - start_time
                
                chapter_errors = []
                for v in eval_result.violations:
                    chapter_errors.append(ChapterError(
                        chapter_file=chapter_file.name,
                        category=v.category,
                        error_type=v.violation_type,
                        description=f"{v.rule}: {v.violation_type}",
                        story_fragment=v.source_text or "",
                    ))
                    story_violations.append(v.to_dict())
                
                result = ChapterResult(
                    story_name=story_name,
                    variant=variant,
                    chapter_file=chapter_file.name,
                    chapter_number=i,
                    errors=chapter_errors,
                    duration_seconds=duration,
                    success=True,
                )
                
                results.results.append(result)
                results.chapters_processed += 1
                results.total_errors += len(chapter_errors)
                
                log(f"    -> {len(chapter_errors)} errors ({duration:.1f}s)")
            
            story_id = f"{story_name}_{variant}"
            final_result = final_analyzer.analyze(story_id, len(chapter_files))
            
            # Phase 6: Run lifecycle tracker final analysis
            lifecycle_result = lifecycle_tracker.final_analysis()
            lifecycle_output = experiment_dir / f"lifecycle_analysis_{story_name.replace(' ', '_').lower()}_{variant}.json"
            with open(lifecycle_output, "w") as f:
                json.dump(lifecycle_result.to_dict(), f, indent=2)
            
            analysis_output = experiment_dir / f"final_analysis_{story_name.replace(' ', '_').lower()}_{variant}.json"
            with open(analysis_output, "w") as f:
                f.write(final_result.to_json())
            
            log(f"  Final analysis: {len(final_result.loose_ends)} loose ends, "
                f"{len(final_result.long_range_inconsistencies)} long-range issues")
            
            # Phase 6: Log lifecycle analysis summary
            log(f"  Lifecycle analysis: {len(lifecycle_result.loose_ends)} loose ends, "
                f"{len(lifecycle_result.back_annotations)} back-annotations")
            
            alias_stats = alias_resolver.get_statistics()
            log(f"  Alias resolver: {alias_stats['total_canonical_ids']} characters, "
                f"{alias_stats['total_aliases']} aliases, "
                f"{alias_stats['conflicts_detected']} conflicts")
            
            item_stats = item_tracker.get_statistics()
            log(f"  Item tracker: {item_stats['total_items']} items, "
                f"{item_stats['active_items']} active, "
                f"{item_stats['suppressed_items']} suppressed, "
                f"{item_stats['causal_items']} causal, "
                f"{item_stats['latent_items']} latent")
            
            # Phase 6: Log lifecycle stats
            lifecycle_stats = lifecycle_tracker.get_statistics()
            log(f"  Lifecycle tracker: {lifecycle_stats['characters']} chars, "
                f"{lifecycle_stats['items']} items, "
                f"{lifecycle_stats['causal_items']} causal, "
                f"{lifecycle_stats['latent_items']} latent, "
                f"{lifecycle_stats['promoted_items']} promoted")
            
            final_analyzer.reset()
            lifecycle_tracker.reset()  # Reset for next story/variant
    
    output_file = experiment_dir / "step2_engine_results.json"
    with open(output_file, "w") as f:
        json.dump(results.to_dict(), f, indent=2)
    
    log(f"\nStep 2 (Engine) complete: {results.chapters_processed} chapters, {results.total_errors} errors")
    log(f"Results saved to: {output_file}")
    
    return results
