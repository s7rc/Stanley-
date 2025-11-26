import requests
import sys
import time

# Output file for good proxies
OUTPUT_FILE = "residential.txt"

# ANSI Colors for Logs
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def save_proxy(proxy):
    with open(OUTPUT_FILE, "a") as f:
        f.write(proxy + "\n")

def check_proxy(raw_proxy):
    raw_proxy = raw_proxy.strip()
    if not raw_proxy:
        return

    # Auto-format: Add http:// if missing for the request
    if "://" not in raw_proxy:
        proxy_url = f"http://{raw_proxy}"
    else:
        proxy_url = raw_proxy

    proxies = {"http": proxy_url, "https": proxy_url}
    
    # Using ip-api.com to look up the ISP Name
    target_url = "http://ip-api.com/json"

    print(f"Testing: {raw_proxy.ljust(25)}", end=" ")
    sys.stdout.flush()

    try:
        response = requests.get(target_url, proxies=proxies, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'fail':
                 print(f"{RED}FAILED (API Error){RESET}")
                 return

            isp = data.get("isp", "Unknown")
            org = data.get("org", "Unknown")
            country = data.get("country", "Unknown")
            
            # Known Datacenter Keywords
            dc_keywords = [
                'Amazon', 'AWS', 'Google', 'Microsoft', 'Azure', 'DigitalOcean', 
                'Linode', 'Vultr', 'Choopa', 'Datacenter', 'Hosting', 'M247', 
                'Leaseweb', 'Hetzner', 'Alibaba', 'Oracle', 'OVH', 'GCP', 
                'Hostinger', 'Server', 'Cloud'
            ]
            
            is_datacenter = any(k.lower() in isp.lower() or k.lower() in org.lower() for k in dc_keywords)
            
            if is_datacenter:
                print(f"{YELLOW}DATACENTER{RESET}  [{isp}]")
            elif isp == org:
                print(f"{YELLOW}LIKELY DC{RESET}   [{isp}]")
            else:
                print(f"{GREEN}RESIDENTIAL{RESET} [{isp}] -> SAVED")
                # SAVE THE RAW PROXY (without http:// prefix if it didn't have one)
                save_proxy(raw_proxy)
        else:
            print(f"{RED}HTTP {response.status_code}{RESET}")

    except:
        # If connection fails, just print Dead
        print(f"{RED}DEAD{RESET}")

def main():
    # Clear previous run file
    with open(OUTPUT_FILE, "w") as f:
        f.write("")

    try:
        with open("Proxy.txt", "r") as f:
            proxy_list = f.readlines()
            
        print(f"Loaded {len(proxy_list)} proxies. Checking now...\n")
        
        for proxy in proxy_list:
            check_proxy(proxy)
            # Rate limit protection
            time.sleep(1.2) 
            
    except FileNotFoundError:
        print(f"{RED}Error: Proxy.txt not found!{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()


