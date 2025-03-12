from typing import Dict, List
from twelvelabs.models import SearchResult

PROJECT = "250219_nif_ndby_LKW_Crash"
LOCAL_VIDEO_PATH = (
    "~/Downloads/12labs/250219_nif_ndby_LKW_Crash/250219_News5_LKW_Crash_A3_1.mp4"
)
RAW_NEWS_FILE_PATH = "~/Downloads/12labs/250219_nif_ndby_LKW_Crash/translated_raw.txt"
TWELVELABS_INDEX_ID = "67cf4c17c14a54d6e58d1388"
TWELVELABS_VIDEO_ID = "67cf69a8f45d9b64a583534c"
CACHED_SEARCH_TO_CLIPS: Dict[str, List[SearchResult]] = {}
CLIPS_USED = {}


# PROJECT = "250221_nif_schw_irrfahrt_rentner"
# LOCAL_VIDEO_PATH = "~/Downloads/12labs/250221_nif_schw_irrfahrt_rentner/250221_NSN_Renterunfall Neu_Ulm_1_lowres.mp4"
# RAW_NEWS_FILE_PATH = (
#     "~/Downloads/12labs/250221_nif_schw_irrfahrt_rentner/translated.txt"
# )
# TWELVELABS_INDEX_ID = "67cf4c17c14a54d6e58d1388"
# TWELVELABS_VIDEO_ID = "67cf699ff45d9b64a5835347"
# CACHED_SEARCH_TO_CLIPS: Dict[str, List[SearchResult]] = {}
# CLIPS_USED = {}
