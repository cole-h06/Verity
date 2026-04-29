import requests
from config import SERPER_API_KEY, TAVILY_API_KEY


def serper_search(query):
    url = "https://google.serper.dev/search"

    payload = {
        "q": query,
        "num": 10
    }

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    res = requests.post(url, json=payload, headers=headers, timeout=10)

    if res.status_code != 200:
        return []

    data = res.json()

    urls = []
    for item in data.get("organic", []):
        link = item.get("link")
        if link:
            urls.append(link)

    return urls


def tavily_search(query):
    url = "https://api.tavily.com/search"

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": 5
    }

    res = requests.post(url, json=payload, timeout=10)

    if res.status_code != 200:
        return []

    data = res.json()

    urls = []
    for item in data.get("results", []):
        link = item.get("url")
        if link:
            urls.append(link)

    if urls:
        return urls

    payload["search_depth"] = "advanced"

    res = requests.post(url, json=payload, timeout=10)

    if res.status_code != 200:
        return []

    data = res.json()

    urls = []
    for item in data.get("results", []):
        link = item.get("url")
        if link:
            urls.append(link)

    return urls