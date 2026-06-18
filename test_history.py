import sqlite3
import os
import sqlite3
import os
from engine import FractalEngine

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

def setup_test_faction():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Delete existing settlements
    cursor.execute("DELETE FROM settlements")
    cursor.execute("DELETE FROM buildings")
    
    # Spawn a rich, unprotected settlement (wealth high, sec 0)
    cursor.execute("""
        INSERT INTO settlements (hex_id, faction_id, population, food_stockpile, wealth, tech_level, security_points, happiness)
        VALUES (5000, 1, 1000, 500.0, 500.0, 2, 0.0, 0.8)
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    setup_test_faction()
if __name__ == "__main__":
    setup_test_faction()
    engine = FractalEngine(DB_PATH)
    
    print("--- Starting History Log Test (100 Ticks) ---")
    for tick in range(1, 101):
        engine.trigger_tick()
        if tick % 10 == 0:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT population, wealth, security_points, happiness FROM settlements LIMIT 1")
            pop, wealth, sec, happy = cursor.fetchone()
            print(f"Tick {tick:03d} | Pop: {pop} | Wealth: {wealth:.1f} | Security: {sec:.1f} | Happiness: {happy:.2f}")
            conn.close()
