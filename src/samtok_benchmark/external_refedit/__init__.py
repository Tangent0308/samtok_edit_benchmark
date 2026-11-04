"""RefEdit-Bench external evaluation; independent of the frozen IF-Bench release and of external_mira."""

DATASET_REPO = "bpathir1/RefEdit-Bench"
DATASET_REVISION = "71fc847382cf4fd8da03de18b6138d383ad6eb00"
DATASET_FILE = "data/test-00000-of-00001.parquet"
DATASET_BYTES = 9141763
OFFICIAL_CODE = "https://github.com/bimsarapathiraja/refedit"
OFFICIAL_COMMIT = "3b4fb55d0ff0e7df124385db1f1afeddeb24b879"
METHOD_COMMIT = "aa5a414e36c01eba60b37fc46cb9e32f803f8a93"
NUM_CASES = 200
EASY_CASES = 100
MODELS = ("sitedit", "qwen21", "qwen2511", "replan", "mirage", "flux3", "mice", "flux2_klein9b")
