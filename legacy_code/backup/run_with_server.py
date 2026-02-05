#!/usr/bin/env python3
"""
run_with_server.py - Run experiment assuming server is already running
======================================================================

This script assumes a llamafile server is already running on port 8080.
It does NOT attempt to start or manage the server.

Usage:
    1. Start your llamafile server manually:
       /path/to/llamafile --port 8080 --gpu nvidia -ngl 99999
       
    2. Run this experiment:
       python3 scripts/run_with_server.py --model-name "gemma"

The script will:
- Verify server is responding on port 8080
- Run both LLM and logic-based linting on modified books
- Generate reports in experiments/<model>_<timestamp>/
"""

import argparse
import json
import os
import sys
import subprocess
import tempfile
import uuid
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
ORIGINAL_BOOKS = REPO_ROOT / "original_books"
MODIFIED_BOOKS = REPO_ROOT / "modified_books"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

BOOKS = ["Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight", "Goosebumps"]
CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]


def log(msg: str, level: str = "INFO"):
    """Print timestamped log message."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", file=sys.stderr)


def check_server(base_url: str, timeout: int = 10) -> Tuple[bool, str]:
    """Check if LLM server is responding."""
    try:
        url = f"{base_url}/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            if models:
                return True, models[0].get("id", "unknown")
            return True, "unknown"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def load_chapters(book_dir: Path, max_chapters: int = 2) -> List[Dict]:
    """Load chapters from a book directory."""
    chapters = []
    if not book_dir.exists():
        return chapters
    
    files = sorted(book_dir.glob("*.txt"))[:max_chapters]
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            lines = text.strip().split('\n')
            title = lines[0].strip()[:100] if lines else f.stem
            chapters.append({
                "id": f.stem,
                "title": title,
                "text": text,
                "path": str(f)
            })
        except Exception as e:
            log(f"Warning: Could not read {f}: {e}", "WARN")
    
    return chapters


def run_story_lint(
    story_text: str,
    base_url: str,
    timeout: int = 600,
    mode: str = "both"
) -> Dict[str, Any]:
    """Run story_lint.py on story text."""
    start_time = datetime.now()
    
    # Write story to temp file
    fd, story_path = tempfile.mkstemp(suffix='.txt', prefix='story_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(story_text)
        
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "story_lint.py"),
            "--mode", mode,
            "--llm-model", "auto",
            "--llm-base-url", base_url,
            "--llm-no-auth",
            "--struct-model", "auto",
            "--struct-base-url", base_url,
            "--struct-no-auth",
            "--llm-timeout", str(timeout),
            "--struct-timeout", str(timeout),
            "--llm-max-tokens", "4096",
            "--struct-max-tokens", "8192",
            story_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * 3,
            cwd=str(REPO_ROOT)
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr[:2000] if result.stderr else "Unknown error",
                "duration_seconds": duration
            }
        
        try:
            output = json.loads(result.stdout)
            output["success"] = True
            output["duration_seconds"] = duration
            return output
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON parse error: {e}",
                "stdout": result.stdout[:2000],
                "duration_seconds": duration
            }
            
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout", "duration_seconds": timeout * 3}
    except Exception as e:
        return {"success": False, "error": str(e), "duration_seconds": 0}
    finally:
        try:
            os.unlink(story_path)
        except:
            pass


def extract_errors(lint_result: Dict, source: str, story_text: str) -> List[Dict]:
    """Extract errors from lint result."""
    errors = []
    if not lint_result.get("success"):
        return errors
    
    key = f"{source}_lint"
    if key not in lint_result:
        return errors
    
    for err in lint_result[key].get("errors", []):
        category = err.get("category", "coherence").lower()
        if category not in CATEGORIES:
            category = "coherence"
        
        errors.append({
            "source": source,
            "category": category,
            "description": err.get("description", "No description"),
            "violation_type": err.get("violation_type", ""),
            "involved_entities": err.get("involved_entities", []),
            "story_fragments": err.get("story_fragments", [])
        })
    
    return errors


def categorize_errors(errors: List[Dict]) -> Dict[str, int]:
    """Count errors by category."""
    counts = {cat: 0 for cat in CATEGORIES}
    for err in errors:
        cat = err.get("category", "coherence")
        if cat in counts:
            counts[cat] += 1
    return counts


def generate_report(results: Dict, output_dir: Path) -> str:
    """Generate markdown report."""
    r = []
    r.append("# Narrative Evaluation Experiment Report\n")
    r.append(f"**Generated:** {datetime.now().isoformat()}\n")
    r.append(f"**Model:** {results.get('model_name', 'Unknown')}\n")
    r.append(f"**Duration:** {results.get('total_duration_seconds', 0):.2f} seconds\n")
    
    r.append("\n## Summary\n")
    r.append(f"- Books processed: {len(results.get('books', []))}\n")
    r.append(f"- Total LLM errors: {results.get('total_llm_errors', 0)}\n")
    r.append(f"- Total Logic errors: {results.get('total_logic_errors', 0)}\n")
    
    r.append("\n## Errors by Category\n")
    r.append("| Category | LLM | Logic |\n")
    r.append("|----------|-----|-------|\n")
    
    llm_cats = {cat: 0 for cat in CATEGORIES}
    logic_cats = {cat: 0 for cat in CATEGORIES}
    
    for book in results.get("books", []):
        for chapter in book.get("chapters", []):
            for cat in CATEGORIES:
                llm_cats[cat] += chapter.get("llm_by_category", {}).get(cat, 0)
                logic_cats[cat] += chapter.get("logic_by_category", {}).get(cat, 0)
    
    for cat in CATEGORIES:
        r.append(f"| {cat.capitalize()} | {llm_cats[cat]} | {logic_cats[cat]} |\n")
    
    r.append("\n## Results by Book\n")
    for book in results.get("books", []):
        r.append(f"\n### {book['name']}\n")
        r.append(f"- Duration: {book.get('duration_seconds', 0):.1f}s\n")
        
        for chapter in book.get("chapters", []):
            r.append(f"\n#### {chapter['id']}\n")
            r.append(f"- LLM errors: {chapter.get('llm_error_count', 0)}\n")
            r.append(f"- Logic errors: {chapter.get('logic_error_count', 0)}\n")
    
    r.append("\n## Sample Errors\n")
    sample_count = 0
    for book in results.get("books", []):
        for chapter in book.get("chapters", []):
            for err in chapter.get("llm_errors", [])[:2]:
                if sample_count >= 10:
                    break
                r.append(f"\n**{book['name']} / {chapter['id']} (LLM - {err.get('category', 'unknown')})**\n")
                r.append(f"> {err.get('description', '')[:300]}\n")
                sample_count += 1
            
            for err in chapter.get("logic_errors", [])[:2]:
                if sample_count >= 10:
                    break
                r.append(f"\n**{book['name']} / {chapter['id']} (Logic - {err.get('category', 'unknown')})**\n")
                r.append(f"> {err.get('description', '')[:300]}\n")
                sample_count += 1
    
    return "".join(r)


def main():
    parser = argparse.ArgumentParser(
        description="Run narrative evaluation experiment (server must be running)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    # Start llamafile first, then:
    python3 scripts/run_with_server.py --model-name "gemma"
        """
    )
    
    parser.add_argument("--model-name", required=True, help="Model name for output directory")
    parser.add_argument("--base-url", default="http://localhost:8080/v1", help="LLM server URL")
    parser.add_argument("--chapters-per-book", type=int, default=2, help="Chapters per book")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout per call (seconds)")
    parser.add_argument("--books", default=None, help="Comma-separated book names")
    
    args = parser.parse_args()
    books = [b.strip() for b in args.books.split(",")] if args.books else BOOKS
    
    # Create experiment directory
    exp_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    exp_name = f"{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
    exp_dir = EXPERIMENTS_DIR / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)
    stories_dir = exp_dir / "stories"
    stories_dir.mkdir()
    
    log(f"Experiment: {exp_name}")
    log(f"Output: {exp_dir}")
    
    # Check server
    log("Checking server...")
    ok, info = check_server(args.base_url)
    if not ok:
        log(f"ERROR: Server not available at {args.base_url}", "ERROR")
        log(f"Please start the llamafile server first.", "ERROR")
        sys.exit(1)
    log(f"Server OK: {info}")
    
    # Initialize results
    results = {
        "model_name": args.model_name,
        "server_model": info,
        "start_time": start_time.isoformat(),
        "config": {
            "base_url": args.base_url,
            "chapters_per_book": args.chapters_per_book,
            "timeout": args.timeout,
            "books": books
        },
        "books": []
    }
    
    # Save config
    (exp_dir / "config.json").write_text(json.dumps(results["config"], indent=2))
    
    total_llm = 0
    total_logic = 0
    
    # Process each book
    for book_name in books:
        log(f"Processing: {book_name}")
        book_start = datetime.now()
        
        book_dir = MODIFIED_BOOKS / book_name
        chapters = load_chapters(book_dir, args.chapters_per_book)
        
        if not chapters:
            log(f"  No chapters found in {book_dir}", "WARN")
            continue
        
        book_result = {"name": book_name, "chapters": []}
        
        # Save story texts
        (stories_dir / book_name).mkdir(exist_ok=True)
        
        for chapter in chapters:
            log(f"  Chapter: {chapter['id']}")
            ch_start = datetime.now()
            
            # Save text
            (stories_dir / book_name / f"{chapter['id']}.txt").write_text(chapter["text"])
            
            # Run lint
            lint_result = run_story_lint(chapter["text"], args.base_url, args.timeout)
            
            # Extract errors
            llm_errors = extract_errors(lint_result, "llm", chapter["text"])
            logic_errors = extract_errors(lint_result, "logic", chapter["text"])
            
            ch_end = datetime.now()
            
            chapter_result = {
                "id": chapter["id"],
                "title": chapter["title"],
                "duration_seconds": (ch_end - ch_start).total_seconds(),
                "success": lint_result.get("success", False),
                "llm_error_count": len(llm_errors),
                "logic_error_count": len(logic_errors),
                "llm_by_category": categorize_errors(llm_errors),
                "logic_by_category": categorize_errors(logic_errors),
                "llm_errors": llm_errors[:20],
                "logic_errors": logic_errors[:20],
                "error": lint_result.get("error") if not lint_result.get("success") else None
            }
            
            book_result["chapters"].append(chapter_result)
            total_llm += len(llm_errors)
            total_logic += len(logic_errors)
            
            log(f"    LLM: {len(llm_errors)}, Logic: {len(logic_errors)} ({chapter_result['duration_seconds']:.1f}s)")
        
        book_end = datetime.now()
        book_result["duration_seconds"] = (book_end - book_start).total_seconds()
        results["books"].append(book_result)
    
    # Finalize
    end_time = datetime.now()
    results["end_time"] = end_time.isoformat()
    results["total_duration_seconds"] = (end_time - start_time).total_seconds()
    results["total_llm_errors"] = total_llm
    results["total_logic_errors"] = total_logic
    
    # Save results
    (exp_dir / "results.json").write_text(json.dumps(results, indent=2, default=str))
    
    # Generate report
    report = generate_report(results, exp_dir)
    (exp_dir / "report.md").write_text(report)
    
    # Rename with end time
    final_name = f"{args.model_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%Y%m%d_%H%M%S')}_{exp_id}"
    final_dir = EXPERIMENTS_DIR / final_name
    try:
        exp_dir.rename(final_dir)
        output_dir = final_dir
    except:
        output_dir = exp_dir
    
    log("=" * 60)
    log("EXPERIMENT COMPLETE")
    log(f"LLM errors: {total_llm}, Logic errors: {total_logic}")
    log(f"Duration: {results['total_duration_seconds']:.2f}s")
    log(f"Output: {output_dir}")
    log("=" * 60)
    
    print(f"\nResults saved to: {output_dir}")
    print(f"  - results.json")
    print(f"  - report.md")


if __name__ == "__main__":
    main()
