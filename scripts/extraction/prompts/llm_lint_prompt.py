"""
LLM lint prompt for chapter analysis.

User prompt: chapter FIRST, then instructions.
"""

LLM_LINT_PROMPT = """---BEGIN CHAPTER---
{chapter_text}
---END CHAPTER---
{previous_summaries_section}
Analyze the chapter above for narrative consistency errors. Consider both within-chapter inconsistencies and contradictions with previous chapters (if summaries are provided above).

ERROR CATEGORIES:
- causality: unexplained effects, missing causes
- coherence: logical impossibilities, contradictions
- temporal: wrong event order, time paradoxes  
- location: impossible travel, characters in two places
- emotional: actions contradicting established relationships
- cross_chapter: contradictions with events/facts from previous chapters

For each error found, include the exact quote from the chapter that contains the error.

Respond with JSON only:
{{"error_count": N, "errors": [{{"category": "causality|coherence|temporal|location|emotional|cross_chapter", "description": "brief description of the error", "error_text": "exact quote from chapter with the error"}}], "chapter_summary": "A brief 2-3 sentence summary of key events, characters introduced, and important facts established in this chapter"}}"""
