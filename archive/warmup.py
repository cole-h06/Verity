from playwright.sync_api import sync_playwright

USER_DATA_DIR = "./user_data"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

TARGETS = [
    "https://www.homedepot.com",
    "https://www.abt.com",
    "https://www.brandsmartusa.com"
]

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=False,

        ignore_default_args=["--enable-automation"],

        args=["--disable-blink-features=AutomationControlled"],

        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="en-US"
    )

    page = context.pages[0] if context.pages else context.new_page()

    for url in TARGETS:
        print(f"[WARMUP] Open this site and solve any challenge if needed: {url}")
        page.goto("https://www.google.com", wait_until="domcontentloaded")
        input(f"Press Enter after {url} looks normal and trusted... ")

    context.close()