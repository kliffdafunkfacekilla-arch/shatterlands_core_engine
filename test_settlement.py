import sqlite3
import os
import sqlite3
import os
from engine import FractalEngine
from codec import unpack_micro_hex

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

def find_hex_with_resource(cursor, target_res_id):
    cursor.execute("SELECT id, state_int FROM micro_hexes")
    for hex_id, state_int in cursor.fetchall():
        if unpack_micro_hex(state_int)["resource_id"] == target_res_id:
            return hex_id
    return None

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Find an ideal Fauna hex (15) and a Desert hex (0)
fauna_hex = find_hex_with_resource(cursor, 15)
if not fauna_hex:
    cursor.execute("SELECT id FROM micro_hexes LIMIT 1")
    fauna_hex = cursor.fetchone()[0]
desert_hex = find_hex_with_resource(cursor, 0)
if not desert_hex:
    cursor.execute("SELECT id FROM micro_hexes ORDER BY id DESC LIMIT 1")
    desert_hex = cursor.fetchone()[0]

print(f"Spawning Settlement 1 on Hex (ID: {fauna_hex})")
print(f"Spawning Settlement 2 on Hex (ID: {desert_hex})")

# Activate clusters
cursor.execute("SELECT cluster_id FROM micro_hexes WHERE id IN (?, ?)", (fauna_hex, desert_hex))
for (c_id,) in cursor.fetchall():
    cursor.execute("UPDATE clusters SET is_active=1 WHERE cluster_id=?", (c_id,))
conn.commit()

# Clean existing settlements for the test
cursor.execute("DELETE FROM settlements")
conn.commit()

# Insert test settlements
cursor.execute("INSERT INTO settlements (hex_id, faction_id, population, food_stockpile) VALUES (?, 1, 100, 500.0)", (fauna_hex,))
cursor.execute("INSERT INTO settlements (hex_id, faction_id, population, food_stockpile) VALUES (?, 2, 100, 500.0)", (desert_hex,))
conn.commit()
conn.close()

engine = FractalEngine(DB_PATH)

# The Desert settlement will just eat its stockpile since Desert yields 0 food.
# Wait, the engine process_ecology currently yields food?
# Actually process_ecology only changes res_id, it doesn't automatically add to food_stockpile.
# Let's see what the metabolic loop does. Ah! The metabolic loop only *consumes* food.
# We need to add the harvest_yield to the food_stockpile in process_ecology!

print("\n--- Running 100 ticks ---")
for i in range(100):
    engine.trigger_tick()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT faction_id, population, food_stockpile FROM settlements")
for faction, pop, food in cursor.fetchall():
    print(f"Faction {faction}: Population = {pop}, Food = {food:.1f}")
conn.close()
