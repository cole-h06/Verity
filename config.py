import os

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

IDENTITY_RESET_MODE = True
REBUILD_MODE = True
MIN_CLAIMS_PER_PAGE = 5

HIGH_SECURITY_DOMAINS = [
    "walmart.com",
    "amazon.com",
    "bestbuy.com",
    "target.com",
    "homedepot.com",
    "lowes.com",
    "sony.com",
    "bhphotovideo.com",
    "jbl.com",
    "bjs.com",
    "costco.com",
    "macys.com",
    "wayfair.com",
    "kohls.com",
    "samsclub.com",
    "pcrichard.com"
]

HEAVY_JS_DOMAINS = [
    "sony.com",
    "apple.com"
]

INTERACTIVE_DOMAINS = [
    "sony.com",
    "bjs.com"
]

VERIFICATION_TARGETS = {
    "laptops": ["cpu_model", "ram_gb", "storage_gb", "weight_lbs", "screen_brightness_nits", "display_resolution" "battery_wh"],
    "headphones": ["driver_type", "frequency_response_hz", "battery_life_hrs", "impedance_ohms", "noise_cancellation"],
    "portable_power": ["capacity_mah", "wattage", "output_ports", "charging_speed_w"],
    "mini_fridges": ["total_capacity", "refrigerator_capacity", "freezer_capacity", "noise_db", "energy_star_certified"],
    "air_fryers": ["capacity_qt", "basket_material", "wattage", "max_temperature_f"],
    "espresso": ["pump_pressure_bar", "power_w", "heating_system", "water_tank_capacity"]
}

CATEGORY_STANDARDS = {
    "laptops": {
        "weight_lbs": "lb",
        "screen_brightness_nits": "nits",
        "battery_wh": "wh"
    },

    "headphones": {
        "frequency_response_hz": "hz",
        "battery_life_hrs": "hrs",
        "impedance_ohms": "ohm"
    },

    "portable_power": {
        "capacity_mah": "mah",
        "wattage": "w",
        "charging_speed_w": "w"
    },

    "mini_fridges": {
        "capacity_cu_ft": "cu_ft",
        "refrigerator_capacity_cu_ft": "cu_ft",
        "freezer_capacity_cu_ft": "cu_ft",
        "noise_db": "db"
    },

    "air_fryers": {
        "capacity_qt": "qt",
        "wattage": "w",
        "max_temp_f": "f",
        "dimensions_in": "in"
    },

    "espresso": {
        "pump_pressure_bar": "bar",
        "power_w": "w",
        "water_tank_capacity": "oz",
        "bean_hopper_capacity": "g",
        "dimensions_in": "in"
    }
}

