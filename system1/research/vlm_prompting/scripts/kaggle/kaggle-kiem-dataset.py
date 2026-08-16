import truststore

truststore.inject_into_ssl()

from kaggle.api.kaggle_api_extended import KaggleApi

api = KaggleApi()
api.authenticate()

slug = f"{api.config_values['username']}/aic-vlm-distill-290"

# dataset_list_files mac dinh page_size=20 -- goi mot lan chi thay 20 file dau,
# de tuong dataset thieu anh roi di upload lai ca bo.
ten_file = []
token = None
while True:
    trang = api.dataset_list_files(slug, page_token=token, page_size=200)
    ten_file += [f.name for f in trang.files]
    token = getattr(trang, "nextPageToken", None) or getattr(trang, "next_page_token", None)
    if not token or not trang.files:
        break

anh = [n for n in ten_file if n.lower().endswith(".jpg")]
khac = [n for n in ten_file if n not in anh]

print(f"Dataset : {slug}")
print(f"Tong file: {len(ten_file)}")
print(f"Anh jpg  : {len(anh)}")
print(f"File khac: {khac}")
