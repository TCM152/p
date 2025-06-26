import asyncio
import aiohttp
import aiodns
import socket
import ipaddress
import argparse
import logging
import json
import csv
from pathlib import Path
from typing import List, Tuple, Dict, Set
import random
import string
import subprocess
import ssl
import sys
from urllib.parse import urlencode
from datetime import datetime
from shodan import Shodan
import pickle
from dataclasses import dataclass

# Setup logging
logging.basicConfig(
    filename=f'bypass_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Konfigurasi CDN dan User-Agent
CDN_IP_RANGES = {
    "Cloudflare": ["173.245.48.0/20", "103.21.244.0/22", "104.16.0.0/13"],
    "Akamai": ["23.32.0.0/11", "23.192.0.0/11"]
}
CDN_ORG_NAMES = {
    "Cloudflare": ["CLOUDFLARE", "CLOUDFLARENET"],
    "Akamai": ["AKAMAI", "AKAMAI TECHNOLOGIES"],
    "Amazon": ["AMAZON", "AWS"]
}
CDN_HEADER_SIGNATURES = {
    "Cloudflare": ["cf-ray", "cf-cache-status"],
    "Akamai": ["akamai-grn", "x-akamai-transformed"],
    "Amazon": ["x-amz-cf-id", "x-amz-cf-pop"]
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

RANDOM_SUBDOMAINS = [''.join(random.choices(string.ascii_lowercase + string.digits, k=15)) for _ in range(5)]

def is_valid_domain(domain: str) -> bool:
    import re
    pattern = r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain))

def is_private_ip(ip: str) -> bool:
    try:
        ip_addr = ipaddress.ip_address(ip)
        return ip_addr.is_private
    except ValueError:
        return False

def is_cdn_ip(ip: str, asn_info: Dict) -> Tuple[bool, str]:
    try:
        ip_addr = ipaddress.ip_address(ip)
        for cdn, ranges in CDN_IP_RANGES.items():
            for cidr in ranges:
                if ip_addr in ipaddress.ip_network(cidr):
                    return True, cdn
        org = asn_info.get("org", "").upper()
        for cdn, org_names in CDN_ORG_NAMES.items():
            if any(name in org for name in org_names):
                return True, cdn
        return False, ""
    except ValueError:
        return False, ""

@dataclass
class ScanResult:
    subdomain: str
    ip: str
    dns_records: Dict
    cdn: Dict
    asn: Dict
    http: Dict
    nuclei_findings: List[Dict]

class CacheManager:
    def __init__(self, cache_file: str = "scan_cache.pkl"):
        self.cache_file = cache_file
        self.cache = self.load_cache()

    def load_cache(self) -> Dict:
        if Path(self.cache_file).exists():
            with open(self.cache_file, "rb") as f:
                return pickle.load(f)
        return {"dns": {}, "http": {}}

    def save_cache(self):
        with open(self.cache_file, "wb") as f:
            pickle.dump(self.cache, f)

    def get_dns(self, subdomain: str) -> Dict:
        return self.cache["dns"].get(subdomain, {})

    def set_dns(self, subdomain: str, data: Dict):
        self.cache["dns"][subdomain] = data
        self.save_cache()

    def get_http(self, ip: str, port: int) -> Dict:
        return self.cache["http"].get(f"{ip}:{port}", {})

    def set_http(self, ip: str, port: int, data: Dict):
        self.cache["http"][f"{ip}:{port}"] = data
        self.save_cache()

