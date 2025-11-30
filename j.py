import time
import os
import sys
import threading
import datetime
import requests
import zipfile
from requests_toolbelt.multipart.encoder import MultipartEncoder
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- SELENIUM IMPORTS ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
#              CONFIGURATION
# ==========================================

# --- EMAIL CHECKER SETTINGS ---
TARGET_URL = "https://signup.live.com/signup"
INPUT_FILE = "emails.txt"
AVAILABLE_FILE = "available.txt"
TAKEN_FILE = "taken.txt"
FAILED_FILE = "failed.txt"
MAX_RETRIES = 2  # Reduced from 3 for speed
CONCURRENT_BROWSERS = 3  # Run multiple browsers simultaneously
WAIT_TIMEOUT = 8  # Reduced from 10 seconds

# --- GOFILE UPLOAD SETTINGS ---
GOFILE_TOKEN = "YKb1gKOqDJ2TWbfTggRJPU1y31Pi36H9"
GOFILE_FOLDER_ID = "dabd7396-7d74-4072-bf83-3bb3ac30a28d"
BACKUP_INTERVAL_HOURS = 3

# Global state management
IS_RUNNING = True
processed_count = 0
available_count = 0
taken_count = 0
stats_lock = threading.Lock()
file_lock = threading.Lock()

# ==========================================
#           BACKUP & UPLOAD LOGIC
# ==========================================

