# %% [markdown]
# # Google Colab: Tien xu ly va Dong goi Du lieu Keyframes sang Kaggle Dataset
#
# ## 1. Muc dich va Tong quan
# Kich ban nay thuc hien tien xu ly va dong goi tap du lieu hinh anh (Keyframes) tren Google Colab:
# - Khac phuc gioi han dung luong o dia 20GB va hien tuong nghen I/O tren Kaggle bang cach tong hop toan bo tap anh thanh mot tep nhi phan duy nhat (`cached_keyframes.blob`) theo chuan `ZIP_STORED` (khong nen).
# - Tep `.blob` cho phep DataLoader truyen luong nhi phan truc tiep len VRAM cua GPU (Virtual Cache Reader) ma khong can giai nen tren phan vung o dia Kaggle.
# - Tu dong sao luu ban copy sang Google Drive va tu dong upload len Kaggle Datasets thong qua thu vien `kagglehub` (kem fallback Kaggle API).
# - Tu dong ghi nhan nhat ky lich su xu ly va dia chi luu tru (Google Drive & Kaggle) vao tep `dataset_history_notes.txt` va `dataset_manifest.json`.
#
# ---
#
# ## 2. Huong dan Thao tac (Quick Start)
#
# ### Buoc A: Thiet lap Kaggle API Token trong Colab Secrets (Thuc hien mot lan)
# 1. Truy cap https://www.kaggle.com/settings -> muc API -> chon "Create New Token" de tai tep `kaggle.json`.
# 2. Mo tep `kaggle.json` de lay `username` va `key`.
# 3. Kiem tra xac minh so dien thoai: Tren Kaggle Settings, cuon xuong muc "Phone verification" de xac minh SMS OTP (Kaggle bat buoc xac minh moi cho phep upload Dataset qua API).
# 4. Tren giao dien Google Colab, mo muc Secrets (bieu tuong khoa o thanh cong cu ben trai):
#    - Them Secret: Name = `KAGGLE_USERNAME`, Value = username tren Kaggle, bat Notebook access.
#    - Them Secret: Name = `KAGGLE_KEY`, Value = key tren Kaggle, bat Notebook access.
#
# ### Buoc B: Chuan bi Du lieu Nguon tren Google Drive
# - Dat cac tep `.zip` chua keyframes (vi du: `Keyframes_L01.zip`, `Keyframes_L02.zip`,...) vao thu muc tren Google Drive (Mac dinh: `/content/drive/MyDrive/AIC2025`).
#
# ### Buoc C: Cau hinh Tham so tai Buoc 1
# - Kiem tra duong dan nguon: `INPUT_DRIVE_PATH = "/content/drive/MyDrive/AIC_Nhat"`.
# - Cap nhat handle Kaggle: `KAGGLE_HANDLE = "username/dataset-slug"` (Vi du: `'nhathoang42/aic2025-keyframes-blob'`).
# - Tuy chon luu Drive: `SAVE_TO_DRIVE = True` de duy tri ban sao luu tren Google Drive.
# - Tuy chon upload Kaggle: `UPLOAD_TO_KAGGLE = True` de day truc tiep len Kaggle Datasets.
#
# ### Buoc D: Khoi chay Toan bo Notebook
# - Chon Menu Runtime -> Run all (hoac bam Ctrl + F9).
# - He thong se tu dong thuc thi tuan tu tu Buoc 0 den Buoc 8.
#
# ---
#
# ## 3. Ket qua Dau ra
# 1. Google Drive (`/content/drive/MyDrive/AIC_Nhat/`):
#    - Tep `.blob`: `cached_keyframes.blob`
#    - Tep nhat ky: `dataset_history_notes.txt`
#    - Tep manifest: `dataset_manifest.json`
# 2. Kaggle Datasets:
#    - URL Dataset: `https://www.kaggle.com/datasets/<KAGGLE_HANDLE>`
#    - Duong dan Mount tren Kaggle: `/kaggle/input/<dataset-slug>/cached_keyframes.blob`

# %% [code]
# ==============================================================================
# BUOC 0: CAI DAT THU VIEN BO TRO
# ==============================================================================
!pip install -q --upgrade kagglehub kaggle

