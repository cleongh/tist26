#!/usr/bin/env python3
"""
story_lint.py - Main Orchestrator for Narrative Consistency Checking
=====================================================================

This is the main entry point for the narrative consistency checker. It combines
two complementary approaches to detect errors in stories:

1. **LLM Direct Linting**: Uses a Large Language Model to directly analyze the
   story text for inconsistencies, temporal conflicts, and logical errors.
   This approach is good at catching subtle, contextual issues.

2. **Logic-Based Linting**: Converts the story to structured JSON, then to
   Answer Set Programming (ASP) facts, and uses the Clingo solver to detect
   violations of formal rules. This approach provides sound, complete reasoning.

Architecture Overview
---------------------

```
                    ┌─────────────────┐
                    │   story.txt     │
                    │  (Input Story)  │
                    └────────┬────────┘
                             │
            ┌────────────────┴────────────────┐
            │                                 │
            ▼                                 ▼
    ┌───────────────┐                ┌────────────────┐
    │  LLM Direct   │                │ LLM Structurer │
    │    Linting    │                │  (→ JSON)      │
    └───────┬───────┘                └───────┬────────┘
            │                                │
            │                                ▼
            │                        ┌───────────────┐
            │                        │ json_to_asp   │
            │                        │  (→ ASP)      │
            │                        └───────┬───────┘
            │                                │
            │                                ▼
            │                        ┌───────────────┐
            │                        │    Clingo     │
            │                        │  (Reasoner)   │
            │                        └───────┬───────┘
            │                                │
            │                                ▼
            │                        ┌───────────────┐
            │                        │ LLM Interpret │
            │                        │ (Violations)  │
            │                        └───────┬───────┘
            │                                │
            └───────────────┬────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   Combined    │
                    │    Report     │
                    └───────────────┘
```

Execution Modes
---------------

- **llm**: Only run LLM direct linting (faster, but less rigorous)
- **logic**: Only run logic-based linting (more rigorous, requires structuring)
- **both**: Run both approaches and combine results (default, most thorough)

LLM Backend Support
-------------------

The script supports multiple LLM backends:

1. **openai**: OpenAI-compatible APIs (OpenAI, llamafile, ollama, vLLM, etc.)
2. **gemini**: Google's Gemini API with native support for thinking budget
3. **guidance**: Microsoft's guidance library for constrained JSON generation

Output
------

Results are:
1. Printed to stdout as JSON (current run only)
2. Appended to `output.json` with full execution details for debugging

The output.json file contains complete history including:
- All prompts sent to LLMs
- Raw responses received
- Generated ASP facts and rules
- Configuration used
- Timing information

Usage Examples
--------------

```bash
# Basic usage with local LLM
python scripts/story_lint.py story.txt

# With Gemini API
python scripts/story_lint.py \\
    --llm-backend gemini \\
    --llm-model gemini-2.5-flash \\
    --llm-api-key "$GEMINI_API_KEY" \\
    --struct-backend gemini \\
    --struct-model gemini-2.5-flash \\
    --struct-api-key "$GEMINI_API_KEY" \\
    story.txt

# Mock mode (no LLM calls, for testing)
python scripts/story_lint.py --mock --mock-llm story.txt
```

Author: Research Project - Narrative Evaluation
License: [Specify License]
"""

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Import our custom modules for story structuring and ASP conversion
from json_to_asp import json_to_asp
from llm_structurer import structure_story

# Import incremental learning modules (optional - graceful fallback)
try:
    from ilasp_learner import ILASPLearner, StoryKnowledge
    ILASP_AVAILABLE = True
except ImportError:
    ILASP_AVAILABLE = False

try:
    from llm_server import LlamafileServer, MODELS as LLAMAFILE_MODELS
    LLAMAFILE_AVAILABLE = True
except ImportError:
    LLAMAFILE_AVAILABLE = False


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

# This prompt is used for direct LLM linting - asking the LLM to find errors
# in the story without going through the formal logic pipeline. It's designed
# to catch subtle, contextual issues that might be missed by formal rules.
LLM_LINT_PROMPT = """You are a narrative linting assistant. Analyze the story for inconsistencies and subtle errors.

Focus on these 5 categories of errors:

1. CAUSALITY: Chekhov's gun violations (introduced elements never used), unexplained effects, events without proper causes, missing preconditions for actions.

2. COHERENCE: Semantic incorrectness, logical impossibilities (dead characters acting, eating inedible objects), physical trait violations (blind character reading).

3. TEMPORAL: Time paradoxes, events happening in impossible order, duration violations, simultaneous events that can't overlap.

4. LOCATION: Characters in two places at once, instant travel between distant locations, interacting with objects/people in different locations.

5. EMOTIONAL: Character actions contradicting their relationships (harming loved ones without reason, helping enemies), emotional state mismatches with behavior.

Return ONLY valid JSON. Do not include reasoning, preambles, or markdown. If you need to think, do it silently.
If you output a <think>...</think> block, place the JSON object after it and output nothing else.

Schema (strict):
{{
  "error_count": integer,
  "errors": [{{
    "id": "e1",
    "category": "causality|coherence|temporal|location|emotional",
    "description": "detailed description of the error",
    "story_fragments": ["relevant quote from the story showing the error"]
  }}]
}}
Ensure error_count equals the number of errors. Each error MUST have a category from the 5 options above.
Include the exact story fragments (quotes) that demonstrate the error.

Story:
\"\"\"
{story}
\"\"\"
"""


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def log(msg):
    """
    Log a message to stderr with a prefix for easy identification.
    
    All logging goes to stderr so that stdout remains clean for JSON output.
    This allows piping the JSON output to other tools while still seeing
    progress messages.
    
    Args:
        msg: The message to log (will be prefixed with [story_lint])
    """
    sys.stderr.write(f"[story_lint] {msg}\n")


def request_with_retry(fn, retries, backoff_seconds):
    """
    Execute a function with exponential backoff retry on transient errors.
    
    This is essential for production use with LLM APIs, which often have
    rate limits (HTTP 429) or temporary unavailability (HTTP 503).
    
    The backoff strategy is exponential: first retry waits backoff_seconds,
    second waits 2*backoff_seconds, third waits 4*backoff_seconds, etc.
    
    Args:
        fn: A callable that may raise urllib.error.HTTPError
        retries: Maximum number of retry attempts
        backoff_seconds: Initial backoff time (doubles each retry)
        
    Returns:
        The return value of fn() if successful
        
    Raises:
        urllib.error.HTTPError: If all retries are exhausted or error is not retryable
    """
    attempt = 0
    while True:
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            # Only retry on rate limit (429) or service unavailable (503)
            if exc.code not in (429, 503) or attempt >= retries:
                raise
            sleep_for = backoff_seconds * (2**attempt)
            log(f"HTTP {exc.code} received, retrying in {sleep_for}s (attempt {attempt + 1}/{retries})")
            time.sleep(sleep_for)
            attempt += 1


def strip_think(text):
    """
    Remove <think>...</think> blocks from LLM output.
    
    Some LLMs (especially those fine-tuned for reasoning) output their
    internal reasoning in <think> tags before providing the actual answer.
    This function strips those blocks to get the clean response.
    
    Args:
        text: Raw LLM output that may contain <think> blocks
        
    Returns:
        Text with <think>...</think> blocks removed
    """
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1 and end > start:
        return text[:start] + text[end + len("</think>") :]
    return text


def sanitize_json_string(text):
    """
    Sanitize a JSON string by fixing common LLM output issues.
    
    LLMs often produce JSON with:
    - Unescaped control characters inside strings
    - Literal newlines inside string values
    - Invalid escape sequences
    
    This function attempts to fix these issues while preserving valid JSON.
    
    Args:
        text: Raw JSON text that may have issues
        
    Returns:
        Sanitized JSON string
    """
    import re
    
    # First, handle control characters that appear inside string values
    # We need to be careful to only fix characters inside strings, not structural JSON
    
    result = []
    in_string = False
    escape_next = False
    
    for i, ch in enumerate(text):
        if escape_next:
            # Previous char was backslash - check if this is a valid escape
            if ch in 'nrtbf\\"/' or ch == 'u':
                result.append(ch)
            elif ch == '\n':
                # Literal newline after backslash - convert to \n
                result.append('n')
            else:
                # Invalid escape - just keep the character
                result.append(ch)
            escape_next = False
            continue
            
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            continue
            
        if ch == '"' and not escape_next:
            in_string = not in_string
            result.append(ch)
            continue
            
        if in_string:
            # Inside a string - escape control characters
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            elif ord(ch) < 32:
                # Other control characters - use unicode escape
                result.append(f'\\u{ord(ch):04x}')
            else:
                result.append(ch)
        else:
            # Outside string - keep as-is (structural JSON)
            result.append(ch)
    
    return ''.join(result)


