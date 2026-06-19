# app.py
import os
import sqlite3
import json
from flask import Flask, jsonify, send_from_directory, request
from core_engine.engine import GlobalEngine
from core_engine.codec import unpack_micro_cluster

app = Flask(__name__, static_folder='client_vtt/src', static_url_path='')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_engine", "world_state.db")
engine = GlobalEngine(DB_PATH)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# --- UNIFIED FRONTEND WEB ASSET ROUTERS ---
@app.route('/')
def index():
    return send_from_directory('client_vtt/src', 'index.html')

@app.route('/<path:path>')
def serve_file(path):
    return send_from_directory('client_vtt/src', path)

# --- BACKEND SIMULATION API ENDPOINTS ---
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
    return jsonify({"hexes": hexes, "settlements": settlements, "entities": entities, "weather": weather})

@app.route('/api/cluster/<global_q>/<global_r>')
def get_cluster(global_q, global_r):
    global_q = int(global_q)
    global_r = int(global_r)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT micro_q, micro_r, pack_ecology, settlement_type, infrastructure_asset, micro_data_json
        FROM simulation_clusters
        WHERE global_q = ? AND global_r = ?
    ''', (global_q, global_r))

    hexes = []
    for row in cursor.fetchall():
        pack_eco = row["pack_ecology"]
        p1 = pack_eco & 0xFF
        p2 = (pack_eco >> 8) & 0xFF
        p3 = (pack_eco >> 16) & 0xFF
        res = (pack_eco >> 24) & 0xFFFF

        hexes.append({
            "micro_q": row["micro_q"],
            "micro_r": row["micro_r"],
            "ecology": {"plants": p1, "prey": p2, "predators": p3, "resources": res},
            "settlement": row["settlement_type"],
            "infrastructure": row["infrastructure_asset"],
            "micro_data": json.loads(row["micro_data_json"]) if row["micro_data_json"] else {}
        })
    conn.close()
    return jsonify({"global_q": global_q, "global_r": global_r, "hexes": hexes})

@app.route('/api/status')
def get_status():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(population) as pop FROM settlements')
    row = cursor.fetchone()
    pop = row["pop"] if row and row["pop"] else 0
    conn.close()
    return jsonify({
        "tick": engine.tick,
        "season": getattr(engine, 'season', 'Unknown'),
        "day": getattr(engine, 'day', 0),
        "year": getattr(engine, 'year', 0),
        "global_population": pop
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
    cursor.execute('SELECT tick, category, message, global_q, global_r FROM event_log ORDER BY id DESC LIMIT 15')
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(logs)

if __name__ == '__main__':
    app.run(port=5000, debug=True)