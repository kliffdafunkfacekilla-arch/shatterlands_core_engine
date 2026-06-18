import sqlite3
import os
import sqlite3
import os
from core_engine.engine import GlobalEngine
from core_engine.codec import unpack_micro_cluster

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_engine/world_state.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Find an ideal Fauna hex (15) and a Desert hex (0)
cursor.execute("SELECT id FROM global_hexes LIMIT 1")
fauna_hex = cursor.fetchone()[0]
cursor.execute("SELECT id FROM global_hexes ORDER BY id DESC LIMIT 1")
desert_hex = cursor.fetchone()[0]

print(f"Spawning Settlement 1 on Hex (ID: {fauna_hex})")
print(f"Spawning Settlement 2 on Hex (ID: {desert_hex})")

# Clean existing settlements for the test
cursor.execute("DELETE FROM settlements")
conn.commit()

# Insert test settlements
cursor.execute("INSERT INTO settlements (global_hex_id, faction_id, name, population) VALUES (?, 1, 'Test1', 100)", (fauna_hex,))
cursor.execute("INSERT INTO settlements (global_hex_id, faction_id, name, population) VALUES (?, 2, 'Test2', 100)", (desert_hex,))
conn.commit()
conn.close()

engine = GlobalEngine(DB_PATH)

print("\n--- Running 100 ticks ---")
for i in range(100):
    engine.trigger_tick()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT faction_id, population FROM settlements")
for faction, pop in cursor.fetchall():
    print(f"Faction {faction}: Population = {pop}")
conn.close()
