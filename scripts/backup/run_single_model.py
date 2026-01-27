#!/usr/bin/env python3
"""
run_single_model.py - Run experiment with externally managed LLM
================================================================

This script runs the narrative evaluation experiment assuming the LLM
server is already running externally (e.g., via gemma.sh).

Usage:
    # Start your model externally first:
    bash /home/cleon/programas/gemma.sh
    
    # Then run this script:
    python3 scripts/run_single_model.py --model-name "Gemma 3 12B"
"""

import os
import sys
import json
import subprocess
import time
import shutil
from datetime import datetime
from pathlib import Path

# Configuration
BASE_DIR = Path("/home/cleon/ucm/investigacion/articulos/2025/evaluador_narrativa/codigo")
ORIGINAL = BASE_DIR / "original_books"
MODIFIED = BASE_DIR / "modified_books"
LLM_URL = "http://127.0.0.1:8080/v1"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run narrative evaluation with external LLM")
    parser.add_argument("--model-name", default="Gemma 3 12B", help="Name of the model for reporting")
    parser.add_argument("--model-id", default="gemma", help="Model ID for API calls")
    parser.add_argument("--chapters-per-book", type=int, default=1, help="Chapters to process per book")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per chapter (seconds)")
    args = parser.parse_args()

    start_time = datetime.now()
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    
    print("=" * 80)
    print("NARRATIVE EVALUATION EXPERIMENT")
    print("=" * 80)
    print(f"Start: {start_time.isoformat()}")
    print(f"Model: {args.model_name}")
    print(f"LLM URL: {LLM_URL}")
    print()

    # Create output directory
    OUTPUT = BASE_DIR / "experiments" / f"narrative_eval-{timestamp}"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT}")
    print()

    # Select chapters from each book
    books = ["Goosebumps", "Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight"]
    chapters = []

    print("Selecting chapters...")
    for book in books:
        orig_dir = ORIGINAL / book
        mod_dir = MODIFIED / book
        
        if orig_dir.exists() and mod_dir.exists():
            orig_files = sorted(orig_dir.glob("*.txt"))[:args.chapters_per_book]
            mod_files = sorted(mod_dir.glob("*.txt"))[:args.chapters_per_book]
            
            for orig, mod in zip(orig_files, mod_files):
                chapters.append({
                    "book": book,
                    "chapter": orig.name,
                    "original": orig,
                    "modified": mod
                })
                print(f"  ✓ {book}/{orig.name}")

    print(f"\nTotal chapters: {len(chapters)}")
    print()

    # Copy chapters to output for reference
    print("Copying chapter files...")
    for ch in chapters:
        book_dir = OUTPUT / ch["book"]
        book_dir.mkdir(exist_ok=True)
        shutil.copy(ch["original"], book_dir / f"original_{ch['chapter']}")
        shutil.copy(ch["modified"], book_dir / f"modified_{ch['chapter']}")
    print("Done.\n")

    # Initialize results
    results = {
        "metadata": {
            "experiment_name": "narrative_evaluation",
            "start_time": start_time.isoformat(),
            "model_name": args.model_name,
            "model_id": args.model_id,
            "llm_url": LLM_URL,
            "chapters_per_book": args.chapters_per_book,
            "total_chapters": len(chapters),
            "books": books
        },
        "chapters": [],
        "summary": {
            "total_llm_errors": 0,
            "total_logic_errors": 0,
            "by_category": {
                "causality": {"llm": 0, "logic": 0},
                "coherence": {"llm": 0, "logic": 0},
                "temporal": {"llm": 0, "logic": 0},
                "location": {"llm": 0, "logic": 0},
                "emotional": {"llm": 0, "logic": 0},
                "other": {"llm": 0, "logic": 0}
            }
        }
    }

    # Process each chapter
    print("=" * 80)
    print(f"PROCESSING WITH: {args.model_name}")
    print("=" * 80)

    for idx, ch in enumerate(chapters, 1):
        print(f"\n[{idx}/{len(chapters)}] {ch['book']} / {ch['chapter']}")
        print("-" * 60)
        
        chapter_start = datetime.now()
        chapter_result = {
            "book": ch["book"],
            "chapter": ch["chapter"],
            "original_file": str(ch["original"]),
            "modified_file": str(ch["modified"]),
            "start_time": chapter_start.isoformat(),
            "llm_errors": [],
            "logic_errors": [],
            "error": None
        }

        # Build story_lint command
        lint_cmd = [
            sys.executable,
            str(BASE_DIR / "scripts" / "story_lint.py"),
            str(ch["modified"]),
            "--mode", "both",
            "--llm-backend", "openai",
            "--llm-base-url", LLM_URL,
            "--struct-base-url", LLM_URL,
            "--llm-model", args.model_id,
            "--struct-model", args.model_id,
            "--llm-no-auth",
            "--struct-no-auth"
        ]

        print(f"  Running story_lint...")
        print(f"  Command: {' '.join(lint_cmd[:6])}...")
        
        try:
            proc_start = time.time()
            result = subprocess.run(
                lint_cmd,
                capture_output=True,
                text=True,
                timeout=args.timeout,
                cwd=str(BASE_DIR / "scripts")
            )
            elapsed = time.time() - proc_start
            
            print(f"  Completed in {elapsed:.1f}s (return code: {result.returncode})")
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    output = json.loads(result.stdout)
                    
                    # Extract errors
                    llm_errors = output.get("llm_errors", [])
                    logic_errors = output.get("logic_errors", [])
                    
                    chapter_result["llm_errors"] = llm_errors
                    chapter_result["logic_errors"] = logic_errors
                    chapter_result["raw_output"] = output
                    chapter_result["success"] = True
                    
                    # Count by category
                    for err in llm_errors:
                        cat = err.get("category", "other").lower()
                        if cat not in results["summary"]["by_category"]:
                            cat = "other"
                        results["summary"]["by_category"][cat]["llm"] += 1
                        results["summary"]["total_llm_errors"] += 1
                    
                    for err in logic_errors:
                        cat = err.get("category", "other").lower()
                        if cat not in results["summary"]["by_category"]:
                            cat = "other"
                        results["summary"]["by_category"][cat]["logic"] += 1
                        results["summary"]["total_logic_errors"] += 1
                    
                    print(f"  ✓ LLM errors: {len(llm_errors)}, Logic errors: {len(logic_errors)}")
                    
                except json.JSONDecodeError as e:
                    print(f"  ✗ JSON parse error: {e}")
                    chapter_result["error"] = f"JSON parse error: {e}"
                    chapter_result["stdout"] = result.stdout[:2000]
                    chapter_result["success"] = False
            else:
                print(f"  ✗ Non-zero return or empty output")
                chapter_result["error"] = f"Return code {result.returncode}"
                chapter_result["stderr"] = result.stderr[:2000] if result.stderr else ""
                chapter_result["stdout"] = result.stdout[:2000] if result.stdout else ""
                chapter_result["success"] = False
                
            chapter_result["elapsed_seconds"] = elapsed
            
        except subprocess.TimeoutExpired:
            print(f"  ✗ TIMEOUT after {args.timeout}s")
            chapter_result["error"] = f"Timeout after {args.timeout}s"
            chapter_result["success"] = False
        except Exception as e:
            print(f"  ✗ Exception: {e}")
            chapter_result["error"] = str(e)
            chapter_result["success"] = False

        chapter_result["end_time"] = datetime.now().isoformat()
        results["chapters"].append(chapter_result)
        
        # Save intermediate results
        with open(OUTPUT / "results.json", 'w') as f:
            json.dump(results, f, indent=2)

    # Finalize
    end_time = datetime.now()
    results["metadata"]["end_time"] = end_time.isoformat()
    results["metadata"]["total_duration_seconds"] = (end_time - start_time).total_seconds()

    # Save final results
    with open(OUTPUT / "results.json", 'w') as f:
        json.dump(results, f, indent=2)

    # Generate report
    print("\n" + "=" * 80)
    print("GENERATING REPORT")
    print("=" * 80)

    report = generate_report(results, OUTPUT)
    
    with open(OUTPUT / "report.md", 'w') as f:
        f.write(report)
    
    print(f"\n✓ Report saved: {OUTPUT / 'report.md'}")
    print(f"✓ Results saved: {OUTPUT / 'results.json'}")

    # Final summary
    print("\n" + "=" * 80)
    print("EXPERIMENT COMPLETE")
    print("=" * 80)
    print(f"Duration: {(end_time - start_time).total_seconds():.1f} seconds")
    print(f"Chapters processed: {len(results['chapters'])}")
    print(f"Total LLM errors: {results['summary']['total_llm_errors']}")
    print(f"Total Logic errors: {results['summary']['total_logic_errors']}")
    print(f"\nOutput: {OUTPUT}")
    print("=" * 80)

    # Rename folder with end timestamp
    final_name = f"narrative_eval-{timestamp}-{end_time.strftime('%H%M%S')}"
    final_path = OUTPUT.parent / final_name
    try:
        OUTPUT.rename(final_path)
        print(f"Renamed to: {final_path}")
    except:
        pass


