#!/usr/bin/env python3
"""
run_logic_lint_only.py - Run logic linting on existing experiment data
======================================================================

This script re-runs the Clingo logic linting on an existing experiment
that has structured JSON data already. It updates the logic_results/
folder and regenerates the report.
"""

import sys
import site

# Ensure user site-packages are in path for clingo
site.ENABLE_USER_SITE = True
if site.getusersitepackages() not in sys.path:
    sys.path.insert(0, site.getusersitepackages())

import json
import os
import re
import tempfile
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any

# Ensure script directory is in path
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from json_to_asp import json_to_asp

# Error categories matching general.lp
ERROR_CATEGORIES = {
    "causality": "Violations of cause-effect relationships (Chekhov's gun, missing causes, unmotivated actions)",
    "coherence": "Semantic and logical inconsistencies (physical impossibility, dead agents, state contradictions)",
    "temporal": "Time-related violations (impossible ordering, duration errors, overlapping conflicts)",
    "location": "Spatial violations (ubiquity, impossible reach, teleportation without travel)",
    "emotional": "Character motivation and relationship violations (harming loved ones, helping enemies)",
}


def sanitize_symbol(s: str) -> str:
    """Sanitize a string to a valid ASP symbol."""
    if not s:
        return "unknown"
    s = re.sub(r'[^a-zA-Z0-9_]', '_', s.lower())
    if s[0].isdigit():
        s = 'x' + s
    return s[:50]


def run_logic_lint(exp_dir: Path, verbose: bool = True):
    """Re-run logic linting on existing experiment."""
    import clingo  # This should work now with site-packages in path
    
    print(f"Clingo version: {clingo.__version__}")
    print(f"Experiment directory: {exp_dir}")
    
    structured_dir = exp_dir / "structured_json"
    logic_results_dir = exp_dir / "logic_results"
    asp_facts_dir = exp_dir / "asp_facts"
    
    if not structured_dir.exists():
        print(f"ERROR: No structured_json folder found at {structured_dir}")
        sys.exit(1)
    
    # Load domain module and general rules paths
    domain_path = exp_dir / "domain_module.lp"
    general_path = REPO_ROOT / "rules" / "general.lp"
    
    if not general_path.exists():
        general_path = REPO_ROOT / "rules" / "base.lp"
        
    print(f"General rules: {general_path}")
    print(f"Domain module: {domain_path}")
    
    # Process each structured JSON
    json_files = sorted(structured_dir.glob("*.json"))
    print(f"Found {len(json_files)} structured stories to process")
    
    all_results = {}
    total_violations = 0
    
    for json_path in json_files:
        title = json_path.stem
        print(f"\n[{datetime.now().isoformat()}] Processing: {title}")
        
        start_time = time.time()
        
        try:
            # Load structured data
            with open(json_path) as f:
                structured_data = json.load(f)
            
            # Convert to ASP facts
            asp_facts = json_to_asp(structured_data)
            
            # Save ASP facts
            asp_path = asp_facts_dir / f"{title}.lp"
            asp_path.write_text(asp_facts)
            
            # Write facts to temp file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
                f.write(asp_facts)
                facts_temp_path = f.name
            
            # Run Clingo
            violations = []
            try:
                ctl = clingo.Control(["--warn=none"])
                
                if general_path.exists():
                    ctl.load(str(general_path))
                if domain_path.exists():
                    ctl.load(str(domain_path))
                ctl.load(facts_temp_path)
                
                ctl.ground([("base", [])])
                
                with ctl.solve(yield_=True) as handle:
                    for model in handle:
                        for atom in model.symbols(shown=True):
                            if atom.name == "violation":
                                parts = tuple(str(arg) for arg in atom.arguments)
                                violations.append(parts)
                                if verbose:
                                    print(f"  VIOLATION: {parts}")
                                    
            finally:
                os.unlink(facts_temp_path)
            
            # Categorize violations
            result = categorize_violations(violations, structured_data)
            elapsed = time.time() - start_time
            
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat(),
                "asp_facts_lines": len(asp_facts.split("\n")),
            }
            
            # Save result
            result_path = logic_results_dir / f"{title}.json"
            with open(result_path, "w") as f:
                json.dump(result, f, indent=2)
            
            all_results[title] = result
            total_violations += result.get("error_count", 0)
            print(f"  Found {result.get('error_count', 0)} violations in {elapsed:.1f}s")
            
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()
            all_results[title] = {
                "error_count": 0,
                "errors": [],
                "_meta": {"error": str(e)},
            }
    
    print(f"\n{'='*60}")
    print(f"LOGIC LINTING COMPLETE")
    print(f"{'='*60}")
    print(f"Total stories: {len(json_files)}")
    print(f"Total violations: {total_violations}")
    
    # Update summary.json
    update_summary(exp_dir, all_results)
    
    # Regenerate report
    regenerate_report(exp_dir, all_results)
    
    return all_results


