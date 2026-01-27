# LLM Integration Guide

## Overview

The Narrative Consistency Checker supports multiple Large Language Model (LLM) backends for two key tasks:

1. **Story Structuring**: Converting raw narrative text into structured JSON
2. **Violation Interpretation**: Converting ASP violation atoms into human-readable explanations

This guide covers configuration, usage patterns, and troubleshooting for each supported backend.

---

## Supported Backends

| Backend | ID | Description | Best For |
|---------|-----|-------------|----------|
| OpenAI-Compatible | `openai` | Any API following OpenAI's chat completion spec | Local LLMs (llamafile, Ollama), OpenAI, Azure |
| Google Gemini | `gemini` | Google's Generative AI API | Production use, high accuracy |
| Guidance | `guidance` | Microsoft's constrained generation library | Guaranteed JSON structure |

---

## 1. OpenAI-Compatible Backend

### Configuration

```bash
# Environment variables
export OPENAI_API_BASE="http://localhost:8080/v1"  # API endpoint
export OPENAI_API_KEY="sk-..."                      # API key (or dummy for local)
```

Or in `.env` file:
```ini
OPENAI_API_BASE=http://localhost:8080/v1
OPENAI_API_KEY=sk-no-key-required
```

### Supported Services

#### Local LLMs via llamafile

```bash
# Start llamafile server
./gemma-3-12b-it.llamafile --server --port 8080

# Configure
export OPENAI_API_BASE=http://localhost:8080/v1
export OPENAI_API_KEY=sk-dummy
```

#### Local LLMs via Ollama

```bash
# Start Ollama
ollama serve

# Pull a model
ollama pull llama3

# Configure
export OPENAI_API_BASE=http://localhost:11434/v1
export OPENAI_API_KEY=ollama
```

#### OpenAI API

```bash
export OPENAI_API_BASE=https://api.openai.com/v1
export OPENAI_API_KEY=sk-your-actual-key
```

#### Azure OpenAI

```bash
export OPENAI_API_BASE=https://your-resource.openai.azure.com/openai/deployments/your-deployment
export OPENAI_API_KEY=your-azure-key
```

### Usage

```bash
# Basic usage (auto-detects model)
python scripts/story_lint.py story.txt --backend openai

# Specify model explicitly
python scripts/story_lint.py story.txt --backend openai --model gpt-4o-mini

# For local LLMs, use "auto" to query the API
python scripts/story_lint.py story.txt --backend openai --model auto
```

### API Request Format

```python
# Request structure
{
    "model": "model-name",
    "messages": [
        {"role": "user", "content": "prompt text"}
    ],
    "temperature": 0.3,
    "response_format": {"type": "json_object"}  # If supported
}

# Response structure
{
    "choices": [
        {
            "message": {
                "content": "response text with JSON"
            }
        }
    ],
    "model": "actual-model-name",
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 50
    }
}
```

### Troubleshooting

**Connection refused**
```bash
# Check if server is running
curl http://localhost:8080/v1/models
```

**Invalid JSON response**
- Local LLMs may struggle with JSON formatting
- Use `--backend gemini` for more reliable JSON output
- Or use `--backend guidance` for constrained generation

**Model not found**
```bash
# List available models
curl http://localhost:8080/v1/models | jq '.data[].id'
```

---

## 2. Google Gemini Backend

### Configuration

```bash
# Get API key from https://makersuite.google.com/app/apikey
export GEMINI_API_KEY=your-gemini-api-key
```

Or in `.env` file:
```ini
GEMINI_API_KEY=AIza...your-key
```

### Usage

```bash
# Default model (gemini-2.5-flash)
python scripts/story_lint.py story.txt --backend gemini

# Specific model
python scripts/story_lint.py story.txt --backend gemini --model gemini-2.5-pro
```

### Available Models

