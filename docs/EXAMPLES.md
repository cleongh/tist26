# Examples and Tutorials

This guide provides worked examples showing how the Narrative Consistency Checker processes stories, detects violations, and produces results.

---

## Example 1: Hansel and Gretel (No Errors)

### Input Story

```
Once upon a time there was a poor woodcutter who lived with his two children, Hansel and Gretel.
The mother died, and the father took a new wife who was harsh and cruel. A great famine came,
and the stepmother persuaded the father to abandon the children in the forest. The woodcutter led
them deep among the trees, but the children overheard and filled their pockets with white pebbles.
When the moon rose, they dropped the pebbles and found their way home.

The stepmother was angry and forced the father to take them into the forest again. This time Hansel
could only crumble bread for a trail, and the birds ate the crumbs. The children wandered and came
to a cottage made of bread and sugar. They ate from the walls, and an old woman invited them inside.
She was a witch who intended to fatten them and eat them. She shut Gretel into a stall and made
Hansel show his finger each day to see if he was plump.

The witch ordered Gretel to heat the oven. Gretel pretended not to understand and asked the witch
to show her. When the witch leaned in, Gretel pushed her into the oven and shut the door. The
children took treasure from the house and fled. They crossed a wide river with the help of a duck.
At last they found their father, who had been sorry and welcomed them home. The stepmother was
gone, and they lived happily ever after.
```

### Running the Checker

```bash
python scripts/story_lint.py story.txt --backend gemini --verbose
```

### Structured JSON Output

```json
{
  "entities": {
    "characters": [
      {"id": "woodcutter", "name": "The Woodcutter", "description": "A poor man, father of Hansel and Gretel"},
      {"id": "hansel", "name": "Hansel", "description": "Young boy, clever and resourceful"},
      {"id": "gretel", "name": "Gretel", "description": "Young girl, brave and quick-thinking"},
      {"id": "mother", "name": "The Mother", "description": "Biological mother who dies"},
      {"id": "stepmother", "name": "The Stepmother", "description": "Cruel second wife"},
      {"id": "witch", "name": "The Witch", "description": "Old woman who eats children"}
    ],
    "objects": [
      {"id": "white_pebbles", "type": "stones", "description": "Pebbles used to mark the path"},
      {"id": "bread", "type": "food", "description": "Bread crumbs for trail"},
      {"id": "treasure", "type": "valuables", "description": "Treasure from witch's house"}
    ],
    "locations": [
      {"id": "home", "description": "The woodcutter's cottage"},
      {"id": "forest", "description": "Deep forest where children are abandoned"},
      {"id": "gingerbread_house", "description": "Cottage made of bread and sugar"},
      {"id": "river", "description": "Wide river they must cross"}
    ]
  },
  "events": [
    {
      "id": "e1",
      "type": "die",
      "agent": "mother",
      "location": "home",
      "time_start": "t1",
      "time_end": "t1",
      "description": "The mother dies"
    },
    {
      "id": "e2",
      "type": "take",
      "agent": "hansel",
      "patient": "white_pebbles",
      "location": "home",
      "time_start": "t2",
      "time_end": "t2",
      "description": "Hansel fills pockets with pebbles"
    },
    {
      "id": "e3",
      "type": "move",
      "agent": ["woodcutter", "hansel", "gretel"],
      "source": "home",
      "destination": "forest",
      "time_start": "t3",
      "time_end": "t4",
      "description": "Family goes into forest"
    },
    {
      "id": "e4",
      "type": "drop",
      "agent": "hansel",
      "patient": "white_pebbles",
      "location": "forest",
      "time_start": "t4",
      "time_end": "t4",
      "description": "Hansel drops pebbles"
    },
    {
      "id": "e5",
      "type": "move",
      "agent": ["hansel", "gretel"],
      "source": "forest",
      "destination": "home",
      "time_start": "t5",
      "time_end": "t6",
      "description": "Children find way home"
    },
    {
      "id": "e6",
      "type": "move",
      "agent": ["woodcutter", "hansel", "gretel"],
      "source": "home",
      "destination": "forest",
      "time_start": "t7",
      "time_end": "t8",
      "description": "Second journey to forest"
    },
    {
      "id": "e7",
      "type": "drop",
      "agent": "hansel",
      "patient": "bread",
      "location": "forest",
      "time_start": "t8",
      "time_end": "t8",
      "description": "Hansel drops bread crumbs"
    },
    {
      "id": "e8",
      "type": "eat",
      "agent": "birds",
      "patient": "bread",
      "location": "forest",
      "time_start": "t9",
      "time_end": "t9",
      "description": "Birds eat the crumbs"
    },
    {
      "id": "e9",
      "type": "move",
      "agent": ["hansel", "gretel"],
      "source": "forest",
      "destination": "gingerbread_house",
      "time_start": "t10",
      "time_end": "t11",
      "description": "Children find gingerbread house"
    },
    {
      "id": "e10",
      "type": "eat",
      "agent": ["hansel", "gretel"],
      "patient": "gingerbread",
      "location": "gingerbread_house",
      "time_start": "t11",
      "time_end": "t11",
      "description": "Children eat from walls"
    },
    {
      "id": "e11",
      "type": "enter",
      "agent": ["hansel", "gretel"],
      "destination": "gingerbread_house",
      "time_start": "t12",
      "time_end": "t12",
      "description": "Witch invites them inside"
    },
    {
      "id": "e12",
      "type": "push",
      "agent": "gretel",
      "patient": "witch",
      "instrument": "oven",
      "location": "gingerbread_house",
      "time_start": "t13",
      "time_end": "t13",
      "description": "Gretel pushes witch into oven"
    },
    {
      "id": "e13",
      "type": "die",
      "agent": "witch",
      "location": "gingerbread_house",
      "time_start": "t13",
      "time_end": "t13",
      "description": "Witch dies in oven"
    },
    {
      "id": "e14",
      "type": "take",
      "agent": ["hansel", "gretel"],
      "patient": "treasure",
      "location": "gingerbread_house",
      "time_start": "t14",
      "time_end": "t14",
      "description": "Children take treasure"
    },
    {
      "id": "e15",
      "type": "move",
      "agent": ["hansel", "gretel"],
      "source": "gingerbread_house",
      "destination": "river",
      "time_start": "t15",
      "time_end": "t16",
      "description": "Children flee"
    },
    {
      "id": "e16",
      "type": "move",
      "agent": ["hansel", "gretel"],
      "source": "river",
      "destination": "home",
      "time_start": "t17",
      "time_end": "t18",
      "description": "Children return home"
    }
  ],
  "time_order": [
    ["t1", "t2"], ["t2", "t3"], ["t3", "t4"], ["t4", "t5"],
    ["t5", "t6"], ["t6", "t7"], ["t7", "t8"], ["t8", "t9"],
    ["t9", "t10"], ["t10", "t11"], ["t11", "t12"], ["t12", "t13"],
    ["t13", "t14"], ["t14", "t15"], ["t15", "t16"], ["t16", "t17"],
    ["t17", "t18"]
  ],
  "fluents": [
    {"name": "alive", "args": ["mother"], "value": true, "start": "t1", "end": "t1"},
    {"name": "alive", "args": ["witch"], "value": true, "start": "t1", "end": "t13"},
    {"name": "has", "args": ["hansel", "white_pebbles"], "value": true, "start": "t2", "end": "t4"}
  ],
  "traits": [
    {"character": "hansel", "trait": "clever"},
    {"character": "gretel", "trait": "brave"},
    {"character": "stepmother", "trait": "cruel"}
  ]
}
```

