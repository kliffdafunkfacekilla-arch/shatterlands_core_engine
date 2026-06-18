import sqlite3
import os
import sqlite3
import os
from core_engine.engine import GlobalEngine

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_engine/world_state.db")

def setup_test_faction():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Delete existing settlements
    cursor.execute("DELETE FROM settlements")
    cursor.execute("DELETE FROM buildings")
    
    # Spawn a rich, unprotected settlement (wealth high, sec 0)
    cursor.execute("""
        INSERT INTO settlements (global_hex_id, faction_id, name, population, wealth, security_points)
        VALUES (5000, 1, 'Testville', 1000, 500.0, 0.0)
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    setup_test_faction()
if __name__ == "__main__":
    setup_test_faction()
    engine = GlobalEngine(DB_PATH)
    
    print("--- Starting History Log Test (100 Ticks) ---")
    for tick in range(1, 101):
        engine.trigger_tick()
        if tick % 10 == 0:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT population, wealth, security_points FROM settlements LIMIT 1")
            pop, wealth, sec = cursor.fetchone()
            print(f"Tick {tick:03d} | Pop: {pop} | Wealth: {wealth:.1f} | Security: {sec:.1f}")
            conn.close()
