import sqlite3
import os
import sys

# Ensure we can import from the local directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_parser import parse_event

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core_engine", "world_state.db")
LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_history.md")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_event_id")

def get_last_processed_id():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0
    return 0

def set_last_processed_id(event_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(event_id))

def get_elevation_for_hex(q, r, conn):
    if q is None or r is None:
        return 1 # Default to surface
    cursor = conn.cursor()
    cursor.execute("SELECT pack_geo FROM global_hexes WHERE q=? AND r=?", (q, r))
    row = cursor.fetchone()
    if row:
        pack_geo = row[0]
        # Same logic as unpack_micro_cluster from codec
        base_biome = pack_geo & 0xF
        elevation_val = (pack_geo >> 4) & 0xF
        base_elev = float(elevation_val)
        if base_biome in [9, 10, 11, 12]:
            base_elev = -base_elev
        return base_elev
    return 1

def update_ledger():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    last_id = get_last_processed_id()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM event_log WHERE id > ? ORDER BY id ASC", (last_id,))
    events = cursor.fetchall()

    if not events:
        print("No new events to process.")
        conn.close()
        return

    prose_lines = []
    max_id = last_id

    for row in events:
        event_dict = dict(row)
        q = event_dict.get('global_q')
        r = event_dict.get('global_r')

        elevation = get_elevation_for_hex(q, r, conn)

        prose = parse_event(event_dict, elevation)
        prose_lines.append(prose)

        if row['id'] > max_id:
            max_id = row['id']

    if prose_lines:
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            for line in prose_lines:
                f.write(line + "\n")

        set_last_processed_id(max_id)
        print(f"Appended {len(prose_lines)} events to {LEDGER_PATH}.")

    conn.close()

if __name__ == "__main__":
    update_ledger()
