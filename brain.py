from db import get_existing_attributes_for_category
from openai import OpenAI
from thefuzz import fuzz
import json
import os
import re

client = OpenAI()

CACHE_FILE = "unit_map_cache.json"

PILLARS = {
    "laptops": ["cpu_model", "ram_gb", "storage_gb", "weight_lb", "screen_brightness_nit", "display_resolution", "battery_life_hr"],
    "headphones": ["driver_type", "frequency_response_hz", "battery_life_hr", "impedance_ohms", "noise_cancellation"],
    "portable_power": ["capacity_mah", "power_w", "output_ports", "charging_speed_w"],
    "mini_fridges": ["total_capacity_cu_ft", "refrigerator_capacity_cu_ft", "freezer_capacity_cu_ft", "noise_db", "energy_star_certified"],
    "air_fryers": ["capacity_qt", "basket_material", "power_w", "max_temperature_f"],
    "espresso": ["pump_pressure_bar", "power_w", "heating_system", "water_tank_capacity_oz"]
}

def clean_price(p):
    if not p:
        return None
    p = str(p)
    p = re.sub(r"[^\d.]", "", p)
    try:
        return float(p)
    except Exception:
        return None

def get_pillar_count(structured, category):
    pillar_keys = PILLARS.get(category, [])
    return sum(1 for k, _ in structured if k in pillar_keys)

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        UNIT_MAP = json.load(f)
else:
    UNIT_MAP = {}

def save_unit_map():
    with open(CACHE_FILE, "w") as f:
        json.dump(UNIT_MAP, f, indent=2)

def normalize_unit_key(text):
    text = text.lower()
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()

def get_standard_unit(raw_unit_word, field_name=None):
    if not raw_unit_word:
        return None

    word = normalize_unit_key(raw_unit_word)

    fast = normalize_unit(word)
    if fast and fast != "text":
        UNIT_MAP[word] = fast
        save_unit_map()
        return fast
   
    if word in UNIT_MAP and UNIT_MAP[word] != "text":
        return UNIT_MAP[word]

    standardized = normalize_unit_llm(word, field_name)
    standardized = standardized.lower().strip()

    if len(standardized) == 0:
        standardized = "text"

    if standardized != "text":
        UNIT_MAP[word] = standardized
        save_unit_map()

    return standardized

def normalize_keys(keys: list[str]):
    if not keys:
        return {}

    system_prompt = """
You are a strict key normalizer.

TASK:
Convert each input label into a clean, consistent snake_case key.

RULES:
- Preserve meaning exactly (DO NOT merge concepts)
- If multiple keys represent the same concept, normalize them to the SAME output key
- DO NOT map to a fixed schema
- DO NOT generalize
- Convert units into suffixes (e.g., '_in', '_cu_ft', '_w')
- Remove punctuation
- Use lowercase
- Use underscores only
- Deterministic output

OUTPUT FORMAT:
{
  "original_key": "normalized_key"
}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(keys)}
            ],
            temperature=0
        )

        return json.loads(response.choices[0].message.content)

    except Exception:
        return {}

def get_existing_unit_map(category):
    rows = get_existing_attributes_for_category(category)

    unit_map = {}

    for r in rows:
        attr = r["attribute"]
        unit = r["unit"]

        if attr and unit:
            unit_map[attr] = unit

    return unit_map

def normalize_key(key):
    key = key.lower().strip()
    key = re.sub(r"[^\w\s]", "", key)
    key = key.replace(" ", "_")
    return key

def normalize_value(value):
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).lower().strip()

def normalize_claim(attr, value):
    return normalize_key(attr), normalize_value(value)

def process_claims(claims):
    results = {}

    for attr, value in claims:
        attr = normalize_key(attr)
        value = normalize_value(value)

        if not attr or not value:
            continue

        if value in ("none", "null", "n/a", "na", "", "not specified"):
            continue

        results[attr] = value

    return [(k, v) for k, v in results.items()]

def merge_similar_keys(new_key, existing_keys, category=None, threshold=96):

    new_key = normalize_key(new_key)

    candidate_keys = set(existing_keys)

    if new_key in candidate_keys:
        return new_key

    compressed_new = new_key.replace("_", "")

    for ek in candidate_keys:

        ek_norm = normalize_key(ek)

        if ek_norm == new_key:
            return ek_norm

        if ek_norm.replace("_", "") == compressed_new:
            return ek_norm

        score = fuzz.ratio(new_key, ek_norm)

        if score >= threshold:
            print(f"[KEY MERGE] {new_key} -> {ek_norm} ({score})")
            return ek_norm

    return new_key