### ASP Facts Generated

```prolog
% Characters
character(woodcutter).
character(hansel).
character(gretel).
character(mother).
character(stepmother).
character(witch).

% Objects
object(white_pebbles).
stones(white_pebbles).
object(bread).
food(bread).
object(treasure).
valuables(treasure).

% Locations
location(home).
location(forest).
location(gingerbread_house).
location(river).

% Events
event(e1).
event_type(e1, die).
agent(e1, mother).
location(e1, home).
time(e1, t1, t1).

event(e2).
event_type(e2, take).
agent(e2, hansel).
patient(e2, white_pebbles).
location(e2, home).
time(e2, t2, t2).

% ... (remaining events)

% Time ordering
time_order(t1, t2).
time_order(t2, t3).
% ... (remaining orderings)

% Fluents
holds(alive(mother), t1, t1).
holds(alive(witch), t1, t13).
holds(has(hansel, white_pebbles), t2, t4).

% Traits
trait(hansel, clever).
trait(gretel, brave).
trait(stepmother, cruel).
```

### Result

```json
{
  "error_count": 0,
  "errors": []
}
```

The story is logically consistent!

---

## Example 2: Story with Dead Agent Violation

### Input Story

```
Alice was a brave adventurer. One day, Alice fell from a cliff and died instantly.
The next morning, Alice walked to the village market to buy some bread.
```

### Expected Detection

The system should detect that Alice acts (walks, buys) after dying.

### Structured JSON

