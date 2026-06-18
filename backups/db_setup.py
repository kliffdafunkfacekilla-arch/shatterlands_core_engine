import sqlite3
import os
import math
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

def pseudo_noise(lon, lat, seed=42):
    x = math.cos(lat) * math.cos(lon)
    y = math.cos(lat) * math.sin(lon)
    z = math.sin(lat)
    return (math.sin(x*3 + seed) + math.cos(y*3 + seed) + math.sin(z*3 + seed)) / 3.0

def calculate_base_biome(elevation, temp, moisture):
    # Ocean Biomes
    if elevation < 0.0:
        if elevation < -0.6: return 12 # Abyssal Trench
        if temp > 0.4: return 10 # Coral Reef
        if temp < -0.4: return 11 # Arctic Ocean
        return 9 # Kelp Forest / Open Ocean
        
    # Land Biomes
    if temp < -0.8: return 8 # Arctic
    if elevation > 0.7:
        if temp > 0.6: return 7 # Volcano
        return 6 # Mountain
    if temp > 0.4: return 0 if moisture > 0.3 else 3 # Jungle vs Desert
    elif temp < -0.4: return 2 if moisture > 0.3 else 5 # Taiga vs Tundra
    else: return 1 if moisture > 0.3 else 4 # Forest vs Plains

