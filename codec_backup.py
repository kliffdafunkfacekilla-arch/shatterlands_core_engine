# codec.py
# Bit-packing and definitions for Shatterlands Simulator

# Base Biomes (0-11). Elevation determines Land vs. Aquatic automatically.
BIOME_BASE = {
    0: "Hot/Wet", 
    1: "Mid/Wet", 
    2: "Cold/Wet", 
    3: "Hot/Dry", 
    4: "Mid/Dry", 
    5: "Cold/Dry", 
    6: "High Relief", 
    7: "Geothermal", 
    8: "Extreme Cold",
    9: "Warped (Chaos Flow)",
    10: "Prison (Magistar Node)",
    11: "The Convergence (Void Crater)"
}

def get_biome_name(biome_id: int, elevation: float) -> str:
    """Translates the base biome into its Terrestrial or Aquatic equivalent."""
    if biome_id == 9: return "Warped Terrain (Chaos Path)"
    if biome_id == 10: return "Magistar Prison Node"
    if biome_id == 11: return "The Convergence Crater"
    
    is_underwater = elevation <= 0
    
    if biome_id == 8: return "Glacier/Ice Shelf"
    if biome_id == 6: return "Abyssal Trench" if is_underwater else "Mountain Peak"
    if biome_id == 7: return "Hydrothermal Vents" if is_underwater else "Geysers/Springs"
    if biome_id == 0: return "Coral Reef" if is_underwater else "Jungle/Rainforest"
    if biome_id == 1: return "Kelp Forest" if is_underwater else "Temperate Forest (Non-Pine)"
    if biome_id == 2: return "Arctic Kelp" if is_underwater else "Taiga (Pine Forest)"
    if biome_id == 3: return "Sand Flats" if is_underwater else "Desert"
    if biome_id == 4: return "Open Ocean" if is_underwater else "Steppe/Grassland"
    if biome_id == 5: return "Deep Cold Ocean" if is_underwater else "Tundra"
    
    return "Unknown"

FACTIONS = {
    0: "Unclaimed", 1: "Canopy Clans", 2: "Vaneer Concord", 3: "Ursine Hegemony",
    4: "Heartland Alliance", 5: "Iron Caldera", 6: "Coastal Theocracy",
    7: "Meridian Chain", 8: "Scute Confederacy", 9: "Prism-Scale Collective",
    10: "Dust-Husk Riders", 11: "Eastern Hounds", 12: "Guerrilla Clans",
    13: "River Folk", 14: "Sump-Kin", 15: "Flower Valley Folk"
}

RESOURCES = {
    0: "None", 1: "Chromium (Lux)", 2: "Titanium (Ordo)", 3: "Lithium (Lex)",
    4: "Gold (Flux)", 5: "Silicon (Ratio)", 6: "Tungsten (Nexus)",
    7: "Bismuth (Anumis)", 8: "Osmium (Mass)", 9: "Iridium (Omen)",
    10: "Silver (Vita)", 11: "Phosphorus (Aura)", 12: "Lead (Motus)",
    13: "Iron/Mining", 14: "Heavy Timber/Flora", 15: "Heavy Food/Fauna"
}

RESOURCE_STATS = {
    # {food value, gather cost, is_renewable}
    0:  {"food": 0, "cost": 0, "renew": False},
    13: {"food": 1, "cost": 3, "renew": False}, # Ore/Iron (Hard to get, 0 food)
    14: {"food": 1, "cost": 1, "renew": True},  # Timber (Easy, low food)
    15: {"food": 5, "cost": 2, "renew": True},  # Fauna (Medium, high food)
}

OVERLAYS = {
    0: "Clear / Mundane",
    1: "Mass (Gravity)", 2: "Ordo (Geometry)", 3: "Lex (Law)",
    4: "Flux (Mutation)", 5: "Ratio (Logic)", 6: "Nexus (Arcane)",
    7: "Anumis (Knowledge)", 8: "Omen (Decay)", 9: "Vita (Vitality)",
    10: "Aura (Charm)", 11: "Motus (Velocity)", 12: "Virantor (Fire)",
    13: "Thunderstorm", 14: "Blizzard", 15: "Heatwave",
    16: "Tornado", 17: "Hurricane"  # Dynamic extremes — exist only in RAM
}

def get_overlay_name(overlay_id: int, elevation: float) -> str:
    """Translates the weather overlay into its Terrestrial or Aquatic equivalent."""
    # Extreme rotational systems — same name above or below water
    if overlay_id == 16: return "Tornado"
    if overlay_id == 17:
        return "Underwater Hurricane Current" if elevation <= 0 else "Hurricane"

    # Chaos flows warp reality the same way whether on land or underwater
    if 1 <= overlay_id <= 12:
        return OVERLAYS[overlay_id]

    is_underwater = elevation <= 0

    if overlay_id == 13:
        return "Nutrient Upwelling (Plankton)" if is_underwater else "Thunderstorm"
    if overlay_id == 14:
        return "Abyssal Brine Freeze" if is_underwater else "Blizzard"
    if overlay_id == 15:
        return "Thermal Boiling Current" if is_underwater else "Heatwave"

    return "Clear / Mundane"

def pack_micro_hex(biome: int, faction: int, resource: int, dev_level: int, overlay: int, spark: int, env_q: int = 0) -> int:
    packed = 0
    packed |= (biome & 0xF)
    packed |= (faction & 0xF) << 4
    packed |= (resource & 0xF) << 8
    packed |= (dev_level & 0x7) << 12
    packed |= (overlay & 0xF) << 15
    packed |= (spark & 0x1) << 19
    packed |= (env_q & 0xF) << 20
    return packed

def unpack_micro_hex(state_int: int) -> dict:
    return {
        "biome_id": state_int & 0xF,
        "faction_id": (state_int >> 4) & 0xF,
        "resource_id": (state_int >> 8) & 0xF,
        "dev_level": (state_int >> 12) & 0x7,
        "overlay_id": (state_int >> 15) & 0xF,
        "spark": (state_int >> 19) & 0x1,
        "env_q": (state_int >> 20) & 0xF
    }
