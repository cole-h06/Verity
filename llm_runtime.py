from openai import OpenAI
import json

client = OpenAI()

PILLARS = {
    "laptops": ["cpu_model", "ram_gb", "weight_lbs", "screen_brightness_nits", "battery_wh"],
    "refrigerators": ["capacity_cu_ft", "width_in", "depth_in", "noise_db", "energy_star_certified"],
    "dishwashers": ["noise_db", "width_in", "place_settings", "energy_star_certified"],
    "air_fryers": ["capacity_qt", "wattage", "max_temp_f"],
    "espresso": ["pressure_bar", "tank_capacity_oz", "power_w"]
}

def map_json_ld_to_pillars(json_ld_data: dict, category: str):
    extracted = {}

    if not json_ld_data:
        return extracted

    props = json_ld_data.get("additionalProperty", [])

    for prop in props:
        if not isinstance(prop, dict):
            continue

        name = prop.get("name", "").lower().replace(" ", "_")
        value = prop.get("value")

        if name in PILLARS.get(category, []):
            extracted[name] = value

    return extracted

def extract_relevant_content(markdown: str) -> str:
    if not markdown:
        return ""

    lines = markdown.splitlines()

    keep = []
    capture = False

    for line in lines:
        l = line.lower()

        if any(k in l for k in ["spec", "feature", "detail", "dimension"]):
            capture = True

        if capture:
            keep.append(line)

    if not keep:
        return markdown[:20000]

    return "\n".join(keep)[:20000]

def run_llm_extraction(markdown: str, category: str, existing_data: dict = None):
    pillars = PILLARS.get(category, [])

    cleaned = extract_relevant_content(markdown)

    if not cleaned:
        return {}

    context_msg = f"I already have: {existing_data}. " if existing_data else ""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a technical data extraction engine. {context_msg}"
                        f"Extract missing specifications into a flat JSON object. "
                        f"Prioritize these keys: {pillars}. "
                        f"Normalize units (lbs, inches, watts). "
                        "Use snake_case keys only. Ignore marketing."
                    )
                },
                {
                    "role": "user",
                    "content": cleaned
                }
            ],
            temperature=0
        )

        return json.loads(response.choices[0].message.content)

    except Exception:
        return {}

def get_final_specs(json_ld: dict, markdown: str, category: str):

    final_data = map_json_ld_to_pillars(json_ld, category)

    missing = [p for p in PILLARS.get(category, []) if p not in final_data]

    if missing and markdown:
        llm_data = run_llm_extraction(
            markdown,
            category,
            existing_data=final_data
        )

        if isinstance(llm_data, dict):
            final_data.update(llm_data)

    return final_data