def categorize_violations(violations: List[Tuple], structured_data: Dict) -> Dict[str, Any]:
    """Categorize violations by error category."""
    errors = []
    category_counts = {cat: 0 for cat in ERROR_CATEGORIES}
    
    # Build event lookup
    event_lookup = {}
    for ev in structured_data.get("events", []):
        ev_id = sanitize_symbol(ev.get("id", ""))
        event_lookup[ev_id] = ev
    
    for i, v in enumerate(violations):
        if len(v) >= 4:
            category = v[0].lower()
            vtype = v[1]
            e1 = v[2]
            e2 = v[3] if len(v) > 3 else ""
        elif len(v) >= 3:
            category = v[0].lower()
            vtype = v[1]
            e1 = v[2]
            e2 = ""
        else:
            category = "coherence"
            vtype = "unknown"
            e1 = str(v[0]) if v else ""
            e2 = ""
        
        # Normalize category
        if category not in ERROR_CATEGORIES:
            category = "coherence"
        
        category_counts[category] = category_counts.get(category, 0) + 1
        
        # Build description from events
        ev1_data = event_lookup.get(e1, {})
        ev2_data = event_lookup.get(e2, {})
        
        description = f"Violation type: {vtype}"
        if ev1_data:
            description += f"\nEvent 1: {ev1_data.get('description', e1)}"
        if ev2_data:
            description += f"\nEvent 2: {ev2_data.get('description', e2)}"
        
        errors.append({
            "id": f"logic_err_{i+1}",
            "category": category,
            "type": vtype,
            "description": description,
            "events": [e1, e2] if e2 else [e1],
            "story_fragment": ev1_data.get("description", ""),
            "conflicting_fragments": [ev2_data.get("description", "")] if ev2_data else [],
            "severity": "medium",
        })
    
    return {
        "error_count": len(errors),
        "errors": errors,
        "summary": {
            "by_category": category_counts,
        },
    }


def update_summary(exp_dir: Path, logic_results: Dict):
    """Update summary.json with new logic results."""
    summary_path = exp_dir / "summary.json"
    
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
    else:
        summary = {}
    
    # Update logic stats
    total_logic_errors = sum(r.get("error_count", 0) for r in logic_results.values())
    logic_by_category = {cat: 0 for cat in ERROR_CATEGORIES}
    
    for result in logic_results.values():
        for cat, count in result.get("summary", {}).get("by_category", {}).items():
            logic_by_category[cat] = logic_by_category.get(cat, 0) + count
    
    summary["logic_total_errors"] = total_logic_errors
    summary["logic_by_category"] = logic_by_category
    summary["logic_updated_at"] = datetime.now().isoformat()
    
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"Updated summary: {summary_path}")