class DNSScanner:
    def __init__(self, domain: str, resolver_path: str = "resolvers.txt"):
        self.domain = domain
        self.resolver_path = resolver_path
        self.resolver = aiodns.DNSResolver()
        self.semaphore = asyncio.Semaphore(100)
        self.cache = CacheManager()

    async def detect_wildcard(self) -> Tuple[bool, Set[str]]:
        wildcard_ips = set()
        for random_sub in RANDOM_SUBDOMAINS:
            try:
                result = await self.resolver.gethostbyname(f"{random_sub}.{self.domain}", socket.AF_INET)
                wildcard_ips.update(result.addresses)
            except:
                continue
        return bool(wildcard_ips), wildcard_ips

    def run_amass(self, wordlist_path: str) -> List[str]:
        try:
            output_file = f"amass_{self.domain}.txt"
            cmd = ["amass", "enum", "-d", self.domain, "-brute", "-w", wordlist_path, "-o", output_file, "-passive"]
            subprocess.run(cmd, check=True, timeout=1800)
            with open(output_file, "r") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logging.error(f"Amass failed: {e}")
            return []

    def run_massdns(self, wordlist_path: str) -> List[Dict]:
        try:
            output_file = f"massdns_{self.domain}.txt"
            cmd = ["massdns", "-r", self.resolver_path, "-t", "A", "-o", "S", "-w", output_file, wordlist_path]
            subprocess.run(cmd, check=True, timeout=600)
            results = []
            with open(output_file, "r") as f:
                for line in f:
                    if " A " in line:
                        subdomain, _, ip = line.strip().split()
                        results.append({"subdomain": subdomain.rstrip("."), "ip": ip})
            return results
        except Exception as e:
            logging.error(f"MassDNS failed: {e}")
            return []

    def run_dnsx(self, subdomains: List[str]) -> List[str]:
        try:
            input_file = f"dnsx_input_{self.domain}.txt"
            output_file = f"dnsx_{self.domain}.txt"
            with open(input_file, "w") as f:
                f.write("\n".join(subdomains))
            cmd = ["dnsx", "-wd", self.domain, "-l", input_file, "-o", output_file]
            subprocess.run(cmd, check=True, timeout=300)
            with open(output_file, "r") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logging.error(f"dnsx failed: {e}")
            return []

    async def resolve_dns(self, subdomain: str, record_types: List[str] = ["A", "AAAA", "CNAME"]) -> Dict:
        cached = self.cache.get_dns(subdomain)
        if cached:
            return cached
        async with self.semaphore:
            results = {}
            for rtype in record_types:
                try:
                    if rtype == "CNAME":
                        answers = await self.resolver.query(subdomain, rtype)
                        results[rtype] = [str(ans.host) for ans in answers]
                    else:
                        result = await self.resolver.gethostbyname(subdomain, socket.AF_INET if rtype == "A" else socket.AF_INET6)
                        results[rtype] = result.addresses
                except Exception as e:
                    results[rtype] = []
                    logging.debug(f"Failed to resolve {subdomain} ({rtype}): {e}")
            self.cache.set_dns(subdomain, results)
            return results