def extract_json(text):
    """
    Extract a JSON object from text that may contain other content.
    
    LLMs sometimes include explanatory text before or after the JSON.
    This function finds and extracts just the JSON object by matching
    balanced braces.
    
    Algorithm:
    1. If text starts and ends with {}, return as-is
    2. Otherwise, find first { and track brace depth
    3. Return substring from first { to matching }
    
    Args:
        text: Text that should contain a JSON object somewhere
        
    Returns:
        The extracted JSON string, or None if no valid JSON object found
    """
    text = text.strip()
    # Best case: text is already just JSON
    if text.startswith("{") and text.endswith("}"):
        return text
    # Find the start of JSON
    start = text.find("{")
    if start == -1:
        return None
    # Track brace depth to find matching closing brace
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def is_local_server(base_url):
    """
    Check if a URL points to a local server.
    
    This is used to determine whether to:
    1. Skip authentication (local servers often don't need it)
    2. Skip response_format parameter (llamafile doesn't support it)
    
    Args:
        base_url: The API base URL to check
        
    Returns:
        True if the URL appears to be a local server
    """
    if not base_url:
        return False
    return "localhost" in base_url or "127.0.0.1" in base_url or "0.0.0.0" in base_url


# =============================================================================
# LLM API FUNCTIONS
# =============================================================================

def call_openai_json(
    prompt,
    model,
    base_url,
    api_key,
    temperature=0.2,
    no_auth=False,
    use_response_format=True,
    timeout=60,
    max_tokens=None,
):
    """
    Call an OpenAI-compatible API endpoint for JSON generation.
    
    This function works with:
    - OpenAI's official API
    - Local servers (llamafile, ollama, vLLM, LM Studio)
    - OpenAI-compatible cloud services (Together AI, Anyscale, etc.)
    
    The function automatically:
    - Disables response_format for local servers (often unsupported)
    - Handles authentication based on no_auth flag
    - Parses the response to extract the generated content
    
    Args:
        prompt: The user prompt to send
        model: Model identifier (e.g., "gpt-4o", "llama-3.1-8b")
        base_url: API base URL (e.g., "https://api.openai.com/v1")
        api_key: API key for authentication
        temperature: Sampling temperature (0.0 = deterministic)
        no_auth: If True, skip Authorization header
        use_response_format: If True, request JSON mode (when supported)
        timeout: Request timeout in seconds
        max_tokens: Maximum tokens to generate (None = model default)
        
    Returns:
        The generated text content from the LLM
        
    Raises:
        urllib.error.HTTPError: On API errors
        json.JSONDecodeError: If response is not valid JSON
        KeyError: If response structure is unexpected
    """
    log("Preparing OpenAI-compatible request for LLM lint.")
    url = base_url.rstrip("/") + "/chat/completions"
    log(f"POST {url} model={model} temperature={temperature} no_auth={no_auth}")
    
    # Build the request payload following OpenAI's chat completion format
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            # System message sets the assistant's behavior
            {"role": "system", "content": "You are a careful JSON-only responder."},
            # User message contains the actual prompt
            {"role": "user", "content": prompt},
        ],
    }
    
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
        
    # response_format forces JSON output but isn't supported by all servers
    # Local servers like llamafile typically don't support it
    if use_response_format and not is_local_server(base_url):
        payload["response_format"] = {"type": "json_object"}
        
    # Encode and send the request
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if not no_auth and api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
        
    log("Sending request...")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    log("Received response.")
    
    # Parse response and extract the generated content
    obj = json.loads(body)
    return obj["choices"][0]["message"]["content"]


def call_gemini_json(
    prompt,
    model,
    base_url,
    api_key,
    temperature=0.2,
    timeout=60,
    max_tokens=None,
    retries=3,
    backoff_seconds=5,
    thinking_budget=0,
):
    """
    Call Google's Gemini API for JSON generation.
    
    Gemini has a different API format than OpenAI, so this function handles
    the translation. It also supports Gemini-specific features like:
    - Thinking budget (for reasoning models)
    - Native JSON mode via responseMimeType
    
    The function automatically handles:
    - Model name normalization (strips "models/" prefix if present)
    - API key authentication (passed as query parameter, not header)
    - Fallback if thinkingConfig is rejected (some models don't support it)
    
    Args:
        prompt: The user prompt to send
        model: Model identifier (e.g., "gemini-2.5-flash", "gemini-pro")
        base_url: API base URL (typically "https://generativelanguage.googleapis.com/v1beta")
        api_key: Gemini API key
        temperature: Sampling temperature
        timeout: Request timeout in seconds
        max_tokens: Maximum output tokens
        retries: Number of retry attempts on transient errors
        backoff_seconds: Initial backoff time for retries
        thinking_budget: Token budget for model's internal reasoning (0 = disabled)
        
    Returns:
        The generated text content from Gemini
        
    Raises:
        SystemExit: If API key is missing or response is invalid
        urllib.error.HTTPError: On API errors
    """
    if not api_key:
        raise SystemExit("Missing GEMINI_API_KEY or --llm-api-key.")
        
    # Normalize model name (remove "models/" prefix if present)
    if model.startswith("models/"):
        model = model[len("models/") :]
        
    # Gemini uses generateContent endpoint with API key as query parameter
    url = base_url.rstrip("/") + f"/models/{model}:generateContent?key={api_key}"
    
    # Build Gemini-format payload
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    
    if max_tokens is not None:
        payload["generationConfig"]["maxOutputTokens"] = max_tokens
        
    # Request JSON output format
    payload["generationConfig"]["responseMimeType"] = "application/json"
    
    # Thinking budget allows the model to "think" internally before responding
    # This can improve quality for complex tasks but uses more tokens
    if thinking_budget is not None:
        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": thinking_budget}
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    
    def do_request():
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    try:
        body = request_with_retry(do_request, retries=retries, backoff_seconds=backoff_seconds)
    except urllib.error.HTTPError as exc:
        # Some Gemini models don't support thinkingConfig - retry without it
        if exc.code == 400 and "thinkingConfig" in payload.get("generationConfig", {}):
            log("Gemini thinkingConfig rejected, retrying without it.")
            payload["generationConfig"].pop("thinkingConfig", None)
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            body = request_with_retry(do_request, retries=retries, backoff_seconds=backoff_seconds)
        else:
            raise
            
    # Parse Gemini's response format
    obj = json.loads(body)
    candidates = obj.get("candidates") or []
    if not candidates:
        raise SystemExit("Gemini response missing candidates.")
        
    # Extract text from the nested parts structure
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text:
        raise SystemExit("Gemini response missing text content.")
    return text


def call_guidance_json(prompt, model, api_key, base_url=None, no_auth=False, timeout=60, max_tokens=None):
    """
    Call an LLM using Microsoft's guidance library for constrained generation.
    
    Guidance allows defining a JSON schema that the LLM must follow, ensuring
    valid JSON output without relying on the model to self-constrain.
    
    This is particularly useful for:
    - Models that struggle with JSON formatting
    - Cases where valid JSON structure is critical
    - Reducing parsing errors and retries
    
    Args:
        prompt: The user prompt
        model: Model identifier
        api_key: API key
        base_url: Optional custom API endpoint
        no_auth: If True, use "local" as API key placeholder
        timeout: Request timeout
        max_tokens: Maximum tokens to generate
        
    Returns:
        Generated JSON as a string
        
    Raises:
        SystemExit: If guidance is not installed
    """
    try:
        import guidance
    except ImportError as exc:
        raise SystemExit("guidance is not installed. Install it or use --llm-backend openai.") from exc

    if no_auth and not api_key:
        api_key = "local"
        
    kwargs = {"model": model, "api_key": api_key, "timeout": timeout, "max_retries": 0}
    if base_url:
        kwargs["base_url"] = base_url
        
    try:
        llm = guidance.models.OpenAI(**kwargs)
    except TypeError:
        kwargs.pop("base_url", None)
        llm = guidance.models.OpenAI(**kwargs)
        
    # Define the JSON schema that output must conform to
    schema = {
        "type": "object",
        "required": ["error_count", "errors"],
        "properties": {
            "error_count": {"type": "integer"},
            "errors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "description"],
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
        },
    }

    def run_with_schema(schema_value):
        """Execute guidance program with optional schema constraint."""
        @guidance.guidance(dedent=False)
        def program(lm, user_prompt, schema, max_tokens):
            with guidance.system():
                lm += "You are a careful JSON-only responder."
            with guidance.user():
                lm += user_prompt
            with guidance.assistant():
                if schema is None:
                    lm += guidance.json(name="json_out", max_tokens=max_tokens)
                else:
                    lm += guidance.json(name="json_out", schema=schema, max_tokens=max_tokens)
            return lm

        return program(user_prompt=prompt, schema=schema_value, max_tokens=max_tokens)(llm)

    try:
        result = run_with_schema(schema)
    except Exception as exc:
        log(f"Guidance schema failed, retrying without schema: {exc}")
        try:
            result = run_with_schema(None)
        except Exception as exc2:
            log(f"Guidance failed, falling back to plain request: {exc2}")
            # Fall back to regular OpenAI call if guidance fails
            return call_openai_json(
                prompt,
                model,
                base_url,
                api_key,
                temperature=0.0,
                no_auth=no_auth,
                use_response_format=False,
                timeout=timeout,
                max_tokens=max_tokens,
            )

    json_out = result["json_out"]
    if isinstance(json_out, str):
        return json_out
    return json.dumps(json_out)


