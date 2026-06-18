# db_setup.py
import sqlite3
import os
import math
from core_engine.codec import pack_micro_hex

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

def pseudo_noise(lon, lat, seed=42):
    x = math.cos(lat) * math.cos(lon)
    y = math.cos(lat) * math.sin(lon)
    z = math.sin(lat)
    return (math.sin(x*3 + seed) + math.cos(y*3 + seed) + math.sin(z*3 + seed)) / 3.0

def calculate_base_biome(elevation, temp, moisture):
    if temp < -0.8: return 8 
    if elevation > 0.7 or elevation < -0.7:
        if temp > 0.6: return 7 
        return 6 
    if temp > 0.4: return 0 if moisture > 0 else 3 
    elif temp < -0.4: return 2 if moisture > 0 else 5 
    else: return 1 if moisture > 0 else 4 

def generate_d20_nodes():
    nodes = []
    lat_offset = 0.4636 
    nodes.append({"lat": math.pi/2, "lon": 0, "overlay_id": 1}) 
    for i in range(5): nodes.append({"lat": lat_offset, "lon": (i * 2 * math.pi) / 5, "overlay_id": i + 2})
    for i in range(5): nodes.append({"lat": -lat_offset, "lon": ((i + 0.5) * 2 * math.pi) / 5, "overlay_id": i + 7})
    nodes.append({"lat": -math.pi/2, "lon": 0, "overlay_id": 12}) 
    return nodes