def regenerate_report(exp_dir: Path, logic_results: Dict):
    """Regenerate the report.md with updated logic results."""
    report_path = exp_dir / "report.md"
    
    # Load existing LLM results
    llm_results = {}
    llm_dir = exp_dir / "llm_results"
    if llm_dir.exists():
        for f in llm_dir.glob("*.json"):
            with open(f) as fp:
                llm_results[f.stem] = json.load(fp)
    
    # Load config
    config_path = exp_dir / "config.json"
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    
    # Calculate totals
    llm_total = sum(r.get("error_count", 0) for r in llm_results.values())
    logic_total = sum(r.get("error_count", 0) for r in logic_results.values())
    
    llm_by_cat = {cat: 0 for cat in ERROR_CATEGORIES}
    logic_by_cat = {cat: 0 for cat in ERROR_CATEGORIES}
    
    for r in llm_results.values():
        for err in r.get("errors", []):
            cat = err.get("category", "coherence").lower()
            if cat in llm_by_cat:
                llm_by_cat[cat] += 1
    
    for r in logic_results.values():
        for cat, cnt in r.get("summary", {}).get("by_category", {}).items():
            if cat in logic_by_cat:
                logic_by_cat[cat] += cnt
    
    # Generate report
    lines = [
        "# Narrative Evaluation Experiment Report",
        "",
        "## Comparing LLM-Based vs Logic-Based Narrative Consistency Analysis",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**LLM Model:** {config.get('llm_model', 'unknown')}",
        f"**Stories Analyzed:** {len(llm_results)}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        "This experiment compares two approaches to detecting narrative inconsistencies:",
        "",
        "1. **LLM-Based Analysis**: Direct semantic analysis using large language models",
        "2. **Logic-Based Analysis**: Formal verification using Answer Set Programming (Clingo)",
        "",
        "### Overall Results",
        "",
        "| Metric | LLM Linter | Logic Linter |",
        "|--------|------------|--------------|",
        f"| **Total Errors Detected** | {llm_total} | {logic_total} |",
        f"| **Average per Story** | {llm_total/max(len(llm_results),1):.2f} | {logic_total/max(len(logic_results),1):.2f} |",
        "",
        "---",
        "",
        "## 2. Errors by Category",
        "",
        "### Category Comparison Table",
        "",
        "| Category | LLM Errors | Logic Errors | Description |",
        "|----------|------------|--------------|-------------|",
    ]
    
    for cat in ERROR_CATEGORIES:
        desc = ERROR_CATEGORIES[cat][:60] + "..."
        lines.append(f"| **{cat.capitalize()}** | {llm_by_cat.get(cat, 0)} | {logic_by_cat.get(cat, 0)} | {desc} |")
    
    lines.extend([
        "",
        "---",
        "",
        "## 3. Detailed Results by Story",
        "",
    ])
    
    # Group by book
    stories_by_book = {}
    for title in sorted(set(llm_results.keys()) | set(logic_results.keys())):
        book = title.rsplit("_Chapter_", 1)[0] if "_Chapter_" in title else title
        if book not in stories_by_book:
            stories_by_book[book] = []
        stories_by_book[book].append(title)
    
    for book in sorted(stories_by_book.keys()):
        lines.append(f"### {book}")
        lines.append("")
        
        for title in sorted(stories_by_book[book]):
            llm_r = llm_results.get(title, {})
            logic_r = logic_results.get(title, {})
            
            lines.append(f"#### {title}")
            lines.append("")
            lines.append(f"- **LLM Errors**: {llm_r.get('error_count', 0)}")
            lines.append(f"- **Logic Errors**: {logic_r.get('error_count', 0)}")
            lines.append("")
            
            # LLM errors
            if llm_r.get("errors"):
                lines.append("**LLM-Detected Errors:**")
                lines.append("")
                for err in llm_r.get("errors", []):
                    cat = err.get("category", "unknown").upper()
                    sev = err.get("severity", "medium").upper()
                    etype = err.get("type", "unknown")
                    desc = err.get("description", "")
                    frag = err.get("story_fragment", "")
                    
                    lines.append(f"- **[{cat}][{sev}]** `{etype}`")
                    lines.append(f"  - {desc}")
                    if frag:
                        lines.append(f"  - Fragment: *\"{frag[:200]}{'...' if len(frag) > 200 else ''}\"*")
                lines.append("")
            
            # Logic errors
            if logic_r.get("errors"):
                lines.append("**Logic-Detected Errors:**")
                lines.append("")
                for err in logic_r.get("errors", []):
                    cat = err.get("category", "unknown").upper()
                    etype = err.get("type", "unknown")
                    desc = err.get("description", "").replace("\n", " ")
                    frag = err.get("story_fragment", "")
                    
                    lines.append(f"- **[{cat}]** `{etype}`")
                    lines.append(f"  - {desc[:300]}")
                    if frag:
                        lines.append(f"  - Fragment: *\"{frag[:200]}{'...' if len(frag) > 200 else ''}\"*")
                lines.append("")
    
    lines.extend([
        "---",
        "",
        "## 4. Analysis Notes",
        "",
        "### Logic Linter Performance",
        "",
        f"The logic-based linter using Clingo ASP detected **{logic_total}** violations.",
        "",
        "The logic linter relies on:",
        "1. Accurate story structuring (events, characters, locations, times)",
        "2. Complete rule coverage in general.lp",
        "3. Proper domain-specific facts in domain_module.lp",
        "",
        "---",
        "",
        f"*Report generated: {datetime.now().isoformat()}*",
    ])
    
    report_content = "\n".join(lines)
    report_path.write_text(report_content)
    print(f"Report updated: {report_path}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run logic linting on existing experiment")
    parser.add_argument("exp_dir", type=Path, help="Path to experiment directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if not args.exp_dir.exists():
        print(f"ERROR: Experiment directory not found: {args.exp_dir}")
        sys.exit(1)
    
    run_logic_lint(args.exp_dir, verbose=args.verbose)


if __name__ == "__main__":
    main()