```json
{
  "entities": {
    "characters": [
      {"id": "alice", "name": "Alice", "description": "A brave adventurer"}
    ],
    "objects": [
      {"id": "bread", "type": "food"}
    ],
    "locations": [
      {"id": "cliff"},
      {"id": "village_market"}
    ]
  },
  "events": [
    {
      "id": "e1",
      "type": "die",
      "agent": "alice",
      "location": "cliff",
      "time_start": "t1",
      "time_end": "t1",
      "description": "Alice falls and dies"
    },
    {
      "id": "e2",
      "type": "move",
      "agent": "alice",
      "destination": "village_market",
      "time_start": "t2",
      "time_end": "t2",
      "description": "Alice walks to market"
    },
    {
      "id": "e3",
      "type": "take",
      "agent": "alice",
      "patient": "bread",
      "location": "village_market",
      "time_start": "t3",
      "time_end": "t3",
      "description": "Alice buys bread"
    }
  ],
  "time_order": [["t1", "t2"], ["t2", "t3"]]
}
```

### ASP Violations Detected

```prolog
violation(dead_agent, e2).
violation(dead_agent, e3).
```

### Final Result

```json
{
  "error_count": 2,
  "errors": [
    {
      "id": "dead_agent_e2",
      "description": "Alice cannot walk to the village market at t2 because she died at t1. Dead characters cannot perform actions."
    },
    {
      "id": "dead_agent_e3",
      "description": "Alice cannot buy bread at t3 because she died at t1. This is temporally impossible."
    }
  ]
}
```

---

## Example 3: Ubiquity Violation (Bilocation)

### Input Story

```
At noon, John was in Paris having lunch at a café. At the same time, John was
giving a presentation in London. Both events lasted for an hour.
```

### Structured JSON

```json
{
  "entities": {
    "characters": [{"id": "john", "name": "John"}],
    "locations": [
      {"id": "paris_cafe", "description": "Café in Paris"},
      {"id": "london_office", "description": "Office in London"}
    ]
  },
  "events": [
    {
      "id": "e1",
      "type": "eat",
      "agent": "john",
      "location": "paris_cafe",
      "time_start": "t1",
      "time_end": "t2",
      "description": "Lunch in Paris"
    },
    {
      "id": "e2",
      "type": "present",
      "agent": "john",
      "location": "london_office",
      "time_start": "t1",
      "time_end": "t2",
      "description": "Presentation in London"
    }
  ],
  "time_order": []
}
```

