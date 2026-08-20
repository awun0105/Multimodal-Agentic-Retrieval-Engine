import os
import sys
import zipfile
import shutil
import subprocess
from pathlib import Path

URLS = [
    "https://aic-data.ledo.io.vn/Keyframes_L21.zip",
    "https://aic-data.ledo.io.vn/Keyframes_L22.zip",
    "https://aic-data.ledo.io.vn/Keyframes_L23.zip",
    "https://aic-data.ledo.io.vn/Keyframes_L24.zip",
    "https://aic-data.ledo.io.vn/Keyframes_L25.zip",
    "https://aic-data.ledo.io.vn/Keyframes_L26_a.zip",
    "https://aic-data.ledo.io.vn/Keyframes_L26_b.zip"
]

def main():
    target_root = Path("mvp-app/data/releases/aic25-b1-v1/keyframes")
    temp_dir = Path("mvp-app/tmp/download")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Target directory for keyframes: {target_root.resolve()}")
    
    for url in URLS:
        filename = url.split("/")[-1]
        zip_path = temp_dir / filename
        
        print(f"\n==================================================")
        print(f"Processing: {filename}")
        print(f"==================================================")
        
        # 1. Download ZIP file using wget
        print(f"Downloading from {url} using wget...")
        try:
            # -c enables resuming partial downloads, -O specifies output file
            cmd = ["wget", "-c", url, "-O", str(zip_path)]
            subprocess.run(cmd, check=True)
            print("Download complete.")
        except Exception as e:
            print(f"Error downloading {url} via wget: {e}")
            continue
                
        # 2. Extract ZIP file
        extract_dir = temp_dir / filename.replace(".zip", "")
        extract_dir.mkdir(parents=True, exist_ok=True)
        print(f"Extracting {zip_path} to {extract_dir}...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            print("Extraction complete.")
        except Exception as e:
            print(f"Error extracting {zip_path}: {e}")
            # Cleanup corrupted zip so it restarts next time
            if zip_path.exists():
                zip_path.unlink()
            continue
            
        # 3. Reorganize keyframes
        print("Reorganizing files to match database layout...")
        moved_count = 0
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith((".jpg", ".png", ".webp")):
                    file_path = Path(root) / file
                    
                    # Resolve destination directory
                    video_id = file_path.parent.name
                    collection_id = file_path.parent.parent.name
                    
                    if video_id.startswith("L") and collection_id.startswith("L"):
                        dest_dir = target_root / collection_id / video_id
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        dest_path = dest_dir / file
                        
                        # Move file (overwrite if exists)
                        if dest_path.exists():
                            dest_path.unlink()
                        shutil.move(str(file_path), str(dest_path))
                        moved_count += 1
                        
        print(f"Moved {moved_count} keyframes to target directories.")
        
        # 4. Clean up
        print("Cleaning up temporary download and extraction folders...")
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
            if zip_path.exists():
                zip_path.unlink()
            print("Cleanup successful.")
        except Exception as e:
            print(f"Error during cleanup: {e}")
            
    print("\nAll tasks completed successfully!")

if __name__ == "__main__":
    main()
