"""
API clients for LLM providers (Gemini, OpenAI, Local).
"""

import json
import os
import time
import urllib.request
from typing import Optional

# Import configuration from state module
from ..state.config import GEMINI_API_KEY, OPENAI_API_KEY, DEFAULT_MODELS
from ..state.logging import log


class GeminiAPIClient:
    """Client for Google Gemini API."""
    
    def __init__(self, model: str = "gemini-2.0-flash", temperature: float = 0.0, api_delay: float = 0.0):
        self.model = model
        self.temperature = temperature
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
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
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
    """Client for OpenAI API."""
    
    def __init__(self, model: str = "gpt-4o", temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self._client = None
        
    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                if not OPENAI_API_KEY:
                    raise ValueError("OPENAI_API_KEY environment variable not set")
                self._client = OpenAI(api_key=OPENAI_API_KEY)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
        """Make an OpenAI API call and return the response text."""
        client = self._get_client()
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."},
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content
    
    def check_server(self) -> bool:
        """Check if OpenAI API is available."""
        try:
            self._get_client()
            return True
        except Exception as e:
            log(f"OpenAI API check failed: {e}", "ERROR")
            return False


class LocalLLMClient:
    """Client for local LLM server (llamafile, llama.cpp, etc.)."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
    
    def extract(self, prompt: str, max_tokens: int = 4096, timeout: int = 120) -> str:
        """Make a local LLM call and return the response text."""
        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else. No explanations."},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "repetition_penalty": 1.1,
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
    else:  # local
        log(f"Using local LLM at: {base_url}", "INFO")
        return LocalLLMClient(base_url=base_url)
