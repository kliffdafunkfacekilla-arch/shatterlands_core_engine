import sqlite3
import json
from core_engine.engine import DB_PATH, unpack_ecology

class NPCDirector:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def get_npc_motivations(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Fetch paragons and their associated settlement/hex data
        cursor.execute("""
            SELECT p.id, p.name, p.descriptor, p.settlement_id,
                   s.faction_id, s.name as s_name, s.wealth, s.security_points,
                   g.pack_ecology, g.chaos_domain, g.q, g.r
            FROM paragons p
            JOIN settlements s ON p.settlement_id = s.id
            JOIN global_hexes g ON s.global_hex_id = g.id
        """)
        paragons = cursor.fetchall()

        npc_table = []
        for p_id, p_name, descriptor, s_id, f_id, s_name, wealth, security, pack_ecology, chaos_domain, q, r in paragons:
            p1_chaos, _, _, _ = unpack_ecology(pack_ecology)

            base_motivation = f"{descriptor} driven by personal goals."

            # Scale motivation by chaos index
            chaos_factor = p1_chaos / 255.0

            scaled_motivation = base_motivation
            if chaos_factor > 0.8:
                scaled_motivation = f"Driven to madness and paranoia by intense chaos from {chaos_domain}."
            elif chaos_factor > 0.5:
                scaled_motivation = f"Highly stressed and suspicious due to rising chaos ({chaos_domain})."
            elif wealth < 100:
                scaled_motivation = f"Desperate for resources and wealth in {s_name}."
            elif security < 50:
                scaled_motivation = f"Fearful for the safety of {s_name}."

            npc_table.append({
                "paragon_id": p_id,
                "name": p_name,
                "descriptor": descriptor,
                "settlement": s_name,
                "faction_id": f_id,
                "local_chaos_index": p1_chaos,
                "chaos_domain": chaos_domain,
                "motivation": scaled_motivation
            })

        conn.close()
        return npc_table

    def get_scaled_faction_trust(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Fetch faction relations
        cursor.execute("SELECT faction_a_id, faction_b_id, trust_level, status FROM faction_relations")
        relations = cursor.fetchall()

        # Calculate average chaos for each faction's settlements
        cursor.execute("""
            SELECT s.faction_id, AVG(g.pack_ecology)
            FROM settlements s
            JOIN global_hexes g ON s.global_hex_id = g.id
            GROUP BY s.faction_id
        """)
        faction_chaos_raw = cursor.fetchall()

        faction_chaos = {}
        for f_id, avg_ecology in faction_chaos_raw:
            p1_chaos, _, _, _ = unpack_ecology(int(avg_ecology))
            faction_chaos[f_id] = p1_chaos

        trust_table = []
        for fa, fb, base_trust, status in relations:
            # Average chaos between the two factions
            chaos_a = faction_chaos.get(fa, 0)
            chaos_b = faction_chaos.get(fb, 0)
            avg_chaos = (chaos_a + chaos_b) / 2.0

            # Chaos breeds paranoia, degrading trust
            # Every 10 points of chaos reduces trust by 1
            chaos_penalty = int(avg_chaos / 10.0)
            scaled_trust = max(-100, min(100, base_trust - chaos_penalty))

            trust_table.append({
                "faction_a_id": fa,
                "faction_b_id": fb,
                "base_trust": base_trust,
                "status": status,
                "avg_chaos_exposure": avg_chaos,
                "scaled_trust": scaled_trust,
                "trust_penalty_from_chaos": chaos_penalty
            })

        conn.close()
        return trust_table
