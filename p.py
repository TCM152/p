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
from datetime import datetime
from scapy.all import *
from scapy.layers.tls.all import *
import hashlib

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
        print("[WARNING] No SecurityTrails API key provided, skipping passive DNS")
        return []
    try:
        headers = {"APIKEY": api_key}
        response = requests.get(f"https://api.securitytrails.com/v1/domain/{domain}/subdomains", headers=headers)
        if response.status_code == 200:
            data = response.json()
            subdomains = [f"{sub}.{domain}" for sub in data.get("subdomains", [])]
            print(f"[INFO] Added {len(subdomains)} passive subdomains from SecurityTrails")
            return subdomains
        else:
            print(f"[ERROR] SecurityTrails API error: {response.status_code}")
            return []
    except Exception as e:
        print(f"[ERROR] Passive DNS lookup failed: {e}")
        return []

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
        print(f"[WARNING] Skipping ASN lookup for private IP: {ip}")
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
        print("[WARNING] ipwhois not installed, falling back to whois CLI")
    except Exception as e:
        print(f"[ERROR] RDAP lookup failed for {ip}: {e}")
    
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
        print(f"[ERROR] Whois CLI lookup failed for {ip}: {e}")
        return {"asn": "-", "org": "-", "country": "-"}

def compute_ja3_fingerprint(host: str, port: int = 443) -> str:
    """Compute JA3 fingerprint using Scapy"""
    try:
        # Konfigurasi TLS ClientHello
        conf.verb = 0  # Suppress Scapy output
        sport = random.randint(1024, 65535)
        packet = IP(dst=host) / TCP(sport=sport, dport=port, flags="S") / TLS(
            type="client_hello",
            version="TLS_1_2",
            ciphers=[
                TLS_RSA_WITH_AES_128_GCM_SHA256,
                TLS_RSA_WITH_AES_256_GCM_SHA384,
                TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
            ],
            exts=[
                TLS_Ext_ServerName(servername=host),
                TLS_Ext_SupportedGroups(groups=["secp256r1", "secp384r1"]),
                TLS_Ext_SignatureAlgorithms(sig_algs=["rsa_pkcs1_sha256"]),
                TLS_Ext_SupportedVersions(versions=["TLS_1_3", "TLS_1_2"])
            ]
        )
        
        # Kirim packet dan ambil response
        response = sr1(packet, timeout=2, verbose=0)
        if not response or not response.haslayer(TLS):
            return "ja3:unknown"

        # Ambil ClientHello fields
        tls = packet[TLS]
        version = str(tls.version)
        ciphers = "-".join([str(c) for c in tls.ciphers]) if tls.ciphers else ""
        extensions = "-".join([str(ext.type) for ext in tls.exts]) if tls.exts else ""
        curves = "-".join([str(g) for g in tls.exts[1].groups]) if len(tls.exts) > 1 else ""
        
        # Gabungin jadi JA3 string
        ja3_string = f"{version},{ciphers},{extensions},{curves},"
        ja3_hash = hashlib.md5(ja3_string.encode()).hexdigest()
        return f"ja3:{ja3_string}|{ja3_hash}"
    except Exception as e:
        print(f"[ERROR] JA3 computation failed for {host}:{port}: {e}")
        return "ja3:unknown"

async def http_fingerprint(ip: str, port: int, session: aiohttp.ClientSession, use_tls_fingerprint: bool = False) -> Dict:
    url = f"http://{ip}:{port}" if port != 443 else f"https://{ip}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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
        if use_tls_fingerprint and port == 443:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.set_alpn_protocols(["h2", "http/1.1"])
            context.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256")
            async with session.get(url, headers=headers, ssl=context, timeout=8) as resp:
                result["status"] = resp.status
                result["headers"] = dict(resp.headers)
                result["final_url"] = str(resp.url)
                result["http2"] = resp.version == (2, 0)
                result["tls_fingerprint"] = compute_ja3_fingerprint(ip, port)
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
            async with session.get(url, headers=headers, timeout=8, allow_redirects=True) as resp:
                result["status"] = resp.status
                result["headers"] = dict(resp.headers)
                result["final_url"] = str(resp.url)
                result["http2"] = resp.version == (2, 0)
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
        print(f"[ERROR] HTTP check failed for {ip}:{port}: {e}")
    return result

def run_nuclei(ip: str, port: int, output_file: str) -> List[Dict]:
    try:
        cmd = [
            "nuclei", "-u", f"http://{ip}:{port}" if port != 443 else f"https://{ip}",
            "-tہ: red]Nuclei scan failed for {ip}:{port}: {e}[/red]")
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