# %% [code]
# ==============================================================================
# BUOC 1: CAU HINH HE THONG VA THAM SO TUY CHINH
# ==============================================================================
import os
import sys
import glob
import json
import shutil
import zipfile
import time

try:
    from google.colab import drive
except ImportError:
    print("[CANH BAO] Thu vien google.colab khong ton tai. Script nay toi uu cho moi truong Google Colab.")

# --- 1.1. Cau hinh Nghiep vu & Mo ta Du lieu ---
DATASET_DESCRIPTION = "Tap du lieu Keyframes AIC 2025 duoc dong goi thanh tep nhi phan don (.blob) theo chuan ZIP_STORED (khong nen) phuc vu co che Virtual Cache DataLoader truyen truc tiep len GPU VRAM tren Kaggle."

# --- 1.2. Cau hinh Nguon & Dich Google Drive ---
# Gan ket (Mount) khong gian luu tru Google Drive
if 'drive' in globals():
    drive.mount('/content/drive')

# Thu muc goc chua cac tep du lieu .zip nguon tren Google Drive
INPUT_DRIVE_PATH = "/content/drive/MyDrive/AIC_Nhat"

# Tuy chon luu tru rieng qua Google Drive
SAVE_TO_DRIVE = True
DRIVE_OUTPUT_DIR = "/content/drive/MyDrive/AIC_Nhat"
DRIVE_BLOB_PATH = os.path.join(DRIVE_OUTPUT_DIR, "cached_keyframes.blob")

# Tep ghi chu nhat ky / Manifest luu tru tren Drive (Tu dong noi them lich su neu file da ton tai)
DRIVE_NOTE_PATH = os.path.join(DRIVE_OUTPUT_DIR, "dataset_history_notes.txt")
DRIVE_MANIFEST_PATH = os.path.join(DRIVE_OUTPUT_DIR, "dataset_manifest.json")

# --- 1.3. Cau hinh Phan vung SSD Cuc bo Colab ---
# Thu muc tam de giai nen anh tren SSD toc do cao
LOCAL_EXTRACT_DIR = "/content/extracted_keyframes"
os.makedirs(LOCAL_EXTRACT_DIR, exist_ok=True)

# Thu muc staging chua du lieu chuan bi day len Kaggle Dataset
LOCAL_DATASET_DIR = "/content/kaggle_dataset"
os.makedirs(LOCAL_DATASET_DIR, exist_ok=True)
LOCAL_BLOB_PATH = os.path.join(LOCAL_DATASET_DIR, "cached_keyframes.blob")

# --- 1.4. Cau hinh Dang tai Kaggle Dataset qua Kagglehub ---
# Bat/tat tinh nang dang tai tu dong len Kaggle
UPLOAD_TO_KAGGLE = True

# Dinh danh Kaggle Dataset: Can dinh dang '<KAGGLE_USERNAME>/<DATASET_SLUG>'
# Vi du: 'nhathoang42/aic2025-keyframes-blob'
KAGGLE_HANDLE = "nhathoang42/aic2025-keyframes-blob"

# Ghi chu phien ban khi tao hoac cap nhat dataset
KAGGLE_VERSION_NOTES = "Packed keyframes blob archive for high-throughput GPU retrieval benchmark"

# Danh sach mau tep can bo qua khi upload len Kaggle
KAGGLE_IGNORE_PATTERNS = ["*.tmp", "*.zip", "original/", "temp/"]

print(f"[CAU HINH] Mo ta du lieu             : {DATASET_DESCRIPTION}")
print(f"[CAU HINH] Nguon du lieu Drive       : {INPUT_DRIVE_PATH}")
print(f"[CAU HINH] Nguon 1 (Google Drive)    : {'BAT -> ' + DRIVE_BLOB_PATH if SAVE_TO_DRIVE else 'TAT'}")
print(f"[CAU HINH] Nguon 2 (Kaggle Dataset)  : {'BAT -> ' + KAGGLE_HANDLE if UPLOAD_TO_KAGGLE else 'TAT'}")
print(f"[CAU HINH] Tep Note/Lich su tren Drive: {DRIVE_NOTE_PATH}")
print(f"[CAU HINH] Thu muc Staging cuc bo    : {LOCAL_DATASET_DIR}")

