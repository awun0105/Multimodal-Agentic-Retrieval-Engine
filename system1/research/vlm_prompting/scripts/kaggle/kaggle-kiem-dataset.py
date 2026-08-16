import truststore

truststore.inject_into_ssl()

from kaggle.api.kaggle_api_extended import KaggleApi

api = KaggleApi()
api.authenticate()

slug = f"{api.config_values['username']}/aic-vlm-distill-290"
for f in api.dataset_list_files(slug).files:
    print(f"{f.name}  {getattr(f, 'total_bytes', '?')}")
