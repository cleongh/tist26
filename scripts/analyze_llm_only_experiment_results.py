"""
Script to analyze experiment results and generate reports.

This script loads experiment data from:
- step1_llm_log.jsonl (JSONL format - LLM interaction logs)
- step1_llm_results.json (JSON format - experiment results)
- harry_potter_errors.csv (CSV format - error checklist)
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any


def find_experiment_files(experiment_dir: Path) -> Dict[str, Path]:
    """
    Find the relevant experiment files in the given directory.
    
    Args:
        experiment_dir: Path to the experiment directory
        
    Returns:
        Dictionary mapping file type to file path
    """
    files = {
        'llm_log': None,
        'llm_results': None
    }
    
    # Look for step1_llm_log.jsonl
    llm_log_path = experiment_dir / 'step1_llm_log.jsonl'
    if llm_log_path.exists():
        files['llm_log'] = llm_log_path
    
    # Look for step1_llm_results.json
    llm_results_path = experiment_dir / 'step1_llm_results.json'
    if llm_results_path.exists():
        files['llm_results'] = llm_results_path
    
    return files


def load_jsonl_file(file_path: Path) -> List[Dict[str, Any]]:
    """
    Load a JSONL file (one JSON object per line).
    
    Args:
        file_path: Path to the JSONL file
        
    Returns:
        List of dictionaries, one per line
    """
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:  # Skip empty lines
                data.append(json.loads(line))
    return data


def load_json_file(file_path: Path) -> Dict[str, Any]:
    """
    Load a JSON file.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        Dictionary containing the JSON data
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_csv_file(file_path: Path) -> List[Dict[str, str]]:
    """
    Load a CSV file.
    
    Args:
        file_path: Path to the CSV file
        
    Returns:
        List of dictionaries, one per row
    """
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data


def group_results_by_story(llm_results: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group LLM results by story name.
    
    Args:
        llm_results: The loaded LLM results JSON object
        
    Returns:
        Dictionary mapping story names to lists of result entries
    """
    grouped = {}
    
    if not llm_results or 'results' not in llm_results:
        return grouped
    
    for entry in llm_results['results']:
        story_name = entry.get('story_name', 'unknown')
        
        if story_name not in grouped:
            grouped[story_name] = []
        
        grouped[story_name].append(entry)
    
    return grouped


def group_log_by_story(llm_log: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group LLM log entries by story name.
    
    Args:
        llm_log: The loaded LLM log data (list of log entries)
        
    Returns:
        Dictionary mapping story names to lists of log entries
    """
    grouped = {}
    
    if not llm_log:
        return grouped
    
    for entry in llm_log:
        story_name = entry.get('story', 'unknown')
        
        if story_name not in grouped:
            grouped[story_name] = []
        
        grouped[story_name].append(entry)
    
    return grouped


def normalize_story_name(story_name: str) -> str:
    """
    Normalize a story name for CSV file matching.
    Converts to lowercase and replaces spaces with underscores.
    
    Args:
        story_name: The original story name
        
    Returns:
        Normalized story name
    """
    return story_name.lower().replace(' ', '_')


def extract_errors_for_chapters(all_stories: List[str],
                                 grouped_results: Dict[str, List[Dict[str, Any]]],
                                 error_checklists: Dict[str, List[Dict[str, str]]],
                                 output_dir: Path) -> None:
    """
    Extract errors from JSON results for chapters that have errors in CSV checklists.
    Creates new CSV files with the extracted errors.
    
    Args:
        all_stories: List of all unique story names
        grouped_results: Grouped results by story
        error_checklists: Dictionary of error checklists by book name
        output_dir: Directory to save the output CSV files
    """
    output_dir.mkdir(exist_ok=True)
    
    for story in all_stories:
        normalized = normalize_story_name(story)
        
        # Check if we have error checklist for this story
        if normalized not in error_checklists:
            print(f"Skipping {story}: No error checklist found")
            continue
        
        # Get error checklist and results for this story
        error_list = error_checklists[normalized]
        results = grouped_results.get(story, [])
        
        if not results:
            print(f"Skipping {story}: No results found in JSON")
            continue
        
        # Get unique chapters from error checklist
        error_chapters = set()
        for error_entry in error_list:
            chapter = error_entry.get('Chapter', '').strip()
            if chapter:
                error_chapters.add(chapter)
        
        print(f"\nProcessing {story}:")
        print(f"  Chapters with errors in CSV: {len(error_chapters)}")
        
        # Build chapter to results mapping for MODIFIED variant only
        chapter_to_results = {}
        for result in results:
            chapter_file = result.get('chapter_file', '')
            variant = result.get('variant', '')
            # Only include modified variant chapters
            if chapter_file and variant == 'modified':
                chapter_to_results[chapter_file] = result
        
        # Extract errors for chapters that appear in error checklist
        extracted_errors = []
        chapters_found = 0
        
        for chapter in error_chapters:
            # Try to find matching result entry
            if chapter in chapter_to_results:
                result = chapter_to_results[chapter]
                chapters_found += 1
                
                # Get errors from this chapter
                errors = result.get('errors', [])
                for error in errors:
                    extracted_errors.append({
                        'Chapter': result.get('chapter_file', ''),
                        'Category': error.get('category', ''),
                        'Description': error.get('description', '')
                    })
        
        print(f"  Chapters found in JSON (modified variant): {chapters_found}/{len(error_chapters)}")
        print(f"  Total errors extracted: {len(extracted_errors)}")
        
        # Write to new CSV file
        if extracted_errors:
            output_file = output_dir / f"{normalized}_extracted_errors.csv"
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['Chapter', 'Category', 'Description'])
                writer.writeheader()
                writer.writerows(extracted_errors)
            print(f"  Output written to: {output_file}")
        else:
            print(f"  No errors extracted (no matching chapters found)")


