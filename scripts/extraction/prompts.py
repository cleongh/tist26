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
- If no errors found, return: {{"error_count": 0, "errors": [], "chapter_summary": "..."}}
- If errors found, return: {{"error_count": N, "errors": [...], "chapter_summary": "..."}}"""

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
- connections: list of other location IDs (ONLY if explicitly connected - see rules below)
- contains: list of sub-location IDs inside this location (e.g., a building contains rooms)

=== LOCATION CONNECTIVITY (EXPLICIT ONLY) ===
Extract connections ONLY when the text EXPLICITLY states them.

EXTRACT A CONNECTION ONLY IF the text says:
- "from X to Y" / "went from X to Y"
- "through X" / "passed through X"
- "inside X" / "entered X"
- "connected to X" / "leads to X"
- "adjacent to X" / "next to X"
- "part of X" / "within X"
- "door to X" / "path to X" / "stairs to X"

CONNECTION RULES:
1. Connections must be EXPLICIT in the text - never inferred
2. If character travels "from kitchen to garden" → connection(kitchen, garden)
3. If "the door led to the cellar" → connection(current_room, cellar)
4. Connections are SYMMETRIC by default (A→B implies B→A) unless text says otherwise
5. "contains" implies connection (parent ↔ child are connected)

DO NOT EXTRACT CONNECTIONS:
- Based on real-world knowledge ("kitchens are usually near dining rooms")
- Based on building type assumptions ("hotels have lobbies")
- When no explicit travel or path statement exists
- When only ONE location exists in the chapter

IF NO EXPLICIT CONNECTIVITY IS STATED:
- Leave connections as an empty list: []
- This is CORRECT - missing data is better than invented data

LOCATION EXAMPLES:
- "Harry walked from the kitchen to the garden" → kitchen.connections: ["garden"], garden.connections: ["kitchen"]
- "The dungeon was beneath the castle" → castle.contains: ["dungeon"], implies connection
- "She was in the library" (no travel mentioned) → library.connections: [] (empty)
- Distant city mentioned in dialogue → connections: [] (no travel path stated)

=== LOCATION PERSISTENCE (CRITICAL FOR TRACKING) ===
Characters REMAIN at a location until explicitly moved.

RULES:
1. Once a character is placed in a location, they STAY THERE until:
   - The text explicitly moves them ("he left", "she walked to...", "they arrived at...")
   - OR a new explicit location is stated for them

2. For EVENTS: If an event's agent was previously placed in a location AND:
   - They have not been moved since
   - No conflicting location is stated for this event
   → Use the SAME location ID for the event

3. NEVER INFER new locations. Only reuse locations explicitly named in the text.

4. If no location is stated or can be derived from persistence, OMIT location entirely.

=== SCENE CO-LOCATION (CRITICAL FOR CONSISTENCY) ===
When characters interact, they are in the SAME PLACE.

APPLY CO-LOCATION WHEN:
1. Two or more characters interact DIRECTLY:
   - talk, argue, discuss, converse
   - give, take, exchange items
   - fight, attack, defend
   - help, save, rescue
   - hug, kiss, touch physically
   
2. AND a location is EXPLICITLY named in the scene (not just implied)

3. THEN: Mark ALL interacting characters as present at that location

CO-LOCATION DOES NOT APPLY TO:
- Internal thoughts ("He thought about her...")
- Emotional states without interaction ("She felt angry")
- Narration about absent characters ("Meanwhile, far away...")
- Remote communication (letters, magical messages, phones)

MULTIPLE LOCATIONS IN SCENE:
- If the scene mentions multiple locations, only apply co-location when:
  - The text clearly anchors the interaction to ONE specific location
  - E.g., "In the kitchen, Harry and Ron argued" → both at kitchen
  - E.g., "Harry was in the kitchen. Ron shouted from upstairs." → DIFFERENT locations

EXAMPLES:
- "In the Great Hall, Harry spoke to Dumbledore." → BOTH at great_hall
- "'Hello,' said Hermione to Ron in the library." → BOTH at library  
- "Harry and Ron ate dinner together at the table." → BOTH at same location (if table's location known)
- "She thought about meeting him tomorrow." → NO co-location (internal thought)
- "Harry received a letter from Sirius." → NO co-location (remote communication)

PERSISTENCE EXAMPLES:
- "Harry was in the kitchen. He ate breakfast." → e1(arrive, kitchen), e2(eat, kitchen) - persistence
- "Hermione was in the library. Ron joined her." → Ron is also at library (co-location + movement)
- "They talked." (no location context) → OMIT location field entirely

=== LOCATION DIAGNOSTIC (OPTIONAL) ===
When extracting locations, you may include a "location_diagnostic" field to indicate extraction certainty.
This field is OPTIONAL and helps identify why location-based reasoning may be limited.

VALID VALUES:
- "no_location_in_scene": No location is explicitly named in this scene/chapter
- "single_location_only": Only one location exists; no travel or connectivity possible
- "no_connectivity_info": Multiple locations exist but no explicit connections stated
- "implicit_persistence_applied": Location inferred from prior scene via persistence rules

WHEN TO USE:
- Use "no_location_in_scene" when the text never names a specific place
- Use "single_location_only" when all events happen in one named location
- Use "no_connectivity_info" when 2+ locations exist but no travel paths stated
- Use "implicit_persistence_applied" when a location is carried forward from context

RULES:
1. This field reflects EXTRACTION certainty, not logic conclusions
2. It is purely informational - it does NOT affect logic behavior
3. Include it only when it provides useful diagnostic information
4. If unsure, omit the field entirely

FORMAT:
- Add to the "locations" array output, e.g.:
  {{"id": "...", "name": "...", "connections": [], "location_diagnostic": "no_connectivity_info"}}

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
- narrative_time: (OPTIONAL) Only set if text EXPLICITLY signals non-linear narration:
  - "flashback" - explicit flashback ("years earlier...", "in the past...")
  - "memory" - character recalling past ("he remembered when...", "she recalled...")
  - "recollection" - narrator recounting past ("long ago...", "once upon a time...")
  - "dream" - dream sequence ("in his dream...", "while she slept...")
  - "vision" - prophetic or magical vision ("he saw a vision of...")
  - "time_jump" - explicit temporal discontinuity ("three years later...")
  If the event is in normal chronological narrative order, OMIT this field entirely.

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
This establishes the INITIAL location for persistence tracking.

CRITICAL: Initial locations set the baseline for location persistence.
All subsequent events for that character will inherit this location
until an explicit movement or new location is stated.

Format:
- character: character id
- location: location id

EXAMPLES:
- "Harry was in his cupboard under the stairs" → {{"character": "harry_potter", "location": "cupboard"}}
- "The Dursleys were at the breakfast table" → {{"character": "uncle_vernon", "location": "kitchen"}}
- "They were all in the living room" → Extract EACH character with location "living_room"

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
    {{"id": "e1", "type": "...", "agent": "...", "patient": "...", "location": "...", "after": null, "source_text": "exact quote from chapter", "narrative_time": null }}
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
      "type": "meet|talk|give|take|attack|help|discover|arrive|leave|die|hug|praise|farewell|encourage|smile|wave|report|learn",
      "agent": "character_id",
      "patient": "character_id_or_null",
      "recipient": "character_id (ONLY for type=report - the authority being informed)",
      "fact": "short literal description of learned content (ONLY for type=learn)",
      "source": "character_id or item_id providing the information (OPTIONAL, ONLY for type=learn)",
      "location": "location_id_or_null",
      "social_action_type": "OPTIONAL - farewell|neutral_departure|dismissal|good_riddance|encourage|comfort|insult|threaten|apologize (see SOCIAL ACTION TYPING)",
      "source_text": "exact quote from text (max 80 chars)"
    }}
  ],
  "initial_rules": [
    {{"subject": "char_id", "predicate": "hates|loves|hostile|friendly", "object": "char_id"}}
  ],
  "implied_presence": [
    {{"entity": "entity_id", "location": "location_id"}}
  ]
}}

=== SOCIAL ACTION TYPING (OPTIONAL FIELD) ===
DO NOT perform sentiment analysis. DO NOT infer emotions not explicitly present.
This is LEXICAL MATCHING only — use ONLY explicit textual cues.

Events may include an OPTIONAL field: social_action_type
Assign ONLY when the text contains EXPLICIT lexical indicators.

ALLOWED VALUES (closed set):

--- DEPARTURE CATEGORIES (mutually exclusive, use MOST SPECIFIC match) ---

farewell:
  MEANING: Explicit goodwill on departure
  LEXICAL TRIGGERS:
  - "wished him/her well"
  - "said goodbye warmly"
  - "gave a warm farewell"
  - "have a good term/trip/journey"
  - "take care"
  - "good luck" (on departure)
  - "waved goodbye fondly/warmly"

neutral_departure:
  MEANING: Procedural, emotionless leaving or parting
  LEXICAL TRIGGERS:
  - "said goodbye" (no adverb or qualifier)
  - "left without comment"
  - "departed shortly after"
  - "took his/her leave"
  - "headed out"
  - parting with no emotional markers

dismissal:
  MEANING: Cold, indifferent, or curt send-off
  LEXICAL TRIGGERS:
  - "dismissed him/her"
  - "said coldly"
  - "without warmth"
  - "curtly told him/her to go"
  - "brushed him/her aside"
  - "waved him/her off dismissively"
  - "turned away without a word"

good_riddance:
  MEANING: Hostile or contemptuous send-off
  LEXICAL TRIGGERS:
  - "glad to see him/her go"
  - "good riddance"
  - "with obvious contempt"
  - "smirked as he/she left"
  - "sneered at his/her departure"
  - "muttered 'finally' as he/she left"

--- OTHER SOCIAL ACTIONS ---

encourage:
  MEANING: Explicit words of support or confidence-building
  LEXICAL TRIGGERS: "you can do it", "I believe in you", "encouraged him/her"

comfort:
  MEANING: Explicit soothing or consoling someone upset
  LEXICAL TRIGGERS: "it's okay", "don't worry", "comforted him/her", "patted his/her back"

insult:
  MEANING: Explicit verbal attack, mockery, or degradation
  LEXICAL TRIGGERS: "called him/her [slur]", "mocked", "insulted", "sneered"

threaten:
  MEANING: Explicit warning of harm or negative consequences
  LEXICAL TRIGGERS: "I'll make you pay", "you'll regret", "threatened", "or else"

apologize:
  MEANING: Explicit expression of regret
  LEXICAL TRIGGERS: "I'm sorry", "forgive me", "apologized", "my apologies"

CATEGORY SELECTION RULES:
1. Choose the MOST SPECIFIC category supported by explicit text
2. If no explicit lexical cue exists, OMIT social_action_type entirely
3. Do NOT downgrade or upgrade categories without textual support
4. Do NOT infer hostility from relationships or context
5. Departure categories are MUTUALLY EXCLUSIVE — pick ONE

EXAMPLES:
- "'Have a good term,' he said warmly." → social_action_type: "farewell"
- "'Goodbye,' she said." → social_action_type: "neutral_departure" (no emotion marker)
- "He dismissed her with a wave." → social_action_type: "dismissal"
- "'Good riddance,' he muttered." → social_action_type: "good_riddance"
- "They parted ways." → OMIT social_action_type (no explicit cue)
- "She praised him for his excellent work." → social_action_type: "praise"
- "'I'm sorry,' Harry muttered." → social_action_type: "apologize"
- "He nodded at her." → OMIT social_action_type (no explicit social intent)

OUTPUT RULE: If social_action_type is not explicitly indicated by lexical cues, OMIT the field entirely (do not set to null).

=== REPORT EVENTS (INFORMING AUTHORITIES) ===
Use type: "report" when a character EXPLICITLY informs an authority about another character.

REQUIRED FIELDS for report events:
- agent: character who does the reporting
- patient: character being reported about
- recipient: authority figure being informed (teacher, official, parent, etc.)

EXTRACT ONLY IF EXPLICITLY STATED:
- "told X about Y"
- "reported Y to X"
- "informed the teacher about Y"
- "went to tell X what Y had done"

DO NOT:
- Infer reporting from consequences alone (e.g., "X got in trouble" doesn't mean someone reported)
- Invent recipients not mentioned in the text
- Extract if patient (the person reported) is not explicit

EXAMPLES:
- "Neville told McGonagall about Harry"
  → type: "report", agent: "neville_longbottom", patient: "harry_potter", recipient: "professor_mcgonagall"
  
- "She informed the headmaster about what he had done"
  → type: "report", agent: "she_id", patient: "he_id", recipient: "headmaster"
  
- "He got detention" (no explicit reporting action)
  → DO NOT extract as report (consequence only, no explicit informing)

=== LEARN EVENTS (KNOWLEDGE ACQUISITION) ===
Use type: "learn" when a character EXPLICITLY acquires knowledge.

IMPORTANT: This is NOT inference or mind reading.
Extract ONLY when the text EXPLICITLY states learning or being told.

REQUIRED FIELDS for learn events:
- agent: character who acquires the knowledge
- fact: a short, literal description of what is learned (must be text-grounded, not abstract)

OPTIONAL FIELDS:
- source: character or item providing the information (if explicitly stated)

EXPLICIT TRIGGERS (extract ONLY when these appear):
- "learned that ..."
- "found out that ..."
- "was told that ..."
- "heard that ..."
- "read that ..."
- "discovered that ..."
- "realized that ..." (only if discovery is explicit, not internal inference)

RULES:
1. Extract a learn event ONLY if the text explicitly indicates knowledge acquisition
2. The fact field must:
   - Be directly supported by the text
   - Not be paraphrased beyond recognition
   - Be short and literal (a few words describing the learned content)
3. If the learned content is vague or unclear, OMIT the event
4. DO NOT infer knowledge from reactions alone (e.g., "He looked surprised" does not mean he learned something)
5. DO NOT extract if the character already knew the information

EXAMPLES:
- "Hermione found out that the stone was missing."
  → type: "learn", agent: "hermione_granger", fact: "stone_missing"
  
- "Harry learned that Sirius was his godfather."
  → type: "learn", agent: "harry_potter", fact: "sirius_is_godfather", source: null
  
- "Ron was told by Fred that the train would leave at eleven."
  → type: "learn", agent: "ron_weasley", fact: "train_leaves_at_eleven", source: "fred_weasley"
  
- "She read in the Daily Prophet that the prisoner had escaped."
  → type: "learn", agent: "she_id", fact: "prisoner_escaped", source: "daily_prophet"
  
- "He seemed surprised by the news." (no explicit learning)
  → DO NOT extract as learn (reaction only, no explicit knowledge acquisition)

=== IMPLIED PRESENCE (OPTIONAL) ===
Use "implied_presence" to record when an entity is EXPLICITLY tied to a location without a direct movement event.

TRIGGERS (extract ONLY when EXPLICITLY stated):
1. POSSESSED OBJECT AT LOCATION: "His wand was on the table in the kitchen"
   → The wand is in the kitchen (implied_presence: wand at kitchen)
   
2. BODY/SELF-REFERENCE: "He found himself in a dark room" / "She noticed her hands were shaking in the library"
   → The character is at that location (implied_presence: character at location)
   
3. OWNED CONTAINER/ROOM: "Harry's trunk was in his bedroom at Privet Drive"
   → The trunk is in the bedroom (implied_presence: trunk at bedroom)

FORMAT:
- entity: character_id OR item_id (the entity whose presence is implied)
- location: location_id (the location where the entity is present)

EXAMPLES:
- "Harry's wand lay on the nightstand in the dormitory"
  → implied_presence: [{{"entity": "harry_wand", "location": "dormitory"}}]
  
- "She woke up in the hospital wing"
  → implied_presence: [{{"entity": "character_id", "location": "hospital_wing"}}]
  
- "His books were scattered across the common room floor"
  → implied_presence: [{{"entity": "books", "location": "common_room"}}]

DO NOT EXTRACT implied_presence if:
- The presence is only inferred (not explicitly stated)
- A movement event (arrive, leave) already captures the location
- The location is vague or unidentified

If no implied_presence exists, return empty array: "implied_presence": []

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

CRITICAL: If an appearance or location is described in the prose and you omit it, the logic engine CANNOT detect inconsistencies. Your extraction directly enables error detection.

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
- appearance: REQUIRED - ONE or TWO words describing current appearance

=== APPEARANCE RULES (CRITICAL FOR CONSISTENCY DETECTION) ===

EXTRACTION PRIORITY: When in doubt, EXTRACT the appearance. Omitting unusual appearances breaks error detection.

USE "normal" ONLY when:
- The text explicitly states the character looks normal/ordinary/unremarkable
- No visual description is given AND no prior unusual state exists
- The character's appearance is clearly restored from a prior unusual state

NEVER USE "normal" when ANY of these apply:
- The text describes a color change (pale, green, flushed, red, blue, etc.)
- The text describes physical state (muddy, bloody, wet, disheveled, dirty, etc.)
- The text describes injury effects (bruised, swollen, cut, scarred, etc.)
- The text describes emotional manifestation (tearful, trembling, sweating, etc.)
- The text describes transformation or disguise

APPEARANCE EXAMPLES:
- "His face turned pale green" → appearance: "pale green"
- "She was covered in mud" → appearance: "muddy"
- "He looked perfectly normal" → appearance: "normal" (EXPLICITLY stated)
- "Her face was flushed with anger" → appearance: "flushed"
- "The boy with messy black hair" → appearance: "normal" (permanent trait, not unusual)
- "His skin had a greenish tinge" → appearance: "greenish" (NOT "normal")
- "She looked pale and shaken" → appearance: "pale"
- "Blood was dripping from his forehead" → appearance: "bloody"
- No description given → appearance: "normal" (default when truly unspecified)

=== LOCATIONS ===
Specific named places where events occur.

CRITICAL: If a character is described as being IN a location, that location MUST be extracted. Location extraction enables movement tracking.

INCLUDE:
- Named buildings (e.g., The Grand Hotel, City Hospital, Central Station)
- Named streets/addresses (e.g., 5th Avenue, Oak Street, The Old Mill)
- Named rooms if they are settings for events (e.g., The Vault, Room 237, kitchen, living_room)
- ANY location where a character performs an action or is explicitly described as present

DO NOT INCLUDE:
- Generic unnamed places ("a room", "the street", "outside") UNLESS a character acts there
- Places only referenced in dialogue but never actually visited

Format:
- id: lowercase_with_underscores
- name: display name
- connections: list of other location IDs (ONLY if explicitly connected - see rules below)
- contains: list of sub-location IDs inside this location (e.g., a building contains rooms)

=== LOCATION CONNECTIVITY (EXPLICIT ONLY) ===
Extract connections ONLY when the text EXPLICITLY states them.

EXTRACT A CONNECTION ONLY IF the text says:
- "from X to Y" / "went from X to Y"
- "through X" / "passed through X"
- "inside X" / "entered X"
- "connected to X" / "leads to X"
- "adjacent to X" / "next to X"
- "part of X" / "within X"
- "door to X" / "path to X" / "stairs to X"

CONNECTION RULES:
1. Connections must be EXPLICIT in the text - never inferred
2. If character travels "from kitchen to garden" → connection(kitchen, garden)
3. If "the door led to the cellar" → connection(current_room, cellar)
4. Connections are SYMMETRIC by default (A→B implies B→A) unless text says otherwise
5. "contains" implies connection (parent ↔ child are connected)

DO NOT EXTRACT CONNECTIONS:
- Based on real-world knowledge ("kitchens are usually near dining rooms")
- Based on building type assumptions ("hotels have lobbies")
- When no explicit travel or path statement exists
- When only ONE location exists in the chapter

IF NO EXPLICIT CONNECTIVITY IS STATED:
- Leave connections as an empty list: []
- This is CORRECT - missing data is better than invented data

LOCATION EXAMPLES:
- "Harry walked from the kitchen to the garden" → kitchen.connections: ["garden"], garden.connections: ["kitchen"]
- "The dungeon was beneath the castle" → castle.contains: ["dungeon"], implies connection
- "She was in the library" (no travel mentioned) → library.connections: [] (empty)
- Distant city mentioned in dialogue → connections: [] (no travel path stated)

=== LOCATION PERSISTENCE (CRITICAL FOR TRACKING) ===
Characters REMAIN at a location until explicitly moved.

RULES:
1. Once a character is placed in a location, they STAY THERE until:
   - The text explicitly moves them ("he left", "she walked to...", "they arrived at...")
   - OR a new explicit location is stated for them

2. For EVENTS: If an event's agent was previously placed in a location AND:
   - They have not been moved since
   - No conflicting location is stated for this event
   → Use the SAME location ID for the event

3. NEVER INFER new locations. Only reuse locations explicitly named in the text.

4. If no location is stated or can be derived from persistence, OMIT location entirely.

=== SCENE CO-LOCATION (CRITICAL FOR CONSISTENCY) ===
When characters interact, they are in the SAME PLACE.

APPLY CO-LOCATION WHEN:
1. Two or more characters interact DIRECTLY:
   - talk, argue, discuss, converse
   - give, take, exchange items
   - fight, attack, defend
   - help, save, rescue
   - hug, kiss, touch physically
   
2. AND a location is EXPLICITLY named in the scene (not just implied)

3. THEN: Mark ALL interacting characters as present at that location

CO-LOCATION DOES NOT APPLY TO:
- Internal thoughts ("He thought about her...")
- Emotional states without interaction ("She felt angry")
- Narration about absent characters ("Meanwhile, far away...")
- Remote communication (letters, magical messages, phones)

MULTIPLE LOCATIONS IN SCENE:
- If the scene mentions multiple locations, only apply co-location when:
  - The text clearly anchors the interaction to ONE specific location
  - E.g., "In the kitchen, Harry and Ron argued" → both at kitchen
  - E.g., "Harry was in the kitchen. Ron shouted from upstairs." → DIFFERENT locations

EXAMPLES:
- "In the Great Hall, Harry spoke to Dumbledore." → BOTH at great_hall
- "'Hello,' said Hermione to Ron in the library." → BOTH at library  
- "Harry and Ron ate dinner together at the table." → BOTH at same location (if table's location known)
- "She thought about meeting him tomorrow." → NO co-location (internal thought)
- "Harry received a letter from Sirius." → NO co-location (remote communication)

PERSISTENCE EXAMPLES:
- "Harry was in the kitchen. He ate breakfast." → e1(arrive, kitchen), e2(eat, kitchen) - persistence
- "Hermione was in the library. Ron joined her." → Ron is also at library (co-location + movement)
- "They talked." (no location context) → OMIT location field entirely

=== LOCATION DIAGNOSTIC (OPTIONAL) ===
When extracting locations, you may include a "location_diagnostic" field to indicate extraction certainty.
This field is OPTIONAL and helps identify why location-based reasoning may be limited.

VALID VALUES:
- "no_location_in_scene": No location is explicitly named in this scene/chapter
- "single_location_only": Only one location exists; no travel or connectivity possible
- "no_connectivity_info": Multiple locations exist but no explicit connections stated
- "implicit_persistence_applied": Location inferred from prior scene via persistence rules

WHEN TO USE:
- Use "no_location_in_scene" when the text never names a specific place
- Use "single_location_only" when all events happen in one named location
- Use "no_connectivity_info" when 2+ locations exist but no travel paths stated
- Use "implicit_persistence_applied" when a location is carried forward from context

RULES:
1. This field reflects EXTRACTION certainty, not logic conclusions
2. It is purely informational - it does NOT affect logic behavior
3. Include it only when it provides useful diagnostic information
4. If unsure, omit the field entirely

FORMAT:
- Add to the "locations" array output, e.g.:
  {{"id": "...", "name": "...", "connections": [], "location_diagnostic": "no_connectivity_info"}}

=== KNOWN ENTITIES CONTEXT (IMPORTANT) ===
The following characters and locations are ALREADY KNOWN from previous chapters.

KNOWN CHARACTERS (authoritative IDs):
{known_characters_list}

KNOWN LOCATIONS (authoritative IDs):
{known_locations_list}

INSTRUCTIONS:
- Prefer reusing these existing IDs when a character or location appears in this chapter.
- If a name, title, or alias clearly refers to an existing character/location, USE the existing ID.
- Only introduce a NEW character or location if the text clearly introduces someone/somewhere not in the known lists.
- If no characters or locations act in this chapter, return empty lists.

DO NOT:
- Rename existing entities
- Create duplicates for aliases (titles, nicknames, honorifics)
- Invent new entities when an existing one fits

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

=== CHAPTER ENTITY CONTEXT (CRITICAL) ===
The following entities are the ONLY valid references for events in this chapter.

VALID CHARACTERS (agents/patients):
{chapter_character_ids}

VALID ITEMS (patients only):
{chapter_item_ids}

VALID LOCATIONS:
{chapter_location_ids}

INSTRUCTIONS:
- Use ONLY these IDs for agent, patient, and location fields.
- agent MUST be a character from the valid character list.
- patient MUST be a character, item, or null.
- location MUST be from the valid location list or null.
- If an action involves an unknown or unclear entity, use null instead of inventing an ID.

EVENT CONSTRAINT:
- If you cannot express an event using ONLY these IDs, DO NOT extract that event.

=== EVENT DEDUPLICATION RULE (CRITICAL) ===
If the same action is described multiple times or repeated later in the text:
- Extract it ONCE
- Use the FIRST occurrence as source_text

=== EVENT FORMAT ===
- id: e1, e2, e3... (strictly sequential, no gaps)
- type: meet | talk | think | give | take | attack | help | discover | escape | arrive | leave | die | hug | praise | farewell | encourage | smile | wave | report | learn
- agent: character id
- patient: character id OR item id OR null
- recipient: character id (ONLY for type="report" - the authority figure being informed)
- fact: short literal description of learned content (ONLY for type="learn")
- source: character id or item id providing the information (OPTIONAL, ONLY for type="learn")
- location: location id OR null
- after: event id ONLY if there is an explicit causal dependency
- social_action_type: OPTIONAL — farewell | neutral_departure | dismissal | good_riddance | encourage | comfort | insult | threaten | apologize (ONLY if explicitly indicated)
- source_text: REQUIRED — exact quote from the chapter (≤ 80 chars)

=== EVENT RULES ===
- agent MUST be a character
- agent ≠ patient
- patient may be null if unclear
- NEVER invent agents, patients, or locations
- source_text MUST be copied verbatim from the chapter (no paraphrasing)

=== SOCIAL ACTION TYPING (OPTIONAL FIELD) ===
DO NOT perform sentiment analysis. DO NOT infer emotions not explicitly present.
This is LEXICAL MATCHING only — use ONLY explicit textual cues.

Events may include an OPTIONAL field: social_action_type
Assign ONLY when the text contains EXPLICIT lexical indicators.

ALLOWED VALUES (closed set):

--- DEPARTURE CATEGORIES (mutually exclusive, use MOST SPECIFIC match) ---

farewell:
  MEANING: Explicit goodwill on departure
  LEXICAL TRIGGERS:
  - "wished him/her well"
  - "said goodbye warmly"
  - "gave a warm farewell"
  - "have a good term/trip/journey"
  - "take care"
  - "good luck" (on departure)
  - "waved goodbye fondly/warmly"

neutral_departure:
  MEANING: Procedural, emotionless leaving or parting
  LEXICAL TRIGGERS:
  - "said goodbye" (no adverb or qualifier)
  - "left without comment"
  - "departed shortly after"
  - "took his/her leave"
  - "headed out"
  - parting with no emotional markers

dismissal:
  MEANING: Cold, indifferent, or curt send-off
  LEXICAL TRIGGERS:
  - "dismissed him/her"
  - "said coldly"
  - "without warmth"
  - "curtly told him/her to go"
  - "brushed him/her aside"
  - "waved him/her off dismissively"
  - "turned away without a word"

good_riddance:
  MEANING: Hostile or contemptuous send-off
  LEXICAL TRIGGERS:
  - "glad to see him/her go"
  - "good riddance"
  - "with obvious contempt"
  - "smirked as he/she left"
  - "sneered at his/her departure"
  - "muttered 'finally' as he/she left"

--- OTHER SOCIAL ACTIONS ---

encourage:
  MEANING: Explicit words of support or confidence-building
  LEXICAL TRIGGERS: "you can do it", "I believe in you", "encouraged him/her"

comfort:
  MEANING: Explicit soothing or consoling someone upset
  LEXICAL TRIGGERS: "it's okay", "don't worry", "comforted him/her", "patted his/her back"

insult:
  MEANING: Explicit verbal attack, mockery, or degradation
  LEXICAL TRIGGERS: "called him/her [slur]", "mocked", "insulted", "sneered"

threaten:
  MEANING: Explicit warning of harm or negative consequences
  LEXICAL TRIGGERS: "I'll make you pay", "you'll regret", "threatened", "or else"

apologize:
  MEANING: Explicit expression of regret
  LEXICAL TRIGGERS: "I'm sorry", "forgive me", "apologized", "my apologies"

CATEGORY SELECTION RULES:
1. Choose the MOST SPECIFIC category supported by explicit text
2. If no explicit lexical cue exists, OMIT social_action_type entirely
3. Do NOT downgrade or upgrade categories without textual support
4. Do NOT infer hostility from relationships or context
5. Departure categories are MUTUALLY EXCLUSIVE — pick ONE

EXAMPLES:
- "'Have a good term,' he said warmly."
  → type: "talk", social_action_type: "farewell"
  
- "'Goodbye,' she said."
  → type: "talk", social_action_type: "neutral_departure" (no emotion marker)
  
- "He dismissed her with a wave."
  → type: "talk", social_action_type: "dismissal"
  
- "'Good riddance,' he muttered."
  → type: "talk", social_action_type: "good_riddance"
  
- "They parted ways."
  → type: "talk" (OMIT social_action_type - no explicit cue)
  
- "She praised him for his excellent work."
  → type: "talk", social_action_type: "praise"
  
- "'I'm sorry,' Harry muttered."
  → type: "talk", social_action_type: "apologize"
  
- "He nodded at her."
  → type: "talk" (OMIT social_action_type - no explicit social intent)

=== REPORT EVENTS (INFORMING AUTHORITIES) ===
Use type: "report" when a character EXPLICITLY informs an authority about another character.

REQUIRED FIELDS for report events:
- agent: character who does the reporting
- patient: character being reported about
- recipient: authority figure being informed (teacher, official, parent, etc.)

EXTRACT ONLY IF EXPLICITLY STATED:
- "told X about Y"
- "reported Y to X"
- "informed the teacher about Y"
- "went to tell X what Y had done"

DO NOT:
- Infer reporting from consequences alone (e.g., "X got in trouble" doesn't mean someone reported)
- Invent recipients not mentioned in the text
- Extract if patient (the person reported) is not explicit

EXAMPLES:
- "Neville told McGonagall about Harry"
  → type: "report", agent: "neville_longbottom", patient: "harry_potter", recipient: "professor_mcgonagall"
  
- "She informed the headmaster about what he had done"
  → type: "report", agent: "she_id", patient: "he_id", recipient: "headmaster"
  
- "He got detention" (no explicit reporting action)
  → DO NOT extract as report (consequence only, no explicit informing)

=== LEARN EVENTS (KNOWLEDGE ACQUISITION) ===
Use type: "learn" when a character EXPLICITLY acquires knowledge.

IMPORTANT: This is NOT inference or mind reading.
Extract ONLY when the text EXPLICITLY states learning or being told.

REQUIRED FIELDS for learn events:
- agent: character who acquires the knowledge
- fact: a short, literal description of what is learned (must be text-grounded, not abstract)

OPTIONAL FIELDS:
- source: character or item providing the information (if explicitly stated)

EXPLICIT TRIGGERS (extract ONLY when these appear):
- "learned that ..."
- "found out that ..."
- "was told that ..."
- "heard that ..."
- "read that ..."
- "discovered that ..."
- "realized that ..." (only if discovery is explicit, not internal inference)

RULES:
1. Extract a learn event ONLY if the text explicitly indicates knowledge acquisition
2. The fact field must:
   - Be directly supported by the text
   - Not be paraphrased beyond recognition
   - Be short and literal (a few words describing the learned content)
3. If the learned content is vague or unclear, OMIT the event
4. DO NOT infer knowledge from reactions alone (e.g., "He looked surprised" does not mean he learned something)
5. DO NOT extract if the character already knew the information

EXAMPLES:
- "Hermione found out that the stone was missing."
  → type: "learn", agent: "hermione_granger", fact: "stone_missing"
  
- "Harry learned that Sirius was his godfather."
  → type: "learn", agent: "harry_potter", fact: "sirius_is_godfather", source: null
  
- "Ron was told by Fred that the train would leave at eleven."
  → type: "learn", agent: "ron_weasley", fact: "train_leaves_at_eleven", source: "fred_weasley"
  
- "She read in the Daily Prophet that the prisoner had escaped."
  → type: "learn", agent: "she_id", fact: "prisoner_escaped", source: "daily_prophet"
  
- "He seemed surprised by the news." (no explicit learning)
  → DO NOT extract as learn (reaction only, no explicit knowledge acquisition)

=== IMPLIED PRESENCE (OPTIONAL) ===
Use "implied_presence" to record when an entity is EXPLICITLY tied to a location without a direct movement event.

TRIGGERS (extract ONLY when EXPLICITLY stated):
1. POSSESSED OBJECT AT LOCATION: "His wand was on the table in the kitchen"
   → The wand is in the kitchen (implied_presence: wand at kitchen)
   
2. BODY/SELF-REFERENCE: "He found himself in a dark room" / "She noticed her hands were shaking in the library"
   → The character is at that location (implied_presence: character at location)
   
3. OWNED CONTAINER/ROOM: "Harry's trunk was in his bedroom at Privet Drive"
   → The trunk is in the bedroom (implied_presence: trunk at bedroom)

FORMAT:
- entity: character_id OR item_id (the entity whose presence is implied)
- location: location_id (the location where the entity is present)

EXAMPLES:
- "Harry's wand lay on the nightstand in the dormitory"
  → implied_presence: [{{"entity": "harry_wand", "location": "dormitory"}}]
  
- "She woke up in the hospital wing"
  → implied_presence: [{{"entity": "character_id", "location": "hospital_wing"}}]
  
- "His books were scattered across the common room floor"
  → implied_presence: [{{"entity": "books", "location": "common_room"}}]

DO NOT EXTRACT implied_presence if:
- The presence is only inferred (not explicitly stated)
- A movement event (arrive, leave) already captures the location
- The location is vague or unidentified

If no implied_presence exists, return empty array: "implied_presence": []

=== LOCATION RULES (CRITICAL FOR CONSISTENCY DETECTION) ===
 If an event occurs in a clearly named place, location MUST be filled.

WHEN TO SET LOCATION:
- If a character is described acting while being in a place, use that place as the event location
- If the scene has an established location and the event occurs within that scene, use it
- If the text explicitly names where the action takes place, use it

WHEN location = null IS ALLOWED:
- The text truly does not specify any place
- The action occurs in an ambiguous or unnamed location
- No valid location ID exists for the described place

DO NOT:
- Guess locations that are not described
- Invent new location IDs not in the VALID LOCATIONS list
- Use null when a valid location is clearly described

EXAMPLES:
- "Harry walked into the kitchen and grabbed the letter" → location: "kitchen" (action in named place)
- "In the Great Hall, Dumbledore stood up" → location: "great_hall" (scene establishes location)
- "He ran outside" → location: null (generic, not a named location)
- "They talked somewhere" → location: null (unspecified)

=== TEMPORAL ORDERING RULES (CRITICAL FOR ASP REASONING) ===
Temporal relationships enable the logic engine to detect timeline violations.

WATCH FOR TEMPORAL PHRASES:
- "before", "after", "earlier", "later"
- "the day before", "the night before", "previously"
- "had already", "had just", "had been"
- "prior to", "following", "subsequently"
- "first... then", "once... then"

EXTRACTION RULES:

1. EXPLICIT CAUSAL/TEMPORAL DEPENDENCY → Use `after` field:
   - When event B explicitly happens AFTER event A in the narration
   - Set B.after = A.id
   - Example: "After Harry arrived, Hagrid spoke" → speak.after = arrive.id

2. PAST PERFECT / FLASHBACK REFERENCE → Use `temporal_constraints`:
   - When narration references something that happened BEFORE current scene
   - When "had already" or "previously" indicates prior action
   - Format: {{"type": "before", "event": "event_id", "reference": "description"}}

3. INTERRUPTED ACTIONS → Use `after` with correct ordering:
   - "Before X could Y, Z happened" → Z interrupts Y, so extract Z; Y may not complete
   - Only extract the action that actually occurred

DO NOT:
- Infer temporal order from narrative position alone (events listed first aren't necessarily first)
- Guess temporal relationships not explicitly stated
- Create circular dependencies (A.after = B AND B.after = A)

TEMPORAL EXAMPLES:
- "Before Harry could leave, Hagrid arrived"
  → Extract: arrive (e1), after: null (Harry didn't actually leave)
  
- "After the feast ended, they went to bed"
  → Extract: feast_end (e1), go_to_bed (e2), e2.after = "e1"
  
- "She had already left earlier that morning"
  → temporal_constraints: [{{"type": "previous", "event": "leave", "agent": "she_id", "reference": "earlier that morning"}}]
  
- "He had been attacked the night before"
  → temporal_constraints: [{{"type": "previous", "event": "attack", "patient": "he_id", "reference": "the night before"}}]

=== OUTPUT FORMAT ===
Return ONLY this JSON structure:

{{
  "events": [
    {{
      "id": "e1",
      "type": "...",
      "agent": "...",
      "patient": "...",
      "fact": "short literal description (ONLY for type=learn)",
      "source": "character_id or item_id providing info (OPTIONAL, ONLY for type=learn)",
      "location": "...",
      "after": null,
      "social_action_type": "...",
      "source_text": "exact quote from chapter"
    }}
  ],
  "temporal_constraints": [
    {{
      "type": "previous",
      "event": "event_type (e.g., leave, attack, arrive)",
      "agent": "character_id or null",
      "patient": "character_id or null",
      "reference": "temporal phrase from text (e.g., 'earlier that morning', 'the night before')"
    }}
  ],
  "implied_presence": [
    {{
      "entity": "character_id or item_id",
      "location": "location_id"
    }}
  ]
}}

NOTES:
- social_action_type: OMIT this field entirely if no explicit social intent is stated
- temporal_constraints: for events referenced as happening BEFORE the current chapter timeline
- after field: for explicit ordering WITHIN this chapter's events
- If no temporal constraints exist, return empty array: "temporal_constraints": []
- implied_presence: for entities explicitly tied to locations without movement events (see IMPLIED PRESENCE section)
- If no implied_presence exists, return empty array: "implied_presence": []
- For learn events: fact is REQUIRED, source is OPTIONAL (include only if explicitly stated)

Return ONLY valid JSON. No markdown. No explanations."""
