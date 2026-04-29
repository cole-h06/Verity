from db import get_existing_attributes_for_category
from openai import OpenAI
from thefuzz import fuzz
import json
import os
import re

client = OpenAI()

CACHE_FILE = "unit_map_cache.json"

PILLARS = {
    "laptops": ["cpu_model", "ram_gb", "storage_gb", "weight_lbs", "screen_brightness_nits", "display_resolution", "battery_wh"],
    "headphones": ["driver_type", "frequency_response_hz", "battery_life_hrs", "impedance_ohms", "noise_cancellation"],
    "portable_power": ["capacity_mah", "wattage", "output_ports", "charging_speed_w"],
    "mini_fridges": ["capacity_cu_ft", "refrigerator_capacity_cu_ft", "freezer_capacity_cu_ft", "noise_db", "energy_star_certified"],
    "air_fryers": ["capacity_qt", "basket_material", "wattage", "max_temperature_f"],
    "espresso": ["pump_pressure_bar", "power_w", "heating_system", "water_tank_capacity", "bean_hopper_capacity"]
}

CATEGORY_STANDARDS = {
    "laptops": {
        "weight_lbs": "lb",
        "screen_brightness_nits": "nit",
        "battery_wh": "wh"
    },
    "headphones": {
        "frequency_response_hz": "hz",
        "battery_life_hrs": "hr",
        "impedance_ohms": "ohm"
    },
    "portable_power": {
        "capacity_mah": "mah",
        "wattage": "w",
        "charging_speed_w": "w"
    },
    "mini_fridges": {
        "capacity_cu_ft": "cu_ft",
        "refrigerator_capacity_cu_ft": "cu_ft",
        "freezer_capacity_cu_ft": "cu_ft",
        "noise_db": "db"
    },
    "air_fryers": {
        "capacity_qt": "qt",
        "wattage": "w",
        "max_temperature_f": "f"
    },
    "espresso": {
        "pump_pressure_bar": "bar",
        "power_w": "w",
        "water_tank_capacity": "oz",
        "bean_hopper_capacity": "g"
    }
}

CONVERSIONS = {
    "kg_to_lb": 2.20462,
    "g_to_lb": 0.00220462,
    "lb_to_kg": 0.453592,
    "lb_to_g": 453.592,

    "l_to_oz": 33.814,
    "oz_to_l": 0.0295735,
    "qt_to_oz": 32.0,
    "oz_to_qt": 0.03125,
    "l_to_qt": 1.05669,
    "qt_to_l": 0.946353,
    "oz_to_lb": 0.0625,
    "lb_to_oz": 16.0,

    "mm_to_in": 0.03937,
    "cm_to_in": 0.3937,
    "in_to_mm": 25.4,
    "in_to_cm": 2.54,

    "lb_to_lb": 1.0,
    "in_to_in": 1.0,
    "w_to_w": 1.0,
    "qt_to_qt": 1.0,
    "oz_to_oz": 1.0,
    "l_to_l": 1.0,
}

UNIT_SYNONYMS = {
    "lb": ["lb", "lbs", "pound", "pounds"],
    "in": ["in", "inch", "inches"],
    "ft": ["ft", "feet", "foot"],
    "w": ["w", "watt", "watts"],
    "qt": ["qt", "quart", "quarts"],
    "oz": ["oz", "ounce", "ounces"],
    "l": ["l", "liter", "liters"],
    "g": ["g", "gram", "grams"],
    "kg": ["kg", "kilogram", "kilograms"],
    "bar": ["bar"],
    "cu_ft": ["cu ft", "cu_ft", "cubic ft", "cubic feet", "ft3"],
    "v": ["v", "volt", "volts"],
    "a": ["a", "amp", "amps", "ampere", "amperes"],
    "f": ["f", "fahrenheit", "degrees fahrenheit", "degree fahrenheit"],
    "gb": ["gb", "gigabyte", "gigabytes"],
    "mb": ["mb", "megabyte", "megabytes"],
    "mhz": ["mhz", "megahertz"],
    "ghz": ["ghz", "gigahertz"],
    "percent": ["percent", "%"],
    "nit": ["nit", "nits"],
}


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

    if standardized in UNIT_SYNONYMS:
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
- DO NOT 
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

