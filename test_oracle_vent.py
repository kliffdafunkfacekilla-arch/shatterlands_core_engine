import json
import sqlite3
from ai_director.oracle import ContextOracle
from core_engine.engine import DB_PATH, pack_ecology

def test_oracle_vent():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Find a hex to modify
    cursor.execute("SELECT id, q, r, pack_geo FROM global_hexes LIMIT 1")
    hex_id, q, r, pack_geo = cursor.fetchone()

    # Set biome to 12 (Abyssal Trench) and keep elevation same
    elevation_val = (pack_geo >> 4) & 0xF
    new_pack_geo = 12 | (elevation_val << 4)

    # Test 1: Normal trench (temp <= 178)
    pack_eco_trench = pack_ecology(100, 100, 100, 0) # p1, p2, p3, res
    cursor.execute("UPDATE global_hexes SET pack_geo=?, pack_ecology=? WHERE id=?", (new_pack_geo, pack_eco_trench, hex_id))
    conn.commit()

    oracle = ContextOracle(DB_PATH)
    res_trench = json.loads(oracle.get_hex_context(q, r))
    assert res_trench["ocean_attributes"]["underwater_biome"] == "Abyssal Trench", f"Expected Abyssal Trench, got {res_trench['ocean_attributes']['underwater_biome']}"
    print("Normal trench test passed.")

    # Test 2: Hydrothermal Vent (temp > 178)
    pack_eco_vent = pack_ecology(100, 200, 100, 0)
    cursor.execute("UPDATE global_hexes SET pack_geo=?, pack_ecology=? WHERE id=?", (new_pack_geo, pack_eco_vent, hex_id))
    conn.commit()

    res_vent = json.loads(oracle.get_hex_context(q, r))
    assert res_vent["ocean_attributes"]["underwater_biome"] == "Hydrothermal Vent", f"Expected Hydrothermal Vent, got {res_vent['ocean_attributes']['underwater_biome']}"
    print("Hydrothermal vent test passed.")

    conn.close()

if __name__ == "__main__":
    test_oracle_vent()
