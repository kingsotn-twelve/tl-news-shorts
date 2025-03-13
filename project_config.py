from typing import Dict, List
from twelvelabs.models import SearchResult
from twelvelabs import TwelveLabs
import os
import dotenv
import subprocess

dotenv.load_dotenv()

# required project_config.py
TWELVELABS_VIDEO_ID = "67b3ef688f8834a99810eded"
TWELVELABS_INDEX_ID = "67b3eb57df4e60cf3c78f7a3"
LOCAL_VIDEO_PATH = None
RAW_NEWS_FILE_PATH = None
CACHED_SEARCH_TO_CLIPS: Dict[str, List[SearchResult]] = {}
CLIPS_USED = {}
# TYPE_PROMPT = "create a concise, factual voiceover text"
TYPE_PROMPT = "exciting and engaging voiceover text"


# automate retreival of video and "news" file
twelve_client = TwelveLabs(api_key=os.getenv("TWELVELABS_API_KEY"))
video = twelve_client.index.video.retrieve(
    index_id=TWELVELABS_INDEX_ID, id=TWELVELABS_VIDEO_ID
)
if video.hls.video_url:
    PROJECT = video.id
    # download the m3u8 video from the url to an mp4 using ffmpeg if we don't have a local video path
    print(f"video.hls.video_url: {video.hls.video_url}")

    # Create the project directory if it doesn't exist
    project_dir = f"videos/{PROJECT}"
    os.makedirs(project_dir, exist_ok=True)

    if not LOCAL_VIDEO_PATH:
        LOCAL_VIDEO_PATH = f"{project_dir}/raw_video.mp4"
        if not os.path.exists(LOCAL_VIDEO_PATH):
            cmd = [
                "ffmpeg",
                "-i",
                video.hls.video_url,
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-threads",
                "4",
                "-movflags",
                "+faststart",
                "-y",
                LOCAL_VIDEO_PATH,
            ]
            subprocess.run(cmd, check=True)
        print(f"video exists at {LOCAL_VIDEO_PATH}")

    # make a pegasus summary call if we don't have a news file
    if not RAW_NEWS_FILE_PATH:
        video_summary = twelve_client.generate.summarize(
            video_id=TWELVELABS_VIDEO_ID, type="summary"
        )
        RAW_NEWS_FILE_PATH = f"{project_dir}/raw_news.txt"
        with open(RAW_NEWS_FILE_PATH, "w") as f:
            f.write(video_summary.summary)
        print(f"Generated summary to {RAW_NEWS_FILE_PATH}")


# validate that we have values for all required variables
if (
    not TWELVELABS_INDEX_ID
    or not TWELVELABS_VIDEO_ID
    or not LOCAL_VIDEO_PATH
    or not RAW_NEWS_FILE_PATH
):
    raise ValueError("Missing required variables")
