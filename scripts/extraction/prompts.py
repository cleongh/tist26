"""
LLM prompts for narrative analysis.

TODO: Future refactors may split large prompts into separate template files.
"""

# System message for JSON-only output
LLM_SYSTEM_MESSAGE = """You are a narrative error detector. You analyze story chapters and return ONLY valid JSON.

CRITICAL RULES:
- Output ONLY a JSON object, nothing else
- Never continue or extend the story
- Never echo back the input
- Always include a brief summary of the chapter (2-3 sentences covering key events, characters, and locations)
- If no errors found, return: {"error_count": 0, "errors": [], "chapter_summary": "..."}
- If errors found, return: {"error_count": N, "errors": [...], "chapter_summary": "..."}"""

# User prompt: chapter FIRST, then instructions
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


# Unified extraction prompt for structuring chapters
# This is the comprehensive prompt used by LogicEvaluator._structure_chapter
# TODO: Consider templating this for easier maintenance
UNIFIED_EXTRACTION_PROMPT = """Extract structured narrative data from the text below.

=== CONSISTENCY RULES CONTEXT ===
Your extraction will be checked by a logic-based consistency verifier. The system detects:

1. CAUSALITY VIOLATIONS:
   - Dead characters acting (character marked as "dead" performing actions later)
   - Characters interacting with dead characters
   - Unintroduced characters suddenly appearing in events

2. LOCATION VIOLATIONS:
   - Characters moving between unconnected locations without travel
   - IMPORTANT: If locations are in the same building/area, specify their connections!
   - Example: If someone walks from "kitchen" to "living_room", they must be connected

3. APPEARANCE/STATE CHANGES:
   - Characters whose appearance changes unusually (face turning colors, sudden injuries)
   - CRITICAL: Track appearance words like "pale", "green", "flushed", "purple" carefully
   - If a character's face/skin color is described, extract it in the "appearance" field

4. RELATIONSHIP VIOLATIONS:
   - Sudden hostile→friendly or friendly→hostile flips without cause
   - Characters helping enemies or harming loved ones unexpectedly

5. COHERENCE VIOLATIONS:
   - Characters in contradictory states (alive and dead, present and absent)
   - Solo communication (talking without a listener, unless it's a speech/announcement)

EXTRACTION PRIORITY: To help detect inconsistencies, pay special attention to:
- Unusual appearance descriptions (colors, conditions)
- Location connections (how rooms/places connect)
- Relationship dynamics (who likes/hates whom)
- Character states (injured, dead, normal)

TEXT:
{chapter_text}

=== CRITICAL INSTRUCTIONS ===
- Output ONE valid JSON object only
- No markdown, no comments, no explanations
- Extract ALL relevant narrative elements - be thorough and comprehensive
- DO NOT INVENT EVENTS: Only extract what EXPLICITLY happens in the text
- DO NOT HALLUCINATE DEATHS: Use "die" event or "dead" state ONLY if someone explicitly dies in this chapter

=== CHARACTER BEHAVIOR ANALYSIS (VERY IMPORTANT) ===
Pay SPECIAL ATTENTION to character behavior and emotional interactions:
- If a character who is normally HOSTILE shows WARMTH, KINDNESS, or AFFECTION → this is significant, extract it!
- If an enemy gives a farewell, hug, encouragement, or praise → ALWAYS extract this as an event
- Look for CONTRADICTIONS between established relationships and current actions
- Warm farewells, sad smiles, unexpected kindness from hostile characters are CRITICAL to capture

EXAMPLES OF CRITICAL BEHAVIOR TO CAPTURE:
- "Uncle Vernon gave Harry a warm smile" → extract as "smile" event (Vernon hates Harry, so this is unusual)
- "Have a good term," said the usually cold teacher warmly → extract as "farewell" or "encourage"
- An enemy wishing someone well → extract as "farewell" with source_text

=== CHARACTERS ===
Named individuals who perform actions in THIS chapter.

INCLUDE:
- Named people (e.g., John Smith, Dr. Wilson, Aunt Martha)
- Named creatures that act intentionally (e.g., a named pet, mount, or companion)

DO NOT INCLUDE:
- Groups ("students", "crowd", "people", "soldiers")
- Unnamed background characters ("a man", "someone", "the waiter")
- Characters only mentioned but not present
- Objects or abstract concepts

Format:
- id: lowercase_with_underscores (john_smith, dr_wilson)
- name: display name as written ("John Smith", "Dr. Wilson")
- emotion: happy | sad | angry | afraid | calm | neutral
- state: normal | injured | dead (ONLY use "dead" if character EXPLICITLY dies in THIS chapter - not mentioned as deceased before, not implied, EXPLICIT death only)
- appearance: REQUIRED - ONE or TWO words describing current appearance. Use "normal" if nothing unusual. Use specific words like "pale", "green", "flushed", "muddy", "bloody", "disheveled" if character's appearance is described as unusual or changed

APPEARANCE EXAMPLES:
- "His face turned pale green" → appearance: "pale green"
- "She was covered in mud" → appearance: "muddy"
- "He looked perfectly normal" → appearance: "normal"
- "Her face was flushed with anger" → appearance: "flushed"
- "The boy with messy black hair" → appearance: "normal" (this is a permanent trait, not unusual)

=== LOCATIONS ===
Specific named places where events occur.

INCLUDE:
- Named buildings (e.g., The Grand Hotel, City Hospital, Central Station)
- Named streets/addresses (e.g., 5th Avenue, Oak Street, The Old Mill)
- Named rooms if they are settings for events (e.g., The Vault, Room 237, kitchen, living_room)

DO NOT INCLUDE:
- Generic unnamed places ("a room", "the street", "outside")
- Places only referenced but never visited

Format:
- id: lowercase_with_underscores
- name: display name
- connections: IMPORTANT - list of other location IDs directly reachable from here (e.g., ["hallway", "garden"])
- contains: list of sub-location IDs inside this location (e.g., a building contains rooms)

LOCATION EXAMPLES:
- A castle with a dungeon and tower: connections: ["great_hall", "dungeon", "tower"]
- A room inside a building: the building's "contains" should list this room
- Distant locations (another city): should NOT be in connections unless travel happens

=== ITEMS ===
Plot-significant objects.

INCLUDE objects that:
- Are given, taken, stolen, or exchanged
- Change state (broken, lost, found)
- Cause or enable key events
- Appear multiple times with significance

DO NOT INCLUDE:
- Food and meals (unless plot-critical)
- Ordinary clothing (unless special/significant)
- Generic furniture, decorations, scenery

Format:
- id: lowercase_with_underscores
- name: display name
- state: intact | damaged | destroyed | hidden | found

=== EVENTS ===
Extract ALL significant plot actions in chronological order. Be thorough - do not skip events.

INCLUDE (HIGH PRIORITY):
- ★ UNUSUAL CHARACTER BEHAVIOR: hostile person being kind, enemy showing affection, unexpected warmth
- ★ FAREWELLS AND DEPARTURES: especially if they involve unusual emotion (warm goodbye from cold person)
- ★ EMOTIONAL INTERACTIONS: hugs, praise, encouragement, smiles, waves
- Key confrontations and conversations
- Arrivals and departures
- Discoveries and revelations
- Attacks, rescues, deaths
- Giving, taking, or exchanging items

CRITICAL - OUT-OF-CHARACTER BEHAVIOR (NEVER SKIP THESE):
- If a hostile character says something warm/kind → extract as "farewell", "praise", or "encourage"
- If someone who hates another character shows affection → extract as "hug", "smile", or "wave"
- If an enemy wishes someone well → extract as "farewell" with the exact source_text
- These events are ESSENTIAL for detecting narrative inconsistencies!

EXAMPLES:
- "Have a good term, my boy," Vernon said with a warm smile → type: "farewell", agent: "uncle_vernon", patient: "harry_potter"
- The usually cold teacher gave an encouraging nod → type: "encourage"
- She hugged her former rival → type: "hug"

DO NOT INCLUDE:
- Routine actions with no narrative significance (generic eating, sleeping)
- Identical repeated events - summarize as one

Format:
- id: e1, e2, e3... (sequential)
- type: meet | talk | think | give | take | attack | help | discover | escape | arrive | leave | die | hug | praise | farewell | encourage | smile | wave
- agent: character id (MUST exist in your characters list)
- patient: character id OR item id OR null (MUST exist in your lists)
- location: location id OR null
- after: event id that MUST happen before this one (optional, only if explicit causal dependency)
- source_text: REQUIRED - The exact sentence or short phrase (max 80 chars) from the chapter where this event happens. Quote the text directly.

EVENT RULES:
- agent != patient (no self-actions)
- Both agent and patient MUST be IDs you defined above
- If you run out of character/item IDs, use null for patient
- "die" event: ONLY if a character EXPLICITLY dies in THIS chapter (not mentioned as already dead, not implied - actual death scene)
- DO NOT invent events that didn't happen in the text
- source_text MUST be an actual quote from the chapter, not a summary

=== RELATIONSHIPS ===
Relationship dynamics established or shown IN THIS CHAPTER.

INCLUDE:
- Key alliances or enmities driving the plot
- Family bonds that affect character actions
- Relationships that CHANGE in this chapter
- Hostile relationships (these are important for detecting contradictory behavior later)

DO NOT INCLUDE:
- Every possible character pair
- Relationships only implied, not shown
- If no strong relationships shown, leave empty: []

Format:
- from: character id
- to: character id
- type: hostile | friendly | family | love | fear

=== INITIAL RULES (for establishing story baseline) ===
Extract rules that are ESTABLISHED FACTS from the story's background/context.
These are relationships or traits that exist BEFORE the events of this chapter.
Only include rules that are EXPLICITLY stated or clearly implied by the narrative context.

CRITICAL: Extract CHARACTER-TO-CHARACTER relationships, NOT abstract concepts.
- CORRECT: "uncle_vernon hates harry_potter" (specific character)
- WRONG: "uncle_vernon hates magic" (abstract concept)

INCLUDE:
- Pre-existing hostility/hatred between SPECIFIC characters
- Family relationships between characters
- Established character traits ("cruel", "kind", "cowardly")

Format:
- subject: character id
- predicate: hates | loves | fears | trusts | hostile | friendly | cruel | kind | brave | cowardly
- object: character id (for relationships) OR "true" (for traits)

EXAMPLES:
- "The Dursleys had always hated their nephew" → {{"subject": "uncle_vernon", "predicate": "hates", "object": "harry_potter"}}
- "He despised his sister's son" → {{"subject": "uncle_vernon", "predicate": "hates", "object": "harry_potter"}}
- "The cruel headmaster ruled with an iron fist" → {{"subject": "headmaster", "predicate": "cruel", "object": "true"}}

=== CHARACTER LOCATIONS (for location tracking) ===
Where are characters located at the START of this chapter?
Only include if the chapter establishes their initial location.

Format:
- character: character id
- location: location id

EXAMPLES:
- "Harry was in his cupboard under the stairs" → {{"character": "harry_potter", "location": "cupboard"}}
- "The Dursleys were at the breakfast table" → {{"character": "uncle_vernon", "location": "kitchen"}}

=== CHARACTER POSSESSIONS (for possession tracking) ===
What items do characters have/own at the START of this chapter?
Only include if possession is EXPLICITLY established (not just mentioned near character).

Format:
- character: character id
- item: item id

EXAMPLES:
- "Harry clutched his wand" → {{"character": "harry_potter", "item": "wand"}}
- "The letter was in Hagrid's pocket" → {{"character": "hagrid", "item": "letter"}}

=== TEMPORAL CONSTRAINTS (for ordering requirements) ===
Are there any explicit ordering requirements mentioned in the chapter?
These are statements like "before X could Y, Z had to happen" or "X won't happen until Y".
Only include if EXPLICITLY stated in the narrative.

Format:
- first_event_type: the event type that must happen first
- second_event_type: the event type that requires the first

EXAMPLES:
- "Harry couldn't open the door until he found the key" → {{"first_event_type": "find", "second_event_type": "open"}}
- "She had to pass the test before she could graduate" → {{"first_event_type": "pass", "second_event_type": "graduate"}}

=== OUTPUT FORMAT ===
Return ONLY this JSON structure, nothing else:

{{
  "characters": [
    {{"id": "...", "name": "...", "emotion": "...", "state": "...", "appearance": "..." }}
  ],
  "locations": [
    {{"id": "...", "name": "...", "connections": ["loc_id1", "loc_id2"], "contains": ["sub_loc"] }}
  ],
  "items": [],
  "events": [
    {{"id": "e1", "type": "...", "agent": "...", "patient": "...", "location": "...", "after": null, "source_text": "exact quote from chapter" }}
  ],
  "relationships": [],
  "initial_rules": [
    {{"subject": "...", "predicate": "...", "object": "..." }}
  ],
  "character_locations": [
    {{"character": "...", "location": "..." }}
  ],
  "character_possessions": [
    {{"character": "...", "item": "..." }}
  ],
  "temporal_constraints": [
    {{"first_event_type": "...", "second_event_type": "..." }}
  ]
}}
"""


