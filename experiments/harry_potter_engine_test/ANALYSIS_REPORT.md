# Experiment Analysis Report: Harry Potter Engine Test

**Date:** 2026-01-31  
**Experiment:** `harry_potter_engine_test`

---

## Executive Summary

The experiment processed 34 chapters (17 original + 17 modified) and detected **only 4 total violations** (2 per version), despite the ground truth indicating **15 intentionally injected errors** in the modified version. This represents a **detection rate of approximately 13%** (2/15 ground truth errors detected).

---

## 1. What Was Detected

### Original Version (Chapter 16)
| Error Type | Description | Story Fragment |
|------------|-------------|----------------|
| `causality/dead_character_acting` | Dead character performing actions | "Quirrell snapped his fingers. Ropes sprang out of thin air" |
| `causality/interacting_with_dead` | Interaction with dead character | "It was Quirrell. 'You!' gasped Harry." |

### Modified Version (Chapter 16)
| Error Type | Description | Story Fragment |
|------------|-------------|----------------|
| `causality/dead_character_acting` | Dead character performing actions | "Quirrell lunged, knocking Harry clean off his feet" |
| `emotional/relationship_flip` | Unexpected relationship change | (no fragment captured) |

**Issue #1:** The `dead_character_acting` errors are **false positives** - Quirrell is not dead until the end of this chapter. The system incorrectly marked him as dead earlier.

---

## 2. Ground Truth Analysis (What Should Have Been Detected)

From `harry_potter_errors.csv`, there are **15 intentionally injected errors**:

| # | Chapter | Error Type | Description | Detected? |
|---|---------|------------|-------------|-----------|
| 0 | 055.txt | Temporal Order | Buckbeak stretching up before laying down | ❌ NO |
| 1 | 026.txt | Location | Madam Pomfrey takes stethoscope from desk (not in office) | ❌ NO |
| 2 | 027.txt | Temporal Order | Harry unlocks stall (but already in it) | ❌ NO |
| 3 | 005.txt | Emotional Relations | Dursleys treat Harry warmly (contradicts hatred) | ❌ NO |
| 4 | 011.txt | Causality | Mysterious door appears, never resolved | ❌ NO |
| 5 | 002.txt | Basic Coherence | Face turning "bubble and squeak" color | ❌ NO |
| 6 | 007.txt | Location | Harry reaches dormitory from dungeon | ❌ NO |
| 7 | 012.txt | Temporal Order | Hermione fretting before knowing information | ❌ NO |
| 8 | 025.txt | Causality | Chamber sealed at specific day, never mentioned again | ❌ NO |
| 9 | 045.txt | Location | Trelawney from dungeon stairs (should be tower) | ❌ NO |
| 10 | 020.txt | Emotional Relations | Ginny not defending Harry (contradicts character) | ❌ NO |
| 11 | 001.txt | Basic Coherence | Dudley goes "pale green" when angry (not sick) | ❌ NO |
| 12 | 035.txt | Causality | Sneakoscope flashing without explanation | ❌ NO |
| 13 | 049.txt | Basic Coherence | Crystal balls "in shadows" on clear tower roof | ❌ NO |
| 14 | 014.txt | Emotional Relations | Neville betraying friends (contradicts loyalty) | ❌ NO |

**Detection rate: 0/15 = 0%** (the detected errors were false positives on both versions)

---

## 3. Root Cause Analysis

### Problem 1: Only 17 Chapters Processed (of ~55+ in ground truth)
The ground truth references chapters like `020.txt`, `025.txt`, `026.txt`, `027.txt`, `035.txt`, `045.txt`, `049.txt`, `055.txt` - but only chapters `000.txt` through `016.txt` were processed. 

**The experiment only processed Book 1 chapters, but the ground truth errors span multiple books.**

### Problem 2: False Positives from Incorrect Death State
The Quirrell errors are false positives - the system marked him as dead too early. This suggests:
- The `mark_dead` logic is being triggered prematurely
- Or the death state is being set without proper event confirmation

### Problem 3: No Rules Actually Applied
From the rule audit:
```json
"times_applied": 0,
"times_triggered_violation": 0
```

