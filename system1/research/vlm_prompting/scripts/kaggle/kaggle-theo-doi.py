"""Doc trang thai phien Kaggle dang chay + log gan nhat."""

import truststore

truststore.inject_into_ssl()

import argparse
from kaggle.api.kaggle_api_extended import KaggleApi

SLUG = "trnkhoa40phm/notebook4764945a8d"

p = argparse.ArgumentParser()
p.add_argument("--log", action="store_true", help="in ca log chay")
p.add_argument("--dong-log", type=int, default=30)
args = p.parse_args()

api = KaggleApi()
api.authenticate()

st = api.kernels_status(SLUG)
print("Trang thai:", getattr(st, "status", st))
loi = getattr(st, "failure_message", None) or getattr(st, "failureMessage", None)
if loi:
    print("Loi:", loi)

if args.log:
    import json

    try:
        raw = api.kernels_output(SLUG, path=None)
        print("Output files:", raw)
    except Exception as e:
        print("Chua co output:", type(e).__name__, str(e)[:200])
