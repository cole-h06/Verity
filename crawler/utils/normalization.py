import json
import os
import re

from config import CATEGORY_STANDARDS, CONVERSIONS, UNIT_SYNONYMS

from openai import OpenAI
from thefuzz import fuzz

from db import (
    get_existing_attributes_for_category
)

client = OpenAI()

CACHE_FILE = "unit_map_cache.json"

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


# retailers serialize units differently ("cu ft", "cu. ft.", "cubic feet"),
# so normalize obvious variants before calling the model again.
def get_standard_unit(raw_unit_word, field_name=None):
    if not raw_unit_word:
        return None

    word = normalize_unit_key(raw_unit_word)

    # fast path for the high-frequency retailer unit variants
    # before falling back to model-based normalization.
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

    # small wording changes here noticeably changed canonicalization behavior
    # across categories, so the prompt stays intentionally rigid.

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
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": json.dumps(keys)
                }
            ],
            temperature=0
        )

        return json.loads(
            response.choices[0].message.content
        )

    except Exception:
        return {}


# reuse previously observed attribute-unit relationships so the
# crawler converges toward stable canonical units over time.
def get_existing_unit_map(category):

    rows = get_existing_attributes_for_category(category)

    unit_map = {}

    for r in rows:

        attr = r["attribute"]
        unit = r["unit"]

        if attr and unit:
            unit_map[attr] = unit

    return unit_map


# stable attribute keys matter because agreement scoring happens
# at the normalized attribute level across independent sources.
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

    return (
        normalize_key(attr),
        normalize_value(value)
    )


# marketplace placeholders and empty retailer values were polluting
# downstream agreement calculations if left unfiltered.
def process_claims(claims):

    results = {}

    for attr, value in claims:

        attr = normalize_key(attr)
        value = normalize_value(value)

        if not attr or not value:
            continue

        if value in (
            "none",
            "null",
            "n/a",
            "na",
            "",
            "not specified"
        ):
            continue

        results[attr] = value

    return [
        (k, v)
        for k, v in results.items()
    ]


# earlier fuzzy merges collapsed unrelated attributes together,
# especially around dimensions, capacity, and power specs.
# I have mostly patched this, but it is still inconsistent.
def merge_similar_keys(
    new_key,
    existing_keys,
    category=None,
    threshold=96
):

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

        score = fuzz.ratio(
            new_key,
            ek_norm
        )

        if score >= threshold:

            print(
                f"[KEY MERGE] "
                f"{new_key} -> "
                f"{ek_norm} ({score})"
            )

            return ek_norm

    return new_key

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

        if candidate_unit:

            normalized_candidate = normalize_unit_key(candidate_unit)

            if normalized_candidate in UNIT_MAP:
                cached = UNIT_MAP[normalized_candidate]

                if cached and cached != "text":
                    return cached

            fast = normalize_unit(normalized_candidate)

            if fast and fast != "text":
                UNIT_MAP[normalized_candidate] = fast
                save_unit_map()
                return fast

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": f"""
You infer the most likely engineering measurement unit implied by a specification label.

- Only infer a numeric unit if the primary semantic meaning of the field is a measurable quantity.
- If numbers appear incidentally inside a descriptive technology name, marketing term, model identifier, resolution string, connectivity standard, or composite text field, return "text".
- "count" should only be used when the specification itself fundamentally represents a discrete quantity.
- Prefer "text" when uncertain.

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