#!/usr/bin/env python3
"""
Quick debug script to test a single chapter extraction.
Usage: python scripts/debug_chapter.py modified_books/Harry\ Potter/007.txt
"""

import sys
import json
import re
import urllib.request
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_chapter.py <chapter_file>")
        sys.exit(1)
    
    chapter_path = Path(sys.argv[1])
    if not chapter_path.exists():
        print(f"File not found: {chapter_path}")
        sys.exit(1)
    
    print(f"Reading chapter: {chapter_path}")
    chapter_text = chapter_path.read_text()
    print(f"Chapter length: {len(chapter_text)} chars")
    
    # Build the prompt (simplified version of what run_narrative_experiment uses)
    prompt = f"""Analyze this chapter and extract structured narrative data.

CHAPTER TEXT:
{chapter_text}

OUTPUT JSON with this exact structure:
{{
  "characters": [
    {{"id": "snake_case_id", "name": "Display Name", "emotion": "happy|sad|angry|afraid|neutral|calm", "state": "normal|injured|dead|unconscious"}}
  ],
  "locations": [
    {{"id": "snake_case_id", "name": "Display Name"}}
  ],
  "items": [
    {{"id": "snake_case_id", "name": "Display Name", "state": "found|hidden|lost|destroyed|intact"}}
  ],
  "events": [
    {{"id": "e1", "type": "meet|talk|fight|leave|arrive|discover|help|attack|die", "agent": "character_id", "patient": "character_or_item_id_or_null", "location": "location_id"}}
  ],
  "relationships": [
    {{"from": "character_id", "to": "character_id", "type": "friendly|hostile|neutral"}}
  ]
}}

CRITICAL RULES:
1. Extract 5-15 key events ONLY
2. Use snake_case for all IDs
3. Use 'fight' ONLY for physical confrontations or hostile arguments, NOT for friendly banter
4. Output ONLY valid JSON, nothing else

YOUR JSON:"""

    print(f"\nPrompt length: {len(prompt)} chars")
    print(f"Sending to LLM...")
    
    payload = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": "You are a narrative analysis assistant. Output ONLY valid JSON, nothing else."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
        "repetition_penalty": 1.1,
    }
    
    try:
        import time
        start = time.time()
        
        req = urllib.request.Request(
            "http://localhost:8080/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
            response = data["choices"][0]["message"]["content"]
            elapsed = time.time() - start
            
            print(f"\n=== LLM RESPONSE (elapsed: {elapsed:.1f}s) ===")
            print(f"Response length: {len(response)} chars")
            print(f"\n--- RAW RESPONSE START ---")
            print(response[:5000] if len(response) > 5000 else response)
            if len(response) > 5000:
                print(f"\n... (truncated, full length: {len(response)} chars)")
            print("--- RAW RESPONSE END ---\n")
            
            # Try to parse
            # Remove think tags
            cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
            cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL)
            cleaned = re.sub(r'```json\s*', '', cleaned)
            cleaned = re.sub(r'```\s*', '', cleaned)
            
            print(f"Cleaned response length: {len(cleaned)} chars")
            
            # Find JSON
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                try:
                    obj = json.loads(match.group())
                    print(f"\n✓ Successfully parsed JSON!")
                    print(f"  Characters: {len(obj.get('characters', []))}")
                    print(f"  Locations: {len(obj.get('locations', []))}")
                    print(f"  Items: {len(obj.get('items', []))}")
                    print(f"  Events: {len(obj.get('events', []))}")
                    print(f"  Relationships: {len(obj.get('relationships', []))}")
                except json.JSONDecodeError as e:
                    print(f"\n✗ JSON parse error: {e}")
                    print(f"  Matched text (first 500 chars): {match.group()[:500]}")
            else:
                print(f"\n✗ No JSON object found in response!")
                if cleaned:
                    print(f"  Cleaned response preview: {cleaned[:500]}")
                    
    except Exception as e:
        import traceback
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()