def generate_aggregate_report(all_stories: List[str],
                              grouped_results: Dict[str, List[Dict[str, Any]]],
                              output_dir: Path) -> None:
    """
    Generate an aggregate CSV report with total errors per story and per variant.
    
    Args:
        all_stories: List of all unique story names
        grouped_results: Grouped results by story
        output_dir: Directory to save the output CSV file
    """
    output_dir.mkdir(exist_ok=True)
    
    print("\nGenerating aggregate report...")
    
    aggregate_data = []
    
    for story in all_stories:
        results = grouped_results.get(story, [])
        
        if not results:
            continue
        
        # Count errors by variant and collect errors for comparison
        variant_counts = {}
        total_errors = 0
        original_errors_set = set()
        modified_errors_set = set()
        
        for result in results:
            variant = result.get('variant', 'unknown')
            chapter = result.get('chapter_file', '')
            errors = result.get('errors', [])
            error_count = len(errors)
            
            total_errors += error_count
            
            if variant not in variant_counts:
                variant_counts[variant] = 0
            variant_counts[variant] += error_count
            
            # Collect error signatures for comparison (chapter + category + description)
            for error in errors:
                error_signature = (
                    chapter,
                    error.get('category', ''),
                    error.get('description', '').strip().lower()
                )
                
                if variant == 'original':
                    original_errors_set.add(error_signature)
                elif variant == 'modified':
                    modified_errors_set.add(error_signature)
        
        # Find common errors (errors that appear in both original and modified variants)
        common_errors = original_errors_set.intersection(modified_errors_set)
        common_error_count = len(common_errors)
        
        # Create row for this story
        row = {
            'Story': story,
            'Total_Errors': total_errors,
            'Original_Errors': variant_counts.get('original', 0),
            'Modified_Errors': variant_counts.get('modified', 0),
            'Common_Errors': common_error_count,
            'Only_Original': len(original_errors_set - modified_errors_set),
            'Only_Modified': len(modified_errors_set - original_errors_set)
        }
        
        aggregate_data.append(row)
        print(f"  {story}: Total={total_errors}, Original={row['Original_Errors']}, Modified={row['Modified_Errors']}, Common={common_error_count}")
    
    # Write aggregate report
    if aggregate_data:
        output_file = output_dir / 'aggregate_error_report.csv'
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['Story', 'Total_Errors', 'Original_Errors', 'Modified_Errors', 
                         'Common_Errors', 'Only_Original', 'Only_Modified']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(aggregate_data)
        print(f"\nAggregate report written to: {output_file}")


