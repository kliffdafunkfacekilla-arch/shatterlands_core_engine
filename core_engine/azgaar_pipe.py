import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import math
import sqlite3
import os
from core_engine.codec import BIOME_MAPPINGS, DEFAULT_TAGS

def ingest_map(json_path, db_path):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error parsing JSON from {json_path}")
            return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cells = data.get("pack", {}).get("cells", [])
    if not cells:
        cells = data.get("cells", [])

    for cell in cells:
        q = cell.get("q")
        r = cell.get("r")

        # TRANSLATE CELL PIXELS TO HEX COORDINATES
        if q is None or r is None:
            p = cell.get("p")
            if p and len(p) == 2:
                x, y = p[0], p[1]
                # Map standard FMG polygon canvas coordinates to a unified hex grid.
                # Assuming generic mapping scale:
                scale = 55.0  # Common FMG to hex scale factor
                q = int((x * (2.0/3.0)) / scale)
                r = int(((-x / 3.0) + (math.sqrt(3)/3.0) * y) / scale)
            else:
                continue

        if q is None or r is None:
            continue


        height = cell.get("height", 0)
        biome_val = cell.get("biome", "")
        biome_str = str(biome_val).lower() if isinstance(biome_val, str) else str(biome_val)

        # Climate variables
        temp = cell.get("temp", 0.0)
        moist = cell.get("moist", 0.0)

        # UNIFIED FLAVOR TREATMENT FOR MARINE TOPOGRAPHY
        # No more arbitrary inversions. A cell's raw elevation value maps straight 
        # into the engine loop as its physical terrain coefficient.
        if biome_str in ["ocean", "marine"]:
            if height > 15:
                biome_str = "vent_field"
            else:
                biome_str = "trench"

        # Get biome ID from mappings core
        biome_id = BIOME_MAPPINGS.get(biome_str, BIOME_MAPPINGS["plains"])

        # Format correctly to read tag values
        formatted_biome_str = biome_str.title().replace(" ", "_")
        tags = DEFAULT_TAGS.get(formatted_biome_str, [])
        if not tags:
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
                    parsed_json = json.loads(row[0])
                    if isinstance(parsed_json, list):
                        micro_data = {"hexes": parsed_json}
                    elif isinstance(parsed_json, dict):
                        micro_data = parsed_json
                except json.JSONDecodeError:
                    pass

            # Inject ecosystem tags and rules
            micro_data["tags"] = tags
            if "rule_overrides" not in micro_data:
                micro_data["rule_overrides"] = {}

            updated_json = json.dumps(micro_data)

            # Map the native elevation index (0-15) cleanly straight into bitwise pack_geo
            elevation_val = max(0, min(15, int(abs(height))))
            pack_geo = (biome_id & 0xF) | ((elevation_val & 0xF) << 4)

            # Save climate data matrices 
            p2 = max(0, min(255, int(abs(temp)*50)))
            p3 = max(0, min(255, int(moist * 10)))

            cursor.execute("SELECT pack_ecology FROM global_hexes WHERE q=? AND r=?", (q, r))
            old_eco = cursor.fetchone()[0] or 0
            p1 = old_eco & 0xFF
            res = (old_eco >> 24) & 0xFFFF
            pack_ecology = p1 | (p2 << 8) | (p3 << 16) | (res << 24)

            cursor.execute("UPDATE global_hexes SET micro_data_json=?, pack_geo=?, pack_ecology=? WHERE q=? AND r=?", (updated_json, pack_geo, pack_ecology, q, r))

    conn.commit()
    conn.close()
    print("Map data normalized and fully populated to the world state database.")

if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")