Note: `time_order` is empty because both events start and end at the same times (they're simultaneous, not sequential).

### ASP Violations Detected

```prolog
violation(ubiquity, e1, e2).
```

### Final Result

```json
{
  "error_count": 1,
  "errors": [
    {
      "id": "ubiquity_e1_e2",
      "description": "John cannot be in Paris (e1) and London (e2) at the same time. These events overlap temporally but occur in different physical locations."
    }
  ]
}
```

---

## Example 4: Eating Non-Edible Object

### Input Story

```
Hansel was very hungry after getting lost in the forest. 
He found some white pebbles and ate them.
```

### Structured JSON

```json
{
  "entities": {
    "characters": [{"id": "hansel", "name": "Hansel"}],
    "objects": [{"id": "pebbles", "type": "stones"}],
    "locations": [{"id": "forest"}]
  },
  "events": [
    {
      "id": "e1",
      "type": "take",
      "agent": "hansel",
      "patient": "pebbles",
      "location": "forest",
      "time_start": "t1",
      "time_end": "t1"
    },
    {
      "id": "e2",
      "type": "eat",
      "agent": "hansel",
      "patient": "pebbles",
      "location": "forest",
      "time_start": "t2",
      "time_end": "t2"
    }
  ],
  "time_order": [["t1", "t2"]]
}
```

### ASP Facts

```prolog
object(pebbles).
stones(pebbles).  % This triggers not_edible(pebbles) via the world knowledge rules

event(e2).
event_type(e2, eat).
patient(e2, pebbles).
```

### ASP Violations

```prolog
violation(non_edible_food, e2).
```

### Final Result

```json
{
  "error_count": 1,
  "errors": [
    {
      "id": "non_edible_food_e2",
      "description": "Hansel cannot eat pebbles (event e2). Stones and pebbles are not edible according to world knowledge."
    }
  ]
}
```

---

## Example 5: Trait Violation (Claustrophobia)

### Input Story

```
Sarah had severe claustrophobia since childhood. During the adventure,
Sarah climbed down into a narrow cave to retrieve the ancient artifact.
```

### Structured JSON

```json
{
  "entities": {
    "characters": [{"id": "sarah", "name": "Sarah"}],
    "objects": [{"id": "artifact", "type": "treasure"}],
    "locations": [{"id": "narrow_cave", "type": "cave"}]
  },
  "events": [
    {
      "id": "e1",
      "type": "enter",
      "agent": "sarah",
      "destination": "narrow_cave",
      "time_start": "t1",
      "time_end": "t1"
    },
    {
      "id": "e2",
      "type": "take",
      "agent": "sarah",
      "patient": "artifact",
      "location": "narrow_cave",
      "time_start": "t2",
      "time_end": "t2"
    }
  ],
  "traits": [
    {"character": "sarah", "trait": "claustrophobic"}
  ],
  "time_order": [["t1", "t2"]]
}
```

### ASP Facts

```prolog
trait(sarah, claustrophobic).
location(narrow_cave).
cave(narrow_cave).

event(e1).
event_type(e1, enter).
agent(e1, sarah).
destination(e1, narrow_cave).
```

### ASP Violation

```prolog
violation(claustrophobia, e1).
```

### Final Result

```json
{
  "error_count": 1,
  "errors": [
    {
      "id": "claustrophobia_e1",
      "description": "Sarah has claustrophobia and would not voluntarily enter a narrow cave (event e1). This contradicts her established character trait."
    }
  ]
}
```

---

## Example 6: Possession Violation

### Input Story

```
Tom wanted to give Mary a beautiful necklace. 
He gave her the diamond necklace that evening.
But Tom had never owned or acquired any necklace.
```

### Structured JSON

```json
{
  "entities": {
    "characters": [
      {"id": "tom", "name": "Tom"},
      {"id": "mary", "name": "Mary"}
    ],
    "objects": [{"id": "necklace", "type": "jewelry"}]
  },
  "events": [
    {
      "id": "e1",
      "type": "give",
      "agent": "tom",
      "patient": "necklace",
      "recipient": "mary",
      "time_start": "t1",
      "time_end": "t1"
    }
  ],
  "fluents": []
}
```

Note: No `has(tom, necklace)` fluent exists.

### ASP Violation

```prolog
violation(possession, e1).
```

### Final Result

```json
{
  "error_count": 1,
  "errors": [
    {
      "id": "possession_e1",
      "description": "Tom cannot give Mary the necklace (event e1) because he never possessed it. The story establishes no acquisition of the necklace by Tom."
    }
  ]
}
```

---

## Tutorial: Creating Custom Rules

### Step 1: Identify the Constraint

Let's add a rule: "Vegetarians cannot eat meat."

### Step 2: Define World Knowledge

Add to `rules/base.lp`:

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% WORLD KNOWLEDGE: MEAT
% ═══════════════════════════════════════════════════════════════════════════════
meat(O) :- beef(O).
meat(O) :- chicken(O).
meat(O) :- pork(O).
meat(O) :- lamb(O).
meat(O) :- fish(O).
meat(O) :- bacon(O).
meat(O) :- steak(O).
```

### Step 3: Add the Violation Rule

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% TRAIT: VEGETARIAN
%
% Vegetarians do not eat meat. If a vegetarian character eats a meat object,
% this is a consistency violation.
% ═══════════════════════════════════════════════════════════════════════════════

violation(vegetarian_eating_meat, E) :-
    trait(C, vegetarian),           % Character has vegetarian trait
    event(E),
    event_type(E, eat),             % It's an eating event
    agent(E, C),                    % The vegetarian is eating
    patient(E, Food),               % What they're eating
    meat(Food).                     % Is meat
```

### Step 4: Test the Rule

Create a test story:

```
Lisa had been a vegetarian for ten years. At the dinner party, 
Lisa ate a delicious steak.
```

### Expected Result

```json
{
  "error_count": 1,
  "errors": [
    {
      "id": "vegetarian_eating_meat_e1",
      "description": "Lisa is a vegetarian but is eating steak in event e1. This contradicts her dietary restriction."
    }
  ]
}
```

---

## Running the Examples

### Basic Usage

```bash
# Check a story with Gemini
python scripts/story_lint.py examples/story.txt --backend gemini

# With verbose output
python scripts/story_lint.py examples/story.txt --backend gemini --verbose

# See the full output including ASP facts
python scripts/story_lint.py examples/story.txt --backend gemini --debug
```

### Inspect the Output

```bash
# View the detailed output
cat output.json | jq '.[-1]'

# View just the violations
cat output.json | jq '.[-1].logic_lint.asp.violations'

# View the structured story
cat output.json | jq '.[-1].logic_lint.structuring.structure'
```

### Create Test Files

```bash
# Create a test file with a known violation
echo "Alice died. Then Alice went shopping." > test_dead.txt

# Run the checker
python scripts/story_lint.py test_dead.txt --backend gemini

# Expected: violation(dead_agent, e2)
```