class HTTPScanner:
    def __init__(self):
        self.cache = CacheManager()

    def get_random_headers(self) -> Dict:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": random.choice(["text/html,application/xhtml+xml", "application/json"]),
            "Accept-Language": random.choice(["en-US,en;q=0.5", "id-ID,id;q=0.9"]),
            "X-Forwarded-For": f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
        }
        if random.random() > 0.3:
            headers["Referer"] = f"https://{''.join(random.choices(string.ascii_lowercase, k=10))}.com"
        if random.random() > 0.4:
            headers["Cookie"] = f"session={''.join(random.choices(string.ascii_letters + string.digits, k=20))}"
        return headers

    async def fingerprint(self, ip: str, port: int, session: aiohttp.ClientSession, use_tls_fingerprint: bool = False, proxy: str = None, max_retries: int = 2) -> Dict:
        cached = self.cache.get_http(ip, port)
        if cached:
            return cached
        url = f"http://{ip}:{port}" if port != 443 else f"https://{ip}"
        if random.random() > 0.5:
            url += "?" + urlencode({f"q{random.randint(1, 100)}": random.randint(1, 1000)})
        
        result = {
            "port": port,
            "status": None,
            "headers": {},
            "title": "-",
            "final_url": "-",
            "tls_fingerprint": "-",
            "http2": False,
            "cdn_detected": "",
            "tech_stack": []
        }

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(random.uniform(0.3, 1.0))
                headers = self.get_random_headers()
                if use_tls_fingerprint and port == 443:
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.set_alpn_protocols(["h2", "http/1.1"])
                    context.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256")
                    async with session.get(url, headers=headers, ssl=context, proxy=proxy, timeout=8) as resp:
                        result["status"] = resp.status
                        result["headers"] = dict(resp.headers)
                        result["final_url"] = str(resp.url)
                        result["http2"] = resp.version == (2, 0)
                        result["tls_fingerprint"] = self.compute_ja3_fingerprint(context)
                        result["tech_stack"] = self.detect_tech_stack(resp.headers)
                        if resp.status in [403, 429]:
                            logging.warning(f"WAF block detected on {ip}:{port} (Status: {resp.status}, Attempt: {attempt+1})")
                            continue
                        try:
                            text = await resp.text()
                            start = text.lower().find("<title>")
                            end = text.lower().find("</title>")
                            if start != -1 and end != -1:
                                result["title"] = text[start + 7:end].strip()
                        except:
                            pass
                        for cdn, signatures in CDN_HEADER_SIGNATURES.items():
                            if any(sig in result["headers"] for sig in signatures):
                                result["cdn_detected"] = cdn
                                break
                        break
                else:
                    async with session.get(url, headers=headers, proxy=proxy, timeout=8, allow_redirects=True) as resp:
                        result["status"] = resp.status
                        result["headers"] = dict(resp.headers)
                        result["final_url"] = str(resp.url)
                        result["http2"] = resp.version == (2, 0)
                        result["tech_stack"] = self.detect_tech_stack(resp.headers)
                        if resp.status in [403, 429]:
                            logging.warning(f"WAF block detected on {ip}:{port} (Status: {resp.status}, Attempt: {attempt+1})")
                            continue
                        try:
                            text = await resp.text()
                            start = text.lower().find("<title>")
                            end = text.lower().find("</title>")
                            if start != -1 and end != -1:
                                result["title"] = text[start + 7:end].strip()
                        except:
                            pass
                        for cdn, signatures in CDN_HEADER_SIGNATURES.items():
                            if any(sig in result["headers"] for sig in signatures):
                                result["cdn_detected"] = cdn
                                break
                        break
            except aiohttp.ClientError as e:
                logging.debug(f"HTTP retry failed for {ip}:{port}: {e}")
                if attempt == max_retries - 1:
                    result["status"] = "ERROR"
            except Exception as e:
                logging.debug(f"HTTP check failed for {ip}:{port}: {e}")
        self.cache.set_http(ip, port, result)
        return result

    def compute_ja3_fingerprint(self, context: ssl.SSLContext) -> str:
        try:
            ciphers = context.get_ciphers()
            cipher_ids = [str(cipher["id"]) for cipher in ciphers]
            return f"ja3:771,{'-'.join(cipher_ids[:3])},..."
        except Exception as e:
            logging.error(f"JA3 computation failed: {e}")
            return "ja3:unknown"

    def detect_tech_stack(self, headers: Dict) -> List[str]:
        tech = []
        server = headers.get("Server", "").lower()
        if "nginx" in server:
            tech.append("Nginx")
        elif "apache" in server:
            tech.append("Apache")
        if "x-powered-by" in headers:
            tech.append(headers["x-powered-by"])
        if "x-drupal-cache" in headers:
            tech.append("Drupal")
        return tech

    def run_httpx(self, subdomains: List[str], ports: List[int]) -> List[Dict]:
        try:
            input_file = f"httpx_input_{random.randint(1000, 9999)}.txt"
            with open(input_file, "w") as f:
                f.write("\n".join(subdomains))
            output_file = f"httpx_{random.randint(1000, 9999)}.json"
            cmd = [
                "httpx", "-l", input_file, "-ports", ",".join(map(str, ports)),
                "-status-code", "-title", "-json", "-o", output_file
            ]
            subprocess.run(cmd, check=True, timeout=600)
            results = []
            with open(output_file, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line.strip())
                        results.append({
                            "url": data.get("url"),
                            "status": data.get("status_code"),
                            "title": data.get("title", "-"),
                            "port": int(data.get("port", 80))
                        })
            return results
        except Exception as e:
            logging.error(f"httpx failed: {e}")
            return []