def normalize_unit_llm(unit_word, field_name=None):
    try:
        context = f"\nField: {field_name}" if field_name else ""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": f"""
You are a unit normalization engine.

TASK:
Convert the given unit into its standard technical abbreviation.

CONTEXT:
The unit comes from a product specification field.

RULES:
- Preserve exact meaning
- Use standard engineering/technical abbreviations when a real measurable unit is present
- Do NOT change measurement type
- If the input is already an abbreviation, keep it
- If the input is clearly a real unit word, abbreviate it
- Prefer technical notation over natural language

EXAMPLES:
- inches → in
- inch → in
- pounds → lb
- lbs → lb
- watts → w
- gigabytes → gb
- megahertz → mhz
- gigahertz → ghz
- percent → percent
- nits → nit

ONLY RETURN "text" IF:
- The input is NOT a measurable unit
- OR it is purely descriptive (e.g., "stainless steel", "digital display")

OUTPUT:
{{ "unit": "..." }}

Unit: {unit_word}
{context}
"""
                }
            ],
            temperature=0
        )

        data = json.loads(res.choices[0].message.content)
        return data.get("unit", "").strip()

    except:
        return "text"

def normalize_unit(u):
    if not u:
        return None

    u = u.lower().strip()
    u = re.sub(r'[^\w\s]', '', u)

    for canonical, variants in UNIT_SYNONYMS.items():
        for v in variants:
            if u == v or u.replace(" ", "") == v.replace(" ", ""):
                return canonical

    return "text"

def run_llm_extraction(markdown: str, category: str, existing_data: dict = None):
    if not markdown:
        return {}

    cleaned = markdown[:60000]

    try:
        system_prompt = (
    f"You are a technical data extraction engine.\n"
    f"Category: {category}\n\n"

    f"TASK:\n"
    f"1. Extract the FULL technical profile of the product from ALL sections of the page.\n"
    f"2. Prioritize the base product specs for the model itself, not example configurations, test setups, or summary tables.\n"
    f"3. Extract these pillar keys whenever present: {PILLARS.get(category, [])}\n"
    f"4. Also extract ALL other valid technical specs as additional snake_case fields.\n"
    f"5. Look through EVERY relevant section, including but not limited to core hardware components, performance characteristics, physical dimensions, materials, power specifications, connectivity, and certifications.\n\n"

    "IMPORTANT RULES:\n"
    "- Do NOT stop after finding a neat summary block or table.\n"
    "- Do NOT return only 'configuration tested' or benchmark/acoustic tables if broader model specs are present.\n"
    "- Prefer the main/base specs for the product over optional upgrades, configurable maximums, or test configurations.\n"
    "- INTERNAL ARCHITECTURE: Extract internal mechanisms, heating systems, control logic, and underlying system types (e.g., controllers, heating elements, compressors, sensors). These are core hardware specs, not marketing.\n"
    "- COMPONENT SPECIFICITY: If a component (e.g., pump, motor, portafilter, compressor) has a size, material, type, or architecture, capture the FULL detail.\n"
    "- COMPONENT GRANULARITY: Extract specific internal technologies, heating methods, control systems, and underlying mechanisms. If a component has a defined type, architecture, or size (e.g., mm, bar, wattage, system type), it MUST be extracted as its own field.\n"
    "- If both base and max/configurable values are present, keep the base/current spec in the main field and use a separate field for max/configurable only if clearly useful.\n"
    "- Multi-line sections must be grouped correctly.\n"
    "- Certifications that describe durability, efficiency, or compliance count as technical claims.\n"
    "- Model number and UPC/EAN count as technical claims when present.\n"
    "- SECTION CONTEXT: If a value appears under a section header (e.g., 'Storage', 'Display'), treat the header as the label.\n"
    "- REASSEMBLE LABELED DATA: If a value appears next to a label (e.g., 'Weight: X', 'Height: X'), extract it correctly.\n"
    "- CAPTURE RAW CONTEXT: Always include the exact snippet where the value appears as raw_quote.\n"
    "- EXHAUSTIVE SCAN: You must scan the entire document. Physical specs like weight and dimensions are often near the end.\n"
    "- ASSEMBLY PERMISSION: You are allowed to link a value to a nearby label. If a label and value are adjacent (even on separate lines), treat them as direct evidence.\n\n"

    "INCLUDE:\n"
    "- Physical dimensions (height, width, depth, weight)\n"
    "- Performance metrics (speed, wattage, capacity, battery)\n"
    "- Hardware components (chips, drivers, motors, materials)\n"
    "- Connectivity (wifi, bluetooth, ports)\n"
    "- Certifications (ip rating, energy star, compliance standards)\n\n"

    "EXCLUDE:\n"
    "- Price, discounts, financing\n"
    "- Ratings, reviews\n"
    "- Warranty, support plans, services\n"
    "- Marketing copy, sales copy, and generic promotional language\n"
    "- Accessibility feature lists, bundled apps, and in-the-box lists unless they contain true hardware specs\n\n"

    f"PILLAR MAPPING:\n"
    f"- Map to these keys when possible: {PILLARS.get(category, [])}\n"
    "- Example: 'brightness' -> 'screen_brightness_nits'\n"
    "- Example: 'battery capacity' -> 'battery_wh'\n\n"

    "STRICT:\n"
    "- EVIDENCE LOCK: Only extract values explicitly present in the provided text.\n"
    "- VERACITY: If a spec is not directly stated, DO NOT infer or use prior knowledge.\n"
    "- NO GUESSING: Do not fill missing fields with typical or expected values.\n"
    "- DATA FIDELITY: You are a technical mirror. If the text states a value (e.g., '15 bar'), you MUST extract that exact value. Never correct, normalize, or override values using prior knowledge.\n"
    "- UNIT PRESERVATION: If a value includes a unit (e.g., '67 oz', '1/2 lb', '22.09 lbs'), you MUST include the unit in the value string.\n"
    "- NEVER strip units from numeric values.\n"
    "- The value field must contain the FULL original measurement (number + unit).\n"
    "- COMPONENT RECOGNITION: Treat capitalized technical terms (e.g., 'Thermocoil', 'PID Control', 'Neural Engine') as real hardware components. Extract them as separate snake_case fields.\n"
    "- EMPTY STATE: If no valid technical specs are found, return an empty JSON object {}.\n"
    "- raw_quote must reflect the closest label-value pairing, even if reconstructed from adjacent lines.\n"
    "- QUOTE FALLBACK: If no explicit label exists, you may use the closest bullet point or line as the raw_quote.\n"
    "- RAW QUOTE RULE: The raw_quote should combine the label and value (e.g., 'Weight: 2.7 pounds'). If they appear on separate lines, you may combine them to reflect the relationship.\n"
    "- STRUCTURAL EVIDENCE: Labels and nearby values in tables or lists count as valid evidence, even if not in full sentences.\n"
    "- LIST EXTRACTION: Bullet lists under a section header inherit that header as context (e.g., under 'Storage', '256GB SSD' is valid evidence).\n"
    "- Do NOT hallucinate\n"
    "- Do NOT skip major sections\n"
    "- Do NOT output placeholders like 'not specified', 'none', or null-like filler values\n\n"

    "FORMAT:\n"
    "Return JSON like this:\n"
    "{\n"
    '  "field_name": {\n'
    '    "value": "...",\n'
    '    "raw_quote": "..."\n'
    "  }\n"
    "}\n"
)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": cleaned}
            ],
            temperature=0
        )

        return json.loads(response.choices[0].message.content)

    except Exception:
        return {}

def translate_specs(raw_specs: dict, category: str):
    system_prompt = (
        f"You are a technical parsing engine for the category: {category}.\n\n"

        "TASK:\n"
        "Extract structured numeric values and their ORIGINAL units from raw specification strings.\n"
        "CRITICAL: You MUST preserve the EXACT field names as provided.\n"
        "DO NOT rename, shorten, or modify keys in any way.\n"
        "DO NOT perform any math. DO NOT convert units.\n"
        "DO NOT normalize or abbreviate units.\n\n"

        "OUTPUT FORMAT (JSON ONLY):\n"
        "{\n"
        '  "field_name": {\n'
        '    "value": number_or_object,\n'
        '    "unit": "unit_exactly_as_written_or_text",\n'
        '    "display": "original_full_string"\n'
        '  }\n'
        "}\n\n"

        "IMPORTANT:\n"
        "- The output keys MUST exactly match the input keys.\n"
        "- If input key is 'pump_pressure_bar', output key MUST be 'pump_pressure_bar'.\n"
        "- NEVER change key names.\n\n"

        "RULES:\n"
        "1. If a number and unit are present:\n"
        "   - Extract the numeric portion as value\n"
        "   - Extract the unit EXACTLY as written in the text (NO abbreviation)\n"
        "   Examples:\n"
        "   - '64 gigabytes' → value: 64, unit: 'gigabytes'\n"
        "   - '0.72 inches' → value: 0.72, unit: 'inches'\n"
        "   - '45 watts' → value: 45, unit: 'watts'\n\n"

        "2. If a measurable unit exists, you MUST extract it exactly as written.\n\n"

        "3. Only use unit = \"text\" if there is NO measurable unit present.\n\n"

        "4. Ranges → {\"min\": X, \"max\": Y}\n\n"

        "5. Multi-state → {\"state\": value}\n\n"

        "6. Multi-value measurements (e.g., dimensions like '12 x 8 x 2 inches'):\n"
        "   - Keep FULL original string as value\n"
        "   - STILL extract the unit exactly as written (e.g., 'inches')\n\n"

        "7. No math, no conversion, no normalization\n\n"

        "8. display MUST contain the full original string\n"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(raw_specs)}
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

def map_structured_specs(product_json, category):
    raw_props = product_json.get("additionalProperty", [])

    props = []

    if isinstance(raw_props, dict):
        if isinstance(raw_props.get("value"), list):
            props = raw_props["value"]

    elif isinstance(raw_props, list):
        for p in raw_props:
            if isinstance(p, dict) and isinstance(p.get("value"), list):
                props.extend(p["value"])
            else:
                props.append(p)

    input_data = []

    for p in props:
        if not (isinstance(p, dict) and p.get("name") and p.get("value")):
            continue

        val = p.get("value")

        if isinstance(val, list):
            val = ", ".join([str(v) for v in val if v])

        input_data.append({
            "name": p.get("name"),
            "value": val
        })

    if not input_data:
        return []

    system_prompt = """
