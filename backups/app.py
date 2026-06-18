import os
import sqlite3
import json
from flask import Flask, jsonify, send_from_directory, request
from engine import GlobalEngine

app = Flask(__name__, static_folder='static')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

engine = GlobalEngine(DB_PATH)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    cursor.execute('SELECT q, r, pack_geo, chaos_domain FROM global_hexes')
    hexes = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT global_hex_id, name, population, faction_id FROM settlements')
    settlements = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT global_hex_id, type FROM world_entities')
    entities = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({
        "hexes": hexes,
        "settlements": settlements,
        "entities": entities
    })

@app.route('/api/hex/<int:q>/<int:r>')
def get_hex(q, r):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, pack_geo, pack_ecology, river_volume, is_lake, chaos_domain FROM global_hexes WHERE q=? AND r=?', (q, r))
    hex_row = cursor.fetchone()
    
    if not hex_row:
        return jsonify({"error": "Hex not found"}), 404
        
    data = dict(hex_row)
    data["biome"] = data["pack_geo"] & 0xF
    data["elevation"] = (data["pack_geo"] >> 4) & 0xF
    
    cursor.execute('SELECT name, population, wealth, security_points FROM settlements WHERE global_hex_id=?', (data["id"],))
    settlement = cursor.fetchone()
    if settlement:
        data["settlement"] = dict(settlement)
        
    conn.close()
    return jsonify(data)

@app.route('/api/cluster/<int:q>/<int:r>')
def get_cluster(q, r):
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
    conn.close()
    
    return jsonify({
        "center_q": q,
        "center_r": r,
        "settlements": settlements,
        "total_population": sum(s["population"] for s in settlements),
        "total_wealth": sum(s["wealth"] for s in settlements)
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
    cursor.execute('SELECT tick, category, message FROM event_logs ORDER BY id DESC LIMIT 50')
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

if __name__ == '__main__':
    app.run(port=5000, debug=True)