# %% [code]
# ==============================================================================
# BUOC 2: XAC THUC TAI KHOAN KAGGLE (KAGGLE AUTHENTICATION)
# ==============================================================================
if UPLOAD_TO_KAGGLE:
    print("[TIEN TRINH] Kiem tra thong tin xac thuc Kaggle API...")
    import kagglehub
    
    # 1. Thu lay thong tin tu Google Colab Secrets
    kaggle_user = None
    kaggle_key = None
    try:
        from google.colab import userdata
        kaggle_user = userdata.get('KAGGLE_USERNAME')
        kaggle_key = userdata.get('KAGGLE_KEY')
    except Exception:
        pass

    if kaggle_user and kaggle_key:
        kaggle_user = str(kaggle_user).strip()
        kaggle_key = str(kaggle_key).strip()
        os.environ["KAGGLE_USERNAME"] = kaggle_user
        os.environ["KAGGLE_KEY"] = kaggle_key
        
        # Tao file ~/.kaggle/kaggle.json de dam bao tuong thich toan dien
        kaggle_config_dir = os.path.expanduser("~/.kaggle")
        os.makedirs(kaggle_config_dir, exist_ok=True)
        kaggle_json_path = os.path.join(kaggle_config_dir, "kaggle.json")
        with open(kaggle_json_path, "w", encoding="utf-8") as f:
            json.dump({"username": kaggle_user, "key": kaggle_key}, f)
        try:
            os.chmod(kaggle_json_path, 0o600)
        except Exception:
            pass
            
        mask_key = kaggle_key[:3] + "..." + kaggle_key[-3:] if len(kaggle_key) > 6 else "***"
        print(f"  -> Da nap thanh cong xac thuc tu Colab Secrets:")
        print(f"     - KAGGLE_USERNAME: {kaggle_user}")
        print(f"     - KAGGLE_KEY     : {mask_key}")
        print(f"     - File cau hinh  : {kaggle_json_path}")
        
        # Kiem tra xem username co khop voi KAGGLE_HANDLE khong
        if "<KAGGLE_USERNAME>" not in KAGGLE_HANDLE:
            handle_user = KAGGLE_HANDLE.split('/')[0].strip()
            if handle_user.lower() != kaggle_user.lower():
                print(f"  [CANH BAO] Username trong Secret ({kaggle_user}) KHONG KHOP voi chu so huu trong KAGGLE_HANDLE ({handle_user}).")
                print(f"             Kaggle se tu choi (401/403) neu ban upload vao tai khoan cua nguoi khac.")
    else:
        # 2. Kiem tra bien moi truong hoac file ~/.kaggle/kaggle.json
        has_env = "KAGGLE_USERNAME" in os.environ and "KAGGLE_KEY" in os.environ
        has_kaggle_json = os.path.exists(os.path.expanduser("~/.kaggle/kaggle.json"))

        if not (has_env or has_kaggle_json):
            print("  [CHU Y] Chua phat hien Kaggle API Token trong Secrets hoac bien moi truong.")
            print("  -> Khoi tao luong dang nhap tuong tac qua kagglehub.login()...")
            try:
                kagglehub.login()
            except Exception as auth_err:
                print(f"  [CANH BAO] Khong the hoan tat xac thuc tu dong: {auth_err}")
                print("  Vui long cau hinh KAGGLE_USERNAME & KAGGLE_KEY qua Colab Secrets hoac os.environ.")
        else:
            print("  -> Thong tin xac thuc Kaggle da san sang tu bien moi truong / file config.")

# %% [code]
# ==============================================================================
# BUOC 3: XA NEN DU LIEU TU GOOGLE DRIVE SANG SSD CUC BO
# ==============================================================================
print(f"\n[TIEN TRINH] Buoc 3: Quet va xa nen cac tep ZIP tu Google Drive sang SSD cuc bo...")

zip_files = glob.glob(os.path.join(INPUT_DRIVE_PATH, "**", "*.zip"), recursive=True)
keyframe_zips = [z for z in zip_files if "keyframe" in os.path.basename(z).lower()]

