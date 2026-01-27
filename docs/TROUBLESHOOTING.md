# Troubleshooting Guide

This guide helps diagnose and fix common issues with the Narrative Consistency Checker.

---

## Quick Diagnostic Commands

```bash
# Check Python version
python --version  # Should be 3.10+

# Check if clingo is installed
python -c "import clingo; print(clingo.__version__)"

# Check if API key is set (Gemini)
echo $GEMINI_API_KEY | head -c 10

# Check if API key is set (OpenAI)
echo $OPENAI_API_KEY | head -c 10

# Test Gemini API connection
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY"

# Test local LLM connection
curl http://localhost:8080/v1/models
```

---

## Installation Issues

### Issue: `ModuleNotFoundError: No module named 'clingo'`

**Cause:** Clingo is not installed or not in the Python path.

**Solution:**
```bash
# Install via pip
pip install clingo

# Or via conda
conda install -c potassco clingo

# Verify
python -c "import clingo; print('OK')"
```

### Issue: `ModuleNotFoundError: No module named 'dotenv'`

**Cause:** python-dotenv not installed.

**Solution:**
```bash
pip install python-dotenv
```

### Issue: Clingo installation fails on Apple Silicon

**Cause:** Pre-built wheels may not be available.

**Solution:**
```bash
# Install via conda (recommended for Apple Silicon)
conda install -c conda-forge clingo

# Or build from source
pip install clingo --no-binary :all:
```

---

## API Connection Issues

### Issue: `Connection refused` for local LLM

**Cause:** The local LLM server is not running.

**Solution:**
```bash
# Start llamafile
./model.llamafile --server --port 8080

# Or start Ollama
ollama serve

# Verify
curl http://localhost:8080/v1/models
```

### Issue: `401 Unauthorized` for Gemini

**Cause:** Invalid or missing API key.

**Solution:**
```bash
# Set the environment variable
export GEMINI_API_KEY="your-actual-key"

# Or create .env file
echo "GEMINI_API_KEY=your-actual-key" > .env

# Verify key works
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY"
```

### Issue: `429 Too Many Requests` for Gemini

**Cause:** Rate limit exceeded.

**Solution:**
- Wait a few minutes before retrying
- Use `--backend openai` with local LLM instead
- Upgrade to paid Gemini tier

### Issue: `API key not found` error

**Cause:** Environment variable not set or .env file not loaded.

**Solution:**
```bash
# Check if .env exists
cat .env

# Ensure dotenv is loaded (add to script if needed)
from dotenv import load_dotenv
load_dotenv()

# Or pass key explicitly
python scripts/story_lint.py story.txt --backend gemini --api-key "your-key"
```

---

## JSON Parsing Issues

### Issue: `JSONDecodeError: Expecting property name`

**Cause:** LLM output contains invalid JSON.

**Symptoms:**
```
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 5 column 3
```

**Diagnosis:**
```bash
# Check the raw output in output.json
cat output.json | jq '.[-1].logic_lint.structuring.raw_response'
```

**Solutions:**

1. **Try Gemini backend** (more reliable JSON):
   ```bash
   python scripts/story_lint.py story.txt --backend gemini
   ```

2. **Use a better local model** (larger models produce better JSON):
   ```bash
   # Use a larger model like llama3-70b instead of 7b
   ```

3. **Lower temperature** (add to script if needed):
   ```python
   temperature = 0.1  # More deterministic output
   ```

### Issue: `<think>` blocks in output

**Cause:** Using a reasoning model that includes thinking traces.

**Symptoms:**
```
<think>Let me analyze this story...</think>
{"entities": ...}
```

**Solution:** The code handles this automatically via `strip_think()`, but verify:
```python
# In llm_structurer.py
text = strip_think(text)  # Removes <think>...</think>
```

### Issue: Markdown code blocks in output

**Cause:** LLM wraps JSON in markdown formatting.

**Symptoms:**
```
```json
{"entities": ...}
```
```

**Solution:** The code handles this automatically, but verify extraction:
```python
# extract_json handles: ```json ... ``` and ``` ... ```
```

---

## ASP/Clingo Issues

### Issue: `syntax error, unexpected IDENTIFIER`

**Cause:** Invalid ASP syntax in generated facts.

**Diagnosis:**
```bash
# Check the ASP facts
cat output.json | jq -r '.[-1].logic_lint.asp.facts'

# Look for invalid characters in atoms
```

**Common causes:**
- Spaces in identifiers: `white pebbles` should be `white_pebbles`
- Hyphens: `gingerbread-house` should be `gingerbread_house`
- Numbers at start: `123abc` should be `x123abc`
- Special characters: `O'Brien` should be `obrien`

**Solution:** The `sanitize_symbol()` function should handle these. If not:
```python
# In json_to_asp.py
def sanitize_symbol(s):
    s = str(s).lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)  # Replace invalid chars
    s = re.sub(r'_+', '_', s)           # Collapse multiple underscores
    s = s.strip('_')
    if s and s[0].isdigit():
        s = 'x' + s
    return s or 'unknown'
```

### Issue: `info: no stable models`

**Cause:** The ASP program is unsatisfiable (contradictory rules).

**Diagnosis:**
```bash
# Run clingo directly with debug output
clingo facts.lp rules/base.lp --warn=all

# Look for conflicting rules
```

**Common causes:**
- Circular negative dependencies
- Contradictory constraints
- Missing required facts

**Solution:**
- Check your custom rules for logical errors
- Simplify rules to isolate the problem
- Use `#show` directives to trace derivations

