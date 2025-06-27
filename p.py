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
from typing import List, Tuple, Dict
import random
import string
import subprocess
import ssl
import sys
import requests
from urllib.parse import urlencode
from itertools import permutations
import time
from jinja2 import Environment, FileSystemLoader
from collections import defaultdict

# Setup logging
logging.basicConfig(
    filename=f'bypass_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Daftar rentang IP dan org name CDN
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
    "Cloudflare": ["cf-ray", "cf-cache-status", "cf-chl-bypass"],
    "Akamai": ["akamai-grn", "x-akamai-transformed"],
    "Amazon": ["x-amz-cf-id", "x-amz-cf-pop"]
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]
HTTP_METHODS = ["GET", "HEAD", "OPTIONS"]
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

async def detect_wildcard(domain: str, resolver: aiodns.DNSResolver) -> Tuple[bool, set]:
    wildcard_ips = set()
    for random_sub in RANDOM_SUBDOMAINS:
        try:
            result = await resolver.gethostbyname(f"{random_sub}.{domain}", socket.AF_INET)
            wildcard_ips.update(result.addresses)
        except:
            continue
    return bool(wildcard_ips), wildcard_ips

async def get_passive_subdomains(domain: str, api_key: str = None) -> List[str]:
    if not api_key:
        logging.info("No SecurityTrails API key provided, skipping passive DNS")
        return []
    try:
        headers = {"APIKEY": api_key}
        response = requests.get(f"https://api.securitytrails.com/v1/domain/{domain}/subdomains", headers=headers)
        if response.status_code == 200:
            data = response.json()
            return [f"{sub}.{domain}" for sub in data.get("subdomains", [])]
        else:
            logging.error(f"SecurityTrails API error: {response.status_code}")
            return []
    except Exception as e:
        logging.error(f"Passive DNS lookup failed: {e}")
        return []

def generate_permutations(wordlist: List[str]) -> List[str]:
    perms = set()
    for word in wordlist[:1000]:
        for perm in permutations(word.split("-"), r=2):
            perms.add("-".join(perm))
    return list(perms)

async def resolve_dns(subdomain: str, resolver: aiodns.DNSResolver, semaphore: asyncio.Semaphore, record_types: List[str] = ["A", "AAAA", "CNAME", "MX"]) -> Dict:
    async with semaphore:
        results = {}
        for rtype in record_types:
            try:
                if rtype == "MX":
                    answers = await resolver.query(subdomain, rtype)
                    results[rtype] = [str(ans.host) for ans in answers]
                else:
                    result = await resolver.gethostbyname(subdomain, socket.AF_INET if rtype == "A" else socket.AF_INET6 if rtype == "AAAA" else socket.AF_INET)
                    results[rtype] = result.addresses
            except Exception as e:
                results[rtype] = []
                logging.debug(f"Failed to resolve {subdomain} ({rtype}): {e}")
        return results

def lookup_asn(ip: str) -> Dict:
    if is_private_ip(ip):
        logging.info(f"Skipping ASN lookup for private IP: {ip}")
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
    except ImportError:
        logging.warning("ipwhois not installed, falling back to whois CLI")
    except Exception as e:
        logging.error(f"RDAP lookup failed for {ip}: {e}")
    
    try:
        result = subprocess.run(
            ["whois", ip],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.lower()
        asn = org = country = "-"
        for line in output.splitlines():
            if "aut-num:" in line or "origin:" in line:
                asn = line.split(":")[1].strip()
            elif "org-name:" in line or "organization:" in line:
                org = line.split(":")[1].strip()
            elif "country:" in line:
                country = line.split(":")[1].strip()
        return {"asn": asn, "org": org, "country": country}
    except Exception as e:
        logging.error(f"Whois CLI lookup failed for {ip}: {e}")
        return {"asn": "-", "org": "-", "country": "-"}

def compute_ja3_fingerprint(context: ssl.SSLContext) -> str:
    try:
        ciphers = context.get_ciphers()
        cipher_ids = [str(cipher["id"]) for cipher in ciphers]
        return f"ja3:771,{'-'.join(cipher_ids[:3])},..."
    except Exception as e:
        logging.error(f"JA3 computation failed: {e}")
        return "ja3:unknown"

def get_random_headers() -> Dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": random.choice([
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "application/json, text/plain, */*"
        ]),
        "Accept-Language": random.choice(["en-US,en;q=0.5", "id-ID,id;q=0.9,en;q=0.8"]),
        "Connection": "keep-alive",
        "X-Forwarded-For": f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}",
        "Cookie": f"session={''.join(random.choices(string.ascii_lowercase, k=10))}" if random.random() > 0.5 else ""
    }

