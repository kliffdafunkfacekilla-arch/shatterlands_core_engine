def parse_event(event_dict, elevation):
    """
    Converts raw DB logs into narrative prose, explicitly differentiating:
    - Surface civilization events
    - Sub-surface abyssal events
    - Fluid Chaos Energy fluctuations
    """
    tick = event_dict.get('tick', 0)
    category = event_dict.get('category', 'Unknown')
    message = event_dict.get('message', '')
    q = event_dict.get('global_q', '?')
    r = event_dict.get('global_r', '?')

    is_underwater = elevation <= 0

    prose = ""

    if category == "Chaos":
        # Fluid Chaos Energy fluctuations
        if is_underwater:
            prose = f"[Tick {tick}] 🌀 A fluid Chaos Energy fluctuation surged through the abyssal depths at ({q}, {r}): {message}"
        else:
            prose = f"[Tick {tick}] 🌪️ A localized spell-storm and reality-warping mutation struck the surface at ({q}, {r}): {message}"
    else:
        if is_underwater:
            # Sub-surface abyssal events
            # Translate surface concepts to underwater ones
            translated_message = message.replace("Wood", "Kelp")
            translated_message = translated_message.replace("crop supply failures", "hydrothermal vent resource battles")
            translated_message = translated_message.replace("trade friction", "deep marine faction shifts")
            translated_message = translated_message.replace("settlement growth", "oceanic trench ecosystem collapses")
            translated_message = translated_message.replace("ecology", "oceanic trench ecosystem collapses")

            prose = f"[Tick {tick}] 🌊 In the abyssal depths at ({q}, {r}): {translated_message}"
        else:
            # Surface civilization events
            prose = f"[Tick {tick}] 🏕️ On the surface at ({q}, {r}): {message}"

    return prose
