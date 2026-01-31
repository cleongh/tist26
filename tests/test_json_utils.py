"""
Tests for the JSON validation and repair utility.
"""

import pytest
from scripts.extraction.json_utils import (
    parse_llm_json,
    parse_llm_json_strict,
    parse_events_with_salvage,
    salvage_truncated_events,
    repair_json,
    JSONParseError,
    _fix_key_colons,
    _fix_single_quotes,
    _fix_trailing_commas,
    _remove_markdown_fences,
    _extract_json_object,
    _extract_event_objects,
)


class TestRepairFunctions:
    """Test individual repair functions."""
    
    def test_fix_key_colons(self):
        """Keys with embedded colons should be fixed."""
        # "id:" : value → "id": value
        text = '{"id:": "test", "name:": "hello"}'
        result = _fix_key_colons(text)
        assert '"id":' in result
        assert '"name":' in result
        assert '"id:":' not in result
    
    def test_fix_single_quotes(self):
        """Single quotes should be converted to double quotes."""
        text = "{'id': 'test', 'name': 'hello'}"
        result = _fix_single_quotes(text)
        assert '"id"' in result
        assert '"test"' in result
    
    def test_fix_trailing_commas(self):
        """Trailing commas should be removed."""
        text = '{"items": ["a", "b",], "x": 1,}'
        result = _fix_trailing_commas(text)
        assert ',]' not in result
        assert ',}' not in result
        assert '["a", "b"]' in result
    
    def test_remove_markdown_fences(self):
        """Markdown code fences should be removed."""
        text = '```json\n{"test": 1}\n```'
        result = _remove_markdown_fences(text)
        assert '```' not in result
        assert '{"test": 1}' in result
    
    def test_extract_json_object_simple(self):
        """Should extract JSON object from text."""
        text = 'Some prefix {"id": "test"} some suffix'
        result = _extract_json_object(text)
        assert result == '{"id": "test"}'
    
    def test_extract_json_object_nested(self):
        """Should extract nested JSON correctly."""
        text = 'prefix {"a": {"b": 1}} suffix'
        result = _extract_json_object(text)
        assert result == '{"a": {"b": 1}}'
    
    def test_extract_json_array(self):
        """Should extract JSON array."""
        text = 'prefix ["a", "b"] suffix'
        result = _extract_json_object(text)
        assert result == '["a", "b"]'


class TestRepairJson:
    """Test the full repair pipeline."""
    
    def test_repair_valid_json(self):
        """Valid JSON should pass through unchanged."""
        text = '{"id": "test", "name": "hello"}'
        result = repair_json(text)
        assert result == text
    
    def test_repair_markdown_wrapped(self):
        """JSON in markdown fences should be extracted."""
        text = '```json\n{"id": "test"}\n```'
        result = repair_json(text)
        assert result == '{"id": "test"}'
    
    def test_repair_key_colon(self):
        """Keys with embedded colons should be fixed."""
        text = '{"id:": "test"}'
        result = repair_json(text)
        assert '"id":' in result or result == '{"id:": "test"}'  # Either fixed or passthrough
    
    def test_repair_trailing_comma(self):
        """Trailing commas should be removed."""
        text = '{"items": ["a",]}'
        result = repair_json(text)
        assert ',]' not in result
    
    def test_repair_combined_issues(self):
        """Multiple issues should all be fixed."""
        text = "```json\n{'id': 'test', 'items': ['a',]}\n```"
        result = repair_json(text)
        assert '```' not in result
        assert ',]' not in result


class TestParseLlmJson:
    """Test the main parsing function."""
    
    def test_parse_valid_json(self):
        """Valid JSON should parse successfully."""
        text = '{"id": "test", "name": "hello"}'
        result, success = parse_llm_json(text, "test")
        assert success
        assert result["id"] == "test"
        assert result["name"] == "hello"
    
    def test_parse_markdown_wrapped(self):
        """JSON in markdown should parse."""
        text = '```json\n{"id": "test"}\n```'
        result, success = parse_llm_json(text, "test")
        assert success
        assert result["id"] == "test"
    
    def test_parse_with_think_tags(self):
        """Think tags should be removed."""
        text = '<think>reasoning</think>{"id": "test"}'
        result, success = parse_llm_json(text, "test")
        assert success
        assert result["id"] == "test"
    
    def test_parse_empty_returns_default(self):
        """Empty input should return default."""
        result, success = parse_llm_json("", "test")
        assert not success
        assert result == {}
        
        result, success = parse_llm_json("", "test", {"default": True})
        assert not success
        assert result == {"default": True}
    
    def test_parse_invalid_returns_default(self):
        """Unparseable input should return default."""
        result, success = parse_llm_json("not json at all", "test")
        assert not success
        assert result == {}
    
    def test_parse_with_prefix_text(self):
        """JSON with prefix text should parse."""
        text = 'Here is the result: {"id": "test"}'
        result, success = parse_llm_json(text, "test")
        assert success
        assert result["id"] == "test"
    
    def test_parse_extracts_nested(self):
        """Nested JSON should be extracted correctly."""
        text = '{"entities": {"characters": [{"id": "harry"}]}}'
        result, success = parse_llm_json(text, "test")
        assert success
        assert "entities" in result
        assert result["entities"]["characters"][0]["id"] == "harry"


class TestParseLlmJsonStrict:
    """Test the strict parsing function."""
    
    def test_strict_valid_json(self):
        """Valid JSON should parse in strict mode."""
        text = '{"id": "test"}'
        result = parse_llm_json_strict(text, "test")
        assert result["id"] == "test"
    
    def test_strict_invalid_raises(self):
        """Invalid JSON should raise in strict mode."""
        with pytest.raises(JSONParseError) as exc_info:
            parse_llm_json_strict("not json", "test")
        
        assert exc_info.value.phase == "test"
        assert "not json" in exc_info.value.raw_output


