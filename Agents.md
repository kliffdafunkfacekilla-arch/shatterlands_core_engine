\# Shatterlands Core Engine - AI Project Context



Welcome, Agent. This repository contains the headless, decoupled world simulation state and narrative chronicle framework for the Shatterlands engine. Read this document carefully before proposing or executing changes.



\## 1. Project Architecture \& Directories

\- `core\_engine/`: Hard simulation math. Handles time ticking, player update states, and database tables.

\- `taleweaver\_chronicle/`: Text parsing and narrative chronicle processing. Converts raw DB logs into narrative prose.

\- `ai\_director/`: Automated Game Master layer. Dynamically builds context payloads out of player coordinates.

\- `client\_vtt/`: Frontend player interface. Unpacks data to procedurally render coordinate layouts.



\## 2. Hardcoded World Geometry Constraints

You must strictly maintain the following nested fractal tree constants in all coordinate calculation loops and database schemas:

\- \*\*Tier 1 (Global Map):\*\* Goldberg-polyhedron icosahedral mesh layout. Hardcoded frequency parameter `L=14`. This configuration results in exactly \*\*10,570 Global Hexes\*\*.

\- \*\*Tier 2 (Regional Layer):\*\* A concentric 5-ring cluster containing exactly \*\*91 Regional Travel Hexes\*\* nested inside every single Global Hex. Each regional travel tile represents exactly 18.5 kilometers across.

\- \*\*Tier 3 (Local / Battle Map Layer):\*\* A concentric 55-ring cluster containing exactly \*\*9,100 Local Hexes\*\* nested inside every single Tier 2 Travel Hex. Each local hex tile represents exactly 166.5 meters across.

\- \*\*Tier 4 (Tactical Combat Grid):\*\* Each individual Tier 3 Local Hex functions directly as the character combat battle map. When activated, it scales into a 55-ring layout of \*\*9,100 Tactical Tiles\*\*, each measuring exactly 5 feet (1.5 meters) across.



\## 3. Decoupled State \& Memory Rules

\- \*\*Procedural On-Demand Wilderness:\*\* Out of the 10,570 Global Hexes, only those containing an active settlement, player structure, or active event are unpacked and saved as explicit rows in the database. Empty terrain must remain procedurally calculated on the fly using deterministic coordinates as seeds.

\- \*\*Contextual Translation:\*\* Never introduce redundant database tags for underwater or specialized biomes. The simulation math applies a standard ecological loop, while the UI layer translates outcomes (e.g., Heavy Rain above sea level translates dynamically to a Nutrient Upwelling/Plankton Bloom below sea level).



\## 4. Commands \& Environment

\- \*\*Runtime:\*\* Python 3.11+

\- \*\*Primary Framework:\*\* Flask

\- \*\*Database:\*\* SQLite (`data/world\_state.db`)

\- \*\*Initialization Command:\*\* `python core\_engine/db\_setup.py`

\- \*\*Execution Loop Tick:\*\* Run by calling `trigger\_tick()` inside `core\_engine/engine.py`



\## 5. Coding Style Guidelines

\- Maintain pure separation between state tracking (data layers) and narrative rendering (text loops).

\- All custom database transactions must explicitly enforce foreign key constraints (`PRAGMA foreign\_keys = ON`).

\- Write comprehensive logging points directly into the `event\_log` table for all state disruptions (starvation, crime shifts, layout changes) to serve as prompt feeds for the chronicle parser.

