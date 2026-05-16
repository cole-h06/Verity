from db import get_existing_attributes_for_category
from config import CATEGORY_STANDARDS, CONVERSIONS, UNIT_SYNONYMS
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

def map_keys_to_pillars(keys, category):

    pillars = PILLARS.get(category, [])

    if not keys or not pillars:
        return {
            normalize_key(k): normalize_key(k)
            for k in keys
        }

    try:

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": f"""
You are a semantic ontology mapper.

TASK:
Map retailer specification LABEL-VALUE PAIRS to a canonical pillar key ONLY when the measured object is explicitly clear.

A generic label like:
- capacity
- pressure
- power
- size
- dimensions

is NOT enough by itself.

You must see explicit contextual evidence in either:
- the label
- or the value

before mapping to a subsystem-specific pillar.
If ambiguity exists, preserve the original generic meaning.
If semantic meaning is ambiguous, preserve the original normalized key instead of forcing a pillar mapping.
Do NOT infer hidden meaning from generic labels.
Preserve ambiguity when context is insufficient.

CATEGORY:
{category}

ALLOWED CANONICAL KEYS:
{pillars}

RULES:
- Canonical pillar keys may contain naming suffixes related to units,
  schema conventions, or representation format.
- These suffixes do NOT change the underlying semantic meaning.
- Determine equivalence based on the underlying physical quantity and concept,
  not literal token overlap.
- A retailer field may omit unit/type suffixes while still matching
  a more specific canonical pillar key.
- Preserve ambiguity ONLY when the underlying measured concept itself is unclear.

Examples:
- battery life hours != battery watt hours
- dimensions != weight
- storage capacity != RAM
- processor speed != processor model
- processor model == cpu_model
- screen size != resolution

- If the retailer label measures a DIFFERENT physical quantity,
  you MUST preserve the original normalized key.

- Never map based on shared topic words alone.
- Preserve meaning exactly
- If no pillar matches, keep the normalized original key
- Return ONLY valid JSON
- Keys must be snake_case

OUTPUT:
{{
  "retailer_key": "canonical_key"
}}
"""
                },
                {
                    "role": "user",
                    "content": json.dumps(keys)
                }
            ],
            temperature=0
        )

        raw = json.loads(response.choices[0].message.content)
        print("\n=== SEMANTIC MAP RAW ===")
        print(json.dumps(raw, indent=2))

        cleaned = {}

        for item in keys:

            if isinstance(item, dict):
                original_key = item["normalized_key"]
            else:
                original_key = normalize_key(item)

            mapped = raw.get(original_key, original_key)

            nk = normalize_key(original_key)
            nv = normalize_key(mapped)
 
            if nv not in [normalize_key(p) for p in pillars]:
                nv = nk

            cleaned[nk] = nv

        return cleaned

    except Exception as e:

        print("[PILLAR MAP ERROR]", e)

        return {
            normalize_key(k): normalize_key(k)
            for k in keys
        }

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

def infer_unit(label, candidate_unit=None):

    try:

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": f"""
You infer the most likely engineering measurement unit implied by a specification label.

RULES:
- Return ONLY a standard abbreviated unit
- Examples of valid outputs: w, v, a, oz, lb, in, mm, bar, qt, cu_ft
- If the label implies a dimensionless quantitative count
  (e.g. number of cores, number of ports, speaker count),
  return "count"

- Return "text" ONLY when the field is purely descriptive
  and not quantitatively measurable
- Do not explain
- Do not return full words
- Output valid JSON only

OUTPUT FORMAT:
{{
  "unit": "..."
}}