**All 8 rules show zero applications and zero triggered violations.** This means:
- The ASP rules are loaded but never actually fired
- The violations detected came from Python-level checks, not ASP logic

### Problem 4: Excessive Loose Ends (50)
50 loose ends were reported, including items like `put_outer`, `letter`, etc. This is excessive and suggests:
- The Chekhov detection is too aggressive
- Items are being flagged even when they ARE used later
- The `causal` vs `latent` classification isn't working correctly

### Problem 5: No Semantic Understanding
The injected errors require **semantic understanding** that the current system cannot perform:
- "Pale green in the face" (coherence) - requires understanding color associations
- "Dursleys being warm" (emotional) - requires character relationship inference
- "Reaching dormitory from dungeon" (location) - requires castle topology knowledge

---

## 4. Classification of Errors by Detectability

### Potentially Detectable (with current architecture)
| Error Type | Example | Why Detectable |
|------------|---------|----------------|
| Temporal Order | Hermione fretting before knowing | Requires tracking information flow |
| Location | Reaching dormitory from dungeon | Requires location connectivity graph |
| Causality | Door appears, never resolved | Chekhov detection (if fixed) |

### Not Detectable (requires semantic reasoning)
| Error Type | Example | Why Not Detectable |
|------------|---------|-------------------|
| Basic Coherence | "Pale green" face | Requires color/emotion semantics |
| Emotional Relations | Dursleys being warm | Requires character relationship model |
| Emotional Relations | Neville betraying friends | Requires personality/loyalty model |

---

## 5. Specific Issues Found

### Issue 5.1: Chapter Coverage Mismatch
```
Processed: 000.txt - 016.txt (17 chapters)
Ground Truth: 001.txt - 055.txt (spans at least 55 chapters)
```
**Action:** Verify book folder structure has all chapters

### Issue 5.2: Rate Limiting
```
[2026-01-31 03:07:46] [WARN] Structure extraction failed: Error code: 429
```
Chapter 10 extraction failed due to OpenAI rate limiting. The system continued but with missing data.

### Issue 5.3: ASP Rules Not Firing
All rules show `times_applied: 0`. The ASP engine is loaded but the facts generated don't match rule patterns.

---

## 6. Recommendations

### Immediate Fixes
1. **Verify chapter coverage** - Ensure all modified chapters are in the experiment folder
2. **Debug death state tracking** - Quirrell false positives indicate premature death marking
3. **Add retry logic for rate limits** - Chapter 10 data was lost

### Architecture Improvements
1. **ASP rule debugging** - Add logging to see which facts are generated vs which rules expect
2. **Reduce loose end threshold** - 50 is too many; add filtering criteria
3. **Add connectivity checking** - Location rules need to check if paths exist

### Scope Limitations
The following error types **cannot be detected** by logic-based rules alone:
- Basic Coherence (color/sensation semantics)
- Emotional Relations (personality models)
- Character behavior patterns

These would require:
- LLM-based semantic analysis
- Character personality profiles
- Emotional state tracking beyond simple relationships

---

## 7. Metrics Summary

| Metric | Original | Modified |
|--------|----------|----------|
| Chapters Processed | 17 | 17 |
| Errors Detected | 2 | 2 |
| True Positives | 0 | ~1 (relationship_flip) |
| False Positives | 2 | 1 |
| Loose Ends | 50 | 50 |
| Alias Conflicts | 0 | 0 |
| Rate Limit Failures | 1 | 1 |
| Total Items Tracked | 42 | 42 |

---

## 8. Conclusion

The experiment reveals **fundamental gaps** between the engine's capabilities and the ground truth errors:

1. **Coverage gap:** Only 17/55+ chapters processed
2. **Detection gap:** 0/15 ground truth errors detected (in covered chapters)
3. **Precision gap:** 3-4 false positives detected
4. **Rule gap:** ASP rules loaded but never applied

The primary issue is that the injected errors require **semantic understanding** that pure logic-based rules cannot provide. The engine can detect structural violations (dead characters acting, missing items) but cannot detect:
- Emotional inconsistencies
- Coherence violations
- Character behavior anomalies

**Recommendation:** Hybrid approach combining:
1. Logic engine for structural/temporal/location violations
2. LLM-based analysis for semantic/emotional/coherence violations