You are a structured data extractor.

TASK:
Extract ALL specification label-value pairs exactly as they appear.

RULES:
- DO NOT normalize keys
- DO NOT modify labels
- DO NOT convert to snake_case
- Preserve original label text EXACTLY
- Extract numeric value if clearly present
- Extract unit if clearly present
- If not numeric → value_numeric = null and unit = "text"
- DO NOT drop anything

OUTPUT FORMAT:
{
  "mapped": [
    {
      "key": "ORIGINAL LABEL EXACTLY",
      "display": "FULL ORIGINAL VALUE",
      "value_numeric": number_or_null,
      "unit": "unit_or_text"
    }
  ]
}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(input_data)}
            ],
            temperature=0
        )

        parsed = json.loads(response.choices[0].message.content)

        mapped = []

        for i in parsed.get("mapped", []):
            if not (i.get("key") and i.get("display") and i.get("unit")):
                continue

            raw_key = i["key"].lower().strip()

            if raw_key == "text":
                raw_key = i["display"]

            raw_key = raw_key.encode("ascii", "ignore").decode()

            key = i["key"]

            unit = get_standard_unit(i["unit"], key)

            val = i.get("value_numeric")

            if not isinstance(val, (int, float)):
                val = None

            mapped.append((
                key,
                {
                    "display": i["display"],
                    "math": val,
                    "unit": unit
                }
            ))

        return mapped

    except Exception:
        return []

