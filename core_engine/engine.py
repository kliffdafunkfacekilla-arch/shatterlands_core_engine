import sqlite3
import random
import os
import json
import math
from core_engine.codec import unpack_micro_cluster, pack_micro_cluster
from core_engine.fractal_core import process_cluster_fidelity

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

def unpack_ecology(pack_val):
    p1 = pack_val & 0xFF
    p2 = (pack_val >> 8) & 0xFF
    p3 = (pack_val >> 16) & 0xFF
    res = (pack_val >> 24) & 0xFFFF
    return p1, p2, p3, res

def pack_ecology(p1, p2, p3, res):
    p1 = max(0, min(255, int(p1)))
    p2 = max(0, min(255, int(p2)))
    p3 = max(0, min(255, int(p3)))
    res = max(0, min(65535, int(res)))
    return p1 | (p2 << 8) | (p3 << 16) | (res << 24)

def get_calendar_info(tick):
    total_days = tick
    year = 1650 + (total_days // 539)
    day_of_year = (total_days % 539) + 1

    months = [("Nexar", 35), ("Massis", 28), ("Motom", 21), ("Fluxen", 42), ("Vitan", 49), ("Lexis", 28), ("Ration", 28), ("Ordis", 28), ("Luxen", 49), ("Omin", 63), ("Aurum", 35), ("Anum", 42), ("Maelen", 84), ("Shadowfall", 7)]
    current_month = ""
    day_of_month = day_of_year
    for m_name, m_days in months:
        if day_of_month <= m_days:
            current_month = m_name
            break
        day_of_month -= m_days

    seasons = [("Shadowburn", 84), ("Dryspell", 42), ("Frostin", 49), ("GreenSpan", 84), ("Highreach", 112), ("Spurium", 77), ("Dimfreeze", 84), ("Shadowfall", 7)]
    current_season = ""
    day_in_season = day_of_year
    for s_name, s_days in seasons:
        if day_in_season <= s_days:
            current_season = s_name
            break
        day_in_season -= s_days

    return year, current_month, day_of_month, current_season

def spend_modular_cost(inventory, group, amount):
    if group not in inventory: return False, {}
    total_available = sum(inventory[group].values())
    if total_available < amount: return False, {}

    used = {}
    remaining = amount
    for res_name, res_amount in list(inventory[group].items()):
        if remaining <= 0: break
        take = min(res_amount, remaining)
        inventory[group][res_name] -= take
        remaining -= take
        used[res_name] = take
    return True, used

def get_total(inventory, group):
    if group not in inventory: return 0
    return sum(inventory[group].values())

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

def wrap_hex(q, r, L=25):
    # D20 teleportation logic (Red Blob Games Idea 3)
    triangles = {}
    for i in range(5):
        triangles[i*4] = ('UP', (i+1)*L + i, -L)
        triangles[i*4 + 1] = ('DN', i*L + i + 1, L-1)
        triangles[i*4 + 2] = ('UP', i*L + i + 1 + L, 0)
        triangles[i*4 + 3] = ('DN', i*L + i + 1, 2*L - 1)

    connections = {}
    for i in range(5):
        t_top, t_mid_dn, t_mid_up, t_bot_dn = i*4, i*4+1, i*4+2, i*4+3
        connections[(t_top, 'B')] = (t_mid_dn, 'T')
        connections[(t_mid_dn, 'T')] = (t_top, 'B')
        connections[(t_mid_dn, 'R')] = (t_mid_up, 'L')
        connections[(t_mid_up, 'L')] = (t_mid_dn, 'R')
        connections[(t_mid_up, 'B')] = (t_bot_dn, 'T')
        connections[(t_bot_dn, 'T')] = (t_mid_up, 'B')

        prev_up = ((i-1)%5)*4+2
        connections[(t_mid_dn, 'L')] = (prev_up, 'R')
        connections[(prev_up, 'R')] = (t_mid_dn, 'L')

        prev_top, next_top = ((i-1)%5)*4, ((i+1)%5)*4
        connections[(t_top, 'L')] = (prev_top, 'R')
        connections[(t_top, 'R')] = (next_top, 'L')

        prev_bot, next_bot = ((i-1)%5)*4+3, ((i+1)%5)*4+3
        connections[(t_bot_dn, 'L')] = (prev_bot, 'R')
        connections[(t_bot_dn, 'R')] = (next_bot, 'L')

    best_t = -1
    best_dist = 999999
    best_b = None
    for t_id, (t_type, q0, r0) in triangles.items():
        if t_type == 'UP':
            b0, b1, b2 = r0 + L - 1 - r, q + r - (q0 + r0), q0 - q
        else:
            b0, b1, b2 = r - (r0 - L + 1), q - q0, q0 + r0 - (q + r)

        dist = 0
        if b0 < 0: dist -= b0
        if b1 < 0: dist -= b1
        if b2 < 0: dist -= b2
        if dist == 0: return q, r # Inside valid triangle

        if dist < best_dist:
            best_dist, best_t, best_b = dist, t_id, (b0, b1, b2)

    if best_dist > 5: return q, r # Too far out, let it fail

    t_type = triangles[best_t][0]
    b0, b1, b2 = best_b
    edge = 'B' if t_type == 'UP' and b0 < 0 else 'T' if t_type == 'DN' and b0 < 0 else 'L' if b1 < 0 else 'R'

    conn = connections.get((best_t, edge))
    if not conn: return q, r
    nt_id, n_edge = conn
    nt_type, nq0, nr0 = triangles[nt_id]

    nb0, nb1, nb2 = b0, b1, b2
    if edge in ['L', 'R'] and n_edge in ['L', 'R']:
        nb0, nb1, nb2 = b0, b2, b1

    if nt_type == 'UP':
        return nq0 - nb2, nr0 + L - 1 - nb0
    else:
        return nq0 + nb1, nr0 - L + 1 + nb0

def step_towards(q, r, t_q, t_r):
    if q == t_q and r == t_r: return (q, r)
    best = (q, r)
    min_dist = abs(q - t_q) + abs(r - t_r) + abs(-q-r - (-t_q-t_r))
    for nq, nr in get_neighbors(q, r):
        dist = abs(nq - t_q) + abs(nr - t_r) + abs(-nq-nr - (-t_q-t_r))
        if dist < min_dist:
            min_dist = dist
            best = (nq, nr)
    return best

class GlobalEngine:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.tick = 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key='current_tick'")
        row = cursor.fetchone()
        if row: self.tick = int(row[0])
        else:
            cursor.execute("INSERT INTO metadata (key, value) VALUES ('current_tick', '0')")
            conn.commit()

        cursor.execute("SELECT value FROM metadata WHERE key='cartel_inventory'")
        c_row = cursor.fetchone()
        if c_row:
            self.cartel_inventory = json.loads(c_row[0])
        else:
            self.cartel_inventory = {"Raw": {}, "BlackMarket": {}}
            cursor.execute("INSERT INTO metadata (key, value) VALUES ('cartel_inventory', ?)", (json.dumps(self.cartel_inventory),))
            conn.commit()

        self.year, self.month, self.day, self.season = get_calendar_info(self.tick)
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('current_year', ?)", (str(self.year),))
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('current_month', ?)", (self.month,))
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('current_day', ?)", (str(self.day),))
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('current_season', ?)", (self.season,))
        conn.commit()
        conn.close()

    def save_metadata(self, conn):
        conn.execute("UPDATE metadata SET value=? WHERE key='current_tick'", (str(self.tick),))
        conn.execute("UPDATE metadata SET value=? WHERE key='cartel_inventory'", (json.dumps(self.cartel_inventory),))
        conn.execute("UPDATE metadata SET value=? WHERE key='current_year'", (str(self.year),))
        conn.execute("UPDATE metadata SET value=? WHERE key='current_month'", (self.month,))
        conn.execute("UPDATE metadata SET value=? WHERE key='current_day'", (str(self.day),))
        conn.execute("UPDATE metadata SET value=? WHERE key='current_season'", (self.season,))

    def log_event(self, category, msg, conn, q=None, r=None):
        cursor = conn.cursor()
        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (self.tick, category, msg, q, r))

    def process_diplomacy(self, cursor, conn, settlements):
        cursor.execute("SELECT id, name, special_rule FROM factions")
        factions = {row[0]: row for row in cursor.fetchall()}

        f_ids = list(factions.keys())
        if len(f_ids) < 2:
            return

        # Seed faction_relations with neutral trust if not already present
        for i in range(len(f_ids)):
            for j in range(i + 1, len(f_ids)):
                fa, fb = f_ids[i], f_ids[j]
                cursor.execute(
                    "INSERT OR IGNORE INTO faction_relations (faction_a_id, faction_b_id, status, trust_level) VALUES (?,?,'Neutral',0)",
                    (fa, fb)
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO faction_relations (faction_a_id, faction_b_id, status, trust_level) VALUES (?,?,'Neutral',0)",
                    (fb, fa)
                )

        # Seed settlement-level diplomacy relations if none exist
        existing = cursor.execute("SELECT COUNT(*) FROM diplomacy_relations").fetchone()[0]
        if existing == 0:
            settlement_list = [(s[0], s[1]) for s in settlements]
            if len(settlement_list) >= 2:
                pairs_added = 0
                attempts = 0
                while pairs_added < min(6, len(settlement_list)) and attempts < 30:
                    attempts += 1
                    a, b = random.sample(settlement_list, 2)
                    if a[1] != b[1]:
                        cursor.execute(
                            "INSERT OR REPLACE INTO diplomacy_relations (settlement_a_id, settlement_b_id, score) VALUES (?,?,50)",
                            (a[0], b[0])
                        )
                        cursor.execute(
                            "INSERT OR REPLACE INTO diplomacy_relations (settlement_a_id, settlement_b_id, score) VALUES (?,?,50)",
                            (b[0], a[0])
                        )
                        pairs_added += 1

        # Process each unique faction pair exactly once per tick
        processed_pairs = set()
        for fa in f_ids:
            for fb in f_ids:
                if fa >= fb:
                    continue
                pair_key = (fa, fb)
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)

                ra = factions[fa][2]
                rb = factions[fb][2]

                # Cults don't do diplomacy
                if ra == "Cult" or rb == "Cult":
                    continue

                cursor.execute(
                    "SELECT trust_level, status FROM faction_relations WHERE faction_a_id=? AND faction_b_id=?",
                    (fa, fb)
                )
                row = cursor.fetchone()
                trust = row[0] if row else 0
                old_status = row[1] if row else 'Neutral'

                # Trait modifiers
                if ra == "Vaneer_Concord" or rb == "Vaneer_Concord":
                    trust += 2
                if ra == "Prism_Scale" or rb == "Prism_Scale":
                    trust += 5
                if ra == "Eastern_Hounds" or rb == "Eastern_Hounds":
                    trust = max(trust, 0)  # No grudges — reset negatives toward neutral

                # Small, slow trust drift each tick (±5 instead of ±15)
                trust += random.randint(-5, 5)
                trust = max(-100, min(100, trust))

                # Determine status from trust level
                if trust > 80:
                    status = 'Alliance'
                elif trust > 40:
                    status = 'Trading'
                elif trust < -50:
                    if (ra == "Vaneer_Concord" or rb == "Vaneer_Concord") and trust > -90:
                        status = 'Neutral'
                    else:
                        status = 'War'
                else:
                    status = 'Neutral'

                cursor.execute(
                    "INSERT OR REPLACE INTO faction_relations (faction_a_id, faction_b_id, status, trust_level) VALUES (?,?,?,?)",
                    (fa, fb, status, trust)
                )
                cursor.execute(
                    "INSERT OR REPLACE INTO faction_relations (faction_a_id, faction_b_id, status, trust_level) VALUES (?,?,?,?)",
                    (fb, fa, status, trust)
                )

                # Only log and act on status changes or meaningful events
                if status == 'War':
                    s1 = [s for s in settlements if s[1] == fa]
                    s2 = [s for s in settlements if s[1] == fb]
                    if s1 and s2:
                        s_a = random.choice(s1)
                        s_b = random.choice(s2)
                        cp_a = s_a[8]
                        cp_b = s_b[8]
                        if ra == "Ursine_Hegemony": cp_a *= 3.0
                        if rb == "Ursine_Hegemony": cp_b *= 3.0
                        if rb == "Guerrilla_Clans": cp_b += max(0, 100 - s_b[5]) * 2.0
                        if rb == "Scute_Confederacy": cp_b *= 2.0
                        if cp_a > cp_b * 1.5:
                            self.log_event("Diplomacy", f"{factions[fa][1]} conquered {s_b[3]} from {factions[fb][1]}! (trust:{trust})", conn)
                            cursor.execute("UPDATE settlements SET faction_id=?, security_points=security_points/2 WHERE id=?", (fa, s_b[0]))
                        else:
                            # Only log skirmish if status just changed to War, not every tick
                            if old_status != 'War':
                                self.log_event("Diplomacy", f"{factions[fa][1]} and {factions[fb][1]} entered conflict — skirmish near {s_b[3]}. (trust:{trust})", conn)
                            cursor.execute("UPDATE settlements SET security_points = max(0, security_points - 2) WHERE id=?", (s_a[0],))
                            cursor.execute("UPDATE settlements SET security_points = max(0, security_points - 2) WHERE id=?", (s_b[0],))

                elif status in ('Trading', 'Alliance'):
                    if old_status != status:
                        self.log_event("Diplomacy", f"{factions[fa][1]} and {factions[fb][1]} are now {status}. (trust:{trust})", conn)
                    s1 = [s for s in settlements if s[1] == fa]
                    s2 = [s for s in settlements if s[1] == fb]
                    if s1 and s2:
                        s_a = random.choice(s1)
                        s_b = random.choice(s2)
                        route_type = 'Land'
                        cursor.execute(
                            "INSERT INTO trade_routes (faction_id, settlement_a_id, settlement_b_id, route_type) VALUES (?,?,?,?)",
                            (fa, s_a[0], s_b[0], route_type)
                        )
                        if status == 'Alliance' and ra == "Fulcrum_Academy":
                            cursor.execute(
                                "UPDATE factions SET technology_level = max(technology_level, (SELECT technology_level FROM factions WHERE id=?)) WHERE id=?",
                                (fa, fb)
                            )

                elif status == 'Neutral' and old_status in ('War', 'Alliance', 'Trading'):
                    self.log_event("Diplomacy", f"{factions[fa][1]} and {factions[fb][1]} returned to Neutral. (trust:{trust})", conn)

    def apply_chaos_event(self, domain, name, pop, sec, inventory, q, r, p_geo, cursor, conn):
        local_farm = 1.0
        local_consume = 1.0
        is_effect_a = random.random() < 0.5

        if domain == "Mass":
            if is_effect_a: # Crushing
                inventory.setdefault("Building", {})["Wood"] = 0
                self.log_event("Chaos", f"Mass crushed {name}! Wood destroyed.", conn, q, r)
            else: # Anti-Gravity
                float_pop = int(pop * 0.2)
                pop -= float_pop
                inventory.setdefault("Survival", {})["Base Food"] = 0
                self.log_event("Chaos", f"Anti-gravity in {name} flung {float_pop} people into the sky!", conn, q, r)

        elif domain == "Ordo":
            if is_effect_a: # Freezing
                local_farm = 0.0
                pop -= int(pop * 0.1)
                self.log_event("Chaos", f"Absolute zero struck {name}, freezing ecology and killing citizens.", conn, q, r)
            else: # Structuring
                inventory["Tags"] = inventory.get("Tags", []) + ["Rigid"]
                self.log_event("Chaos", f"Ordo structured {name}, removing brittle tags.", conn, q, r)

        elif domain == "Motus":
            if is_effect_a: # Sonic Boom
                inventory.setdefault("Building", {})["Stone"] = 0
                sec = max(0, sec - 20)
                self.log_event("Chaos", f"Sonic boom shattered stone and security in {name}!", conn, q, r)
            else: # Frictionless
                inventory["Building"] = {}
                self.log_event("Chaos", f"Resources in {name} slid away frictionlessly across the map!", conn, q, r)

        elif domain == "Flux":
            if is_effect_a: # Transmutation
                wood = inventory.get("Building", {}).get("Wood", 0)
                inventory.setdefault("Survival", {})["Base Food"] = inventory.get("Survival", {}).get("Base Food", 0) + wood
                inventory.setdefault("Building", {})["Wood"] = 0
                self.log_event("Chaos", f"Flux transmuted wood to food in {name}!", conn, q, r)
            else: # Terrain Shift
                neighbors = get_neighbors(q, r)
                swap_coord = random.choice(neighbors)
                cursor.execute("SELECT id, pack_geo FROM global_hexes WHERE q=? AND r=?", (swap_coord[0], swap_coord[1]))
                row = cursor.fetchone()
                if row:
                    n_id, n_geo = row
                    cursor.execute("UPDATE global_hexes SET pack_geo=? WHERE id=?", (p_geo, n_id))
                    cursor.execute("UPDATE global_hexes SET pack_geo=? WHERE q=? AND r=?", (n_geo, q, r))
                    p_geo = n_geo
                self.log_event("Chaos", f"Flux swapped the geography of {name} with a neighboring hex!", conn, q, r)

        elif domain == "Vita":
            if is_effect_a: # Fecundity
                local_farm *= 5.0
                pop -= int(pop * 0.1)
                self.log_event("Chaos", f"Hyper-evolution in {name} exploded crop yields but caused lethal cancers!", conn, q, r)
            else: # Toxic Overgrowth
                p_geo = 3 # Jungle/Swamp
                cursor.execute("UPDATE global_hexes SET pack_geo=?, pack_ecology=pack_ecology | 200 WHERE q=? AND r=?", (p_geo, q, r))
                self.log_event("Chaos", f"Toxic overgrowth permanently mutated {name} into a deadly jungle!", conn, q, r)

        elif domain == "Nexus":
            if is_effect_a: # Fire Storms
                inventory.setdefault("Building", {})["Wood"] = 0
                self.log_event("Chaos", f"Fire storms burned all the wood in {name}!", conn, q, r)
            else: # Violent Reactions
                if inventory.get("Reagents", {}).get("Oils", 0) > 0:
                    inventory["Reagents"]["Oils"] = 0
                    sec = max(0, sec - 50)
                    self.log_event("Chaos", f"Volatile oils exploded violently in {name}!", conn, q, r)

        elif domain == "Ratio":
            if is_effect_a: # Logic Break
                inventory["Tags"] = inventory.get("Tags", []) + ["Logic Broken"]
                self.log_event("Chaos", f"Logic broke in {name}, randomizing construction costs!", conn, q, r)
            else: # Logic Riots
                sec = max(0, sec - 30)
                self.log_event("Chaos", f"People logiced themselves into violence in {name}, triggering massive riots!", conn, q, r)

        elif domain == "Anumis":
            if is_effect_a: # Tag Inversion
                inventory["Tags"] = inventory.get("Tags", []) + ["Inverted Physics"]
                self.log_event("Chaos", f"Anumis inverted physical properties in {name}!", conn, q, r)
            else: # Whirlwind
                inventory.setdefault("Building", {})["Stone"] = 0
                inventory.setdefault("Survival", {})["Base Food"] = 0
                self.log_event("Chaos", f"An arcane whirlwind shredded resources in {name}!", conn, q, r)

        elif domain == "Lux":
            if is_effect_a: # Intense Light
                local_farm *= 0.5
                pop -= int(pop * 0.05)
                self.log_event("Chaos", f"Blinding light scorched {name}, causing sunburns and blindness!", conn, q, r)
            else: # Illusions
                sec = 0
                self.log_event("Chaos", f"Terrifying illusions tanked morale and security in {name}!", conn, q, r)

        elif domain == "Omen":
            if is_effect_a: # Fast Forward
                inventory.setdefault("Survival", {})["Base Food"] = inventory.get("Survival", {}).get("Base Food", 0) + (pop * 5)
                self.log_event("Chaos", f"Omen simulated ticks ahead for {name}, generating instant food!", conn, q, r)
            else: # Rot
                inventory.setdefault("Survival", {})["Base Food"] = 0
                pop -= int(pop * 0.1)
                self.log_event("Chaos", f"Temporal rot instantly decayed food and aged citizens in {name}!", conn, q, r)

        elif domain == "Aura":
            if is_effect_a: # Euphoria
                sec = 100
                local_farm = 0.0
                self.log_event("Chaos", f"Toxic euphoria paralyzed {name} in bliss. 0 production.", conn, q, r)
            else: # Hate Riots
                sec = 0
                pop -= int(pop * 0.2)
                self.log_event("Chaos", f"Bloody hate riots decimated {name}!", conn, q, r)

        elif domain == "Lex":
            if is_effect_a: # Stasis
                sec = 100
                local_farm = 0.0
                local_consume = 0.0
                self.log_event("Chaos", f"Lex locked {name} in an absolute void of stasis!", conn, q, r)
            else: # Holy War
                local_farm = 0.0
                pop -= int(pop * 0.1)
                self.log_event("Chaos", f"A violent theological war halted production in {name} with massive fatalities!", conn, q, r)

        return pop, sec, inventory, local_farm, local_consume, p_geo

    def process_global_chaos_flow(self, cursor):
        cursor.execute("SELECT id, pack_ecology, flow_target_id FROM global_hexes")
        all_hexes = cursor.fetchall()

        hex_dict = {h[0]: list(unpack_ecology(h[1])) for h in all_hexes}
        flow_targets = {h[0]: h[2] for h in all_hexes if h[2]}

        for h_id, target_id in flow_targets.items():
            if target_id in hex_dict:
                p1 = hex_dict[h_id][0]
                if p1 > 5:
                    flow_amt = int(p1 * 0.15)
                    hex_dict[h_id][0] -= flow_amt
                    hex_dict[target_id][0] = min(255, hex_dict[target_id][0] + flow_amt)

        for h_id, vals in hex_dict.items():
            p1, p2, p3, res = vals
            if self.season in ["Shadowburn", "Highreach"]:
                p1 = min(255, p1 + 1)
            elif self.season == "GreenSpan":
                p2 = min(255, p2 + 2)
            elif self.season == "Shadowfall":
                p1 = min(255, p1 + 5)
                p2 = max(0, p2 - 1)
            hex_dict[h_id] = (p1, p2, p3, res)

        cursor.executemany("UPDATE global_hexes SET pack_ecology=? WHERE id=?",
                           [(pack_ecology(*v), k) for k, v in hex_dict.items()])

    def is_hex_in_chaos_flow(self, q, r, chaos_nodes):
        """Calculates if a hex is currently under a chaos flow based on the moon phase."""
        lunar_offset = (self.tick // 24) % 28 # Assuming 24 hour ticks, 28 day moon cycle
        drift = math.sin((lunar_offset / 28.0) * 2 * math.pi) * 0.05

        lon = (q / 50.0) * (2 * math.pi) - math.pi
        lat = (r / 50.0) * math.pi - (math.pi / 2)

        for node in chaos_nodes:
            n_lon, n_lat = node["lon"] + drift, node["lat"] + drift
            line_len_sq = n_lon**2 + n_lat**2
            if line_len_sq > 0:
                t = max(0, min(1, (lon * n_lon + lat * n_lat) / line_len_sq))
                proj_lon, proj_lat = t * n_lon, t * n_lat
                if math.sqrt((lon - proj_lon)**2 + (lat - proj_lat)**2) < 0.04:
                    return True
        return False

    def manage_weather(self, cursor, conn):
        """
        Thermodynamic weather engine. Storms spawn, drift on the wind, gain
        vorticity from temp gradients, and decay.
        """
        # Spawning logic: Ocean + High Moisture -> Hurricane
        if random.random() < 0.2:
            cursor.execute("SELECT id, q, r FROM global_hexes WHERE (pack_geo & 15) >= 9 ORDER BY RANDOM() LIMIT 1")
            row = cursor.fetchone()
            if row:
                cursor.execute("INSERT INTO weather_systems (type, global_q, global_r, energy, moisture, vorticity) VALUES ('Hurricane', ?, ?, 0.8, 0.9, 0.1)", (row[1], row[2]))

        # Spawning logic: Land + High Temp difference -> Tornado
        if random.random() < 0.1:
            cursor.execute("SELECT id, q, r FROM global_hexes WHERE (pack_geo & 15) <= 4 ORDER BY RANDOM() LIMIT 1")
            row = cursor.fetchone()
            if row:
                cursor.execute("INSERT INTO weather_systems (type, global_q, global_r, energy, moisture, vorticity) VALUES ('Tornado', ?, ?, 0.5, 0.2, 0.8)", (row[1], row[2]))

        cursor.execute("SELECT id, type, global_q, global_r, energy, moisture, vorticity, is_chaos, chaos_domain FROM weather_systems")
        storms = cursor.fetchall()

        # Build chaos nodes (12 primal nodes)
        chaos_nodes = []
        for i in range(12):
            lat = math.asin(2 * random.random() - 1)
            lon = 2 * math.pi * random.random()
            chaos_nodes.append({"lon": lon, "lat": lat})

        domains = ["Mass", "Ordo", "Motus", "Flux", "Vita", "Nexus", "Ratio", "Anumis", "Lux", "Omen", "Aura", "Lex"]

        updates = []
        deletes = []

        for w_id, w_type, q, r, energy, moisture, vorticity, is_chaos, domain in storms:
            cursor.execute("SELECT wind_direction, pack_geo, chaos_domain FROM global_hexes WHERE q=? AND r=?", (q, r))
            hex_data = cursor.fetchone()
            if not hex_data:
                deletes.append((w_id,))
                continue

            wind, p_geo, h_domain = hex_data
            vecs = {'W': (-1, 0), 'E': (1, 0)}
            wq, wr = vecs.get(wind, (1, 0))

            # Drift on wind
            q, r = wrap_hex(q + wq, r + wr)

            # Decay
            energy -= 0.05
            moisture -= 0.02
            vorticity -= 0.01

            if energy <= 0 and moisture <= 0 and vorticity <= 0:
                deletes.append((w_id,))
            else:
                updates.append((w_type, q, r, energy, moisture, vorticity, is_chaos, domain, w_id))

        cursor.executemany("UPDATE weather_systems SET type=?, global_q=?, global_r=?, energy=?, moisture=?, vorticity=?, is_chaos=?, chaos_domain=? WHERE id=?", updates)
        cursor.executemany("DELETE FROM weather_systems WHERE id=?", deletes)

    def process_world_entities(self, cursor, conn):
        # 1. Chaos Flow Spawns (Chaos Creatures)
        chaos_nodes = []
        random.seed(12345)
        for i in range(12):
            lat = math.asin(2 * random.random() - 1)
            lon = 2 * math.pi * random.random()
            chaos_nodes.append({"lon": lon, "lat": lat})
        random.seed()

        cursor.execute("SELECT id, q, r FROM global_hexes ORDER BY RANDOM() LIMIT 20")
        for row in cursor.fetchall():
            if self.is_hex_in_chaos_flow(row[1], row[2], chaos_nodes):
                if random.random() < 0.2:
                    cursor.execute("INSERT INTO world_entities (type, global_hex_id, radius, duration) VALUES ('Chaos Creature', ?, 1, 20)", (row[0],))
                    self.log_event("Chaos", "A wild Chaos Creature spawned on a Chaos Path!", conn)

        # 2. Null Zealot Spawns
        cursor.execute("SELECT SUM(population) FROM settlements")
        global_pop = cursor.fetchone()[0] or 1000
        cursor.execute("SELECT COUNT(*) FROM world_entities WHERE type='Null Zealots'")
        num_nulls = cursor.fetchone()[0]
        if num_nulls < max(1, global_pop // 2000):
            cursor.execute("SELECT id FROM global_hexes ORDER BY RANDOM() LIMIT 1")
            g_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO world_entities (type, global_hex_id, radius, duration) VALUES ('Null Zealots', ?, 1, 50)", (g_id,))
            self.log_event("Mandate", "A crusade of Null Zealots has mobilized!", conn)

        cursor.execute("SELECT id, type, global_hex_id, radius, duration, alignment, micro_q, micro_r FROM world_entities")
        entities = cursor.fetchall()

        # Get Prisons for routing
        cursor.execute("SELECT q, r, chaos_domain FROM global_hexes WHERE chaos_domain IS NOT NULL")
        prison_coords = {row[2]: (row[0], row[1]) for row in cursor.fetchall()}

        vecs = {'W': (-1, 0), 'E': (1, 0)}
        alive_entities = []

        for e_id, e_type, g_id, e_rad, e_dur, e_align, m_q, m_r in entities:
            e_dur -= 1
            if e_dur <= 0:
                cursor.execute("DELETE FROM world_entities WHERE id=?", (e_id,))
                continue

            cursor.execute("SELECT q, r, wind_direction, pack_ecology, chaos_domain, pack_geo, pack_meso, micro_data_json FROM global_hexes WHERE id=?", (g_id,))
            hex_data = cursor.fetchone()
            if not hex_data:
                cursor.execute("DELETE FROM world_entities WHERE id=?", (e_id,))
                continue

            q, r, wind, p_eco, domain, p_geo, p_meso, micro_data_json = hex_data
            p1 = p_eco & 255

            if e_type in ["Hurricane", "Tornado", "Overcast", "Clear Skies"]:
                if p1 > 100 and random.random() < 0.25:
                    e_type = "Chaos Storm"
                    e_dur = 20
                    e_align = domain
                    self.log_event("Chaos", f"A {e_type} has mutated into a Chaos Storm of {e_align}!", conn)

            # 1. Determine intended MICRO step
            nm_q, nm_r = m_q, m_r
            intended_global_q, intended_global_r = q, r

            if e_type == "Chaos Storm":
                nm_q, nm_r = random.choice(get_neighbors(m_q, m_r))
                micro_hexes = unpack_micro_cluster(q, r, p_geo, p_meso, p_eco, micro_data_json)
                if (nm_q, nm_r) in micro_hexes:
                    micro_hexes[(nm_q, nm_r)].p1 = 255
                    cursor.execute("UPDATE global_hexes SET micro_data_json=? WHERE id=?", (pack_micro_cluster(micro_hexes), g_id))
            elif e_type == "Chaos Creature":
                nm_q, nm_r = random.choice(get_neighbors(m_q, m_r))
                micro_hexes = unpack_micro_cluster(q, r, p_geo, p_meso, p_eco, micro_data_json)
                if (nm_q, nm_r) in micro_hexes:
                    micro_hexes[(nm_q, nm_r)].p2 = 255
                    micro_hexes[(nm_q, nm_r)].p3 = 255
                    cursor.execute("UPDATE global_hexes SET micro_data_json=? WHERE id=?", (pack_micro_cluster(micro_hexes), g_id))
            elif e_type == "Null Zealots":
                if prison_coords:
                    pq, pr = random.choice(list(prison_coords.values()))
                    # Macro pathfind
                    if (q, r) != (pq, pr): intended_global_q, intended_global_r = step_towards(q, r, pq, pr)
                    # Micro step towards the boundary of the intended macro direction
                    nm_q, nm_r = random.choice(get_neighbors(m_q, m_r))
                else:
                    nm_q, nm_r = random.choice(get_neighbors(m_q, m_r))
            elif e_type == "Cult Monster" and e_align in prison_coords:
                pq, pr = prison_coords[e_align]
                if (q, r) != (pq, pr): intended_global_q, intended_global_r = step_towards(q, r, pq, pr)
                nm_q, nm_r = random.choice(get_neighbors(m_q, m_r))
                micro_hexes = unpack_micro_cluster(q, r, p_geo, p_meso, p_eco, micro_data_json)
                if (nm_q, nm_r) in micro_hexes:
                    micro_hexes[(nm_q, nm_r)].p1 = 255
                    micro_hexes[(nm_q, nm_r)].p3 = 255
                    cursor.execute("UPDATE global_hexes SET micro_data_json=? WHERE id=?", (pack_micro_cluster(micro_hexes), g_id))
            else:
                # Weather follows wind
                wq, wr = vecs.get(wind, (1, 0))
                nm_q, nm_r = m_q + wq, m_r + wr
                intended_global_q, intended_global_r = q + wq, r + wr

            # 2. Check Micro Boundary
            dist = (abs(nm_q) + abs(nm_r) + abs(-nm_q - nm_r)) // 2

            if dist > 4:
                # Crossed the micro-cluster boundary!
                # Move to intended global hex and reset micro coords to center
                nq, nr = intended_global_q, intended_global_r
                if nq == q and nr == r:
                    # If it was wandering and hit the edge, pick a random global neighbor
                    nq, nr = random.choice(get_neighbors(q, r))

                nq, nr = wrap_hex(nq, nr)

                cursor.execute("SELECT id FROM global_hexes WHERE q=? AND r=?", (nq, nr))
                new_g_id_row = cursor.fetchone()

                if new_g_id_row:
                    new_g_id = new_g_id_row[0]
                    cursor.execute("UPDATE world_entities SET global_hex_id=?, duration=?, type=?, alignment=?, micro_q=?, micro_r=? WHERE id=?",
                                   (new_g_id, e_dur, e_type, e_align, 0, 0, e_id))
                    alive_entities.append((e_id, e_type, new_g_id, e_rad, 0, 0, e_align))
                else:
                    # Hit the edge of the world
                    cursor.execute("DELETE FROM world_entities WHERE id=?", (e_id,))
            else:
                # Still inside the same micro-cluster
                cursor.execute("UPDATE world_entities SET duration=?, type=?, alignment=?, micro_q=?, micro_r=? WHERE id=?",
                               (e_dur, e_type, e_align, nm_q, nm_r, e_id))
                alive_entities.append((e_id, e_type, g_id, e_rad, nm_q, nm_r, e_align))

        return alive_entities

    def process_trade_routes(self, cursor, conn):
        cursor.execute("""
            SELECT tr.id, tr.faction_id, tr.settlement_a_id, tr.settlement_b_id, tr.route_type,
                   sa.wealth, sa.security_points, sb.wealth, sb.security_points,
                   sa.global_hex_id, sb.global_hex_id, f.special_rule
            FROM trade_routes tr
            JOIN settlements sa ON tr.settlement_a_id = sa.id
            JOIN settlements sb ON tr.settlement_b_id = sb.id
            JOIN factions f ON tr.faction_id = f.id
        """)
        routes = cursor.fetchall()

        sa_updates = []
        for row in routes:
            tr_id, f_id, sa_id, sb_id, r_type, w_a, sec_a, w_b, sec_b, g_a, g_b, f_rule = row

            # Base Trade Yield
            yield_val = 15.0

            # Check if traversing Chaos
            is_chaos = random.random() < 0.2
            if is_chaos and f_rule != "Sumpkin":
                yield_val = 0.0

            # Dust-Husk Riders Border Trade
            if r_type == 'Land' and f_rule == "Dust_Husk":
                yield_val *= 2.0 # They buy low and sell high!

            w_a += yield_val
            w_b += yield_val

            # Underworld Siphoning
            if random.random() < 0.3:
                siphon = yield_val * 0.5
                w_a -= siphon
                w_b -= siphon

                # Distribute illicit wealth to Syndicates and Smugglers
                cursor.execute("SELECT id, special_rule FROM factions WHERE special_rule IN ('Obsidian_Syndicate', 'Silk_Syndicate', 'Ghost_Flotilla', 'Sky_Baronies', 'Silent_Current', 'Black_Label', 'Spring_Ghosts', 'Crimson_Corsairs') ORDER BY RANDOM() LIMIT 1")
                syndicate = cursor.fetchone()
                if syndicate:
                    cursor.execute("UPDATE factions SET treasury = treasury + ? WHERE id=?", (siphon * 2, syndicate[0]))

            sa_updates.append((w_a, sa_id))
            sa_updates.append((w_b, sb_id))

            # Active trade route improves trust between the two factions
            fa_id = f_id
            cursor.execute("SELECT faction_id FROM settlements WHERE id=?", (sb_id,))
            fb_row = cursor.fetchone()
            if fb_row and fb_row[0] != fa_id:
                self._apply_trust_delta(fa_id, fb_row[0], 2, cursor)

        cursor.executemany("UPDATE settlements SET wealth=? WHERE id=?", sa_updates)

    def _apply_trust_delta(self, fa_id, fb_id, delta, cursor):
        """Apply a trust change between two factions, clamped to [-100, 100]."""
        cursor.execute(
            "SELECT trust_level FROM faction_relations WHERE faction_a_id=? AND faction_b_id=?",
            (fa_id, fb_id)
        )
        row = cursor.fetchone()
        trust = (row[0] if row else 0) + delta
        trust = max(-100, min(100, trust))
        cursor.execute(
            "INSERT OR REPLACE INTO faction_relations (faction_a_id, faction_b_id, status, trust_level) VALUES (?,?,?,?)",
            (fa_id, fb_id, self._trust_to_status(trust), trust)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO faction_relations (faction_a_id, faction_b_id, status, trust_level) VALUES (?,?,?,?)",
            (fb_id, fa_id, self._trust_to_status(trust), trust)
        )

    def _trust_to_status(self, trust):
        if trust > 80:   return 'Alliance'
        if trust > 40:   return 'Trading'
        if trust < -50:  return 'War'
        return 'Neutral'

    def process_crimes(self, cursor):
        """Generate crimes in settlements with low security. Cross-faction crimes damage trust."""
        cursor.execute("SELECT id, faction_id, security_points FROM settlements")
        for row in cursor.fetchall():
            s_id, s_faction, sec = row[0], row[1], row[2]
            if sec < 5 and random.random() < 0.3:
                crime_type = random.choice(["Theft", "Smuggling", "Assault"])
                severity = random.choice([1, 2, 3])
                cursor.execute(
                    "INSERT INTO crimes (settlement_id, type, severity) VALUES (?,?,?)",
                    (s_id, crime_type, severity)
                )
                cursor.execute(
                    "UPDATE settlements SET security_points = security_points - 1 WHERE id=?",
                    (s_id,)
                )
                # Cross-faction crimes damage diplomatic trust
                # Find if the criminal faction differs from the victim settlement's faction
                # Crimes originate internally; if security is collapsed, it signals
                # spillover from neighboring hostile factions — apply small trust hit
                # between this settlement's faction and the lowest-trust neighbor
                cursor.execute(
                    """SELECT fr.faction_a_id, fr.faction_b_id, fr.trust_level
                       FROM faction_relations fr
                       WHERE (fr.faction_a_id=? OR fr.faction_b_id=?)
                         AND fr.trust_level < 0
                       ORDER BY fr.trust_level ASC LIMIT 1""",
                    (s_faction, s_faction)
                )
                hostile = cursor.fetchone()
                if hostile:
                    other_f = hostile[1] if hostile[0] == s_faction else hostile[0]
                    self._apply_trust_delta(s_faction, other_f, -3, cursor)

    def process_paragons(self, cursor, conn, settlements):
        """Each paragon makes one decision per tick weighted by their faction's diplomacy."""
        cursor.execute("""
            SELECT p.id, p.name, p.archetype as descriptor, p.settlement_id,
                   s.faction_id, s.name as s_name, s.wealth, s.security_points
            FROM paragons p
            JOIN settlements s ON p.settlement_id = s.id
        """)
        paragons = cursor.fetchall()
        if not paragons:
            return

        # Build a map of faction_id -> list of enemy/ally faction ids
        cursor.execute("SELECT faction_a_id, faction_b_id, trust_level, status FROM faction_relations")
        all_relations = cursor.fetchall()
        # relation_map[fa][fb] = (trust, status)
        relation_map = {}
        for fa, fb, trust, status in all_relations:
            relation_map.setdefault(fa, {})[fb] = (trust, status)

        # Build settlement map by faction
        faction_settlements = {}
        for s in settlements:
            faction_settlements.setdefault(s[1], []).append(s)

        for p in paragons:
            p_id, p_name, archetype, s_id, faction_id, s_name, s_wealth, s_sec = p

            my_relations = relation_map.get(faction_id, {})
            if not my_relations:
                continue

            # Find the highest-trust and lowest-trust other faction
            best_f = max(my_relations, key=lambda f: my_relations[f][0], default=None)
            worst_f = min(my_relations, key=lambda f: my_relations[f][0], default=None)
            if best_f is None:
                continue

            best_trust, best_status = my_relations[best_f]
            worst_trust, worst_status = my_relations.get(worst_f, (0, 'Neutral'))

            # Archetype modifiers
            is_diplomat = (archetype == 'Diplomat')
            is_warrior  = (archetype == 'Warrior')
            is_merchant = (archetype == 'Merchant')

            if worst_status == 'War' and not is_diplomat:
                # Warrior paragons raid; others skirmish
                enemy_settlements = faction_settlements.get(worst_f, [])
                if enemy_settlements:
                    target = random.choice(enemy_settlements)
                    sec_dmg = 4 if is_warrior else 2
                    cursor.execute(
                        "UPDATE settlements SET security_points = max(0, security_points - ?) WHERE id=?",
                        (sec_dmg, target[0])
                    )
                    cursor.execute(
                        "INSERT INTO crimes (settlement_id, type, severity) VALUES (?,?,?)",
                        (target[0], 'Raid', 3 if is_warrior else 2)
                    )
                    self.log_event(
                        "Paragon",
                        f"{p_name} ({archetype}) of {s_name} raided {target[3]} (sec -{sec_dmg}).",
                        conn
                    )
                    self._apply_trust_delta(faction_id, worst_f, -5 if is_warrior else -2, cursor)

            elif best_status in ('Alliance', 'Trading'):
                # Diplomat/Merchant paragons boost trade
                ally_settlements = faction_settlements.get(best_f, [])
                if ally_settlements:
                    target = random.choice(ally_settlements)
                    trade_bonus = 30.0 if is_merchant else 15.0
                    cursor.execute(
                        "UPDATE settlements SET wealth = wealth + ? WHERE id=?",
                        (trade_bonus, s_id)
                    )
                    cursor.execute(
                        "UPDATE settlements SET wealth = wealth + ? WHERE id=?",
                        (trade_bonus, target[0])
                    )
                    trust_bonus = 7 if is_diplomat else 4
                    self._apply_trust_delta(faction_id, best_f, trust_bonus, cursor)
                    self.log_event(
                        "Paragon",
                        f"{p_name} ({archetype}) of {s_name} fostered trade with {target[3]} (+{trust_bonus} trust, +{trade_bonus} wealth each).",
                        conn
                    )

            else:
                # Neutral — paragon patrols, small security boost at home
                cursor.execute(
                    "UPDATE settlements SET security_points = min(100, security_points + 1) WHERE id=?",
                    (s_id,)
                )

    def trigger_tick(self):
        self.tick += 1
        self.year, self.month, self.day, self.season = get_calendar_info(self.tick)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        self.process_global_chaos_flow(cursor)
        self.manage_weather(cursor, conn)
        active_entities = self.process_world_entities(cursor, conn)

        cursor.execute("""
            SELECT s.id, s.faction_id, s.global_hex_id, s.name, s.settlement_level, s.population, s.spark_born_population, s.wealth, s.security_points, s.inventory_json, s.hidden_cultists, s.magic_loadout,
                   g.q, g.r, g.pack_geo, g.pack_meso, g.pack_ecology, g.micro_data_json, g.river_volume, g.is_lake, g.chaos_domain,
                   f.special_rule, s.micro_q, s.micro_r
            FROM settlements s
            JOIN global_hexes g ON s.global_hex_id = g.id
            JOIN factions f ON s.faction_id = f.id
        """)
        settlements = cursor.fetchall()

        if self.tick % 10 == 0:
            self.process_diplomacy(cursor, conn, settlements)
            self.process_trade_routes(cursor, conn)
            self.process_paragons(cursor, conn, settlements)
        # Crimes processed every tick
        self.process_crimes(cursor)

        # Order of the Clockwork Balancing
        normal_settlements = [row for row in settlements if not row[3].startswith("Prison") and row[3] != "The Warden Spire"]
        normal_settlements.sort(key=lambda x: x[6]) # sort by wealth
        clockwork_buffs = {s[0]: 50.0 for s in normal_settlements[:max(1, len(normal_settlements)//10)]}
        clockwork_debuffs = {s[0]: 50.0 for s in normal_settlements[-max(1, len(normal_settlements)//10):]}

        prisons = {}
        warden_spire = None
        for row in settlements:
            if row[3].startswith("Prison of "): prisons[row[18]] = (row[0], row[5])
            if row[3] == "The Warden Spire": warden_spire = row

        s_updates = []
        g_updates = []

        weather_farm_mod = 1.0
        weather_consume_mod = 1.0

        if self.season in ["Shadowburn", "Highreach"]: weather_farm_mod = 1.5
        elif self.season in ["Frostin", "Dimfreeze"]:
            weather_farm_mod = 0.5
            weather_consume_mod = 1.5
        elif self.season == "GreenSpan": weather_farm_mod = 2.0
        elif self.season == "Shadowfall": weather_farm_mod = 0.0

        global_rank2_cleanse = 0
        global_rank3_cleanse = 0

        if warden_spire:
            s_id, f_id, g_hex_id, name, s_level, pop, spark_pop, wealth, sec, inv_str, hidden, loadout_str, q, r, p_geo, p_meso, p_eco, micro, rvol, islake, domain, f_rule, m_q, m_r = warden_spire
            inventory = json.loads(inv_str)
            ranks = inventory.get("Warden Ranks", {"Rank 1": 0, "Rank 2": 0, "Rank 3": 0, "Rank 4": 0})

            inventory["Warden Ranks"]["Rank 1"] = ranks.get("Rank 1", 0) + 1
            pop += 1
            if random.random() < 0.5: spark_pop += 1

            if random.random() < 0.10 and ranks["Rank 1"] > 0:
                ranks["Rank 1"] -= 1; ranks["Rank 2"] += 1
            if random.random() < 0.05 and ranks["Rank 2"] > 0:
                ranks["Rank 2"] -= 1; ranks["Rank 3"] += 1
            if random.random() < 0.01 and ranks["Rank 3"] > 0:
                ranks["Rank 3"] -= 1; ranks["Rank 4"] += 1

            if ranks["Rank 1"] > 0:
                inventory.setdefault("Building", {})["Stone"] = inventory.get("Building", {}).get("Stone", 0) + ranks["Rank 1"]
            global_rank2_cleanse = ranks["Rank 2"]
            global_rank3_cleanse = ranks["Rank 3"]

            if ranks["Rank 4"] > 0:
                cursor.execute("SELECT id, pack_ecology, chaos_domain FROM global_hexes WHERE chaos_domain IS NOT NULL")
                prison_hexes = cursor.fetchall()
                highest_hex = None
                highest_p1 = 0
                for ph_id, ph_eco, ph_dom in prison_hexes:
                    ph_p1 = unpack_ecology(ph_eco)[0]
                    if ph_p1 > highest_p1:
                        highest_p1 = ph_p1
                        highest_hex = ph_id

                if highest_p1 >= 200:
                    ranks["Rank 4"] -= 1
                    pop -= 1
                    cursor.execute("UPDATE global_hexes SET pack_ecology=pack_ecology & 0xFFFFFF00 WHERE id=?", (highest_hex,))
                    self.log_event("Kamikaze", f"A Rank 4 Warden sacrificed themselves to seal a Prison!", conn)

            inventory["Warden Ranks"] = ranks
            s_updates.append((s_level, pop, spark_pop, wealth, sec, json.dumps(inventory), hidden, s_id))

        for row in settlements:
            s_id, f_id, g_hex_id, name, s_level, pop, spark_pop, wealth, sec, inv_str, hidden, loadout_str, q, r, p_geo, p_meso, p_eco, micro_json, river_vol, is_lake, domain, f_rule, m_q, m_r = row
            if name == "The Warden Spire": continue

            try: loadout = json.loads(loadout_str)
            except: loadout = ["Mass", "Mass", "Mass"]
            primary_dragon = loadout[0] if loadout else "Mass"

            # Spark Born Global Buffs
            if not name.startswith("Prison"):
                sec += (pop * 0.15) # Soldiers (15%)
                wealth += (pop * 0.05) # Wizards (7.5%)

                # Faction Unique Mechanics
                if f_rule == "Ursine_Hegemony":
                    sec += (pop * 0.30) # Total 3x combat power
                    local_weather_farm = 1.2 # Hearth bonus
                elif f_rule == "Heartland_Alliance":
                    if (p_geo & 0xF) == 4: local_weather_farm = 3.0 # Plains 3x
                    sec += 20.0 # Wolf / Beaver
                elif f_rule == "Iron_Caldera":
                    if (p_geo & 0xF) in [7, 3]: wealth += 50.0 # Volcano / Desert forge
                elif f_rule == "Sylvan_Empire":
                    if (p_geo & 0xF) == 1: sec += 50.0 # Forest
                elif f_rule == "Canopy_Clans":
                    if (p_geo & 0xF) == 0: local_weather_farm = 2.0 # Jungle
                elif f_rule == "Eastern_Hounds":
                    hidden = 0 # Purge cultists
                elif f_rule == "Flower_Valley":
                    sec += 100.0
                elif f_rule == "Hive_Commonwealth":
                    wealth += 20.0 # Honey/Textiles
                elif f_rule == "Coastal_Theocracy" and (river_vol > 0 or is_lake or (p_geo & 0xF) >= 9):
                    sec += (pop * 0.15)

                # Order of the Clockwork interference
                if s_id in clockwork_buffs: wealth += clockwork_buffs[s_id]
                if s_id in clockwork_debuffs: wealth = max(0, wealth - clockwork_debuffs[s_id])

            try: inventory = json.loads(inv_str)
            except: inventory = {"Survival": {}, "Building": {}, "Materials": {}, "Reagents": {}, "Magic": {}, "Equipment": {}, "Consumables": {}, "Vehicles": {}}
            for group in ["Survival", "Building", "Materials", "Reagents", "Magic", "Equipment", "Consumables", "Vehicles"]:
                if group not in inventory: inventory[group] = {}

            # Evaluate Tags and Rule Overrides
            cell_tags = []
            rule_overrides = {}
            if micro_json:
                try:
                    micro_data = json.loads(micro_json)
                    if isinstance(micro_data, dict):
                        cell_tags = micro_data.get("tags", [])
                        rule_overrides = micro_data.get("rule_overrides", {})
                except json.JSONDecodeError:
                    pass

            pop_growth_mod = rule_overrides.get("population_growth_modifier", 1.0)
            res_tick_mod = rule_overrides.get("resource_tick_multiplier", 1.0)

            local_weather_farm = 1.0 * res_tick_mod
            local_consume = 1.0

            # Example Tag Reaction: FLAMMABLE
            is_flammable = "FLAMMABLE" in cell_tags

            for w_id, w_type, w_g_id, w_rad, wq, wr, w_align in active_entities:
                dist = (abs(q - wq) + abs(r - wr) + abs(-q-r - (-wq-wr))) // 2
                if dist <= w_rad:
                    # Get storm attributes. w_align might contain a string of tags.
                    # e.g., "FIRE,NEXUS,DESTRUCTIVE"
                    storm_tags = []
                    if w_align:
                        storm_tags = [tag.strip() for tag in w_align.split(',')]

                    # Tag evaluation with storms dynamically
                    if "FIRE" in storm_tags and is_flammable:
                        self.log_event("Chaos", f"A FIRE storm mutated a FLAMMABLE cell at {name} into CHARRED ruins!", conn)
                        if "CHARRED" not in cell_tags:
                            cell_tags.append("CHARRED")
                        if "FLAMMABLE" in cell_tags:
                            cell_tags.remove("FLAMMABLE")
                        is_flammable = False
                        sec -= 10.0
                        pop -= max(1, int(pop * 0.1))
                        # Save modified tags
                        try:
                            md = json.loads(micro_json) if micro_json else {}
                            if isinstance(md, dict):
                                md["tags"] = cell_tags
                                micro_json = json.dumps(md)
                                cursor.execute("UPDATE global_hexes SET micro_data_json=? WHERE id=?", (micro_json, g_hex_id))
                        except json.JSONDecodeError:
                            pass

                    if w_type == "Hurricane": local_weather_farm *= 0.5
                    elif w_type == "Tornado": sec -= 5.0
                    elif w_type == "Overcast": local_weather_farm *= 1.2
                    elif w_type in ["Chaos Storm", "Cult Monster"]:
                        if f_rule == "Reliance":
                            pass # Completely immune to chaos
                        elif f_rule == "Prism_Scale" and w_align == "Lux":
                            pass # Immune to Lux
                        else:
                            # Trigger massive 50/50 domain effect!
                            pop, sec, inventory, d_farm, d_con, p_geo = self.apply_chaos_event(w_align, name, pop, sec, inventory, q, r, p_geo, cursor, conn)
                            local_weather_farm *= d_farm
                            local_consume *= d_con

                            if f_rule == "Sylvan_Empire" and w_align == "Nexus":
                                sec -= 50.0 # Hate fire

                            # Apply Cultist Infection (50% Spark Born vulnerable)
                            if "Inverted Physics" not in inventory.get("Tags", []) and f_rule != "Eastern_Hounds":
                                if random.random() < 0.5: hidden += 1

                    elif w_type == "Chaos Creature":
                        sec -= 20.0
                        pop -= max(1, int(pop * 0.05))
                    elif w_type == "Null Zealots":
                        if name.startswith("Prison of "):
                            global_rank3_cleanse += 5 # Nulls inadvertently help seal prisons by cleansing chaos
                        else:
                            sec -= 10.0
                            killed = min(spark_pop, max(1, int(spark_pop * 0.20)))
                            spark_pop -= killed
                            pop -= killed # Nulls persecute Spark Born

            if river_vol > 0 or is_lake:
                local_weather_farm *= 1.5

            farm_mult = weather_farm_mod * local_weather_farm * max(0.1, 1.0 - (hidden * 0.05))

            # Apply pop_growth_mod if they grow population somewhere (e.g. at end of year or generally)
            # Currently we can just apply it to spark_born/population growth if there is any,
            # or multiply wealth/security as a proxy for the multiplier if it's general.
            # But the requirement specifically mentions "multiplying baseline engine equations (like population growth curves)".
            # If the engine has a natural growth logic per tick, we apply it.
            # Looking at this loop, population natural growth seems to be missing except for prisons.
            # Let's add a basic growth tick using the modifier if no other exists.
            if self.tick % 10 == 0:
                pop += int(max(1, pop * 0.01 * pop_growth_mod))

            if global_rank2_cleanse > 0 and hidden > 0:
                cleansed = min(hidden, global_rank2_cleanse)
                hidden -= cleansed
                global_rank2_cleanse -= cleansed

            if hidden >= 10:
                hidden -= 1
                pop -= 1
                if prisons:
                    target_domain = random.choice(list(prisons.keys()))
                    p_s_id, _ = prisons[target_domain]
                    cursor.execute("UPDATE settlements SET population = population + 1 WHERE id=?", (p_s_id,))

            if name.startswith("Prison of "):
                if global_rank3_cleanse > 0:
                    p1, p2, p3, res = unpack_ecology(p_eco)
                    cleansed = min(p1, global_rank3_cleanse * 10)
                    p1 -= cleansed
                    p_eco = pack_ecology(p1, p2, p3, res)
                    g_updates.append((p_eco, g_hex_id))

                if pop >= 100 and random.random() < 0.05:
                    pop -= 50
                    cursor.execute("INSERT INTO world_entities (type, global_hex_id, radius, duration, alignment) VALUES ('Cult Monster', ?, 1, 50, ?)", (g_hex_id, domain))
                    self.log_event("Chaos", f"A Monstrous Cultist erupted from {name}!", conn)

            # Save changes applied by world entities to settlements
            s_updates.append((s_level, pop, spark_pop, wealth, sec, json.dumps(inventory), hidden, s_id))

        cursor.executemany("UPDATE settlements SET settlement_level=?, population=?, spark_born_population=?, wealth=?, security_points=?, inventory_json=?, hidden_cultists=? WHERE id=?", s_updates)
        if g_updates:
            cursor.executemany("UPDATE global_hexes SET pack_ecology=? WHERE id=?", g_updates)

        # Execute Layer 0: High-Fidelity Cluster Simulation
        cursor.execute("SELECT DISTINCT global_hex_id FROM settlements")
        active_clusters = cursor.fetchall()
        for (c_id,) in active_clusters:
            process_cluster_fidelity(self.tick, c_id, conn)

        self.save_metadata(conn)
        conn.commit()
        conn.close()
        return {"tick": self.tick, "processed": len(settlements)}

if __name__ == "__main__":
    engine = GlobalEngine()
    print("Running Tick...")
    res = engine.trigger_tick()
    print(res)
