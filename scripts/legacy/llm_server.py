#!/usr/bin/env python3
"""
llm_server.py - Llamafile Server Manager for Isolated Experiments
===================================================================

Manages llamafile LLM servers, ensuring a FRESH instance for each experiment.

KEY PRINCIPLE: Complete Isolation
─────────────────────────────────

Each experiment gets a FRESH LLM server with NO memory of previous runs.
The server is started before the experiment and killed after.

    Experiment 1:
        → Start fresh llamafile server
        → Process chapters
        → Kill server (clear all state)
    
    Experiment 2:
        → Start NEW fresh llamafile server
        → Knows NOTHING from Experiment 1

AVAILABLE MODELS (in /home/mrcorner/Workspace/models/):
───────────────────────────────────────────────────────

    - deepseek-r1-7b: DeepSeek-R1-Distill-Qwen-7B-Q8_0.llamafile
    - gemma-3-12b:    google_gemma-3-12b-it-Q4_K_M.llamafile  
    - mistral-7b:     Mistral-7B-Instruct-v0.3.Q5_1.llamafile

USAGE:
──────

    # As a module
    from llm_server import LlamafileServer
    
    with LlamafileServer(model="mistral-7b") as server:
        response = server.chat("Hello, world!")
    # Server automatically killed on exit
    
    # As CLI
    python llm_server.py start --model mistral-7b
    python llm_server.py stop
    python llm_server.py status

Author: Research Project - Narrative Evaluation
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# Configuration
MODELS_DIR = Path("/home/mrcorner/Workspace/models")
DEFAULT_PORT = 8080
DEFAULT_HOST = "127.0.0.1"
STARTUP_TIMEOUT = 120  # seconds to wait for server to start
HEALTH_CHECK_INTERVAL = 1  # seconds between health checks

# Model registry
MODELS = {
    "deepseek-r1-7b": {
        "file": "DeepSeek-R1-Distill-Qwen-7B-Q8_0.llamafile",
        "context_size": 4096,
        "description": "DeepSeek R1 Distill Qwen 7B (Q8_0)",
    },
    "gemma-3-12b": {
        "file": "google_gemma-3-12b-it-Q4_K_M.llamafile",
        "context_size": 8192,
        "description": "Google Gemma 3 12B Instruct (Q4_K_M)",
    },
    "mistral-7b": {
        "file": "Mistral-7B-Instruct-v0.3.Q5_1.llamafile",
        "context_size": 8192,
        "description": "Mistral 7B Instruct v0.3 (Q5_1)",
    },
}

# PID file location
PID_FILE = Path("/tmp/llamafile_server.pid")


@dataclass
class ServerConfig:
    """Configuration for a llamafile server instance."""
    model: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    n_gpu_layers: int = -1  # -1 = use all GPU layers
    context_size: Optional[int] = None
    threads: int = 8
    
    def __post_init__(self):
        if self.model not in MODELS:
            available = ", ".join(MODELS.keys())
            raise ValueError(f"Unknown model: {self.model}. Available: {available}")
        
        if self.context_size is None:
            self.context_size = MODELS[self.model]["context_size"]
    
    @property
    def model_path(self) -> Path:
        return MODELS_DIR / MODELS[self.model]["file"]
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class LlamafileServer:
    """
    Manager for a llamafile LLM server.
    
    IMPORTANT: Each instance creates a FRESH server with no memory.
    Use as a context manager to ensure proper cleanup.
    
    Example:
        with LlamafileServer(model="mistral-7b") as server:
            response = server.chat("Hello!")
        # Server killed automatically
    """
    
    def __init__(
        self,
        model: str = "mistral-7b",
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        n_gpu_layers: int = -1,
        context_size: Optional[int] = None,
        verbose: bool = True,
        auto_start: bool = True,
    ):
        """
        Initialize server manager.
        
        Args:
            model: Model name (mistral-7b, gemma-3-12b, deepseek-r1-7b)
            host: Host to bind to
            port: Port to listen on
            n_gpu_layers: GPU layers (-1 = all, 0 = CPU only)
            context_size: Context window size
            verbose: Print status messages
            auto_start: Start server immediately
        """
        self.config = ServerConfig(
            model=model,
            host=host,
            port=port,
            n_gpu_layers=n_gpu_layers,
            context_size=context_size,
        )
        self.verbose = verbose
        self.process: Optional[subprocess.Popen] = None
        self._started = False
        
        if auto_start:
            self.start()
    
    def log(self, msg: str) -> None:
        """Log message if verbose."""
        if self.verbose:
            print(f"[LLM Server] {msg}", file=sys.stderr)
    
    def start(self) -> None:
        """Start the llamafile server (FRESH instance)."""
        # First, kill any existing server
        self._kill_existing()
        
        # Verify model file exists
        if not self.config.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.config.model_path}")
        
        self.log(f"Starting {self.config.model} on {self.config.base_url}...")
        
        # Build command
        # Note: llamafiles require 'bash' prefix on some Linux systems
        cmd = [
            "bash",
            str(self.config.model_path),
            "--server",
            "--nobrowser",
            "--host", self.config.host,
            "--port", str(self.config.port),
            "--ctx-size", str(self.config.context_size),
            "--threads", str(self.config.threads),
            "-ngl", "9999",  # Offload all layers to GPU
            "--gpu", "nvidia",
            "--log-disable",  # Reduce log noise
        ]
        
        self.log(f"Command: {' '.join(cmd)}")
        
        # Start process
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,  # Create new process group for clean kill
        )
        
        # Save PID
        PID_FILE.write_text(str(self.process.pid))
        
        # Wait for server to be ready
        if not self._wait_for_ready():
            self.stop()
            raise RuntimeError("Server failed to start within timeout")
        
        self._started = True
        self.log(f"Server ready at {self.config.base_url}")
    
    def stop(self) -> None:
        """Stop the server and clean up."""
        if self.process:
            self.log("Stopping server...")
            try:
                # Kill the entire process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.process = None
        
        # Clean up PID file
        if PID_FILE.exists():
            PID_FILE.unlink()
        
        self._started = False
        self.log("Server stopped")
    
    def _kill_existing(self) -> None:
        """Kill any existing llamafile server."""
        # Check PID file
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                time.sleep(1)
            except (ValueError, ProcessLookupError, PermissionError):
                pass
            PID_FILE.unlink(missing_ok=True)
        
        # Also kill by port
        self._kill_port_process()
    
    def _kill_port_process(self) -> None:
        """Kill any process using our port."""
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{self.config.port}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                for pid in result.stdout.strip().split("\n"):
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except (ValueError, ProcessLookupError):
                        pass
                time.sleep(1)
        except FileNotFoundError:
            pass  # lsof not available
    
    def _wait_for_ready(self) -> bool:
        """Wait for server to respond to health checks."""
        start_time = time.time()
        
        while time.time() - start_time < STARTUP_TIMEOUT:
            if self._is_ready():
                return True
            
            # Check if process died
            if self.process and self.process.poll() is not None:
                stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                self.log(f"Process died: {stderr[:500]}")
                return False
            
            time.sleep(HEALTH_CHECK_INTERVAL)
        
        return False
    
    def _is_ready(self) -> bool:
        """Check if server is responding."""
        try:
            response = requests.get(
                f"{self.config.base_url}/health",
                timeout=2,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def is_running(self) -> bool:
        """Check if server is currently running."""
        return self._started and self._is_ready()
    
    def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send a chat message and get response.
        
        Args:
            message: User message
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            Model response text
        """
        if not self.is_running():
            raise RuntimeError("Server is not running")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        
        response = requests.post(
            f"{self.config.base_url}/v1/chat/completions",
            json={
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=300,  # 5 minutes for long responses
        )
        response.raise_for_status()
        
        data = response.json()
        return data["choices"][0]["message"]["content"]
    
    def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stop: Optional[List[str]] = None,
    ) -> str:
        """
        Text completion (non-chat).
        
        Args:
            prompt: Text prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            stop: Stop sequences
            
        Returns:
            Completion text
        """
        if not self.is_running():
            raise RuntimeError("Server is not running")
        
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stream": False,
        }
        if stop:
            payload["stop"] = stop
        
        response = requests.post(
            f"{self.config.base_url}/completion",
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        
        return response.json()["content"]
    
    def structure_narrative(self, text: str) -> Dict[str, Any]:
        """
        Structure narrative text into JSON format.
        
        This is the main method used by the incremental linter.
        
        Args:
            text: Narrative chapter text
            
        Returns:
            Structured JSON with entities, events, relationships
        """
        system_prompt = """You are a narrative analyst. Extract structured information from story text.

Output ONLY valid JSON with this structure:
{
  "entities": {
    "characters": [{"id": "char_name", "name": "Full Name", "description": "brief description"}],
    "objects": [{"id": "obj_id", "type": "weapon/tool/etc", "description": "brief description"}],
    "locations": [{"id": "loc_id", "description": "brief description"}]
  },
  "events": [
    {
      "id": "e1",
      "type": "action_type",
      "agent": "character_id",
      "patient": "affected_entity_id",
      "location": "location_id",
      "description": "what happened"
    }
  ],
  "relationships": [
    {"type": "parent/friend/enemy/spouse/etc", "from": "char_id", "to": "char_id"}
  ],
  "traits": [
    {"character": "char_id", "trait": "trait_name"}
  ],
  "fluents": [
    {"id": "alive(char_id)", "value": true},
    {"id": "has(char_id, obj_id)", "value": true},
    {"id": "at_location(char_id, loc_id)", "value": true}
  ]
}

Event types include: move, take, give, drop, speak, see, hear, attack, defend, die, kill, create, destroy, meet, leave, enter

Use lowercase with underscores for IDs. Output ONLY the JSON, no explanation."""

        response = self.chat(
            message=f"Extract structured information from this story chapter:\n\n{text[:8000]}",  # Limit to context
            system_prompt=system_prompt,
            temperature=0.3,  # Lower temperature for consistency
            max_tokens=4096,
        )
        
        # Parse JSON from response
        try:
            # Try to find JSON in the response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse JSON: {e}")
            self.log(f"Response was: {response[:500]}...")
            # Return minimal structure
            return {
                "entities": {"characters": [], "objects": [], "locations": []},
                "events": [],
                "relationships": [],
                "traits": [],
                "fluents": [],
            }
    
    def __enter__(self) -> "LlamafileServer":
        """Context manager entry."""
        if not self._started:
            self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures server is killed."""
        self.stop()


@contextmanager
def fresh_llm_server(
    model: str = "mistral-7b",
    port: int = DEFAULT_PORT,
    verbose: bool = True,
):
    """
    Context manager for a fresh LLM server.
    
    Ensures the server is started fresh and killed on exit.
    
    Example:
        with fresh_llm_server(model="mistral-7b") as server:
            result = server.chat("Hello!")
        # Server is killed here
    """
    server = LlamafileServer(
        model=model,
        port=port,
        verbose=verbose,
        auto_start=True,
    )
    try:
        yield server
    finally:
        server.stop()


def get_running_server() -> Optional[Dict[str, Any]]:
    """Get info about currently running server, if any."""
    if not PID_FILE.exists():
        return None
    
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)
        
        # Try to get health
        response = requests.get(f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health", timeout=2)
        if response.status_code == 200:
            return {
                "pid": pid,
                "host": DEFAULT_HOST,
                "port": DEFAULT_PORT,
                "status": "running",
            }
    except (ValueError, ProcessLookupError, requests.RequestException):
        pass
    
    return None


def stop_all_servers() -> None:
    """Stop any running llamafile servers."""
    # Kill by PID file
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        PID_FILE.unlink(missing_ok=True)
    
    # Kill by port
    for port in [8080, 8081, 8082]:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                for pid in result.stdout.strip().split("\n"):
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except (ValueError, ProcessLookupError):
                        pass
        except FileNotFoundError:
            pass


def list_models() -> None:
    """Print available models."""
    print("Available models:")
    print("-" * 60)
    for name, info in MODELS.items():
        path = MODELS_DIR / info["file"]
        exists = "✓" if path.exists() else "✗"
        size = f"{path.stat().st_size / 1e9:.1f} GB" if path.exists() else "N/A"
        print(f"  {exists} {name:20s} {size:>10s}")
        print(f"    {info['description']}")
        print(f"    Context: {info['context_size']} tokens")
    print("-" * 60)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Llamafile LLM Server Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available models
  python llm_server.py list
  
  # Start server with specific model
  python llm_server.py start --model mistral-7b
  
  # Check server status
  python llm_server.py status
  
  # Stop server
  python llm_server.py stop
  
  # Test server with a message
  python llm_server.py test "Hello, how are you?"
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # list command
    subparsers.add_parser("list", help="List available models")
    
    # start command
    start_parser = subparsers.add_parser("start", help="Start LLM server")
    start_parser.add_argument(
        "--model", "-m",
        default="mistral-7b",
        choices=list(MODELS.keys()),
        help="Model to use",
    )
    start_parser.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_PORT,
        help="Port to listen on",
    )
    start_parser.add_argument(
        "--gpu-layers", "-g",
        type=int,
        default=-1,
        help="GPU layers (-1 = all, 0 = CPU only)",
    )
    
    # stop command
    subparsers.add_parser("stop", help="Stop LLM server")
    
    # status command
    subparsers.add_parser("status", help="Check server status")
    
    # test command
    test_parser = subparsers.add_parser("test", help="Test server with a message")
    test_parser.add_argument("message", help="Message to send")
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_models()
    
    elif args.command == "start":
        server = LlamafileServer(
            model=args.model,
            port=args.port,
            n_gpu_layers=args.gpu_layers,
            auto_start=True,
        )
        print(f"Server running at {server.config.base_url}")
        print("Press Ctrl+C to stop...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
    
    elif args.command == "stop":
        stop_all_servers()
        print("All servers stopped")
    
    elif args.command == "status":
        info = get_running_server()
        if info:
            print(f"Server running:")
            print(f"  PID: {info['pid']}")
            print(f"  URL: http://{info['host']}:{info['port']}")
        else:
            print("No server running")
    
    elif args.command == "test":
        info = get_running_server()
        if not info:
            print("Error: No server running. Start one with 'python llm_server.py start'")
            sys.exit(1)
        
        server = LlamafileServer(auto_start=False)
        server._started = True  # Pretend we started it
        response = server.chat(args.message)
        print(f"Response:\n{response}")


if __name__ == "__main__":
    main()
