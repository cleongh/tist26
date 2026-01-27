#!/usr/bin/env python3
"""
experiment_runner.py - Comprehensive Narrative Evaluation Experiment
=====================================================================

This script runs a complete experiment comparing LLM-based and Logic-based
narrative evaluation across all five error categories:

1. CAUSALITY - Chekhov's gun, cause-effect violations
2. COHERENCE - Semantic/logical violations, physical impossibility
3. TEMPORAL  - Time ordering, duration, overlap violations  
4. LOCATION  - Spatial constraints, ubiquity, teleportation
5. EMOTIONAL - Character relationships, motivations, behavior

WORKFLOW:
1. Create experiment folder with timestamps and UUID
2. Load/create stories for analysis
3. For each story:
   a. Run LLM linting (direct semantic analysis)
   b. Run Logic linting (ASP-based formal verification)
   c. Compare and record results by category
4. Generate domain-specific ASP module from all stories
5. Generate comprehensive markdown report

OUTPUT STRUCTURE:
experiment_<name>-<start>-<end>-<uuid>/
├── config.json           # Experiment configuration
├── stories/              # Input stories as text files
├── llm_results/          # LLM lint JSON per story
├── logic_results/        # Logic lint JSON per story
├── structured_json/      # Structured story JSON
├── asp_facts/            # Generated ASP facts
├── domain_module.lp      # Generated domain-specific rules
├── logs/                 # Timestamped execution logs
├── report.md             # Comprehensive markdown report
└── summary.json          # Machine-readable summary

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from json_to_asp import json_to_asp
from llm_structurer import structure_story
from domain_generator import DomainGenerator, generate_domain_from_stories

# Error categories
ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]


def log(msg: str, log_file: Optional[Path] = None) -> None:
    """Log message to stderr and optionally to file."""
    timestamp = datetime.now().isoformat()
    formatted = f"[{timestamp}] {msg}"
    sys.stderr.write(formatted + "\n")
    if log_file:
        with open(log_file, "a") as f:
            f.write(formatted + "\n")


def create_experiment_folder(name: str, base_dir: Path) -> Tuple[Path, str, datetime]:
    """Create experiment folder with timestamp and UUID."""
    start_time = datetime.now()
    exp_uuid = str(uuid.uuid4())[:8]
    folder_name = f"{name}-{start_time.strftime('%Y%m%d_%H%M%S')}-pending-{exp_uuid}"
    exp_dir = base_dir / folder_name
    
    # Create subdirectories
    (exp_dir / "stories").mkdir(parents=True)
    (exp_dir / "llm_results").mkdir()
    (exp_dir / "logic_results").mkdir()
    (exp_dir / "structured_json").mkdir()
    (exp_dir / "asp_facts").mkdir()
    (exp_dir / "logs").mkdir()
    
    return exp_dir, exp_uuid, start_time


def finalize_experiment_folder(exp_dir: Path, start_time: datetime) -> Path:
    """Rename folder with end timestamp."""
    end_time = datetime.now()
    old_name = exp_dir.name
    # Replace 'pending' with end timestamp
    new_name = old_name.replace("-pending-", f"-{end_time.strftime('%Y%m%d_%H%M%S')}-")
    new_dir = exp_dir.parent / new_name
    exp_dir.rename(new_dir)
    return new_dir


class ExperimentRunner:
    """
    Runs comprehensive narrative evaluation experiments.
    
    Compares LLM-based semantic analysis with Logic-based ASP reasoning
    across five error categories.
    """
    
    def __init__(
        self,
        exp_dir: Path,
        llm_base_url: str = "http://localhost:8080/v1",
        llm_timeout: int = 600,
        llm_model: str = "auto",
    ):
        self.exp_dir = exp_dir
        self.llm_base_url = llm_base_url
        self.llm_timeout = llm_timeout
        self.llm_model = llm_model
        self.log_file = exp_dir / "logs" / "experiment.log"
        
        # Results storage
        self.stories: Dict[str, str] = {}
        self.llm_results: Dict[str, Dict] = {}
        self.logic_results: Dict[str, Dict] = {}
        self.structured_data: List[Dict] = []
        
        # Load prompts - use v2 if available, fall back to original
        repo_root = SCRIPT_DIR.parent
        lint_v2_path = repo_root / "prompts" / "lint_prompt_v2.txt"
        if lint_v2_path.exists():
            self.lint_prompt = lint_v2_path.read_text()
        else:
            # Fallback basic prompt
            self.lint_prompt = """Analyze this story for narrative errors. Return JSON:
{{"error_count": N, "errors": [{{"id": "e1", "category": "...", "type": "...", "description": "...", "story_fragment": "..."}}], "summary": {{"by_category": {{"causality": N, "coherence": N, "temporal": N, "location": N, "emotional": N}}}}}}

