"""
Unified extraction prompt for structuring chapters.

This is the comprehensive prompt used by LogicEvaluator._structure_chapter.
"""

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