### Issue: Clingo timeout

**Cause:** Very complex story or inefficient rules.

**Solution:**
```bash
# Increase timeout (in code)
ctl.solve(async_=True).wait(timeout=60)

# Simplify the problem
# - Reduce number of events
# - Use simpler rules
```

---

## Output Issues

### Issue: Empty violations list but story has obvious errors

**Cause:** The structured JSON doesn't capture the relevant information.

**Diagnosis:**
```bash
# Check what the LLM extracted
cat output.json | jq '.[-1].logic_lint.structuring.structure'

# Check the ASP facts
cat output.json | jq -r '.[-1].logic_lint.asp.facts'
```

**Common causes:**
- LLM missed an entity or event
- Wrong event type (e.g., "walk" instead of "move")
- Missing time ordering
- Missing fluents

**Solution:**
- Improve the structuring prompt
- Use a better LLM model
- Add examples to the prompt

### Issue: Too many false positive violations

**Cause:** Rules are too strict or world knowledge is incomplete.

**Examples:**
- `non_edible_food` for fantasy foods (magic mushrooms)
- `ubiquity` for teleportation stories
- `dead_agent` for ghost/zombie stories

**Solution:**

1. **Add exceptions to rules:**
   ```prolog
   % Ghosts can act after death
   violation(dead_agent, E) :-
       event(E), agent(E, A), time(E, T, _),
       dead_at(A, T),
       not ghost(A).  % Exception for ghosts
   ```

2. **Add domain-specific knowledge:**
   ```prolog
   % Fantasy foods are edible
   edible(O) :- magic_mushroom(O).
   edible(O) :- fairy_cake(O).
   ```

3. **Mark special characters:**
   ```json
   {
     "traits": [
       {"character": "casper", "trait": "ghost"}
     ]
   }
   ```

### Issue: output.json grows too large

**Cause:** Many runs appending to the same file.

**Solution:**
```bash
# Archive old output
mv output.json "output_$(date +%Y%m%d).json"

# Or truncate
echo '[]' > output.json

# Or use separate output files
python scripts/story_lint.py story.txt --output "run_$(date +%s).json"
```

---

## Performance Issues

### Issue: Structuring is slow

**Cause:** Large story or slow LLM.

**Solutions:**
1. Use Gemini Flash (faster):
   ```bash
   python scripts/story_lint.py story.txt --backend gemini --model gemini-2.5-flash
   ```

2. Split long stories:
   ```bash
   # Process in chunks
   split -l 50 story.txt chunk_
   for f in chunk_*; do
       python scripts/story_lint.py "$f" --backend gemini
   done
   ```

3. Use local LLM with GPU:
   ```bash
   # llamafile with GPU acceleration
   ./model.llamafile --server --port 8080 --n-gpu-layers 35
   ```

### Issue: Clingo is slow

**Cause:** Complex rules or many events.

**Diagnosis:**
```bash
# Time the solving
time clingo facts.lp rules/base.lp
```

**Solutions:**
1. Simplify rules (avoid excessive recursion)
2. Add domain predicates to limit grounding
3. Use Clingo's `--parallel-mode` for multi-core

---

## Debugging Techniques

### Enable Verbose Output

```bash
python scripts/story_lint.py story.txt --backend gemini --verbose
```

### Inspect Intermediate Files

```bash
# Extract facts to a file
cat output.json | jq -r '.[-1].logic_lint.asp.facts' > /tmp/facts.lp

# Run clingo manually
clingo /tmp/facts.lp rules/base.lp

# With trace output
clingo /tmp/facts.lp rules/base.lp --outf=2 | jq
```

### Add Debug Rules

```prolog
% In rules/base.lp, add:
#show violation/2.
#show violation/3.

% For more debugging:
#show dead_at/2.
#show overlap/2.
#show before/2.
```

### Test Individual Components

```python
# Test JSON to ASP conversion
from scripts.json_to_asp import json_to_asp
import json

data = json.load(open("examples/story.json"))
print(json_to_asp(data))
```

```python
# Test LLM structuring
from scripts.llm_structurer import structure_story

result = structure_story(
    "Alice went to the store.",
    backend="gemini",
    api_key="your-key",
    return_details=True
)
print(result["raw_response"])
```

### Check for Clingo Warnings

```bash
clingo facts.lp rules/base.lp --warn=all 2>&1 | grep -i warn
```

---

## Getting Help

### Collect Diagnostic Information

When reporting issues, include:

```bash
# System info
uname -a
python --version
python -c "import clingo; print(clingo.__version__)"

# Package versions
pip freeze | grep -E "clingo|requests|python-dotenv"

# Error output
python scripts/story_lint.py story.txt --backend gemini --verbose 2>&1 | tee debug.log

# Relevant output.json section
cat output.json | jq '.[-1]' > last_run.json
```

### Common Error Messages Reference

| Error | Likely Cause | Quick Fix |
|-------|--------------|-----------|
| `No module named 'clingo'` | Clingo not installed | `pip install clingo` |
| `GEMINI_API_KEY not set` | Missing env var | `export GEMINI_API_KEY=...` |
| `Connection refused` | Server not running | Start llamafile/Ollama |
| `401 Unauthorized` | Invalid API key | Check key is correct |
| `JSONDecodeError` | Bad LLM output | Use Gemini, lower temp |
| `syntax error` (ASP) | Invalid characters | Check sanitize_symbol |
| `no stable models` | Contradictory rules | Debug rules logic |
