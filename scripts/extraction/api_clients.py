"""
API clients for LLM providers (Gemini, OpenAI, Local).
"""

import json
import os
import time
import urllib.request
from typing import Optional

# Import configuration from state module
from ..state.config import (
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    MOONSHOT_API_KEY,
    DASHSCOPE_API_KEY,
    DEFAULT_MODELS,
    PROVIDER_BASE_URLS,
)
from ..state.logging import log


class GeminiAPIClient:
    """Client for Google Gemini API."""
    
    def __init__(self, model: str = "gemini-2.0-flash", temperature: float = 0.2, 
                 top_p: float = 0.9, top_k: int = 0, api_delay: float = 0.0):
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.api_delay = api_delay
        self._client = None
        self._last_call_time = 0
        
    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                if not GEMINI_API_KEY:
                    raise ValueError("GEMINI_API_KEY environment variable not set")
                genai.configure(api_key=GEMINI_API_KEY)
                self._client = genai.GenerativeModel(self.model)
            except ImportError:
                raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
        return self._client
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 300) -> str:
        """Make a Gemini API call and return the response text."""
        import google.generativeai as genai
        
        # Rate limiting delay
        if self.api_delay > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.api_delay:
                time.sleep(self.api_delay - elapsed)
        
        client = self._get_client()
        
        system_prompt = "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."
        full_prompt = f"{system_prompt}\n\n{prompt}"
        
        generation_config = genai.GenerationConfig(
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            max_output_tokens=max_tokens,
        )
        
        response = client.generate_content(
            full_prompt,
            generation_config=generation_config,
        )
        
        self._last_call_time = time.time()
        return response.text
    
    def check_server(self) -> bool:
        """Check if Gemini API is available."""
        try:
            self._get_client()
            return True
        except Exception as e:
            log(f"Gemini API check failed: {e}", "ERROR")
            return False


class OpenAIAPIClient:
    """Client for OpenAI-compatible chat-completions APIs (OpenAI, and via
    base_url override, other OpenAI-compatible providers)."""
    
    def __init__(self, model: str = "gpt-4o", temperature: float = 0.2,
                 top_p: float = 0.9, presence_penalty: float = 0.0, frequency_penalty: float = 0.0,
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 provider: str = "openai"):
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.presence_penalty = presence_penalty
        self.frequency_penalty = frequency_penalty
        self.base_url = base_url
        self.api_key = api_key
        self.provider = provider
        self._client = None
        
    def _get_client(self):
        """Lazy initialization of OpenAI-compatible client."""
        if self._client is None:
            try:
                from openai import OpenAI
                key = self.api_key or OPENAI_API_KEY
                if not key:
                    raise ValueError("OPENAI_API_KEY environment variable not set")
                if self.base_url:
                    self._client = OpenAI(api_key=key, base_url=self.base_url)
                else:
                    self._client = OpenAI(api_key=key)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client
    
    def _uses_max_completion_tokens(self) -> bool:
        """Check if model requires max_completion_tokens instead of max_tokens.
        
        Newer OpenAI models (GPT-5 family, o1, o3, o4, etc.) use
        max_completion_tokens. Legacy models (GPT-4o, GPT-4, GPT-3.5) use
        max_tokens. Only applies to the "openai" provider.
        """
        if self.provider != "openai":
            return False
        model_lower = self.model.lower()
        # GPT-5 family and reasoning models use max_completion_tokens
        if any(prefix in model_lower for prefix in ['gpt-5', 'o1', 'o3', 'o4']):
            return True
        return False
    
    def _is_restricted_model(self) -> bool:
        """Check if model has restricted parameters (no temperature, top_p, etc.).
        
        Some newer OpenAI models (GPT-5 mini, reasoning models) only support
        default parameter values and will error if custom values are passed.
        All current Kimi models fix temperature/top_p/penalties and error on
        any explicit override. Qwen's hybrid-thinking models allow full
        parameter control, so they are not restricted here.
        """
        model_lower = self.model.lower()
        if self.provider == "openai":
            # GPT-5-mini and reasoning models have parameter restrictions
            if any(prefix in model_lower for prefix in ['gpt-5-mini', 'o1', 'o3', 'o4']):
                return True
        elif self.provider == "kimi":
            return True
        return False
    
    def _kimi_thinking_toggle(self) -> Optional[dict]:
        """Extra request body to disable Kimi's thinking mode, where supported.
        
        K2.6/K2.5 think by default and their hidden reasoning_content shares
        the max_tokens budget with the visible output, which can silently
        truncate short extraction calls to nothing. K3 and K2.7-code don't
        accept this parameter (K3 has no toggle; K2.7-code always thinks).
        """
        model_lower = self.model.lower()
        if self.provider == "kimi" and ("k2.6" in model_lower or "k2.5" in model_lower):
            return {"thinking": {"type": "disabled"}}
        return None
    
    def _qwen_thinking_toggle(self) -> Optional[dict]:
        """Extra request body to disable Qwen's hybrid thinking mode.
        
        Qwen3+ models default to reasoning enabled, and their hidden
        reasoning_content shares the max_tokens budget with the visible
        output just like Kimi, risking silent truncation on short calls.
        """
        if self.provider == "qwen":
            return {"enable_thinking": False}
        return None
    
    def _min_output_tokens(self) -> Optional[int]:
        """Minimum completion token budget this model needs.
        
        Reasoning models (e.g. Kimi K3) emit hidden reasoning_content that
        counts against the same max_tokens/max_completion_tokens budget as
        the visible content, so callers' default budgets can be too small.
        """
        model_lower = self.model.lower()
        if self.provider == "kimi" and "k3" in model_lower:
            return 32768
        return None
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
        """Make an OpenAI API call and return the response text."""
        client = self._get_client()
        
        # Build base request parameters
        request_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."},
                {"role": "user", "content": prompt}
            ],
        }
        
        # Only add sampling parameters for models that support them
        if not self._is_restricted_model():
            request_params["temperature"] = self.temperature
            # Anthropic's OpenAI-compat endpoint rejects temperature+top_p together
            if self.provider != "claude":
                request_params["top_p"] = self.top_p
            request_params["presence_penalty"] = self.presence_penalty
            request_params["frequency_penalty"] = self.frequency_penalty
        
        thinking_toggle = self._kimi_thinking_toggle() or self._qwen_thinking_toggle()
        if thinking_toggle:
            request_params["extra_body"] = thinking_toggle
        
        # Raise the budget floor for models whose reasoning tokens share it
        min_tokens = self._min_output_tokens()
        effective_max_tokens = max(max_tokens, min_tokens) if min_tokens else max_tokens
        
        # Use appropriate token limit parameter based on model
        if self._uses_max_completion_tokens():
            request_params["max_completion_tokens"] = effective_max_tokens
        else:
            request_params["max_tokens"] = effective_max_tokens
        
        response = client.chat.completions.create(**request_params)
        message = response.choices[0].message
        content = message.content or ""
        
        # Reasoning models can exhaust the budget on hidden reasoning and
        # return no visible content; surface this instead of failing silently
        if not content and response.choices[0].finish_reason == "length":
            reasoning = getattr(message, "reasoning_content", None)
            log(
                f"{self.provider.title()} response truncated with no visible "
                f"content (finish_reason=length, reasoning_content_len="
                f"{len(reasoning) if reasoning else 0}); consider raising max_tokens",
                "WARN",
            )
        
        return content
    
    def check_server(self) -> bool:
        """Check if the OpenAI-compatible API is available."""
        try:
            self._get_client()
            return True
        except Exception as e:
            log(f"{self.provider.title()} API check failed: {e}", "ERROR")
            return False