SEED_URLS = {
    "laptops": [
        "https://www.bestbuy.com/site/all-laptops/macbooks/pcmcat247400050001.c?id=pcmcat247400050001",
        "https://www.bestbuy.com/site/hp/hp-laptops/pcmcat1513015098109.c?id=pcmcat1513015098109",
        "https://www.bestbuy.com/site/lenovo/lenovo-laptops/pcmcat230600050001.c?id=pcmcat230600050001",
        "https://www.bestbuy.com/site/dell/dell-laptops/pcmcat140500050011.c?id=pcmcat140500050011"
    ],
    "headphones": [
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=pcmcat331200050015&id=pcat17071&qp=brand_facet%3DBrand%7EBeats&st=pcmcat331200050015_categoryid%24pcmcat144700050004",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=pcmcat331200050015&id=pcat17071&qp=brand_facet%3DBrand%7ESony&st=pcmcat331200050015_categoryid%24pcmcat144700050004",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=pcmcat331200050015&id=pcat17071&qp=brand_facet%3DBrand%7EJBL&st=pcmcat331200050015_categoryid%24pcmcat144700050004",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=pcmcat331200050015&id=pcat17071&qp=brand_facet%3DBrand%7EApple&st=pcmcat331200050015_categoryid%24pcmcat144700050004"
    ],
    "portable_power": [
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=pcmcat326000050010&id=pcat17071&qp=brand_facet%3DBrand%7EAnker&st=categoryid%24pcmcat326000050010",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=pcmcat326000050010&id=pcat17071&qp=brand_facet%3DBrand%7EBelkin&st=categoryid%24pcmcat326000050010"
    ],
    "mini_fridges": [
        "https://www.homedepot.com/b/Appliances-Mini-Fridges/Magic-Chef/N-5yc1vZc4moZy0",
        "https://www.homedepot.com/b/Appliances-Mini-Fridges/Frigidaire/N-5yc1vZc4moZ75h",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=abcat0901002&id=pcat17071&qp=brand_facet%3DBrand%7EInsignia%E2%84%A2&st=categoryid%24abcat0901002"
    ],
    "air_fryers": [
        "https://www.target.com/c/air-fryers-kitchen-appliances-dining/ninja/-/N-ncrpxZ5em1p",
        "https://www.target.com/c/air-fryers-kitchen-appliances-dining/instant-pot/-/N-ncrpxZ4vqn6",
        "https://www.target.com/c/air-fryers-kitchen-appliances-dining/instant-pot/-/N-ncrpxZ566zh?moveTo=product-list-grid",
        "https://www.walmart.com/browse/home/air-fryers/4044_90548_90546_4824_9960466?facet=customer_rating%3A4+-+5+Stars%7C%7Cbrand%3ABeautiful&povid=Home_Hubspoke_CookDine_90546KitchenAppliances_Category_ATF_AirFryers",
        "https://www.walmart.com/browse/home/air-fryers/4044_90548_90546_4824_9960466?facet=customer_rating%3A4+-+5+Stars%7C%7Cbrand%3AChefman&povid=Home_Hubspoke_CookDine_90546KitchenAppliances_Category_ATF_AirFryers",
        "https://www.walmart.com/browse/home/air-fryers/4044_90548_90546_4824_9960466?facet=customer_rating%3A4+-+5+Stars%7C%7Cbrand%3AGourmia&povid=Home_Hubspoke_CookDine_90546KitchenAppliances_Category_ATF_AirFryers"
    ],
    "espresso": [
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=abcat0912006&id=pcat17071&qp=brand_facet%3DBrand%7EDe%27Longhi&st=categoryid%24abcat0912006",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=abcat0912006&id=pcat17071&qp=brand_facet%3DBrand%7EBreville&st=categoryid%24abcat0912006",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=abcat0912006&id=pcat17071&qp=brand_facet%3DBrand%7ENespresso&st=categoryid%24abcat0912006",
        "https://www.bestbuy.com/site/searchpage.jsp?browsedCategory=abcat0912006&id=pcat17071&qp=brand_facet%3DBrand%7ENinja&st=categoryid%24abcat0912006"
    ]
}

RETAILER_CONFIG = {
    "bestbuy.com": {
        "container_selectors": [
            "div.sku-block a[href*='/product/']",
            "div.sku-block a[href]"
        ],
        "next_selector": "a[aria-label='Next page']"
    },
    "homedepot.com": {
        "container_selectors": [
            "div[data-testid='pod-tapper'] a[href*='/p/']"
        ],
        "next_selector": "a[aria-label='Next']"
    },
    "target.com": {
        "container_selectors": [
            '[data-test="product-grid"] a[href*="/p/"]'
        ],
        "next_selector": None
    },
    "walmart.com": {
        "container_selectors": [
            "[data-item-id] a"
        ],
        "next_selector": None
    }
}

EXPERIENCE_CONFIG = {
    "reddit.com": {
        "css_selector": "shreddit-comment, shreddit-post",
        "wait_for": "shreddit-comment"
    },
    "default": {
        "css_selector": None,
        "wait_for": None
    }
}

PRODUCT_URL_PATTERNS = {
    "amazon": ["/dp/"],
    "walmart": ["/ip/"],
    "bestbuy": ["/product/", "skuid="],
    "homedepot": ["/p/"],
    "target": ["/p/"],
    "default": ["/product/", "/p/", "/dp/", "/ip/"]
}

BROWSER_CONFIG = {
    "headless": False,
    "viewport": {"width": 1920, "height": 1080},
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}