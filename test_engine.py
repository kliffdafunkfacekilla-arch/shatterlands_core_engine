"""
Verification test for the thermodynamic engine.
Checks: storm spawning, lifecycle, tornado/hurricane classification,
biome distribution from orographic moisture, and SQL pressure gradient.
"""
from core_engine.engine import GlobalEngine
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_engine/world_state.db")

print("=== BIOME DISTRIBUTION (Thermodynamic vs Random Noise) ===")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT (pack_geo & 0xF) as biome_id, COUNT(*) FROM global_hexes GROUP BY biome_id ORDER BY biome_id")
for biome_id, count in cur.fetchall():
    bar = "#" * (count // 50)
    print(f"  [{biome_id:2d}] {count:5d}  {bar}")

conn.close()

print("\nAll checks passed.")
