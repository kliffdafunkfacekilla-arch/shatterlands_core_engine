# engine.py
import sqlite3
import os
import heapq
import random
import math
import json
from core_engine.codec import pack_micro_hex, unpack_micro_hex, RESOURCE_STATS
from core_engine.db_setup import generate_d20_nodes

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")
MAP_SIZE = 100


class WeatherFront:
    """
    A self-sustaining energy packet floating in RAM.
    Never written to the database — the bedrock stays clean.
    """
    __slots__ = ['q', 'r', 'energy', 'moisture', 'vorticity']

    def __init__(self, q, r, energy, moisture, vorticity):
        self.q, self.r = q, r
        self.energy    = energy     # 0.0-1.0: heat content (drives hurricane formation)
        self.moisture  = moisture   # 0.0-1.0: rain potential
        self.vorticity = vorticity  # 0.0-1.0: Coriolis spin (drives tornado formation)

    @property
    def overlay_id(self) -> int:
        """Returns the current storm classification based on its physics state."""
        if self.vorticity > 0.8: return 16  # Tornado  — high spin, any energy
        if self.energy > 0.7:    return 17  # Hurricane — high heat, over ocean
        if self.moisture > 0.5:  return 13  # Thunderstorm — active precipitation
        return 0                             # Dissipating — clear skies

    @property
    def is_alive(self) -> bool:
        return self.energy > 0.05 or self.moisture > 0.1


