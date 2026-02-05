"""
Prompt for extracting ITEMS from chapters.

Part of the four-function extraction pipeline (Phase 2: Split Extraction Prompts).
"""

EXTRACT_ITEMS_PROMPT = """Extract ITEMS from the text below.

TEXT:
{chapter_text}

=== ITEMS ===
Plot-significant objects.

INCLUDE objects that:
- Are given, taken, stolen, or exchanged
- Change state (broken, lost, found)
- Cause or enable key events
- Appear multiple times with significance
- Doors, windows, containers if they affect actions or are described in detail
- Are described with narrative emphasis, even if it is furniture or clothing

DO NOT INCLUDE:
- Food and meals (unless plot-critical)
- Ordinary clothing (unless special/significant)
- Generic furniture, decorations, scenery

Format:
- id: lowercase_with_underscores
- name: display name
- state: intact | damaged | destroyed | hidden | found

=== ITEM EXTRACTION RULES (CRITICAL) ===

ONLY extract an item if AT LEAST ONE of the following is true:
1. The item is carried, given, taken, used, lost, discovered, or destroyed
2. The item affects an event or a character's behavior
3. The item is mentioned with clear narrative emphasis (focus, repetition, or consequence)
4. The item is likely to persist across scenes or chapters
5. The item enables or blocks future actions (keys, weapons, letters, tools, artifacts)

DO NOT extract items that are:
- Ordinary background objects (chairs, tables, doors, food, clothing)
- Mentioned only as scenery or setting flavor
- Not interacted with by any character
- Immediately irrelevant and never referred to again in the chapter

=== KNOWN ITEMS CONTEXT (IMPORTANT) ===
The following items are ALREADY KNOWN from previous chapters.

KNOWN ITEMS (authoritative IDs and states):
{known_items_with_states}

INSTRUCTIONS:
- Prefer reusing these existing item IDs when an item appears in this chapter.
- Update item relevance ONLY if the item is used, exchanged, referenced emotionally, or affects events.
- Introduce a NEW item ONLY if it is clearly distinct and narratively relevant in this chapter.

ITEM RELEVANCE RULES:
- Do NOT extract background objects (furniture, food, clothing) unless they matter to the plot.
- Items briefly mentioned without narrative impact should NOT be extracted.
- If unsure whether an item is relevant, DO NOT include it.

DO NOT:
- Duplicate existing items with slightly different names
- Promote an item to relevant without evidence in the text

=== OUTPUT FORMAT ===
Return ONLY this JSON structure, nothing else:

{{
  "items": [
    {{"id": "...", "name": "...", "state": "...", "relevance": "causal|latent"}}
  ]
}}

Use relevance="causal" if the item participates in an event in this chapter.
Use relevance="latent" if the item is extracted under the CHEKHOV RULE (introduced but not yet used).

Return ONLY valid JSON, no markdown or explanations."""
