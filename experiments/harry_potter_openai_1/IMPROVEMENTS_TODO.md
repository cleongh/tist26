# Step 2 Logic Improvements TODO

Based on experiment `harry_potter_openai_1` run on 2026-01-30.

## Critical Issues

### 1. Planted Error Not Detected (Vernon's Warm Farewell in Ch.5)
- **Expected**: Detect contradiction when Vernon shows warmth to Harry
- **Actual**: Not detected in original or modified

---

## ROOT CAUSE ANALYSIS (from step2_logic_log.jsonl)

### Finding 1: Farewell Event NOT EXTRACTED
The planted modification ("Uncle Vernon gave Harry a warm hug...") was **never extracted as an event**!
Only uncle_vernon interaction in modified Ch5:
```
e54: type=talk, agent=harry_potter, patient=uncle_vernon, source="Er — Uncle Vernon?"
```
This is Harry asking about the station, not Vernon's warm farewell.

### Finding 2: Wrong Relationship Object
- **Original Ch5 initial_rules**: `uncle_vernon hates harry_potter` ✓
- **Modified Ch5 initial_rules**: `uncle_vernon hates magic` ✗

The LLM extracted "hates magic" instead of "hates harry_potter" in the modified version.

### Finding 3: Character ID Inconsistency
- Ch.0 story_rules: `mr_dursley hates magic`, `mr_dursley hates potters`
- Ch.5 initial_rules: `uncle_vernon hates harry_potter`
- No unification between `mr_dursley` and `uncle_vernon`

### Finding 4: No Contradiction-Triggering Event Types
Even if extracted, event types like `hug`, `praise`, `warm_farewell` are not in `action_contradicts_relationship`

---

## Recommended Improvements

### High Priority

#### 1. Character ID Normalization
Add a normalization step to map character aliases to canonical IDs:
```python
CHAR_ALIASES = {
    'uncle_vernon': 'mr_dursley',
    'aunt_petunia': 'mrs_dursley', 
    'vernon_dursley': 'uncle_vernon',
    'petunia_dursley': 'aunt_petunia',
    ...
}
```
**Files to modify**: `run_narrative_experiment.py` - add normalization in `_to_asp()` or after extraction

#### 2. Enhanced Relationship Extraction
Modify the prompt to explicitly ask for character-to-character hostility:
```
IMPORTANT: Extract specific character-to-character relationships, especially:
- Hostility toward named characters (e.g., "uncle_vernon hates harry_potter")
- NOT abstract concepts like "hates magic"
```
**Files to modify**: `run_narrative_experiment.py` - `_structure_chapter()` prompt

### Medium Priority

#### 3. Expand Action Types for Contradiction
Add more action types that contradict hate relationships:
```asp
action_contradicts_relationship(farewell, hates).
action_contradicts_relationship(warm_farewell, hates).
action_contradicts_relationship(kind_words, hates).
action_contradicts_relationship(smile, hates).
action_contradicts_relationship(wave, hates).
action_contradicts_relationship(encourage, hates).
action_contradicts_relationship(wish_well, hates).
action_contradicts_relationship(support, hates).
```
**Files to modify**: `rules/story_rules.lp`

#### 4. Reduce False Positive Location Violations
Options:
- Make location violations less strict (require same chapter)
- Add more travel event types
- Only trigger if locations are in same connected subgraph
**Files to modify**: `rules/story_rules.lp`

#### 5. Smarter Possession Tracking
`give_without_having` triggers because items appear suddenly. Options:
- Initialize common items as possessed by "world"
- Allow first-mention possession
- Only flag if the same item was explicitly possessed by someone else
**Files to modify**: `rules/story_rules.lp`

### Low Priority

#### 6. Add Event Source to Violation Output
Include source text in violation output for debugging:
```
Violation: wrong_location at e23 - "Harry walked into the kitchen"
```
**Files to modify**: `run_narrative_experiment.py` - violation formatting

---

## False Positives to Reduce

| Chapter | Error | Likely Cause |
|---------|-------|--------------|
| Ch.2 (original) | `wrong_location` | Character moved but LLM didn't extract travel event |
| Ch.3-4 | `give_without_having` | Items given without prior possession tracking |
| Ch.6 | `dead_character_acting` | LLM incorrectly marked someone as dead |

---

## Test Results Summary

| Metric | Original | Modified |
|--------|----------|----------|
| Chapters Processed | 11 | 11 |
| Total Errors | 4 | 5 |
| Planted Error Detected | ❌ | ❌ |
