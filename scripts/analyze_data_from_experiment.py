#!/usr/bin/env python3
"""
Experiment Data Analyzer

Analyzes experiment data for a specific story, comparing chapters with
implanted errors against the extraction and evaluation results.

Usage:
    python scripts/analyze_data_from_experiment.py <experiment_name> <story_name>
    
Example:
    python scripts/analyze_data_from_experiment.py 05_openai_one_book "Harry Potter"
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def normalize_story_name(name: str) -> str:
    """Convert story name to lowercase snake_case."""
    # Replace spaces and special chars with underscores
    normalized = re.sub(r'[^a-zA-Z0-9]+', '_', name.lower())
    # Remove leading/trailing underscores and collapse multiple underscores
    normalized = re.sub(r'_+', '_', normalized).strip('_')
    return normalized


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file into a list of dictionaries."""
    entries = []
    if not path.exists():
        return entries
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file."""
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_errors_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """Load the implanted errors CSV file."""
    errors = []
    if not csv_path.exists():
        return errors
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            errors.append({
                'chunk': row.get('Chunk', ''),
                'chapter': row.get('Chapter', ''),
                'error_type': row.get('Error Type', ''),
                'error_description': row.get('Error description', ''),
                'error_sentence': row.get('Error sentence', ''),
            })
    return errors


def filter_by_story(entries: List[Dict], story_name: str) -> List[Dict]:
    """Filter JSONL entries by story name (case-insensitive)."""
    story_lower = story_name.lower()
    return [e for e in entries if e.get('story', '').lower() == story_lower]


def filter_by_variant(entries: List[Dict], variant: str) -> List[Dict]:
    """Filter entries by variant (original/modified)."""
    return [e for e in entries if e.get('variant', '').lower() == variant.lower()]


def filter_by_chapter(entries: List[Dict], chapter_num: int) -> List[Dict]:
    """Filter entries by chapter number."""
    return [e for e in entries if e.get('chapter') == chapter_num]


def get_processed_chapters(extractions: List[Dict]) -> Set[int]:
    """Get set of processed chapter numbers from extractions."""
    return {e.get('chapter') for e in extractions if e.get('chapter') is not None}


def chapter_file_to_number(chapter_file: str) -> int:
    """Convert chapter filename (e.g., '003.txt') to chapter number (3)."""
    match = re.match(r'(\d+)', chapter_file)
    if match:
        return int(match.group(1))
    return -1


def aggregate_entities_from_extractions(
    extractions: List[Dict]
) -> Dict[str, Any]:
    """Aggregate all entities (characters, locations, items, relationships) from extractions."""
    all_characters: Dict[str, Dict] = {}
    all_locations: Dict[str, Dict] = {}
    all_items: Dict[str, Dict] = {}
    all_events: List[Dict] = []
    all_relationships: List[Dict] = []
    
    for entry in extractions:
        extraction = entry.get('extraction', {})
        entities = extraction.get('entities', {})
        
        # Characters
        for char in entities.get('characters', []):
            char_id = char.get('id', '')
            if char_id:
                if char_id not in all_characters:
                    all_characters[char_id] = {
                        'id': char_id,
                        'name': char.get('name', char_id),
                        'aliases': set(),
                        'first_seen_chapter': entry.get('chapter', 0),
                    }
                # Add any aliases
                for alias in char.get('aliases', []):
                    all_characters[char_id]['aliases'].add(alias)
        
        # Locations
        for loc in entities.get('locations', []):
            loc_id = loc.get('id', '')
            if loc_id:
                if loc_id not in all_locations:
                    all_locations[loc_id] = {
                        'id': loc_id,
                        'name': loc.get('name', loc_id),
                        'first_seen_chapter': entry.get('chapter', 0),
                    }
        
        # Items
        for item in entities.get('items', []):
            item_id = item.get('id', '')
            if item_id:
                if item_id not in all_items:
                    all_items[item_id] = {
                        'id': item_id,
                        'name': item.get('name', item_id),
                        'first_seen_chapter': entry.get('chapter', 0),
                    }
        
        # Relationships
        for rel in entities.get('relationships', []):
            all_relationships.append({
                'from': rel.get('from', ''),
                'to': rel.get('to', ''),
                'type': rel.get('type', ''),
                'chapter': entry.get('chapter', 0),
            })
        
        # Events
        for event in extraction.get('events', []):
            all_events.append({
                **event,
                'chapter': entry.get('chapter', 0),
            })
    
    # Convert aliases sets to lists for JSON serialization
    for char_id, char_data in all_characters.items():
        char_data['aliases'] = list(char_data['aliases'])
    
    return {
        'characters': all_characters,
        'locations': all_locations,
        'items': all_items,
        'events': all_events,
        'relationships': all_relationships,
    }


def get_chapter_data(
    extractions: List[Dict],
    events_log: List[Dict],
    engine_results: Dict,
    chapter_num: int,
    variant: str,
) -> Dict[str, Any]:
    """Get all data for a specific chapter."""
    # Filter to this chapter and variant
    chapter_extractions = [
        e for e in extractions 
        if e.get('chapter') == chapter_num and e.get('variant', '').lower() == variant.lower()
    ]
    # Events from events_log (engine-processed events)
    chapter_events_from_log = [
        e.get('event', e) for e in events_log 
        if e.get('chapter') == chapter_num and e.get('variant', '').lower() == variant.lower()
    ]
    
    # Get errors from engine results
    chapter_errors = []
    for result in engine_results.get('results', []):
        if (result.get('chapter_number') == chapter_num and 
            result.get('variant', '').lower() == variant.lower()):
            chapter_errors = result.get('errors', [])
            break
    
    # Aggregate entities for this chapter
    entities = aggregate_entities_from_extractions(chapter_extractions)
    
    return {
        'chapter': chapter_num,
        'variant': variant,
        'items': {
            'total': len(entities['items']),
            'list': list(entities['items'].values()),
        },
        'characters': {
            'total': len(entities['characters']),
            'list': list(entities['characters'].values()),
        },
        'locations': {
            'total': len(entities['locations']),
            'list': list(entities['locations'].values()),
        },
        'events': {
            'total': len(entities['events']),
            'list': entities['events'],
        },
        'events_from_log': {
            'total': len(chapter_events_from_log),
            'list': chapter_events_from_log,
        },
        'relationships': {
            'total': len(entities['relationships']),
            'list': entities['relationships'],
        },
        'errors': {
            'total': len(chapter_errors),
            'list': chapter_errors,
        },
    }


def analyze_experiment(
    experiment_name: str,
    story_name: str,
    experiments_dir: Path,
    errors_checklist_dir: Path,
) -> Dict[str, Any]:
    """
    Analyze an experiment for a specific story.
    
    Returns a comprehensive report comparing implanted errors against
    the extraction and evaluation results.
    """
    experiment_dir = experiments_dir / experiment_name
    story_normalized = normalize_story_name(story_name)
    
    # Validate experiment exists
    if not experiment_dir.exists():
        raise ValueError(f"Experiment not found: {experiment_dir}")
    
    # Load implanted errors CSV
    csv_path = errors_checklist_dir / f"{story_normalized}_errors.csv"
    implanted_errors = load_errors_csv(csv_path)
    if not implanted_errors:
        print(f"Warning: No errors CSV found at {csv_path}")
    
    debug_logs_dir = experiment_dir / "debug_logs"

    # Load experiment data
    extractions = load_jsonl(experiment_dir / "step2_extractions.jsonl")
    events_log = load_jsonl(debug_logs_dir / "step2_events_log.jsonl")
    item_stats = load_jsonl(debug_logs_dir / "step2_item_stats.jsonl")
    alias_conflicts = load_jsonl(debug_logs_dir / "step2_alias_conflicts.jsonl")
    engine_results = load_json(experiment_dir / "step2_engine_results.json") or {}
    
    # Load lifecycle analysis if available
    lifecycle_original = load_json(
        experiment_dir / f"lifecycle_analysis_{story_normalized}_original.json"
    )
    lifecycle_modified = load_json(
        experiment_dir / f"lifecycle_analysis_{story_normalized}_modified.json"
    )
    
    # Filter data by story
    extractions = filter_by_story(extractions, story_name)
    events_log = filter_by_story(events_log, story_name)
    item_stats = filter_by_story(item_stats, story_name)
    alias_conflicts = filter_by_story(alias_conflicts, story_name)
    
    # Filter engine results by story
    story_results = [
        r for r in engine_results.get('results', [])
        if r.get('story_name', '').lower() == story_name.lower()
    ]
    engine_results['results'] = story_results
    
    # Determine processed chapters
    processed_chapters = get_processed_chapters(extractions)
    max_chapter = max(processed_chapters) if processed_chapters else 0
    
    # Filter implanted errors to only those in processed chapters
    relevant_errors = []
    for error in implanted_errors:
        chapter_num = chapter_file_to_number(error['chapter'])
        if chapter_num >= 0 and chapter_num <= max_chapter:
            error['chapter_number'] = chapter_num
            relevant_errors.append(error)
    
    chapters_with_errors = {e['chapter_number'] for e in relevant_errors}
    
    # Separate extractions by variant
    original_extractions = filter_by_variant(extractions, 'original')
    modified_extractions = filter_by_variant(extractions, 'modified')
    
    # Aggregate entities per variant
    original_entities = aggregate_entities_from_extractions(original_extractions)
    modified_entities = aggregate_entities_from_extractions(modified_extractions)
    
    # Build report
    report = {
        'experiment_name': experiment_name,
        'story_name': story_name,
        'story_normalized': story_normalized,
        'total_chapters_processed': len(processed_chapters),
        'chapters_with_implanted_errors': sorted(list(chapters_with_errors)),
        'summary': {
            'original': {
                'items': {
                    'total': len(original_entities['items']),
                    'list': list(original_entities['items'].values()),
                },
                'characters': {
                    'total': len(original_entities['characters']),
                    'list': list(original_entities['characters'].values()),
                },
                'locations': {
                    'total': len(original_entities['locations']),
                    'list': list(original_entities['locations'].values()),
                },
                'events': {
                    'total': len(original_entities['events']),
                    'list': original_entities['events'],
                },
                'relationships': {
                    'total': len(original_entities['relationships']),
                    'list': original_entities['relationships'],
                },
            },
            'modified': {
                'items': {
                    'total': len(modified_entities['items']),
                    'list': list(modified_entities['items'].values()),
                },
                'characters': {
                    'total': len(modified_entities['characters']),
                    'list': list(modified_entities['characters'].values()),
                },
                'locations': {
                    'total': len(modified_entities['locations']),
                    'list': list(modified_entities['locations'].values()),
                },
                'events': {
                    'total': len(modified_entities['events']),
                    'list': modified_entities['events'],
                },
                'relationships': {
                    'total': len(modified_entities['relationships']),
                    'list': modified_entities['relationships'],
                },
            },
        },
        'alias_conflicts': {
            'total': len(alias_conflicts),
            'list': alias_conflicts,
        },
        'item_stats': {
            'total_entries': len(item_stats),
            'list': item_stats,
        },
        'lifecycle_analysis': {
            'original': lifecycle_original,
            'modified': lifecycle_modified,
        },
        'chapters_with_errors': [],
    }
    
    # Detailed analysis for chapters with implanted errors
    for error in relevant_errors:
        chapter_num = error['chapter_number']
        
        # Get data for both variants
        original_data = get_chapter_data(
            extractions, events_log, engine_results, chapter_num, 'original'
        )
        modified_data = get_chapter_data(
            extractions, events_log, engine_results, chapter_num, 'modified'
        )
        
        chapter_analysis = {
            'chapter_number': chapter_num,
            'chapter_file': error['chapter'],
            'implanted_error': {
                'error_type': error['error_type'],
                'error_description': error['error_description'],
                'error_sentence': error['error_sentence'],
            },
            'original': original_data,
            'modified': modified_data,
        }
        
        report['chapters_with_errors'].append(chapter_analysis)
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Analyze experiment data for a specific story"
    )
    parser.add_argument(
        'experiment_name',
        type=str,
        help='Name of the experiment to analyze'
    )
    parser.add_argument(
        'story_name',
        type=str,
        help='Name of the story to analyze (e.g., "Harry Potter")'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file path (default: experiments/<experiment>/analysis_<story>.json)'
    )
    
    args = parser.parse_args()
    
    # Setup paths
    script_dir = Path(__file__).parent.resolve()
    repo_root = script_dir.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.state.config import ERRORS_CHECKLIST_DIR

    experiments_dir = repo_root / "experiments"
    errors_checklist_dir = ERRORS_CHECKLIST_DIR
    
    try:
        report = analyze_experiment(
            args.experiment_name,
            args.story_name,
            experiments_dir,
            errors_checklist_dir,
        )
        
        # Determine output path
        story_normalized = normalize_story_name(args.story_name)
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = experiments_dir / args.experiment_name / f"comparative_analysis_with_inserted_errors_{story_normalized}.json"
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write report
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"Analysis complete!")
        print(f"Report saved to: {output_path}")
        print(f"\nSummary:")
        print(f"  Story: {args.story_name}")
        print(f"  Experiment: {args.experiment_name}")
        print(f"  Total chapters processed: {report['total_chapters_processed']}")
        print(f"  Chapters with implanted errors: {len(report['chapters_with_errors'])}")
        print(f"\n  Original variant:")
        print(f"    Characters: {report['summary']['original']['characters']['total']}")
        print(f"    Locations: {report['summary']['original']['locations']['total']}")
        print(f"    Items: {report['summary']['original']['items']['total']}")
        print(f"    Events: {report['summary']['original']['events']['total']}")
        print(f"    Relationships: {report['summary']['original']['relationships']['total']}")
        print(f"\n  Modified variant:")
        print(f"    Characters: {report['summary']['modified']['characters']['total']}")
        print(f"    Locations: {report['summary']['modified']['locations']['total']}")
        print(f"    Items: {report['summary']['modified']['items']['total']}")
        print(f"    Events: {report['summary']['modified']['events']['total']}")
        print(f"    Relationships: {report['summary']['modified']['relationships']['total']}")
        print(f"\n  Alias conflicts: {report['alias_conflicts']['total']}")
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