def normalize_specs(raw_claims, category):
    standards = CATEGORY_STANDARDS.get(category, {})

    parsed = {}

    for k, v in raw_claims:

        if isinstance(v, dict):
            parsed[k] = {
                "value": v.get("math"),
                "display": v.get("display"),
                "unit": v.get("unit") or "text"
            }
            continue

        parsed[k] = {
            "value": None,
            "unit": "text",
            "display": str(v)
        }

    normalized = []

    for attr, data in parsed.items():
        print("\n--- NORMALIZING ---")
        print("FIELD:", attr)
        print("RAW:", data)

        attr = normalize_key(attr)

        target_unit = standards.get(attr)

        display = data.get("display")
        value = data.get("value")
        unit = data.get("unit")

        print("PARSED VALUE:", value)
        print("PARSED UNIT:", unit)
        print("TARGET UNIT:", target_unit)

        if isinstance(value, dict):
            for sub_key, sub_val in value.items():

                sub_unit = unit

                if (not unit or unit == "text") and target_unit and display:
                    display_lower = display.lower()

                    if any(u in display_lower for u in UNIT_SYNONYMS.get(target_unit, [])):
                        sub_unit = target_unit

                normalized.append((
                    f"{attr}_{sub_key}",
                    {
                        "display": f"{sub_val}",
                        "math": sub_val,
                        "unit": sub_unit,
                        "source_unit": unit
                    }
                ))
            continue
        else:
            base_value = value

        math_value = base_value

        if isinstance(base_value, dict):
            if target_unit and unit != target_unit:
                key = f"{unit}_to_{target_unit}"
                factor = CONVERSIONS.get(key)

                if factor:
                    math_value = {
                        "min": round(base_value.get("min") * factor, 2),
                        "max": round(base_value.get("max") * factor, 2)
                    }

        elif isinstance(base_value, (int, float)):
            if target_unit and unit != target_unit:
                key = f"{unit}_to_{target_unit}"
                factor = CONVERSIONS.get(key)

                if factor:
                    math_value = round(base_value * factor, 2)

        print("FINAL MATH:", math_value)
        print("DISPLAY:", display)

        final_unit = unit

        if (not unit or unit == "text") and target_unit:
            if isinstance(math_value, (int, float)) and display:
                display_lower = display.lower()

                if any(u in display_lower for u in UNIT_SYNONYMS.get(target_unit, [])):
                    final_unit = target_unit

        normalized.append((
            attr,
            {
                "display": display,
                "math": math_value,
                "unit": final_unit,
                "source_unit": unit
            }
        ))

    return normalized

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

