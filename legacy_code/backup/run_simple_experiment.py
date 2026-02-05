#!/usr/bin/env python3
"""
run_simple_experiment.py - Minimal Experiment Runner
=====================================================

Simplest possible experiment runner for testing narrative evaluation.

Usage:
    # Ensure LLM server is running on localhost:8080, then:
    python3 scripts/run_simple_experiment.py

This processes 2 chapters per book across all 5 books using both
LLM and logic-based linting, then generates a report.
"""

import json
import os
import sys
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
BOOKS = ["Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight", "Goosebumps"]
CHAPTERS_PER_BOOK = 2
BASE_URL = "http://localhost:8080/v1"
TIMEOUT = 600


def log(msg):
    """Print timestamped log message."""
    print(f"[{datetime.now().isoformat()}] {msg}", file=sys.stderr)


def check_server():
    """Check if server is running."""
    import urllib.request
    import urllib.error
    try:
        url = f"{BASE_URL}/models"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            models = data.get("data", [])
            if models:
                return True, models[0].get("id", "unknown")
            return True, "unknown"
    except Exception as e:
        return False, str(e)


def load_chapters(book_dir, max_chapters=2):
    """Load chapters from directory."""
    chapters = []
    if not book_dir.exists():
        return chapters
    
    files = sorted(book_dir.glob("*.txt"))[:max_chapters]
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        lines = text.strip().split('\n')
        title = lines[0].strip()[:80] if lines else f.stem
        chapters.append({"id": f.stem, "title": title, "text": text})
    return chapters


def run_lint(story_text, mode="both"):
    """Run story_lint.py on story text."""
    fd, path = tempfile.mkstemp(suffix='.txt')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(story_text)
        
        cmd = [
            sys.executable, str(SCRIPT_DIR / "story_lint.py"),
            "--mode", mode,
            "--llm-model", "auto",
            "--llm-base-url", BASE_URL,
            "--llm-no-auth",
            "--struct-model", "auto",
            "--struct-base-url", BASE_URL,
            "--struct-no-auth",
            "--llm-timeout", str(TIMEOUT),
            "--struct-timeout", str(TIMEOUT),
            "--llm-max-tokens", "4096",
            "--struct-max-tokens", "8192",
            path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT*3, cwd=str(REPO_ROOT))
        
        if result.returncode != 0:
            return {"success": False, "error": result.stderr[:1000]}
        
        try:
            output = json.loads(result.stdout)
            output["success"] = True
            return output
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON error: {e}", "stdout": result.stdout[:500]}
    
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try: os.unlink(path)
        except: pass