# Engine-based extraction prompt with continuity context
# Used by _structure_chapter_standalone for Phase 5 engine evaluation
ENGINE_EXTRACTION_PROMPT = """Extract structured narrative data from the text below.

=== CONTINUITY CONTEXT (AUTHORITATIVE) ===
The following facts are TRUE before this chapter begins.
You MUST treat them as ground truth.
Do NOT reinterpret, soften, or restate them unless the chapter EXPLICITLY changes them.

KNOWN CHARACTERS:
{known_characters_json}

KNOWN RELATIONSHIPS:
{known_relationships_json}

KNOWN CHARACTER STATES:
{known_character_states_json}

IDENTITY RULES:
- Each character has ONE canonical id.
- If the text uses a title, nickname, or alternate name, map it to the canonical id.
- DO NOT create a new character if an alias matches a known character.
- Use the canonical id in ALL outputs.

=== CONSISTENCY RULES CONTEXT ===
Your extraction will be checked by a logic-based consistency verifier. The system detects:

1. RELATIONSHIP VIOLATIONS:
   - Sudden hostile→friendly or friendly→hostile flips without cause
   - Characters helping enemies or harming loved ones unexpectedly
   - CRITICAL: If someone who hates another shows warmth/kindness, this MUST be extracted

2. COHERENCE VIOLATIONS:
   - Characters in contradictory states
   - Actions that contradict established relationships

TEXT:
{chapter_text}

=== CHARACTER BEHAVIOR ANALYSIS (VERY IMPORTANT) ===
Pay SPECIAL ATTENTION to character behavior and emotional interactions:
- If a character who is normally HOSTILE shows WARMTH, KINDNESS, or AFFECTION → this is significant!
- If an enemy gives a farewell, hug, encouragement, or praise → ALWAYS extract this as an event
- Look for CONTRADICTIONS between established relationships and current actions
- Populate "aliases" ONLY if the chapter introduces a new way to refer to an existing character

If hostility, warmth, or affection is described for a GROUP
(e.g., "the family", "the guards", "his classmates"):

- Extract the relationship for EACH named individual in that group.
- Do not collapse group behavior into a single representative character.
Example:
"The group despised Alex" →
  member_1 -> alex (hostile)
  member_2 -> alex (hostile)
  member_3 -> alex (hostile)

EXAMPLES OF CRITICAL BEHAVIOR TO CAPTURE:
- "Uncle Vernon gave Harry a warm smile" → event type: "farewell" or "praise"
- "Have a good term," said the usually cold teacher warmly → event type: "farewell"
- An enemy wishing someone well → MUST be extracted as "farewell" event

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

=== OUTPUT FORMAT ===
Return ONLY this JSON structure:

{{
  "entities": {{
    "characters": [{{"id": "name_in_snake_case", "name": "Full Name", "aliases": [], "state": "normal/dead", "emotion": "emotion", "appearance": "normal/unusual"}}],
    "locations": [{{"id": "location_id", "name": "Location Name", "connections": []}}],
    "items": [{{"id": "item_id", "name": "Item Name", "state": "intact", "relevance": "causal|latent"}}],
    "relationships": [{{"from": "char_id", "to": "char_id", "type": "hostile/friendly/family/love/fear"}}]
  }},
  "events": [
    {{
      "id": "e1",
      "type": "meet|talk|give|take|attack|help|discover|arrive|leave|die|hug|praise|farewell|encourage|smile|wave",
      "agent": "character_id",
      "patient": "character_id_or_null",
      "location": "location_id_or_null",
      "source_text": "exact quote from text (max 80 chars)"
    }}
  ],
  "initial_rules": [
    {{"subject": "char_id", "predicate": "hates|loves|hostile|friendly", "object": "char_id"}}
  ]
}}

CRITICAL RULES:
- Extract ALL farewell/praise/encourage events, especially from hostile characters
- Include initial_rules ONLY for relationships EXPLICITLY stated or MODIFIED in this chapter
- DO NOT restate known relationships from the continuity context
- source_text MUST be an actual quote from the chapter
- Use relevance="causal" if the item participates in an event in this chapter
- Use relevance="latent" if the item is extracted under the CHEKHOV RULE
- Treat this chapter as a DELTA over the continuity context:
  - DO NOT restate unchanged relationships or states
  - ONLY extract new events, changes, or contradictions introduced in this chapter

Return ONLY valid JSON, no markdown or explanations."""