# =============================================================================
# RESPONSE PARSING
# =============================================================================

def parse_llm_lint(content):
    """
    Parse and validate the LLM's lint response.
    
    This function:
    1. Extracts JSON from the response (handling wrapper text)
    2. Strips <think> blocks if present
    3. Sanitizes control characters inside strings
    4. Validates required fields (error_count, errors)
    5. Normalizes the error_count to match actual error list length
    
    Args:
        content: Raw LLM response text
        
    Returns:
        Parsed and validated dictionary with error_count and errors
        
    Raises:
        SystemExit: If response cannot be parsed or lacks required fields
    """
    log("Parsing LLM lint JSON.")
    
    # Try to extract JSON, stripping <think> blocks if needed
    raw_json = extract_json(content)
    if raw_json is None:
        raw_json = extract_json(strip_think(content))
    if raw_json is None:
        snippet = content.strip().replace("\n", " ")[:300]
        log(f"LLM lint raw output (truncated): {snippet}")
        raise SystemExit("LLM lint output did not contain a JSON object.")
    
    # Try to parse JSON, sanitizing if first attempt fails
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        log(f"JSON parse error: {e}. Attempting sanitization.")
        try:
            sanitized = sanitize_json_string(raw_json)
            data = json.loads(sanitized)
            log("JSON parsed after sanitization.")
        except json.JSONDecodeError as e2:
            # Log the problematic area for debugging
            log(f"Sanitization failed: {e2}")
            # Try to show context around the error
            if hasattr(e2, 'pos') and e2.pos:
                start = max(0, e2.pos - 50)
                end = min(len(raw_json), e2.pos + 50)
                context = raw_json[start:end]
                log(f"Error context: ...{context!r}...")
            raise SystemExit(f"LLM lint JSON parse failed: {e2}")
    
    # Validate required fields
    if "errors" not in data or "error_count" not in data:
        raise SystemExit("LLM lint output missing required keys.")
    if not isinstance(data["errors"], list):
        raise SystemExit("LLM lint output errors must be a list.")
        
    # Normalize error_count to match actual list length
    # (LLMs sometimes get the count wrong)
    data["error_count"] = int(data["error_count"])
    if data["error_count"] != len(data["errors"]):
        data["error_count"] = len(data["errors"])
        
    return data


# =============================================================================
# VIOLATION INTERPRETATION
# =============================================================================

# Prompt for converting raw ASP violations into human-readable explanations
# Enhanced to include story fragments for traceability
VIOLATION_INTERPRET_PROMPT = """You are a helpful assistant that explains logic violations found in a story.
Given a list of raw ASP (Answer Set Programming) violation atoms and the original story text,
provide a human-readable description for each violation AND include the exact story fragments that caused it.

The violations are categorized into 5 types:
1. CAUSALITY: Chekhov's gun, unexplained effects, missing causes
2. COHERENCE: Semantic errors, dead agents, physical impossibilities
3. TEMPORAL: Time ordering violations, duration errors
4. LOCATION: Ubiquity (two places at once), impossible travel
5. EMOTIONAL: Relationship-behavior mismatches

Return ONLY valid JSON. Do not include reasoning, preambles, or markdown.
If you output a <think>...</think> block, place the JSON object after it and output nothing else.

Schema (strict):
{{
  "error_count": integer,
  "errors": [{{
    "id": "logic_1",
    "category": "causality|coherence|temporal|location|emotional",
    "description": "human readable explanation",
    "violation_type": "the specific violation type from the ASP atom",
    "involved_entities": ["list of characters, objects, or events involved"],
    "story_fragments": ["EXACT quote from the story that shows this violation"],
    "related_fragments": ["other relevant quotes if the error involves multiple parts"]
  }}]
}}

CRITICAL: The story_fragments field MUST contain the EXACT word-for-word quotes from the original story
that demonstrate the error. This is essential for verification. Look for the relevant passages
based on the entities and events mentioned in the violation.

Ensure the category matches the violation type:
- chekhov_gun, uncaused_event, effect_without_cause, precondition_missing -> causality
- dead_agent, non_edible_food, physical_impossibility, focus_overlap -> coherence  
- circular_time, negative_duration, explicit_order_violated -> temporal
- ubiquity, proximity_required, impossible_travel -> location
- harm_loved, help_enemy, approach_feared, misplaced_trust, state_action_mismatch -> emotional

Original story text:
\"\"\"
{story}
\"\"\"

ASP facts extracted from story:
{asp_facts}

Raw violations found by Clingo:
{violations}
"""


def interpret_violations_with_llm(violations, args, story_text=None, asp_facts=None):
    """
    Use LLM to interpret raw Clingo violations into human-readable text.
    
    ENHANCED: Now includes story fragments in the output for traceability.
    
    Raw violations from Clingo look like:
        violation(non_edible_food, e14)
        violation(dead_agent, e5)
    
    This function asks the LLM to explain what these mean in context AND
    to extract the exact story fragments that caused each violation.
    
    Args:
        violations: List of violation tuples from Clingo, e.g., [["non_edible_food", "e14"]]
        args: Parsed command-line arguments (for LLM configuration)
        story_text: Original story text for fragment extraction
        asp_facts: Generated ASP facts (for context)
        
    Returns:
        Dictionary with:
            - error_count: Number of violations
            - errors: List of {id, description, story_fragments, ...} objects
            - raw_violations: Original violation strings
            - interpretation: Details about the LLM call
    """
    if not violations:
        return {"error_count": 0, "errors": [], "raw_violations": [], "interpretation": None}
    
    # Convert violation tuples to readable strings
    raw_strs = [f"violation({', '.join(v)})" for v in violations]
    
    # Build prompt with story text and ASP facts for fragment extraction
    prompt = VIOLATION_INTERPRET_PROMPT.format(
        violations="\n".join(raw_strs),
        story=story_text[:3000] if story_text else "(story text not available)",
        asp_facts=asp_facts[:2000] if asp_facts else "(ASP facts not available)"
    )
    
    log("Calling LLM to interpret logic violations with story fragments.")
    raw_response = None
    
    try:
        # Call appropriate backend with temperature=0 for determinism
        if args.llm_backend == "gemini":
            raw_response = call_gemini_json(
                prompt,
                args.llm_model,
                args.llm_base_url,
                args.llm_api_key,
                temperature=0.0,
                timeout=args.llm_timeout,
                max_tokens=2048,  # Increased for story fragments
                retries=args.llm_retries,
                backoff_seconds=args.llm_backoff,
                thinking_budget=0,
            )
        else:
            raw_response = call_openai_json(
                prompt,
                args.llm_model,
                args.llm_base_url,
                args.llm_api_key,
                no_auth=args.llm_no_auth,
                temperature=0.0,
                timeout=args.llm_timeout,
                max_tokens=2048,  # Increased for story fragments
            )
            
        # Parse the response
        raw_json = extract_json(raw_response)
        if raw_json is None:
            raw_json = extract_json(strip_think(raw_response))
        if raw_json:
            data = json.loads(raw_json)
            data["raw_violations"] = raw_strs
            data["interpretation"] = {
                "prompt": prompt[:500] + "...",  # Truncate for storage
                "raw_response": raw_response,
                "model": args.llm_model,
                "backend": args.llm_backend,
            }
            
            # Ensure all errors have story_fragments field
            for error in data.get("errors", []):
                if "story_fragments" not in error:
                    error["story_fragments"] = []
                if "related_fragments" not in error:
                    error["related_fragments"] = []
            
            return data
    except Exception as exc:
        log(f"LLM interpretation failed: {exc}")
    
    # Fallback: return raw violations with attempt to extract fragments from ASP
    log("Using fallback: raw violations with basic fragment extraction.")
    errors = []
    for i, v in enumerate(violations, 1):
        error = {
            "id": f"logic_{i}",
            "description": f"violation({', '.join(v)})",
            "violation_type": v[0] if v else "unknown",
            "category": _infer_category_from_violation(v[0] if v else ""),
            "story_fragments": [],
            "related_fragments": [],
            "involved_entities": v[1:] if len(v) > 1 else []
        }
        
        # Try to extract fragments from ASP facts if available
        if asp_facts and len(v) > 1:
            for entity in v[1:]:
                # Look for story_fragment facts mentioning this entity
                import re
                fragment_match = re.search(
                    rf'story_fragment\({entity},\s*"([^"]+)"\)',
                    asp_facts
                )
                if fragment_match:
                    error["story_fragments"].append(fragment_match.group(1))
        
        errors.append(error)
    
    return {
        "error_count": len(errors),
        "errors": errors,
        "raw_violations": raw_strs,
        "interpretation": {
            "prompt": prompt[:500] + "...",
            "raw_response": raw_response,
            "error": "LLM interpretation failed, using fallback",
        },
    }


