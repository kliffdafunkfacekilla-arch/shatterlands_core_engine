1. **Update Core Constants Matrix (`core_engine/codec.py`)**:
   - Ensure `BIOME_MAPPINGS` dict maps string names ('ocean', 'reef', 'vent_field', 'trench', 'plains', 'forest', 'mountain', etc.) to biome IDs (0-15).
   - Establish `CHAOS_DOMAINS` dict (e.g. WARP_STORM, CULT_INSURGENCY).
   - Define a `DEFAULT_TAGS` dictionary mapping string biome names to default emergent property tag arrays.

2. **Build Map Ingestion Module (`core_engine/azgaar_pipe.py`)**:
   - Create a new module that exposes a function `ingest_map(json_path, db_path)`.
   - Read JSON file, for each cell map to database (by matching coordinates `q`, `r` in `global_hexes`).
   - If biome is 'ocean' or 'marine' (or derived height < 20), apply Deep Abyss Inversion Formula: `New_Height = 20 - h`. Map these to specialized sub-surface biome IDs ('vent_field' or 'trench').
   - Extract `DEFAULT_TAGS` based on biome, embed this array into `global_hexes.micro_data_json`.
   - Also insert an empty `rule_overrides` dictionary into `global_hexes.micro_data_json` if it doesn't exist, updating the record.

3. **Build Modifiers & Overrides Controller (`core_engine/override_panel.py`)**:
   - Create a new module with functions like `apply_override(q, r, modifier_dict, db_path)`.
   - Do not alter `settlements` tables directly here.
   - Fetch the hex's `micro_data_json`, decode it, inject or update keys inside `rule_overrides` (like `population_growth_modifier`, `resource_tick_multiplier`, `production_cost_scalar`).
   - Allow appending tags to a `custom_tags` list or similar structure in `micro_data_json`.

4. **Implement Emergent Tag Evaluation Loop (`core_engine/engine.py`)**:
   - In `engine.py` (e.g., within `trigger_tick` or wherever population is grown/reduced), read the `rule_overrides` from `micro_data_json` inside the loop fetching `settlements` data.
   - Extract `population_growth_modifier` etc. and use it to adjust the baseline engine equations (like multiplying `pop += 1` logic or farm_mult logic by these multipliers).
   - Read local cell tags, cross-reference against intersecting weather/storm attribute tags.
   - Example: if a cell has "FLAMMABLE" and a storm has "FIRE", trigger an effect (remove "FLAMMABLE", add "CHARRED", modifying hazards). Storm entities might need an `attributes_str` or tags system.

5. **Execute Pre-Commit Steps**
   - Call `pre_commit_instructions` to ensure proper testing, verification, review, and reflection are done.

6. **Submit**
   - Submit the changes using the `submit` tool.