def generate_full_gathered_errors(all_stories: List[str],
                                   grouped_results: Dict[str, List[Dict[str, Any]]],
                                   output_dir: Path) -> None:
    """
    Generate CSV files with all errors per story, organized by chapter with separate columns for original and modified variants.
    
    Args:
        all_stories: List of all unique story names
        grouped_results: Grouped results by story
        output_dir: Directory to save the output CSV files
    """
    output_dir.mkdir(exist_ok=True)
    
    print("\nGenerating full gathered errors per story...")
    
    for story in all_stories:
        results = grouped_results.get(story, [])
        
        if not results:
            continue
        
        # Group errors by chapter and variant
        chapter_errors = {}
        
        for result in results:
            variant = result.get('variant', 'unknown')
            chapter = result.get('chapter_file', '')
            errors = result.get('errors', [])
            
            if not chapter:
                continue
            
            if chapter not in chapter_errors:
                chapter_errors[chapter] = {'original': [], 'modified': []}
            
            # Collect error descriptions
            for error in errors:
                error_text = f"[{error.get('category', 'unknown')}] {error.get('description', '')}"
                if variant == 'original':
                    chapter_errors[chapter]['original'].append(error_text)
                elif variant == 'modified':
                    chapter_errors[chapter]['modified'].append(error_text)
        
        # Build rows for CSV
        rows = []
        for chapter in sorted(chapter_errors.keys()):
            original_errors = chapter_errors[chapter]['original']
            modified_errors = chapter_errors[chapter]['modified']
            
            # Get the maximum number of errors for this chapter
            max_errors = max(len(original_errors), len(modified_errors))
            
            # Create a row for each error, pairing original and modified when both exist
            for i in range(max_errors):
                rows.append({
                    'Chapter': chapter,
                    'Error_Original': original_errors[i] if i < len(original_errors) else '',
                    'Error_Modified': modified_errors[i] if i < len(modified_errors) else ''
                })
        
        # Write to CSV
        if rows:
            normalized = normalize_story_name(story)
            output_file = output_dir / f"{normalized}_full_gathered_errors.csv"
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['Chapter', 'Error_Original', 'Error_Modified']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"  {story}: {len(rows)} chapters written to {output_file.name}")