| Model | Speed | Quality | Cost |
|-------|-------|---------|------|
| `gemini-2.5-flash` | Fast | Good | Low |
| `gemini-2.5-pro` | Slower | Excellent | Higher |
| `gemini-1.5-flash` | Fast | Good | Low |
| `gemini-1.5-pro` | Medium | Very Good | Medium |

### API Request Format

```python
# Request structure (REST API)
{
    "contents": [
        {
            "parts": [
                {"text": "prompt text"}
            ]
        }
    ],
    "generationConfig": {
        "temperature": 0.3,
        "responseMimeType": "application/json"  # Forces JSON output
    }
}

# Response structure
{
    "candidates": [
        {
            "content": {
                "parts": [
                    {"text": "response JSON"}
                ]
            }
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 100,
        "candidatesTokenCount": 50
    }
}
```

### Advantages

- **Native JSON mode**: Gemini can be forced to output valid JSON
- **High accuracy**: Excellent at following complex instructions
- **Fast inference**: Especially with Flash models
- **Generous free tier**: Good for development and testing

### Troubleshooting

**API key invalid**
```bash
# Test API key
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY"
```

**Rate limiting**
- Free tier has limits (60 requests/minute)
- Add delays between requests or upgrade to paid tier

**Response blocked**
- Gemini may refuse certain content
- Check `candidates[0].finishReason` in response

---

## 3. Guidance Backend

### Configuration

```bash
# Requires local model or HuggingFace model
pip install guidance transformers torch
```

### Usage

```bash
# With llamafile backend
python scripts/story_lint.py story.txt --backend guidance

# Note: Guidance requires special model support
```

### How It Works

Guidance uses constrained decoding to guarantee valid JSON:

```python
from guidance import models, gen

# Load model
llm = models.LlamaCpp("path/to/model.gguf")

# Constrained generation
with llm:
    response = llm + f'''
    {prompt}
    
    Output JSON:
    {{
        "error_count": {gen('count', regex=r'\d+')},
        "errors": [
            {gen('errors', max_tokens=2000)}
        ]
    }}
    '''
```

### Advantages

- **Guaranteed valid JSON**: Uses grammar-constrained decoding
- **Efficient**: Doesn't waste tokens on invalid output
- **Works offline**: Uses local models

### Disadvantages

- **Limited model support**: Not all models work with guidance
- **Complex setup**: Requires specific model formats
- **Slower**: Constrained decoding adds overhead

### Troubleshooting

**Model not compatible**
- Guidance works best with GGUF format models
- Not all models support grammar-constrained decoding

---

## Model Auto-Detection

When `--model auto` is specified, the system attempts to detect the available model:

### OpenAI Backend
```python
def get_model_id(api_base, api_key):
    """Query /v1/models endpoint to find available model."""
    response = requests.get(
        f"{api_base}/models",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    models = response.json()["data"]
    
    # Return first available model
    if models:
        return models[0]["id"]
    return "gpt-3.5-turbo"  # Fallback
```

### Gemini Backend
```python
def get_gemini_model():
    """Default to gemini-2.5-flash if not specified."""
    return "gemini-2.5-flash"
```

---

## Prompts

### Story Structuring Prompt

Located at `prompts/structure_prompt.txt`:

```
You are a narrative analyzer. Convert the following story into structured JSON.

STORY:
{{STORY}}

Output a JSON object with this structure:
{
  "entities": {
    "characters": [...],
    "objects": [...],
    "locations": [...]
  },
  "events": [...],
  "time_order": [...],
  "fluents": [...],
  "traits": [...],
  "rules": [...]
}

[Detailed schema documentation...]
```

### LLM Lint Prompt

Embedded in `story_lint.py`:

```python
LLM_LINT_PROMPT = """
You are a narrative consistency checker. Analyze the following story for logical errors.

STORY:
{story}

Check for:
1. Temporal inconsistencies (events in impossible order)
2. Spatial violations (person in two places at once)
3. Causal violations (effect before cause)
4. Character trait violations
5. Physical impossibilities
6. Continuity errors

Output JSON:
{{
  "error_count": <number>,
  "errors": [
    {{"id": "E1", "description": "..."}}
  ]
}}
"""
```