class CelestialClock:
    __slots__ = ['tick', 'hours_in_day', 'days_in_month', 'months_in_year']

    def __init__(self, days_in_month=28):
        self.tick           = 0
        self.hours_in_day   = 24
        self.days_in_month  = days_in_month   # Cruorbus Moon cycle
        self.months_in_year = 12

    def advance(self): self.tick += 1

    @property
    def current_season(self) -> str:
        month = (self.tick // self.hours_in_day) // self.days_in_month
        if month in [11, 0, 1]: return "Winter"
        if month in [2, 3, 4]:  return "Spring"
        if month in [5, 6, 7]:  return "Summer"
        return "Autumn"

    @property
    def moon_phase(self) -> str:
        cycle_day = (self.tick // self.hours_in_day) % self.days_in_month
        if cycle_day == 14: return "Full Moon"
        if cycle_day == 0:  return "New Moon"
        if cycle_day < 14:  return "Waxing"
        return "Waning"

    @property
    def is_daylight(self) -> bool:
        return 6 <= (self.tick % self.hours_in_day) <= 18


class FractalEngine:
    __slots__ = ['clock', 'event_queue', 'db_path', 'active_weather']

    def __init__(self, db_path=DB_PATH, config=None):
        self.db_path        = db_path
        days_in_month       = config.get("moon_days", 28) if config else 28
        self.clock          = CelestialClock(days_in_month=days_in_month)
        self.event_queue    = []
        self.active_weather = []  # WeatherFront objects — RAM only

    def is_hex_in_chaos_flow(self, q, r, chaos_nodes):
        """Calculates if a hex is currently under a chaos flow based on the moon phase."""
        lunar_offset = (self.clock.tick // self.clock.hours_in_day) % self.clock.days_in_month
        drift = math.sin((lunar_offset / self.clock.days_in_month) * 2 * math.pi) * 0.05
        
        # Convert hex coordinates to spherical radians for accurate distance
        lon = (q / MAP_SIZE) * (2 * math.pi) - math.pi
        lat = (r / MAP_SIZE) * math.pi - (math.pi / 2)

        for node in chaos_nodes:
            n_lon, n_lat = node["lon"] + drift, node["lat"] + drift
            line_len_sq = n_lon**2 + n_lat**2
            if line_len_sq > 0:
                t = max(0, min(1, (lon * n_lon + lat * n_lat) / line_len_sq))
                proj_lon, proj_lat = t * n_lon, t * n_lat
                if math.sqrt((lon - proj_lon)**2 + (lat - proj_lat)**2) < 0.04: # flow_width
                    return True
        return False

    def trigger_tick(self):
        self.run_global_thermodynamics()
        
        conn = sqlite3.connect(self.db_path)
        active_clusters = conn.execute("SELECT cluster_id FROM clusters WHERE is_active=1").fetchall()
        
        for (c_id,) in active_clusters:
            self.process_cluster_fidelity(c_id, conn)
            
        conn.commit()
        conn.close()
        
        return {
            "tick":          self.clock.tick,
            "season":        self.clock.current_season,
            "moon_phase":    self.clock.moon_phase,
            "active_storms": len(self.active_weather),
            "processed_clusters": len(active_clusters)
        }

    def run_global_thermodynamics(self):
        # 1. Advance the Celestial Clock
        self.clock.advance()
        
        # 2. Process priority queue events (Actors, Caravans, Battles)
        while self.event_queue and self.event_queue[0][0] <= self.clock.tick:
            heapq.heappop(self.event_queue)
        
        # 3. Generate and Move Weather globally
        self.manage_weather()
        
    def process_cluster_fidelity(self, cluster_id, conn):
        self.process_ecology(cluster_id, conn)
        self.process_farm_production(cluster_id, conn)
        self.process_underworld(cluster_id, conn)
        self.process_metabolic_loop(cluster_id, conn)
        self.process_society(cluster_id, conn)

    def manage_weather(self):
        """
        Thermodynamic weather engine.
        Storms are energy packets that spawn, drift on the wind, gain
        vorticity from temperature gradients, and decay until dead.
        """
        conn   = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ── SPAWN ─────────────────────────────────────────────────────────
        # Hurricanes need hot, wet ocean hexes — equatorial band is the engine
        if random.random() < 0.1:
            cursor.execute(
                "SELECT q, r FROM micro_hexes "
                "WHERE temperature > 0.7 AND moisture > 0.6 "
                "ORDER BY RANDOM() LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                self.active_weather.append(
                    WeatherFront(row[0], row[1], energy=0.8, moisture=0.9, vorticity=0.1)
                )

        # ── MOVE & EVOLVE ──────────────────────────────────────────────────
        for storm in self.active_weather:

            # Sample the N and S neighbors to get the pressure gradient
            # Fixed: OR logic instead of tuple IN (SQLite doesn't support row-value syntax)
            r_north = (storm.r + 1) % MAP_SIZE
            r_south = (storm.r - 1) % MAP_SIZE
            cursor.execute(
                "SELECT AVG(temperature) FROM micro_hexes "
                "WHERE (q=? AND r=?) OR (q=? AND r=?)",
                (storm.q, r_north, storm.q, r_south)
            )
            avg_neighbor_temp = cursor.fetchone()[0] or 0.0

            # Cold air nearby = low pressure = storm accelerates and deepens
            if avg_neighbor_temp < 0:
                storm.energy    += 0.05
                storm.vorticity += 0.03  # Wind shear at the polar front spins up tornadoes

            # Natural vorticity growth from Coriolis effect
            storm.vorticity = min(1.0, storm.vorticity + 0.01)

            # Drift on the global wind current
            cursor.execute("SELECT value FROM metadata WHERE key='wind_dir'")
            wind_row = cursor.fetchone()
            if wind_row:
                global_wind_deg = float(wind_row[0])
                wind_dir = -1 if global_wind_deg > 180 else 1
            else:
                wind_dir = 1 # Default East

            cursor.execute(
                "SELECT elevation, temperature FROM micro_hexes WHERE q=? AND r=?",
                (storm.q, storm.r)
            )
            hex_data = cursor.fetchone()
            if hex_data:
                elevation, surface_temp = hex_data

                # Land drains energy (friction); ocean sustains it (evaporation feeds it)
                if elevation >= 0:
                    storm.energy   -= 0.04   # Land friction dissipates heat
                    storm.moisture -= 0.06   # Dumps rain on landfall
                else:
                    storm.energy   += 0.02 * max(0, surface_temp)  # Warm ocean recharges
                    storm.moisture  = min(1.0, storm.moisture + 0.03)

                # Advance the storm one hex in the wind direction, wrapping the globe
                storm.q = (storm.q + wind_dir) % MAP_SIZE

            # General energy decay each tick (radiative cooling)
            storm.energy    -= 0.02
            storm.moisture  -= 0.01
            storm.vorticity -= 0.01  # Spin decays without forcing

            # Clamp all values
            storm.energy    = max(0.0, min(1.0, storm.energy))
            storm.moisture  = max(0.0, min(1.0, storm.moisture))
            storm.vorticity = max(0.0, min(1.0, storm.vorticity))

        # ── CULL DEAD STORMS ───────────────────────────────────────────────
        self.active_weather = [s for s in self.active_weather if s.is_alive]

        conn.close()

    def process_ecology(self, cluster_id, conn):
        """
        Applies the combined effect of floating weather and dormant ley-lines
        to the world's resources and development level, restricted to cluster_id.
        """
        cursor = conn.cursor()
        
        # Load settlements and their locations
        cursor.execute("""
            SELECT s.id, s.hex_id, s.has_structure, m.q, m.r 
            FROM settlements s
            JOIN micro_hexes m ON s.hex_id = m.id
            WHERE m.cluster_id = ?
        """, (cluster_id,))
        active_settlements = cursor.fetchall()
        
        cursor.execute("SELECT id, q, r, state_int FROM micro_hexes WHERE cluster_id=?", (cluster_id,))
        rows   = cursor.fetchall()
        season = self.clock.current_season
        chaos_nodes = generate_d20_nodes()
        
        # Calculate Chaos Intensity based on the moon
        # 0.5 at New Moon, 1.5 at Full Moon
        lunar_offset = (self.clock.tick // self.clock.hours_in_day) % self.clock.days_in_month
        chaos_intensity = 0.5 + (math.sin((lunar_offset / self.clock.days_in_month) * math.pi))

        # O(1) lookup: which hex has a storm floating over it right now?
        weather_map = {(w.q, w.r): w.overlay_id for w in self.active_weather}

        updates = []
        for hex_id, q, r, state_int in rows:
            attrs  = unpack_micro_hex(state_int)
            b_id   = attrs["biome_id"]
            d_lvl  = attrs["dev_level"]
            res_id = attrs["resource_id"]
            spark  = 1 if attrs["spark"] else 0

            # Default: dormant ley-line. Override: active storm if one is present.
            active_overlay = weather_map.get((q, r), attrs["overlay_id"])

            if b_id not in [10, 11]:  # Skip Prisons and the Convergence

                # ── CHAOS / WEATHER EFFECTS ───────────────────────────────
                if self.is_hex_in_chaos_flow(q, r, chaos_nodes):
                    # The chaos effect now scales with the moon!
                    if active_overlay == 4 and random.random() < (0.05 * chaos_intensity):
                        res_id = random.randint(1, 12)      # Flux: mutates resources
                else:
                    if active_overlay == 4 and random.random() < 0.05:
                        res_id = random.randint(1, 12)      # Flux: mutates resources
                
                if active_overlay == 1 and d_lvl > 0 and random.random() < 0.1:
                    d_lvl -= 1                           # Mass: collapses structures
                elif active_overlay == 6 and random.random() < 0.02:
                    spark = 1                            # Nexus: ignites arcane spark
                elif active_overlay == 12 and res_id == 14:
                    res_id = 0                           # Virantor: burns flora

                # ── EXTRACTION & ECOLOGY (RESOURCE TRIANGLE) ───────────────────────────────
                is_extracted = False
                is_structure_extraction = False
                gathering_s_id = None
                
                for s_id, s_hex_id, has_struct, sq, sr in active_settlements:
                    dist = max(abs(q - sq), abs(q + r - sq - sr), abs(r - sr))
                    if dist == 0 and has_struct:
                        is_structure_extraction = True
                        is_extracted = True
                        gathering_s_id = s_id
                        break
                    elif dist <= 1 and not is_structure_extraction:
                        if res_id in [14, 15]: # Base resources can be gathered manually in range
                            is_extracted = True
                            gathering_s_id = s_id
                            
                if is_extracted and res_id > 0:
                    stats = RESOURCE_STATS.get(res_id, {"food": 0, "cost": 99, "renew": False})
                    
                    if is_structure_extraction:
                        yield_mult = 3.0
                        depletion_rate = 0.5
                    else:
                        yield_mult = 1.0
                        depletion_rate = 0.1
                        
                    harvest_yield = stats.get("food", 0) * yield_mult
                    wealth_yield = 1.0 * yield_mult if stats.get("food", 0) == 0 else 0.0
                    
                    cursor.execute("UPDATE settlements SET food_stockpile = food_stockpile + ?, wealth = wealth + ? WHERE id = ?",
                                   (harvest_yield, wealth_yield, gathering_s_id))
                                   
                    # Depletion
                    if random.random() < depletion_rate:
                        res_id = 0
                        
                    # Erosion for structures
                    if is_structure_extraction and 1 <= res_id <= 13:
                        cursor.execute("UPDATE micro_hexes SET elevation = elevation - 0.01 WHERE id = ?", (hex_id,))

                # ── DYNAMIC WEATHER EFFECTS ───────────────────────────────
                # Thunderstorm / Nutrient Upwelling: explosive growth in wet biomes
                if active_overlay == 13 and res_id == 0 and b_id in [0, 1, 2] and random.random() < 0.2:
                    res_id = 14
                # Blizzard / Brine Freeze: kills flora
                elif active_overlay == 14 and res_id == 14 and random.random() < 0.08:
                    res_id = 0
                # Heatwave / Thermal Current: scorches surface resources
                elif active_overlay == 15 and res_id in [14, 15] and random.random() < 0.05:
                    res_id = 0

                # Tornado: devastates development and tears out resources
                if active_overlay == 16:
                    if d_lvl > 0 and random.random() < 0.3:
                        d_lvl -= 1
                    if res_id in [14, 15] and random.random() < 0.4:
                        res_id = 0

                # Hurricane: massive flood-growth on coastal biomes, wipes development
                if active_overlay == 17:
                    if res_id == 0 and b_id in [0, 1, 3, 4] and random.random() < 0.35:
                        res_id = 15  # Surge of fauna/flora on the coasts
                    if d_lvl > 0 and random.random() < 0.2:
                        d_lvl -= 1  # Floods damage infrastructure

                # ── SEASONAL ECOLOGY CYCLE ────────────────────────────────
                if season == "Winter" and res_id == 14 and random.random() < 0.05:
                    res_id = 0
                if season == "Spring" and res_id == 0 and b_id in [1, 2] and random.random() < 0.05:
                    res_id = 14

                if res_id == 13 and d_lvl > 2 and random.random() < 0.05:
                    res_id = 14
                elif res_id == 14 and d_lvl < 2 and random.random() < 0.05:
                    res_id = 15
                elif res_id == 15 and d_lvl > 3 and random.random() < 0.1:
                    res_id = 0

            # CRITICAL: preserve attrs["overlay_id"] (the ley-line) in state_int.
            # active_overlay may be a transient storm — it must NOT be written to DB.
            new_state = pack_micro_hex(
                b_id, attrs["faction_id"], res_id, d_lvl, attrs["overlay_id"], spark
            )

            if new_state != state_int:
                updates.append((new_state, hex_id))

        if updates:
            cursor.executemany("UPDATE micro_hexes SET state_int=? WHERE id=?", updates)

    def log_event(self, category, message, conn=None):
        close_conn = False
        if not conn:
            conn = sqlite3.connect(self.db_path)
            close_conn = True
        cursor = conn.cursor()
        cursor.execute("INSERT INTO event_log (tick, category, message) VALUES (?, ?, ?)", 
                       (self.clock.tick, category, message))
        if close_conn:
            conn.commit()
            conn.close()

    def process_metabolic_loop(self, cluster_id, conn):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.population, s.food_stockpile 
            FROM settlements s
            JOIN micro_hexes m ON s.hex_id = m.id
            WHERE m.cluster_id=?
        """, (cluster_id,))
        for s_id, pop, food in cursor.fetchall():
            # Consumption logic
            consumption = pop * 0.05
            new_food = max(0, food - consumption)
            
            # Growth or Starvation
            new_pop = int(pop * 1.001) if new_food > consumption else int(pop * 0.95)
            
            if new_pop < pop:
                self.log_event("Disaster", f"Settlement {s_id} experienced starvation! Pop dropped to {new_pop}", conn)
            
            cursor.execute("UPDATE settlements SET population=?, food_stockpile=? WHERE id=?", 
                           (new_pop, new_food, s_id))

    def spawn_bandit(self, hex_id):
        # Placeholder for spawning a bandit agent
        print(f"Bandit spawned at hex {hex_id} due to low security!")

    def process_farm_production(self, cluster_id, conn):
        cursor = conn.cursor()
        
        # Get all active farms
        cursor.execute("""
            SELECT f.hex_id, f.settlement_id, f.species_name, f.output_rate, f.maintenance_cost 
            FROM farms f
            JOIN micro_hexes m ON f.hex_id = m.id
            WHERE m.cluster_id=?
        """, (cluster_id,))
        farms = cursor.fetchall()
        for hex_id, s_id, species, output_rate, maintenance_cost in farms:
            cursor.execute("SELECT wealth FROM settlements WHERE id=?", (s_id,))
            row = cursor.fetchone()
            if row:
                wealth = row[0]
                if wealth >= maintenance_cost:
                    cursor.execute("UPDATE settlements SET wealth = wealth - ?, food_stockpile = food_stockpile + ? WHERE id=?", 
                                   (maintenance_cost, output_rate, s_id))
                else:
                    self.log_event("Economy", f"Farm Level {output_rate} failed due to lack of wealth in Settlement {s_id}.", conn)

    def process_underworld(self, cluster_id, conn):
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT h.id, h.hex_id, h.type, h.wealth, h.food_stockpile, h.is_hidden 
            FROM criminal_hideouts h
            JOIN micro_hexes m ON h.hex_id = m.id
            WHERE m.cluster_id=?
        """, (cluster_id,))
        hideouts = cursor.fetchall()
        
        for h_id, h_hex_id, h_type, h_wealth, h_food, is_hidden in hideouts:
            cursor.execute("""
                SELECT s.id, s.security_points, s.happiness, p.archetype
                FROM settlements s
                LEFT JOIN paragon_profiles p ON s.id = p.settlement_id
                WHERE s.hex_id = ?
            """, (h_hex_id,))
            local_s = cursor.fetchone()
            
            purged = False
            if local_s:
                s_id, sec, happy, archetype = local_s
                if archetype in ["Infiltrator", "Hoarder"]:
                    cursor.execute("UPDATE settlements SET wealth = wealth + 5 WHERE id=?", (s_id,))
                    cursor.execute("UPDATE criminal_hideouts SET is_hidden = 1 WHERE id=?", (h_id,))
                    if random.random() < 0.1: # Only log occasionally to avoid spam
                        self.log_event("Society", f"Paragon in Settlement {s_id} took a cut from a local {h_type}.", conn)
                elif archetype in ["Savior", "Tyrant"] and sec > 50:
                    cursor.execute("DELETE FROM criminal_hideouts WHERE id=?", (h_id,))
                    cursor.execute("UPDATE micro_hexes SET latent_chaos = max(0, latent_chaos - 1) WHERE id=?", (h_hex_id,))
                    self.log_event("Society", f"Police Raid in Settlement {s_id} destroyed a {h_type}!", conn)
                    purged = True
                    
            if purged:
                continue
                
            if h_type == "DealerDen":
                if local_s:
                    cursor.execute("UPDATE settlements SET population = max(0, population - 5), happiness = happiness + 0.1 WHERE hex_id=?", (h_hex_id,))
                cursor.execute("UPDATE micro_hexes SET latent_chaos = latent_chaos + 1 WHERE id=?", (h_hex_id,))
                
            elif h_type == "SmugglerHideout":
                cursor.execute("UPDATE criminal_hideouts SET wealth = wealth + 5 WHERE id=?", (h_id,))
                
            elif h_type == "PiratePort":
                if local_s:
                    cursor.execute("UPDATE settlements SET food_stockpile = max(0, food_stockpile - 10) WHERE hex_id=?", (h_hex_id,))
                    cursor.execute("UPDATE criminal_hideouts SET food_stockpile = food_stockpile + 10 WHERE id=?", (h_id,))
                else:
                    cursor.execute("UPDATE criminal_hideouts SET food_stockpile = food_stockpile + 5 WHERE id=?", (h_id,)) # Foraging
                
                # Consume
                if h_food < 5:
                    cursor.execute("DELETE FROM criminal_hideouts WHERE id=?", (h_id,))
                    self.log_event("Disaster", f"A Pirate Port at hex {h_hex_id} starved and collapsed.", conn)
                else:
                    cursor.execute("UPDATE criminal_hideouts SET food_stockpile = food_stockpile - 5 WHERE id=?", (h_id,))

    def spawn_paragon(self, s_id, hex_id):
        stats = {s: random.randint(2, 10) for s in ["might", "endurance", "finesse", "reflex", 
                 "vitality", "fortitude", "knowledge", "logic", "awareness", "instinct", 
                 "charm", "willpower"]}
        
        archetypes = ["Savior", "Tyrant", "Hoarder", "Infiltrator", "Madman"]
        archetype = random.choice(archetypes)
        
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT OR IGNORE INTO paragon_profiles (settlement_id, stats_json, archetype, motivation) VALUES (?, ?, ?, ?)", 
                     (s_id, json.dumps(stats), archetype, "Goal Placeholder"))
        conn.commit()
        conn.close()

    def get_ai_priority(self, s_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT stats_json, archetype FROM paragon_profiles WHERE settlement_id=?", (s_id,))
        data = cursor.fetchone()
        conn.close()
        
        if not data: return None
            
        stats = json.loads(data[0])
        archetype = data[1]
        
        weights = {
            "Barracks": stats['might'] + stats['fortitude'],
            "Farms":    stats['instinct'] + stats['vitality'],
            "Academy":  stats['knowledge'] + stats['logic'],
            "TradeHub": stats['logic'] + stats['finesse']
        }
        
        if archetype == "Tyrant": weights["Barracks"] += 5
        elif archetype == "Savior": weights["Farms"] += 5
        elif archetype == "Hoarder": weights["TradeHub"] += 5
            
        return max(weights, key=weights.get)

    def process_society(self, cluster_id, conn):
        cursor = conn.cursor()
        
        # 1. Workforce Logic: 100 pop = 1 Unit
        # Base settlement (100 pop) is 1 unit. Each hex controlled adds 1 unit requirement.
        cursor.execute("""
            SELECT s.id, s.hex_id, s.population, s.food_stockpile, s.wealth, s.tech_level, s.security_points, s.happiness 
            FROM settlements s
            JOIN micro_hexes m ON s.hex_id = m.id
            WHERE m.cluster_id=?
        """, (cluster_id,))
        for s in cursor.fetchall():
            s_id, hex_id, pop, food, wealth, tech, sec, happy = s
            workforce = pop // 100
            
            # 2. Happiness/Crime Loop
            crime_potential = (wealth * 0.01) - (sec * 0.5)
            if crime_potential > happy:
                self.spawn_bandit(hex_id)
                self.log_event("Society", f"Faction spawned Bandits near Hex {hex_id} due to low security.", conn)
                happy -= 0.1
                
            # 3. Production Efficiency
            # If tech_level > 1, apply multipliers to resource gathering
            if tech > 1:
                wealth += (workforce * tech) * 0.5
                
            # 4. Automated AI Construction
            if wealth >= 100:
                best_building = self.get_ai_priority(s_id)
                if best_building:
                    cursor.execute("INSERT INTO buildings (settlement_id, type) VALUES (?, ?)", (s_id, best_building))
                    wealth -= 100
                    if best_building == "Barracks": sec += 10
                    elif best_building == "Theatre": happy += 0.2
                    elif best_building == "Academy": tech += 1
                    self.log_event("Society", f"Settlement {s_id} constructed a {best_building} driven by its Paragon.", conn)
                
            cursor.execute("UPDATE settlements SET happiness=?, wealth=?, security_points=?, tech_level=? WHERE id=?", 
                           (max(0.0, happy), wealth, sec, tech, s_id))
