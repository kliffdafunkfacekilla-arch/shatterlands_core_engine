import sqlite3
import json
import os
from core_engine.engine import unpack_ecology, DB_PATH

class ContextOracle:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def get_hex_context(self, q, r):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Fetch base hex data
        cursor.execute("""
            SELECT id, pack_geo, pack_meso, pack_ecology, micro_data_json, wind_direction
            FROM global_hexes
            WHERE q=? AND r=?
        """, (q, r))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return {"error": f"Hex ({q}, {r}) not found."}

        hex_id, pack_geo, pack_meso, pack_ecology, micro_data_json, wind_direction = row

        p1_chaos, p2_temp, p3_moist, res = unpack_ecology(pack_ecology)

        base_biome = pack_geo & 0xF
        elevation_val = (pack_geo >> 4) & 0xF

        is_underwater = base_biome in [9, 10, 11, 12]

        # Determine depth layer and specific attributes
        depth_layer = "Surface"
        ocean_attributes = {}
        if is_underwater:
            depth_layer = "Sub-Surface/Abyssal"
            if base_biome == 9:
                biome_name = "Ocean"
            elif base_biome == 10:
                biome_name = "Bioluminescent Reef"
            elif base_biome == 11:
                biome_name = "Arctic Ocean"
            elif base_biome == 12:
                biome_name = "Abyssal Trench"

            ocean_attributes = {
                "underwater_biome": biome_name,
                "active_current_index": wind_direction
            }

            # Extract deep resource supply networks from micro_data_json if available
            deep_resources = []
            if micro_data_json:
                micro_data = json.loads(micro_data_json)
                for hx in micro_data:
                    if "res_special" in hx and hx["res_special"]:
                        deep_resources.append({
                            "q": hx.get("q"),
                            "r": hx.get("r"),
                            "resource": hx.get("res_special")
                        })
            if deep_resources:
                ocean_attributes["deep_resource_networks"] = deep_resources

        # Track magical storms intersecting this coordinate
        cursor.execute("""
            SELECT type, energy, moisture, vorticity, is_chaos, chaos_domain
            FROM weather_systems
            WHERE global_q=? AND global_r=?
        """, (q, r))
        weather_rows = cursor.fetchall()

        storms = []
        environmental_effects = []
        for w_type, energy, moisture, vorticity, is_chaos, chaos_domain in weather_rows:
            storms.append({
                "type": w_type,
                "energy": energy,
                "moisture": moisture,
                "vorticity": vorticity,
                "is_chaos": bool(is_chaos),
                "chaos_domain": chaos_domain
            })

            # Output dynamic environmental side-effects
            if w_type == "Hurricane":
                environmental_effects.append("Heavy rains and flooding. If underwater, translates to massive nutrient upwelling and plankton bloom.")
            elif w_type == "Tornado":
                environmental_effects.append("Violent wind vortex. If underwater, translates to dangerous localized whirlpools/eddies.")
            elif w_type == "Chaos Storm":
                environmental_effects.append(f"Reality distortion from {chaos_domain} domain. Magic is highly volatile.")
            elif w_type == "Overcast":
                environmental_effects.append("Diminished sunlight.")

        conn.close()

        payload = {
            "coordinate": {"q": q, "r": r},
            "ambient_chaos_energy": p1_chaos,
            "temperature": p2_temp,
            "moisture": p3_moist,
            "depth_layer": depth_layer,
            "is_underwater": is_underwater,
        }

        if is_underwater:
            payload["ocean_attributes"] = ocean_attributes

        if storms:
            payload["active_storms"] = storms
            payload["dynamic_environmental_effects"] = environmental_effects

        return json.dumps(payload, indent=2)