# =============================================================================
# PHASE 2: SPLIT EXTRACTION PROMPTS
# =============================================================================
# These prompts are used by the four-function extraction pipeline.
# Each function calls the LLM independently with the full chapter text.
# The wording is preserved from the original UNIFIED_EXTRACTION_PROMPT.
# =============================================================================

EXTRACT_CHARACTERS_AND_LOCATIONS_PROMPT = """Extract CHARACTERS and LOCATIONS from the text below.

TEXT:
{chapter_text}

=== CHARACTERS ===
Named individuals who perform actions in THIS chapter.

INCLUDE:
- Named people (e.g., John Smith, Dr. Wilson, Aunt Martha)
- Named creatures that act intentionally (e.g., a named pet, mount, or companion)

DO NOT INCLUDE:
- Groups ("students", "crowd", "people", "soldiers")
- Unnamed background characters ("a man", "someone", "the waiter")
- Characters only mentioned but not present
- Objects or abstract concepts

Format:
- id: lowercase_with_underscores (john_smith, dr_wilson)
- name: display name as written ("John Smith", "Dr. Wilson")
- emotion: happy | sad | angry | afraid | calm | neutral
- state: normal | injured | dead (ONLY use "dead" if character EXPLICITLY dies in THIS chapter - not mentioned as deceased before, not implied, EXPLICIT death only)
- appearance: REQUIRED - ONE or TWO words describing current appearance. Use "normal" if nothing unusual. Use specific words like "pale", "green", "flushed", "muddy", "bloody", "disheveled" if character's appearance is described as unusual or changed

APPEARANCE EXAMPLES:
- "His face turned pale green" → appearance: "pale green"
- "She was covered in mud" → appearance: "muddy"
- "He looked perfectly normal" → appearance: "normal"
- "Her face was flushed with anger" → appearance: "flushed"
- "The boy with messy black hair" → appearance: "normal" (this is a permanent trait, not unusual)

=== LOCATIONS ===
Specific named places where events occur.

INCLUDE:
- Named buildings (e.g., The Grand Hotel, City Hospital, Central Station)
- Named streets/addresses (e.g., 5th Avenue, Oak Street, The Old Mill)
- Named rooms if they are settings for events (e.g., The Vault, Room 237, kitchen, living_room)

DO NOT INCLUDE:
- Generic unnamed places ("a room", "the street", "outside")
- Places only referenced but never visited

Format:
- id: lowercase_with_underscores
- name: display name
- connections: IMPORTANT - list of other location IDs directly reachable from here (e.g., ["hallway", "garden"])
- contains: list of sub-location IDs inside this location (e.g., a building contains rooms)

LOCATION EXAMPLES:
- A castle with a dungeon and tower: connections: ["great_hall", "dungeon", "tower"]
- A room inside a building: the building's "contains" should list this room
- Distant locations (another city): should NOT be in connections unless travel happens

=== OUTPUT FORMAT ===
Return ONLY this JSON structure, nothing else:

{{
  "characters": [
    {{"id": "...", "name": "...", "emotion": "...", "state": "...", "appearance": "..."}}
  ],
  "locations": [
    {{"id": "...", "name": "...", "connections": ["loc_id1", "loc_id2"], "contains": ["sub_loc"]}}
  ]
}}

Return ONLY valid JSON, no markdown or explanations."""


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


