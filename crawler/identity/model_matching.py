def normalize_model_tokens(model):
    if not model:
        return []

    model = model.upper()
    return re.findall(r"[A-Z]+|\d+", model)


def model_similarity(a, b):
    if not a or not b:
        return 0.0

    a = a.upper()
    b = b.upper()

    if a == b:
        return 1.0

    a_tokens = normalize_model_tokens(a)
    b_tokens = normalize_model_tokens(b)

    a_digits = "".join(t for t in a_tokens if t.isdigit())
    b_digits = "".join(t for t in b_tokens if t.isdigit())

    if not a_digits or not b_digits or a_digits != b_digits:
        return 0.0

    a_alpha = "".join(t for t in a_tokens if t.isalpha())
    b_alpha = "".join(t for t in b_tokens if t.isalpha())

    score = 0.0

    if a_digits and b_digits and a_digits == b_digits:
        score += 0.45

    if a_alpha and b_alpha and (a_alpha in b_alpha or b_alpha in a_alpha):
        score += 0.30

    if a in b or b in a:
        score += 0.20

    overlap = len(set(a_tokens) & set(b_tokens))
    total = max(len(set(a_tokens)), 1)
    score += 0.05 * (overlap / total)

    if score >= 0.5:
        print(f"[MODEL SIM] {a} <-> {b} = {score:.2f}")

    return min(score, 1.0)


def find_existing_by_model(conn, model, threshold=0.80):
    if not model:
        return None

    rows = conn.execute("""
        SELECT *
        FROM products
        WHERE model IS NOT NULL
    """).fetchall()

    best = None
    best_score = 0.0

    for row in rows:
        score = model_similarity(model, row["model"])

        if score > best_score:
            best_score = score
            best = row

    print(f"[MODEL SEARCH] input={model} best={best['model'] if best else None} score={best_score:.2f}")

    if best and best_score >= threshold:
        print(f"[FUZZY MODEL MATCH] {model} -> {best['model']} ({best_score:.2f})")
        return best

    return None


def has_model_support(markdown, model):
    if not model or not markdown:
        return False

    m = model.lower()
    text = markdown.lower()

    if text.count(m) >= 2:
        return True

    if re.search(rf"(model|mpn)[^a-z0-9]{{0,10}}{re.escape(m)}", text):
        return True

    return False