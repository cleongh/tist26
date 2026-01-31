"""
LLM client for chapter evaluation (Step 1: LLM-only evaluation).
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .api_clients import create_api_client
from .prompts import LLM_SYSTEM_MESSAGE, LLM_LINT_PROMPT
from ..state.logging import log


class LLMClient:
    """Simple LLM client for chapter evaluation."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0, log_file: Path = None,
                 api_mode: str = "local", api_model: str = None, api_delay: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.log_file = log_file
        self.api_mode = api_mode
        self.api_model = api_model
        # Create the appropriate API client
        self.api_client = create_api_client(api_mode, api_model, base_url, api_delay)
        
        # Initialize log file with empty list
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "w") as f:
                f.write("")  # Clear/create file
    
    def _log_interaction(self, story: str, variant: str, chapter: str, prompt: str, response: str, errors: List[Dict], duration: float):
        """Log a prompt/response interaction to the log file."""
        if not self.log_file:
            return
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "story": story,
            "variant": variant,
            "chapter": chapter,
            "duration_seconds": duration,
            "prompt_length": len(prompt),
            "response_length": len(response),
            "errors_detected": len(errors),
            "prompt": prompt,
            "response": response,
            "parsed_errors": errors,
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def check_server(self) -> bool:
        """Check if LLM server is available."""
        return self.api_client.check_server()
    
    def evaluate_chapter(self, chapter_text: str, story: str = "", variant: str = "", chapter_name: str = "", 
                          previous_summaries: List[str] = None) -> Tuple[List[Dict], float, str, str, str]:
        """
        Evaluate a single chapter for narrative errors.
        
        Args:
            chapter_text: The text of the chapter to evaluate
            story: Name of the story
            variant: "original" or "modified"
            chapter_name: Name of the chapter file
            previous_summaries: List of summaries from previous chapters for context
        
        Returns:
            Tuple of (list of error dicts, duration in seconds, prompt, response, chapter_summary)
        """
        start_time = time.time()
        
        # Build previous summaries section
        if previous_summaries:
            summaries_text = "\n---PREVIOUS CHAPTER SUMMARIES---\n"
            for i, summary in enumerate(previous_summaries):
                summaries_text += f"Chapter {i + 1}: {summary}\n"
            summaries_text += "---END PREVIOUS SUMMARIES---\n\n"
        else:
            summaries_text = "\n"
        
        prompt = LLM_LINT_PROMPT.format(chapter_text=chapter_text, previous_summaries_section=summaries_text)
        
        response_text = ""
        try:
            # Prepend system message to prompt for API clients
            full_prompt = f"{LLM_SYSTEM_MESSAGE}\n\n{prompt}"
            response_text = self.api_client.extract(full_prompt, max_tokens=1500, timeout=180)
        except Exception as e:
            log(f"LLM request failed: {e}", "ERROR")
            return [], time.time() - start_time, prompt, str(e), ""
        
        duration = time.time() - start_time
        
        # Parse response (now also extracts summary)
        errors, chapter_summary = self._parse_response(response_text)
        
        # Log interaction
        self._log_interaction(story, variant, chapter_name, prompt, response_text, errors, duration)
        
        return errors, duration, prompt, response_text, chapter_summary
    
    def _parse_response(self, response: str) -> Tuple[List[Dict], str]:
        """Parse LLM response into error list and chapter summary.
        
        Returns:
            Tuple of (list of error dicts, chapter summary string)
        """
        # Clean response
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        
        # Find JSON
        start = response.find('{')
        end = response.rfind('}')
        if start == -1 or end == -1:
            log(f"No JSON found in response (length={len(response)})", "WARN")
            log(f"Response preview: {response[:200]}...", "DEBUG")
            return [], ""
        
        try:
            data = json.loads(response[start:end + 1])
            errors = data.get("errors", [])
            chapter_summary = data.get("chapter_summary", "")
            error_count = data.get("error_count", len(errors))
            if error_count > 0:
                log(f"    LLM reported {error_count} errors", "DEBUG")
            if chapter_summary:
                log(f"    Summary: {chapter_summary[:80]}...", "DEBUG")
            return errors, chapter_summary
        except json.JSONDecodeError as e:
            log(f"JSON parse error: {e}", "WARN")
            log(f"JSON preview: {response[start:start+200]}...", "DEBUG")
            return [], ""
