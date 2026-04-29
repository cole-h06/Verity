from __future__ import annotations
import re
from typing import List, Dict


MODEL_PATTERNS = [
    r"\b[A-Z0-9]{4,}-[A-Z0-9]{2,}\b",
    r"\b[A-Z0-9]{6,}/[A-Z0-9]{2,}\b",
    r"\b[A-Z0-9]{5,}\b"
]


def normalize_token(token: str) -> str:
    if not token:
        return ""

    t = token.strip().upper()

    # unify separators
    t = t.replace("/", "-")

    # remove all non-alphanumeric for matching layer
    t = re.sub(r"[^A-Z0-9]", "", t)

    return t


def extract_identity_tokens(html: str) -> List[Dict]:
    tokens = set()

    for pattern in MODEL_PATTERNS:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for m in matches:
            tokens.add(m)

    results = []

    for raw in tokens:
        normalized = normalize_token(raw)

        if not normalized:
            continue

        results.append({
            "token": raw,
            "token_type": "model",
            "normalized_token": normalized
        })

    return results


# -------------------------------------------------------
# MODEL MATCHING (PHASE 1 CORE)
# -------------------------------------------------------

def is_model_alias(a: str, b: str) -> bool:
    if not a or not b:
        return False

    a_norm = normalize_token(a)
    b_norm = normalize_token(b)

    if not a_norm or not b_norm:
        return False

    # exact match
    if a_norm == b_norm:
        return True

    # substring match (core logic)
    if a_norm in b_norm or b_norm in a_norm:
        return True

    return False


# -------------------------------------------------------
# CLUSTERING HELPER
# -------------------------------------------------------

def cluster_models(models: List[str]) -> List[List[str]]:
    clusters: List[List[str]] = []

    for model in models:
        if not model:
            continue

        placed = False

        for cluster in clusters:
            if any(is_model_alias(model, existing) for existing in cluster):
                cluster.append(model)
                placed = True
                break

        if not placed:
            clusters.append([model])

    return clusters


# -------------------------------------------------------
# CANONICAL MODEL SELECTION
# -------------------------------------------------------

def pick_canonical_model(cluster: List[str]) -> str | None:
    if not cluster:
        return None

    return max(cluster, key=lambda x: len(normalize_token(x)))