def get_all_story_names(grouped_results: Dict[str, List[Dict[str, Any]]], 
                        grouped_log: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """
    Get a list of all unique story names from both grouped results and log.
    
    Args:
        grouped_results: Grouped results by story
        grouped_log: Grouped log entries by story
        
    Returns:
        Sorted list of unique story names
    """
    all_stories = set()
    
    # Add stories from results
    all_stories.update(grouped_results.keys())
    
    # Add stories from log
    all_stories.update(grouped_log.keys())
    
    # Remove 'unknown' if present
    all_stories.discard('unknown')
    
    return sorted(list(all_stories))


def generate_data_summary(all_stories: List[str],
                         grouped_results: Dict[str, List[Dict[str, Any]]],
                         grouped_log: Dict[str, List[Dict[str, Any]]],
                         error_checklists: Dict[str, List[Dict[str, str]]]) -> None:
    """
    Generate and display a summary of collected data.
    
    Args:
        all_stories: List of all unique story names
        grouped_results: Grouped results by story
        grouped_log: Grouped log entries by story
        error_checklists: Dictionary of error checklists by book name
    """
    print("\n" + "=" * 80)
    print("DATA COLLECTION SUMMARY")
    print("=" * 80)
    
    print(f"\nTotal unique stories detected: {len(all_stories)}")
    print("\nStory names and CSV files:")
    for story in all_stories:
        normalized = normalize_story_name(story)
        csv_found = normalized in error_checklists
        csv_status = f"[FOUND] {normalized}_errors.csv" if csv_found else "[NOT FOUND] No CSV file"
        print(f"  - {story}")
        print(f"      Normalized: {normalized}")
        print(f"      CSV file:   {csv_status}")
    
    print("\n" + "-" * 80)
    print("PER-STORY BREAKDOWN:")
    print("-" * 80)
    
    for story in all_stories:
        normalized = normalize_story_name(story)
        num_results = len(grouped_results.get(story, []))
        num_logs = len(grouped_log.get(story, []))
        num_errors = len(error_checklists.get(normalized, []))
        
        print(f"\n{story}:")
        print(f"  Normalized name:          {normalized}")
        print(f"  Number of result entries: {num_results}")
        print(f"  Number of log entries:    {num_logs}")
        print(f"  Number of errors in CSV:  {num_errors}")
    
    print("\n" + "=" * 80)


def load_all_data(experiment_name: str) -> Dict[str, Any]:
    """
    Load all relevant data for analysis.
    
    Args:
        experiment_name: Name of the experiment directory
        
    Returns:
        Dictionary containing all loaded data
    """
    # Set up paths
    root_dir = Path(__file__).parent.parent
    experiment_dir = root_dir / 'experiments' / experiment_name
    errors_dir = root_dir / 'errors_checklist'
    
    # Initialize data storage
    loaded_data = {
        'llm_log': None,
        'llm_results': None,
        'error_checklists': {}
    }
    
    # Find and load experiment files
    experiment_files = find_experiment_files(experiment_dir)
    
    if experiment_files['llm_log']:
        print(f"Loading LLM log from: {experiment_files['llm_log']}")
        loaded_data['llm_log'] = load_jsonl_file(experiment_files['llm_log'])
        print(f"  Loaded {len(loaded_data['llm_log'])} log entries")
    
    if experiment_files['llm_results']:
        print(f"Loading LLM results from: {experiment_files['llm_results']}")
        loaded_data['llm_results'] = load_json_file(experiment_files['llm_results'])
        print(f"  Loaded results with {len(loaded_data['llm_results'].get('results', []))} entries")
    
    # Load error checklists
    if errors_dir.exists():
        print(f"\nLoading error checklists from: {errors_dir}")
        for csv_file in errors_dir.glob('*.csv'):
            book_name = csv_file.stem.replace('_errors', '')
            print(f"  Loading {book_name} errors...")
            loaded_data['error_checklists'][book_name] = load_csv_file(csv_file)
            print(f"    Loaded {len(loaded_data['error_checklists'][book_name])} errors")
    
    return loaded_data


def main():
    """Main entry point for the script."""
    # Specify the experiment to analyze
    experiment_name = '11_openai_full_only_llm'
    
    print(f"Loading data for experiment: {experiment_name}")
    print("=" * 60)
    
    # Load all data
    data = load_all_data(experiment_name)
    
    # Summary
    print("\n" + "=" * 60)
    print("Data loading complete!")
    print(f"  LLM log entries: {len(data['llm_log']) if data['llm_log'] else 0}")
    print(f"  LLM results: {len(data['llm_results'].get('results', [])) if data['llm_results'] else 0}")
    print(f"  Error checklist books: {len(data['error_checklists'])}")
    for book, errors in data['error_checklists'].items():
        print(f"    - {book}: {len(errors)} errors")
    
    # Group results by story
    print("\n" + "=" * 60)
    print("Grouping results by story...")
    grouped_results = group_results_by_story(data['llm_results'])
    print(f"Found {len(grouped_results)} unique stories:")
    for story_name, entries in grouped_results.items():
        print(f"  - {story_name}: {len(entries)} entries")
    
    # Group log entries by story
    print("\n" + "=" * 60)
    print("Grouping log entries by story...")
    grouped_log = group_log_by_story(data['llm_log'])
    print(f"Found {len(grouped_log)} unique stories in log:")
    for story_name, entries in grouped_log.items():
        print(f"  - {story_name}: {len(entries)} log entries")
    
    # Get list of all unique stories
    print("\n" + "=" * 60)
    print("Extracting all unique story names...")
    all_stories = get_all_story_names(grouped_results, grouped_log)
    print(f"Total unique stories detected: {len(all_stories)}")
    print("Stories:")
    for story in all_stories:
        print(f"  - {story}")
    
    # Generate and display summary
    generate_data_summary(all_stories, grouped_results, grouped_log, data['error_checklists'])
    
    # Extract errors for chapters with known errors
    print("\n" + "=" * 60)
    print("Extracting errors for chapters in error checklists...")
    print("=" * 60)
    
    root_dir = Path(__file__).parent.parent
    output_dir = root_dir / 'experiments' / experiment_name / 'extracted_errors'
    extract_errors_for_chapters(all_stories, grouped_results, data['error_checklists'], output_dir)
    
    # Generate aggregate report
    print("\n" + "=" * 60)
    print("Generating aggregate error report...")
    print("=" * 60)
    generate_aggregate_report(all_stories, grouped_results, output_dir)
    
    # Generate full gathered errors per story
    print("\n" + "=" * 60)
    print("Generating full gathered errors per story...")
    print("=" * 60)
    generate_full_gathered_errors(all_stories, grouped_results, output_dir)
    
    print("\n" + "=" * 60)
    print("Processing complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
