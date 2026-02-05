"""
Prompt for extracting EVENTS from chapters.

Part of the four-function extraction pipeline (Phase 2: Split Extraction Prompts).
"""

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