def get_timestamped_name():
    """Generates a filename with a timestamp."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"Backup_{timestamp}.zip"

def zip_results(output_filename):
    """Zips the current directory (filtering for relevant files)"""
    try:
        source_dir = "."
        zip_path = os.path.abspath(output_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    if file == output_filename:
                        continue
                    
                    if file == INPUT_FILE or file.endswith(('.txt', '.png', '.py')):
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, file)
        return zip_path
    except Exception as e:
        print(f"[BACKUP ERROR] Could not zip files: {e}")
        return None

def upload_to_gofile(filepath):
    """Uploads the file to GoFile"""
    if not os.path.isfile(filepath):
        return False

    url = "https://upload.gofile.io/uploadfile"
    filename = os.path.basename(filepath)
    
    print(f"\n[BACKUP] Uploading {filename}...")

    try:
        encoder = MultipartEncoder(
            fields={
                'file': (filename, open(filepath, 'rb'), 'application/octet-stream'),
                'token': GOFILE_TOKEN,
                'folderId': GOFILE_FOLDER_ID
            }
        )
        headers = {'Content-Type': encoder.content_type}
        
        response = requests.post(url, data=encoder, headers=headers, timeout=60)
        
        try:
            data = response.json()
            if data.get('status') == 'ok':
                link = data.get('data', {}).get('downloadPage')
                print(f"[BACKUP] Success! Link: {link}")
                return True
            else:
                print(f"[BACKUP] Failed. Status: {data.get('status')}")
        except:
            print(f"[BACKUP] Failed to parse response.")
            
    except Exception as e:
        print(f"[BACKUP] Upload Error: {e}")
    
    return False

def background_backup_task():
    """Running in a separate thread to handle periodic backups."""
    global IS_RUNNING
    print(f"[SYSTEM] Backup scheduler started. Will upload every {BACKUP_INTERVAL_HOURS} hours.")
    
    while IS_RUNNING:
        for _ in range(BACKUP_INTERVAL_HOURS * 3600): 
            if not IS_RUNNING: 
                break
            time.sleep(1)
        
        if IS_RUNNING:
            perform_backup()

def perform_backup():
    """Executes the Zip -> Upload -> Cleanup cycle."""
    zip_name = get_timestamped_name()
    zip_path = zip_results(zip_name)
    
    if zip_path:
        upload_to_gofile(zip_path)
        try:
            os.remove(zip_path)
            print("[BACKUP] Local temp file cleaned up.")
        except:
            pass

# ==========================================
#           EMAIL CHECKER LOGIC
# ==========================================

def setup_driver():
    """Setup optimized Chrome driver"""
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Uncomment for speed
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Speed optimizations
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")  # Don't load images
    chrome_options.add_argument("--disable-plugins")
    chrome_options.page_load_strategy = 'eager'  # Don't wait for full page load
    
    # Disable unnecessary features
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(15)
    
    return driver

def load_processed_emails():
    """Load all previously processed emails"""
    processed = set()
    for filename in [AVAILABLE_FILE, TAKEN_FILE, FAILED_FILE]:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                for line in f:
                    if line.strip(): 
                        processed.add(line.strip())
    return processed

def update_stats():
    """Print live statistics"""
    global processed_count, available_count, taken_count
    sys.stdout.write(f"\r[Stats] Processed: {processed_count} | Available: {available_count} | Taken: {taken_count}")
    sys.stdout.flush()

def check_single_email(email, worker_id, total_emails):
    """Check a single email using dedicated browser instance"""
    global processed_count, available_count, taken_count
    
    driver = None
    result = None
    
    try:
        driver = setup_driver()
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"\n[Worker {worker_id}] Checking: {email} (Attempt {attempt})")
                
                driver.get(TARGET_URL)
                
                # Wait for and fill email input
                email_input = wait.until(
                    EC.element_to_be_clickable((By.NAME, "Email"))
                )
                email_input.clear()
                email_input.send_keys(email)
                
                # Click next button
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, '[data-testid="primaryButton"]')
                    next_btn.click()
                except NoSuchElementException:
                    driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
                
                # Wait for result with shorter timeout
                time.sleep(2)  # Brief pause for page to update
                
                page_source = driver.page_source.lower()
                
                if "create your password" in page_source or "create a password" in page_source:
                    result = "available"
                    print(f"[Worker {worker_id}] -> ✓ AVAILABLE")
                    break
                elif "taken" in page_source or "already in use" in page_source:
                    result = "taken"
                    print(f"[Worker {worker_id}] -> ✗ TAKEN")
                    break
                else:
                    if attempt < MAX_RETRIES:
                        print(f"[Worker {worker_id}] -> Unclear response, retrying...")
                        time.sleep(1)
                    
            except (TimeoutException, WebDriverException) as e:
                print(f"[Worker {worker_id}] -> Error: {str(e)[:50]}")
                if attempt < MAX_RETRIES:
                    time.sleep(2)
        
        # Write result to file
        with file_lock:
            if result == "available":
                with open(AVAILABLE_FILE, 'a') as f:
                    f.write(email + "\n")
                with stats_lock:
                    available_count += 1
            elif result == "taken":
                with open(TAKEN_FILE, 'a') as f:
                    f.write(email + "\n")
                with stats_lock:
                    taken_count += 1
            else:
                with open(FAILED_FILE, 'a') as f:
                    f.write(email + "\n")
            
            with stats_lock:
                processed_count += 1
            
            update_stats()
        
    except Exception as e:
        print(f"\n[Worker {worker_id}] Fatal error: {e}")
        with file_lock:
            with open(FAILED_FILE, 'a') as f:
                f.write(email + "\n")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return result

def process_emails():
    """Main processing function with parallel execution"""
    global IS_RUNNING, processed_count, available_count, taken_count
    
    # Start backup thread
    backup_thread = threading.Thread(target=background_backup_task, daemon=True)
    backup_thread.start()
    
    start_time = time.time()
    
    try:
        # Load emails
        try:
            with open(INPUT_FILE, 'r') as f:
                all_emails = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Error: {INPUT_FILE} not found.")
            IS_RUNNING = False
            return
        
        processed_emails = load_processed_emails()
        emails_to_check = [e for e in all_emails if e not in processed_emails]
        
        if not emails_to_check:
            print("All emails have been processed.")
            IS_RUNNING = False
            return
        
        total = len(emails_to_check)
        print(f"\n{'='*60}")
        print(f"Starting optimized processing for {total} emails...")
        print(f"Using {CONCURRENT_BROWSERS} parallel browsers")
        print(f"{'='*60}\n")
        
        # Process emails in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=CONCURRENT_BROWSERS) as executor:
            futures = {
                executor.submit(check_single_email, email, idx % CONCURRENT_BROWSERS + 1, total): email 
                for idx, email in enumerate(emails_to_check)
            }
            
            for future in as_completed(futures):
                pass  # Results are handled in check_single_email
        
        elapsed = time.time() - start_time
        rate = processed_count / elapsed if elapsed > 0 else 0
        
        print(f"\n\n{'='*60}")
        print(f"Processing Complete!")
        print(f"{'='*60}")
        print(f"Total Processed: {processed_count}")
        print(f"Available: {available_count}")
        print(f"Taken: {taken_count}")
        print(f"Failed: {processed_count - available_count - taken_count}")
        print(f"Time Taken: {elapsed:.2f} seconds")
        print(f"Average Rate: {rate:.2f} emails/second")
        print(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        print("\n\nProcess stopped by user.")
    finally:
        print("Stopping backup scheduler...")
        IS_RUNNING = False
        
        print("Performing final backup...")
        perform_backup()
        print("Done.")

if __name__ == "__main__":
    process_emails()