class LocalLLMClient:
    """Client for local LLM server (llamafile, llama.cpp, etc.)."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.2,
                 top_p: float = 0.9, top_k: int = 0, repeat_penalty: float = 1.0,
                 presence_penalty: float = 0.0, frequency_penalty: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.repeat_penalty = repeat_penalty
        self.presence_penalty = presence_penalty
        self.frequency_penalty = frequency_penalty
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 300) -> str:
        """Make a local LLM call and return the response text."""
        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_tokens": max_tokens,
            "repetition_penalty": self.repeat_penalty,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
        }
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
    
    def check_server(self) -> bool:
        """Check if local LLM server is available."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False


def create_api_client(api_mode: str, api_model: str = None, base_url: str = "http://localhost:8080/v1", api_delay: float = 0.0):
    """Factory function to create the appropriate API client."""
    if api_mode == "gemini":
        model = api_model or DEFAULT_MODELS["gemini"]
        log(f"Using Gemini API with model: {model}", "INFO")
        if api_delay > 0:
            log(f"Rate limit delay: {api_delay}s between API calls", "INFO")
        return GeminiAPIClient(model=model, api_delay=api_delay)
    elif api_mode == "openai":
        model = api_model or DEFAULT_MODELS["openai"]
        log(f"Using OpenAI API with model: {model}", "INFO")
        return OpenAIAPIClient(model=model)
    elif api_mode == "claude":
        model = api_model or DEFAULT_MODELS["claude"]
        log(f"Using Claude (Anthropic) API with model: {model}", "INFO")
        return OpenAIAPIClient(
            model=model,
            base_url=PROVIDER_BASE_URLS["claude"],
            api_key=ANTHROPIC_API_KEY,
            provider="claude",
        )
    elif api_mode == "kimi":
        model = api_model or DEFAULT_MODELS["kimi"]
        log(f"Using Kimi (Moonshot) API with model: {model}", "INFO")
        return OpenAIAPIClient(
            model=model,
            base_url=PROVIDER_BASE_URLS["kimi"],
            api_key=MOONSHOT_API_KEY,
            provider="kimi",
        )
    elif api_mode == "qwen":
        model = api_model or DEFAULT_MODELS["qwen"]
        log(f"Using Qwen (Alibaba Model Studio) API with model: {model}", "INFO")
        return OpenAIAPIClient(
            model=model,
            base_url=PROVIDER_BASE_URLS["qwen"],
            api_key=DASHSCOPE_API_KEY,
            provider="qwen",
        )
    else:  # local
        log(f"Using local LLM at: {base_url}", "INFO")
        return LocalLLMClient(base_url=base_url)
