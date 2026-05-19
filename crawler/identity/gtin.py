import re

def normalize_gtin(gtin):
    if not gtin:
        return None

    gtin = re.sub(r"\D", "", str(gtin))

    if len(gtin) == 13 and gtin.startswith("0"):
        return gtin[1:]

    return gtin if len(gtin) in (12, 13, 14) else None


def gtin_similarity(a, b):
    a = normalize_gtin(a)
    b = normalize_gtin(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    if a.lstrip("0") == b.lstrip("0"):
        return 0.99

    matches = 0

    for x, y in zip(a, b):
        if x == y:
            matches += 1

    score = matches / max(len(a), len(b))

    if len(a) > 4 and len(b) > 4:
        if a[:4] != b[:4]:
            score *= 0.5

    return score