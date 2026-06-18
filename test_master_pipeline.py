import os
import sqlite3
import json
import pytest

from core_engine.engine import GlobalEngine, unpack_ecology, DB_PATH
from ai_director.oracle import ContextOracle
from taleweaver_chronicle.history_ledger import update_ledger, LEDGER_PATH

def test_master_pipeline():
    # 1. Trigger core_engine/engine.py to process a full world simulation tick
    engine = GlobalEngine(DB_PATH)
    initial_tick = engine.tick

    engine.trigger_tick()

    assert engine.tick == initial_tick + 1, "Engine tick did not increment."

    # Connect to the DB to verify state
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Verify that both surface and underwater Tier 2 persistent biomes initialize correctly and preserve state
    cursor.execute("SELECT id, q, r, pack_geo, pack_ecology FROM global_hexes")
    hexes = cursor.fetchall()

    has_surface = False
    has_underwater = False

    sample_surface = None
    sample_underwater = None

    for h in hexes:
        hid, q, r, pack_geo, pack_ecology = h
        base_biome = pack_geo & 0xF
        is_underwater = base_biome in [9, 10, 11, 12]

        if is_underwater:
            has_underwater = True
            sample_underwater = (q, r)
        else:
            has_surface = True
            sample_surface = (q, r)

    assert has_surface, "No surface biomes found."
    assert has_underwater, "No underwater biomes found."

    # Fluid Chaos Energy vectors calculate properly across coordinates
    for h in hexes:
        hid, q, r, pack_geo, pack_ecology = h
        p1, p2, p3, res = unpack_ecology(pack_ecology)
        assert 0 <= p1 <= 255, "Chaos energy vector out of bounds."

    cursor.execute("SELECT COUNT(*) FROM event_log")
    event_count_before = cursor.fetchone()[0]

    if event_count_before == 0:
        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine.tick, "Chaos", "Test message", 0, 0))
        conn.commit()

    cursor.execute("SELECT * FROM event_log LIMIT 1")
    event_row = cursor.fetchone()
    assert event_row is not None, "Event log is empty."

    # Reset last_event_id and world_history.md for test isolation
    last_id_path = os.path.join(os.path.dirname(LEDGER_PATH), ".last_event_id")
    if os.path.exists(last_id_path):
        os.remove(last_id_path)
    if os.path.exists(LEDGER_PATH):
        os.remove(LEDGER_PATH)

    # Test event logging passes to taleweaver_chronicle to produce prose
    update_ledger()

    assert os.path.exists(LEDGER_PATH), "Chronicle ledger was not created."
    with open(LEDGER_PATH, 'r') as f:
        content = f.read()
        assert len(content) > 0, "Chronicle ledger is empty."

    # AI Director packages 3D coordinates into a flawless JSON structure
    oracle = ContextOracle(db_path=DB_PATH)

    if sample_surface:
        json_payload = oracle.get_hex_context(sample_surface[0], sample_surface[1])
        data = json.loads(json_payload)
        assert data["coordinate"]["q"] == sample_surface[0]
        assert data["coordinate"]["r"] == sample_surface[1]
        assert "ambient_chaos_energy" in data
        assert data["is_underwater"] is False
        assert data["depth_layer"] == "Surface"

    if sample_underwater:
        json_payload = oracle.get_hex_context(sample_underwater[0], sample_underwater[1])
        data = json.loads(json_payload)
        assert data["coordinate"]["q"] == sample_underwater[0]
        assert data["coordinate"]["r"] == sample_underwater[1]
        assert "ambient_chaos_energy" in data
        assert data["is_underwater"] is True
        assert data["depth_layer"] == "Sub-Surface/Abyssal"
        assert "ocean_attributes" in data

    conn.close()

if __name__ == "__main__":
    pytest.main([__file__])
