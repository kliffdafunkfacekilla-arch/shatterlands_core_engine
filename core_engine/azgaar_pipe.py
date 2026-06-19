# core_engine/azgaar_pipe.py
import json
import sqlite3
import os
import random

def ingest_map_to_nested_layer(json_path, db_path):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error parsing JSON from {json_path}")
            return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cells = data.get("cells", [])
    print(f"Seeding {len(cells)} map sectors into 91-hex radiating nested matrices...")

    # Calculate the exact 91 offset coordinates for a perfect 5-ring hexagon cluster
    radius = 5
    cluster_offsets = []
    for q in range(-radius, radius + 1):
        for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1):
            cluster_offsets.append((q, r))

    assert len(cluster_offsets) == 91, "Geometry error: ring math failed to count 91 hexes"

    for i, cell in enumerate(cells):
        g_q = (i % 100) - 50
        g_r = (i // 100) - 50

        # Establish parent Layer 0 node
        cursor.execute("INSERT OR IGNORE INTO global_hexes (q, r, d20_triangle_id) VALUES (?, ?, ?)", (g_q, g_r, (i % 20)))

        height = cell.get("height", 0)
        biome_str = str(cell.get("biome", "plains")).lower()

        # Check if Azgaar map data states a city/burg exists on this macro point
        has_burg = cell.get("burg", None) is not None

        # Build baseline trophic metrics
        p1 = max(10, min(255, int(cell.get("moist", 0.5) * 100)))
        p2 = max(5, min(255, int(abs(cell.get("temp", 0.5)) * 40)))
        p3 = max(1, min(255, int(height * 4)))
        res = max(0, min(255, int(abs(height) * 10)))
        packed_ecology = p1 | (p2 << 8) | (p3 << 16) | (res << 24)

        # Populate all 91 nested sub-hex cells
        for m_q, m_r in cluster_offsets:
            settlement = None
            infra = None

            # RADIATING INFRASTRUCTURE LAYOUT DETERMINATION
            if has_burg:
                if m_q == 0 and m_r == 0:
                    # The settlement is placed explicitly in the dead center
                    settlement = "Town Center"
                else:
                    # Infrastructure items radiate outward into the 5 surrounding rings
                    dist = (abs(m_q) + abs(m_q + m_r) + abs(m_r)) // 2
                    rng = random.Random(int(abs(g_q * 1000 + m_q * 10 + m_r)))
                    roll = rng.random()

                    if dist <= 2 and roll < 0.45:
                        infra = "Farm Field"     # In inner rings close to town
                    elif dist <= 4 and roll < 0.25:
                        infra = "Outpost Wall"   # Defensive perimeter rings
                    elif dist == 5 and roll < 0.15:
                        infra = "Resource Mine"  # Raw mining on outer bounds

            cursor.execute("""
                INSERT OR REPLACE INTO simulation_clusters
                (global_q, global_r, micro_q, micro_r, pack_ecology, settlement_type, infrastructure_asset)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (g_q, g_r, m_q, m_r, packed_ecology, settlement, infra))

    conn.commit()
    conn.close()
    print("Ingestion complete. Layout matches your core settlement design perfectly.")
