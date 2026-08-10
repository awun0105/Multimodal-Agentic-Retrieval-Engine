# %% [markdown]
# # Google Colab: Tiền xử lý và Đóng gói Dữ liệu (Data Preparation)
#
# **Mô tả:**
# Kịch bản này chịu trách nhiệm tiền xử lý dữ liệu trên môi trường Google Colab. 
# Nhằm khắc phục giới hạn nghiêm ngặt về số lượng tập tin (I/O bottleneck) và dung lượng 
# ổ đĩa (20GB) trên Kaggle, quy trình này sẽ tổng hợp toàn bộ tập dữ liệu ảnh thành một 
# tệp lưu trữ nhị phân duy nhất (`.blob`).
#
# **Cơ chế hoạt động:**
# 1. Định vị và giải nén các tệp `.zip` từ Google Drive vào phân vùng SSD cục bộ của Colab.
# 2. Tổng hợp các tệp hình ảnh và đóng gói vào định dạng tệp lưu trữ không nén (`.blob`) nhằm tối ưu tốc độ đọc tuyến tính.
# 3. Bảo tồn tuyệt đối cấu trúc thư mục tương đối của mỗi tệp tin nhằm duy trì khả năng truy xuất nguồn gốc (provenance).
#
# **Hướng dẫn sử dụng:**
# 1. Thực thi Notebook này trên Google Colab.
# 2. Chờ hệ thống xử lý hoàn tất và lấy tệp `.blob` đầu ra từ Google Drive.
# 3. Đăng tải (Upload) tệp `.blob` lên hệ thống Kaggle dưới dạng một Dataset.

# %% [code]
import os
import zipfile
import glob
try:
    from google.colab import drive
except ImportError:
    print("[CẢNH BÁO] Thư viện google.colab không tồn tại. Script này yêu cầu môi trường Google Colab.")

# ==============================================================================
# CẤU HÌNH ĐƯỜNG DẪN HỆ THỐNG
# ==============================================================================
# Gắn kết (Mount) không gian lưu trữ Google Drive
if 'drive' in globals():
    drive.mount('/content/drive')

# Thư mục gốc chứa các tệp dữ liệu .zip trên Google Drive
INPUT_DRIVE_PATH = "/content/drive/MyDrive/AIC2025" 

# Đường dẫn đích cho tệp lưu trữ dữ liệu tập trung. 
# Lưu ý: Sử dụng phần mở rộng .blob nhằm tránh việc Kaggle tự động xả nén.
os.makedirs("/content/drive/MyDrive/AIC_Nhat", exist_ok=True)
OUTPUT_BLOB_PATH = "/content/drive/MyDrive/AIC_Nhat/cached_keyframes.blob"

# Thư mục tạm thời trên phân vùng SSD cục bộ của Colab để tăng tốc độ truy xuất
LOCAL_EXTRACT_DIR = "/content/extracted_keyframes"
os.makedirs(LOCAL_EXTRACT_DIR, exist_ok=True)

# %% [code]
# ==============================================================================
# BƯỚC 1: XẢ NÉN DỮ LIỆU CỤC BỘ
# ==============================================================================
print(f"[TIẾN TRÌNH] Bước 1: Xả nén các tệp lưu trữ từ Google Drive sang SSD cục bộ.")
zip_files = glob.glob(os.path.join(INPUT_DRIVE_PATH, "**", "*.zip"), recursive=True)
keyframe_zips = [z for z in zip_files if "keyframe" in os.path.basename(z).lower()]
print(f"[THÔNG TIN] Khám phá được {len(keyframe_zips)} tệp dữ liệu Keyframes định dạng ZIP.")

for zf in keyframe_zips:
    folder_name = os.path.splitext(os.path.basename(zf))[0]
    target_dir = os.path.join(LOCAL_EXTRACT_DIR, folder_name)
    if not os.path.exists(target_dir):
        print(f"  -> Bắt đầu xả nén: {os.path.basename(zf)}...")
        try:
            with zipfile.ZipFile(zf, "r") as zip_ref:
                zip_ref.extractall(target_dir)
        except Exception as e:
            print(f"  [LỖI CỤC BỘ] Lỗi trong quá trình giải mã tệp {zf}: {e}")
    else:
        print(f"  -> Dữ liệu đã được xả nén trước đó: {os.path.basename(zf)}")

# %% [code]
# ==============================================================================
# BƯỚC 2: TỔNG HỢP VÀ ĐÓNG GÓI DỮ LIỆU
# ==============================================================================
print(f"\n[TIẾN TRÌNH] Bước 2: Quét tập tin và khởi tạo cấu trúc .blob.")
exts = ['*.jpg', '*.jpeg', '*.png', '*.webp', '*.JPG', '*.JPEG', '*.PNG']
all_images = []
for ext in exts:
    all_images.extend(glob.glob(os.path.join(LOCAL_EXTRACT_DIR, "**", ext), recursive=True))

all_images = sorted(all_images)
print(f"[THÔNG TIN] Tổng cộng {len(all_images)} khung hình hợp lệ đã được xác định.")

if len(all_images) > 0:
    print(f"\n[THÔNG TIN] Tiến hành lưu trữ tệp tin tại địa chỉ: {OUTPUT_BLOB_PATH}")
    
    # Sử dụng chuẩn ZIP_STORED (Không nén) nhằm tối ưu hóa chu kỳ CPU khi giải mã tuần tự
    with zipfile.ZipFile(OUTPUT_BLOB_PATH, 'w', zipfile.ZIP_STORED) as zipf:
        for i, img_path in enumerate(all_images):
            if i > 0 and i % 10000 == 0:
                print(f"  -> Tiến độ tích hợp: {i}/{len(all_images)} khung hình...")
                
            # Trích xuất đường dẫn tương đối nhằm duy trì cấu trúc định danh dữ liệu
            # Ví dụ: /content/extracted_keyframes/Keyframes_L25/L25_V001/0001.jpg 
            # -> Keyframes_L25/L25_V001/0001.jpg
            arcname = os.path.relpath(img_path, LOCAL_EXTRACT_DIR)
            zipf.write(img_path, arcname)
            
    print(f"\n[HOÀN TẤT] Quy trình đóng gói đã kết thúc thành công.")
else:
    print("[LỖI NGHIÊM TRỌNG] Không phát hiện tập tin hình ảnh nào. Vui lòng kiểm tra quá trình Mount và đường dẫn nguồn.")
