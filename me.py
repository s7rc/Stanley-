#!/usr/bin/env python3
import sys
import os
import requests
import zipfile  # Added for zipping
import shutil   # Added for deleting the folder
import argparse # Added for handling -z and -zd flags
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from tqdm import tqdm  # For the progress bar

# --- YOUR ACCOUNT DETAILS ---
# Token from your browser's local storage
TOKEN = "YKb1gKOqDJ2TWbfTggRJPU1y31Pi36H9" 

# The specific folder ID you want to upload to (the UUID)
FOLDER_ID = "dabd7396-7d74-4072-bf83-3bb3ac30a28d" 
# ----------------------------


def zip_folder(folder_path):
    """
    Zips an entire folder and returns the path to the new zip file.
    The zip file is created INSIDE the folder being zipped to avoid path conflicts.
    """
    abs_folder_path = os.path.abspath(folder_path)
    folder_name = os.path.basename(abs_folder_path)
    
    # Create the zip file INSIDE the folder it's zipping
    zip_name = f"{folder_name}.zip"
    zip_path = os.path.join(abs_folder_path, zip_name)
    
    print(f"\nZipping folder '{abs_folder_path}' to '{zip_path}'...")

    try:
        # Create a new zip file
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk the directory tree
            for root, dirs, files in os.walk(abs_folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # Don't add the zip file to itself!
                    if os.path.abspath(file_path) == os.path.abspath(zip_path):
                        continue
                        
                    # Create the relative path for the file inside the zip
                    archive_name = os.path.relpath(file_path, abs_folder_path)
                    
                    # Write the file to the zip
                    zipf.write(file_path, archive_name)

        print("Zipping complete.")
        return zip_path
        
    except Exception as e:
        print(f"Error while zipping: {e}", file=sys.stderr)
        return None # Return None on failure


def upload_file_with_progress(filepath):
    """
    Uploads a single file to a specific GoFile.io folder with a progress bar.
    """
    # Check if the file exists
    if not os.path.isfile(filepath):
        print(f"ERROR: File not found at '{filepath}'", file=sys.stderr)
        return False

    url = "https://upload.gofile.io/uploadfile"
    filename = os.path.basename(filepath)
    
    # Create the multipart encoder
    encoder = MultipartEncoder(
        fields={
            'file': (filename, open(filepath, 'rb'), 'application/octet-stream'),
            'token': TOKEN,
            'folderId': FOLDER_ID
        }
    )
    
    progress_bar = tqdm(total=encoder.len, unit='B', unit_scale=True, desc=f"Uploading {filename}")
    
    try:
        monitor = MultipartEncoderMonitor(encoder, lambda m: progress_bar.update(m.bytes_read - progress_bar.n))
        headers = {'Content-Type': monitor.content_type}

        response = requests.post(url, data=monitor, headers=headers)
        
        progress_bar.close()
        response.raise_for_status()
        data = response.json()

        if data.get('status') == 'ok':
            link = data.get('data', {}).get('downloadPage')
            if link:
                print("\nUpload Complete!")
                print(link)
                return True # Success
            else:
                print("\nUpload failed! 'downloadPage' not found in response.", file=sys.stderr)
                print(data, file=sys.stderr)
                return False # Failure
        else:
            print(f"\nUpload failed! Status: {data.get('status')}", file=sys.stderr)
            print(data, file=sys.stderr)
            return False # Failure

    except requests.exceptions.RequestException as e:
        progress_bar.close()
        print(f"\nAn error occurred: {e}", file=sys.stderr)
        return False # Failure
    except Exception as e:
        progress_bar.close()
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        return False # Failure


def main():
    # 1. Set up the argument parser
    parser = argparse.ArgumentParser(
        description="Upload a file or folder (as zip) to GoFile.io.",
        usage=f"python {os.path.basename(sys.argv[0])} [-z | -zd | -zdd] [path]"
    )
    
    # Use 'nargs=?' to make the path optional, defaulting to '.'
    parser.add_argument("path", help="Path to the file or folder to upload. Defaults to '.' (current directory).",
                        nargs='?', default='.')
    
    # Create a mutually exclusive group for zip flags
    zip_group = parser.add_mutually_exclusive_group()
    zip_group.add_argument("-z", "--zip", action="store_true", help="Zip the target folder and upload the single zip.")
    zip_group.add_argument("-zd", "--zip-delete", action="store_true", help="Zip target, upload, and delete original folder/contents.")
    zip_group.add_argument("-zdd", "--zip-deep-delete", action="store_true", help="Upload loose files, and zip/upload/delete all subfolders.")

    args = parser.parse_args()
    script_path = os.path.abspath(sys.argv[0])

    # --- BEHAVIOR 1: NEW! Zip Deep Delete (-zdd) ---
    if args.zip_deep_delete:
        target_dir = os.path.abspath(args.path)
        if not os.path.isdir(target_dir):
            print(f"Error: -zdd flag must be used with a directory. '{target_dir}' is not valid.", file=sys.stderr)
            sys.exit(1)
            
        print(f"--- Starting Batch Mode (-zdd) for '{target_dir}' ---")
        items_processed = 0
        
        # Iterate over all items in the target directory
        for item_name in sorted(os.listdir(target_dir)):
            item_path = os.path.join(target_dir, item_name)
            
            # --- Handle Files ---
            if os.path.isfile(item_path):
                # Don't upload the script itself
                if os.path.abspath(item_path) == script_path:
                    print(f"Skipping script file: {item_name}")
                    continue
                
                items_processed += 1
                print(f"\n--- Processing file {items_processed}: {item_name} ---")
                upload_file_with_progress(item_path)

            # --- Handle Subfolders ---
            elif os.path.isdir(item_path):
                items_processed += 1
                print(f"\n--- Processing subfolder {items_processed}: {item_name} ---")
                
                # 1. Zip the subfolder
                zip_path = zip_folder(item_path)
                if not zip_path:
                    print(f"Skipping {item_name} due to zipping error.")
                    continue
                
                # 2. Upload the new zip file
                upload_success = upload_file_with_progress(zip_path)
                
                # 3. Clean up the temporary zip file
                if os.path.isfile(zip_path):
                    try:
                        os.remove(zip_path)
                    except Exception as e:
                        print(f"Warning: Could not delete temp zip {zip_path}. {e}", file=sys.stderr)
                
                # 4. Delete the original subfolder if upload was successful
                if upload_success:
                    print(f"Attempting to delete original folder: {item_path}")
                    try:
                        shutil.rmtree(item_path)
                        print("Successfully deleted original folder.")
                    except Exception as e:
                        print(f"Error: Could not delete folder {item_path}. {e}", file=sys.stderr)
                else:
                    print(f"Upload failed for {item_name}. Original folder will not be deleted.")

        if items_processed == 0:
            print("No files or subfolders found to process.")
        print("\n--- Batch Mode complete. ---")
        sys.exit(0)

    # --- BEHAVIOR 2: Zip Single Folder (-z or -zd) ---
    if args.zip or args.zip_delete:
        if not os.path.isdir(args.path):
            print(f"Error: -z and -zd flags can only be used with a directory. '{args.path}' is not a directory.", file=sys.stderr)
            sys.exit(1)
        
        # 1. Zip the folder
        filepath_to_upload = zip_folder(args.path)
        if not filepath_to_upload:
             sys.exit(1) # Zipping failed
             
        zip_file_to_delete = filepath_to_upload
        folder_to_delete = os.path.abspath(args.path) if args.zip_delete else None
        
        # 2. Upload the new zip file
        upload_success = upload_file_with_progress(filepath_to_upload)
        
        # 3. Clean up the temporary zip file
        if os.path.isfile(zip_file_to_delete):
            try:
                os.remove(zip_file_to_delete)
            except Exception as e:
                print(f"Warning: Could not delete temp zip {zip_file_to_delete}. {e}", file=sys.stderr)

        # 4. Delete the original folder/contents if requested
        if folder_to_delete and upload_success:
            current_working_dir = os.path.abspath(os.getcwd())

            if folder_to_delete == current_working_dir:
                print(f"\nAttempting to delete contents of current directory: {folder_to_delete}")
                for item_name in os.listdir(folder_to_delete):
                    item_path = os.path.join(folder_to_delete, item_name)
                    if os.path.abspath(item_path) == script_path:
                        print(f"Skipping active script: {item_name}")
                        continue
                    if os.path.isdir(item_path): shutil.rmtree(item_path); print(f"Deleted folder: {item_name}")
                    elif os.path.isfile(item_path): os.remove(item_path); print(f"Deleted file: {item_name}")
                print("Successfully deleted contents of original folder.")
            else:
                print(f"\nAttempting to delete original folder: {folder_to_delete}")
                try:
                    shutil.rmtree(folder_to_delete)
                    print("Successfully deleted original folder.")
                except Exception as e:
                    print(f"Error: Could not delete folder. {e}", file=sys.stderr)
        
        elif folder_to_delete and not upload_success:
             print("\nUpload failed. Original folder will not be deleted.", file=sys.stderr)

        sys.exit(0) # We are done

    # --- BEHAVIOR 3: No zip flags used (Default) ---
    
    # Case 3a: The path is a single file
    if os.path.isfile(args.path):
        upload_file_with_progress(args.path)
    
    # Case 3b: The path is a directory (e.g., ".")
    elif os.path.isdir(args.path):
        print(f"Scanning directory '{os.path.abspath(args.path)}' for files...")
        files_found = 0

        items_in_dir = sorted(os.listdir(args.path))
        
        for item in items_in_dir:
            full_item_path = os.path.join(args.path, item)
            
            if os.path.isfile(full_item_path):
                if os.path.abspath(full_item_path) == script_path:
                    print(f"Skipping script file: {item}")
                    continue
                
                files_found += 1
                print(f"\n--- Uploading file {files_found} ({item}) ---")
                upload_file_with_progress(full_item_path)
            
            elif os.path.isdir(full_item_path):
                print(f"Skipping directory: {item}")
        
        if files_found == 0: print("No files found in the top-level directory to upload.")
        else: print(f"\n--- Batch complete: {files_found} files uploaded. ---")

    # Case 3c: The path doesn't exist
    else:
        print(f"Error: Path '{args.path}' is not a valid file or directory.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