if not keyframe_zips:
    keyframe_zips = zip_files

processed_zip_names = [os.path.basename(z) for z in keyframe_zips]
processed_folder_names = [os.path.splitext(os.path.basename(z))[0] for z in keyframe_zips]

print(f"[THONG TIN] Phat hien {len(keyframe_zips)} tep du lieu ZIP:")
for z_name in processed_zip_names:
    print(f"  - {z_name}")

for idx, zf in enumerate(keyframe_zips, 1):
    folder_name = os.path.splitext(os.path.basename(zf))[0]
    target_dir = os.path.join(LOCAL_EXTRACT_DIR, folder_name)
    if not os.path.exists(target_dir):
        print(f"  [{idx}/{len(keyframe_zips)}] Bat dau xa nen: {os.path.basename(zf)}...")
        try:
            with zipfile.ZipFile(zf, "r") as zip_ref:
                zip_ref.extractall(target_dir)
        except Exception as e:
            print(f"  [LOI] Loi trong qua trinh giai ma tep {zf}: {e}")
    else:
        print(f"  [{idx}/{len(keyframe_zips)}] Du lieu da duoc xa nen truoc do: {os.path.basename(zf)}")

print("[HOAN TAT] Qua trinh giai nen len SSD hoan thanh.")

# %% [code]
# ==============================================================================
# BUOC 4: TONG HOP VA DONG GOI TEP LUU TRU .blob
# ==============================================================================
print(f"\n[TIEN TRINH] Buoc 4: Quet tap tin hinh anh va khoi tao cau truc .blob tren SSD cuc bo.")
image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.webp', '*.JPG', '*.JPEG', '*.PNG']
all_images = []
for ext in image_extensions:
    all_images.extend(glob.glob(os.path.join(LOCAL_EXTRACT_DIR, "**", ext), recursive=True))

all_images = sorted(all_images)
total_images = len(all_images)
print(f"[THONG TIN] Tong cong {total_images:,} khung hinh hop le da duoc xac dinh.")

if total_images == 0:
    raise RuntimeError("[LOI NGHIEM TRONG] Khong phat hien tap tin hinh anh nao. Vui long kiem tra duong dan INPUT_DRIVE_PATH.")

print(f"\n[TIEN TRINH] Dang dong goi du lieu vao: {LOCAL_BLOB_PATH}")
start_pack_time = time.time()

# Su dung chuan ZIP_STORED (Khong nen) nham toi uu hoa chu ky CPU & VRAM khi doc truc tiep ngau nhien
with zipfile.ZipFile(LOCAL_BLOB_PATH, 'w', zipfile.ZIP_STORED) as zipf:
    for i, img_path in enumerate(all_images, 1):
        if i % 10000 == 0 or i == total_images:
            elapsed = time.time() - start_pack_time
            rate = i / elapsed if elapsed > 0 else 0
            print(f"  -> Tien do dong goi: {i:,}/{total_images:,} áº£nh ({i/total_images*100:.1f}%) | Toc do: {rate:.0f} anh/giay")
            
        arcname = os.path.relpath(img_path, LOCAL_EXTRACT_DIR)
        zipf.write(img_path, arcname)

pack_duration = time.time() - start_pack_time
blob_size_bytes = os.path.getsize(LOCAL_BLOB_PATH)
blob_size_gb = blob_size_bytes / (1024 ** 3)
print(f"\n[HOAN TAT] Dong goi .blob thanh cong trong {pack_duration:.1f}s.")
print(f"  -> Kich thuoc tep: {blob_size_gb:.2f} GB ({blob_size_bytes:,} bytes)")
print(f"  -> Vi tri tep: {LOCAL_BLOB_PATH}")

