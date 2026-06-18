import random
import json

BIOME_RESOURCES = {
    "Forest": {"plant": "Berries", "meat": "Venison", "material": "Leather", "building": "Wood", "reagent": "Resin"},
    "Plains": {"plant": "Grain", "meat": "Beef", "material": "Leather", "building": "Clay", "reagent": "Fiber"},
    "Mountain": {"plant": "Roots", "meat": "Goat", "material": "Horn", "building": "Stone", "reagent": "Ash"},
    "Desert": {"plant": "Cactus", "meat": "Lizard", "material": "Scales", "building": "Sandstone", "reagent": "Venom"},
    "Glacier": {"plant": "Moss", "meat": "Seal", "material": "Fur", "building": "Ice", "reagent": "Oil"}
}

VARIANTS = {
    "Berries": "Bloodthorn Berries",
    "Wood": "Ironwood",
    "Venison": "Shadow-Stag Meat",
    "Leather": "Shadow-Stag Hide",
    "Resin": "Amberglass",
    "Grain": "Sun-Wheat",
    "Beef": "Auroch Meat",
    "Clay": "Red-River Clay",
    "Fiber": "Silkweed",
    "Roots": "Deep-Tuber",
    "Goat": "Crag-Goat",
    "Horn": "Crag-Horn",
    "Stone": "Marble",
    "Ash": "Volcanic Ash",
    "Cactus": "Glass-Spine Cactus",
    "Lizard": "Sand-Drake Meat",
    "Scales": "Sand-Drake Scales",
    "Sandstone": "Obsidian",
    "Venom": "Basilisk Venom",
    "Moss": "Frost-Lichen",
    "Seal": "Ice-Leviathan Meat",
    "Fur": "Ice-Leviathan Fur",
    "Ice": "True-Ice",
    "Oil": "Leviathan Blubber"
}

def get_biome_type(biome_id):
    if biome_id in (1, 4, 5): return "Forest"
    if biome_id in (2, 3): return "Plains"
    if biome_id in (6, 7): return "Mountain"
    if biome_id == 8: return "Desert"
    if biome_id == 0: return "Glacier"
    return "Plains"

def mutate_resource(base_name):
    if random.random() < 0.10: # 10% mutation chance
        return VARIANTS.get(base_name, base_name)
    return base_name

class MicroHex:
    def __init__(self, q, r, biome_id, elevation):
        self.q = q
        self.r = r
        self.biome_id = biome_id
        self.elevation = elevation
        self.p1 = 0
        self.p2 = 0
        self.p3 = 0
        self.res = 0

        self.res_plant = ""
        self.res_meat = ""
        self.res_material = ""
        self.res_building = ""
        self.res_reagent = ""
        self.res_special = ""

    @property
    def distance_from_center(self):
        return (abs(self.q) + abs(self.r) + abs(-self.q - self.r)) // 2

def get_hexes_in_radius(N):
    hexes = []
    for q in range(-N, N+1):
        for r in range(max(-N, -q-N), min(N, -q+N)+1):
            hexes.append((q, r))
    return hexes

def unpack_micro_cluster(global_q, global_r, pack_geo, pack_meso, pack_eco, micro_data_json=None):
    random.seed(f"{global_q}_{global_r}_{pack_meso}")

    base_biome = pack_geo & 0xF
    elevation_val = (pack_geo >> 4) & 0xF
    base_elev = float(elevation_val)
    if base_biome in [9, 10, 11, 12]:
        base_elev = -base_elev

    micro_hexes = {}
    coords = get_hexes_in_radius(5)

    for q, r in coords:
        noise = random.uniform(-1.5, 1.5)
        elev = base_elev + noise

        final_biome = base_biome
        if random.random() < 0.1:
            final_biome = (base_biome + random.randint(-1, 1)) % 16

        hx = MicroHex(q, r, final_biome, elev)

        b_type = get_biome_type(final_biome)
        res_dict = BIOME_RESOURCES[b_type]

        hx.res_plant = mutate_resource(res_dict["plant"])
        hx.res_meat = mutate_resource(res_dict["meat"])
        hx.res_material = mutate_resource(res_dict["material"])
        hx.res_building = mutate_resource(res_dict["building"])
        hx.res_reagent = mutate_resource(res_dict["reagent"])

        special_chance = random.random()
        if b_type == "Mountain" and special_chance < 0.15:
            hx.res_special = random.choice(["Iron Vein", "Copper Vein", "Gold Vein", "Fire Element", "Earth Element"])
        elif special_chance < 0.02:
            hx.res_special = random.choice(["Dragon Stone", "Blackstone", "Ancient Artifact", "Relic"])

        micro_hexes[(q, r)] = hx

    if micro_data_json:
        data = json.loads(micro_data_json)
        for hex_data in data:
            q = hex_data.get("q", 0)
            r = hex_data.get("r", 0)
            if (q, r) in micro_hexes:
                hx = micro_hexes[(q, r)]
                hx.p1 = hex_data.get("p1", 0)
                hx.p2 = hex_data.get("p2", 0)
                hx.p3 = hex_data.get("p3", 0)
                hx.res = hex_data.get("res", 0)

                if "res_plant" in hex_data: hx.res_plant = hex_data["res_plant"]
                if "res_meat" in hex_data: hx.res_meat = hex_data["res_meat"]
                if "res_material" in hex_data: hx.res_material = hex_data["res_material"]
                if "res_building" in hex_data: hx.res_building = hex_data["res_building"]
                if "res_reagent" in hex_data: hx.res_reagent = hex_data["res_reagent"]
                if "res_special" in hex_data: hx.res_special = hex_data["res_special"]
    else:
        g_p1 = pack_eco & 0xFF
        g_p2 = (pack_eco >> 8) & 0xFF
        g_p3 = (pack_eco >> 16) & 0xFF
        g_res = (pack_eco >> 24) & 0xFFFF

        for (q, r), hx in micro_hexes.items():
            hx.p1 = max(0, min(255, int(g_p1 + random.uniform(-20, 20))))
            hx.p2 = max(0, min(255, int(g_p2 + random.uniform(-20, 20))))
            hx.p3 = max(0, min(255, int(g_p3 + random.uniform(-10, 10))))
            hx.res = max(0, int(g_res + random.uniform(-1000, 1000)))

    return micro_hexes

def pack_micro_cluster(micro_hexes):
    data = []
    for (q, r), hx in micro_hexes.items():
        data.append({
            "q": q,
            "r": r,
            "p1": hx.p1,
            "p2": hx.p2,
            "p3": hx.p3,
            "res": hx.res,
            "res_plant": hx.res_plant,
            "res_meat": hx.res_meat,
            "res_material": hx.res_material,
            "res_building": hx.res_building,
            "res_reagent": hx.res_reagent,
            "res_special": hx.res_special
        })
    return json.dumps(data)
