import os
import requests
import sys

def check_proxy():
    # 1. Get Proxy from Environment Variable
    raw_proxy = os.environ.get("PROXY_TO_CHECK")

    if not raw_proxy:
        print("❌ Error: No proxy provided.")
        print("Please set the 'MY_PROXY_URL' secret in GitHub or provide an input.")
        sys.exit(1)

    # --- NEW: Format Handling ---
    # If the user inputs "67.43.228.253:24315", we must add the protocol.
    if "://" not in raw_proxy:
        print(f"ℹ️  Raw IP:PORT format detected. Defaulting to HTTP.")
        proxy_url = f"http://{raw_proxy}"
    else:
        proxy_url = raw_proxy

    # Mask the IP for logs slightly (privacy)
    safe_print_url = proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url
    print(f"🔄 Connecting via: {safe_print_url} ...")

    # 2. Configure Proxy Dictionary
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }

    # 3. Define the Target API
    target_url = "http://ip-api.com/json"

    try:
        # 4. Make the Request
        print("⏳ Querying IP database...")
        # 10s timeout is usually enough for a working proxy
        response = requests.get(target_url, proxies=proxies, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # 5. Extract Data
            ip = data.get("query", "Unknown")
            isp = data.get("isp", "Unknown")
            org = data.get("org", "Unknown")
            country = data.get("country", "Unknown")
            
            # 6. Analyze Results
            print("\n" + "="*30)
            print(f"🔎 PROXY ANALYSIS REPORT")
            print("="*30)
            print(f"🌍 Country:      {country}")
            print(f"🔢 IP Address:   {ip}")
            print(f"🏢 ISP Name:     {isp}")
            print(f"💼 Organization: {org}")
            print("-" * 30)

            # Heuristic Detection
            dc_keywords = [
                'Amazon', 'AWS', 'Google', 'Microsoft', 'Azure', 
                'DigitalOcean', 'Linode', 'Vultr', 'Choopa', 
                'Datacenter', 'Hosting', 'M247', 'Leaseweb', 'Hetzner',
                'Alibaba', 'Oracle', 'OVH', 'GCP', 'Hostinger'
            ]
            
            is_datacenter = any(k.lower() in isp.lower() or k.lower() in org.lower() for k in dc_keywords)
            
            if is_datacenter:
                print("⚠️  VERDICT: DATACENTER PROXY DETECTED")
                print("   (This IP belongs to a known hosting provider)")
            elif isp == org:
                print("❓ VERDICT: LIKELY DATACENTER / BUSINESS")
                print("   (ISP and Org are identical, typical for commercial IPs)")
            else:
                print("✅ VERDICT: LIKELY RESIDENTIAL")
                print("   (ISP appears to be a standard internet provider)")
                
            print("="*30 + "\n")

        else:
            print(f"❌ API Error: Received status code {response.status_code}")
            sys.exit(1)

    except requests.exceptions.ProxyError:
        print("❌ CONNECTION FAILED: The proxy refused connection or credentials are wrong.")
        sys.exit(1)
    except requests.exceptions.ConnectTimeout:
        print("❌ TIMEOUT: The proxy is dead or too slow.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_proxy()