EXTRACT_EVENTS_PROMPT = """Extract EVENTS from the text below.

TEXT:
{chapter_text}

=== GLOBAL CONSTRAINTS (CRITICAL) ===
- ONLY use character, item, and location IDs that were already extracted in previous phases.
- DO NOT invent new entities.
- DO NOT repeat the same event multiple times.
- If an event clearly happens once, extract it ONCE.

=== CRITICAL INSTRUCTIONS ===
- DO NOT INVENT EVENTS: Only extract what EXPLICITLY happens in the text.
- DO NOT HALLUCINATE DEATHS: Use "die" ONLY if a character explicitly dies in THIS chapter.
- Prefer UNDER-extraction to over-extraction if unsure.

=== CHARACTER BEHAVIOR ANALYSIS (VERY IMPORTANT) ===
Pay special attention to behavior that is EMOTIONALLY or NARRATIVELY SIGNIFICANT:

- Hostile characters showing warmth, kindness, praise, encouragement, or farewell
- Enemies helping, comforting, or protecting each other
- Unexpected emotional reactions (smiles, hugs, waves, encouragement)
- Actions that CONTRADICT established relationships

These events are CRITICAL for narrative consistency checks.

=== EVENTS ===
Extract ALL SIGNIFICANT plot actions in CHRONOLOGICAL ORDER.

HIGH PRIORITY EVENTS (DO NOT SKIP):
- ★ OUT-OF-CHARACTER BEHAVIOR:
  - hostile → kind
  - enemy → supportive
  - cold → affectionate
- ★ EMOTIONAL INTERACTIONS:
  hug, smile, wave, praise, encourage, farewell
- ★ ARRIVALS AND DEPARTURES:
  arrive, leave, escape
- ★ MAJOR ACTIONS:
  attack, help, discover, die
- ★ ITEM INTERACTIONS:
  give, take (ONLY if narratively relevant)

LOW PRIORITY (INCLUDE ONLY IF PLOT-RELEVANT):
- Routine dialogue ("talk") — do NOT extract every line of conversation
- Repeated or redundant dialogue — summarize as a SINGLE event

DO NOT INCLUDE:
- Repeated dialogue or actions already captured earlier
- Long back-and-forth conversations unless they change the story state
- Mundane actions with no narrative consequence

=== EVENT DEDUPLICATION RULE (CRITICAL) ===
If the same action is described multiple times or repeated later in the text:
- Extract it ONCE
- Use the FIRST occurrence as source_text

=== EVENT FORMAT ===
- id: e1, e2, e3... (strictly sequential, no gaps)
- type: meet | talk | think | give | take | attack | help | discover | escape | arrive | leave | die | hug | praise | farewell | encourage | smile | wave
- agent: character id
- patient: character id OR item id OR null
- location: location id OR null
- after: event id ONLY if there is an explicit causal dependency
- source_text: REQUIRED — exact quote from the chapter (≤ 80 chars)

=== EVENT RULES ===
- agent MUST be a character
- agent ≠ patient
- patient may be null if unclear
- location may be null if not explicit
- NEVER invent agents, patients, or locations
- source_text MUST be copied verbatim from the chapter (no paraphrasing)

=== OUTPUT FORMAT ===
Return ONLY this JSON structure:

{{
  "events": [
    {{
      "id": "e1",
      "type": "...",
      "agent": "...",
      "patient": "...",
      "location": "...",
      "after": null,
      "source_text": "exact quote from chapter"
    }}
  ]
}}

Return ONLY valid JSON. No markdown. No explanations."""