def _infer_category_from_violation(violation_type: str) -> str:
    """Infer error category from violation type string."""
    vtype = violation_type.lower()
    
    if any(kw in vtype for kw in ['chekhov', 'cause', 'effect', 'precondition']):
        return 'causality'
    elif any(kw in vtype for kw in ['dead', 'edible', 'physical', 'focus']):
        return 'coherence'
    elif any(kw in vtype for kw in ['time', 'duration', 'order', 'temporal']):
        return 'temporal'
    elif any(kw in vtype for kw in ['ubiquity', 'proximity', 'travel', 'location']):
        return 'location'
    elif any(kw in vtype for kw in ['harm', 'help', 'enemy', 'love', 'fear', 'trust', 'emotion']):
        return 'emotional'
    
    return 'coherence'  # Default


def format_logic_violations(violations):
    """
    Simple fallback formatter for mock mode (no LLM call).
    
    When running with --no-interpret or in testing, this provides
    raw violation output without LLM interpretation.
    
    Args:
        violations: List of violation tuples from Clingo
        
    Returns:
        Dictionary with error_count, errors, and raw_violations
    """
    log(f"Formatting {len(violations)} logic violations (fallback mode).")
    raw_strs = [f"violation({', '.join(v)})" for v in violations]
    errors = [{"id": f"logic_{i}", "description": v} for i, v in enumerate(raw_strs, 1)]
    return {"error_count": len(errors), "errors": errors, "raw_violations": raw_strs}


# =============================================================================
# MAIN LINTING FUNCTIONS
# =============================================================================