Story:
\"\"\"
{story}
\"\"\"
"""
        # Use original simpler prompt for structuring (more reliable with local LLMs)
        struct_v2_path = repo_root / "prompts" / "structure_prompt_v2.txt"
        struct_orig_path = repo_root / "prompts" / "structure_prompt.txt"
        if struct_orig_path.exists():
            self.structure_prompt_path = "prompts/structure_prompt.txt"
        elif struct_v2_path.exists():
            self.structure_prompt_path = "prompts/structure_prompt_v2.txt"
        else:
            self.structure_prompt_path = "prompts/structure_prompt_documented.txt"
        
    def log(self, msg: str) -> None:
        """Log with timestamp."""
        log(msg, self.log_file)
        
    def add_story(self, title: str, content: str) -> None:
        """Add a story for analysis."""
        self.stories[title] = content
        # Save to stories folder
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        story_path = self.exp_dir / "stories" / f"{safe_title}.txt"
        story_path.write_text(content)
        self.log(f"Added story: {title} ({len(content)} chars)")
        
    def run_llm_lint(self, title: str, content: str) -> Dict[str, Any]:
        """Run LLM-based linting on a story."""
        import urllib.request
        import urllib.error
        
        self.log(f"Running LLM lint on: {title}")
        start_time = time.time()
        
        prompt = self.lint_prompt.format(story=content.strip())
        
        # Call LLM
        url = self.llm_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.llm_model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": "You are a narrative consistency analyzer. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 4096,
        }
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            
            with urllib.request.urlopen(req, timeout=self.llm_timeout) as resp:
                body = resp.read().decode("utf-8")
                
            obj = json.loads(body)
            content_str = obj["choices"][0]["message"]["content"]
            
            # Extract JSON from response
            result = self._extract_json(content_str)
            
            elapsed = time.time() - start_time
            self.log(f"LLM lint completed in {elapsed:.1f}s: {result.get('error_count', 0)} errors")
            
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat(),
                "model": self.llm_model,
            }
            
            return result
            
        except Exception as e:
            self.log(f"LLM lint failed for {title}: {e}")
            return {
                "error_count": 0,
                "errors": [],
                "summary": {cat: 0 for cat in ERROR_CATEGORIES},
                "_meta": {"error": str(e)},
            }
            
    def run_logic_lint(self, title: str, content: str) -> Dict[str, Any]:
        """Run logic-based linting on a story."""
        self.log(f"Running Logic lint on: {title}")
        start_time = time.time()
        
        try:
            # Step 1: Structure the story
            struct_result = structure_story(
                content,
                prompt_path=self.structure_prompt_path,
                model=self.llm_model,
                base_url=self.llm_base_url,
                timeout=self.llm_timeout,
                max_tokens=16384,
                return_details=True,
            )
            
            structured_data = struct_result["parsed"]
            self.structured_data.append(structured_data)
            
            # Save structured JSON
            safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
            json_path = self.exp_dir / "structured_json" / f"{safe_title}.json"
            json_path.write_text(json.dumps(structured_data, indent=2))
            
            # Step 2: Convert to ASP facts
            asp_facts = json_to_asp(structured_data)
            facts_path = self.exp_dir / "asp_facts" / f"{safe_title}.lp"
            facts_path.write_text(asp_facts)
            
            # Step 3: Run Clingo with general rules
            violations = self._run_clingo(asp_facts)
            
            # Step 4: Categorize violations
            result = self._categorize_violations(violations)
            
            elapsed = time.time() - start_time
            self.log(f"Logic lint completed in {elapsed:.1f}s: {result.get('error_count', 0)} violations")
            
            result["_meta"] = {
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat(),
                "asp_facts_lines": len(asp_facts.split("\n")),
            }
            
            return result
            
        except Exception as e:
            self.log(f"Logic lint failed for {title}: {e}")
            import traceback
            self.log(traceback.format_exc())
            return {
                "error_count": 0,
                "errors": [],
                "summary": {"by_category": {cat: 0 for cat in ERROR_CATEGORIES}},
                "_meta": {"error": str(e)},
            }
            
    def _extract_json(self, text: str) -> Dict:
        """Extract JSON from LLM response."""
        text = text.strip()
        
        # Remove <think> blocks
        start = text.find("<think>")
        end = text.find("</think>")
        if start != -1 and end != -1:
            text = text[:start] + text[end + len("</think>"):]
            
        # Find JSON
        start = text.find("{")
        if start == -1:
            return {"error_count": 0, "errors": [], "summary": {}}
            
        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i+1])
                    
        return {"error_count": 0, "errors": [], "summary": {}}
        
    def _run_clingo(self, asp_facts: str) -> List[Tuple]:
        """Run Clingo solver and return violations."""
        import clingo
        
        violations = []
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(asp_facts)
            facts_path = f.name
            
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load general rules and domain rules
            general_path = SCRIPT_DIR.parent / "rules" / "general.lp"
            if general_path.exists():
                ctl.load(str(general_path))
            else:
                # Fall back to base.lp
                base_path = SCRIPT_DIR.parent / "rules" / "base.lp"
                if base_path.exists():
                    ctl.load(str(base_path))
                    
            # Load domain module if exists
            domain_path = self.exp_dir / "domain_module.lp"
            if domain_path.exists():
                ctl.load(str(domain_path))
                
            ctl.load(facts_path)
            ctl.ground([("base", [])])
            
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "violation":
                            parts = tuple(str(arg) for arg in atom.arguments)
                            violations.append(parts)
                            
        finally:
            os.unlink(facts_path)
            
        return violations
        
    def _categorize_violations(self, violations: List[Tuple]) -> Dict[str, Any]:
        """Categorize violations by the five error categories."""
        errors = []
        category_counts = {cat: 0 for cat in ERROR_CATEGORIES}
        
        for i, v in enumerate(violations):
            # Violations can be (category, type, event, detail) or (type, event) or (type, event, detail)
            if len(v) >= 4:
                category = v[0].lower()
                vtype = v[1]
                event = v[2]
                detail = v[3]
            elif len(v) >= 2:
                # Legacy format - infer category from type
                vtype = v[0]
                event = v[1]
                detail = v[2] if len(v) > 2 else ""
                category = self._infer_category(vtype)
            else:
                continue
                
            if category in category_counts:
                category_counts[category] += 1
                
            errors.append({
                "id": f"logic_{i+1}",
                "category": category,
                "type": vtype,
                "event": event,
                "detail": str(detail),
                "description": f"Violation: {vtype} at event {event}" + (f" ({detail})" if detail else ""),
            })
            
        return {
            "error_count": len(errors),
            "errors": errors,
            "summary": {
                "by_category": category_counts,
            },
        }
        
    def _infer_category(self, vtype: str) -> str:
        """Infer error category from violation type."""
        vtype = vtype.lower()
        
        if vtype in {"ubiquity", "proximity_required", "impossible_travel"}:
            return "location"
        if vtype in {"circular_time", "negative_duration", "explicit_order_violated"}:
            return "temporal"
        if vtype in {"chekhov_gun", "uncaused_event", "effect_without_cause", "precondition_missing"}:
            return "causality"
        if vtype in {"harm_loved", "help_enemy", "approach_feared", "misplaced_trust", "state_action_mismatch"}:
            return "emotional"
        # Default to coherence
        return "coherence"
        
    def generate_domain_module(self) -> None:
        """Generate domain-specific ASP module from all structured stories."""
        self.log("Generating domain-specific ASP module...")
        
        if not self.structured_data:
            self.log("No structured data available for domain generation")
            return
            
        asp_content = generate_domain_from_stories(
            self.structured_data,
            self.exp_dir / "domain_module.lp"
        )
        
        self.log(f"Domain module generated: {len(asp_content)} bytes")
        
    def run_experiment(self) -> Dict[str, Any]:
        """Run the complete experiment."""
        self.log(f"Starting experiment with {len(self.stories)} stories")
        
        # First pass: structure all stories and generate domain module
        self.log("Phase 1: Structuring stories and generating domain module...")
        for title, content in self.stories.items():
            try:
                struct_result = structure_story(
                    content,
                    prompt_path=self.structure_prompt_path,
                    model=self.llm_model,
                    base_url=self.llm_base_url,
                    timeout=self.llm_timeout,
                    max_tokens=16384,
                    return_details=True,
                )
                self.structured_data.append(struct_result["parsed"])
                
                # Save structured JSON
                safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
                json_path = self.exp_dir / "structured_json" / f"{safe_title}.json"
                json_path.write_text(json.dumps(struct_result["parsed"], indent=2))
                
            except Exception as e:
                self.log(f"Failed to structure {title}: {e}")
                
        # Generate domain module
        self.generate_domain_module()
        
        # Second pass: run linting
        self.log("Phase 2: Running linters...")
        for title, content in self.stories.items():
            safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
            
            # LLM lint
            llm_result = self.run_llm_lint(title, content)
            self.llm_results[title] = llm_result
            llm_path = self.exp_dir / "llm_results" / f"{safe_title}.json"
            llm_path.write_text(json.dumps(llm_result, indent=2))
            
            # Logic lint
            logic_result = self.run_logic_lint(title, content)
            self.logic_results[title] = logic_result
            logic_path = self.exp_dir / "logic_results" / f"{safe_title}.json"
            logic_path.write_text(json.dumps(logic_result, indent=2))
            
        return self._compile_summary()
        
    def _compile_summary(self) -> Dict[str, Any]:
        """Compile experiment summary."""
        summary = {
            "total_stories": len(self.stories),
            "llm_total_errors": sum(r.get("error_count", 0) for r in self.llm_results.values()),
            "logic_total_errors": sum(r.get("error_count", 0) for r in self.logic_results.values()),
            "by_category": {
                "llm": {cat: 0 for cat in ERROR_CATEGORIES},
                "logic": {cat: 0 for cat in ERROR_CATEGORIES},
            },
            "per_story": {},
        }
        
        for title in self.stories:
            llm_r = self.llm_results.get(title, {})
            logic_r = self.logic_results.get(title, {})
            
            summary["per_story"][title] = {
                "llm_errors": llm_r.get("error_count", 0),
                "logic_errors": logic_r.get("error_count", 0),
            }
            
            # Aggregate by category
            llm_summary = llm_r.get("summary", {}).get("by_category", {})
            for cat in ERROR_CATEGORIES:
                summary["by_category"]["llm"][cat] += llm_summary.get(cat, 0)
                
            logic_summary = logic_r.get("summary", {}).get("by_category", {})
            for cat in ERROR_CATEGORIES:
                summary["by_category"]["logic"][cat] += logic_summary.get(cat, 0)
                
        return summary
        
    def generate_report(self) -> str:
        """Generate comprehensive markdown report."""
        summary = self._compile_summary()
        
        lines = []
        lines.append("# Narrative Evaluation Experiment Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().isoformat()}")
        lines.append(f"**Stories Analyzed:** {summary['total_stories']}")
        lines.append("")
        
        lines.append("## Executive Summary")
        lines.append("")
        lines.append("| Metric | LLM Linter | Logic Linter |")
        lines.append("|--------|------------|--------------|")
        lines.append(f"| Total Errors | {summary['llm_total_errors']} | {summary['logic_total_errors']} |")
        lines.append("")
        
        lines.append("## Errors by Category")
        lines.append("")
        lines.append("| Category | LLM | Logic | Description |")
        lines.append("|----------|-----|-------|-------------|")
        
        category_descriptions = {
            "causality": "Chekhov's gun, cause-effect violations",
            "coherence": "Semantic/logical consistency, physical impossibility",
            "temporal": "Time ordering, duration, overlap violations",
            "location": "Spatial constraints, ubiquity, impossible travel",
            "emotional": "Character relationships, motivations, behavior",
        }
        
        for cat in ERROR_CATEGORIES:
            llm_count = summary["by_category"]["llm"].get(cat, 0)
            logic_count = summary["by_category"]["logic"].get(cat, 0)
            desc = category_descriptions.get(cat, "")
            lines.append(f"| **{cat.title()}** | {llm_count} | {logic_count} | {desc} |")
            
        lines.append("")
        
        lines.append("## Per-Story Results")
        lines.append("")
        
        for title in sorted(self.stories.keys()):
            lines.append(f"### {title}")
            lines.append("")
            
            llm_r = self.llm_results.get(title, {})
            logic_r = self.logic_results.get(title, {})
            
            lines.append(f"**LLM Errors:** {llm_r.get('error_count', 0)}")
            lines.append(f"**Logic Errors:** {logic_r.get('error_count', 0)}")
            lines.append("")
            
            # List LLM errors
            if llm_r.get("errors"):
                lines.append("#### LLM-Detected Errors")
                lines.append("")
                for err in llm_r["errors"]:
                    cat = err.get("category", "unknown")
                    desc = err.get("description", "No description")
                    frag = err.get("story_fragment", "")
                    lines.append(f"- **[{cat.upper()}]** {desc}")
                    if frag:
                        lines.append(f"  - Fragment: *\"{frag[:200]}...\"*" if len(frag) > 200 else f"  - Fragment: *\"{frag}\"*")
                lines.append("")
                
            # List Logic errors
            if logic_r.get("errors"):
                lines.append("#### Logic-Detected Errors")
                lines.append("")
                for err in logic_r["errors"]:
                    cat = err.get("category", "unknown")
                    vtype = err.get("type", "unknown")
                    event = err.get("event", "")
                    lines.append(f"- **[{cat.upper()}]** {vtype} at event {event}")
                lines.append("")
                
        lines.append("## Methodology")
        lines.append("")
        lines.append("### LLM-Based Linting")
        lines.append("Direct semantic analysis using a large language model to identify narrative inconsistencies.")
        lines.append("The LLM analyzes the story text for logical, temporal, spatial, and emotional coherence.")
        lines.append("")
        lines.append("### Logic-Based Linting")
        lines.append("Formal verification using Answer Set Programming (ASP) with the Clingo solver.")
        lines.append("Stories are first converted to structured JSON, then to ASP facts.")
        lines.append("The reasoner applies general narrative consistency rules and domain-specific knowledge.")
        lines.append("")
        lines.append("### Error Categories")
        lines.append("")
        lines.append("1. **Causality**: Violations of cause-effect relationships (Chekhov's gun principle)")
        lines.append("2. **Coherence**: Semantic and logical inconsistencies (physical impossibility)")
        lines.append("3. **Temporal**: Time-related violations (impossible ordering, duration)")
        lines.append("4. **Location**: Spatial violations (ubiquity, impossible travel)")
        lines.append("5. **Emotional**: Character motivation and relationship violations")
        lines.append("")
        
        return "\n".join(lines)


def main():
    """Main entry point for experiment runner."""
    parser = argparse.ArgumentParser(description="Run narrative evaluation experiment")
    parser.add_argument("--name", default="narrative_eval", help="Experiment name")
    parser.add_argument("--stories-dir", type=Path, help="Directory containing story files")
    parser.add_argument("--output-dir", type=Path, default=Path("experiments"), help="Output directory")
    parser.add_argument("--llm-base-url", default="http://localhost:8080/v1", help="LLM API URL")
    parser.add_argument("--llm-timeout", type=int, default=600, help="LLM timeout in seconds")
    parser.add_argument("--llm-model", default="auto", help="LLM model name")
    
    args = parser.parse_args()
    
    # Create experiment folder
    exp_dir, exp_uuid, start_time = create_experiment_folder(args.name, args.output_dir)
    
    print(f"Experiment folder: {exp_dir}")
    
    # Initialize runner
    runner = ExperimentRunner(
        exp_dir,
        llm_base_url=args.llm_base_url,
        llm_timeout=args.llm_timeout,
        llm_model=args.llm_model,
    )
    
    # Load stories
    if args.stories_dir and args.stories_dir.exists():
        for story_file in sorted(args.stories_dir.glob("*.txt")):
            title = story_file.stem
            content = story_file.read_text()
            runner.add_story(title, content)
    else:
        print("No stories directory specified. Use --stories-dir or add stories programmatically.")
        return
        
    # Run experiment
    summary = runner.run_experiment()
    
    # Save summary
    summary_path = exp_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    
    # Generate and save report
    report = runner.generate_report()
    report_path = exp_dir / "report.md"
    report_path.write_text(report)
    
    # Finalize folder name
    final_dir = finalize_experiment_folder(exp_dir, start_time)
    
    print(f"Experiment complete: {final_dir}")
    print(f"Report: {final_dir / 'report.md'}")


if __name__ == "__main__":
    main()
