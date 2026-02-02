"""
Logic-based evaluator using ILASP and Clingo.

This is the main evaluator class that orchestrates:
- LLM extraction (via API clients)
- ASP fact generation
- Clingo violation checking
- ILASP rule learning
"""

import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..state.config import RULES_DIR
from ..state.logging import log
from ..extraction.api_clients import create_api_client
from ..extraction.prompts import UNIFIED_EXTRACTION_PROMPT
from ..merge.json_parser import parse_json_object
from .asp_converter import to_asp, sanitize, sanitize_char
from .ilasp_learner import learn_rules_from_violations as ilasp_learn


class LogicEvaluator:
    """Logic-based evaluator using ILASP and Clingo."""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", temperature: float = 0.0, log_file: Path = None,
                 api_mode: str = "local", api_model: str = None, api_delay: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.api_mode = api_mode
        self.api_model = api_model
        # Create the appropriate API client
        self.api_client = create_api_client(api_mode, api_model, base_url, api_delay)
        # Load multiple rule files for comprehensive checking
        self.rule_files = [
            RULES_DIR / "simple_narrative.lp",
            RULES_DIR / "story_rules.lp",
        ]
        self.mode_declarations = RULES_DIR / "ilasp_mode_declarations.las"
        self.log_file = log_file
        
        # Accumulated knowledge for incremental learning
        self.accumulated_facts: List[str] = []
        self.learned_rules: List[str] = []
        self.chapter_violations_history: List[Dict] = []
        
        # Cross-chapter state tracking
        self.dead_characters: set = set()
        self.character_emotions: Dict[str, str] = {}
        self.established_traits: Dict[str, str] = {}
        self.relationships: Dict[Tuple[str, str], str] = {}
        
        # Global event ID system
        self.next_event_id: int = 1
        
        # Event log
        self.event_log: List[Dict] = []
        
        # Dynamic story rules
        self.story_rules: List[Dict] = []
        
        # Event log file path
        self.event_log_file: Path = None
        
        # Initialize log file
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "w") as f:
                f.write("")
    
    def _log_interaction(self, story: str, variant: str, chapter: str, step: str, 
                         prompt: str, response: str, data: Dict, duration: float):
        """Log a processing step to the log file."""
        if not self.log_file:
            return
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "story": story,
            "variant": variant,
            "chapter": chapter,
            "step": step,
            "duration_seconds": duration,
            "prompt": prompt,
            "response": response,
            "data": data,
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    
    def reset(self):
        """Reset accumulated knowledge (for new story/variant)."""
        self.accumulated_facts = []
        self.learned_rules = []
        self.chapter_violations_history = []
        self.dead_characters = set()
        self.character_emotions = {}
        self.established_traits = {}
        self.relationships = {}
        self.next_event_id = 1
        self.event_log = []
        self.story_rules = []
    
    def _log_events_to_file(self, events: List[Dict], chapter_num: int):
        """Log events with source text to file for debugging."""
        if not self.event_log_file:
            return
        
        for event in events:
            entry = {
                "chapter": chapter_num,
                "event_id": event.get('global_id'),
                "type": event.get('type'),
                "agent": event.get('agent'),
                "patient": event.get('patient'),
                "location": event.get('location'),
                "source_text": event.get('source_text', ''),
            }
            with open(self.event_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
    
    def _assign_global_event_ids(self, events: List[Dict], chapter_num: int) -> List[Dict]:
        """Assign continuous global IDs to events and log them."""
        for event in events:
            event['global_id'] = f"e{self.next_event_id}"
            event['chapter'] = chapter_num
            self.next_event_id += 1
            
            self.event_log.append({
                'id': event['global_id'],
                'type': event.get('type'),
                'agent': event.get('agent'),
                'patient': event.get('patient'),
                'location': event.get('location'),
                'source_text': event.get('source_text', ''),
                'chapter': chapter_num
            })
        
        return events
    
    def _initialize_story_rules(self, initial_rules: List[Dict], relationships: List[Dict],
                                character_locations: List[Dict] = None,
                                character_possessions: List[Dict] = None,
                                temporal_constraints: List[Dict] = None):
        """Initialize story rules from first chapter extraction."""
        character_locations = character_locations or []
        character_possessions = character_possessions or []
        temporal_constraints = temporal_constraints or []
        
        # Process explicit initial_rules
        for rule in initial_rules:
            subject = rule.get('subject', '')
            predicate = rule.get('predicate', '')
            obj = rule.get('object', '')
            
            if subject and predicate:
                rule_type = 'trait' if obj == 'true' else 'relationship'
                self.story_rules.append({
                    'type': rule_type,
                    'subject': subject,
                    'predicate': predicate,
                    'object': obj if obj != 'true' else None,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Initial rule: {subject} {predicate} {obj}", "DEBUG")
        
        # Convert extracted relationships to rules
        for rel in relationships:
            from_char = rel.get('from', '')
            to_char = rel.get('to', '')
            rel_type = rel.get('type', '')
            
            if from_char and to_char and rel_type:
                predicate_map = {
                    'hostile': 'hates',
                    'friendly': 'friendly',
                    'family': 'family',
                    'love': 'loves',
                    'fear': 'fears'
                }
                predicate = predicate_map.get(rel_type, rel_type)
                
                self.story_rules.append({
                    'type': 'relationship',
                    'subject': from_char,
                    'predicate': predicate,
                    'object': to_char,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Relationship rule: {from_char} {predicate} {to_char}", "DEBUG")
        
        # Process character locations
        for loc_rule in character_locations:
            char = loc_rule.get('character', '')
            location = loc_rule.get('location', '')
            
            if char and location:
                self.story_rules.append({
                    'type': 'location',
                    'subject': char,
                    'predicate': 'at',
                    'object': location,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Location rule: {char} at {location}", "DEBUG")
        
        # Process character possessions
        for poss_rule in character_possessions:
            char = poss_rule.get('character', '')
            item = poss_rule.get('item', '')
            
            if char and item:
                self.story_rules.append({
                    'type': 'possession',
                    'subject': char,
                    'predicate': 'has',
                    'object': item,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Possession rule: {char} has {item}", "DEBUG")
        
        # Process temporal constraints
        for temp_rule in temporal_constraints:
            first_type = temp_rule.get('first_event_type', '')
            second_type = temp_rule.get('second_event_type', '')
            
            if first_type and second_type:
                self.story_rules.append({
                    'type': 'temporal',
                    'subject': first_type,
                    'predicate': 'must_precede',
                    'object': second_type,
                    'established_by': 'e0',
                    'valid': True
                })
                log(f"    Temporal rule: {first_type} must_precede {second_type}", "DEBUG")
        
        log(f"  Initialized {len(self.story_rules)} story rules", "INFO")
    
    def _update_rules_from_events(self, events: List[Dict]):
        """Update story rules based on modifier events."""
        positive_modifiers = {
            'forgive', 'forgives', 'reconcile', 'reconciles', 'apologize', 'apologizes',
            'befriend', 'befriends', 'accept', 'accepts', 'save', 'saves', 'rescue', 'rescues'
        }
        
        negative_modifiers = {
            'betray', 'betrays', 'attack', 'attacks', 'insult', 'insults',
            'abandon', 'abandons', 'deceive', 'deceives', 'hurt', 'hurts',
            'reject', 'rejects', 'steal_from', 'steals_from'
        }
        
        for event in events:
            event_type = event.get('type', '').lower()
            agent = event.get('agent')
            patient = event.get('patient')
            event_id = event.get('global_id')
            
            if not agent or not patient:
                continue
            
            if event_type in positive_modifiers:
                self._modify_rule(agent, patient, 'friendly', event_id)
                log(f"    Event {event_id} ({event_type}): {agent} → {patient} now friendly", "DEBUG")
            elif event_type in negative_modifiers:
                self._modify_rule(agent, patient, 'hostile', event_id)
                log(f"    Event {event_id} ({event_type}): {agent} → {patient} now hostile", "DEBUG")
    
    def _modify_rule(self, subject: str, obj: str, new_predicate: str, event_id: str):
        """Modify an existing rule or create a new one."""
        subject = sanitize_char(subject)
        obj = sanitize_char(obj)
        
        # Find and invalidate existing rule
        for rule in self.story_rules:
            if (rule['type'] == 'relationship' and 
                rule['subject'] == subject and 
                rule['object'] == obj and
                rule['valid']):
                rule['valid'] = False
                log(f"    Invalidated rule: {subject} {rule['predicate']} {obj} (by {event_id})", "DEBUG")
        
        # Create new rule
        self.story_rules.append({
            'type': 'relationship',
            'subject': subject,
            'predicate': new_predicate,
            'object': obj,
            'established_by': event_id,
            'valid': True
        })

    def _accumulate_cross_chapter_state(self, facts: str) -> List[str]:
        """Extract and accumulate important cross-chapter state from current facts."""
        state_facts = []
        
        for line in facts.split('\n'):
            line = line.strip()
            
            if line.startswith('is_dead('):
                match = re.match(r'is_dead\(([^)]+)\)\.', line)
                if match:
                    char = match.group(1)
                    self.dead_characters.add(char)
            
            if line.startswith('character_emotion('):
                match = re.match(r'character_emotion\(([^,]+),\s*([^)]+)\)\.', line)
                if match:
                    char, emotion = match.group(1), match.group(2)
                    self.character_emotions[char] = emotion
                    if emotion in ['nasty', 'kind', 'hostile', 'friendly', 'cruel', 'warm', 'cold']:
                        if char not in self.established_traits:
                            self.established_traits[char] = emotion
            
            if line.startswith('relationship('):
                match = re.match(r'relationship\(([^,]+),\s*([^,]+),\s*([^)]+)\)\.', line)
                if match:
                    char1, char2, rel_type = match.group(1), match.group(2), match.group(3)
                    self.relationships[(char1, char2)] = rel_type
        
        for char in self.dead_characters:
            state_facts.append(f"is_dead({char}).")
        
        for char, emotion in self.character_emotions.items():
            state_facts.append(f"previous_emotion({char}, {emotion}).")
        
        for char, trait in self.established_traits.items():
            state_facts.append(f"established_trait({char}, {trait}).")
        
        for (char1, char2), rel_type in self.relationships.items():
            state_facts.append(f"previous_relationship({char1}, {char2}, {rel_type}).")
        
        return state_facts

    def _accumulate_persistent_facts(self, facts: str) -> None:
        """Accumulate only PERSISTENT facts that should carry across chapters."""
        for line in facts.split('\n'):
            line = line.strip()
            if not line or line.startswith('%'):
                continue
            
            if line.startswith('character(') or line.startswith('location_entity('):
                if line not in self.accumulated_facts:
                    self.accumulated_facts.append(line)

    def _validate_and_fix_events(self, events: List[Dict]) -> List[Dict]:
        """Validate and fix extracted events post-processing."""
        no_patient_actions = {
            'travel', 'walk', 'run', 'fly', 'drive', 'move', 'go', 'leave', 'arrive',
            'escape', 'flee', 'return', 'enter', 'exit', 'climb', 'jump', 'land',
            'die', 'dies', 'died', 'death', 'faint', 'collapse', 'wake', 'sleep',
            'rest', 'hide', 'wait', 'stand', 'sit', 'kneel', 'bow', 'fall',
            'think', 'read', 'write', 'sing', 'cry', 'laugh', 'scream', 'shout',
            'practice', 'train', 'study', 'work', 'eat', 'drink',
            'discover', 'realize', 'understand', 'learn', 'notice', 'observe',
        }
        
        requires_patient_actions = {
            'attack', 'hit', 'punch', 'kick', 'stab', 'shoot', 'kill', 'murder',
            'give', 'take', 'steal', 'borrow', 'lend', 'receive',
            'help', 'save', 'rescue', 'heal', 'cure', 'protect',
            'meet', 'greet', 'hug', 'kiss', 'marry',
        }
        
        fixed_events = []
        for event in events:
            agent = event.get('agent')
            patient = event.get('patient')
            event_type = event.get('type', '').lower()
            
            if agent and patient and str(agent).lower() == str(patient).lower():
                if event_type in no_patient_actions:
                    event['patient'] = None
                    log(f"    Fixed reflexive action: {event_type} agent={agent}", "DEBUG")
                elif event_type in requires_patient_actions:
                    log(f"    Suspicious self-action: {event_type} agent={agent}", "DEBUG")
                else:
                    event['patient'] = None
                    log(f"    Fixed unknown action as reflexive: {event_type} agent={agent}", "DEBUG")
            
            fixed_events.append(event)
        
        return fixed_events

    def _llm_extract(self, prompt: str, max_tokens: int = 512, timeout: int = 120) -> str:
        """Make a single LLM call and return the response text."""
        return self.api_client.extract(prompt, max_tokens=max_tokens, timeout=timeout)
    
    def _structure_chapter(self, chapter_text: str, max_retries: int = 2) -> Tuple[Dict, str, str]:
        """Use LLM to structure chapter into JSON using a single unified prompt."""
        unified_prompt = UNIFIED_EXTRACTION_PROMPT.format(chapter_text=chapter_text)

        try:
            log(f"  Calling LLM for unified extraction...", "DEBUG")
            response = self._llm_extract(unified_prompt, max_tokens=8192, timeout=300)
            log(f"  LLM response length: {len(response)} chars", "DEBUG")
            if len(response) < 100:
                log(f"  Short response content: {response}", "WARN")
            parsed = parse_json_object(response)
            
            if not parsed:
                log(f"First parse failed (empty result). Response preview: {response[:500] if response else 'EMPTY'}", "WARN")
                log("Retrying LLM call...", "DEBUG")
                response = self._llm_extract(unified_prompt, max_tokens=12288, timeout=300)
                log(f"  Retry response length: {len(response)} chars", "DEBUG")
                parsed = parse_json_object(response)
            
            # Deduplicate arrays by ID
            def dedupe_by_id(arr):
                if not arr:
                    return []
                seen = set()
                result = []
                for item in arr:
                    item_id = item.get("id", "") if isinstance(item, dict) else str(item)
                    base_id = re.sub(r'_\d+$', '', item_id)
                    base_id = re.sub(r'(.+?)_\1', r'\1', base_id)
                    if base_id not in seen and item_id not in seen:
                        seen.add(item_id)
                        seen.add(base_id)
                        result.append(item)
                return result
            
            parsed["characters"] = dedupe_by_id(parsed.get("characters", []))
            parsed["locations"] = dedupe_by_id(parsed.get("locations", []))
            parsed["items"] = dedupe_by_id(parsed.get("items", []))
            parsed["events"] = dedupe_by_id(parsed.get("events", []))
            
            result = {
                "entities": {
                    "characters": parsed.get("characters", []),
                    "locations": parsed.get("locations", []),
                    "items": parsed.get("items", []),
                    "relationships": parsed.get("relationships", [])
                },
                "events": self._validate_and_fix_events(parsed.get("events", [])),
                "initial_rules": parsed.get("initial_rules", []),
                "character_locations": parsed.get("character_locations", []),
                "character_possessions": parsed.get("character_possessions", []),
                "temporal_constraints": parsed.get("temporal_constraints", [])
            }
            
            # Log warnings if limits exceeded
            MAX_CHARS = 15
            MAX_LOCS = 10  
            MAX_ITEMS = 10
            MAX_EVENTS = 12
            MAX_RELS = 5
            
            if len(result["entities"]["characters"]) > MAX_CHARS:
                log(f"  WARNING: Characters ({len(result['entities']['characters'])}) exceeds suggested limit ({MAX_CHARS})", "WARN")
            if len(result["entities"]["locations"]) > MAX_LOCS:
                log(f"  WARNING: Locations ({len(result['entities']['locations'])}) exceeds suggested limit ({MAX_LOCS})", "WARN")
            if len(result["entities"]["items"]) > MAX_ITEMS:
                log(f"  WARNING: Items ({len(result['entities']['items'])}) exceeds suggested limit ({MAX_ITEMS})", "WARN")
            if len(result["events"]) > MAX_EVENTS:
                log(f"  WARNING: Events ({len(result['events'])}) exceeds suggested limit ({MAX_EVENTS})", "WARN")
            if len(result["entities"]["relationships"]) > MAX_RELS:
                log(f"  WARNING: Relationships ({len(result['entities']['relationships'])}) exceeds suggested limit ({MAX_RELS})", "WARN")
            
            if result.get("initial_rules"):
                log(f"  Extracted {len(result['initial_rules'])} initial rules", "DEBUG")
            if result.get("character_locations"):
                log(f"  Extracted {len(result['character_locations'])} character locations", "DEBUG")
            if result.get("character_possessions"):
                log(f"  Extracted {len(result['character_possessions'])} character possessions", "DEBUG")
            if result.get("temporal_constraints"):
                log(f"  Extracted {len(result['temporal_constraints'])} temporal constraints", "DEBUG")
            
            prompt_summary = "Unified extraction"
            response_summary = f"chars={len(result['entities']['characters'])}, locs={len(result['entities']['locations'])}, items={len(result['entities']['items'])}, events={len(result['events'])}, rels={len(result['entities']['relationships'])}, rules={len(result.get('initial_rules', []))}"
            
            log(f"  Extracted: {response_summary}", "DEBUG")
            
            return result, prompt_summary, response_summary
            
        except Exception as e:
            import traceback
            log(f"Unified extraction failed: {type(e).__name__}: {e}", "ERROR")
            log(f"Traceback: {traceback.format_exc()}", "DEBUG")
            return {
                "entities": {"characters": [], "locations": [], "items": [], "relationships": []},
                "events": [],
                "initial_rules": [],
                "character_locations": [],
                "character_possessions": [],
                "temporal_constraints": []
            }, f"Unified extraction (failed: {type(e).__name__})", "chars=0, locs=0, items=0, events=0, rules=0"
    
    def _to_asp(self, data: Dict, chapter_num: int) -> str:
        """Convert structured JSON to ASP facts."""
        return to_asp(data, chapter_num, self.story_rules)
    
    def _learn_rules_from_violations(self, current_facts: str, violations: List[Dict], chapter_num: int) -> List[str]:
        """Use ILASP to learn rules from detected violations."""
        new_rules = ilasp_learn(
            current_facts, 
            violations, 
            chapter_num,
            self.accumulated_facts,
            self.learned_rules,
            self.mode_declarations
        )
        self.learned_rules.extend(new_rules)
        return new_rules
    
    def _violations_to_structured_output(self, violations: List[Dict]) -> List[Dict]:
        """Convert violations to structured output format."""
        errors = []
        for v in violations:
            event_id = v.get("event", "")
            event_time = 0
            if event_id.startswith('e') and event_id[1:].isdigit():
                event_time = int(event_id[1:])
            
            severity = "soft"
            hard_types = {"dead_agent", "dead_patient", "invalid_time_order", 
                          "circular_dependency", "self_contradiction"}
            if v.get("type") in hard_types:
                severity = "hard"
            elif v.get("category") == "system":
                severity = "hard"
            
            errors.append({
                "rule": f"{v.get('category', 'unknown')}/{v.get('type', 'unknown')}",
                "category": v.get("category", "unknown"),
                "type": v.get("type", "unknown"),
                "event_id": event_id,
                "event_time": event_time,
                "entities": [v.get("detail", "")] if v.get("detail") else [],
                "severity": severity,
                "source_text": v.get("source_text", ""),
                "description": f"Violation: {v.get('type', 'unknown')}",
                "error_text": v.get("detail", ""),
            })
        return errors
    
    def _interpret_violations(self, violations: List[Dict], chapter_text: str, structured: Dict) -> List[Dict]:
        """Use LLM to interpret violations and produce natural language errors."""
        import urllib.request
        
        if not violations:
            return []
        
        violation_summary = []
        for v in violations:
            violation_summary.append({
                "category": v.get("category", "unknown"),
                "type": v.get("type", "unknown"),
                "event": v.get("event", ""),
                "detail": v.get("detail", ""),
            })
        
        chapter_excerpt = chapter_text[:3000]
        
        prompt = f"""---CHAPTER EXCERPT---
{chapter_excerpt}
---END CHAPTER---

The following logical violations were detected in this chapter:
{json.dumps(violation_summary, indent=2)}

For each violation, find the relevant text in the chapter and explain the error.

Return JSON array with this exact format:
[{{"category": "causality|coherence|temporal|location|emotional", "description": "what the error is", "error_text": "the exact quote from the chapter with the error"}}]

Return ONLY the JSON array, nothing else."""

        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "You interpret logical violations and find corresponding text. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
        }
        
        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
                response_text = data["choices"][0]["message"]["content"]
            
            cleaned = re.sub(r'```json\s*', '', response_text)
            cleaned = re.sub(r'```\s*', '', cleaned)
            
            match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if match:
                errors = json.loads(match.group())
                return errors
                
        except Exception as e:
            log(f"Interpretation failed: {e}", "WARN")
        
        # Fallback
        errors = []
        for v in violations:
            desc = v.get("description", f"Violation: {v.get('type', 'unknown')}")
            source = v.get("source_text", "")
            if source:
                desc = f"{desc} - \"{source}\""
            errors.append({
                "category": v.get("category", "unknown"),
                "description": desc,
                "error_text": v.get("detail", ""),
                "event": v.get("event", ""),
                "source_text": source,
            })
        return errors
    
    def _check_with_clingo(self, facts: str, chapter_num: int) -> List[Dict]:
        """Use Clingo to find violations."""
        from engine.asp_diagnostics import log_asp_universe
        
        violations = []
        
        try:
            import clingo
        except ImportError:
            log("Clingo not available", "WARN")
            return []
        
        state_facts = self._accumulate_cross_chapter_state(facts)
        
        program_parts = [facts]
        
        if state_facts:
            program_parts.append("\n% Cross-chapter state:")
            program_parts.extend(state_facts)
        
        if self.accumulated_facts:
            program_parts.append("\n% Previously introduced entities:")
            program_parts.extend(self.accumulated_facts)
        if self.learned_rules:
            program_parts.append("\n% Learned rules:")
            program_parts.extend(self.learned_rules)
        
        combined = "\n".join(program_parts)
        
        # Phase 8.8: Log ASP universe size diagnostics (optional, no overhead when disabled)
        log_asp_universe(combined, chapter_num)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(combined)
            facts_path = f.name
        
        try:
            ctl = clingo.Control(["--warn=none"])
            
            rules_loaded = 0
            for rule_file in self.rule_files:
                if rule_file.exists():
                    ctl.load(str(rule_file))
                    rules_loaded += 1
                else:
                    log(f"Rules file not found: {rule_file}", "WARN")
            
            if rules_loaded == 0:
                log("No rule files loaded!", "ERROR")
            
            ctl.load(facts_path)
            ctl.ground([("base", [])])
            
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "violation":
                            parts = [str(arg) for arg in atom.arguments]
                            event_id = parts[2] if len(parts) > 2 else ""
                            
                            source_text = ""
                            if event_id:
                                source_pattern = f'event_source({event_id}, "'
                                for line in combined.split('\n'):
                                    if source_pattern in line:
                                        try:
                                            start = line.index('"') + 1
                                            end = line.rindex('"')
                                            source_text = line[start:end]
                                        except ValueError:
                                            pass
                                        break
                            
                            violations.append({
                                "category": parts[0] if len(parts) > 0 else "unknown",
                                "type": parts[1] if len(parts) > 1 else "unknown",
                                "event": event_id,
                                "detail": parts[3] if len(parts) > 3 else "",
                                "source_text": source_text,
                                "description": f"Violation: {parts[1] if len(parts) > 1 else 'unknown'}",
                            })
                            
        except Exception as e:
            log(f"Clingo error: {e}", "ERROR")
        finally:
            os.unlink(facts_path)
        
        return violations

    def evaluate_chapter(self, chapter_text: str, chapter_num: int, 
                         story: str = "", variant: str = "", chapter_name: str = "") -> Tuple[List[Dict], float]:
        """Evaluate a chapter using logic-based approach."""
        start_time = time.time()
        
        # Step 1: Structure with LLM
        structured, struct_prompt, struct_response = self._structure_chapter(chapter_text)
        
        self._log_interaction(
            story, variant, chapter_name, "step1_structure",
            struct_prompt, struct_response, structured,
            time.time() - start_time
        )
        
        # Step 2: Assign global event IDs
        events = structured.get("events", [])
        events = self._assign_global_event_ids(events, chapter_num)
        structured["events"] = events
        
        log(f"    Assigned global IDs: e{self.next_event_id - len(events)} to e{self.next_event_id - 1}", "DEBUG")
        
        # Step 3: Initialize or update story rules
        if chapter_num == 0:
            initial_rules = structured.get("initial_rules", [])
            relationships = structured.get("entities", {}).get("relationships", [])
            character_locations = structured.get("character_locations", [])
            character_possessions = structured.get("character_possessions", [])
            temporal_constraints = structured.get("temporal_constraints", [])
            if initial_rules or relationships or character_locations or character_possessions or temporal_constraints:
                self._initialize_story_rules(
                    initial_rules, relationships, 
                    character_locations, character_possessions, temporal_constraints
                )
        
        self._update_rules_from_events(events)
        self._log_events_to_file(events, chapter_num)
        
        # Step 4: Convert to ASP + Check with Clingo
        facts = self._to_asp(structured, chapter_num)
        violations = self._check_with_clingo(facts, chapter_num)
        
        self._log_interaction(
            story, variant, chapter_name, "step2_clingo",
            facts, "", {"violations": violations, "learned_rules_count": len(self.learned_rules), "story_rules_count": len(self.story_rules)},
            time.time() - start_time
        )
        
        # Step 5: ILASP Learning
        new_rules = self._learn_rules_from_violations(facts, violations, chapter_num)
        self._accumulate_persistent_facts(facts)
        
        if violations:
            self.chapter_violations_history.append({
                "chapter": chapter_num,
                "violations": violations,
            })
        
        self._log_interaction(
            story, variant, chapter_name, "step3_ilasp",
            "", "", {"new_rules": new_rules, "total_rules": len(self.learned_rules)},
            time.time() - start_time
        )
        
        # Step 6: LLM Interpretation
        errors = self._interpret_violations(violations, chapter_text, structured)
        
        self._log_interaction(
            story, variant, chapter_name, "step4_interpret",
            "", "", {"errors": errors},
            time.time() - start_time
        )
        
        duration = time.time() - start_time
        return errors, duration

    def evaluate_chapter_v2(self, chapter_text: str, chapter_num: int, 
                            story: str = "", variant: str = "", chapter_name: str = "",
                            sequential: bool = False) -> Tuple[List[Dict], float]:
        """Phase 4 refactored evaluate_chapter with structured output only."""
        start_time = time.time()
        
        # Step 1: Structure with LLM
        structured, struct_prompt, struct_response = self._structure_chapter(chapter_text)
        
        self._log_interaction(
            story, variant, chapter_name, "step1_structure",
            struct_prompt, struct_response, structured,
            time.time() - start_time
        )
        
        # Step 2: Assign global event IDs
        events = structured.get("events", [])
        events = self._assign_global_event_ids(events, chapter_num)
        structured["events"] = events
        
        log(f"    Assigned global IDs: e{self.next_event_id - len(events)} to e{self.next_event_id - 1}", "DEBUG")
        
        # Step 3: Initialize or update story rules
        if chapter_num == 0:
            initial_rules = structured.get("initial_rules", [])
            relationships = structured.get("entities", {}).get("relationships", [])
            character_locations = structured.get("character_locations", [])
            character_possessions = structured.get("character_possessions", [])
            temporal_constraints = structured.get("temporal_constraints", [])
            if initial_rules or relationships or character_locations or character_possessions or temporal_constraints:
                self._initialize_story_rules(
                    initial_rules, relationships, 
                    character_locations, character_possessions, temporal_constraints
                )
        
        self._update_rules_from_events(events)
        self._log_events_to_file(events, chapter_num)
        
        # Step 4: Convert to ASP + Check with Clingo
        facts = self._to_asp(structured, chapter_num)
        violations = self._check_with_clingo(facts, chapter_num)
        
        self._log_interaction(
            story, variant, chapter_name, "step2_clingo",
            facts, "", {"violations": violations, "learned_rules_count": len(self.learned_rules), "story_rules_count": len(self.story_rules)},
            time.time() - start_time
        )
        
        # Step 5: ILASP Learning
        new_rules = self._learn_rules_from_violations(facts, violations, chapter_num)
        self._accumulate_persistent_facts(facts)
        
        if violations:
            self.chapter_violations_history.append({
                "chapter": chapter_num,
                "violations": violations,
            })
        
        self._log_interaction(
            story, variant, chapter_name, "step3_ilasp",
            "", "", {"new_rules": new_rules, "total_rules": len(self.learned_rules)},
            time.time() - start_time
        )
        
        # NO LLM Interpretation - Direct structured output
        errors = self._violations_to_structured_output(violations)
        
        self._log_interaction(
            story, variant, chapter_name, "step4_structured_output",
            "", "", {"errors": errors, "mode": "structured_only"},
            time.time() - start_time
        )
        
        duration = time.time() - start_time
        return errors, duration
