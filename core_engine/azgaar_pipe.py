import json
import sqlite3
import os
from core_engine.codec import BIOME_MAPPINGS, DEFAULT_TAGS

def ingest_map(json_path, db_path):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error parsing JSON from {json_path}")
            return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cells = data.get("cells", [])

    for cell in cells:
        q = cell.get("q")
        r = cell.get("r")
        if q is None or r is None:
            continue

        height = cell.get("height", 0)
        biome_str = cell.get("biome", "").lower()

        # Climate variables
        temp = cell.get("temp", 0.0)
        moist = cell.get("moist", 0.0)

        # Deep Abyss Inversion
        if biome_str in ["ocean", "marine"] and height < 20:
            height = 20 - height
            if height > 15: # Arbitrary threshold for trench
                biome_str = "trench"
            else:
                biome_str = "vent_field"

        # Get biome ID
        biome_id = BIOME_MAPPINGS.get(biome_str, BIOME_MAPPINGS["plains"])

        # Get default tags
        # Capitalize correctly to match DEFAULT_TAGS keys like 'Vent_Field'
        formatted_biome_str = biome_str.title().replace(" ", "_")
        tags = DEFAULT_TAGS.get(formatted_biome_str, [])
        if not tags:
            # Fallback handling just in case
            if "vent" in biome_str: tags = DEFAULT_TAGS["Vent_Field"]
            elif "ocean" in biome_str or "marine" in biome_str: tags = DEFAULT_TAGS["Ocean"]
            elif "trench" in biome_str: tags = DEFAULT_TAGS["Trench"]
            else: tags = DEFAULT_TAGS["Plains"]

        # Fetch existing micro_data_json if it exists
        cursor.execute("SELECT micro_data_json FROM global_hexes WHERE q=? AND r=?", (q, r))
        row = cursor.fetchone()

        if row:
            micro_data = {}
            if row[0]:
                try:
                    # It might be a list (from pack_micro_cluster) or a dict.
                    # If it's a list, we might need to wrap it or adapt.
                    # Wait, pack_micro_cluster returns a JSON string of a list.
                    # But the requirement asks us to embed tags and rule_overrides into micro_data_json.
                    # If it's a list, we'll convert it to a dict and put the list under 'hexes'.
                    parsed_json = json.loads(row[0])
                    if isinstance(parsed_json, list):
                        micro_data = {"hexes": parsed_json}
                    elif isinstance(parsed_json, dict):
                        micro_data = parsed_json
                except json.JSONDecodeError:
                    pass

            # Inject tags and rule_overrides
            micro_data["tags"] = tags
            if "rule_overrides" not in micro_data:
                micro_data["rule_overrides"] = {}

            updated_json = json.dumps(micro_data)

            # We also might want to update pack_geo based on height and biome_id,
            # but instructions didn't explicitly say to rewrite pack_geo, just to "Map these to specialized sub-surface biome IDs" and "Map elevation, biomes... directly to the database".
            # So let's update pack_geo.
            elevation_val = max(0, min(15, int(abs(height))))
            pack_geo = (biome_id & 0xF) | ((elevation_val & 0xF) << 4)

            # Map climate variables to pack_meso or pack_ecology if needed.
            # But the requirement asks to "Map elevation, biomes, climate variables, and locations directly to the database".
            # Since climate maps to pack_ecology (p2 for temp, p3 for moisture) in db_setup.py.
            p2 = max(0, min(255, int(abs(temp)*50)))
            p3 = max(0, min(255, int(moist * 10)))

            cursor.execute("SELECT pack_ecology FROM global_hexes WHERE q=? AND r=?", (q, r))
            old_eco = cursor.fetchone()[0] or 0
            p1 = old_eco & 0xFF
            res = (old_eco >> 24) & 0xFFFF
            pack_ecology = p1 | (p2 << 8) | (p3 << 16) | (res << 24)

            cursor.execute("UPDATE global_hexes SET micro_data_json=?, pack_geo=?, pack_ecology=? WHERE q=? AND r=?", (updated_json, pack_geo, pack_ecology, q, r))
        else:
            # If cell doesn't exist, we might want to insert, but db_setup.py already inserts hexes.
            pass

    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")
    # ingest_map("path/to/azgaar.json", db_path)
