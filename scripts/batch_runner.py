#!/usr/bin/env python3
"""Batch experiment runner for narrative linter.

Runs the story linter on multiple stories and collects results.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def run_story(story_path, output_dir, api_key, delay_between_runs=30):
    """Run the linter on a single story and save results."""
    story_name = Path(story_path).stem
    output_json = output_dir / f"{story_name}_result.json"
    output_log = output_dir / f"{story_name}_log.txt"
    
    cmd = [
        sys.executable, "scripts/story_lint.py",
        "--mode", "both",
        "--llm-backend", "gemini",
        "--llm-model", "gemini-2.5-flash",
        "--llm-base-url", "https://generativelanguage.googleapis.com/v1beta",
        "--llm-api-key", api_key,
        "--struct-backend", "gemini", 
        "--struct-model", "gemini-2.5-flash",
        "--struct-base-url", "https://generativelanguage.googleapis.com/v1beta",
        "--struct-api-key", api_key,
        "--llm-timeout", "180",
        "--struct-timeout", "180",
        "--llm-retries", "5",
        "--struct-retries", "5",
        "--llm-backoff", "30",
        "--struct-backoff", "30",
        str(story_path)
    ]
    
    print(f"\n{'='*60}")
    print(f"Processing: {story_name}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout per story
        )
        
        # Save log
        with open(output_log, 'w') as f:
            f.write(f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}")
        
        # Parse and save JSON
        try:
            # Find JSON in stdout
            stdout = result.stdout
            json_start = stdout.find('{')
            if json_start >= 0:
                json_data = json.loads(stdout[json_start:])
                json_data['story_file'] = str(story_path)
                json_data['story_name'] = story_name
                
                with open(output_json, 'w') as f:
                    json.dump(json_data, f, indent=2)
                
                return {
                    'story': story_name,
                    'success': True,
                    'llm_errors': json_data.get('llm_lint', {}).get('error_count', 0),
                    'logic_errors': json_data.get('logic_lint', {}).get('error_count', 0),
                    'total': json_data.get('total_errors', 0)
                }
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}")
            
        return {
            'story': story_name,
            'success': False,
            'error': result.stderr[:500] if result.stderr else "Unknown error"
        }
        
    except subprocess.TimeoutExpired:
        return {
            'story': story_name,
            'success': False,
            'error': "Timeout after 10 minutes"
        }
    except Exception as e:
        return {
            'story': story_name,
            'success': False,
            'error': str(e)
        }

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Run batch narrative linting experiments')
    parser.add_argument('input_dir', help='Directory containing story files')
    parser.add_argument('output_dir', help='Directory for results')
    parser.add_argument('--delay', type=int, default=45, help='Delay between stories (seconds)')
    args = parser.parse_args()
    
    # Get API key
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        env_file = Path('.env')
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith('GEMINI_API_KEY='):
                    api_key = line.split('=', 1)[1]
                    break
    
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found")
        sys.exit(1)
    
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all story files
    stories = sorted(input_dir.glob('*.txt'))
    print(f"Found {len(stories)} stories in {input_dir}")
    
    results = []
    for i, story in enumerate(stories):
        result = run_story(story, output_dir, api_key)
        results.append(result)
        
        if result['success']:
            print(f"  ✓ LLM: {result['llm_errors']} | Logic: {result['logic_errors']} | Total: {result['total']}")
        else:
            print(f"  ✗ Error: {result.get('error', 'Unknown')[:100]}")
        
        # Delay between stories to avoid rate limiting
        if i < len(stories) - 1:
            print(f"  Waiting {args.delay}s before next story...")
            time.sleep(args.delay)
    
    # Save summary
    summary = {
        'total_stories': len(stories),
        'successful': sum(1 for r in results if r['success']),
        'failed': sum(1 for r in results if not r['success']),
        'results': results
    }
    
    summary_file = output_dir / 'batch_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*60}")
    print("BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"Successful: {summary['successful']}/{summary['total_stories']}")
    print(f"Results saved to: {output_dir}")
    
    return results

if __name__ == '__main__':
    main()
