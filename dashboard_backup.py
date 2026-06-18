# dashboard.py
import streamlit as st
import sqlite3
import pandas as pd
import os
from engine import FractalEngine
from codec import FACTIONS, RESOURCES, OVERLAYS, unpack_micro_hex, get_biome_name, get_overlay_name

import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

st.set_page_config(page_title="Shatterlands Engine", layout="wide")

if "engine" not in st.session_state:
    st.session_state.engine = FractalEngine(DB_PATH)
engine = st.session_state.engine

st.title("🌌 Shatterlands D20 Planet Simulator")

# --- SIDEBAR (Director & Blueprints) ---
with st.sidebar:
    st.header("Blueprint Registry")
    with st.expander("Register New Entity"):
        entity_name = st.text_input("Entity Name")
        category = st.selectbox("Category", ["Flora", "Fauna", "Faction"])
        props = st.text_area("Stats (JSON)", value='{"nutritional_value": 0}')
        
        if st.button("Register Blueprint"):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""CREATE TABLE IF NOT EXISTS entity_registry (
                            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, props_json TEXT)""")
            conn.execute("INSERT INTO entity_registry (name, category, props_json) VALUES (?, ?, ?)", 
                         (entity_name, category, props))
            conn.commit()
            conn.close()
            st.success(f"Registered: {entity_name}")

    st.divider()

    st.subheader("Director Actions")
    target_hex = st.number_input("Target Hex ID", min_value=1, step=1)
    faction = st.selectbox("Faction", list(FACTIONS.values()))
    has_structure = st.checkbox("Build Structure (High Yield / High Impact)", value=False)
    
    if st.button("Spawn Settlement"):
        from engine import FractalEngine
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO settlements (hex_id, faction_id, has_structure) VALUES (?, ?, ?)", 
                     (target_hex, list(FACTIONS.values()).index(faction), 1 if has_structure else 0))
        s_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        engine = FractalEngine(DB_PATH)
        engine.spawn_paragon(s_id, target_hex)
        
        st.success("Settlement spawned!")
        
    if st.button("Build Farm"):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM settlements WHERE hex_id=?", (target_hex,))
        row = cursor.fetchone()
        s_id = row[0] if row else 1
        
        conn.execute("INSERT INTO farms (hex_id, settlement_id, species_name) VALUES (?, ?, 'Gloom-Shroom')", 
                     (target_hex, s_id))
        conn.commit()
        conn.close()
        st.success("Farm established.")

    st.divider()
    h_type = st.selectbox("Hideout Type", ["PiratePort", "SmugglerHideout", "DealerDen"])
    if st.button("Spawn Underworld Hideout"):
        conn = sqlite3.connect(DB_PATH)
        # Using INSERT OR REPLACE to avoid unique constraint if we spawn twice on the same hex
        conn.execute("INSERT OR REPLACE INTO criminal_hideouts (hex_id, type, food_stockpile, wealth) VALUES (?, ?, 20, 0)", 
                     (target_hex, h_type))
        conn.commit()
        conn.close()
        st.warning(f"A hidden {h_type} has emerged.")

    st.divider()
    st.subheader("Fractal Settings")
    target_cluster = st.number_input("Target Cluster ID", min_value=0, step=1)
    if st.button("Activate Cluster"):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE clusters SET is_active=1 WHERE cluster_id=?", (target_cluster,))
        conn.commit()
        conn.close()
        st.success(f"Cluster {target_cluster} is now ACTIVE.")

    with st.expander("👤 Paragon Insight"):
        s_id_input = st.number_input("Target Settlement ID for Paragon", min_value=1, step=1)
        if st.button("Get Personality"):
            conn = sqlite3.connect(DB_PATH)
            p = conn.execute("SELECT archetype, stats_json FROM paragon_profiles WHERE settlement_id=?", (s_id_input,)).fetchone()
            conn.close()
            if p:
                st.write(f"**Archetype**: {p[0]}")
                import json
                st.json(json.loads(p[1]))
            else:
                st.write("No Paragon profile found for this settlement.")

    with st.expander("🛠️ Manage Settlement Structures"):
        settlement_id = st.number_input("Target Settlement ID", min_value=1, step=1)
        b_type = st.selectbox("Building Type", ["Barracks", "Theatre", "Forge", "Academy"])
        
        if st.button("Construct Building"):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO buildings (settlement_id, type) VALUES (?, ?)", 
                         (settlement_id, b_type))
            
            # Apply civic buffs immediately for simplicity
            if b_type == "Barracks":
                conn.execute("UPDATE settlements SET security_points = security_points + 10 WHERE id=?", (settlement_id,))
            elif b_type == "Theatre":
                conn.execute("UPDATE settlements SET happiness = happiness + 0.2 WHERE id=?", (settlement_id,))
            elif b_type == "Academy":
                conn.execute("UPDATE settlements SET tech_level = tech_level + 1 WHERE id=?", (settlement_id,))
                
            conn.commit()
            conn.close()
            st.success(f"{b_type} constructed!")

# --- MAIN TABS ---
tab_genesis, tab_map = st.tabs(["World Genesis", "Planet Map"])

with tab_genesis:
    st.header("🌍 Genesis Control Panel")
    
    # 1. Global Parameters
    col1, col2 = st.columns(2)
    with col1:
        map_size = st.slider("Map Resolution (Grid Size)", 50, 200, 100)
        temp_offset = st.slider("Global Temperature Offset", -1.0, 1.0, 0.0)
    with col2:
        moon_cycle = st.slider("Moon Phase Cycle", 14, 56, 28)
        
    # 2. Genesis Action
    if st.button("🚀 BUILD PLANET"):
        with st.spinner("Generating geography..."):
            from db_setup import init_database, seed_planet
            conn = init_database()
            seed_planet(conn, map_size=map_size)
            conn.close()
            
            # Re-init the engine to clear old RAM weather/events
            st.session_state.engine = FractalEngine(DB_PATH)
            st.session_state.engine.clock.days_in_month = moon_cycle # Apply parameter
            st.success("World Generated!")

with tab_map:
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("Global Clock Tick", engine.clock.tick)
    with col2: st.metric("Current Season", engine.clock.current_season)
    with col3: st.metric("Moon Phase", engine.clock.moon_phase)
    with col4: st.metric("Daylight Status", "Day" if engine.clock.is_daylight else "Night")
    with col5: st.metric("Active Storms", len(engine.active_weather))

    col_tick1, col_tick2, col_tick3 = st.columns(3)
    with col_tick1:
        if st.button("Trigger Simulation Tick (+1 Hour)"):
            res = engine.trigger_tick()
            st.success(f"Tick completed. Season: {res['season']} | Moon: {res['moon_phase']} | Clusters: {res['processed_clusters']}")
            
    with col_tick2:
        if st.button("Trigger Full Day (+24 Hours)"):
            with st.spinner("Simulating 24 hours..."):
                for _ in range(24):
                    res = engine.trigger_tick()
            st.success(f"24 Ticks completed. Season: {res['season']} | Moon: {res['moon_phase']} | Clusters: {res['processed_clusters']}")
            
    with col_tick3:
        if "auto_tick" not in st.session_state:
            st.session_state.auto_tick = False
            
        def toggle_auto_tick():
            st.session_state.auto_tick = not st.session_state.auto_tick
            
        st.button("Stop Auto-Tick" if st.session_state.auto_tick else "Start Auto-Tick", on_click=toggle_auto_tick)

    st.subheader("🗺️ Micro-Hex Database Snapshot")

    conn = sqlite3.connect(DB_PATH)
    raw_df = pd.read_sql_query("""
        SELECT m.q, m.r, m.elevation, m.temperature, m.moisture, m.climate_band, m.wind_dir, m.state_int, c.cluster_id 
        FROM micro_hexes m
        JOIN clusters c ON m.cluster_id = c.cluster_id
        WHERE c.is_active = 1
        ORDER BY m.q, m.r LIMIT 100
    """, conn)
    conn.close()

    display_data = []
    for index, row in raw_df.iterrows():
        attrs = unpack_micro_hex(int(row['state_int']))
        actual_biome_name = get_biome_name(attrs["biome_id"], row["elevation"])
        actual_overlay_name = get_overlay_name(attrs["overlay_id"], row["elevation"])

        wind_text = "East->West" if row["wind_dir"] == -1 else "West->East"

        display_data.append({
            "Cluster": row['cluster_id'],
            "Q (Lon)": row['q'],
            "R (Lat)": row['r'],
            "Band (0-4)": row['climate_band'],
            "Currents": wind_text,
            "Elevation": round(row['elevation'], 2),
            "Temp": round(row['temperature'], 2),
            "Biome": actual_biome_name,
            "Resource": RESOURCES[attrs["resource_id"]],
            "Overlay": actual_overlay_name,
            "Spark": "Active" if attrs["spark"] else "Dormant"
        })

    st.dataframe(pd.DataFrame(display_data), use_container_width=True)

    with st.expander("📊 Live Event Log"):
        conn = sqlite3.connect(DB_PATH)
        # Check if the event_log table exists to avoid errors on first run
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_log'")
        if cursor.fetchone():
            logs = pd.read_sql("SELECT * FROM event_log ORDER BY tick DESC LIMIT 20", conn)
            st.table(logs)
        else:
            st.write("No events logged yet.")
        conn.close()

if st.session_state.get("auto_tick", False):
    import time
    engine.trigger_tick()
    time.sleep(0.5)
    st.rerun()