def init_database(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS global_hexes")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS global_hexes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        q INTEGER, 
        r INTEGER,
        pack_geo INTEGER DEFAULT 0,
        pack_meso INTEGER DEFAULT 0,
        pack_ecology INTEGER DEFAULT 0,
        micro_data_json TEXT,
        flow_target_id INTEGER,
        wind_direction TEXT,
        river_volume INTEGER DEFAULT 0,
        is_lake BOOLEAN DEFAULT 0,
        chaos_domain TEXT
    )""")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ghex_qr ON global_hexes (q, r)")

    cursor.execute("DROP TABLE IF EXISTS factions")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS factions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        treasury REAL DEFAULT 1000.0,
        technology_level INTEGER DEFAULT 1,
        special_rule TEXT
    )""")
    
    cursor.execute("DROP TABLE IF EXISTS faction_relations")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faction_relations (
        faction_a_id INTEGER NOT NULL,
        faction_b_id INTEGER NOT NULL,
        status TEXT DEFAULT 'Neutral',
        trust_level INTEGER DEFAULT 0,
        FOREIGN KEY(faction_a_id) REFERENCES factions(id),
        FOREIGN KEY(faction_b_id) REFERENCES factions(id),
        PRIMARY KEY(faction_a_id, faction_b_id)
    )""")

    cursor.execute("DROP TABLE IF EXISTS settlements")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faction_id INTEGER NOT NULL,
        global_hex_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        settlement_level INTEGER DEFAULT 1,
        population INTEGER DEFAULT 50,
        wealth REAL DEFAULT 100.0,
        security_points REAL DEFAULT 10.0,
        inventory_json TEXT,
        hidden_cultists INTEGER DEFAULT 0,
        magic_loadout TEXT DEFAULT '[]',
        FOREIGN KEY(faction_id) REFERENCES factions(id),
        FOREIGN KEY(global_hex_id) REFERENCES global_hexes(id)
    )""")
    
    cursor.execute("DROP TABLE IF EXISTS trade_routes")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trade_routes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faction_id INTEGER NOT NULL,
        settlement_a_id INTEGER NOT NULL,
        settlement_b_id INTEGER NOT NULL,
        bandwidth INTEGER DEFAULT 10,
        route_type TEXT DEFAULT 'Land',
        FOREIGN KEY(faction_id) REFERENCES factions(id),
        FOREIGN KEY(settlement_a_id) REFERENCES settlements(id),
        FOREIGN KEY(settlement_b_id) REFERENCES settlements(id)
    )""")
    
    cursor.execute("DROP TABLE IF EXISTS buildings")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS buildings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        settlement_id INTEGER NOT NULL,
        type TEXT,
        level INTEGER DEFAULT 1,
        input_materials_json TEXT,
        tags_json TEXT,
        FOREIGN KEY(settlement_id) REFERENCES settlements(id)
    )""")

    cursor.execute("DROP TABLE IF EXISTS paragons")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS paragons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        settlement_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        archetype TEXT,
        level INTEGER DEFAULT 1,
        stats_json TEXT,
        traits_json TEXT,
        motivation TEXT,
        FOREIGN KEY(settlement_id) REFERENCES settlements(id)
    )""")

    cursor.execute("DROP TABLE IF EXISTS world_entities")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS world_entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        global_hex_id INTEGER NOT NULL,
        radius INTEGER DEFAULT 1,
        duration INTEGER DEFAULT 10,
        intensity REAL DEFAULT 1.0,
        alignment TEXT,
        custom_speed INTEGER DEFAULT 1,
        ticks_since_move INTEGER DEFAULT 0,
        FOREIGN KEY(global_hex_id) REFERENCES global_hexes(id)
    )""")

    cursor.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("DROP TABLE IF EXISTS event_log")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tick INTEGER,
        category TEXT,
        message TEXT
    )""")
    
    conn.commit()
    conn.close()

def get_neighbors(q, r):
    return [(q, r-1), (q+1, r-1), (q+1, r), (q, r+1), (q-1, r+1), (q-1, r)]

def step_towards_origin(q, r):
    if q == 0 and r == 0: return (0, 0)
    best = (q, r)
    min_dist = abs(q) + abs(r) + abs(-q-r)
    for nq, nr in get_neighbors(q, r):
        dist = abs(nq) + abs(nr) + abs(-nq-nr)
        if dist < min_dist:
            min_dist = dist
            best = (nq, nr)
    return best

def seed_planet(db_path=DB_PATH, R=57, config=None):
    if config is None:
        config = {"elevation_seed": 100, "temp_offset": 0.0}
        
    init_database(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    elevation_seed = config.get("elevation_seed", 100)
    temp_offset = config.get("temp_offset", 0.0)
    
    hex_coords = []
    for q in range(-R, R+1):
        for r in range(max(-R, -q-R), min(R, -q+R)+1):
            hex_coords.append((q, r))
            
    inner_R = R // 2
    prisons = [
        (0, -R), (R, -R), (R, 0), (0, R), (-R, R), (-R, 0),
        (0, -inner_R), (inner_R, -inner_R), (inner_R, 0), (0, inner_R), (-inner_R, inner_R), (-inner_R, 0)
    ]
    
    leyline_paths = {}
    for p_q, p_r in prisons:
        curr_q, curr_r = p_q, p_r
        while (curr_q, curr_r) != (0, 0):
            next_q, next_r = step_towards_origin(curr_q, curr_r)
            leyline_paths[(curr_q, curr_r)] = (next_q, next_r)
            curr_q, curr_r = next_q, next_r

    map_size = R * 2
    
    elevation_map = {}
    temp_map = {}
    wind_map = {}
    
    for q, r in hex_coords:
        lon = (q / map_size) * math.pi * 2 - math.pi
        lat = (r / map_size) * math.pi - (math.pi / 2)
        
        if lat > 1.047: # Polar N
            wind_dir = "W"
            base_temp = -0.9
        elif lat > 0.26: # Temperate N
            wind_dir = "E"
            base_temp = 0.5
        elif lat > -0.26: # Equatorial
            wind_dir = "W"
            base_temp = 0.8
        elif lat > -1.047: # Temperate S
            wind_dir = "E"
            base_temp = 0.5
        else: # Polar S
            wind_dir = "W"
            base_temp = -0.9
            
        elevation = pseudo_noise(lon, lat, seed=elevation_seed)
        temp = pseudo_noise(lon, lat, seed=elevation_seed+1) * 0.3 + base_temp + temp_offset
        
        if elevation > 0.2:
            temp -= elevation * 0.5
            
        elevation_map[(q, r)] = elevation
        temp_map[(q, r)] = temp
        wind_map[(q, r)] = wind_dir

    air_mass = {k: (10.0 if v < 0.0 else 0.0) for k, v in elevation_map.items()}
    rainfall = {k: 0.0 for k in hex_coords}
    
    vecs = {'W': (-1, 0), 'E': (1, 0)}
    
    for sweep in range(15):
        new_air = {k: 0.0 for k in hex_coords}
        for (q, r), air in air_mass.items():
            if air <= 0: continue
            wq, wr = vecs[wind_map[(q, r)]]
            nq, nr = q + wq, r + wr
            if (nq, nr) in elevation_map:
                diff = elevation_map[(nq, nr)] - elevation_map[(q, r)]
                if diff > 0.05:
                    precip = air * diff * 2.0
                    if precip > air: precip = air
                    rainfall[(nq, nr)] += precip
                    new_air[(nq, nr)] += (air - precip)
                else:
                    new_air[(nq, nr)] += air
        
        air_mass = new_air
        for k in air_mass:
            if elevation_map[k] < 0.0:
                air_mass[k] = 10.0 

    river_volume = {k: int(rainfall[k]) for k in hex_coords}
    is_lake = {k: False for k in hex_coords}
    
    sorted_hexes = sorted(hex_coords, key=lambda k: elevation_map[k], reverse=True)
    
    for q, r in sorted_hexes:
        if river_volume[(q, r)] > 0 and elevation_map[(q, r)] >= 0.0:
            neighbors = get_neighbors(q, r)
            valid_n = [n for n in neighbors if n in elevation_map]
            if not valid_n: continue
            
            lowest = min(valid_n, key=lambda n: elevation_map[n])
            if elevation_map[lowest] < elevation_map[(q, r)]:
                river_volume[lowest] += river_volume[(q, r)]
            else:
                is_lake[(q, r)] = True 
    
    domains = ["Mass", "Ordo", "Motus", "Flux", "Vita", "Nexus", "Ratio", "Anumis", "Lux", "Omen", "Aura", "Lex"]
    prison_domains = {prisons[i]: domains[i] for i in range(12)}
    
    records = []
    coord_to_db_id = {}
    
    for idx, (q, r) in enumerate(hex_coords):
        biome = calculate_base_biome(elevation_map[(q, r)], temp_map[(q, r)], rainfall[(q, r)] / 10.0)
        
        domain = None
        if (q, r) in prisons:
            # Prisons force a specific biome (we'll just use 13 for Prison/Wastes)
            biome = 13
            p1_chaos = 255
            domain = prison_domains[(q, r)]
        elif (q, r) in leyline_paths:
            p1_chaos = 200
        elif (q, r) == (0, 0):
            biome = 13 
            p1_chaos = 255
        else:
            p1_chaos = max(0, min(255, int(abs(elevation_map[(q, r)])*50)))
            
        pack_geo = biome & 0xF
        
        p2 = max(0, min(255, int(abs(temp_map[(q, r)])*50)))
        p3_moisture = max(0, min(255, int((rainfall[(q, r)] + river_volume[(q, r)]) * 10)))
        res = 60000 if (q, r) in leyline_paths else 0
            
        pack_eco = p1_chaos | (p2 << 8) | (p3_moisture << 16) | (res << 24)
        
        db_id = idx + 1
        coord_to_db_id[(q, r)] = db_id
        
        records.append((db_id, q, r, pack_geo, 0, pack_eco, None, None, wind_map[(q, r)], river_volume[(q, r)], 1 if is_lake[(q, r)] else 0, domain))
        
    cursor.executemany("""
        INSERT INTO global_hexes (id, q, r, pack_geo, pack_meso, pack_ecology, micro_data_json, flow_target_id, wind_direction, river_volume, is_lake, chaos_domain)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, records)
    
    flow_updates = []
    for coord, target_coord in leyline_paths.items():
        if coord in coord_to_db_id and target_coord in coord_to_db_id:
            db_id = coord_to_db_id[coord]
            target_id = coord_to_db_id[target_coord]
            flow_updates.append((target_id, db_id))
            
    cursor.executemany("UPDATE global_hexes SET flow_target_id=? WHERE id=?", flow_updates)
    
    cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('current_tick', '0')")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    print("Seeding new Icosahedral Planet with Orographic Weather and Hydrology...")
    seed_planet()
    print("Planet generation complete.")