# %% [code]
# ==============================================================================
# BUOC 5: SAO LUU RIENG BIET SANG GOOGLE DRIVE (DRIVE BACKUP)
# ==============================================================================
backup_duration = 0.0
if SAVE_TO_DRIVE:
    print(f"\n[TIEN TRINH] Buoc 5: Tien hanh sao luu tep .blob sang Google Drive...")
    os.makedirs(DRIVE_OUTPUT_DIR, exist_ok=True)
    
    start_backup_time = time.time()
    print(f"  -> Dang sao chep tu SSD sang Google Drive: {DRIVE_BLOB_PATH}...")
    
    shutil.copyfile(LOCAL_BLOB_PATH, DRIVE_BLOB_PATH)
    
    backup_duration = time.time() - start_backup_time
    drive_size_gb = os.path.getsize(DRIVE_BLOB_PATH) / (1024 ** 3)
    print(f"[HOAN TAT] Da sao luu thanh cong sang Google Drive trong {backup_duration:.1f}s.")
    print(f"  -> Dung luong tren Drive: {drive_size_gb:.2f} GB")
    print(f"  -> Duong dan Drive: {DRIVE_BLOB_PATH}")
else:
    print("\n[BO QUA] Tinh nang luu Google Drive dang duoc tat (SAVE_TO_DRIVE = False).")

# %% [code]
# ==============================================================================
# BUOC 6: DANG TAI TRUC TIEP LEN KAGGLE DATASET (KAGGLEHUB UPLOAD)
# ==============================================================================
upload_status = "SKIPPED"
upload_response = None
kaggle_dataset_url = "N/A"
kaggle_input_mount_path = "N/A"
dataset_slug = "N/A"

if UPLOAD_TO_KAGGLE:
    print(f"\n[TIEN TRINH] Buoc 6: Dang tai tap du lieu len Kaggle thong qua kagglehub...")
    
    if "<KAGGLE_USERNAME>" in KAGGLE_HANDLE or "<DATASET_SLUG>" in KAGGLE_HANDLE:
        upload_status = "FAILED_INVALID_HANDLE"
        print("[CANH BAO] Vui long cap nhat KAGGLE_HANDLE voi Username va Dataset Slug that cua ban truoc khi upload.")
        print("  Vi du: KAGGLE_HANDLE = 'nhathoang42/aic2025-keyframes-blob'")
    else:
        dataset_slug = KAGGLE_HANDLE.split('/')[-1].strip()
        kaggle_input_mount_path = f"/kaggle/input/{dataset_slug}/cached_keyframes.blob"
        kaggle_dataset_url = f"https://www.kaggle.com/datasets/{KAGGLE_HANDLE}"
        
        # Tao tep dataset-metadata.json de dam bao tuong thich toan dien
        meta_path = os.path.join(LOCAL_DATASET_DIR, "dataset-metadata.json")
        meta_data = {
            "title": dataset_slug.replace("-", " ").title(),
            "id": KAGGLE_HANDLE,
            "licenses": [{"name": "CC0-1.0"}]
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2)
            
        print(f"  -> Bat dau day du lieu tu: {LOCAL_DATASET_DIR}")
        print(f"  -> Muc tieu Kaggle Handle: {KAGGLE_HANDLE}")
        print(f"  -> Version Notes: {KAGGLE_VERSION_NOTES}")
        print(f"  -> Ignore Patterns: {KAGGLE_IGNORE_PATTERNS}")
        
        # Phuong thuc 1: Thu upload bang kagglehub
        try:
            import kagglehub
            upload_response = kagglehub.dataset_upload(
                handle=KAGGLE_HANDLE,
                local_dataset_dir=LOCAL_DATASET_DIR,
                version_notes=KAGGLE_VERSION_NOTES,
                ignore_patterns=KAGGLE_IGNORE_PATTERNS
            )
            upload_status = "SUCCESS"
            print(f"\n[HOAN TAT] Dang tai Kaggle Dataset thanh cong qua kagglehub.")
            print(f"  -> Dataset URL: {kaggle_dataset_url}")
            print(f"  -> Kaggle Mount Path: {kaggle_input_mount_path}")
            if upload_response:
                print(f"  -> Phan hoi he thong: {upload_response}")
        except Exception as hub_err:
            print(f"  [CANH BAO] kagglehub upload khong thanh cong: {hub_err}")
            print("  -> Chuyen sang Phuong thuc 2: Su dung Kaggle Official API fallback...")
            
            # Phuong thuc 2: Fallback qua Kaggle Official CLI
            try:
                # Kiem tra dataset da ton tai chua
                check_cmd = f"kaggle datasets status {KAGGLE_HANDLE}"
                status_code = os.system(check_cmd)
                
                if status_code == 0:
                    print(f"  -> Phat hien Dataset da ton tai. Tien hanh tao phien ban moi (create new version)...")
                    upload_cmd = f"kaggle datasets version -p {LOCAL_DATASET_DIR} -m \"{KAGGLE_VERSION_NOTES}\" --dir-mode zip"
                else:
                    print(f"  -> Dataset chua ton tai. Tien hanh khoi tao Dataset moi (create new dataset)...")
                    upload_cmd = f"kaggle datasets create -p {LOCAL_DATASET_DIR} --dir-mode zip -r tar"
                
                ret = os.system(upload_cmd)
                if ret == 0:
                    upload_status = "SUCCESS_VIA_KAGGLE_CLI"
                    print(f"\n[HOAN TAT] Dang tai Kaggle Dataset thanh cong qua Kaggle CLI.")
                    print(f"  -> Dataset URL: {kaggle_dataset_url}")
                else:
                    upload_status = f"FAILED_CLI_EXIT_{ret}"
                    print(f"\n[LOI DANG TAI] Ca 2 phuong thuc deu khong thanh cong.")
            except Exception as cli_err:
                upload_status = f"ERROR: {cli_err}"
                print(f"\n[LOI DANG TAI] Loi khi chay Kaggle CLI: {cli_err}")
