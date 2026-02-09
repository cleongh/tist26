# Logic-Only Test Runner

Runs the ASP/Clingo logic engine on pre-extracted chapter data **without invoking LLMs**. Useful for testing rule changes or validating logic on existing extractions.

## Prerequisites

- Existing `step2_extractions.jsonl` file in the experiment directory
- Clingo installed and available in Python environment

## Basic Usage

```powershell
python scripts/logic_only_test_runner.py --experiment_dir experiments/<experiment_name>
```

## Arguments

| Argument | Short | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `--experiment_dir` | | Yes | - | Path to experiment directory containing `step2_extractions.jsonl` |
| `--output_log` | | No | `logic_test_results.txt` | Path to output log file |
| `--verbose` | `-v` | No | false | Print verbose output during processing |
| `--trace` | `-t` | No | false | Enable per-statement evaluation traces |
| `--story` | `-s` | No | all | Filter to specific stories (supports multiple) |

## Examples

**Run on all stories:**
```powershell
python scripts/logic_only_test_runner.py --experiment_dir experiments/12_openai_hp_full
```

**Filter to one story:**
```powershell
python scripts/logic_only_test_runner.py --experiment_dir experiments/12_openai_hp_full -s "Harry Potter"
```

**Filter to multiple stories:**
```powershell
python scripts/logic_only_test_runner.py --experiment_dir experiments/12_openai_hp_full -s "Harry Potter" "Twilight"
```

**With verbose output and trace:**
```powershell
python scripts/logic_only_test_runner.py --experiment_dir experiments/12_openai_hp_full -v -t
```

**Custom output file:**
```powershell
python scripts/logic_only_test_runner.py --experiment_dir experiments/12_openai_hp_full --output_log my_results.txt
```

## Output

- **Log file**: Contains violations per chapter, aggregated counts, and optionally per-statement traces
- **Console**: Summary with total violations and breakdown by category

When using `--story`, the output filename automatically appends the story name(s):
- Single story: `logic_test_results_harry_potter.txt`
- Multiple stories: `logic_test_results_harry_potter_twilight.txt`

## Workflow

1. Run extraction with `--extraction-only` flag (generates `step2_extractions.jsonl`)
2. Modify rules in `rules/` directory as needed
3. Run this script to test rule changes without re-running LLM extraction
4. Iterate on rules until satisfied
