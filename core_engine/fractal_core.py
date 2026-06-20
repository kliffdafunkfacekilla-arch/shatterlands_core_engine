import json
import sqlite3
import random
from core_engine.codec import unpack_micro_cluster, pack_micro_cluster

def process_cluster_fidelity(engine_tick, global_hex_id, conn):
    cursor = conn.cursor()
    cursor.execute("SELECT q, r, pack_geo, pack_meso, pack_ecology, micro_data_json FROM global_hexes WHERE id=?", (global_hex_id,))
    row = cursor.fetchone()
    if not row: return
    g_q, g_r, p_geo, p_meso, p_eco, micro_json = row

    micro_hexes = unpack_micro_cluster(g_q, g_r, p_geo, p_meso, p_eco, micro_json)

    cursor.execute("SELECT id, faction_id, name, settlement_level, population, spark_born_population, inventory_json, wealth, security_points, micro_q, micro_r, capital_id, expansion_ring FROM settlements WHERE global_hex_id=?", (global_hex_id,))
    settlements = cursor.fetchall()

    # --- ECOLOGY LOOP (Plant -> Prey -> Predator) ---
    for hx in micro_hexes.values():
        cursor.execute("SELECT id FROM buildings WHERE type='farm' AND settlement_id IN (SELECT id FROM settlements WHERE global_hex_id=? AND micro_q=? AND micro_r=?)", (global_hex_id, hx.q, hx.r))
        has_structure = cursor.fetchone()

        if has_structure:
            # Building removes the 3 part cycle by mechanics
            pass
        else:
            # Baseline plant growth
            if hx.p1 < 250: hx.p1 += 5

            # Prey eat plants
            if hx.p1 > 10 and hx.p2 < 100:
                hx.p1 -= 2
                hx.p2 += 1

            # Predators eat prey
            if hx.p2 > 10 and hx.p3 < 50:
                hx.p2 -= 2
                hx.p3 += 1

    # --- SETTLEMENT METABOLIC LOOP ---
    for s in settlements:
        s_id, f_id, name, level, pop, spark_born_pop, inv_str, wealth, sec, m_q, m_r, cap_id, exp_ring = s

        try:
            inventory = json.loads(inv_str)
        except:
            inventory = {"Survival": {"Food": 500.0}}
        food_stockpile = inventory.setdefault("Survival", {}).get("Food", 0.0)

        cursor.execute("SELECT name, special_rule FROM factions WHERE id=?", (f_id,))
        f_row = cursor.fetchone()
        f_rule = f_row[1] if f_row else ""

        # Calculate working population
        working_pop = max(1, pop)

        def get_dist(hq, hr):
            # Explicitly handle None values as center-bias
            q = m_q if m_q is not None else 0
            r = m_r if m_r is not None else 0
            return (abs(hq - q) + abs(hr - r) + abs(-hq-hr - (-q-r))) // 2

        exp_ring = exp_ring if exp_ring is not None else 0
        reachable = [hx for hx in micro_hexes.values() if get_dist(hx.q, hx.r) <= level + 2 + exp_ring]

        # Gather Phase
        for hx in reachable:
            if working_pop <= 0: break

            assign = min(50, working_pop)
            working_pop -= assign

            # The Golden Rule: 1 Unit of Food = 1 Worker Action
            if food_stockpile < assign:
                assign = int(food_stockpile)
            food_stockpile -= assign
            if assign <= 0: break

            cursor.execute("SELECT level FROM buildings WHERE type='farm' AND settlement_id=? LIMIT 1", (s_id,))
            farm = cursor.fetchone()

            if farm:
                out_rate = farm[0] * 5
                maint = farm[0] * 2
                # Heartland Alliance: Farm yield is tripled on Plains
                if f_rule == "Heartland_Alliance" and hx.biome_id == 4:
                    out_rate *= 3.0

                if wealth >= maint:
                    wealth -= maint
                    # Farms multiply output
                    food_stockpile += assign * out_rate
                else:
                    farm = None # Farm fails, fallback to manual

            if not farm:
                # Paragon dictates priorities!
                import json
                cursor.execute("SELECT motivation, stats_json FROM paragons WHERE settlement_id=?", (s_id,))
                paragon = cursor.fetchone()

                goal = paragon[0] if paragon else "Survive"
                stats = json.loads(paragon[1]) if paragon and paragon[1] else {}

                s_vita = stats.get("vita", 1)
                s_motus = stats.get("motus", 1)
                s_flux = stats.get("flux", 1)

                # Dynamic priority queue based on Paragon Personality
                priorities = [("Predator", hx.p3), ("Prey", hx.p2), ("Plant", hx.p1)]
                if goal == "Survive" or s_vita > 5:
                    priorities = [("Plant", hx.p1), ("Prey", hx.p2), ("Predator", hx.p3)] # Safe food
                elif goal == "Build an Army" or s_motus > 5:
                    priorities = [("Predator", hx.p3), ("Plant", hx.p1), ("Prey", hx.p2)] # Materials for weapons
                elif goal == "Hoard Wealth" or s_flux > 5:
                    priorities = [("Prey", hx.p2), ("Predator", hx.p3), ("Plant", hx.p1)] # Reagents for trade

                harvested = False
                for p_type, amount in priorities:
                    if amount >= 1:
                        harvest = min(amount, assign)
                        if p_type == "Predator":
                            hx.p3 -= harvest; food_stockpile += harvest * 0.5; wealth += harvest * 0.5
                        elif p_type == "Prey":
                            hx.p2 -= harvest; food_stockpile += harvest * 0.8; wealth += harvest * 0.2
                        elif p_type == "Plant":
                            hx.p1 -= harvest;
                            food_yield = harvest * 0.9
                            # Canopy Clans: Double food production in Jungle
                            if f_rule == "Canopy_Clans" and hx.biome_id == 3: food_yield *= 2.0
                            food_stockpile += food_yield
                            wealth += harvest * 0.1
                        harvested = True
                        break

                if not harvested:
                    # Gather Base Material
                    food_stockpile += assign * 0.2 # Starvation rations
                    if hx.biome_id in [6, 7]: # Mountains (Stone/Crystal)
                        hx.elevation -= 0.01 * assign # Causes erosion
                        wealth += assign
                        if goal == "Build an Army": sec += assign * 0.1 # Stone fortifications
                    elif hx.biome_id in [8, 10]: # Desert/Volcano
                        if f_rule in ["Iron_Caldera", "Hearthless"]:
                            wealth += assign * 3.0 # Massive weapons/metal generation
                            sec += assign * 0.5
                            if f_rule == "Hearthless":
                                food_stockpile += assign * 1.5 # Hearth boost to food effectiveness
                        else:
                            wealth += assign * 0.5
                    elif hx.biome_id in [1, 2]: # Forest (Wood)
                        hx.biome_id = 3 # Deforests to Plains
                        w_yield = assign
                        if f_rule == "Sylvan_Empire": w_yield *= 3.0 # Wood generation tripled
                        wealth += w_yield

            # River Folk passive bonus near water
            if f_rule == "River_Folk" and hx.biome_id in [9, 11]: # Ocean/Lake
                food_stockpile += assign * 0.5
                wealth += assign * 0.5

        # Consumption Phase
        # Hive Commonwealth wealth boost from textiles/honey exports
        if f_rule == "Hive_Commonwealth": wealth += pop * 0.5

        consume_rate = 1.0
        if f_rule == "Hearthless": consume_rate = 0.5 # Less food consumed due to Hearth boost
        elif f_rule == "Dust_Husk": consume_rate = 0.5 # Consume 50% less food globally

        if food_stockpile > pop * consume_rate:
            # Surplus -> Growth
            if f_rule != "Hearthless": # Hearthless don't naturally grow
                pop += 1
                if random.random() < 0.5: spark_born_pop += 1
            wealth += 1.0
        else:
            # Starvation
            starved = max(1, int(pop * 0.1))
            pop -= starved
            spark_born_pop = max(0, spark_born_pop - (starved // 2))
            sec -= 1.0
            cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)",
                           (engine_tick, "Starvation", f"{name} is starving!", g_q, g_r))

        # --- RING EXPANSION & HUB LOGISTICS LOOP ---
        if cap_id is None: # Capital City
            if pop >= 150 + (exp_ring * 50) and wealth >= 200 + (exp_ring * 100) and exp_ring < 4:
                # Expand Territory!
                exp_ring += 1
                wealth -= 100
                cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)",
                               (engine_tick, "Expansion", f"{name} expanded to Ring {exp_ring}!", g_q, g_r))

                # Check for Hub Spawning if reaching deep rings
                if exp_ring >= 3 and pop >= 200:
                    outer_hexes = [hx for hx in micro_hexes.values() if get_dist(hx.q, hx.r) == exp_ring + 2 and hx.biome_id in [3, 4]] # Plains/Savanna for clear building
                    if outer_hexes:
                        hub_hex = random.choice(outer_hexes)
                        pop -= 20
                        wealth -= 50
                        hub_name = f"{name} Hub-Village"
                        cursor.execute("""
                            INSERT INTO settlements (faction_id, global_hex_id, name, settlement_level, capital_id, population, spark_born_population, wealth, security_points, micro_q, micro_r)
                            VALUES (?, ?, ?, 1, ?, 20, 10, 50.0, 10.0, ?, ?)
                        """, (f_id, global_hex_id, hub_name, s_id, hub_hex.q, hub_hex.r))

                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)",
                                       (engine_tick, "Expansion", f"{name} founded a relay Hub-Village to secure outer nodes!", g_q, g_r))
        else:
            # Hub Village Logistics: Send excess up the chain
            if wealth > 20:
                tribute = wealth - 20
                wealth = 20
                cursor.execute("UPDATE settlements SET wealth = wealth + ? WHERE id=?", (tribute, cap_id))
            if food_stockpile > pop * 2:
                food_trib = food_stockpile - (pop * 2)
                food_stockpile -= food_trib
                cursor.execute("SELECT inventory_json FROM settlements WHERE id=?", (cap_id,))
                c_row = cursor.fetchone()
                if c_row:
                    try: c_inv = json.loads(c_row[0])
                    except: c_inv = {}
                    c_inv.setdefault("Survival", {})["Food"] = c_inv.setdefault("Survival", {}).get("Food", 0) + food_trib
                    cursor.execute("UPDATE settlements SET inventory_json=? WHERE id=?", (json.dumps(c_inv), cap_id))

        # --- LUNAR CHAOS EFFECTS ---
        import math
        chaos_nodes = []
        random.seed(12345)
        for i in range(12):
            lat = math.asin(2 * random.random() - 1)
            lon = 2 * math.pi * random.random()
            chaos_nodes.append({"lon": lon, "lat": lat})
        random.seed()

        lunar_offset = (engine_tick // 24) % 28
        drift = math.sin((lunar_offset / 28.0) * 2 * math.pi) * 0.05

        lon = (g_q / 50.0) * (2 * math.pi) - math.pi
        lat = (g_r / 50.0) * math.pi - (math.pi / 2)

        is_awakened = False
        for node in chaos_nodes:
            n_lon, n_lat = node["lon"] + drift, node["lat"] + drift
            line_len_sq = n_lon**2 + n_lat**2
            if line_len_sq > 0:
                t = max(0, min(1, (lon * n_lon + lat * n_lat) / line_len_sq))
                proj_lon, proj_lat = t * n_lon, t * n_lat
                if math.sqrt((lon - proj_lon)**2 + (lat - proj_lat)**2) < 0.04:
                    is_awakened = True
                    break

        if is_awakened:
            cursor.execute("SELECT chaos_domain FROM global_hexes WHERE q=? AND r=?", (g_q, g_r))
            row = cursor.fetchone()
            if row and row[0]:
                domain = row[0]
                effect_roll = random.random()
                if domain == "Mass":
                    if effect_roll < 0.5:
                        wealth = max(0, wealth - 20)
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"{name} crushed by Mass gravity!", g_q, g_r))
                    else:
                        pop = max(1, pop - 10)
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"People flung into the air at {name}!", g_q, g_r))
                elif domain == "Ordo":
                    if effect_roll < 0.5:
                        pop = max(1, pop - 5)
                        for hx in micro_hexes.values(): hx.p1 = 0; hx.p2 = 0
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Ordo froze {name}'s ecology!", g_q, g_r))
                    else:
                        sec += 20
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Ordo rigidly structured {name}!", g_q, g_r))
                elif domain == "Motus":
                    if effect_roll < 0.5:
                        wealth = max(0, wealth - 50)
                    else:
                        pop = max(1, pop - 5); wealth = max(0, wealth - 10)
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Motus sonic gale ripped through {name}!", g_q, g_r))
                elif domain == "Flux":
                    if effect_roll < 0.5:
                        for hx in micro_hexes.values(): hx.res = random.randint(1, 12)
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Flux transmuted the land around {name}!", g_q, g_r))
                elif domain == "Vita":
                    for hx in micro_hexes.values(): hx.p1 = 255
                    if effect_roll < 0.5:
                        pop = max(1, pop - 15)
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Vita cancerous overgrowth killed people at {name}!", g_q, g_r))
                    else:
                        sec = max(0, sec - 10)
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Vita toxic hazards formed at {name}!", g_q, g_r))
                elif domain == "Nexus":
                    if effect_roll < 0.5:
                        pop = max(1, pop - 10)
                        for hx in micro_hexes.values(): hx.p1 = 0
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Nexus fire storm burned {name}!", g_q, g_r))
                    else:
                        wealth = max(0, wealth - 30)
                        cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Nexus explosive reactions wrecked {name}!", g_q, g_r))
                elif domain == "Ratio":
                    if effect_roll < 0.5:
                        wealth = random.randint(0, 100)
                    else:
                        sec = max(0, sec - 20)
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Ratio logic-riots disrupted {name}!", g_q, g_r))
                elif domain == "Anumis":
                    if effect_roll < 0.5:
                        temp = wealth; wealth = sec; sec = temp
                    else:
                        wealth = 0
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Anumis warped reality at {name}!", g_q, g_r))
                elif domain == "Lux":
                    if effect_roll < 0.5:
                        pop = max(1, pop - 2)
                    else:
                        sec = max(0, sec - 20)
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Lux blinded and panicked {name}!", g_q, g_r))
                elif domain == "Omen":
                    if effect_roll < 0.5:
                        pop += 5; wealth += 10
                    else:
                        pop = max(1, pop - 5); wealth = max(0, wealth - 20)
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Omen shifted time at {name}!", g_q, g_r))
                elif domain == "Aura":
                    if effect_roll < 0.5:
                        sec = 100; wealth = max(0, wealth - 10)
                    else:
                        sec = max(0, sec - 30); pop = max(1, pop - 5)
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Aura emotional spikes hit {name}!", g_q, g_r))
                elif domain == "Lex":
                    if effect_roll < 0.5:
                        sec = 100
                    else:
                        sec = 0
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Lex mandates rewrote {name}!", g_q, g_r))

        # --- UNDERWORLD & CRIME LOOP ---

        # Bandits skim trade routes based on low security
        cursor.execute("SELECT sum(bandwidth) FROM trade_routes WHERE settlement_a_id=? OR settlement_b_id=?", (s_id, s_id))
        route_data = cursor.fetchone()
        trade_vol = route_data[0] if route_data and route_data[0] else 0

        if trade_vol > 0:
            theft_rate = max(0.01, 0.10 - (sec * 0.01))
            stolen_wealth = wealth * theft_rate
            stolen_food = food_stockpile * theft_rate

            wealth -= stolen_wealth
            food_stockpile -= stolen_food

            cursor.execute("SELECT id, wealth FROM criminal_hideouts WHERE global_hex_id=?", (global_hex_id,))
            hideout = cursor.fetchone()
            if hideout:
                h_id, h_wealth = hideout
                cursor.execute("UPDATE criminal_hideouts SET wealth=wealth+? WHERE id=?", (stolen_wealth, h_id))

                # Smuggling & Consumption
                if sec < 10 and h_wealth > 20: # Narcotics
                    cursor.execute("UPDATE criminal_hideouts SET wealth=wealth-20 WHERE id=?", (h_id,))
                    pop -= 1 # Health debuff
                    sec -= 2 # Crime increase
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Crime", f"Narcotics smuggled into {name}!", g_q, g_r))
                elif sec < 0 and h_wealth > 50: # Terrorist Weapons
                    cursor.execute("UPDATE criminal_hideouts SET wealth=wealth-50 WHERE id=?", (h_id,))
                    pop -= max(5, int(pop * 0.1))
                    sec -= 10
                    cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Crime", f"Terrorist explosion in {name}!", g_q, g_r))

        inventory["Survival"]["Food"] = food_stockpile
        cursor.execute("UPDATE settlements SET population=?, spark_born_population=?, inventory_json=?, wealth=?, security_points=?, expansion_ring=? WHERE id=?", (pop, spark_born_pop, json.dumps(inventory), wealth, sec, exp_ring, s_id))

    # --- CHAOS AGENTS LOOP ---
    cursor.execute("SELECT id, type, strength, micro_q, micro_r FROM chaos_agents WHERE global_hex_id=? AND is_active=1", (global_hex_id,))
    for agent in cursor.fetchall():
        a_id, a_type, a_str, a_q, a_r = agent
        if a_type == "Cultist":
            # Just log since latent_chaos doesn't exist explicitly in micro_hexes table structure
            cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Cultists are increasing Latent Chaos at {a_q},{a_r}!", g_q, g_r))
        elif a_type == "Warden":
            cursor.execute("INSERT INTO event_log (tick, category, message, global_q, global_r) VALUES (?, ?, ?, ?, ?)", (engine_tick, "Chaos", f"Wardens are purging Latent Chaos at {a_q},{a_r}!", g_q, g_r))

    # Save micro hexes back to JSON
    new_json = pack_micro_cluster(micro_hexes)

    # Update global pack_ecology
    avg_p1 = sum(hx.p1 for hx in micro_hexes.values()) // 91
    avg_p2 = sum(hx.p2 for hx in micro_hexes.values()) // 91
    avg_p3 = sum(hx.p3 for hx in micro_hexes.values()) // 91
    avg_res = sum(hx.res for hx in micro_hexes.values()) // 91

    g_p1 = max(0, min(255, int(avg_p1)))
    g_p2 = max(0, min(255, int(avg_p2)))
    g_p3 = max(0, min(255, int(avg_p3)))
    g_res = max(0, min(65535, int(avg_res)))
    new_eco = g_p1 | (g_p2 << 8) | (g_p3 << 16) | (g_res << 24)

    cursor.execute("UPDATE global_hexes SET pack_ecology=?, micro_data_json=? WHERE id=?", (new_eco, new_json, global_hex_id))