else:
    print("\n[BO QUA] Tinh nang upload Kaggle dang duoc tat (UPLOAD_TO_KAGGLE = False).")

# %% [code]
# ==============================================================================
# BUOC 7: CAP NHAT TEP GHI CHU & LICH SU DU LIEU TREN GOOGLE DRIVE
# ==============================================================================
print(f"\n[TIEN TRINH] Buoc 7: Cap nhat tep ghi chu & lich su du lieu vao Google Drive...")
os.makedirs(DRIVE_OUTPUT_DIR, exist_ok=True)
current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

# 1. Tao ban ghi Text chi tiet
note_entry = f"""
================================================================================
[BAN GHI LICH SU DU LIEU & DIA CHI TRUY CAP]
Thoi gian ghi nhan: {current_time_str}
--------------------------------------------------------------------------------
1. NOI DUNG DA XU LY (WHAT WAS PROCESSED):
   - Muc dich / Nghiep vu : {DATASET_DESCRIPTION}
   - Quy chuan dong goi   : Tep nhi phan .blob (ZIP_STORED, Khong nen)
   - Thu muc nguon Drive  : {INPUT_DRIVE_PATH}
   - Danh sach goi ZIP    : {len(processed_zip_names)} tep ({', '.join(processed_zip_names)})
   - Cac thu muc tich hop : {', '.join(processed_folder_names)}
   - Tong so khung hinh   : {total_images:,} anh
   - Kich thuoc tep .blob : {blob_size_gb:.2f} GB ({blob_size_bytes:,} bytes)
   - Thoi gian dong goi   : {pack_duration:.1f} giay

2. DIA CHI NGUON 1 - GOOGLE DRIVE:
   - Trang thai luu tru   : {'BAT (Da luu thanh cong)' if SAVE_TO_DRIVE else 'TAT'}
   - Thu muc dich Drive   : {DRIVE_OUTPUT_DIR if SAVE_TO_DRIVE else 'N/A'}
   - Duong dan tep .blob  : {DRIVE_BLOB_PATH if SAVE_TO_DRIVE else 'N/A'}
   - Thoi gian sao luu    : {backup_duration:.1f}s if SAVE_TO_DRIVE else 'N/A'

3. DIA CHI NGUON 2 - KAGGLE DATASETS:
   - Trang thai dang tai  : {'BAT' if UPLOAD_TO_KAGGLE else 'TAT'} (Ket qua: {upload_status})
   - Kaggle Handle        : {KAGGLE_HANDLE if UPLOAD_TO_KAGGLE else 'N/A'}
   - Link truy cap Web    : {kaggle_dataset_url}
   - Duong dan Mount      : {kaggle_input_mount_path}
   - Cu phap tai qua Code : import kagglehub; path = kagglehub.dataset_download('{KAGGLE_HANDLE}')
   - Ghi chu phien ban    : {KAGGLE_VERSION_NOTES if UPLOAD_TO_KAGGLE else 'N/A'}
================================================================================
"""

