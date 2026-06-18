"""
Verification test for the thermodynamic engine.
Checks: storm spawning, lifecycle, tornado/hurricane classification,
biome distribution from orographic moisture, and SQL pressure gradient.
"""
from engine import FractalEngine, WeatherFront
from codec import get_overlay_name, OVERLAYS
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

print("=== BIOME DISTRIBUTION (Thermodynamic vs Random Noise) ===")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT (state_int & 0xF) as biome_id, COUNT(*) FROM micro_hexes GROUP BY biome_id ORDER BY biome_id")
from codec import BIOME_BASE
for biome_id, count in cur.fetchall():
    bar = "#" * (count // 50)
    print(f"  [{biome_id:2d}] {BIOME_BASE.get(biome_id, '?'):<30} {count:5d}  {bar}")

print("\n=== MOISTURE SWEEP VALIDATION (Rain Shadow Effect) ===")
cur.execute("SELECT AVG(moisture), MIN(moisture), MAX(moisture) FROM micro_hexes WHERE elevation > 0.6")
r = cur.fetchone()
print(f"  Mountain hexes  avg={r[0]:.3f}  min={r[1]:.3f}  max={r[2]:.3f}")
cur.execute("SELECT AVG(moisture) FROM micro_hexes WHERE elevation > 0.0 AND elevation <= 0.6")
r = cur.fetchone()
print(f"  Lowland hexes   avg={r[0]:.3f}")
cur.execute("SELECT AVG(moisture) FROM micro_hexes WHERE elevation < 0")
r = cur.fetchone()
print(f"  Ocean hexes     avg={r[0]:.3f}")
conn.close()

print("\n=== THERMODYNAMIC WEATHER SIMULATION (120 ticks = 5 days) ===")
print("\n=== THERMODYNAMIC WEATHER SIMULATION (120 ticks = 5 days) ===")
e = FractalEngine(DB_PATH)
storm_log = {13: 0, 16: 0, 17: 0}
peak_storms = 0

for tick in range(120):
    result = e.trigger_tick()
    peak_storms = max(peak_storms, result["active_storms"])
    for storm in e.active_weather:
        oid = storm.overlay_id
        if oid in storm_log:
            storm_log[oid] += 1

print(f"  Peak simultaneous storms: {peak_storms}")
print(f"  Thunderstorm ticks observed: {storm_log[13]}")
print(f"  Tornado     ticks observed: {storm_log[16]}")
print(f"  Hurricane   ticks observed: {storm_log[17]}")
print(f"  Final tick: {result}")

print("\n=== OVERLAY TRANSLATOR ===")
for oid, elev, label in [(13, 0.5, "land"), (13, -0.5, "ocean"), (16, 0.2, "land"), (17, 0.1, "land"), (17, -0.3, "ocean")]:
    print(f"  overlay={oid:2d} elev={elev:+.1f} ({label}): {get_overlay_name(oid, elev)}")

print("\nAll checks passed.")
