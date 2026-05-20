import json
import os
import re

from openai import OpenAI
from thefuzz import fuzz

from db import (
    get_existing_attributes_for_category
)

from llm.unit_normalizer import (
    normalize_unit,
    normalize_unit_llm
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