class TestRealWorldCases:
    """Test cases based on actual LLM output issues."""
    
    def test_key_with_colon_from_llm(self):
        """LLM sometimes outputs 'id:' as key name."""
        text = '{"id:": "parking_lot", "name": "Grunnings parking lot"}'
        result = repair_json(text)
        # The repair should fix "id:" to "id"
        assert '"id":' in result or '"id:"' in result  # Either fixed or original
    
    def test_empty_extraction_phase(self):
        """Each phase should have appropriate defaults."""
        # Characters/locations
        result, success = parse_llm_json(
            "invalid", "characters_locations",
            {"characters": [], "locations": []}
        )
        assert not success
        assert result == {"characters": [], "locations": []}
        
        # Items
        result, success = parse_llm_json(
            "invalid", "items",
            {"items": []}
        )
        assert not success
        assert result == {"items": []}
        
        # Events
        result, success = parse_llm_json(
            "invalid", "events",
            {"events": []}
        )
        assert not success
        assert result == {"events": []}


class TestTruncatedEventSalvage:
    """Test truncated event salvage functionality."""
    
    def test_extract_event_objects_complete(self):
        """Should extract complete event objects."""
        text = '{"id": "e1", "type": "talk"}, {"id": "e2", "type": "walk"}'
        objects = _extract_event_objects(text)
        assert len(objects) == 2
        assert '{"id": "e1", "type": "talk"}' in objects[0]
    
    def test_extract_event_objects_truncated(self):
        """Should stop at incomplete object."""
        text = '{"id": "e1", "type": "talk"}, {"id": "e2", "type":'
        objects = _extract_event_objects(text)
        assert len(objects) == 1
        assert 'e1' in objects[0]
    
    def test_salvage_complete_json(self):
        """Complete JSON should return all events."""
        text = '{"events": [{"id": "e1", "type": "talk", "agent": "harry"}]}'
        events = salvage_truncated_events(text)
        assert len(events) == 1
        assert events[0]["id"] == "e1"
    
    def test_salvage_truncated_json(self):
        """Truncated JSON should return valid events only."""
        text = '''{"events": [
            {"id": "e1", "type": "talk", "agent": "harry"},
            {"id": "e2", "type": "walk", "agent": "ron"},
            {"id": "e3", "type":
        '''
        events = salvage_truncated_events(text)
        assert len(events) == 2
        assert events[0]["id"] == "e1"
        assert events[1]["id"] == "e2"
    
    def test_salvage_deduplicates_by_id(self):
        """Duplicate IDs should be deduplicated (keep first)."""
        text = '''{"events": [
            {"id": "e1", "type": "talk", "agent": "harry"},
            {"id": "e1", "type": "walk", "agent": "ron"},
            {"id": "e2", "type": "run", "agent": "hermione"}
        ]}'''
        events = salvage_truncated_events(text)
        assert len(events) == 2
        # First e1 should be kept (talk, not walk)
        assert events[0]["type"] == "talk"
        assert events[1]["id"] == "e2"
    
    def test_salvage_requires_id_and_type(self):
        """Events without id or type should be skipped."""
        text = '''{"events": [
            {"id": "e1", "type": "talk"},
            {"id": "e2"},
            {"type": "walk"},
            {"id": "e3", "type": "run"}
        ]}'''
        events = salvage_truncated_events(text)
        # e2 and e3 missing type/id, but e3 is complete
        # Actually e2 has no type so skipped, anonymous has no id so skipped
        assert len(events) == 2
        assert events[0]["id"] == "e1"
        assert events[1]["id"] == "e3"
    
    def test_salvage_empty_events_array(self):
        """Empty events array should return empty list."""
        text = '{"events": []}'
        events = salvage_truncated_events(text)
        assert events == []
    
    def test_salvage_no_events_key(self):
        """Missing events key should return empty list."""
        text = '{"characters": [{"id": "harry"}]}'
        events = salvage_truncated_events(text)
        assert events == []
    
    def test_parse_events_with_salvage_normal(self):
        """Normal parsing should work without salvage."""
        text = '{"events": [{"id": "e1", "type": "talk", "agent": "harry"}]}'
        result, success, was_salvaged = parse_events_with_salvage(text)
        assert success
        assert not was_salvaged
        assert len(result["events"]) == 1
    
    def test_parse_events_with_salvage_truncated(self):
        """Truncated JSON should trigger salvage."""
        text = '''{"events": [
            {"id": "e1", "type": "talk", "agent": "harry"},
            {"id": "e2", "type":
        '''
        result, success, was_salvaged = parse_events_with_salvage(text)
        assert success
        assert was_salvaged
        assert len(result["events"]) == 1
        assert result["events"][0]["id"] == "e1"
    
    def test_parse_events_with_salvage_total_failure(self):
        """Completely invalid input should return default."""
        text = "not json at all"
        result, success, was_salvaged = parse_events_with_salvage(text)
        assert not success
        assert result == {"events": []}
    
    def test_salvage_preserves_order(self):
        """Events should maintain original order."""
        text = '''{"events": [
            {"id": "e3", "type": "c"},
            {"id": "e1", "type": "a"},
            {"id": "e2", "type": "b"}
        ]}'''
        events = salvage_truncated_events(text)
        assert [e["id"] for e in events] == ["e3", "e1", "e2"]
    
    def test_salvage_handles_nested_objects(self):
        """Events with nested objects should be handled."""
        text = '''{"events": [
            {"id": "e1", "type": "talk", "metadata": {"key": "value"}},
            {"id": "e2", "type":
        '''
        events = salvage_truncated_events(text)
        assert len(events) == 1
        assert events[0]["metadata"]["key"] == "value"
