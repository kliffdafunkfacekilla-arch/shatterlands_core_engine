import os
import sqlite3
import json
from flask import Flask, jsonify, send_from_directory, request
from core_engine.engine import GlobalEngine
from core_engine.codec import unpack_micro_cluster

app = Flask(__name__, static_folder='static')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

engine = GlobalEngine(DB_PATH)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/api/map')
def get_map():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, q, r, pack_geo, pack_ecology, chaos_domain FROM global_hexes')
    hexes = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT global_hex_id, name, population, wealth, faction_id FROM settlements')
    settlements = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT global_hex_id, type FROM world_entities')
    entities = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT id, type, global_q, global_r, is_chaos, chaos_domain FROM weather_systems')
    weather = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({
        "hexes": hexes,
        "settlements": settlements,
        "entities": entities,
        "weather": weather
    })

@app.route('/api/hex/<q>/<r>')
def get_hex(q, r):
    q = int(q)
    r = int(r)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, q, r, pack_geo, pack_ecology, river_volume, is_lake, chaos_domain FROM global_hexes WHERE q=? AND r=?', (q, r))
    hex_row = cursor.fetchone()
    
    if not hex_row:
        return jsonify({"error": "Hex not found"}), 404
        
    data = dict(hex_row)
    data["biome"] = data["pack_geo"] & 0xF
    elevation_val = (data["pack_geo"] >> 4) & 0xF
    if data["biome"] in [9, 10, 11, 12]:
        elevation_val = -elevation_val
    data["elevation"] = elevation_val
    
    cursor.execute('''
        SELECT s.name, s.population, s.wealth, s.security_points, s.inventory_json, s.hidden_cultists, s.magic_loadout, f.name as faction_name, f.special_rule
        FROM settlements s
        LEFT JOIN factions f ON s.faction_id = f.id
        WHERE s.global_hex_id=?
    ''', (data["id"],))
    settlement = cursor.fetchone()
    if settlement:
        data["settlement"] = dict(settlement)
        
    conn.close()
    return jsonify(data)

@app.route('/api/cluster/<q>/<r>')
def get_cluster(q, r):
    q, r = int(q), int(r)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.name as s_name, s.population, s.wealth, f.name as f_name
        FROM settlements s
        JOIN global_hexes g ON s.global_hex_id = g.id
        LEFT JOIN factions f ON s.faction_id = f.id
        WHERE g.q BETWEEN ? AND ? AND g.r BETWEEN ? AND ?
    ''', (q-4, q+4, r-4, r+4))
    settlements = [dict(row) for row in cursor.fetchall()]
    cursor.execute('''
        SELECT count(tr.id) as route_count
        FROM trade_routes tr
        JOIN settlements sa ON tr.settlement_a_id = sa.id
        JOIN global_hexes g ON sa.global_hex_id = g.id
        WHERE g.q BETWEEN ? AND ? AND g.r BETWEEN ? AND ?
    ''', (q-4, q+4, r-4, r+4))
    route_count = cursor.fetchone()["route_count"]

    conn.close()
    
    return jsonify({
        "center_q": q,
        "center_r": r,
        "settlements": settlements,
        "total_population": sum(s["population"] for s in settlements),
        "total_wealth": sum(s["wealth"] for s in settlements),
        "active_trade_routes": route_count
    })

@app.route('/api/micro/<q>/<r>')
def get_micro_cluster(q, r):
    q = int(q)
    r = int(r)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, pack_geo, pack_meso, pack_ecology, micro_data_json FROM global_hexes WHERE q=? AND r=?', (q, r))
    hex_row = cursor.fetchone()
    
    if not hex_row:
        return jsonify({"error": "Hex not found"}), 404
        
    g_id, p_geo, p_meso, p_eco, micro_json = hex_row
    
    micro_hexes = unpack_micro_cluster(q, r, p_geo, p_meso, p_eco, micro_json)
    hexes_list = [
        {"q": hx.q, "r": hx.r, "biome_id": hx.biome_id, "elevation": hx.elevation, "p1": hx.p1, "p2": hx.p2, "p3": hx.p3, "res": hx.res}
        for hx in micro_hexes.values()
    ]
    
    cursor.execute('SELECT name, population, wealth, security_points, micro_q, micro_r FROM settlements WHERE global_hex_id=?', (g_id,))
    settlements = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT type, alignment, micro_q, micro_r FROM world_entities WHERE global_hex_id=?', (g_id,))
    entities = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('''
        SELECT count(tr.id) as route_count
        FROM trade_routes tr
        JOIN settlements sa ON tr.settlement_a_id = sa.id
        JOIN global_hexes g ON sa.global_hex_id = g.id
        WHERE g.q BETWEEN ? AND ? AND g.r BETWEEN ? AND ?
    ''', (q-4, q+4, r-4, r+4))
    route_count = cursor.fetchone()["route_count"]
    
    conn.close()
    return jsonify({
        "global_q": q,
        "global_r": r,
        "micro_hexes": hexes_list,
        "settlements": settlements,
        "entities": entities,
        "active_trade_routes": route_count
    })

@app.route('/api/tick', methods=['POST'])
def run_tick():
    data = request.json or {}
    ticks = data.get("ticks", 1)
    for _ in range(ticks):
        engine.trigger_tick()
    return jsonify({"status": "success", "tick": engine.tick})

@app.route('/api/logs')
def get_logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT tick, category, message, global_q, global_r FROM event_log ORDER BY id DESC LIMIT 50')
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(logs)

@app.route('/api/status')
def get_status():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(population) as pop FROM settlements')
    pop = cursor.fetchone()["pop"]
    conn.close()
    return jsonify({
        "tick": engine.tick,
        "season": engine.season,
        "day": engine.day,
        "year": engine.year,
        "global_population": pop
    })

@app.route('/api/diplomacy')
def get_diplomacy():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT dr.id, s1.name as settlement_a, s2.name as settlement_b, dr.score, dr.last_updated FROM diplomacy_relations dr JOIN settlements s1 ON dr.settlement_a_id = s1.id JOIN settlements s2 ON dr.settlement_b_id = s2.id')
    relations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(relations)

@app.route('/api/crimes')
def get_crimes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT c.id, s.name as settlement, c.type, c.severity, c.reported_at FROM crimes c JOIN settlements s ON c.settlement_id = s.id ORDER BY c.reported_at DESC LIMIT 100')
    crimes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(crimes)

@app.route('/api/trade_routes')
def get_trade_routes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT tr.id, sa.name as settlement_a, sb.name as settlement_b, tr.bandwidth, tr.route_type, f.name as faction_name, f.special_rule
        FROM trade_routes tr
        JOIN settlements sa ON tr.settlement_a_id = sa.id
        JOIN settlements sb ON tr.settlement_b_id = sb.id
        JOIN factions f ON tr.faction_id = f.id
    ''')
    routes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(routes)

if __name__ == '__main__':
    app.run(port=5000, debug=True)