def calculate_subdomain_score(result: Dict) -> int:
    """Skor subdomain berdasarkan nilai: non-CDN, port terbuka, HTTP status"""
    score = 0
    if not result["cdn"]["is_cdn"]:
        score += 50
    if result.get("http", {}).get("status") == 200:
        score += 30
    if result.get("http", {}).get("port") in [80, 443]:
        score += 20
    if result.get("nuclei_findings"):
        score += len(result["nuclei_findings"]) * 10
    return score

async def http_fingerprint(ip: str, port: int, session: aiohttp.ClientSession, use_tls_fingerprint: bool = False, proxy: str = None, rate_limiter: Dict = None) -> Dict:
    url = f"http://{ip}:{port}" if port != 443 else f"https://{ip}"
    if random.random() > 0.5:
        url += "?" + urlencode({f"q{random.randint(1, 100)}": random.randint(1, 1000)})
    
    headers = get_random_headers()
    method = random.choice(HTTP_METHODS)
    result = {
        "port": port,
        "status": None,
        "headers": {},
        "title": "-",
        "final_url": "-",
        "tls_fingerprint": "-",
        "http2": False,
        "cdn_detected": "",
        "cloudflare_bypass": False,
        "tech_stack": []
    }

    try:
        if rate_limiter and rate_limiter["last_429"] > time.time() - 60:
            await asyncio.sleep(random.uniform(1, 3))
        else:
            await asyncio.sleep(random.uniform(0.1, 0.5))

        if use_tls_fingerprint and port == 443:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.set_alpn_protocols(["h2", "http/1.1"])
            context.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256")
            async with session.request(method, url, headers=headers, ssl=context, proxy=proxy, timeout=8) as resp:
                result["status"] = resp.status
                result["headers"] = dict(resp.headers)
                result["final_url"] = str(resp.url)
                result["http2"] = resp.version == (2, 0)
                result["tls_fingerprint"] = compute_ja3_fingerprint(context)
                if resp.status == 403 and "cloudflare" in str(resp.headers).lower():
                    result["cloudflare_bypass"] = False
                    logging.warning(f"Cloudflare WAF detected on {ip}:{port}")
                elif resp.status == 429:
                    rate_limiter["last_429"] = time.time()
                    logging.warning(f"Rate limit hit on {ip}:{port}")
                try:
                    text = await resp.text()
                    start = text.lower().find("<title>")
                    end = text.lower().find("</title>")
                    if start != -1 and end != -1:
                        result["title"] = text[start + 7:end].strip()
                    if "cloudflare" in text.lower() and "jschl" in text.lower():
                        result["cloudflare_bypass"] = False
                        logging.warning(f"Cloudflare JS challenge detected on {ip}:{port}")
                except:
                    pass
                for cdn, signatures in CDN_HEADER_SIGNATURES.items():
                    if any(sig in result["headers"] for sig in signatures):
                        result["cdn_detected"] = cdn
                        break
        else:
            async with session.request(method, url, headers=headers, proxy=proxy, timeout=8, allow_redirects=True) as resp:
                result["status"] = resp.status
                result["headers"] = dict(resp.headers)
                result["final_url"] = str(resp.url)
                result["http2"] = resp.version == (2, 0)
                if resp.status == 403 and "cloudflare" in str(resp.headers).lower():
                    result["cloudflare_bypass"] = False
                    logging.warning(f"Cloudflare WAF detected on {ip}:{port}")
                elif resp.status == 429:
                    rate_limiter["last_429"] = time.time()
                    logging.warning(f"Rate limit hit on {ip}:{port}")
                try:
                    text = await resp.text()
                    start = text.lower().find("<title>")
                    end = text.lower().find("</title>")
                    if start != -1 and end != -1:
                        result["title"] = text[start + 7:end].strip()
                    if "cloudflare" in text.lower() and "jschl" in text.lower():
                        result["cloudflare_bypass"] = False
                        logging.warning(f"Cloudflare JS challenge detected on {ip}:{port}")
                except:
                    pass
                for cdn, signatures in CDN_HEADER_SIGNATURES.items():
                    if any(sig in result["headers"] for sig in signatures):
                        result["cdn_detected"] = cdn
                        break
    except Exception as e:
        logging.debug(f"HTTP check failed for {ip}:{port}: {e}")
    return result