def generate_report(results: dict, output_dir: Path) -> str:
    """Generate markdown report from results."""
    
    meta = results["metadata"]
    summary = results["summary"]
    
    report = f"""# Narrative Evaluation Experiment Report

## Experiment Metadata

| Property | Value |
|----------|-------|
| **Model** | {meta['model_name']} |
| **Start Time** | {meta['start_time']} |
| **End Time** | {meta.get('end_time', 'N/A')} |
| **Duration** | {meta.get('total_duration_seconds', 0):.1f} seconds |
| **Chapters Processed** | {meta['total_chapters']} |
| **Books** | {', '.join(meta['books'])} |

## Summary Statistics

### Total Errors Detected

| Approach | Count |
|----------|-------|
| LLM-based | {summary['total_llm_errors']} |
| Logic-based (Clingo) | {summary['total_logic_errors']} |
| **Total** | {summary['total_llm_errors'] + summary['total_logic_errors']} |

### Errors by Category

| Category | LLM | Logic | Total |
|----------|-----|-------|-------|
| Causality | {summary['by_category']['causality']['llm']} | {summary['by_category']['causality']['logic']} | {summary['by_category']['causality']['llm'] + summary['by_category']['causality']['logic']} |
| Coherence | {summary['by_category']['coherence']['llm']} | {summary['by_category']['coherence']['logic']} | {summary['by_category']['coherence']['llm'] + summary['by_category']['coherence']['logic']} |
| Temporal | {summary['by_category']['temporal']['llm']} | {summary['by_category']['temporal']['logic']} | {summary['by_category']['temporal']['llm'] + summary['by_category']['temporal']['logic']} |
| Location | {summary['by_category']['location']['llm']} | {summary['by_category']['location']['logic']} | {summary['by_category']['location']['llm'] + summary['by_category']['location']['logic']} |
| Emotional | {summary['by_category']['emotional']['llm']} | {summary['by_category']['emotional']['logic']} | {summary['by_category']['emotional']['llm'] + summary['by_category']['emotional']['logic']} |
| Other | {summary['by_category']['other']['llm']} | {summary['by_category']['other']['logic']} | {summary['by_category']['other']['llm'] + summary['by_category']['other']['logic']} |

## Per-Chapter Results

| Book | Chapter | LLM Errors | Logic Errors | Time (s) | Status |
|------|---------|------------|--------------|----------|--------|
"""

    for ch in results["chapters"]:
        status = "✓" if ch.get("success") else "✗"
        llm_count = len(ch.get("llm_errors", []))
        logic_count = len(ch.get("logic_errors", []))
        elapsed = ch.get("elapsed_seconds", 0)
        report += f"| {ch['book']} | {ch['chapter']} | {llm_count} | {logic_count} | {elapsed:.1f} | {status} |\n"

    report += """

## Detailed Error Analysis

"""

    # Add detailed errors for each chapter
    for ch in results["chapters"]:
        if not ch.get("success"):
            continue
            
        llm_errors = ch.get("llm_errors", [])
        logic_errors = ch.get("logic_errors", [])
        
        if llm_errors or logic_errors:
            report += f"### {ch['book']} - {ch['chapter']}\n\n"
            
            if llm_errors:
                report += "#### LLM-Detected Errors\n\n"
                for i, err in enumerate(llm_errors, 1):
                    cat = err.get("category", "unknown")
                    desc = err.get("description", "No description")
                    fragments = err.get("story_fragments", [])
                    
                    report += f"**Error {i}** [{cat.upper()}]\n\n"
                    report += f"> {desc}\n\n"
                    if fragments:
                        report += "Story fragments:\n"
                        for frag in fragments:
                            report += f"- \"{frag[:200]}{'...' if len(frag) > 200 else ''}\"\n"
                    report += "\n"
            
            if logic_errors:
                report += "#### Logic-Detected Errors (Clingo)\n\n"
                for i, err in enumerate(logic_errors, 1):
                    cat = err.get("category", "unknown")
                    desc = err.get("description", str(err))
                    
                    report += f"**Error {i}** [{cat.upper()}]\n\n"
                    report += f"> {desc}\n\n"

    report += """
## Methodology

This experiment compares two approaches to narrative consistency checking:

1. **LLM-based Linting**: Direct analysis by a Large Language Model, looking for semantic inconsistencies, logical errors, and narrative problems.

2. **Logic-based Linting (ASP/Clingo)**: Translation of story structure to Answer Set Programming facts, followed by formal reasoning using Clingo solver.

### Error Categories

1. **Causality**: Chekhov's gun violations, unexplained effects, missing causes
2. **Coherence**: Semantic errors, physical impossibilities, logical contradictions
3. **Temporal**: Time paradoxes, ordering violations, duration errors
4. **Location**: Spatial impossibilities, ubiquity, travel constraints
5. **Emotional**: Character behavior vs. relationships/emotional states

## Conclusion

The hybrid approach combining neural (LLM) and symbolic (ASP) methods provides complementary coverage for narrative consistency checking. LLM excels at contextual understanding while logic-based approaches provide formal guarantees.

---

*Report generated: {datetime.now().isoformat()}*
"""

    return report


if __name__ == "__main__":
    main()