LABEL:
{label}
"""
                }
            ],
            temperature=0
        )

        data = json.loads(res.choices[0].message.content)

        unit = data.get("unit", "text").strip().lower()

        if unit and unit != "text":
            UNIT_MAP[candidate_unit.lower().strip()] = unit
            save_unit_map()
            return unit

        return "text"

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
    f"1. Extract only technical specifications explicitly supported by the source text.\n"
    f"2. Prioritize the base product specs for the model itself, not example configurations, test setups, or summary tables.\n"
    f"3. Also extract ALL other valid technical specs as additional snake_case fields.\n"
    f"4. Look through EVERY relevant section, including but not limited to core hardware components, performance characteristics, physical dimensions, materials, power specifications, connectivity, and certifications.\n\n"

    "IMPORTANT RULES:\n"
    "- Do NOT stop after finding a neat summary block or table.\n"
    "- Do NOT return only 'configuration tested' or benchmark/acoustic tables if broader model specs are present.\n"
    "- Prefer the main/base specs for the product over optional upgrades, configurable maximums, or test configurations.\n"
    "- If both base and max/configurable values are present, keep the base/current spec in the main field and use a separate field for max/configurable only if clearly useful.\n"
    "- Multi-line sections must be grouped correctly.\n"
    "- Certifications that describe durability, efficiency, or compliance count as technical claims.\n"
    "- IDENTITY EXTRACTION (CRITICAL):\n"
    "- Extract ONLY the following identifiers:\n"
    "- model\n"
    "- gtin (includes UPC, EAN, GTIN)\n"
    "- These identifiers are NOT optional and must ALWAYS be extracted when present.\n"
    "- They may appear in titles, bullets, or product information sections.\n"
    "- Always scan the FULL document for them.\n"
    "- Treat identifiers as FIRST-CLASS fields.\n"
    "- Output using these exact keys:\n"
    "  - model\n"
    "  - gtin\n"
    "- MAPPING RULES:\n"
    "  - UPC → gtin\n"
    "  - EAN → gtin\n"
    "  - GTIN → gtin\n"
    "- FORMAT REQUIREMENTS:\n"
    "  - gtin must be a 12–14 digit numeric code\n"
    "  - model must be the exact model number as written\n"
    "- Return identifiers even if no other specs are found.\n"
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

    "STRICT:\n"
    "- MISSING DATA RULE:\n"
    "- If a specification is not explicitly present in the source text, OMIT THE FIELD ENTIRELY.\n"
    "- Do NOT output placeholders such as:\n"
    "- 'Not specified'\n"
    "- 'Unknown'\n"
    "- 'N/A'\n"
    "- 'None'\n"
    "- 'Unavailable'\n"
    "- inferred negatives\n"
    "- estimated values\n"
    "- A missing specification must be omitted from the JSON completely.\n\n"
    "- SCHEMA VALIDITY:\n"
    "- Any field whose value is missing, unknown, unavailable, null-like, inferred absent, or unspecified is INVALID and MUST NOT appear in the JSON.\n"
    "- A placeholder value is considered schema-invalid output.\n"
    "- If a specification is absent, the entire field must be omitted completely.\n"
    "- Never represent missingness as a claim.\n\n"
    "- EVIDENCE LOCK: Only extract values explicitly present in the provided text.\n"
    "- VERACITY: If a spec is not directly stated, DO NOT infer or use prior knowledge.\n"
    "- NO GUESSING: Do not fill missing fields with typical or expected values.\n"
    "- DATA FIDELITY: You are a technical mirror. If the text states a value (e.g., '15 bar'), you MUST extract that exact value. Never correct, normalize, or override values using prior knowledge.\n"
    "- UNIT PRESERVATION: If a value includes a unit (e.g., '67 oz', '1/2 lb', '22.09 lbs'), you MUST include the unit in the value string.\n"
    "- NEVER strip units from numeric values.\n"
    "- The value field must contain the FULL original measurement (number + unit).\n"
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
- If the value is numeric but the unit is omitted,
  infer the most likely engineering unit from the specification label
- Only infer units when the label clearly implies a standard measurable unit

Examples:
- Wattage -> watts
- Voltage -> volts
- Amperage -> amps
- Pressure -> bar
- Capacity -> ounces

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
        source_label = data.get("source_label", "")

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
        final_unit = unit

        if isinstance(base_value, dict):
            if target_unit and unit != target_unit:
                key = f"{unit}_to_{target_unit}"
                factor = CONVERSIONS.get(key)

                if factor:
                    math_value = {
                        "min": round(base_value.get("min") * factor, 2),
                        "max": round(base_value.get("max") * factor, 2)
                    }
                    final_unit = target_unit

        elif isinstance(base_value, (int, float)):
            if target_unit and unit != target_unit:
                key = f"{unit}_to_{target_unit}"
                factor = CONVERSIONS.get(key)

                if factor:
                    math_value = round(base_value * factor, 2)
                    final_unit = target_unit

        print("FINAL MATH:", math_value)
        print("DISPLAY:", display)

        if not final_unit:
            final_unit = unit

        context_text = f"{source_label} {display}".lower()

        if (not unit or unit == "text") and target_unit:
            if isinstance(math_value, (int, float)):

                if any(
                    u in context_text
                    for u in UNIT_SYNONYMS.get(target_unit, [])
                ):
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

def merge_similar_keys(new_key, existing_keys, category=None, threshold=96):

    new_key = normalize_key(new_key)

    candidate_keys = set(existing_keys)

    if category in PILLARS:
        candidate_keys.update(
            [normalize_key(x) for x in PILLARS[category]]
        )

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

def process_product(
    product_json,
    markdown,
    category,
    skip_llm=False,
    structured_input=None,
    heuristic_mode=False
):

    claims = []
    raw_keys = []

    structured_mode = bool(structured_input)

    existing_keys = get_existing_attributes_for_category(category)

    existing_normalized = [
        normalize_key(x["attribute"])
        for x in existing_keys
        if x.get("attribute")
    ]

    if structured_input:

        raw_structured_specs = {}

        for item in structured_input:

            if isinstance(item, dict):
                label = item.get("source_label")
                value = item.get("source_value")
            else:
                label, value = item

            if not label or value is None:
                continue

            raw_structured_specs[normalize_key(label)] = {
                "display": str(value).strip(),
                "source_label": label
            }

        mapping_inputs = []

        for k, payload in raw_structured_specs.items():
            mapping_inputs.append({
                "normalized_key": normalize_key(payload["source_label"]),
                "source_label": payload["source_label"],
                "value": payload["display"]
            })

        semantic_map = map_keys_to_pillars(
            mapping_inputs,
            category
        )

        for k, payload in raw_structured_specs.items():

            raw_keys.append(k)

            source_lookup_key = normalize_key(payload["source_label"])

            normalized_key = semantic_map.get(
                source_lookup_key,
                normalize_key(k)
            )
            print(f"[SEMANTIC MAP] {k} -> {normalized_key}")

            if normalized_key in PILLARS.get(category, []):
                final_key = normalized_key
            else:
                final_key = merge_similar_keys(
                    normalized_key,
                    existing_normalized,
                    category=category
                )

            display = payload["display"]

            math_val = None
            unit_val = "text"

            measurement_source = f"{payload['source_label']} {display}"

            measurement_match = None

            if heuristic_mode or structured_mode:

                measurement_match = re.search(
                    r"(-?(?:\d*\.\d+|\d+))\s*(?:\(|\[)?([a-zA-Z%]+)(?:\)|\])?",
                    measurement_source
                )

                if not measurement_match:

                    label_unit_match = re.search(
                        r"\(([^()]+)\)",
                       payload["source_label"]
                    )

                    if label_unit_match:

                        candidate_unit = label_unit_match.group(1)

                        number_match = re.search(
                            r"-?(?:\d*\.\d+|\d+)",
                            display
                        )

                        if number_match:

                            candidate_number = number_match.group(0)
    
                            measurement_match = (
                                candidate_number,
                                candidate_unit
                            )

            if measurement_match:

                if isinstance(measurement_match, tuple):
                    candidate_number, candidate_unit = measurement_match
                else:
                    candidate_number = measurement_match.group(1)
                    candidate_unit = measurement_match.group(2)

                standardized = get_standard_unit(candidate_unit, final_key)

                if standardized == "text":
                    standardized = None

                if standardized:
                    try:
                        math_val = float(candidate_number)
                        unit_val = standardized
                    except:
                        pass

            if math_val is None:

                number_match = re.search(
                    r"-?(?:\d*\.\d+|\d+)",
                    display
                )

                target_unit = CATEGORY_STANDARDS.get(category, {}).get(final_key)

                if number_match and target_unit:

                    try:
                        math_val = float(number_match.group(0))
                        unit_val = target_unit
                    except:
                        pass

                elif number_match:

                    candidate_unit = re.sub(
                        r"[-+]?\d*\.?\d+",
                        "",
                        display
                    ).strip()

                    inferred_unit = infer_unit(
                        payload["source_label"],
                        candidate_unit
                    )

                    if inferred_unit and inferred_unit != "text":

                        try:
                            math_val = float(number_match.group(0))
                            unit_val = inferred_unit
                        except:
                            pass

            claims.append((
                final_key,
                {
                    "display": display,
                    "math": math_val,
                    "unit": unit_val,
                    "source_label": payload["source_label"]
                }
            ))

    if product_json:
        mapped_claims = map_structured_specs(product_json, category)
  
        mapping_inputs = []

        for k, data in mapped_claims:

            mapping_inputs.append({
                "normalized_key": normalize_key(k),
                "source_label": k,
                "value": data.get("display")
            })
 
        semantic_map = map_keys_to_pillars(
            mapping_inputs,
            category
        )

        for k, data in mapped_claims:

            source_lookup_key = normalize_key(k)

            normalized_key = semantic_map.get(
                source_lookup_key,
                normalize_key(k)
            )

            if normalized_key in PILLARS.get(category, []):
                final_key = normalized_key
            else:
                final_key = merge_similar_keys(
                    normalized_key,
                    existing_normalized,
                    category=category
                )

            raw_keys.append(final_key)
    
            claims.append((final_key, data))

    if not skip_llm and markdown and not structured_mode:
        llm_output = run_llm_extraction(markdown, category=category, existing_data=None)

        filtered_llm_specs = {}

        if isinstance(llm_output, dict):
            for key, data in llm_output.items():

                if not isinstance(data, dict):
                    continue

                value = data.get("value")

                if not value:
                    continue

                value_text = str(value).strip().lower()

                if any(x in value_text for x in [
                    "not specified",
                    "unknown",
                    "n/a",
                    "unavailable",
                    "not available",
                    "none"
                ]):
                    continue

                filtered_llm_specs[key] = value

        translated_llm = (
            translate_specs(filtered_llm_specs, category)
            if filtered_llm_specs else {}
        )

        if isinstance(llm_output, dict):
            for key, data in llm_output.items():
                if not isinstance(data, dict):
                    continue

                value = data.get("value")
                if not value:
                    continue

                value_text = str(value).strip().lower()

                if any(x in value_text for x in [
                    "not specified",
                    "unknown",
                    "n/a",
                    "unavailable",
                    "not available",
                    "none"
                ]): 
                    continue

                normalized_key = normalize_key(key)

                semantic_map = map_keys_to_pillars(
                    [{
                        "normalized_key": normalized_key,
                        "source_label": key,
                        "value": value
                    }],
                    category
                )

                normalized_key = semantic_map.get(
                    normalized_key,
                    normalized_key
                )

                if normalized_key == key and "_" in key:
                    final_key = normalized_key
                else:
                    final_key = merge_similar_keys(
                        normalized_key,
                        existing_normalized,
                        category=category
                    )

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

    final = []

    for attr, data in claims:

        normalized_key = normalize_key(attr)

        canonical_key = merge_similar_keys(
            normalized_key,
            existing_normalized,
            category=category
        )

        final.append((canonical_key, data))

    raw_for_normalization = []

    for attr, data in final:
        raw_for_normalization.append((attr, data))

    normalized = normalize_specs(raw_for_normalization, category)
    return normalized