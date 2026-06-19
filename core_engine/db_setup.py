# core_engine/db_setup.py
import sqlite3

def initialize_shatterlands_database(db_path="world_state.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Initializing Shatterlands 2-Tier Nested Database...")

    # --- LAYER 0: GLOBAL STRATEGIC GEOGRAPHY (198 km) ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS global_hexes (
        q INTEGER,
        r INTEGER,
        d20_triangle_id INTEGER NOT NULL,
        pack_geo INTEGER DEFAULT 0,       -- Biome ID | Elevation
        PRIMARY KEY (q, r)
    );
    """)

    # --- LAYER 1: NESTED 5-RING SIMULATION CLUSTER (18.5 km) ---
    # Exactly 91 sub-hexes nested inside each global hex block.
    # Settlements sit at (0,0), infrastructure radiates outward.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS simulation_clusters (
        global_q INTEGER,
        global_r INTEGER,
        micro_q INTEGER,
        micro_r INTEGER,
        pack_ecology INTEGER DEFAULT 0,       -- Plants(p1) | Prey(p2) | Predators(p3) | Res(24)
        settlement_type TEXT DEFAULT NULL,    -- Town, Keep, City, or NULL
        infrastructure_asset TEXT DEFAULT NULL, -- Farm, Quarry, Fortification, Mine
        micro_data_json TEXT DEFAULT '{}',    -- Lore tags, rules overrides, crime logs
        PRIMARY KEY (global_q, global_r, micro_q, micro_r),
        FOREIGN KEY (global_q, global_r) REFERENCES global_hexes(q, r) ON DELETE CASCADE
    );
    """)

    # Fast index lookup arrays
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cluster_parent ON simulation_clusters(global_q, global_r);")

    conn.commit()
    conn.close()
    print("Database blueprint verified. System restricted to 2 active nested tables.")

if __name__ == "__main__":
    initialize_shatterlands_database()