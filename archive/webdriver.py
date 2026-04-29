from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
import time


CHROMEDRIVER_PATH = r"C:\webdriver\chromedriver.exe"


def render_with_selenium(url):

    chrome_options = Options()

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    chrome_options.add_argument("--disable-http2")
    chrome_options.add_argument("--disable-features=NetworkService")

    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    service = Service(executable_path=CHROMEDRIVER_PATH)

    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    try:

        driver.get(url)

        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        time.sleep(2)

        rendered_html = driver.page_source

        if "this site can’t be reached" in rendered_html.lower() or "err_http2" in rendered_html.lower():
            print("[SELENIUM BLOCKED PAGE]")
            return None, None

        driver.execute_script("""
        let el = document.getElementById("specDetails");
        if (el && el.firstChild && el.firstChild.firstChild && el.firstChild.firstChild.firstChild) {
            el.firstChild.firstChild.firstChild.firstChild.click();
        }
        """)

        time.sleep(3)

        specs_html = driver.execute_script("""
        let el = document.getElementById("specDetails");
        if (el && el.firstChild && el.firstChild.firstChild) {
            let specs = el.firstChild.firstChild.children[1];
            if (specs) return specs.outerHTML;
        }
        return null;
        """)

        return rendered_html, specs_html

    except Exception as e:

        print("[SELENIUM ERROR]", e)
        return None, None

    finally:
        driver.quit()