async def process_batch(subdomains: List[str], resolver: aiodns.DNSResolver, semaphore: asyncio.Semaphore, wildcard_ips: set) -> List[Dict]:
    results = []
    for i, sub in enumerate(subdomains, 1):
        print(f"[INFO] Processing subdomain {i}/{len(subdomains)}: {sub}")
        dns_records = await resolve_dns(sub, resolver, semaphore)
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
                "cdn_name": result["cdn"]["name"] or "-",
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

def display_results(results: List[Dict]):
    for result in results:
        print(f"Subdomain: {result['subdomain']}")
        print(f"IP: {result['ip']}")
        print(f"ASN: {result['asn']['asn']}")
        print(f"Org: {result['asn']['org']}")
        print(f"CDN: {result['cdn']['name'] or '-'}")
        print(f"Port: {result.get('http', {}).get('port', '-')}")
        print(f"Status: {result.get('http', {}).get('status', '-')}")
        print(f"Server: {result.get('http', {}).get('headers', {}).get('Server', '-')}")
        print(f"Title: {result.get('http', {}).get('title', '-')}")
        print(f"Final URL: {result.get('http', {}).get('final_url', '-')}")
        print(f"HTTP/2: {result.get('http', {}).get('http2', False)}")
        print(f"TLS Fingerprint: {result.get('http', {}).get('tls_fingerprint', '-')}")
        print(f"CDN Detected: {result.get('http', {}).get('cdn_detected', '-')}")
        print("-" * 50)

async def main(domain: str, wordlist_path: str, ports: str, use_tls_fingerprint: bool, use_nuclei: bool, securitytrails_api: str = None):
    print("WARNING: Gunakan skrip ini hanya pada domain yang Anda miliki atau dengan izin eksplisit!")

    if not is_valid_domain(domain):
        print("ERROR: Domain tidak valid")
        return

    if not Path(wordlist_path).is_file():
        print(f"ERROR: File wordlist '{wordlist_path}' tidak ditemukan")
        return

    target_ports = parse_ports(ports)
    if not target_ports:
        print("ERROR: Port tidak valid")
        return

    with open(wordlist_path, "r") as f:
        words = [line.strip() for line in f if line.strip()]
    subdomains = [f"{w}.{domain}" for w in words]
    if securitytrails_api:
        passive_subdomains = await get_passive_subdomains(domain, securitytrails_api)
        subdomains.extend(passive_subdomains)
        subdomains = list(set(subdomains))

    resolver = aiodns.DNSResolver()
    semaphore = asyncio.Semaphore(100)
    has_wildcard, wildcard_ips = await detect_wildcard(domain, resolver)
    if has_wildcard:
        print(f"WARNING: Wildcard DNS detected for {domain}. IPs: {wildcard_ips}")
        logging.info(f"Wildcard DNS detected: {wildcard_ips}")

    all_results = []
    for i in range(0, len(subdomains), 1000):
        batch = subdomains[i:i + 1000]
        batch_results = await process_batch(batch, resolver, semaphore, wildcard_ips)
        all_results.extend(batch_results)

    if not all_results:
        print("ERROR: Tidak ditemukan subdomain valid di luar wildcard/CDN")
        logging.info("No valid subdomains found")
        return

    async with aiohttp.ClientSession() as session:
        for result in all_results:
            ip = result["ip"]
            for port in target_ports:
                http_result = await http_fingerprint(ip, port, session, use_tls_fingerprint)
                if http_result["status"]:
                    result["http"] = http_result
                    if use_nuclei:
                        nuclei_output = f"nuclei_{ip}_{port}.jsonl"
                        result["nuclei_findings"] = run_nuclei(ip, port, nuclei_output)
                    break

    # Tampilin hasil
    display_results(all_results)

    # Simpan hasil
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = f"results_{domain}_{timestamp}.json"
    csv_file = f"results_{domain}_{timestamp}.csv"
    save_results(all_results, json_file, csv_file)
    print(f"INFO: Results saved to {json_file} and {csv_file}")
    logging.info(f"Results saved to {json_file} and {csv_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloudflare Origin IP Bypass - Scapy JA3")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("wordlist", help="Path to subdomain wordlist file")
    parser.add_argument("--ports", help="Comma-separated ports or range (e.g., 80,443 or 1-1000)", default="80,443,8080")
    parser.add_argument("--tls-fingerprint", action="store_true", help="Enable TLS fingerprinting for WAF/CDN bypass")
    parser.add_argument("--nuclei", action="store_true", help="Enable Nuclei vulnerability scanning")
    parser.add_argument("--securitytrails-api", help="SecurityTrails API key for passive DNS", default=None)
    args = parser.parse_args()

    try:
        asyncio.run(main(args.domain, args.wordlist, args.ports, args.tls_fingerprint, args.nuclei, args.securitytrails_api))
    except KeyboardInterrupt:
        print("\nERROR: Scan dihentikan oleh pengguna")
        logging.info("Scan interrupted by user")