# Noi them (Append) vao dataset_history_notes.txt
try:
    is_new_file = not os.path.exists(DRIVE_NOTE_PATH)
    with open(DRIVE_NOTE_PATH, "a", encoding="utf-8") as f:
        if is_new_file:
            f.write("# NHAT KY LICH SU KHOI TAO & DONG BO DATASET (AIC 2025)\n")
            f.write("# Tep nay tu dong luu vet chi tiet noi dung da xu ly va 2 dia chi dich (Drive + Kaggle).\n")
        f.write(note_entry)
    print(f"  -> Da cap nhat thanh cong ghi chu van ban: {DRIVE_NOTE_PATH}")
except Exception as e:
    print(f"  [CANH BAO] Khong the cap nhat {DRIVE_NOTE_PATH}: {e}")

# 2. Cap nhat vao tep JSON manifest (dataset_manifest.json)
try:
    manifest_entries = []
    if os.path.exists(DRIVE_MANIFEST_PATH):
        try:
            with open(DRIVE_MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest_entries = json.load(f)
                if not isinstance(manifest_entries, list):
                    manifest_entries = [manifest_entries]
        except Exception:
            manifest_entries = []

    new_manifest_record = {
        "timestamp": current_time_str,
        "dataset_description": DATASET_DESCRIPTION,
        "processing_type": "Virtual Cache Blob (ZIP_STORED, Uncompressed)",
        "source_data": {
            "input_drive_path": INPUT_DRIVE_PATH,
            "zip_count": len(keyframe_zips),
            "processed_zip_names": processed_zip_names,
            "processed_folder_names": processed_folder_names,
            "total_images": total_images,
            "blob_size_gb": round(blob_size_gb, 4),
            "blob_size_bytes": blob_size_bytes,
            "pack_duration_seconds": round(pack_duration, 2)
        },
        "storage_sources": {
            "google_drive": {
                "enabled": SAVE_TO_DRIVE,
                "directory": DRIVE_OUTPUT_DIR if SAVE_TO_DRIVE else None,
                "blob_path": DRIVE_BLOB_PATH if SAVE_TO_DRIVE else None,
                "backup_duration_seconds": round(backup_duration, 2) if SAVE_TO_DRIVE else 0.0
            },
            "kaggle": {
                "enabled": UPLOAD_TO_KAGGLE,
                "upload_status": upload_status,
                "handle": KAGGLE_HANDLE if UPLOAD_TO_KAGGLE else None,
                "web_url": kaggle_dataset_url,
                "kaggle_input_mount_path": kaggle_input_mount_path,
                "python_download_snippet": f"import kagglehub; path = kagglehub.dataset_download('{KAGGLE_HANDLE}')" if UPLOAD_TO_KAGGLE else None,
                "version_notes": KAGGLE_VERSION_NOTES if UPLOAD_TO_KAGGLE else None
            }
        }
    }
    manifest_entries.append(new_manifest_record)

    with open(DRIVE_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_entries, f, ensure_ascii=False, indent=2)
    print(f"  -> Da cap nhat thanh cong tep cau truc JSON: {DRIVE_MANIFEST_PATH}")
except Exception as e:
    print(f"  [CANH BAO] Khong the cap nhat {DRIVE_MANIFEST_PATH}: {e}")

# %% [code]
# ==============================================================================
# BUOC 8: DON DEP PHAN VUNG SSD TAM THOI (TUY CHON)
# ==============================================================================
# Bo ghi chu cac dong duoi day neu ban muon giai phong dung luong SSD Colab sau khi da luu xong
# print("\n[DON DEP] Dang giai phong bo nho tam thoi tren Colab SSD...")
# if os.path.exists(LOCAL_EXTRACT_DIR):
#     shutil.rmtree(LOCAL_EXTRACT_DIR)
#     print(f"  -> Da xoa thu muc tam: {LOCAL_EXTRACT_DIR}")
# print("[HOAN TAT] Toan bo quy trinh tien xu ly va dong bo du lieu da ket thuc thanh cong.")