class ResultProcessor:
    def __init__(self, domain: str):
        self.domain = domain
        self.results: List[ScanResult] = []

    def add_result(self, result: ScanResult):
        self.results.append(result)

    def filter_results(self) -> List[ScanResult]:
        filtered = []
        seen_ips = set()
        for result in self.results:
            if (
                result.http.get("status") in [200, 301]
                and not result.cdn["is_cdn"]
                and result.ip not in seen_ips
            ):
                filtered.append(result)
                seen_ips.add(result.ip)
        return filtered

    def save_results(self, json_file: str, csv_file: str):
        filtered_results = self.filter_results()
        with open(json_file, "w") as f:
            json.dump([r.__dict__ for r in filtered_results], f, indent=2)
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "subdomain", "ip", "asn", "org", "cdn_name", "port", "status",
                "server", "title", "final_url", "http2", "tls_fingerprint", "cdn_detected", "tech_stack", "nuclei_findings"
            ])
            writer.writeheader()
            for result in filtered_results:
                writer.writerow({
                    "subdomain": result.subdomain,
                    "ip": result.ip,  # Fixed: Use result.ip instead of result.asn["asn"]
                    "asn": result.asn["asn"],
                    "org": result.asn["org"],
                    "cdn_name": result.cdn["name"],
                    "port": result.http.get("port", "-"),
                    "status": result.http.get("status", "-"),
                    "server": result.http.get("headers", {}).get("Server", "-"),
                    "title": result.http.get("title", "-"),
                    "final_url": result.http.get("final_url", "-"),
                    "http2": str(result.http.get("http2", False)),
                    "tls_fingerprint": result.http.get("tls_fingerprint", "-"),
                    "cdn_detected": result.http.get("cdn_detected", "-"),
                    "tech_stack": ",".join(result.http.get("tech_stack", [])),
                    "nuclei_findings": json.dumps(result.nuclei_findings)
                })

