"""
Prompt for extracting CHARACTERS and LOCATIONS from chapters.

Part of the four-function extraction pipeline (Phase 2: Split Extraction Prompts).
"""

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
