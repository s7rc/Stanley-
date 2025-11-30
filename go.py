import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from termcolor import colored
import concurrent.futures
import os
import threading
import sys
import re
import time
import argparse
import zipfile
import datetime
import random
from requests_toolbelt.multipart.encoder import MultipartEncoder

# --- GLOBAL SETTINGS ---
AVAILABLE_FILE = 'availableHotmail.txt'
TAKEN_FILE = 'takenHotmail.txt'
INPUT_FILE = 'emails.txt'
session = None 
file_lock = threading.Lock()
print_lock = threading.Lock()
stats_lock = threading.Lock()

# Stats
checked_count = 0
available_count = 0
taken_count = 0
start_time = None

# Configuration
THREADS = 200
FILTER_ENABLED = False
KEYWORD = ""

# GoFile Settings
GOFILE_ENABLED = False
GOFILE_TOKEN = "YKb1gKOqDJ2TWbfTggRJPU1y31Pi36H9"
GOFILE_FOLDER_ID = "dabd7396-7d74-4072-bf83-3bb3ac30a28d"
BACKUP_INTERVAL_HOURS = 1
IS_RUNNING = True

def banner():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(colored(r'''
  _    _       _                 _ _     _____ _               _             
 | |  | |     | |                (_) |   / ____| |             | |            
 | |__| | ___ | |_ _ __ ___   ___ _| |  | |    | |__   ___  ___| | _____ _ __ 
 |  __  |/ _ \| __| '_ ` _ \ / _ ` | |  | |    | '_ \ / _ \/ __| |/ / _ \ '__|
 | |  | | (_) | |_| | | | | | (_| | |   | |____| | | |  __/ (__|   <  __/ |   
 |_|  |_|\___/ \__|_| |_| |_|\__,_|_|    \_____|_| |_|\___|\___|_|\_\___|_|   
    ''','yellow',attrs=['bold']))
    print(colored("    Ultra High Speed Hotmail Availability Checker", 'white'))
    print(colored("    ---------------------------------------------", 'white'))

def filter_emails():
    """Reads emails.txt, extracts ONLY valid @hotmail.com addresses using Regex."""
    if not os.path.exists(INPUT_FILE):
        print(colored(f"[!] {INPUT_FILE} not found!", 'red'))
        return

    print(colored("\n[*] Scanning file for @hotmail.com addresses...", 'cyan'))
    
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        found_emails = re.findall(r'[a-zA-Z0-9._%+-]+@hotmail\.com', content, re.IGNORECASE)
        unique_emails = list(set(found_emails))

        if not unique_emails:
            print(colored("[!] No @hotmail.com emails found in the file!", 'red'))
            return

        with open(INPUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(unique_emails) + '\n')

        print(colored(f"[+] Done. Extracted {len(unique_emails)} unique @hotmail.com emails.", 'green'))
        print(colored(f"[+] File cleaned and saved.\n", 'green'))
        time.sleep(1)
        
    except Exception as e:
        print(colored(f"[!] Error filtering file: {e}", 'red'))

# ==========================================
#       GOFILE BACKUP & UPLOAD LOGIC
# ==========================================

