"""
Prompt for extracting RELATIONSHIPS and INITIAL RULES from chapters.

Part of the four-function extraction pipeline (Phase 2: Split Extraction Prompts).
"""

EXTRACT_RELATIONSHIPS_PROMPT = """Extract RELATIONSHIPS and INITIAL RULES from the text below.

TEXT:
{chapter_text}

=== GLOBAL CONSTRAINTS (CRITICAL) ===
- ONLY use character IDs that were already extracted in previous phases.
- DO NOT invent new characters.
- DO NOT infer abstract or thematic relationships.
- Extract ONLY relationships involving named characters.

=== GROUP & IMPLIED RELATIONSHIPS (CRITICAL) ===
If the text describes a relationship (hostility, affection, fear, alliance) applying to a GROUP
(e.g., "the family", "his relatives", "the guards"):

- Apply the relationship to EACH named individual in that group.
- Do NOT collapse group behavior into a single representative character.

Example:
"The family despised Alex" →
  member_1 -> alex (hostile)
  member_2 -> alex (hostile)

=== CHARACTER BEHAVIOR ANALYSIS (VERY IMPORTANT) ===
Pay special attention to behavior that REVEALS or CONTRADICTS relationships:

- Hostile characters showing warmth, kindness, concern, praise, or farewell
- Enemies helping, protecting, or comforting each other
- Family members acting against expected loyalties
- Fear, distrust, or avoidance shown through dialogue or actions

These behaviors MUST be extracted as relationships or changes in relationships.

=== RELATIONSHIPS (CHAPTER-SPECIFIC) ===
Relationships that are SHOWN, ACTED UPON, or CHALLENGED in THIS CHAPTER.

INCLUDE:
- Explicit hostility, friendliness, fear, love, or family bonds
- Relationships demonstrated through dialogue or actions
- Relationship changes or contradictions (even if temporary)

DO NOT INCLUDE:
- Background-only facts (those go in INITIAL RULES)
- Weakly implied relationships without evidence
- Every possible character pair

Format:
- from: character id (snake_case)
- to: character id (snake_case)
- type: hostile | friendly | family | love | fear

=== INITIAL RULES (STORY BASELINE FACTS) ===
Extract relationships or traits that are ESTABLISHED BEFORE this chapter.

INCLUDE ONLY IF:
- Explicitly stated as long-standing
- Clearly implied as pre-existing background
- Necessary to understand later contradictions

CRITICAL:
- Subject MUST be a character
- Object MUST be a character OR "true" (for traits)
- Do NOT include abstract concepts

Allowed predicates:
- hates | loves | fears | trusts
- hostile | friendly
- cruel | kind | brave | cowardly

Examples:
- "They had always hated their nephew" →
  {{"subject": "relative_1", "predicate": "hates", "object": "nephew"}}
- "He was a cruel man" →
  {{"subject": "character", "predicate": "cruel", "object": "true"}}

  === CHAPTER ENTITY CONTEXT (CRITICAL) ===
The following characters are CONFIRMED to appear or act in this chapter.

CHARACTERS IN THIS CHAPTER:
{chapter_character_ids}

INSTRUCTIONS:
- Extract relationships ONLY between characters listed above.
- Use ONLY these character IDs.
- If a relationship is described for a GROUP (family, relatives, guards):
  apply it to EACH relevant named character from this list.

RELATIONSHIP SCOPE RULE:
- If a relationship is long-standing or background → INITIAL RULE
- If a relationship is shown, challenged, or contradicted in this chapter → RELATIONSHIP
- If unsure, prefer INITIAL RULE only when clearly pre-existing

=== OUTPUT FORMAT ===
Return ONLY this JSON structure:

{{
  "relationships": [
    {{"from": "...", "to": "...", "type": "..."}}
  ],
  "initial_rules": [
    {{"subject": "...", "predicate": "...", "object": "..."}}
  ]
}}

Return ONLY valid JSON. No markdown. No explanations."""
