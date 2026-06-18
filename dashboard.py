import streamlit as st
import sqlite3
import pandas as pd
import os
import json
import time
import math
import plotly.graph_objects as go
from core_engine.engine import GlobalEngine

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

st.set_page_config(page_title="Shatterlands Director", layout="wide")
st.title("Shatterlands Global Director")

# Initialize Engine
if "engine" not in st.session_state:
    st.session_state.engine = GlobalEngine(DB_PATH)
engine = st.session_state.engine

# State for clicked hexes
if "selected_hex" not in st.session_state:
    st.session_state.selected_hex = None
if "cluster_hex" not in st.session_state:
    st.session_state.cluster_hex = None
if "last_click_time" not in st.session_state:
    st.session_state.last_click_time = 0
if "last_click_hex" not in st.session_state:
    st.session_state.last_click_hex = None

# === TOP CONTROLS ===
st.write("### ⚙️ Simulation Controls")
col_slider, col_btn = st.columns([2, 1])
with col_slider:
    ticks_to_run = st.slider("Ticks (+1 Hour each) to simulate:", 1, 100, 1)
with col_btn:
    if st.button("▶ Run Simulation"):
        with st.spinner(f"Running {ticks_to_run} ticks in background..."):
            for _ in range(ticks_to_run):
                engine.trigger_tick()
        st.success("Simulation Complete. Map Synced.")

st.divider()

# === FETCH MAP DATA ===
@st.cache_data(ttl=1)
def get_map_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, q, r, pack_geo FROM global_hexes')
    geo_rows = cursor.fetchall()
    
    cursor.execute('SELECT global_hex_id FROM settlements')
    settlements = {row[0]: True for row in cursor.fetchall()}
    conn.close()
    
    BIOME_COLORS = {
        0: "#FFFF00", # Jungle
        1: "#228B22", # Forest
        2: "#00FFFF", # Taiga
        3: "#DAA520", # Desert
        4: "#6B8E23", # Plains
        5: "#2F4F4F", # Tundra
        6: "#8B4513", # Mountain
        7: "#FF4500", # Volcano
        8: "#FFFAFA", # Arctic
        9: "#20B2AA", # Kelp Forest
        10: "#0000CD", # Coral Reef
        11: "#000080", # Arctic Ocean
        12: "#000033", # Abyssal Trench
        13: "#4B0082"  # Prison Wastes
    }

    xs = []
    ys = []
    colors = []
    qs = []
    rs = []
    texts = []
    
    for h_id, q, r, p_geo in geo_rows:
        biome = p_geo & 0xF
        color = BIOME_COLORS.get(biome, "#333333")
        
        # Plotly coordinates matching original raw grid shape (no hex offset)
        x = q
        y = -r # Negative so higher R goes down
        
        text = f"q={q}, r={r}"
        
        if h_id in settlements:
            color = "#FF00FF" # Magenta for settlements
            text += " 🏰"
            
        xs.append(x)
        ys.append(y)
        colors.append(color)
        qs.append(q)
        rs.append(r)
        texts.append(text)
        
    return xs, ys, colors, qs, rs, texts

xs, ys, colors, qs, rs, texts = get_map_data()

# === THREE PANEL LAYOUT ===
col_left, col_center, col_right = st.columns([1, 2, 1])

with col_center:
    st.subheader("🌐 Interactive Global Map")
    st.caption("Click a hex to inspect it. (Magenta dots = Settlements)")
    
    fig = go.Figure(data=go.Scatter(
        x=xs,
        y=ys,
        mode='markers',
        marker=dict(
            symbol='square', # Square symbol looks better for raw grid
            size=6,
            color=colors
        ),
        text=texts,
        hoverinfo='text'
    ))
    
    fig.update_layout(
        plot_bgcolor='rgb(10,10,10)',
        paper_bgcolor='rgb(10,10,10)',
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        dragmode='pan',
        height=700
    )
    
    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="plotly_map")
    
    if event and event.selection and "points" in event.selection and len(event.selection["points"]) > 0:
        point_idx = event.selection["points"][0]["point_index"]
        
        q = qs[point_idx]
        r = rs[point_idx]
        
        st.session_state.selected_hex = (q, r)

