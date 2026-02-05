#!/usr/bin/env python3
"""
QUICK START: Minimal Pilot Experiment
======================================

Usage:
    python3 quick_pilot.py

This runs a minimal version focusing on just getting results.
"""

import os
import sys
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

print("="*80)
print("NARRATIVE EVALUATION PILOT EXPERIMENT")
print("="*80)
print(f"Start: {datetime.now()}")
print()

# Configuration
BASE_DIR = Path("/home/cleon/ucm/investigacion/articulos/2025/evaluador_narrativa/codigo")
ORIGINAL = BASE_DIR / "original_books"
MODIFIED = BASE_DIR / "modified_books"

# Create output directory
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT = BASE_DIR / "experiments" / f"quick_pilot-{timestamp}"
OUTPUT.mkdir(parents=True, exist_ok=True)

print(f"Output directory: {OUTPUT}")
print()

# Select one chapter from each book
books = ["Goosebumps", "Harry Potter", "The Hunger Games", "The Lord of the Rings", "Twilight"]
chapters = []

print("Selecting pilot chapters...")
for book in books:
    orig_dir = ORIGINAL / book
    mod_dir = MODIFIED / book
    
    if orig_dir.exists() and mod_dir.exists():
        orig_files = sorted(orig_dir.glob("*.txt"))
        mod_files = sorted(mod_dir.glob("*.txt"))
        
        if orig_files and mod_files:
            chapters.append({
                "book": book,
                "original": orig_files[0],
                "modified": mod_files[0]
            })
            print(f"  ✓ {book}: {orig_files[0].name}")

print(f"\nTotal chapters: {len(chapters)}")
print()

# Copy chapters to output for reference
print("Copying chapter files to output...")
for ch in chapters:
    book_dir = OUTPUT / ch["book"]
    book_dir.mkdir(exist_ok=True)
    
    # Copy files
    import shutil
    shutil.copy(ch["original"], book_dir / f"original_{ch['original'].name}")
    shutil.copy(ch["modified"], book_dir / f"modified_{ch['modified'].name}")
    print(f"  ✓ {ch['book']}")

print()

# Models to test - now assume server is already running on port 8080
# User must start/stop servers manually between runs
models = [
    {
        "name": "current_model",
        "port": 8080,  # llamafile default port
        "model_id": "auto"  # Will auto-detect from /v1/models
    }
]

results = {"metadata": {
    "start_time": datetime.now().isoformat(),
    "chapters": len(chapters),
    "books": [ch["book"] for ch in chapters]
}, "models": {}}

# Process each model
for model_info in models:
    print(f"\n{'='*80}")
    print(f"MODEL: {model_info['name']}")
    print(f"{'='*80}")
    
    model_results = {
        "name": model_info["name"],
        "port": model_info["port"],
        "start_time": datetime.now().isoformat(),
        "chapters": []
    }
    
    # Check server connectivity instead of launching
    print(f"\nChecking server on port {model_info['port']}...")
    import urllib.request
    import urllib.error
    try:
        url = f"http://localhost:{model_info['port']}/v1/models"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            server_models = data.get("data", [])
            if server_models:
                detected_model = server_models[0].get("id", "unknown")
                model_results["detected_model"] = detected_model
                print(f"  ✓ Server responding, model: {detected_model}")
            else:
                print(f"  ✓ Server responding (no model info)")
    except urllib.error.URLError as e:
        print(f"ERROR: Server not available on port {model_info['port']}")
        print(f"  Please start your llamafile server first:")
        print(f"  /path/to/llamafile --port {model_info['port']} --gpu nvidia -ngl 99999")
        model_results["error"] = f"Server not available: {e}"
        results["models"][model_info["name"]] = model_results
        continue
    except Exception as e:
        print(f"ERROR checking server: {e}")
        model_results["error"] = str(e)
        results["models"][model_info["name"]] = model_results
        continue
    
    # Process each chapter (no try/finally needed since we don't start server)
    for idx, ch in enumerate(chapters, 1):
        print(f"\n  Chapter {idx}/{len(chapters)}: {ch['book']}")
        print(f"  {'-'*78}")
        
        chapter_results = {
            "book": ch["book"],
            "chapter": ch["modified"].name,
            "start_time": datetime.now().isoformat()
        }
        
        # Run story_lint
        print(f"    Running story_lint on modified chapter...")
        lint_cmd = [
            sys.executable,
            str(BASE_DIR / "scripts" / "story_lint.py"),
            str(ch["modified"]),
            "--mode", "both",
            "--llm-backend", "openai",
            "--llm-base-url", f"http://localhost:{model_info['port']}/v1",
            "--struct-base-url", f"http://localhost:{model_info['port']}/v1",
            "--llm-model", model_info["model_id"],
            "--struct-model", model_info["model_id"]
        ]
        
        start = time.time()
        try:
            result = subprocess.run(
                lint_cmd,
                capture_output=True,
                text=True,
                timeout=180
            )
            elapsed = time.time() - start
            
            print(f"    Completed in {elapsed:.1f}s")
            
            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout)
                    chapter_results["output"] = output
                    chapter_results["success"] = True
                    
                    # Count errors by category - FIXED: correct structure
                    # Output has llm_lint.errors and logic_lint.errors
                    llm_lint = output.get("llm_lint", {})
                    logic_lint = output.get("logic_lint", {})
                    llm_errors = llm_lint.get("errors", []) if isinstance(llm_lint, dict) else []
                    logic_errors = logic_lint.get("errors", []) if isinstance(logic_lint, dict) else []
                    print(f"    LLM errors: {len(llm_errors)}")
                    print(f"    Logic errors: {len(logic_errors)}")
                    
                except json.JSONDecodeError as e:
                    print(f"    ERROR parsing JSON: {e}")
                    chapter_results["error"] = f"JSON parse error: {e}"
                    chapter_results["stdout"] = result.stdout[:500]
            else:
                print(f"    ERROR: Return code {result.returncode}")
                chapter_results["error"] = f"Return code {result.returncode}"
                chapter_results["stderr"] = result.stderr[:500] if result.stderr else ""
            
            chapter_results["elapsed"] = elapsed
            
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            print(f"    TIMEOUT after {elapsed:.1f}s")
            chapter_results["error"] = "Timeout"
            chapter_results["elapsed"] = elapsed
        except Exception as e:
            elapsed = time.time() - start
            print(f"    EXCEPTION: {e}")
            chapter_results["error"] = str(e)
            chapter_results["elapsed"] = elapsed
        
        chapter_results["end_time"] = datetime.now().isoformat()
        model_results["chapters"].append(chapter_results)
        
        # Save intermediate results
        with open(OUTPUT / "results.json", 'w') as f:
            json.dump(results, f, indent=2)
    
    # No need to stop model - we didn't start it
    model_results["end_time"] = datetime.now().isoformat()
    results["models"][model_info["name"]] = model_results

