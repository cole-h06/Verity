import requests
import os

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

def tavily_extract(url):
    try:
        res = requests.post(
            "https://api.tavily.com/extract",
            json={
                "api_key": TAVILY_API_KEY,
                "urls": [url]
            }
        )
        data = res.json()
        return data["results"][0]["raw_content"]
    except:
        return None