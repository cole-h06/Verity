import requests

def fetch_hd_specs(product_id):
    url = "https://apionline.homedepot.com/federation-gateway/graphql"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    payload = {
        "operationName": "productDetails",
        "variables": {
            "itemId": product_id,
            "storeId": "8119",
            "zipCode": "07027"
        },
        "query": """
        query productDetails($itemId: String!) {
          product(itemId: $itemId) {
            specificationGroups {
              specifications {
                specName
                specValue
              }
            }
          }
        }
        """
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()

        specs = []

        groups = data.get("data", {}).get("product", {}).get("specificationGroups", [])

        for group in groups:
            for spec in group.get("specifications", []):
                name = spec.get("specName")
                value = spec.get("specValue")

                if name and value:
                    specs.append((name, value))

        return specs

    except:
        return []


API_HANDLERS = {
    "homedepot.com": fetch_hd_specs
}