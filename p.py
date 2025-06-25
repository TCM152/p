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
from shodan import Shodan

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
    "Cloudflare": ["cf-ray", "cf-cache-status"],
    "Akamai": ["akamai-grn", "x-akamai-transformed"],
    "Amazon": ["x-amz-cf-id", "x-amz-cf-pop"]
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
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

def run_massdns(domain: str, wordlist_path: str, resolver_path: str = "resolvers.txt") -> List[Dict]:
    """Jalankan massdns untuk brute-force subdomain"""
    try:
        output_file = f"massdns_{domain}.txt"
        cmd = [
            "massdns", "-r", resolver_path, "-t", "A", "-o", "S", "-w", output_file,
            wordlist_path
        ]
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

def run_dnsx(domain: str, input_file: str) -> List[str]:
    """Filter wildcard dengan dnsx"""
    try:
        output_file = f"dnsx_{domain}.txt"
        cmd = ["dnsx", "-wd", domain, "-l", input_file, "-o", output_file]
        subprocess.run(cmd, check=True, timeout=300)
        with open(output_file, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"dnsx failed: {e}")
        return []

def run_httpx(subdomains: List[str], ports: List[int]) -> List[Dict]:
    """Cek HTTP/HTTPS dengan httpx"""
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

def run_shodan_search(domain: str, api_key: str) -> List[Dict]:
    """Cari subdomain/IP via Shodan"""
    try:
        shodan = Shodan(api_key)
        results = shodan.search(f"hostname:{domain}", limit=100)
        subdomains = []
        for result in results["matches"]:
            ip = result.get("ip_str")
            hostnames = result.get("hostnames", [])
            port = result.get("port")
            for hostname in hostnames:
                subdomains.append({
                    "subdomain": hostname,
                    "ip": ip,
                    "port": port
                })
        return subdomains
    except Exception as e:
        logging.error(f"Shodan search failed: {e}")
        return []

async def http_fingerprint(ip: str, port: int, session: aiohttp.ClientSession, use_tls_fingerprint: bool = False, proxy: str = None) -> Dict:
    url = f"http://{ip}:{port}" if port != 443 else f"https://{ip}"
    if random.random() > 0.5:
        url += "?" + urlencode({f"q{random.randint(1, 100)}": random.randint(1, 1000)})
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": random.choice(["text/html,application/xhtml+xml", "application/json"]),
        "Accept-Language": random.choice(["en-US,en;q=0.5", "id-ID,id;q=0.9"])
    }
    result = {
        "port": port,
        "status": None,
        "headers": {},
        "title": "-",
        "final_url": "-",
        "tls_fingerprint": "-",
        "http2": False,
        "cdn_detected": ""
    }

    try:
        await asyncio.sleep(random.uniform(0.1, 0.5))
        if use_tls_fingerprint and port == 443:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.set_alpn_protocols(["h2", "http/1.1"])
            context.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256")
            async with session.get(url, headers=headers, ssl=context, proxy=proxy, timeout=8) as resp:
                result["status"] = resp.status
                result["headers"] = dict(resp.headers)
                result["final_url"] = str(resp.url)
                result["http2"] = resp.version == (2, 0)
                result["tls_fingerprint"] = compute_ja3_fingerprint(context)
                if resp.status in [403, 429]:
                    logging.warning(f"WAF block detected on {ip}:{port} (Status: {resp.status})")
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
        else:
            async with session.get(url, headers=headers, proxy=proxy, timeout=8, allow_redirects=True) as resp:
                result["status"] = resp.status
                result["headers"] = dict(resp.headers)
                result["final_url"] = str(resp.url)
                result["http2"] = resp.version == (2, 0)
                if resp.status in [403, 429]:
                    logging.warning(f"WAF block detected on {ip}:{port} (Status: {resp.status})")
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
    except Exception as e:
        logging.debug(f"HTTP check failed for {ip}:{port}: {e}")
    return result

def compute_ja3_fingerprint(context: ssl.SSLContext) -> str:
    try:
        ciphers = context.get_ciphers()
        cipher_ids = [str(cipher["id"]) for cipher in ciphers]
        return f"ja3:771,{'-'.join(cipher_ids[:3])},..."
    except Exception as e:
        logging.error(f"JA3 computation failed: {e}")
        return "ja3:unknown"

