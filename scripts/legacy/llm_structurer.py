"""LLM-based story structurer module.

Converts narrative text into structured JSON using an LLM.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Get directory containing this script and repo root (for resolving relative paths)
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent  # prompts/ is at repo root


def log(msg):
    sys.stderr.write(f"[llm_structurer] {msg}\n")


def load_prompt(prompt_path, story_text):
    # Resolve path relative to repo root (not script dir) if not absolute
    path = Path(prompt_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    template = path.read_text()
    
    # Include ASP rules for schema alignment if available
    rules_content = ""
    for rules_file in ['rules/general.lp', 'rules/base.lp']:
        rules_path = REPO_ROOT / rules_file
        if rules_path.exists():
            rules_content += f"\n\n=== {rules_file} (schema reference) ===\n"
            # Include relevant portions of the rules (not the full file)
            rules_text = rules_path.read_text()
            # Extract key schema information
            rules_content += _extract_schema_info(rules_text)
    
    # Replace placeholders
    result = template.replace("{{STORY}}", story_text.strip())
    if "{{RULES}}" in result:
        result = result.replace("{{RULES}}", rules_content)
    
    return result


def _extract_schema_info(rules_text):
    """
    Extract key schema information from ASP rules for prompt injection.
    
    This ensures the LLM generates JSON that aligns with the ASP schema.
    """
    info = []
    
    # Extract violation types
    if "violation(" in rules_text:
        info.append("Violation types defined:")
        violation_types = set()
        for line in rules_text.split('\n'):
            if 'violation(' in line and ':-' in line:
                # Extract violation type from rule head
                import re
                match = re.search(r'violation\((\w+)', line)
                if match:
                    violation_types.add(match.group(1))
        for vt in sorted(violation_types):
            info.append(f"  - {vt}")
    
    # Extract categories
    if "category" in rules_text.lower():
        info.append("\nError categories: causality, coherence, temporal, location, emotional")
    
    # Extract key predicates
    key_predicates = ['character', 'object', 'location', 'event', 'event_type', 
                      'agent', 'patient', 'time', 'loves', 'hates', 'fears', 
                      'trusts', 'distrusts', 'emotional_state', 'trait']
    found = [p for p in key_predicates if f"{p}(" in rules_text]
    if found:
        info.append(f"\nExpected predicates: {', '.join(found)}")
    
    return '\n'.join(info) if info else "(no schema info extracted)"


def request_with_retry(fn, retries, backoff_seconds):
    attempt = 0
    while True:
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt >= retries:
                raise
            sleep_for = backoff_seconds * (2**attempt)
            log(f"HTTP {exc.code} received, retrying in {sleep_for}s (attempt {attempt + 1}/{retries})")
            time.sleep(sleep_for)
            attempt += 1


def is_local_server(base_url):
    """Check if connecting to a local server."""
    if not base_url:
        return False
    return "localhost" in base_url or "127.0.0.1" in base_url or "0.0.0.0" in base_url


def call_openai(
    prompt,
    model,
    base_url,
    api_key,
    temperature=0.2,
    no_auth=False,
    use_response_format=True,
    timeout=60,
    max_tokens=None,
    retries=2,
    backoff_seconds=2,
):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": "You are a semantic parser for narrative text."},
            {"role": "user", "content": prompt},
        ],
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    # Disable response_format for local servers (llamafile, ollama often don't support it)
    if use_response_format and not is_local_server(base_url):
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if not no_auth and api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    def do_request():
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    body = request_with_retry(do_request, retries=retries, backoff_seconds=backoff_seconds)
    obj = json.loads(body)
    return obj["choices"][0]["message"]["content"]


def call_gemini(
    prompt,
    model,
    base_url,
    api_key,
    temperature=0.2,
    timeout=60,
    max_tokens=None,
    retries=2,
    backoff_seconds=2,
    thinking_budget=0,
):
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY or api_key.")
    if model.startswith("models/"):
        model = model[len("models/"):]
    url = base_url.rstrip("/") + f"/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if max_tokens is not None:
        payload["generationConfig"]["maxOutputTokens"] = max_tokens
    payload["generationConfig"]["responseMimeType"] = "application/json"
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
        if exc.code == 400 and "thinkingConfig" in payload.get("generationConfig", {}):
            payload["generationConfig"].pop("thinkingConfig", None)
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            body = request_with_retry(do_request, retries=retries, backoff_seconds=backoff_seconds)
        else:
            raise
    obj = json.loads(body)
    candidates = obj.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini response missing candidates.")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text:
        raise ValueError("Gemini response missing text content.")
    return text


def story_json_schema():
    return {
        "type": "object",
        "required": [
            "schema_version",
            "entities",
            "events",
            "fluents",
            "traits",
            "rules",
            "constraints",
            "candidate_rules",
        ],
        "properties": {
            "schema_version": {"type": "string"},
            "entities": {
                "type": "object",
                "required": ["characters", "objects", "locations"],
                "properties": {
                    "characters": {
                        "type": "array",
                        "items": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
                    },
                    "objects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "type"],
                            "properties": {"id": {"type": "string"}, "type": {"type": "string"}},
                        },
                    },
                    "locations": {
                        "type": "array",
                        "items": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
                    },
                },
            },
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "type", "agent", "patient", "location", "time", "requires_focus"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "agent": {"type": "string"},
                        "patient": {"type": ["string", "null"]},
                        "location": {"type": "string"},
                        "time": {
                            "type": "object",
                            "required": ["start", "end"],
                            "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
                        },
                        "requires_focus": {"type": "boolean"},
                    },
                },
            },
            "fluents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "time"],
                    "properties": {
                        "id": {"type": "string"},
                        "time": {
                            "type": "object",
                            "required": ["start", "end"],
                            "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
                        },
                    },
                },
            },
            "traits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["character", "trait"],
                    "properties": {"character": {"type": "string"}, "trait": {"type": "string"}},
                },
            },
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "type", "head", "body"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "head": {"type": "string"},
                        "body": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "constraints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "type", "description", "body"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "description": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
            },
            "candidate_rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "type", "rule", "confidence"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "rule": {"type": "string"},
                        "confidence": {"type": "string"},
                    },
                },
            },
        },
    }


def call_guidance(
    prompt,
    model,
    api_key,
    base_url=None,
    no_auth=False,
    timeout=60,
    max_tokens=None,
    retries=2,
):
    try:
        import guidance
    except ImportError as exc:
        raise ImportError("guidance is not installed. Install it or use backend='openai'.") from exc

    if no_auth and not api_key:
        api_key = "local"
    kwargs = {"model": model, "api_key": api_key, "timeout": timeout, "max_retries": retries}
    if base_url:
        kwargs["base_url"] = base_url
    try:
        llm = guidance.models.OpenAI(**kwargs)
    except TypeError:
        kwargs.pop("base_url", None)
        llm = guidance.models.OpenAI(**kwargs)

    schema = story_json_schema()

    def run_with_schema(schema_value):
        @guidance.guidance(dedent=False)
        def program(lm, user_prompt, schema, max_tokens):
            with guidance.system():
                lm += "You are a semantic parser for narrative text."
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
    except Exception:
        try:
            result = run_with_schema(None)
        except Exception:
            return call_openai(
                prompt,
                model,
                base_url,
                api_key,
                temperature=0.0,
                no_auth=no_auth,
                use_response_format=False,
                timeout=timeout,
                max_tokens=max_tokens,
                retries=retries,
                backoff_seconds=2,
            )

    json_out = result["json_out"]
    if isinstance(json_out, str):
        return json_out
    return json.dumps(json_out)


def extract_json(text):
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def strip_think(text):
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1 and end > start:
        return text[:start] + text[end + len("</think>"):]
    return text


def basic_validate(data):
    """Add defaults for missing keys to be more lenient with local models."""
    if "schema_version" not in data:
        data["schema_version"] = "1.0"
    if "entities" not in data:
        data["entities"] = {"characters": [], "objects": [], "locations": []}
    if "events" not in data:
        data["events"] = []
    if "fluents" not in data:
        data["fluents"] = []
    if "traits" not in data:
        data["traits"] = []
    if "rules" not in data:
        data["rules"] = []
    if "constraints" not in data:
        data["constraints"] = []
    if "candidate_rules" not in data:
        data["candidate_rules"] = []
    # Ensure entities has all sub-keys
    if isinstance(data.get("entities"), dict):
        data["entities"].setdefault("characters", [])
        data["entities"].setdefault("objects", [])
        data["entities"].setdefault("locations", [])


def structure_story(
    story_text,
    *,
    prompt_path="prompts/structure_prompt.txt",
    model="auto",
    base_url="http://localhost:8080/v1",
    api_key=None,
    no_auth=False,
    backend="openai",
    timeout=300,
    max_tokens=8192,
    retries=5,
    backoff=30,
    thinking_budget=0,
    return_details=False,
):
    """
    Structure a story text into JSON using an LLM.

    Args:
        story_text: The narrative text to structure.
        prompt_path: Path to the prompt template file.
        model: Model name or "auto" to auto-detect.
        base_url: API base URL.
        api_key: API key (required for Gemini, optional for local).
        no_auth: Skip Authorization header.
        backend: LLM backend ("openai", "guidance", "gemini").
        timeout: Request timeout in seconds.
        max_tokens: Max tokens for model output.
        retries: Retry count for HTTP 429/503.
        backoff: Base backoff seconds for retries.
        thinking_budget: Gemini thinking budget (0 disables).
        return_details: If True, return dict with prompt, raw_response, and parsed data.

    Returns:
        dict: If return_details=False, the parsed story JSON structure.
              If return_details=True, dict with keys: prompt, raw_response, parsed, model, backend.

    Raises:
        ValueError: If LLM output is invalid or cannot be parsed.
    """
    # Infer no_auth from base_url if not set
    if not no_auth:
        no_auth = is_local_server(base_url)

    # Resolve model ID
    if model in ("auto", "llama"):
        if backend in {"openai", "guidance"}:
            model = _resolve_model_id_openai(base_url, model, api_key, no_auth, timeout)
        elif backend == "gemini":
            model = _resolve_model_id_gemini(base_url, model, api_key, timeout)

    log(f"Structuring story with model={model} backend={backend}")

    # Load and fill prompt template
    prompt = load_prompt(prompt_path, story_text)

    # Call appropriate backend
    if backend == "gemini":
        if not api_key:
            raise ValueError("Missing api_key for gemini backend.")
        content = call_gemini(
            prompt,
            model,
            base_url,
            api_key,
            temperature=0.0,
            timeout=timeout,
            max_tokens=max_tokens,
            retries=retries,
            backoff_seconds=backoff,
            thinking_budget=thinking_budget,
        )
    elif backend == "guidance":
        content = call_guidance(
            prompt,
            model,
            api_key,
            base_url=base_url,
            no_auth=no_auth,
            timeout=timeout,
            max_tokens=max_tokens,
            retries=retries,
        )
    else:  # openai
        content = call_openai(
            prompt,
            model,
            base_url,
            api_key,
            no_auth=no_auth,
            timeout=timeout,
            max_tokens=max_tokens,
            retries=retries,
            backoff_seconds=backoff,
        )

    # Extract and parse JSON
    raw_json = extract_json(content)
    if raw_json is None:
        raw_json = extract_json(strip_think(content))
    if raw_json is None:
        snippet = content.strip().replace("\n", " ")[:300]
        log(f"LLM raw output (truncated): {snippet}")
        raise ValueError("LLM output did not contain a JSON object.")

    parsed = json.loads(raw_json)
    basic_validate(parsed)

    if return_details:
        return {
            "prompt": prompt,
            "raw_response": content,
            "parsed": parsed,
            "model": model,
            "backend": backend,
        }
    return parsed


def _resolve_model_id_openai(base_url, model, api_key, no_auth, timeout):
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
    except Exception:
        return model
    models = data.get("data") or []
    if models:
        model_id = models[0].get("id")
        if model_id:
            return model_id
    return model


def _resolve_model_id_gemini(base_url, model, api_key, timeout):
    if model != "auto":
        return model
    if not api_key:
        return model
    models_url = base_url.rstrip("/") + f"/models?key={api_key}"
    try:
        with urllib.request.urlopen(models_url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return model
    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
    preferred = [
        "models/gemini-2.0-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.5-flash",
    ]
    for name in preferred:
        if name in models:
            return name
    if models:
        return models[0]
    return model