def init_database(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS production")
    cursor.execute("DROP TABLE IF EXISTS settlements")
    cursor.execute("DROP TABLE IF EXISTS micro_hexes")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS micro_hexes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        q INTEGER, r INTEGER,
        state_int INTEGER,
        elevation REAL,
        temperature REAL,
        moisture REAL,
        climate_band INTEGER,
        wind_dir INTEGER,
        latent_chaos INTEGER DEFAULT 0,
        cluster_id INTEGER DEFAULT 0
    )""")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_hex_qr ON micro_hexes (q, r)")
    
    # Settlements hold the population and economic state
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hex_id INTEGER NOT NULL,
        faction_id INTEGER NOT NULL, population INTEGER NOT NULL DEFAULT 100,
        food_stockpile REAL DEFAULT 500.0, wealth REAL DEFAULT 100.0,
        tech_level INTEGER DEFAULT 1, has_structure INTEGER DEFAULT 0,
        security_points REAL DEFAULT 0.0, happiness REAL DEFAULT 0.7,
        FOREIGN KEY(hex_id) REFERENCES micro_hexes(id)
    )""")
    # Buildings for extraction, civic, etc.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS buildings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        settlement_id INTEGER NOT NULL,
        type TEXT,
        level INTEGER DEFAULT 1,
        hex_dependency INTEGER,
        FOREIGN KEY(settlement_id) REFERENCES settlements(id)
    )""")
    # Production chains link inputs to outputs via tech requirements
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS production (
        id INTEGER PRIMARY KEY AUTOINCREMENT, settlement_id INTEGER NOT NULL,
        input_res INTEGER, output_res INTEGER, tech_req INTEGER,
        FOREIGN KEY(settlement_id) REFERENCES settlements(id)
    )""")
    # Static production model for farms
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS farms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hex_id INTEGER UNIQUE,
        settlement_id INTEGER,
        species_name TEXT,
        output_rate REAL DEFAULT 1.0,
        maintenance_cost REAL DEFAULT 5.0,
        level INTEGER DEFAULT 1,
        FOREIGN KEY(hex_id) REFERENCES micro_hexes(id),
        FOREIGN KEY(settlement_id) REFERENCES settlements(id)
    )""")
    # Global Event Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tick INTEGER,
        category TEXT,
        message TEXT
    )""")
    # Paragon/Motivation Profiles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS paragon_profiles (
        settlement_id INTEGER PRIMARY KEY,
        stats_json TEXT,
        archetype TEXT,
        motivation TEXT,
        FOREIGN KEY(settlement_id) REFERENCES settlements(id)
    )""")
    # Underworld Infrastructure
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS criminal_hideouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hex_id INTEGER UNIQUE,
        type TEXT,
        wealth REAL DEFAULT 0.0,
        food_stockpile REAL DEFAULT 0.0,
        is_hidden INTEGER DEFAULT 1
    )""")
    # Add cluster management
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clusters (
        cluster_id INTEGER PRIMARY KEY,
        is_active INTEGER DEFAULT 0,
        wealth_summary REAL DEFAULT 0.0
    )""")
    conn.commit()
    return conn

def init_fractal_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS clusters (
        cluster_id INTEGER PRIMARY KEY,
        is_active INTEGER DEFAULT 0,
        wealth_summary REAL DEFAULT 0.0)""")
    
    try:
        cursor.execute("ALTER TABLE micro_hexes ADD COLUMN cluster_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    cursor.execute("UPDATE micro_hexes SET cluster_id = (q/10) + ((r/10) * 10)")
    # Seed clusters table
    cursor.execute("INSERT OR IGNORE INTO clusters (cluster_id, is_active) SELECT DISTINCT cluster_id, 0 FROM micro_hexes")
    conn.commit()
    conn.close()

def apply_hydrology(world_grid, map_size):
    print("Pass 2.5: Hydrology (Rivers, Lakes, Marshes)...")
    
    flow_map = {pos: 0 for pos in world_grid}
    
    # 1. Determine Flow Direction (Find the lowest neighbor)
    for q in range(map_size):
        for r in range(map_size):
            cell = world_grid[(q, r)]
            # Find neighbor with lowest elevation
            neighbors = [((q+1)%map_size, r), ((q-1)%map_size, r),
                         (q, (r+1)%map_size), (q, (r-1)%map_size),
                         ((q+1)%map_size, (r-1)%map_size), ((q-1)%map_size, (r+1)%map_size)]
            
            lowest_neighbor = None
            lowest_elev = cell["elevation"]
            
            for nq, nr in neighbors:
                if (nq, nr) in world_grid and world_grid[(nq, nr)]["elevation"] < lowest_elev:
                    lowest_elev = world_grid[(nq, nr)]["elevation"]
                    lowest_neighbor = (nq, nr)
            
            # If a lower neighbor exists, add flow to it
            if lowest_neighbor:
                flow_map[lowest_neighbor] += (cell["moisture"] * 5)
    
    # 2. Assign Hydrology based on accumulated flow
    for pos, flow in flow_map.items():
        cell = world_grid[pos]
        cell["env_q"] = 0
        if flow > 20: # It's a River/Lake
            cell["elevation"] = -0.1 # Forces it to look like water
            cell["moisture"] = 1.0   # Maximum hydration
            cell["env_q"] = 3
        elif flow > 5 and cell["elevation"] < 0.1:
            cell["biome_override"] = 4 # Converts Plains to Marsh
            cell["env_q"] = 2

def seed_planet(conn, map_size=100, config=None):
    if config is None:
        config = {"elevation_seed": 100, "temp_offset": 0.0, "moon_days": 28}
        
    elevation_seed = config.get("elevation_seed", 100)
    temp_offset = config.get("temp_offset", 0.0)
    
    cursor = conn.cursor()
    chaos_nodes = generate_d20_nodes()
    world_grid = {}

    conv_lon, conv_lat = 0.0, 0.0
    blast_radius = 0.15
    prison_radius = 0.08
    flow_width = 0.04

    # --- PASS 1: PHYSICAL BEDROCK ---
    print(f"Pass 1: Laying bedrock, temperature, and wind (seed={elevation_seed})...")
    for q in range(map_size):
        for r in range(map_size):
            lon = (q / map_size) * (2 * math.pi) - math.pi
            lat = (r / map_size) * math.pi - (math.pi / 2)

            elevation = pseudo_noise(lon, lat, seed=elevation_seed)

            if lat > 1.047:
                climate_band, wind_dir, base_temp = 0, -1, -0.9
            elif lat > 0.26:
                climate_band, wind_dir, base_temp = 1,  1,  0.0
            elif lat > -0.26:
                climate_band, wind_dir, base_temp = 2, -1,  0.9
            elif lat > -1.047:
                climate_band, wind_dir, base_temp = 3,  1,  0.0
            else:
                climate_band, wind_dir, base_temp = 4, -1, -0.9

            temp = base_temp + temp_offset + (pseudo_noise(lon, lat, seed=elevation_seed+200) * 0.3) - (max(0, elevation) * 0.5)
            temp = max(-1.0, min(1.0, temp))

            world_grid[(q, r)] = {
                "lon": lon, "lat": lat, "elevation": elevation,
                "temp": temp, "wind_dir": wind_dir, "climate_band": climate_band,
                "moisture": 0.0  # Will be filled by the moisture sweep
            }

    # --- PASS 2: THERMODYNAMIC MOISTURE SWEEP (Orographic Lift) ---
    print("Pass 2: Sweeping moisture via orographic lift physics...")
    for r in range(map_size):
        wind_dir = world_grid[(0, r)]["wind_dir"]
        q_order = range(map_size) if wind_dir == 1 else reversed(range(map_size))
        current_air_water = 0.0

        # Two sweeps so the globe wraps: first primes the air, second is accurate
        for _sweep in range(2):
            for q in q_order:
                cell = world_grid[(q, r)]

                if cell["elevation"] < 0:
                    # Ocean: sponge absorbs water. Warmer water = faster evaporation.
                    evaporation_rate = max(0.1, cell["temp"]) * 0.6
                    current_air_water = min(1.0, current_air_water + evaporation_rate)
                    cell["moisture"] = current_air_water
                else:
                    if cell["elevation"] > 0.6:
                        # Mountain: orographic lift dumps everything on the windward slope.
                        # The leeward side enters the rain shadow — bone dry.
                        cell["moisture"] = current_air_water
                        current_air_water *= 0.1  # 90% moisture lost over the peak
                    else:
                        # Normal land: steady precipitation as air slowly dries
                        cell["moisture"] = current_air_water
                        current_air_water *= 0.85  # 15% moisture lost per hex

    apply_hydrology(world_grid, map_size)

    # --- PASS 3: CHAOS MAPPING AND DATABASE INSERTION ---
    print("Pass 3: Mapping chaos nodes and writing to database...")
    micro_coords = []
    for (q, r), cell in world_grid.items():
        lon, lat = cell["lon"], cell["lat"]
        elevation = cell["elevation"]
        temp      = cell["temp"]
        moisture  = cell["moisture"]
        climate_band = cell["climate_band"]
        wind_dir     = cell["wind_dir"]
        env_q        = cell.get("env_q", 0)

        biome_id = calculate_base_biome(elevation, temp, moisture)
        if "biome_override" in cell:
            biome_id = cell["biome_override"]
            
        closest_overlay = 0
        latent_chaos = 0

        dist_to_conv = math.sqrt((lon - conv_lon)**2 + (lat - conv_lat)**2)

        if dist_to_conv < blast_radius:
            elevation -= 2.0
            biome_id, temp, latent_chaos = 11, 1.0, 13
        else:
            min_dist_to_node = float('inf')
            for node in chaos_nodes:
                n_lon, n_lat = node["lon"], node["lat"]
                dist = math.sqrt((lon - n_lon)**2 + (lat - n_lat)**2)

                if dist < min_dist_to_node:
                    min_dist_to_node = dist
                    latent_chaos = node["overlay_id"]

                if dist < prison_radius:
                    biome_id = 10
                    closest_overlay = node["overlay_id"]

                line_len_sq = n_lon**2 + n_lat**2
                if line_len_sq > 0:
                    t = max(0, min(1, (lon * n_lon + lat * n_lat) / line_len_sq))
                    proj_lon, proj_lat = t * n_lon, t * n_lat
                    if math.sqrt((lon - proj_lon)**2 + (lat - proj_lat)**2) < flow_width:
                        biome_id = 9

        state_int = pack_micro_hex(biome_id, 0, 0, 0, closest_overlay, 0, env_q)
        micro_coords.append((q, r, state_int, elevation, temp, moisture, climate_band, wind_dir, latent_chaos))

    cursor.executemany(
        "INSERT INTO micro_hexes (q, r, state_int, elevation, temperature, moisture, climate_band, wind_dir, latent_chaos) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        micro_coords
    )
    conn.commit()
    print(f"Successfully generated {len(micro_coords)} thermodynamic hexes.")

if __name__ == "__main__":
    conn = init_database()
    seed_planet(conn, map_size=100)
    conn.close()