class Scanner:
    def __init__(self, domain: str, wordlist_path: str, ports: List[int], proxy_file: str = None, shodan_api: str = None, use_tor: bool = False):
        self.domain = domain
        self.wordlist_path = wordlist_path
        self.ports = ports
        self.proxy_file = proxy_file
        self.shodan_api = shodan_api
        self.use_tor = use_tor
        self.dns_scanner = DNSScanner(domain)
        self.http_scanner = HTTPScanner()
        self.result_processor = ResultProcessor(domain)
        self.proxies = self.load_proxies() if proxy_file else []
        if use_tor:
            tor_proxy = self.setup_tor_proxy()
            if tor_proxy:
                self.proxies.append(tor_proxy)

    def load_proxies(self) -> List[str]:
        if not Path(self.proxy_file).is_file():
            logging.warning(f"Proxy file '{self.proxy_file}' tidak ditemukan")
            return []
        with open(self.proxy_file, "r") as f:
            return [line.strip() for line in f if line.strip()]

    def setup_tor_proxy(self) -> str:
        try:
            subprocess.run(["tor"], capture_output=True, timeout=5)
            return "socks5://127.0.0.1:9050"
        except Exception as e:
            logging.warning(f"Tor setup failed: {e}")
            return None

    def run_shodan_search(self) -> List[Dict]:
        if not self.shodan_api:
            return []
        try:
            shodan = Shodan(self.shodan_api)
            results = shodan.search(f"hostname:{self.domain}", limit=100)
            subdomains = []
            for result in results["matches"]:
                ip = result.get("ip_str")
                hostnames = result.get("hostnames", [])
                port = result.get("port")
                for hostname in hostnames:
                    subdomains.append({"subdomain": hostname, "ip": ip, "port": port})
            return subdomains
        except Exception as e:
            logging.error(f"Shodan search failed: {e}")
            return []

    def lookup_asn(self, ip: str) -> Dict:
        if is_private_ip(ip):
            return {"asn": "-", "org": "Private IP", "country": "-"}
        try:
            from ipwhois import IPWhois
            obj = IPWhois(ip)
            results = obj.lookup_rdap()
            return {
                "asn": results.get("asn", "-"),
                "org": results.get("network", {}).get("name", "-"),
                "country": results.get("network", {}).get("country", "-")
            }
        except Exception as e:
            logging.error(f"ASN lookup failed for {ip}: {e}")
            return {"asn": "-", "org": "-", "country": "-"}

    async def run(self, use_tls_fingerprint: bool, use_nuclei: bool):
        print("⚠️ PERINGATAN: Gunakan skrip ini hanya pada domain yang Anda miliki atau dengan izin eksplisit!")
        amass_subdomains = self.dns_scanner.run_amass(self.wordlist_path)
        logging.info(f"Amass found {len(amass_subdomains)} subdomains")

        massdns_results = self.dns_scanner.run_massdns(self.wordlist_path)
        logging.info(f"MassDNS found {len(massdns_results)} subdomains")

        valid_subdomains = self.dns_scanner.run_dnsx([r["subdomain"] for r in massdns_results] + amass_subdomains)
        logging.info(f"dnsx filtered {len(valid_subdomains)} valid subdomains")

        shodan_subdomains = self.run_shodan_search()
        subdomains = list(set(valid_subdomains + [s["subdomain"] for s in shodan_subdomains]))
        logging.info(f"Total subdomains: {len(subdomains)}")

        httpx_results = self.http_scanner.run_httpx(subdomains, self.ports)  # Fixed: Call run_httpx from http_scanner
        logging.info(f"httpx found {len(httpx_results)} live subdomains")

        async with aiohttp.ClientSession() as session:
            for httpx_result in httpx_results:
                ip = next((r["ip"] for r in massdns_results if r["subdomain"] in httpx_result["url"]), None)
                if not ip or is_private_ip(ip):
                    continue
                asn_info = self.lookup_asn(ip)
                is_cdn, cdn_name = is_cdn_ip(ip, asn_info)
                http_result = await self.http_scanner.fingerprint(
                    ip, httpx_result["port"], session, use_tls_fingerprint, random.choice(self.proxies) if self.proxies else None
                )
                result = ScanResult(
                    subdomain=httpx_result["url"].split("://")[1].split(":")[0],
                    ip=ip,
                    dns_records={"A": [ip]},
                    cdn={"is_cdn": is_cdn, "name": cdn_name},
                    asn=asn_info,
                    http=http_result,
                    nuclei_findings=[] if not use_nuclei else self.run_nuclei(ip, httpx_result["port"])
                )
                self.result_processor.add_result(result)

        json_file = f"results_{self.domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        csv_file = f"results_{self.domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.result_processor.save_results(json_file, csv_file)
        print(f"Results saved to {json_file} and {csv_file}")

    def run_nuclei(self, ip: str, port: int) -> List[Dict]:
        try:
            output_file = f"nuclei_{ip}_{port}.jsonl"
            cmd = [
                "nuclei", "-u", f"http://{ip}:{port}" if port != 443 else f"https://{ip}",
                "-t", "cves/", "-t", "technologies/", "-jsonl", "-o", output_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            findings = []
            with open(output_file, "r") as f:
                for line in f:
                    findings.append(json.loads(line.strip()))
            return findings
        except Exception as e:
            logging.error(f"Nuclei scan failed for {ip}:{port}: {e}")
            return []

def parse_ports(port_str: str) -> List[int]:
    ports = []
    for part in port_str.split(','):
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                ports.extend(range(start, end + 1))
            except ValueError:
                continue
        else:
            try:
                ports.append(int(part))
            except ValueError:
                continue
    return sorted(list(set(ports)))

def main():
    parser = argparse.ArgumentParser(description="Ultra-Modular Cloudflare Origin IP Bypass v5 - God-Tier")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("wordlist", help="Path to subdomain wordlist file")
    parser.add_argument("--ports", help="Comma-separated ports or range (e.g., 80,443 or 1-1000)", default="80,443,8080")
    parser.add_argument("--tls-fingerprint", action="store_true", help="Enable TLS fingerprinting for WAF/CDN bypass")
    parser.add_argument("--nuclei", action="store_true", help="Enable Nuclei vulnerability scanning")
    parser.add_argument("--proxy-file", help="Path to proxy list file (one proxy per line)", default=None)
    parser.add_argument("--shodan-api", help="Shodan API key for passive enumeration", default=None)
    parser.add_argument("--use-tor", action="store_true", help="Use Tor for proxy rotation")
    args = parser.parse_args()

    if not is_valid_domain(args.domain):
        print("Error: Domain tidak valid")
        return

    if not Path(args.wordlist).is_file():
        print(f"Error: File wordlist '{args.wordlist}' tidak ditemukan")
        return

    ports = parse_ports(args.ports)
    if not ports:
        print("Error: Port tidak valid")
        return

    scanner = Scanner(args.domain, args.wordlist, ports, args.proxy_file, args.shodan_api, args.use_tor)
    try:
        asyncio.run(scanner.run(args.tls_fingerprint, args.nuclei))
    except KeyboardInterrupt:
        print("\nScan dihentikan oleh pengguna")
        logging.info("Scan interrupted by user")

if __name__ == "__main__":
    main()
