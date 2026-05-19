from extraction.identity_extractors import (
    extract_hard_ids,
    extract_labeled_ids,
    extract_model_fallback
)

from extraction.target import (
    get_upc
)

from identity.gtin import (
    normalize_gtin
)

from identity.model_matching import (
    has_model_support
)

from miner import (
    run_llm_identity,
    is_valid_model
)


def enrich_identity(
    identity,
    html,
    markdown,
    product,
    next_specs,
    combined_specs,
    domain
):
    if html:
        html_upc = get_upc(html)

        if html_upc:
            html_upc = normalize_gtin(html_upc)

        if html_upc:
            if not identity["gtin"]:
                identity["gtin"] = html_upc
                print(f"[HTML GTIN FALLBACK] {html_upc}")
            else:
                print(f"[JSON-LD GTIN PRESERVED] {identity['gtin']}")

            combined_specs.append(("gtin", html_upc))

    hard_ids = extract_hard_ids(
        html if html else markdown
    )

    for k, v in hard_ids:
        combined_specs.append((k, v))

    labeled_ids = extract_labeled_ids(markdown)

    for k, v in next_specs:
        if str(k).lower() in ["gtin", "upc"]:

            forced = normalize_gtin(v)

            if forced:

                if not identity["gtin"]:
                    identity["gtin"] = forced
                    print(f"[API GTIN FALLBACK] {forced}")

                else:
                    print(
                        f"[JSON-LD GTIN PRESERVED] "
                        f"{identity['gtin']}"
                    )

    if not identity["gtin"] and labeled_ids["gtin"]:
        identity["gtin"] = labeled_ids["gtin"]

        print(
            f"[LABEL GTIN FOUND] "
            f"{identity['gtin']}"
        )

    if not identity["model"] and labeled_ids["model"]:
        identity["model"] = labeled_ids["model"]

        print(
            f"[LABEL MODEL FOUND] "
            f"{identity['model']}"
        )

    fallback_model = None

    if not identity["model"]:

        fallback_model = extract_model_fallback(markdown)

        if (
            is_valid_model(fallback_model)
            and has_model_support(markdown, fallback_model)
        ):

            identity["model"] = fallback_model

            print(
                f"[MODEL ACCEPTED - FALLBACK] "
                f"{identity['model']}"
            )

        else:
            print(
                f"[MODEL REJECTED - FALLBACK] "
                f"{fallback_model}"
            )

    if (
        (
            not identity["gtin"]
            or not identity["model"]
        )
        and len(markdown) > 2000
    ):

        llm_ids = run_llm_identity(markdown)

        if llm_ids:

            if (
                llm_ids.get("gtin")
                and llm_ids["gtin"].isdigit()
            ):

                if not identity["gtin"]:

                    identity["gtin"] = normalize_gtin(
                        llm_ids["gtin"]
                    )

                    print(
                        f"[LLM GTIN] "
                        f"{identity['gtin']}"
                    )

            if (
                llm_ids.get("model")
                and is_valid_model(llm_ids["model"])
            ):

                if not identity["model"]:

                    identity["model"] = llm_ids["model"]

                    print(
                        f"[LLM MODEL] "
                        f"{identity['model']}"
                    )

    amazon_gtin = None

    if "amazon.com" in domain:

        for name, value in combined_specs:

            k = str(name).lower()
            val = normalize_gtin(value)

            if k in ["gtin", "upc"] and val:
                amazon_gtin = val
                break

        if amazon_gtin:
            print(
                f"[AMAZON GTIN AUTHORITY] "
                f"{amazon_gtin}"
            )

            identity["gtin"] = amazon_gtin

    clean_specs = []

    for name, value in combined_specs:

        k = str(name).lower()
        val = str(value).strip()

        if k in ["gtin", "upc"]:

            normalized_val = normalize_gtin(val)

            if normalized_val:

                is_json_ld_gtin = (
                    product
                    and (
                        normalize_gtin(product.get("gtin13")) == normalized_val
                        or normalize_gtin(product.get("gtin12")) == normalized_val
                        or normalize_gtin(product.get("gtin14")) == normalized_val
                        or normalize_gtin(product.get("gtin")) == normalized_val
                        or normalize_gtin(product.get("upc")) == normalized_val
                    )
                )

                if amazon_gtin:

                    if normalized_val != amazon_gtin:

                        print(
                            f"[AMAZON GTIN PRESERVED] "
                            f"{amazon_gtin} ignored={normalized_val}"
                        )

                elif is_json_ld_gtin:

                    if identity["gtin"] != normalized_val:

                        print(
                            f"[JSON-LD GTIN OVERRIDE] "
                            f"{identity['gtin']} -> "
                            f"{normalized_val}"
                        )

                    identity["gtin"] = normalized_val

                elif not identity["gtin"]:

                    identity["gtin"] = normalized_val

                    print(
                        f"[IDENTITY GTIN FALLBACK] "
                        f"{normalized_val}"
                    )

                else:

                    print(
                        f"[GTIN PRESERVED] "
                        f"{identity['gtin']} "
                        f"ignored={normalized_val}"
                    )

            else:
                print(f"[REJECTED GTIN] {val}")

            continue

        elif k in ["model_number", "mpn"]:

            if (
                not identity["model"]
                and is_valid_model(val)
            ):

                identity["model"] = val

                print(
                    f"[IDENTITY] MODEL_NUMBER: "
                    f"{val}"
                )

            elif not is_valid_model(val):

                print(
                    f"[REJECTED MODEL_NUMBER] "
                    f"{val}"
                )

            continue

        elif k == "model":

            if not identity["model"]:

                if (
                    is_valid_model(val)
                    and has_model_support(markdown, val)
                ):

                    identity["model"] = val
                    print(f"[MODEL ACCEPTED] {val}")

                else:
                    print(f"[MODEL REJECTED] {val}")

            continue

        elif k == "sku":

            identity["sku"] = val

            print(f"[IDENTITY] SKU: {val}")

            continue

        clean_specs.append((name, value))

    combined_specs = clean_specs

    return {
        "identity": identity,
        "combined_specs": combined_specs
    }