def run_nuclei(ip: str, port: int, output_file: str) -> List[Dict]:
    try:
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

def load_proxies(proxy_file: str) -> List[str]:
    if not Path(proxy_file).is_file():
        logging.warning(f"Proxy file '{proxy_file}' tidak ditemukan")
        return []
    with open(proxy_file, "r") as f:
        return [line.strip() for line in f if line.strip()]

def generate_html_report(results: List[Dict], domain: str, output_file: str):
    """Generate HTML dashboard pake Jinja2"""
    env = Environment(loader=FileSystemLoader('.'))
    template = env.from_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Scan Report - {{ domain }}</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            .high { background-color: #ffcccc; }
            .medium { background-color: #ffffcc; }
            .low { background-color: #ccffcc; }
        </style>
    </head>
    <body>
        <h1>Scan Report for {{ domain }}</h1>
        <p>Generated: {{ timestamp }}</p>
        <h2>Summary</h2>
        <p>Total Subdomains: {{ total_subdomains }}</p>
        <p>Non-CDN Subdomains: {{ non_cdn_count }}</p>
        <p>Open Ports: {{ open_ports_count }}</p>
        <h2>Results</h2>
        <table>
            <tr>
                <th>Score</th>
                <th>Subdomain</th>
                <th>IP</th>
                <th>ASN</th>
                <th>Org</th>
                <th>CDN</th>
                <th>Port</th>
                <th>Status</th>
                <th>Title</th>
                <th>HTTP/2</th>
                <th>Tech Stack</th>
            </tr>
            {% for result in results %}
            <tr class="{% if result.score >= 80 %}high{% elif result.score >= 50 %}medium{% else %}low{% endif %}">
                <td>{{ result.score }}</td>
                <td>{{ result.subdomain }}</td>
                <td>{{ result.ip }}</td>
                <td>{{ result.asn.asn }}</td>
                <td>{{ result.asn.org }}</td>
                <td>{{ result.cdn.name or "None" }}</td>
                <td>{{ result.http.port if result.http else "-" }}</td>
                <td>{{ result.http.status if result.http else "-" }}</td>
                <td>{{ result.http.title if result.http else "-" }}</td>
                <td>{{ "Yes" if result.http.http2 else "No" if result.http else "-" }}</td>
                <td>{{ result.http.tech_stack | join(", ") if result.http else "-" }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """)
    
    non_cdn_count = sum(1 for r in results if not r["cdn"]["is_cdn"])
    open_ports_count = sum(1 for r in results if r.get("http", {}).get("status"))
    rendered = template.render(
        domain=domain,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        results=results,
        total_subdomains=len(results),
        non_cdn_count=non_cdn_count,
        open_ports_count=open_ports_count
    )
    with open(output_file, "w") as f:
        f.write(rendered)

def save_results(results: List[Dict], json_file: str, csv_file: str, html_file: str, domain: str):
    # Tambah skor dan tech stack
    for result in results:
        result["score"] = calculate_subdomain_score(result)
        if result.get("nuclei_findings"):
            result["http"]["tech_stack"] = [f["info"]["name"] for f in result["nuclei_findings"] if f["template-id"] == "tech-detect"]
    
    # Cluster IP berdasarkan ASN
    asn_clusters = defaultdict(list)
    for result in results:
        asn = result["asn"]["asn"]
        asn_clusters[asn].append(result["ip"])
    
    # Tambah summary ke JSON
    summary = {
        "total_subdomains": len(results),
        "non_cdn_count": sum(1 for r in results if not r["cdn"]["is_cdn"]),
        "open_ports_count": sum(1 for r in results if r.get("http", {}).get("status")),
        "asn_clusters": {asn: list(set(ips)) for asn, ips in asn_clusters.items()}
    }
    
    with open(json_file, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "score", "subdomain", "ip", "asn", "org", "cdn_name", "port", "status",
            "server", "title", "final_url", "http2", "tls_fingerprint", "cdn_detected", 
            "cloudflare_bypass", "tech_stack", "nuclei_findings"
        ])
        writer.writeheader()
        for result in results:
            writer.writerow({
                "score": result["score"],
                "subdomain": result["subdomain"],
                "ip": result["ip"],
                "asn": result["asn"]["asn"],
                "org": result["asn"]["org"],
                "cdn_name": result["cdn"]["name"],
                "port": result.get("http", {}).get("port", "-"),
                "status": result.get("http", {}).get("status", "-"),
                "server": result.get("http", {}).get("headers", {}).get("Server", "-"),
                "title": result.get("http", {}).get("title", "-"),
                "final_url": result.get("http", {}).get("final_url", "-"),
                "http2": str(result.get("http", {}).get("http2", False)),
                "tls_fingerprint": result.get("http", {}).get("tls_fingerprint", "-"),
                "cdn_detected": result.get("http", {}).get("cdn_detected", "-"),
                "cloudflare_bypass": str(result.get("http", {}).get("cloudflare_bypass", "-")),
                "tech_stack": ",".join(result.get("http", {}).get("tech_stack", [])),
                "nuclei_findings": json.dumps(result.get("nuclei_findings", []))
            })
    
    generate_html_report(results, domain, html_file)

async def process_batch(subdomains: List[str], resolver: aiodns.DNSResolver, semaphore: asyncio.Semaphore, wildcard_ips: set) -> List[Dict]:
    tasks = [resolve_dns(sub, resolver, semaphore) for sub in subdomains]
    resolved = await asyncio.gather(*tasks, return_exceptions=True)
    results = []
    for sub, dns_records in zip(subdomains, resolved):
        if isinstance(dns_records, Exception):
            logging.error(f"DNS resolution failed for {sub}: {dns_records}")
            continue
        valid_records = {k: v for k, v in dns_records.items() if v}
        if valid_records:
            for ip in valid_records.get("A", []) + valid_records.get("AAAA", []):
                if ip not in wildcard_ips:
                    asn_info = lookup_asn(ip)
                    is_cdn, cdn_name = is_cdn_ip(ip, asn_info)
                    results.append({
                        "subdomain": sub,
                        "ip": ip,
                        "dns_records": valid_records,
                        "cdn": {"is_cdn": is_cdn, "name": cdn_name},
                        "asn": asn_info
                    })
    return results

async def main(domain: str, wordlist_path: str, ports: str, use_tls_fingerprint: bool, use_nuclei: bool, securitytrails_api: str = None, proxy_file: str = None):
    print("⚠️ PERINGATAN: Gunakan skrip ini hanya pada domain yang Anda miliki atau dengan izin eksplisit!")
    logging.info(f"Starting scan for domain: {domain}")

    if not is_valid_domain(domain):
        print("Error: Domain tidak valid")
        return

    if not Path(wordlist_path).is_file():
        print(f"Error: File wordlist '{wordlist_path}' tidak ditemukan")
        return

    target_ports = parse_ports(ports)
    if not target_ports:
        print("Error: Port tidak valid")
        return

    proxies = load_proxies(proxy_file) if proxy_file else []
    if proxies:
        logging.info(f"Loaded {len(proxies)} proxies")

    with open(wordlist_path, "r") as f:
        words = [line.strip() for line in f if line.strip()]
    subdomains = [f"{w}.{domain}" for w in words]
    if securitytrails_api:
        passive_subdomains = await get_passive_subdomains(domain, securitytrails_api)
        subdomains.extend(passive_subdomains)
        logging.info(f"Added {len(passive_subdomains)} passive subdomains from SecurityTrails")
    permuted_subdomains = [f"{p}.{domain}" for p in generate_permutations(words)]
    subdomains.extend(permuted_subdomains)
    subdomains = list(set(subdomains))
    logging.info(f"Added {len(permuted_subdomains)} permuted subdomains")

    resolver = aiodns.DNSResolver()
    semaphore = asyncio.Semaphore(100)
    rate_limiter = {"last_429": 0}
    has_wildcard, wildcard_ips = await detect_wildcard(domain, resolver)
    if has_wildcard:
        print(f"Wildcard DNS detected for {domain}. IPs: {wildcard_ips}")
        logging.info(f"Wildcard DNS detected: {wildcard_ips}")

    batch_size = 1000
    all_results = []
    for i in range(0, len(subdomains), batch_size):
        batch = subdomains[i:i + batch_size]
        try:
            batch_results = await process_batch(batch, resolver, semaphore, wildcard_ips)
            all_results.extend(batch_results)
            print(f"Processed {min(i + batch_size, len(subdomains))}/{len(subdomains)} subdomains")
        except Exception as e:
            logging.error(f"Batch processing failed: {e}")
            continue

    if not all_results:
        print("Tidak ditemukan subdomain valid di luar wildcard/CDN")
        logging.info("No valid subdomains found")
        return

    async with aiohttp.ClientSession() as session:
        for result in all_results:
            ip = result["ip"]
            for port in target_ports:
                proxy = random.choice(proxies) if proxies else None
                try:
                    http_result = await http_fingerprint(ip, port, session, use_tls_fingerprint, proxy, rate_limiter)
                    if http_result["status"] and http_result["status"] not in [403, 429]:
                        result["http"] = http_result
                        if use_nuclei:
                            nuclei_output = f"nuclei_{ip}_{port}.jsonl"
                            result["nuclei_findings"] = run_nuclei(ip, port, nuclei_output)
                        break
                except Exception as e:
                    logging.error(f"HTTP fingerprint failed for {ip}:{port}: {e}")
                    continue

    json_file = f"results_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    csv_file = f"results_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    html_file = f"results_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    save_results(all_results, json_file, csv_file, html_file, domain)
    print(f"Results saved to {json_file}, {csv_file}, and {html_file}")
    logging.info(f"Results saved to {json_file}, {csv_file}, and {html_file}")

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Elite-Level Cloudflare Origin IP Bypass")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("wordlist", help="Path to subdomain wordlist file")
    parser.add_argument("--ports", help="Comma-separated ports or range (e.g., 80,443 or 1-1000)", default="80,443,8080")
    parser.add_argument("--tls-fingerprint", action="store_true", help="Enable TLS fingerprinting for WAF/CDN bypass")
    parser.add_argument("--nuclei", action="store_true", help="Enable Nuclei vulnerability scanning")
    parser.add_argument("--securitytrails-api", help="SecurityTrails API key for passive DNS", default=None)
    parser.add_argument("--proxy-file", help="Path to proxy list file (one proxy per line)", default=None)
    args = parser.parse_args()

    try:
        asyncio.run(main(args.domain, args.wordlist, args.ports, args.tls_fingerprint, args.nuclei, args.securitytrails_api, args.proxy_file))
    except KeyboardInterrupt:
        print("\nScan dihentikan oleh pengguna")
        logging.info("Scan interrupted by user")