### Violation Interpretation Prompt

```python
INTERPRET_PROMPT = """
Convert these logical violations into human-readable error descriptions.

Story context: {story}

Violations detected:
{violations}

For each violation, explain what inconsistency it represents.

Output JSON:
{{
  "error_count": <number>,
  "errors": [
    {{"id": "<violation_id>", "description": "..."}}
  ]
}}
"""
```

---

## Best Practices

### 1. Model Selection

| Use Case | Recommended Backend | Model |
|----------|---------------------|-------|
| Development/Testing | OpenAI (local) | Any llamafile model |
| Production | Gemini | gemini-2.5-flash |
| Guaranteed JSON | Guidance | Local GGUF model |
| Highest accuracy | Gemini | gemini-2.5-pro |

### 2. Temperature Settings

```python
# For structured output (JSON)
temperature = 0.1  # Low temperature = more deterministic

# For creative interpretation
temperature = 0.5  # Medium temperature

# For diverse outputs
temperature = 0.8  # Higher temperature = more variety
```

### 3. Error Handling

```python
def call_with_retry(func, max_retries=3):
    """Retry API calls with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
```

### 4. JSON Extraction

```python
def extract_json(text):
    """Extract JSON from LLM response, handling various formats."""
    
    # Remove <think> blocks (for reasoning models)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # Try to find JSON block
    patterns = [
        r'```json\s*(.*?)\s*```',  # Markdown code block
        r'```\s*(.*?)\s*```',       # Generic code block
        r'(\{.*\})',                # Raw JSON
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    
    # Last resort: try to parse entire text
    return json.loads(text)
```

### 5. Validation

```python
def validate_structure(data):
    """Ensure LLM output has required fields."""
    
    # Add missing top-level fields
    data.setdefault("entities", {})
    data.setdefault("events", [])
    data.setdefault("time_order", [])
    data.setdefault("fluents", [])
    data.setdefault("traits", [])
    data.setdefault("rules", [])
    
    # Add missing entity types
    data["entities"].setdefault("characters", [])
    data["entities"].setdefault("objects", [])
    data["entities"].setdefault("locations", [])
    
    return data
```

---

## Performance Comparison

| Backend | Speed | JSON Reliability | Cost | Offline |
|---------|-------|------------------|------|---------|
| Local llamafile | Medium | Variable | Free | ✅ |
| Ollama | Medium | Variable | Free | ✅ |
| OpenAI API | Fast | High | $$ | ❌ |
| Gemini | Fast | Very High | $ | ❌ |
| Guidance | Slow | Perfect | Free | ✅ |

---

## Example Integration

### Minimal Python Usage

```python
from scripts.llm_structurer import structure_story

# Using Gemini
result = structure_story(
    story_text=open("story.txt").read(),
    backend="gemini",
    api_key="your-gemini-key",
    return_details=True
)

# Result contains:
# - result["structure"]: The structured JSON
# - result["prompt"]: The prompt used
# - result["raw_response"]: The raw LLM response
# - result["model"]: The model used
```

### Full Pipeline Example

```python
import json
from scripts.llm_structurer import structure_story
from scripts.json_to_asp import json_to_asp
import clingo

# 1. Structure the story
story = open("story.txt").read()
structured = structure_story(story, backend="gemini", api_key=API_KEY)

# 2. Convert to ASP
asp_facts = json_to_asp(structured["structure"])

# 3. Run Clingo
ctl = clingo.Control()
ctl.add("facts", [], asp_facts)
ctl.load("rules/base.lp")
ctl.ground([("facts", []), ("base", [])])

# 4. Collect violations
violations = []
with ctl.solve(yield_=True) as handle:
    for model in handle:
        for atom in model.symbols(shown=True):
            if atom.name == "violation":
                violations.append(str(atom))

print(f"Found {len(violations)} violations")
for v in violations:
    print(f"  - {v}")
```