def merge_similar_keys(new_key, existing_keys, threshold=90):
    new_key = new_key.lower().strip()

    if new_key in existing_keys:
        return new_key

    best_match = None
    best_score = 0

    for ek in existing_keys:
        score = fuzz.token_set_ratio(new_key, ek)
        if score > best_score:
            best_score = score
            best_match = ek

    if best_score >= threshold:
        return best_match

    for ek in existing_keys:
        if new_key.replace("_", "") == ek.replace("_", ""):
            return ek

    return new_key

def map_to_pillars(raw_key, category, existing_keys):
    raw = normalize_key(raw_key)

    pillars = PILLARS.get(category, [])

    best_match = None
    best_score = 0

    for p in pillars:
        score = fuzz.token_set_ratio(raw, p)
        if score > best_score:
            best_score = score
            best_match = p

    if best_score >= 80:
        return best_match

    return raw

def process_product(product_json, markdown, category, skip_llm=False, structured_input=None):

    claims = []
    raw_keys = []

    existing_keys = get_existing_attributes_for_category(category)
    if structured_input:
        raw_structured_specs = {normalize_key(k): v for k, v in structured_input}
        for k in raw_structured_specs.keys():
            raw_keys.append(k)
        translated_structured = translate_specs(raw_structured_specs, category) if raw_structured_specs else {}

        for k, v in raw_structured_specs.items():
            translated_item = translated_structured.get(normalize_key(k), {})
 
            val = translated_item.get("value")

            if isinstance(val, (int, float)):
                math_val = val
            elif isinstance(val, str):
                try:
                    math_val = float(val)
                except:
                    math_val = None
            else:
                math_val = None

            unit_raw = translated_item.get("unit")
            unit_val = get_standard_unit(unit_raw, k)

            mapped_key = map_to_pillars(k, category, existing_keys)

            claims.append((
                mapped_key,
                {
                    "display": translated_item.get("display") or v,
                    "math": math_val,
                    "unit": unit_val
                }
            ))

    if product_json:
        mapped_claims = map_structured_specs(product_json, category)
  
        for k, data in mapped_claims:
            raw_keys.append(k)
            claims.append((k, data))

    if not skip_llm and markdown:
        llm_output = run_llm_extraction(markdown, category=category, existing_data=None)

        flat_llm_specs = {}

        if isinstance(llm_output, dict):
            for key, data in llm_output.items():
                if isinstance(data, dict):
                    value = data.get("value")
                    if value:
                        flat_llm_specs[key] = value

        translated_llm = translate_specs(flat_llm_specs, category) if flat_llm_specs else {}

        if isinstance(llm_output, dict):
            for key, data in llm_output.items():
                if not isinstance(data, dict):
                    continue

                value = data.get("value")
                if not value:
                    continue

                normalized_key = normalize_key(key)

                if normalized_key == key and "_" in key:
                    final_key = normalized_key
                else:
                    final_key = map_to_pillars(key, category, existing_keys)

                translated_item = (
                    translated_llm.get(key)
                    or translated_llm.get(normalize_key(key))
                    or {}
                )

                val = translated_item.get("value")

                if isinstance(val, (int, float)):
                    math_value = val
                elif isinstance(val, str):
                    try:
                        math_value = float(val)
                    except:
                        math_value = None
                else:
                    math_value = None

                raw_unit = translated_item.get("unit")
                unit_value = get_standard_unit(raw_unit, final_key)

                display_value = translated_item.get("display") or value
 
                claims.append((
                    final_key,
                    {
                        "display": display_value,
                        "math": math_value,
                        "unit": unit_value
                    }
                ))
                raw_keys.append(final_key)

    print("\n===== RAW CLAIMS =====")
    for c in claims:
        print(c)

    print("TOTAL CLAIMS:", len(claims))

    cleaned_keys = [normalize_key(k) for k in raw_keys]
    key_map = normalize_keys(list(dict.fromkeys(cleaned_keys)))

    normalized_claims = []

    for attr, data in claims:
        lookup = attr
        if lookup not in key_map:
            lookup = normalize_key(attr)

        new_key = key_map.get(lookup, normalize_key(attr))
        normalized_claims.append((new_key, data))

    final = normalized_claims

    raw_for_normalization = []

    for attr, data in final:
        raw_for_normalization.append((attr, data))

    normalized = normalize_specs(raw_for_normalization, category)
    return normalized