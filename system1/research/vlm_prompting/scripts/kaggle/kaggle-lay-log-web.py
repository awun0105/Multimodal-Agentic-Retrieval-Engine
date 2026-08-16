"""Lay log chay bang cach goi thang endpoint log cua Kaggle.

kernels_output() treo khi lan chay bi loi (khong co output de tai). Endpoint
/kernels/{slug}/output tra ve JSON co truong log rieng, doc duoc ca khi loi.
"""

import truststore

truststore.inject_into_ssl()

import json
import sys

import requests
from kaggle.api.kaggle_api_extended import KaggleApi

SLUG = "trnkhoa40phm/notebook4764945a8d"

api = KaggleApi()
api.authenticate()

phien = requests.Session()
phien.auth = (api.config_values["username"], api.config_values["key"])

url = "https://www.kaggle.com/api/v1/kernels/output"
r = phien.get(url, params={"userName": SLUG.split("/")[0], "kernelSlug": SLUG.split("/")[1]}, timeout=90)
print("HTTP", r.status_code)

if r.status_code != 200:
    print(r.text[:1500])
    sys.exit(1)

du_lieu = r.json()
print("Cac truong:", list(du_lieu.keys()))

log = du_lieu.get("log")
if not log:
    print("Khong co truong log. Toan bo JSON (cat 2000):")
    print(json.dumps(du_lieu, indent=2)[:2000])
    sys.exit(0)

try:
    muc = json.loads(log) if isinstance(log, str) else log
except Exception:
    print(str(log)[-6000:])
    sys.exit(0)

for m in muc:
    chu = (m.get("data") or "").rstrip()
    if chu:
        print(f"[{m.get('stream_name', '')}] {chu[:500]}")