def logic_lint(story_text, args):
    """
    Perform logic-based linting using LLM structuring + ASP reasoning.
    
    This is the main logic pipeline:
    
    1. **Structure**: Use LLM to convert story text to structured JSON
       - Characters, objects, locations
       - Events with temporal information
       - Fluents (time-varying properties)
       - Character traits
       
    2. **Convert**: Transform JSON to ASP facts using json_to_asp module
       - character(hansel). object(bread). event(e1). etc.
       
    3. **Reason**: Load ASP facts + rules into Clingo solver
       - rules/base.lp contains consistency rules
       - Clingo finds all violations
       
    4. **Interpret**: Use LLM to explain violations in natural language
       - violation(non_edible_food, e14) → "Tried to eat non-edible cottage"
    
    Args:
        story_text: The narrative text to analyze
        args: Parsed command-line arguments
        
    Returns:
        Dictionary with:
            - error_count: Number of violations found
            - errors: List of {id, description} objects
            - raw_violations: Original Clingo output
            - details: Full debugging information
    """
    log("Starting logic-based lint flow.")
    
    # Initialize details dictionary for comprehensive output
    details = {
        "structurer": {},
        "asp_facts": None,
        "asp_rules": None,
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        facts_path = tmpdir / "facts.lp"

        # ===== STEP 1: Structure the story via LLM =====
        if getattr(args, 'mock', False):
            # Mock mode: use pre-made JSON for testing
            log("Using mock structured data from examples/story.json.")
            structured_data = json.loads(Path("examples/story.json").read_text())
            details["structurer"] = {
                "mock": True,
                "parsed": structured_data,
            }
        else:
            # Real mode: call LLM to structure the story
            log("Structuring story via LLM -> JSON.")
            struct_result = structure_story(
                story_text,
                model=args.struct_model,
                base_url=args.struct_base_url,
                api_key=args.struct_api_key,
                no_auth=args.struct_no_auth,
                backend=args.struct_backend,
                timeout=args.struct_timeout,
                max_tokens=args.struct_max_tokens,
                retries=args.struct_retries,
                backoff=args.struct_backoff,
                thinking_budget=args.struct_thinking_budget,
                return_details=True,  # Get full details for output.json
            )
            structured_data = struct_result["parsed"]
            details["structurer"] = struct_result
        log("Story structured successfully.")

        # ===== STEP 2: Convert JSON to ASP facts =====
        log("Converting structured JSON -> ASP facts.")
        asp_facts = json_to_asp(structured_data, include_candidates=args.include_candidates)
        facts_path.write_text(asp_facts)
        details["asp_facts"] = asp_facts
        log(f"ASP facts written to {facts_path}.")

        # Load ASP rules for reference in output
        # Try enhanced rules first, fall back to base.lp
        rules_path = Path("rules/general_narrative.lp")
        if not rules_path.exists():
            rules_path = Path("rules/base.lp")
        if rules_path.exists():
            details["asp_rules"] = rules_path.read_text()
            details["asp_rules_file"] = str(rules_path)

        # ===== STEP 3: Run Clingo reasoner =====
        log("Running clingo reasoner.")
        violations = []
        try:
            import clingo
            
            # Create Clingo control object with warnings suppressed
            ctl = clingo.Control(["--warn=none"])
            
            # Load the reasoning rules and generated facts
            # Use enhanced rules if available
            rules_file = Path("rules/general_narrative.lp")
            if not rules_file.exists():
                rules_file = Path("rules/base.lp")
            ctl.load(str(rules_file.absolute()))
            ctl.load(str(facts_path))
            
            # Ground the program (instantiate all rules with concrete values)
            ctl.ground([("base", [])])
            
            # Solve and collect all violation atoms
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "violation":
                            # Extract violation arguments as strings
                            parts = [str(arg) for arg in atom.arguments]
                            violations.append(parts)
                            
            log(f"Found {len(violations)} violations via clingo Python API.")
            
        except ImportError:
            raise SystemExit("clingo Python module not available. Install it with: pip install clingo")
        except RuntimeError as exc:
            # Log the generated facts for debugging ASP syntax errors
            log(f"Clingo parsing failed. ASP facts:\n{asp_facts[:2000]}")
            raise SystemExit(f"Clingo parsing failed: {exc}")
        
        # ===== STEP 4: Interpret violations =====
        if getattr(args, 'no_interpret', False):
            result = format_logic_violations(violations)
        else:
            # Pass story_text and asp_facts for story fragment extraction
            result = interpret_violations_with_llm(
                violations, args, 
                story_text=story_text, 
                asp_facts=asp_facts
            )
        
        # Add all the details to result for comprehensive output
        result["details"] = details
        return result


def llm_lint(story_text, args):
    """
    Perform direct LLM-based linting without formal logic.
    
    This approach asks the LLM to directly analyze the story for
    inconsistencies. It's faster than the logic pipeline and can catch
    subtle, contextual issues that formal rules might miss.
    
    However, it can also:
    - Hallucinate non-existent errors
    - Miss errors that formal logic would catch
    - Be inconsistent across runs
    
    Best used in combination with logic_lint for comprehensive coverage.
    
    Args:
        story_text: The narrative text to analyze
        args: Parsed command-line arguments
        
    Returns:
        Dictionary with error_count, errors, and details
    """
    log("Starting LLM-only lint flow.")
    
    # Mock mode for testing
    if getattr(args, 'mock_llm', False):
        log("Using mock LLM lint response (--mock-llm).")
        return {
            "error_count": 1,
            "errors": [{"id": "mock_1", "description": "Mock LLM error for testing."}],
            "details": {"mock": True},
        }
        
    # Build the prompt with the story
    prompt = LLM_LINT_PROMPT.format(story=story_text.strip())
    raw_response = None
    
    def fetch(max_tokens):
        """Inner function to call LLM with given max_tokens."""
        nonlocal raw_response
        if args.llm_backend == "gemini":
            raw_response = call_gemini_json(
                prompt,
                args.llm_model,
                args.llm_base_url,
                args.llm_api_key,
                temperature=args.llm_temperature,
                timeout=args.llm_timeout,
                max_tokens=max_tokens,
                retries=args.llm_retries,
                backoff_seconds=args.llm_backoff,
                thinking_budget=args.llm_thinking_budget,
            )
            return raw_response
        if args.llm_backend == "guidance":
            raw_response = call_guidance_json(
                prompt,
                args.llm_model,
                args.llm_api_key,
                base_url=args.llm_base_url,
                no_auth=args.llm_no_auth,
                timeout=args.llm_timeout,
                max_tokens=max_tokens,
            )
            return raw_response
        # Default: OpenAI-compatible
        raw_response = call_openai_json(
            prompt,
            args.llm_model,
            args.llm_base_url,
            args.llm_api_key,
            no_auth=args.llm_no_auth,
            temperature=args.llm_temperature,
            timeout=args.llm_timeout,
            max_tokens=max_tokens,
        )
        return raw_response

    # Try with default max_tokens, retry with more if parsing fails
    try:
        content = fetch(args.llm_max_tokens)
        result = parse_llm_lint(content)
    except SystemExit as exc:
        log(f"LLM lint parse failed, retrying with higher max_tokens: {exc}")
        try:
            content = fetch(max(args.llm_max_tokens * 2, 2048))
            result = parse_llm_lint(content)
        except SystemExit as exc2:
            log(f"LLM lint parse failed again, returning empty result: {exc2}")
            result = {
                "error_count": 0,
                "errors": [],
                "parse_error": str(exc2)
            }
    
    # Add full details for debugging
    result["details"] = {
        "prompt": prompt,
        "raw_response": raw_response,
        "model": args.llm_model,
        "backend": args.llm_backend,
    }
    return result


# =============================================================================
# UTILITY FUNCTIONS FOR CONFIGURATION
# =============================================================================

def render_report(title, result):
    """
    Render a human-readable report from lint results.
    
    Args:
        title: Report title (e.g., "LLM Lint Results")
        result: Dictionary with error_count and errors
        
    Returns:
        Formatted string report
    """
    log(f"Rendering report for {title}.")
    lines = [f"{title}:"]
    lines.append(f"Total errors: {result['error_count']}")
    for err in result["errors"]:
        lines.append(f"- {err['description']}")
    return "\n".join(lines)


def infer_no_auth(base_url, flag_value):
    """
    Infer whether to skip authentication based on URL.
    
    Local servers typically don't need authentication, so we automatically
    enable --no-auth for localhost URLs unless explicitly overridden.
    
    Args:
        base_url: The API base URL
        flag_value: Explicit --no-auth flag value
        
    Returns:
        True if authentication should be skipped
    """
    if flag_value:
        return True
    if not base_url:
        return False
    return "localhost" in base_url or "127.0.0.1" in base_url or "0.0.0.0" in base_url


def resolve_model_id_openai(base_url, model, api_key, no_auth, timeout):
    """
    Resolve "auto" model ID by querying the OpenAI-compatible /models endpoint.
    
    When model is "auto", this function queries the API to find available
    models and uses the first one. This is useful for local servers where
    the model name might not be known in advance.
    
    Args:
        base_url: API base URL
        model: Model ID or "auto"
        api_key: API key
        no_auth: Whether to skip authentication
        timeout: Request timeout
        
    Returns:
        Resolved model ID
    """
    if model not in ("auto", "llama"):
        return model
    if not base_url:
        return model
        
    models_url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(models_url)
    if not no_auth and api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
        
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log(f"Could not resolve model from {models_url}: {exc}")
        return model
        
    models = data.get("data") or []
    if models:
        model_id = models[0].get("id")
        if model_id:
            log(f"Resolved model id from {models_url}: {model_id}")
            return model_id
    return model


def resolve_model_id_gemini(base_url, model, api_key, timeout):
    """
    Resolve "auto" model ID by querying Google's Gemini API.
    
    Queries the /models endpoint and selects a preferred model from
    the available list (preferring newer flash models).
    
    Args:
        base_url: Gemini API base URL
        model: Model ID or "auto"
        api_key: Gemini API key
        timeout: Request timeout
        
    Returns:
        Resolved model ID
    """
    if model != "auto":
        return model
    if not api_key:
        return model
        
    models_url = base_url.rstrip("/") + f"/models?key={api_key}"
    log_url = base_url.rstrip("/") + "/models?key=***"  # Redacted for logging
    
    try:
        with urllib.request.urlopen(models_url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log(f"Could not resolve Gemini model from {log_url}: {exc}")
        return model
        
    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
    
    # Prefer newer flash models for speed
    preferred = [
        "models/gemini-2.0-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.5-flash",
    ]
    for name in preferred:
        if name in models:
            log(f"Resolved Gemini model id from {log_url}: {name}")
            return name
    if models:
        log(f"Resolved Gemini model id from {log_url}: {models[0]}")
        return models[0]
    return model


# =============================================================================
# INCREMENTAL LINTING (ILASP + Chapter-by-Chapter Learning)
# =============================================================================

def incremental_lint(story_path, args):
    """
    Perform incremental linting comparing LLM direct linting vs ILASP learning.
    
    This mode processes a story directory containing chapter files (000.txt, 001.txt, etc.)
    and runs TWO approaches in parallel for comparison:
    
    1. LLM Direct Linting: Ask LLM to find inconsistencies directly (per chapter)
    2. ILASP Incremental Learning: Learn rules from earlier chapters, check later ones
    
    KEY PRINCIPLE: COMPLETE ISOLATION
    Each run starts with a FRESH LLM server and FRESH ILASP learner.
    There is no state carryover between experiments.
    
    Workflow:
        For each chapter:
            - LLM: Direct analysis of chapter for inconsistencies
            - ILASP: Chapter 1 learns only, Chapter 2+ checks then learns
        Compare results at the end.
    
    Args:
        story_path: Path to directory containing chapter .txt files
        args: Parsed command-line arguments
        
    Returns:
        Dictionary with:
            - error_count: Total violations found (combined)
            - llm_errors: Errors found by LLM direct linting
            - ilasp_errors: Errors found by ILASP incremental learning
            - chapters: Per-chapter results with both approaches
            - knowledge_summary: Final accumulated ILASP knowledge
            - comparison: Summary comparing both approaches
    """
    log("Starting incremental lint: LLM vs ILASP comparison mode.")
    
    # Validate dependencies
    if not ILASP_AVAILABLE:
        raise SystemExit("ILASP learner module not available. Check ilasp_learner.py exists.")
    
    story_dir = Path(story_path)
    if not story_dir.is_dir():
        raise SystemExit(f"Incremental mode requires a directory of chapter files: {story_path}")
    
    # Get chapter files (sorted)
    chapter_files = sorted(story_dir.glob("*.txt"), key=lambda p: p.stem)
    if not chapter_files:
        raise SystemExit(f"No .txt chapter files found in {story_path}")
    
    log(f"Found {len(chapter_files)} chapter files in {story_path}")
    
    # Generate experiment ID
    experiment_id = args.experiment_id or f"{story_dir.parent.name}_{story_dir.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Initialize results (now tracking both LLM and ILASP)
    result = {
        "experiment_id": experiment_id,
        "story_dir": str(story_dir),
        "error_count": 0,  # Combined total
        "llm_errors": [],  # LLM direct linting errors
        "ilasp_errors": [],  # ILASP incremental learning errors
        "chapters": [],
        "knowledge_summary": {},
        "comparison": {},  # Summary comparing both approaches
    }
    
    # Create FRESH ILASP learner (isolated state)
    learner = ILASPLearner(experiment_id=experiment_id, verbose=True)
    
    # Start FRESH LLM server if using local llamafile
    llm_server = None
    if LLAMAFILE_AVAILABLE and args.llm_backend == "openai" and is_local_server(args.llm_base_url):
        try:
            log(f"Starting FRESH local LLM server: {args.local_llm}")
            llm_server = LlamafileServer(
                model=args.local_llm,
                port=args.local_llm_port,
                verbose=True,
                auto_start=True,
            )
            # Update base URL to use our fresh server
            args.llm_base_url = f"http://127.0.0.1:{args.local_llm_port}/v1"
            args.struct_base_url = args.llm_base_url
            log(f"LLM server ready at {args.llm_base_url}")
        except Exception as e:
            log(f"Could not start local LLM server: {e}")
            llm_server = None
    
    try:
        # Process each chapter with BOTH approaches
        for i, chapter_path in enumerate(chapter_files):
            chapter_num = i + 1
            log(f"\n{'='*60}")
            log(f"Processing chapter {chapter_num}: {chapter_path.name}")
            
            chapter_result = _process_chapter_incremental(
                chapter_path, chapter_num, learner, args
            )
            result["chapters"].append(chapter_result)
            
            # Accumulate LLM errors
            for error in chapter_result.get("llm_violations", []):
                result["llm_errors"].append({
                    "id": f"ch{chapter_num}_llm_{error.get('id', 'unknown')}",
                    "category": error.get("category", "llm_detected"),
                    "description": error.get("description", str(error)),
                    "chapter": chapter_num,
                    "chapter_file": chapter_path.name,
                    "severity": error.get("severity", "medium"),
                    "source": "llm_direct",
                })
            
            # Accumulate ILASP errors
            for violation in chapter_result.get("ilasp_violations", []):
                result["ilasp_errors"].append({
                    "id": f"ch{chapter_num}_ilasp_{violation.get('type', 'unknown')}",
                    "category": violation.get("category", "ilasp_detected"),
                    "description": violation.get("description", str(violation)),
                    "chapter": chapter_num,
                    "chapter_file": chapter_path.name,
                    "severity": violation.get("severity", "medium"),
                    "source": "ilasp_incremental",
                })
        
        # Get final knowledge summary
        result["knowledge_summary"] = learner.get_summary()
        
        # Build comparison summary
        result["error_count"] = len(result["llm_errors"]) + len(result["ilasp_errors"])
        result["comparison"] = _build_comparison_summary(result)
        
    finally:
        # ALWAYS stop the LLM server (ensures clean state for next experiment)
        if llm_server is not None:
            log("Stopping LLM server (cleaning state)...")
            try:
                llm_server.stop()
            except Exception as e:
                log(f"Error stopping server: {e}")
    
    log(f"\nIncremental lint complete:")
    log(f"  LLM direct: {len(result['llm_errors'])} errors")
    log(f"  ILASP incremental: {len(result['ilasp_errors'])} errors")
    log(f"  Combined total: {result['error_count']} errors")
    return result


def _process_chapter_incremental(chapter_path, chapter_num, learner, args):
    """
    Process a single chapter through BOTH LLM direct linting and ILASP learning.
    
    This runs two parallel analysis approaches:
    1. LLM Direct: Ask LLM to find inconsistencies in this chapter
    2. ILASP Incremental: Check against learned knowledge, then learn from chapter
    
    Args:
        chapter_path: Path to chapter file
        chapter_num: Chapter number (1-indexed)
        learner: ILASPLearner instance
        args: Command-line arguments
        
    Returns:
        Dictionary with chapter processing results from both approaches
    """
    result = {
        "chapter_num": chapter_num,
        "file": chapter_path.name,
        "llm_violations": [],   # LLM direct linting results
        "ilasp_violations": [], # ILASP incremental learning results
        "entities_found": 0,
        "events_found": 0,
    }
    
    # Read chapter text
    try:
        text = chapter_path.read_text(encoding="utf-8")
    except Exception as e:
        log(f"  Error reading file: {e}")
        result["error"] = str(e)
        return result
    
    # ========== APPROACH 1: LLM DIRECT LINTING ==========
    log(f"  [LLM] Running direct LLM linting...")
    try:
        if getattr(args, 'mock_llm', False):
            log("  [LLM] Using mock response.")
            llm_result = {"error_count": 0, "errors": []}
        else:
            llm_result = _llm_lint_chapter(text, chapter_num, args)
        
        result["llm_violations"] = llm_result.get("errors", [])
        log(f"  [LLM] Found {len(result['llm_violations'])} issues")
    except Exception as e:
        log(f"  [LLM] Direct linting failed: {e}")
        result["llm_error"] = str(e)
    
    # ========== APPROACH 2: ILASP INCREMENTAL LEARNING ==========
    log(f"  [ILASP] Running incremental learning...")
    
    # Structure text using LLM (needed for ILASP)
    try:
        if getattr(args, 'mock', False):
            log("  [ILASP] Using mock structured data.")
            structured = {
                "entities": {"characters": [], "objects": [], "locations": []},
                "events": [],
                "relationships": [],
                "traits": [],
                "fluents": [],
            }
        else:
            log(f"  [ILASP] Structuring chapter via LLM...")
            struct_result = structure_story(
                text,
                model=args.struct_model,
                base_url=args.struct_base_url,
                api_key=args.struct_api_key,
                no_auth=args.struct_no_auth,
                backend=args.struct_backend,
                timeout=args.struct_timeout,
                max_tokens=args.struct_max_tokens,
                retries=args.struct_retries,
                backoff=args.struct_backoff,
                thinking_budget=args.struct_thinking_budget,
                return_details=False,
            )
            structured = struct_result if isinstance(struct_result, dict) else struct_result.get("parsed", {})
    except Exception as e:
        log(f"  [ILASP] LLM structuring failed: {e}")
        # Fallback to simple structure
        structured = _simple_structure_text(text)
    
    result["entities_found"] = len(structured.get("entities", {}).get("characters", []))
    result["events_found"] = len(structured.get("events", []))
    
    # Process with ILASP learner (check + learn)
    ilasp_violations = learner.process_chapter(
        structured_json=structured,
        chapter_num=chapter_num,
        chapter_text=text,
    )
    
    result["ilasp_violations"] = ilasp_violations
    log(f"  [ILASP] Found {len(ilasp_violations)} violations, learned from chapter")
    
    # Summary for this chapter
    log(f"  Chapter {chapter_num} summary: LLM={len(result['llm_violations'])} ILASP={len(result['ilasp_violations'])}")
    
    return result


def _llm_lint_chapter(chapter_text, chapter_num, args):
    """
    Run direct LLM linting on a single chapter.
    
    Uses the same prompt structure as llm_lint() but adapted for per-chapter use.
    
    Args:
        chapter_text: Text content of the chapter
        chapter_num: Chapter number for context
        args: Command-line arguments
        
    Returns:
        Dictionary with error_count and errors list
    """
    # Build prompt for chapter-specific linting
    prompt = f"""Analyze this chapter (Chapter {chapter_num}) for narrative inconsistencies.

Look for:
1. Characters acting out of established character
2. Timeline inconsistencies
3. Location/spatial impossibilities
4. Objects appearing/disappearing without explanation
5. Contradictions with established facts

Chapter text:
{chapter_text.strip()}

Respond with JSON:
{{
  "error_count": <number>,
  "errors": [
    {{
      "id": "<unique_id>",
      "category": "<category>",
      "description": "<detailed description>",
      "severity": "low|medium|high",
      "evidence": "<quote from text>"
    }}
  ]
}}

If no errors found, return {{"error_count": 0, "errors": []}}"""

    raw_response = None
    
    try:
        if args.llm_backend == "gemini":
            raw_response = call_gemini_json(
                prompt,
                args.llm_model,
                args.llm_base_url,
                args.llm_api_key,
                temperature=args.llm_temperature,
                timeout=args.llm_timeout,
                max_tokens=args.llm_max_tokens,
                retries=args.llm_retries,
                backoff_seconds=args.llm_backoff,
                thinking_budget=args.llm_thinking_budget,
            )
        elif args.llm_backend == "guidance":
            raw_response = call_guidance_json(
                prompt,
                args.llm_model,
                args.llm_api_key,
                base_url=args.llm_base_url,
                no_auth=args.llm_no_auth,
                timeout=args.llm_timeout,
                max_tokens=args.llm_max_tokens,
            )
        else:
            # OpenAI-compatible
            raw_response = call_openai_json(
                prompt,
                args.llm_model,
                args.llm_base_url,
                args.llm_api_key,
                no_auth=args.llm_no_auth,
                temperature=args.llm_temperature,
                timeout=args.llm_timeout,
                max_tokens=args.llm_max_tokens,
            )
        
        # Parse the response
        result = parse_llm_lint(raw_response)
        return result
        
    except Exception as e:
        log(f"  [LLM] Chapter lint failed: {e}")
        return {"error_count": 0, "errors": [], "error": str(e)}


def _build_comparison_summary(result):
    """
    Build a summary comparing LLM direct linting vs ILASP incremental learning.
    
    This analyzes the errors found by each approach and categorizes them
    to help understand the strengths of each method.
    
    Args:
        result: The full incremental lint result dictionary
        
    Returns:
        Dictionary with comparison statistics and analysis
    """
    llm_errors = result.get("llm_errors", [])
    ilasp_errors = result.get("ilasp_errors", [])
    chapters = result.get("chapters", [])
    
    # Per-chapter breakdown
    chapter_breakdown = []
    for ch in chapters:
        chapter_breakdown.append({
            "chapter": ch.get("chapter_num", 0),
            "file": ch.get("file", ""),
            "llm_count": len(ch.get("llm_violations", [])),
            "ilasp_count": len(ch.get("ilasp_violations", [])),
        })
    
    # Categorize by severity
    llm_by_severity = {"high": 0, "medium": 0, "low": 0}
    for err in llm_errors:
        sev = err.get("severity", "medium").lower()
        if sev in llm_by_severity:
            llm_by_severity[sev] += 1
        else:
            llm_by_severity["medium"] += 1
    
    ilasp_by_severity = {"high": 0, "medium": 0, "low": 0}
    for err in ilasp_errors:
        sev = err.get("severity", "medium").lower()
        if sev in ilasp_by_severity:
            ilasp_by_severity[sev] += 1
        else:
            ilasp_by_severity["medium"] += 1
    
    # Categorize by error type/category
    llm_categories = {}
    for err in llm_errors:
        cat = err.get("category", "unknown")
        llm_categories[cat] = llm_categories.get(cat, 0) + 1
    
    ilasp_categories = {}
    for err in ilasp_errors:
        cat = err.get("category", "unknown")
        ilasp_categories[cat] = ilasp_categories.get(cat, 0) + 1
    
    # Summary statistics
    return {
        "llm_total": len(llm_errors),
        "ilasp_total": len(ilasp_errors),
        "combined_total": len(llm_errors) + len(ilasp_errors),
        "llm_by_severity": llm_by_severity,
        "ilasp_by_severity": ilasp_by_severity,
        "llm_categories": llm_categories,
        "ilasp_categories": ilasp_categories,
        "chapter_breakdown": chapter_breakdown,
        "analysis": {
            "llm_only_advantage": "Direct contextual analysis, catches subtle stylistic issues",
            "ilasp_only_advantage": "Logical consistency based on learned rules, no hallucination",
            "recommendation": "Use both for comprehensive coverage",
        },
    }


def _simple_structure_text(text):
    """Simple fallback text structuring without LLM."""
    import re
    
    entities = {"characters": [], "objects": [], "locations": []}
    events = []
    
    # Find speakers from dialogue patterns
    speakers = set()
    for match in re.finditer(r'"[^"]+"\s*(?:said|asked|replied|shouted)\s+(\w+)', text, re.I):
        speakers.add(match.group(1))
    for match in re.finditer(r'(\w+)\s+(?:said|asked|replied|shouted)\s*"', text, re.I):
        speakers.add(match.group(1))
    
    for speaker in speakers:
        entities["characters"].append({
            "id": f"char_{speaker.lower()}",
            "name": speaker,
        })
    
    return {
        "entities": entities,
        "events": events,
        "relationships": [],
        "traits": [],
        "fluents": [],
    }


def compare_incremental(original_dir, modified_dir, args):
    """
    Run TWO COMPLETELY ISOLATED incremental experiments and compare.
    
    Each experiment gets a FRESH LLM server that is killed after.
    The modified experiment knows NOTHING about the original.
    
    Runs BOTH LLM direct linting and ILASP learning on each story,
    then compares results to see which approach better detects the modifications.
    
    Args:
        original_dir: Path to original story directory
        modified_dir: Path to modified story directory
        args: Command-line arguments
        
    Returns:
        Comparison result dictionary with LLM vs ILASP breakdown
    """
    log("="*60)
    log("COMPARISON EXPERIMENT (Incremental Mode: LLM vs ILASP)")
    log("="*60)
    log(f"Original: {original_dir}")
    log(f"Modified: {modified_dir}")
    
    # Run original (ISOLATED)
    log("\n>>> RUNNING ORIGINAL (isolated experiment)")
    args.experiment_id = f"original_{Path(original_dir).name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    original_result = incremental_lint(original_dir, args)
    
    # Run modified (COMPLETELY FRESH - ISOLATED)
    log("\n>>> RUNNING MODIFIED (isolated experiment - NO knowledge from original)")
    args.experiment_id = f"modified_{Path(modified_dir).name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    modified_result = incremental_lint(modified_dir, args)
    
    # Build comparison with LLM vs ILASP breakdown
    comparison = {
        "original": {
            "story_dir": original_dir,
            "chapters": len(original_result["chapters"]),
            "total_errors": original_result["error_count"],
            "llm_errors": len(original_result["llm_errors"]),
            "ilasp_errors": len(original_result["ilasp_errors"]),
            "comparison": original_result.get("comparison", {}),
        },
        "modified": {
            "story_dir": modified_dir,
            "chapters": len(modified_result["chapters"]),
            "total_errors": modified_result["error_count"],
            "llm_errors": len(modified_result["llm_errors"]),
            "ilasp_errors": len(modified_result["ilasp_errors"]),
            "comparison": modified_result.get("comparison", {}),
        },
        "detection_analysis": {
            # Overall detection
            "combined_detection_success": modified_result["error_count"] > original_result["error_count"],
            "combined_additional": modified_result["error_count"] - original_result["error_count"],
            # LLM-specific detection
            "llm_detection_success": len(modified_result["llm_errors"]) > len(original_result["llm_errors"]),
            "llm_additional": len(modified_result["llm_errors"]) - len(original_result["llm_errors"]),
            # ILASP-specific detection
            "ilasp_detection_success": len(modified_result["ilasp_errors"]) > len(original_result["ilasp_errors"]),
            "ilasp_additional": len(modified_result["ilasp_errors"]) - len(original_result["ilasp_errors"]),
        },
        "error_count": modified_result["error_count"],  # For compatibility
    }
    
    log("\n" + "="*60)
    log("COMPARISON RESULTS: LLM vs ILASP")
    log("="*60)
    log(f"\nOriginal story:")
    log(f"  Total errors: {comparison['original']['total_errors']}")
    log(f"  LLM direct:   {comparison['original']['llm_errors']}")
    log(f"  ILASP:        {comparison['original']['ilasp_errors']}")
    log(f"\nModified story:")
    log(f"  Total errors: {comparison['modified']['total_errors']}")
    log(f"  LLM direct:   {comparison['modified']['llm_errors']}")
    log(f"  ILASP:        {comparison['modified']['ilasp_errors']}")
    log(f"\nDetection Analysis:")
    log(f"  Combined: +{comparison['detection_analysis']['combined_additional']} errors {'(SUCCESS)' if comparison['detection_analysis']['combined_detection_success'] else '(FAILED)'}")
    log(f"  LLM only: +{comparison['detection_analysis']['llm_additional']} errors {'(SUCCESS)' if comparison['detection_analysis']['llm_detection_success'] else '(FAILED)'}")
    log(f"  ILASP:    +{comparison['detection_analysis']['ilasp_additional']} errors {'(SUCCESS)' if comparison['detection_analysis']['ilasp_detection_success'] else '(FAILED)'}")
    
    return comparison


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point for the story linting tool.
    
    This function:
    1. Parses command-line arguments
    2. Validates configuration
    3. Reads the story file
    4. Runs selected lint mode(s)
    5. Outputs results to stdout and output.json
    """
    # ===== ARGUMENT PARSING =====
    parser = argparse.ArgumentParser(
        description="Lint a story using LLM and/or logic-based reasoning.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with local LLM
  python scripts/story_lint.py story.txt
  
  # With Gemini API
  python scripts/story_lint.py --llm-backend gemini --llm-model gemini-2.5-flash story.txt
  
  # Logic-only mode
  python scripts/story_lint.py --mode logic story.txt
  
  # Mock mode for testing
  python scripts/story_lint.py --mock --mock-llm story.txt
  
  # Incremental mode (compares LLM direct linting vs ILASP learning per chapter)
  python scripts/story_lint.py --mode incremental original_books/Goosebumps/
  
  # Compare original vs modified (incremental mode, detects injected errors)
  python scripts/story_lint.py --mode incremental original_books/Goosebumps/ --compare-dir modified_books/Goosebumps/
  
  # Incremental mode with specific local LLM
  python scripts/story_lint.py --mode incremental --local-llm gemma-3-12b original_books/Goosebumps/
        """
    )
    
    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["llm", "logic", "both", "incremental"],
        default="both",
        help="Which lint modes to run: llm (direct LLM analysis), logic (ASP reasoning), both (default), or incremental (chapter-by-chapter comparison of LLM vs ILASP learning)"
    )
    parser.add_argument(
        "story",
        nargs="?",
        default="story.txt",
        help="Path to story file or directory of chapters (for incremental mode)"
    )
    
    # LLM configuration (for direct linting and violation interpretation)
    parser.add_argument("--llm-model", default="auto", help="LLM model ID or 'auto' to detect")
    parser.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:8080/v1"),
                        help="LLM API base URL")
    parser.add_argument("--llm-api-key", default=os.environ.get("LLM_API_KEY", ""), help="LLM API key")
    parser.add_argument("--llm-no-auth", action="store_true", help="Skip Authorization header")
    parser.add_argument("--llm-backend", choices=["openai", "guidance", "gemini"], default="openai",
                        help="LLM backend type")
    parser.add_argument("--llm-temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--llm-timeout", type=int, default=600, help="Request timeout in seconds")
    parser.add_argument("--llm-max-tokens", type=int, default=2048, help="Max output tokens")
    parser.add_argument("--llm-retries", type=int, default=3, help="Retry count on failure")
    parser.add_argument("--llm-backoff", type=int, default=5, help="Initial backoff seconds")
    parser.add_argument("--llm-thinking-budget", type=int, default=0, help="Gemini thinking budget")
    
    # Structurer configuration (for JSON conversion)
    parser.add_argument("--struct-model", default="auto", help="Structurer model ID")
    parser.add_argument("--struct-base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:8080/v1"),
                        help="Structurer API base URL")
    parser.add_argument("--struct-api-key", default=os.environ.get("LLM_API_KEY", ""), help="Structurer API key")
    parser.add_argument("--struct-no-auth", action="store_true", help="Skip auth for structurer")
    parser.add_argument("--struct-backend", choices=["openai", "guidance", "gemini"], default="openai",
                        help="Structurer backend type")
    parser.add_argument("--struct-timeout", type=int, default=600, help="Structurer timeout")
    parser.add_argument("--struct-max-tokens", type=int, default=8192, help="Structurer max tokens")
    parser.add_argument("--struct-retries", type=int, default=5, help="Structurer retries")
    parser.add_argument("--struct-backoff", type=int, default=30, help="Structurer backoff")
    parser.add_argument("--struct-thinking-budget", type=int, default=0, help="Structurer thinking budget")
    
    # Incremental mode options (for chapter-by-chapter ILASP learning)
    parser.add_argument("--local-llm", default="mistral-7b",
                        choices=["mistral-7b", "gemma-3-12b", "deepseek-r1-7b"],
                        help="Local llamafile model for incremental mode")
    parser.add_argument("--local-llm-port", type=int, default=8080,
                        help="Port for local llamafile server")
    parser.add_argument("--experiment-id", default=None,
                        help="Custom experiment ID for incremental mode")
    parser.add_argument("--compare-dir", default=None,
                        help="Compare story directory with this modified version (incremental mode)")
    
    # Other options
    parser.add_argument("--include-candidates", action="store_true",
                        help="Include candidate_rules in ASP facts")
    parser.add_argument("--mock", action="store_true",
                        help="Use examples/story.json instead of LLM structuring")
    parser.add_argument("--mock-llm", action="store_true",
                        help="Skip LLM lint, return mock response")
    parser.add_argument("--no-interpret", action="store_true",
                        help="Skip LLM interpretation of violations")
    
    args = parser.parse_args()

    # ===== INITIALIZATION =====
    log("Story lint starting.")
    
    # Auto-detect no-auth for local servers
    args.llm_no_auth = infer_no_auth(args.llm_base_url, args.llm_no_auth)
    args.struct_no_auth = infer_no_auth(args.struct_base_url, args.struct_no_auth)
    
    # Resolve "auto" model IDs
    if args.llm_backend in {"openai", "guidance"}:
        args.llm_model = resolve_model_id_openai(
            args.llm_base_url, args.llm_model, args.llm_api_key, args.llm_no_auth, args.llm_timeout
        )
    elif args.llm_backend == "gemini":
        args.llm_model = resolve_model_id_gemini(
            args.llm_base_url, args.llm_model, args.llm_api_key, args.llm_timeout
        )
    if args.struct_backend in {"openai", "guidance"}:
        args.struct_model = resolve_model_id_openai(
            args.struct_base_url, args.struct_model, args.struct_api_key, args.struct_no_auth, args.struct_timeout
        )
    elif args.struct_backend == "gemini":
        args.struct_model = resolve_model_id_gemini(
            args.struct_base_url, args.struct_model, args.struct_api_key, args.struct_timeout
        )
        
    # Log configuration
    log(f"Mode={args.mode} LLM={args.llm_model} Struct={args.struct_model}")
    log(f"LLM base URL={args.llm_base_url} no_auth={args.llm_no_auth} backend={args.llm_backend} "
        f"timeout={args.llm_timeout}s max_tokens={args.llm_max_tokens} retries={args.llm_retries} "
        f"thinking_budget={args.llm_thinking_budget}")
    log(f"Struct base URL={args.struct_base_url} no_auth={args.struct_no_auth} backend={args.struct_backend} "
        f"timeout={args.struct_timeout}s max_tokens={args.struct_max_tokens} retries={args.struct_retries} "
        f"thinking_budget={args.struct_thinking_budget}")

    # ===== VALIDATION =====
    # Check for required API keys based on mode and backend
    if args.mode in {"llm", "both"}:
        if args.llm_backend == "gemini" and not args.llm_api_key:
            raise SystemExit("Missing GEMINI_API_KEY or --llm-api-key for gemini backend.")
        if args.llm_backend == "guidance" and not args.llm_api_key and not args.llm_no_auth:
            raise SystemExit("Missing OPENAI_API_KEY or --llm-api-key for guidance backend (or use --llm-no-auth).")
        if args.llm_backend == "openai" and not args.llm_no_auth and not args.llm_api_key:
            raise SystemExit("Missing OPENAI_API_KEY or --llm-api-key (or use --llm-no-auth).")
    if args.mode in {"logic", "both"}:
        if args.struct_backend == "gemini" and not args.struct_api_key:
            raise SystemExit("Missing GEMINI_API_KEY or --struct-api-key for gemini backend.")
        if args.struct_backend == "guidance" and not args.struct_api_key and not args.struct_no_auth:
            raise SystemExit("Missing OPENAI_API_KEY or --struct-api-key for guidance backend (or use --struct-no-auth).")
        if args.struct_backend == "openai" and not args.struct_no_auth and not args.struct_api_key:
            raise SystemExit("Missing OPENAI_API_KEY or --struct-api-key (or use --struct-no-auth).")

    # ===== INCREMENTAL MODE =====
    # Incremental mode has different path handling (directory vs file)
    if args.mode == "incremental":
        story_path = Path(args.story)
        if not story_path.exists():
            raise SystemExit(f"Story path not found: {story_path}")
        
        start_time = datetime.now()
        
        # Check if comparing two directories
        if args.compare_dir:
            result = compare_incremental(str(story_path), args.compare_dir, args)
            result["mode"] = "incremental_compare"
        else:
            result = incremental_lint(str(story_path), args)
            result["mode"] = "incremental"
        
        end_time = datetime.now()
        result["total_errors"] = result.get("error_count", 0)
        
        # Build execution record for incremental mode
        command_line = " ".join(sys.argv)
        execution_record = {
            "command": command_line,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "config": {
                "mode": args.mode,
                "local_llm": args.local_llm,
                "local_llm_port": args.local_llm_port,
                "experiment_id": args.experiment_id,
                "compare_dir": args.compare_dir,
            },
            "story_path": str(story_path),
            "result": result,
        }
        
        # Save to output.json
        output_file = Path("output.json")
        if output_file.exists():
            try:
                history = json.loads(output_file.read_text())
                if not isinstance(history, list):
                    history = [history]
            except json.JSONDecodeError:
                history = []
        else:
            history = []
        history.append(execution_record)
        output_file.write_text(json.dumps(history, indent=2) + "\n")
        log(f"Appended result to {output_file}")
        
        # Output to stdout
        log("Writing JSON result to stdout.")
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return

    # ===== LOAD STORY (for non-incremental modes) =====
    story_path = Path(args.story)
    if not story_path.exists():
        raise SystemExit(f"Story file not found: {story_path}")
    if story_path.is_dir():
        raise SystemExit(f"For directory processing, use --mode incremental: {story_path}")
    story_text = story_path.read_text()
    if not story_text.strip():
        raise SystemExit("Story file is empty.")
    log(f"Read story from {story_path} ({len(story_text)} bytes).")

    # ===== RUN LINTING =====
    start_time = datetime.now()
    result = {}
    
    if args.mode in {"llm", "both"}:
        result["llm_lint"] = llm_lint(story_text, args)
        
    if args.mode in {"logic", "both"}:
        result["logic_lint"] = logic_lint(story_text, args)
        
    end_time = datetime.now()

    # ===== CALCULATE TOTALS =====
    total = 0
    if "llm_lint" in result:
        total += result["llm_lint"].get("error_count", 0)
    if "logic_lint" in result:
        total += result["logic_lint"].get("error_count", 0)
    result["total_errors"] = total

    # ===== BUILD EXECUTION RECORD =====
    # This comprehensive record is saved to output.json for debugging and analysis
    command_line = " ".join(sys.argv)
    execution_record = {
        "command": command_line,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": (end_time - start_time).total_seconds(),
        "config": {
            "mode": args.mode,
            "llm": {
                "model": args.llm_model,
                "backend": args.llm_backend,
                "base_url": args.llm_base_url,
                "temperature": args.llm_temperature,
                "timeout": args.llm_timeout,
                "max_tokens": args.llm_max_tokens,
                "retries": args.llm_retries,
                "backoff": args.llm_backoff,
                "thinking_budget": args.llm_thinking_budget,
                "no_auth": args.llm_no_auth,
            },
            "structurer": {
                "model": args.struct_model,
                "backend": args.struct_backend,
                "base_url": args.struct_base_url,
                "timeout": args.struct_timeout,
                "max_tokens": args.struct_max_tokens,
                "retries": args.struct_retries,
                "backoff": args.struct_backoff,
                "thinking_budget": args.struct_thinking_budget,
                "no_auth": args.struct_no_auth,
            },
            "mock": getattr(args, 'mock', False),
            "mock_llm": getattr(args, 'mock_llm', False),
            "no_interpret": getattr(args, 'no_interpret', False),
            "include_candidates": args.include_candidates,
        },
        "story_path": str(story_path),
        "story": story_text,
        "result": result,
    }

    # ===== SAVE TO OUTPUT.JSON =====
    # Append to history (don't overwrite previous runs)
    output_file = Path("output.json")
    if output_file.exists():
        try:
            history = json.loads(output_file.read_text())
            if not isinstance(history, list):
                history = [history]
        except json.JSONDecodeError:
            history = []
    else:
        history = []
    history.append(execution_record)
    output_file.write_text(json.dumps(history, indent=2) + "\n")
    log(f"Appended result to {output_file}")

    # ===== OUTPUT TO STDOUT =====
    log("Writing JSON result to stdout.")
    sys.stdout.write(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