# === LEFT PANEL: HEX DETAILS ===
with col_left:
    st.subheader("📍 Hex Detail")
    if st.session_state.selected_hex:
        q, r = st.session_state.selected_hex
        st.write(f"**Coordinates:** q={q}, r={r}")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, pack_geo, pack_meso, pack_ecology, river_volume, is_lake, chaos_domain FROM global_hexes WHERE q=? AND r=?", (q, r))
        row = cursor.fetchone()
        if row:
            h_id, p_geo, p_meso, p_eco, r_vol, is_lake, domain = row
            biome = p_geo & 0xF
            elevation = (p_geo >> 4) & 0xF
            
            st.write(f"**Biome ID:** {biome}")
            st.write(f"**Elevation Tier:** {elevation}")
            st.write(f"**River Volume:** {r_vol:.1f} | **Lake:** {bool(is_lake)}")
            if domain:
                st.error(f"⚠️ **Chaos Domain:** {domain}")
            
            # Check for settlement
            cursor.execute("""
                SELECT s.name, s.population, s.wealth, s.security_points, s.inventory_json, s.hidden_cultists, s.magic_loadout, f.name, f.special_rule
                FROM settlements s
                LEFT JOIN factions f ON s.faction_id = f.id
                WHERE s.global_hex_id=?
            """, (h_id,))
            s_row = cursor.fetchone()
            if s_row:
                s_name, pop, wealth, sec, inv_str, hidden, loadout_str, f_name, f_rule = s_row
                st.success(f"🏰 **Settlement:** {s_name} ({f_name})")
                st.write(f"**Pop:** {pop:.0f} | **Wealth:** {wealth:.0f} | **Sec:** {sec:.0f}")
                
                try: inv = json.loads(inv_str)
                except: inv = {}
                
                if inv:
                    st.write("**📦 Inventory:**")
                    survival = inv.get("Survival", {})
                    building = inv.get("Building", {})
                    if survival: st.write(f"- *Survival:* Food: {survival.get('Food', 0):.0f} | Water: {survival.get('Water', 0):.0f}")
                    if building: st.write(f"- *Building:* Wood: {building.get('Wood', 0):.0f} | Stone: {building.get('Stone', 0):.0f}")
                
                if hidden > 0:
                    st.error(f"🩸 **Hidden Cultists:** {hidden}")
                
                try: loadout = json.loads(loadout_str)
                except: loadout = []
                if loadout:
                    st.info(f"✨ **Magic Loadout:** {', '.join(loadout)}")
                
            st.divider()
            if st.button("🔍 Inspect Full Cluster (61-Hex Radius)"):
                st.session_state.cluster_hex = (q, r)
                
        else:
            st.write("Hex not found in DB.")
        conn.close()
    else:
        st.info("Click a hex on the map.")

# === RIGHT PANEL: CLUSTER DATA ===
with col_right:
    st.subheader("🧩 Cluster Overview")
    if st.session_state.cluster_hex:
        cq, cr = st.session_state.cluster_hex
        st.write(f"**Cluster Center:** q={cq}, r={cr}")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.population, s.wealth, f.name 
            FROM settlements s
            JOIN global_hexes g ON s.global_hex_id = g.id
            LEFT JOIN factions f ON s.faction_id = f.id
            WHERE g.q BETWEEN ? AND ? AND g.r BETWEEN ? AND ?
        """, (cq-4, cq+4, cr-4, cr+4))
        
        cluster_setts = cursor.fetchall()
        if cluster_setts:
            total_pop = sum(x[0] for x in cluster_setts)
            total_wealth = sum(x[1] for x in cluster_setts)
            factions = set(x[2] for x in cluster_setts)
            
            st.write(f"**Settlements in Radius:** {len(cluster_setts)}")
            st.write(f"**Cluster Pop:** {total_pop:.0f}")
            st.write(f"**Cluster Wealth:** {total_wealth:.0f}")
            
            cursor.execute("""
                SELECT count(tr.id) 
                FROM trade_routes tr
                JOIN settlements sa ON tr.settlement_a_id = sa.id
                JOIN global_hexes g ON sa.global_hex_id = g.id
                WHERE g.q BETWEEN ? AND ? AND g.r BETWEEN ? AND ?
            """, (cq-4, cq+4, cr-4, cr+4))
            route_cnt = cursor.fetchone()[0]
            st.write(f"**Active Trade Routes:** {route_cnt}")
            
            st.write("**Active Factions:**")
            for fac in factions:
                st.write(f"- {fac}")
        else:
            st.write("No settlements in this cluster radius.")
            
        conn.close()
    else:
        st.info("Click the 'Inspect Full Cluster' button on a hex to see the surrounding data.")

    st.divider()
    with st.expander("📊 Live Event Log (Recent History)"):
        conn = sqlite3.connect(DB_PATH)
        import pandas as pd
        try:
            logs = pd.read_sql("SELECT tick, category, message, global_q, global_r FROM event_log ORDER BY tick DESC LIMIT 20", conn)
            st.dataframe(logs, use_container_width=True)
        except Exception as e:
            st.write("No events logged yet.")
        conn.close()