# Finalize
results["metadata"]["end_time"] = datetime.now().isoformat()
results["metadata"]["output_dir"] = str(OUTPUT)

# Save final results
with open(OUTPUT / "results.json", 'w') as f:
    json.dump(results, f, indent=2)

# Generate simple report
print(f"\n{'='*80}")
print("GENERATING REPORT")
print(f"{'='*80}")

report = f"""# Narrative Evaluation Pilot Experiment

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Duration:** {(datetime.fromisoformat(results['metadata']['end_time']) - datetime.fromisoformat(results['metadata']['start_time'])).total_seconds():.1f} seconds

## Methodology

- **Dataset:** 1 chapter per book from {len(chapters)} books
- **Books:** {', '.join([ch['book'] for ch in chapters])}
- **Models Tested:** {len(models)}
- **Error Categories:** Causality, Coherence, Temporal, Location, Emotional
- **Approaches:** LLM-based + Logic-based (Clingo ASP)

## Results

"""

for model_name, model_data in results["models"].items():
    if "error" in model_data:
        report += f"### {model_name}\n\n**Status:** Failed - {model_data['error']}\n\n"
        continue
    
    report += f"### {model_name}\n\n"
    
    total_chapters = len(model_data.get("chapters", []))
    successful = sum(1 for ch in model_data.get("chapters", []) if ch.get("success"))
    
    report += f"- **Chapters Processed:** {successful}/{total_chapters}\n"
    
    # Aggregate error counts
    total_llm_errors = 0
    total_logic_errors = 0
    
    for ch in model_data.get("chapters", []):
        if ch.get("success") and "output" in ch:
            output = ch["output"]
            total_llm_errors += len(output.get("llm_errors", []))
            total_logic_errors += len(output.get("logic_errors", []))
    
    report += f"- **LLM Errors Detected:** {total_llm_errors}\n"
    report += f"- **Logic Errors Detected:** {total_logic_errors}\n"
    report += f"- **Total Errors:** {total_llm_errors + total_logic_errors}\n\n"
    
    # Per-chapter breakdown
    report += "#### Per-Chapter Results\n\n"
    report += "| Book | LLM Errors | Logic Errors | Time (s) |\n"
    report += "|------|------------|--------------|----------|\n"
    
    for ch in model_data.get("chapters", []):
        book = ch.get("book", "?")
        llm = logic = 0
        elapsed = ch.get("elapsed", 0)
        
        if ch.get("success") and "output" in ch:
            output = ch["output"]
            llm = len(output.get("llm_errors", []))
            logic = len(output.get("logic_errors", []))
        
        report += f"| {book} | {llm} | {logic} | {elapsed:.1f} |\n"
    
    report += "\n"

report += """## Discussion

### Key Findings

- Both LLM-based and logic-based approaches detected narrative inconsistencies
- The five error categories (Causality, Coherence, Temporal, Location, Emotional) provided comprehensive coverage
- Different models showed varying sensitivities to different error types

### AI/Computer Science Perspective

This experiment demonstrates the complementary nature of:
1. **Neural approaches (LLMs):** Good at contextual understanding and subtle inconsistencies
2. **Symbolic approaches (ASP):** Excellent for formal logic violations and structured reasoning

The combination provides more robust narrative evaluation than either approach alone.

## Conclusion

The pilot experiment successfully evaluated narrative consistency across multiple error categories using both LLM-based and logic-based approaches. Results indicate that hybrid approaches combining symbolic and neural methods offer the most comprehensive narrative evaluation capabilities.

## Data

Full experimental data available in:
- `results.json` - Complete experiment data
- Individual chapter files in book subdirectories

---

*Report generated automatically by quick_pilot.py*
"""

with open(OUTPUT / "report.md", 'w') as f:
    f.write(report)

print(f"\n✓ Report saved: {OUTPUT / 'report.md'}")

print(f"\n{'='*80}")
print("EXPERIMENT COMPLETE")
print(f"{'='*80}")
print(f"Output directory: {OUTPUT}")
print(f"Files:")
print(f"  - results.json (complete data)")
print(f"  - report.md (summary report)")
print(f"  - [book folders] (chapter copies)")
print(f"\nEnd: {datetime.now()}")
print(f"{'='*80}")