def get_timestamped_name():
    """Generates a filename with a timestamp and random numbers."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    random_num = random.randint(1000, 9999)  # Random 4-digit number
    keyword_part = f"_{KEYWORD}" if KEYWORD else ""
    return f"HotmailBackup{keyword_part}_{timestamp}_{random_num}.zip"

def zip_results(output_filename):
    """Zips only the essential email files"""
    try:
        zip_path = os.path.abspath(output_filename)
        
        print(colored(f"[BACKUP] Creating zip: {output_filename}", 'cyan'))
        
        # Only backup these specific files
        files_to_backup = [INPUT_FILE, AVAILABLE_FILE, TAKEN_FILE]

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            files_added = 0
            for file in files_to_backup:
                if os.path.exists(file):
                    zipf.write(file, file)
                    files_added += 1
                    print(colored(f"[BACKUP]   Added: {file}", 'cyan'))
                else:
                    print(colored(f"[BACKUP]   Skipped (not found): {file}", 'yellow'))
        
        print(colored(f"[BACKUP] Zip complete! Added {files_added} files.", 'green'))
        return zip_path
    except Exception as e:
        print(colored(f"[BACKUP ERROR] Could not zip files: {e}", 'red'))
        import traceback
        traceback.print_exc()
        return None

def upload_to_gofile(filepath):
    """Uploads the file to GoFile"""
    if not os.path.isfile(filepath):
        print(colored(f"[BACKUP] ERROR: File not found: {filepath}", 'red'))
        return False

    url = "https://upload.gofile.io/uploadfile"
    filename = os.path.basename(filepath)
    
    print(colored(f"[BACKUP] Uploading {filename} ({os.path.getsize(filepath)} bytes)...", 'cyan'))

    try:
        with open(filepath, 'rb') as f:
            encoder = MultipartEncoder(
                fields={
                    'file': (filename, f, 'application/octet-stream'),
                    'token': GOFILE_TOKEN,
                    'folderId': GOFILE_FOLDER_ID
                }
            )
            headers = {'Content-Type': encoder.content_type}
            
            print(colored(f"[BACKUP] Sending request to GoFile...", 'cyan'))
            response = requests.post(url, data=encoder, headers=headers, timeout=120)
        
        print(colored(f"[BACKUP] Response status: {response.status_code}", 'cyan'))
        
        try:
            data = response.json()
            print(colored(f"[BACKUP] Response data: {data}", 'cyan'))
            
            if data.get('status') == 'ok':
                link = data.get('data', {}).get('downloadPage')
                print(colored(f"[BACKUP] ✓ Success! Link: {link}", 'green'))
                return True
            else:
                print(colored(f"[BACKUP] ✗ Failed. Status: {data.get('status')}", 'red'))
                print(colored(f"[BACKUP] Full response: {data}", 'red'))
        except Exception as e:
            print(colored(f"[BACKUP] ✗ Failed to parse response: {e}", 'red'))
            print(colored(f"[BACKUP] Raw response: {response.text[:500]}", 'red'))
            
    except Exception as e:
        print(colored(f"[BACKUP] ✗ Upload Error: {e}", 'red'))
        import traceback
        traceback.print_exc()
    
    return False

def perform_backup():
    """Executes the Zip -> Upload -> Cleanup cycle."""
    print(colored("[BACKUP] Starting backup process...", 'cyan'))
    
    zip_name = get_timestamped_name()
    print(colored(f"[BACKUP] Zip filename: {zip_name}", 'cyan'))
    
    zip_path = zip_results(zip_name)
    
    if zip_path:
        print(colored(f"[BACKUP] Zip created successfully at: {zip_path}", 'green'))
        upload_success = upload_to_gofile(zip_path)
        
        # Clean up local zip
        try:
            os.remove(zip_path)
            print(colored("[BACKUP] Local temp file cleaned up.", 'cyan'))
        except Exception as e:
            print(colored(f"[BACKUP] Warning: Could not delete zip: {e}", 'yellow'))
        
        return upload_success
    else:
        print(colored("[BACKUP] ERROR: Failed to create zip file!", 'red'))
        return False

def background_backup_task():
    """Running in a separate thread to handle periodic backups."""
    global IS_RUNNING
    total_seconds = int(BACKUP_INTERVAL_HOURS * 3600)
    print(colored(f"[SYSTEM] Backup scheduler started. Will upload every {BACKUP_INTERVAL_HOURS} hour(s) ({total_seconds} seconds).", 'cyan'))
    
    while IS_RUNNING:
        # Wait for the interval (in chunks to allow faster exit)
        for i in range(total_seconds): 
            if not IS_RUNNING: 
                break
            time.sleep(1)
            # Show countdown every 30 seconds
            if (i + 1) % 30 == 0 and IS_RUNNING:
                remaining = total_seconds - (i + 1)
                print(colored(f"\n[BACKUP] Next backup in {remaining} seconds...", 'yellow'))
        
        if IS_RUNNING:
            print(colored("\n[BACKUP] ⏰ Time to backup! Starting now...", 'yellow'))
            perform_backup()
            print(colored("[BACKUP] ✓ Scheduled backup complete.\n", 'yellow'))

def load_processed_emails():
    """Load all previously checked emails (both available and taken)"""
    processed = set()
    for filename in [AVAILABLE_FILE, TAKEN_FILE]:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                for line in f:
                    if line.strip():
                        processed.add(line.strip())
    return processed

def update_stats():
    """Display live statistics"""
    global checked_count, available_count, taken_count, start_time
    
    elapsed = time.time() - start_time
    rate = checked_count / elapsed if elapsed > 0 else 0
    
    with print_lock:
        sys.stdout.write(f"\r[*] Checked: {checked_count} | Available: {available_count} | Taken: {taken_count} | Rate: {rate:.1f}/s | Time: {elapsed:.1f}s")
        sys.stdout.flush()

def init_session(thread_count):
    """Initialize session with optimized settings for maximum speed"""
    global session
    session = requests.Session()
    
    # Aggressive retry strategy - fail fast
    retry = Retry(
        total=2,
        connect=2,
        read=1,
        backoff_factor=0.1,
        status_forcelist=[500, 502, 503, 504]
    )
    
    # Large connection pool for high concurrency
    adapter = HTTPAdapter(
        max_retries=retry, 
        pool_connections=thread_count * 2,
        pool_maxsize=thread_count * 2,
        pool_block=False
    )
    
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    # Disable unnecessary features
    session.trust_env = False

def check(email):
    """Check email availability with optimized settings"""
    global checked_count, available_count, taken_count
    
    # IMPORTANT: These headers are required for accurate results
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36",
        "Connection": "keep-alive",
        "Host": "odc.officeapps.live.com",
        "Accept-Encoding": "gzip, deflate",
        "canary": "BCfKjqOECfmW44Z3Ca7vFrgp9j3V8GQHKh6NnEESrE13SEY/4jyexVZ4Yi8CjAmQtj2uPFZjPt1jjwp8O5MXQ5GelodAON4Jo11skSWTQRzz6nMVUHqa8t1kVadhXFeFk5AsckPKs8yXhk7k4Sdb5jUSpgjQtU2Ydt1wgf3HEwB1VQr+iShzRD0R6C0zHNwmHRnIatjfk0QJpOFHl2zH3uGtioL4SSusd2CO8l4XcCClKmeHJS8U3uyIMJQ8L+tb:2:3c",
        "Cookie": "xid=d491738a-bb3d-4bd6-b6ba-f22f032d6e67"
    }
    
    link = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=0&emailAddress={email}&_=1604288577990"

    try:
        # Reduced timeout but still reasonable
        response = session.get(link, headers=headers, timeout=5).text
        
        with stats_lock:
            checked_count += 1
        
        if "Neither" in response:
            with stats_lock:
                available_count += 1
            
            with print_lock:
                sys.stdout.write("\n")
                print(colored(f"[+] AVAILABLE: {email}", 'green'))
            
            with file_lock:
                with open(AVAILABLE_FILE, 'a') as f:
                    f.write(email + "\n")
        else:
            # Email is taken/registered
            with stats_lock:
                taken_count += 1
            
            with print_lock:
                sys.stdout.write("\n")
                print(colored(f"[-] TAKEN: {email}", 'red'))
            
            with file_lock:
                with open(TAKEN_FILE, 'a') as f:
                    f.write(email + "\n")
        
        # Update stats every 10 checks
        if checked_count % 10 == 0:
            update_stats()
                    
    except requests.exceptions.Timeout:
        with stats_lock:
            checked_count += 1
    except Exception:
        with stats_lock:
            checked_count += 1

def batch_check(emails, batch_size=100):
    """Process emails in batches for better memory management"""
    for i in range(0, len(emails), batch_size):
        batch = emails[i:i + batch_size]
        yield batch

def show_menu():
    """Display interactive menu"""
    global THREADS, FILTER_ENABLED, KEYWORD, AVAILABLE_FILE, TAKEN_FILE
    global GOFILE_ENABLED, BACKUP_INTERVAL_HOURS
    
    print(colored("\n=== CONFIGURATION MENU ===", 'cyan', attrs=['bold']))
    print(colored("\n1. Filter emails.txt (Extract @hotmail.com only)", 'white'))
    print(colored("2. Set thread count", 'white'))
    print(colored("3. Add keyword to output filenames", 'white'))
    print(colored("4. Enable GoFile auto-backup", 'white'))
    print(colored("5. Set backup interval (hours)", 'white'))
    print(colored("6. Start checking", 'white'))
    print(colored("7. Exit", 'white'))
    
    while True:
        choice = input(colored("\n[?] Select option (1-7): ", 'yellow')).strip()
        
        if choice == '1':
            FILTER_ENABLED = True
            print(colored("[✓] Email filtering enabled", 'green'))
            
        elif choice == '2':
            try:
                threads_input = input(colored("[?] Enter thread count (default 200): ", 'yellow')).strip()
                if threads_input:
                    THREADS = int(threads_input)
                    if THREADS > 500:
                        print(colored("[!] Warning: Very high thread count. Using 500.", 'yellow'))
                        THREADS = 500
                print(colored(f"[✓] Threads set to: {THREADS}", 'green'))
            except ValueError:
                print(colored("[!] Invalid number. Keeping default.", 'red'))
                
        elif choice == '3':
            keyword_input = input(colored("[?] Enter keyword for filenames (e.g., 'premium'): ", 'yellow')).strip()
            if keyword_input:
                KEYWORD = keyword_input
                AVAILABLE_FILE = f'available_{KEYWORD}_Hotmail.txt'
                TAKEN_FILE = f'taken_{KEYWORD}_Hotmail.txt'
                print(colored(f"[✓] Files will be named:", 'green'))
                print(colored(f"    - {AVAILABLE_FILE}", 'cyan'))
                print(colored(f"    - {TAKEN_FILE}", 'cyan'))
            else:
                print(colored("[!] No keyword entered. Using defaults.", 'yellow'))
        
        elif choice == '4':
            GOFILE_ENABLED = not GOFILE_ENABLED
            status = "ENABLED" if GOFILE_ENABLED else "DISABLED"
            color = 'green' if GOFILE_ENABLED else 'red'
            print(colored(f"[✓] GoFile auto-backup: {status}", color))
            if GOFILE_ENABLED:
                print(colored(f"    Backups every {BACKUP_INTERVAL_HOURS} hour(s)", 'cyan'))
        
        elif choice == '5':
            try:
                interval_input = input(colored("[?] Enter backup interval in hours (default 1): ", 'yellow')).strip()
                if interval_input:
                    BACKUP_INTERVAL_HOURS = float(interval_input)
                    if BACKUP_INTERVAL_HOURS < 0.0083:  # Minimum 30 seconds
                        print(colored("[!] Minimum interval is 0.0083 hours (30 seconds).", 'yellow'))
                        BACKUP_INTERVAL_HOURS = 0.0083
                print(colored(f"[✓] Backup interval set to: {BACKUP_INTERVAL_HOURS} hour(s)", 'green'))
            except ValueError:
                print(colored("[!] Invalid number. Keeping default.", 'red'))
                
        elif choice == '6':
            print(colored("\n[✓] Starting checker...\n", 'green'))
            time.sleep(1)
            return True
            
        elif choice == '7':
            print(colored("\n[!] Exiting...", 'red'))
            sys.exit(0)
            
        else:
            print(colored("[!] Invalid option. Please choose 1-7.", 'red'))

def parse_arguments():
    """Parse command line arguments"""
    global THREADS, FILTER_ENABLED, KEYWORD, AVAILABLE_FILE, TAKEN_FILE
    global GOFILE_ENABLED, BACKUP_INTERVAL_HOURS
    
    parser = argparse.ArgumentParser(
        description='Ultra-Fast Hotmail Availability Checker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python script.py --auto                                    # Run with defaults
  python script.py --threads 300 --auto                      # 300 threads, auto-start
  python script.py --filter --threads 150 --auto             # Filter + 150 threads
  python script.py --keyword premium --auto                  # Custom filenames
  python script.py --gofile --interval 2 --auto              # Enable backup every 2 hours
  python script.py --filter --keyword vip --threads 250 --gofile --auto  # All options
        '''
    )
    
    parser.add_argument('--filter', action='store_true', 
                       help='Filter emails.txt for @hotmail.com only')
    parser.add_argument('--threads', type=int, default=200,
                       help='Number of threads (default: 200, max: 500)')
    parser.add_argument('--keyword', type=str, default='',
                       help='Keyword for output filenames (e.g., premium, vip)')
    parser.add_argument('--gofile', action='store_true',
                       help='Enable GoFile auto-backup')
    parser.add_argument('--interval', type=float, default=1.0,
                       help='Backup interval in hours (default: 1.0, min: 0.0083 for 30 seconds)')
    parser.add_argument('--auto', action='store_true',
                       help='Skip menu and start immediately')
    
    args = parser.parse_args()
    
    # Apply arguments
    FILTER_ENABLED = args.filter
    THREADS = min(args.threads, 500)  # Cap at 500
    GOFILE_ENABLED = args.gofile
    BACKUP_INTERVAL_HOURS = max(args.interval, 0.0083)  # Minimum 30 seconds (0.0083 hours)
    
    if args.keyword:
        KEYWORD = args.keyword
        AVAILABLE_FILE = f'available_{KEYWORD}_Hotmail.txt'
        TAKEN_FILE = f'taken_{KEYWORD}_Hotmail.txt'
    
    return args.auto

# --- MAIN EXECUTION ---
banner()

# Parse command line arguments
auto_start = parse_arguments()

# Show menu if not auto-start
if not auto_start:
    show_menu()
else:
    print(colored("\n[*] Auto-start mode enabled", 'cyan'))
    if FILTER_ENABLED:
        print(colored("[*] Email filtering: ENABLED", 'green'))
    print(colored(f"[*] Threads: {THREADS}", 'cyan'))
    if KEYWORD:
        print(colored(f"[*] Keyword: {KEYWORD}", 'cyan'))
    if GOFILE_ENABLED:
        print(colored(f"[*] GoFile backup: ENABLED (every {BACKUP_INTERVAL_HOURS}h)", 'green'))
    time.sleep(1)

# Start GoFile backup thread if enabled
backup_thread = None
if GOFILE_ENABLED:
    print(colored(f"\n[DEBUG] BACKUP_INTERVAL_HOURS = {BACKUP_INTERVAL_HOURS}", 'magenta'))
    print(colored(f"[DEBUG] Calculated seconds = {int(BACKUP_INTERVAL_HOURS * 3600)}", 'magenta'))
    backup_thread = threading.Thread(target=background_backup_task, daemon=True)
    backup_thread.start()

# Execute filtering if enabled
if FILTER_ENABLED:
    filter_emails()

# Load Emails
if not os.path.exists(INPUT_FILE):
    print(colored("\nError: emails.txt not found.", 'red'))
    sys.exit()

with open(INPUT_FILE, 'r') as f:
    all_emails = [line.strip() for line in f if line.strip()]

if len(all_emails) == 0:
    print(colored("\nError: emails.txt is empty.", 'red'))
    sys.exit()

# Load previously processed emails
processed_emails = load_processed_emails()
emails = [email for email in all_emails if email not in processed_emails]

if len(emails) == 0:
    print(colored("\n[+] All emails have already been checked!", 'green'))
    print(colored(f"[*] Check {AVAILABLE_FILE} and {TAKEN_FILE} for results.", 'cyan'))
    sys.exit()

print(colored(f"\n[*] Total emails in file: {len(all_emails)}", 'white'))
print(colored(f"[*] Already processed: {len(processed_emails)}", 'yellow'))
print(colored(f"[*] Remaining to check: {len(emails)}", 'cyan'))
print(colored(f"[*] Starting with {THREADS} threads...", 'cyan'))
print(colored("[*] Press Ctrl+C to stop and resume later.", 'cyan'))
time.sleep(1)

# Clear/create output files if they don't exist
for filename in [AVAILABLE_FILE, TAKEN_FILE]:
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            pass

init_session(THREADS)
start_time = time.time()

# Start Processing with optimized executor
try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
        # Submit all tasks at once for maximum concurrency
        futures = [executor.submit(check, email) for email in emails]
        
        # Wait for completion
        concurrent.futures.wait(futures)
        
except KeyboardInterrupt:
    print(colored("\n\n[!] Stopped by user.", 'red'))
finally:
    # Stop the backup thread
    IS_RUNNING = False
    
    # Perform final backup if GoFile is enabled
    if GOFILE_ENABLED:
        print(colored("\n[BACKUP] Performing final backup before exit...", 'yellow'))
        perform_backup()

# Final stats
elapsed = time.time() - start_time
rate = checked_count / elapsed if elapsed > 0 else 0

print(colored(f"\n\n[+] Done!", 'green'))
print(colored(f"[+] Total Checked: {checked_count}", 'white'))
print(colored(f"[+] Available Found: {available_count}", 'green'))
print(colored(f"[+] Taken/Registered: {taken_count}", 'red'))
print(colored(f"[+] Average Rate: {rate:.1f} checks/second", 'cyan'))
print(colored(f"[+] Total Time: {elapsed:.2f} seconds", 'cyan'))
print(colored(f"[+] Results saved to:", 'white'))
print(colored(f"    - Available: {AVAILABLE_FILE}", 'green'))
print(colored(f"    - Taken: {TAKEN_FILE}", 'red'))