def save_results(results: List[Dict], json_file: str, csv_file: str):
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "subdomain", "ip", "asn", "org", "cdn_name", "port", "status",
            "server", "title", "final_url", "http2", "tls_fingerprint", "cdn_detected", "nuclei_findings"
        ])
        writer.writeheader()
        for result in results:
            writer.writerow({
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
                "nuclei_findings": json.dumps(result.get("nuclei_findings", []))
            })

async def main(domain: str, wordlist_path: str, ports: str, use_tls_fingerprint: bool, use_nuclei: bool, securitytrails_api: str = None, proxy_file: str = None, shodan_api: str = None):
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

    # Load proxies
    proxies = load_proxies(proxy_file) if proxy_file else []
    if proxies:
        logging.info(f"Loaded {len(proxies)} proxies")

    # Step 1: Brute-force dengan massdns
    massdns_results = run_massdns(domain, wordlist_path)
    logging.info(f"MassDNS found {len(massdns_results)} subdomains")

    # Step 2: Filter wildcard dengan dnsx
    massdns_input = f"massdns_input_{domain}.txt"
    with open(massdns_input, "w") as f:
        f.write("\n".join([r["subdomain"] for r in massdns_results]))
    valid_subdomains = run_dnsx(domain, massdns_input)
    logging.info(f"dnsx filtered {len(valid_subdomains)} valid subdomains")

    # Step 3: Augment dengan Shodan
    shodan_subdomains = run_shodan_search(domain, shodan_api) if shodan_api else []
    subdomains = valid_subdomains + [s["subdomain"] for s in shodan_subdomains]
    subdomains = list(set(subdomains))  # Deduplikasi
    logging.info(f"Total subdomains after Shodan: {len(subdomains)}")

    # Step 4: Cek HTTP/HTTPS dengan httpx
    httpx_results = run_httpx(subdomains, target_ports)
    logging.info(f"httpx found {len(httpx_results)} live subdomains")

    # Step 5: HTTP fingerprinting tambahan
    all_results = []
    async with aiohttp.ClientSession() as session:
        for httpx_result in httpx_results:
            ip = next((r["ip"] for r in massdns_results if r["subdomain"] in httpx_result["url"]), None)
            if not ip:
                continue
            asn_info = lookup_asn(ip)
            is_cdn, cdn_name = is_cdn_ip(ip, asn_info)
            http_result = await http_fingerprint(ip, httpx_result["port"], session, use_tls_fingerprint, random.choice(proxies) if proxies else None)
            result = {
                "subdomain": httpx_result["url"].split("://")[1].split(":")[0],
                "ip": ip,
                "dns_records": {"A": [ip]},
                "cdn": {"is_cdn": is_cdn, "name": cdn_name},
                "asn": asn_info,
                "http": http_result
            }
            if use_nuclei:
                nuclei_output = f"nuclei_{ip}_{httpx_result['port']}.jsonl"
                result["nuclei_findings"] = run_nuclei(ip, httpx_result["port"], nuclei_output)
            all_results.append(result)

    json_file = f"results_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    csv_file = f"results_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    save_results(all_results, json_file, csv_file)
    print(f"Results saved to {json_file} and {csv_file}")
    logging.info(f"Results saved to {json_file} and {csv_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Supercharged Cloudflare Origin IP Bypass v3 - Ninja Wildcard Buster")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("wordlist", help="Path to subdomain wordlist file")
    parser.add_argument("--ports", help="Comma-separated ports or range (e.g., 80,443 or 1-1000)", default="80,443,8080")
    parser.add_argument("--tls-fingerprint", action="store_true", help="Enable TLS fingerprinting for WAF/CDN bypass")
    parser.add_argument("--nuclei", action="store_true", help="Enable Nuclei vulnerability scanning")
    parser.add_argument("--securitytrails-api", help="SecurityTrails API key for passive DNS", default=None)
    parser.add_argument("--proxy-file", help="Path to proxy list file (one proxy per line)", default=None)
    parser.add_argument("--shodan-api", help="Shodan API key for passive enumeration", default=None)
    args = parser.parse_args()

    try:
        asyncio.run(main(args.domain, args.wordlist, args.ports, args.tls_fingerprint, args.nuclei, args.securitytrails_api, args.proxy_file, args.shodan_api))
    except KeyboardInterrupt:
        print("\nScan dihentikan oleh pengguna")
        logging.info("Scan interrupted by user")