def main():
    start_time = datetime.now()
    log("Starting simple experiment")
    
    # Check server
    ok, info = check_server()
    if not ok:
        log(f"ERROR: Server not available at {BASE_URL}")
        log(f"Details: {info}")
        log("Please start the LLM server first.")
        sys.exit(1)
    log(f"Server OK: {info}")
    
    # Create output directory
    exp_dir = REPO_ROOT / "experiments" / f"simple_{start_time.strftime('%Y%m%d_%H%M%S')}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    stories_dir = exp_dir / "stories"
    stories_dir.mkdir()
    
    results = {
        "start_time": start_time.isoformat(),
        "model": info,
        "books": []
    }
    
    # Process books
    for book_name in BOOKS:
        log(f"Processing book: {book_name}")
        book_start = datetime.now()
        
        book_dir = REPO_ROOT / "modified_books" / book_name
        chapters = load_chapters(book_dir, CHAPTERS_PER_BOOK)
        
        if not chapters:
            log(f"  No chapters found in {book_dir}")
            continue
        
        book_results = {"name": book_name, "chapters": []}
        
        # Save chapter texts
        (stories_dir / book_name).mkdir(exist_ok=True)
        
        for chapter in chapters:
            log(f"  Chapter: {chapter['id']}")
            ch_start = datetime.now()
            
            # Save chapter text
            (stories_dir / book_name / f"{chapter['id']}.txt").write_text(chapter["text"])
            
            # Run linting
            result = run_lint(chapter["text"])
            
            ch_end = datetime.now()
            
            # Extract error counts
            llm_errors = []
            logic_errors = []
            
            if result.get("success"):
                if "llm_lint" in result:
                    llm_errors = result["llm_lint"].get("errors", [])
                if "logic_lint" in result:
                    logic_errors = result["logic_lint"].get("errors", [])
            
            chapter_result = {
                "id": chapter["id"],
                "title": chapter["title"],
                "duration_seconds": (ch_end - ch_start).total_seconds(),
                "success": result.get("success", False),
                "llm_error_count": len(llm_errors),
                "logic_error_count": len(logic_errors),
                "llm_errors": llm_errors[:10],
                "logic_errors": logic_errors[:10],
                "error": result.get("error") if not result.get("success") else None
            }
            
            book_results["chapters"].append(chapter_result)
            log(f"    LLM: {len(llm_errors)} errors, Logic: {len(logic_errors)} errors ({(ch_end-ch_start).total_seconds():.1f}s)")
        
        book_end = datetime.now()
        book_results["duration_seconds"] = (book_end - book_start).total_seconds()
        results["books"].append(book_results)
    
    # Finalize
    end_time = datetime.now()
    results["end_time"] = end_time.isoformat()
    results["total_duration_seconds"] = (end_time - start_time).total_seconds()
    
    # Calculate totals
    total_llm = sum(c["llm_error_count"] for b in results["books"] for c in b["chapters"])
    total_logic = sum(c["logic_error_count"] for b in results["books"] for c in b["chapters"])
    results["total_llm_errors"] = total_llm
    results["total_logic_errors"] = total_logic
    
    # Save results
    (exp_dir / "results.json").write_text(json.dumps(results, indent=2, default=str))
    
    # Generate simple report
    report = f"""# Simple Experiment Report

**Start:** {start_time.isoformat()}
**End:** {end_time.isoformat()}
**Duration:** {(end_time - start_time).total_seconds():.2f} seconds
**Model:** {info}

## Summary

| Metric | Value |
|--------|-------|
| Books processed | {len(results['books'])} |
| Total LLM errors | {total_llm} |
| Total Logic errors | {total_logic} |

## Results by Book

"""
    for book in results["books"]:
        book_llm = sum(c["llm_error_count"] for c in book["chapters"])
        book_logic = sum(c["logic_error_count"] for c in book["chapters"])
        report += f"### {book['name']}\n"
        report += f"- Duration: {book['duration_seconds']:.1f}s\n"
        report += f"- LLM errors: {book_llm}\n"
        report += f"- Logic errors: {book_logic}\n\n"
    
    report += "\n## Sample Errors\n\n"
    
    sample_count = 0
    for book in results["books"]:
        for chapter in book["chapters"]:
            for err in chapter.get("llm_errors", [])[:2]:
                if sample_count >= 10:
                    break
                report += f"**{book['name']} / {chapter['id']} (LLM)**\n"
                report += f"- Category: {err.get('category', 'unknown')}\n"
                report += f"- Description: {err.get('description', 'No description')[:200]}\n\n"
                sample_count += 1
            
            for err in chapter.get("logic_errors", [])[:2]:
                if sample_count >= 10:
                    break
                report += f"**{book['name']} / {chapter['id']} (Logic)**\n"
                report += f"- Category: {err.get('category', 'unknown')}\n"
                report += f"- Description: {err.get('description', 'No description')[:200]}\n\n"
                sample_count += 1
    
    (exp_dir / "report.md").write_text(report)
    
    # Rename with end time
    final_name = f"simple_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%Y%m%d_%H%M%S')}"
    final_dir = REPO_ROOT / "experiments" / final_name
    try:
        exp_dir.rename(final_dir)
        log(f"Results saved to: {final_dir}")
    except:
        log(f"Results saved to: {exp_dir}")
    
    log("="*50)
    log("EXPERIMENT COMPLETE")
    log(f"Total LLM errors: {total_llm}")
    log(f"Total Logic errors: {total_logic}")
    log(f"Duration: {(end_time - start_time).total_seconds():.2f} seconds")
    log("="*50)


if __name__ == "__main__":
    main()
