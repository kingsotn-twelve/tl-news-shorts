import subprocess
from typing import List, Dict
import uuid
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from openai import OpenAI
from pydantic import BaseModel, Field
from twelvelabs import TwelveLabs
from twelvelabs.models import SearchResult
from elevenlabs import VoiceSettings
import os
import json
from datetime import datetime
from project_config import (
    PROJECT,
    LOCAL_VIDEO_PATH,
    RAW_NEWS_FILE_PATH,
    TWELVELABS_INDEX_ID,
    TWELVELABS_VIDEO_ID,
    CACHED_SEARCH_TO_CLIPS,
    CLIPS_USED,
)

load_dotenv()


class ReturnedSearchResult(BaseModel):
    clips: List[SearchResult]
    id: str


class StoryBoardEvent(BaseModel):
    index: int
    highlight_description: str = Field(
        description="A description of the key moment in the video. Short and concise 5-10 words."
    )
    summary: str = Field(description="A concise summary of the key moment in the video")
    shot_type: str = Field(
        description="The type of shot to be used for the event, eg. wide, close-up, etc."
    )


class StoryBoard(BaseModel):
    location: str
    storyboard: List[StoryBoardEvent]


def create_storyboard(raw_news_file_path: str) -> StoryBoard:
    SYSTEM_PROMPT = """Generate a structured JSON storyboard highlighting key moments in a video. ensure that the final storyboard can be narrated in around 25 seconds long"""

    # Expand the tilde to the user's home directory
    expanded_path = os.path.expanduser(raw_news_file_path)

    # Check if file exists before opening
    if not os.path.exists(expanded_path):
        raise FileNotFoundError(f"File not found: {raw_news_file_path}")

    with open(expanded_path, "r") as file:
        raw_news = file.read()

    client = OpenAI()
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Raw news: {raw_news}"},
        ],
        response_format=StoryBoard,
    )

    storyboard: StoryBoard = completion.choices[0].message.parsed

    print(storyboard)

    return storyboard


class VoiceOver(BaseModel):
    to_voiceover: str


def create_voiceover_text(storyboard: StoryBoard, raw_news_file_path: str) -> str:
    client = OpenAI()
    SYSTEM_PROMPT = """Using the provided JSON highlights and raw news, create a concise, factual voiceover text (about 25 seconds) clearly summarizing key events. Emphasize precise details."""
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Raw news: {raw_news_file_path}"},
            {"role": "user", "content": f"Storyboard: {storyboard}"},
        ],
        response_format=VoiceOver,
    )
    voiceover: VoiceOver = completion.choices[0].message.parsed

    voiceover_text = voiceover.to_voiceover
    location = storyboard.location

    return_text = f"{location}\n\n{voiceover_text}"
    return return_text


def generate_audio(text):
    client = ElevenLabs(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
    )

    response = client.text_to_speech.convert(
        text=text,
        voice_id="JBFqnCBsd6RMkjVDRZzb",
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            speed=1.1,
        ),
    )

    save_file_path = f"audio/{PROJECT}.mp3"
    os.makedirs(os.path.dirname(save_file_path), exist_ok=True)

    # Remove existing file if present
    if os.path.exists(save_file_path):
        os.remove(save_file_path)

    with open(save_file_path, "wb") as f:
        for chunk in response:
            if chunk:
                f.write(chunk)

    print(f"{save_file_path}: A new audio file was saved successfully!")
    return save_file_path


def get_clips(storyboard: StoryBoard):
    client = TwelveLabs(
        api_key=os.getenv("TWELVELABS_API_KEY"),
        version="v1.3",
    )

    for s in storyboard.storyboard:
        res: SearchResult = client.search.query(
            index_id=TWELVELABS_INDEX_ID,
            options=["visual", "audio"],
            query_text=s.highlight_description,
            filter={"id": [TWELVELABS_VIDEO_ID]},
        )

        CACHED_SEARCH_TO_CLIPS[s.highlight_description] = res

        print(f"<{s.highlight_description}>: {res}\n")

    return


def combine_clips(storyboard: StoryBoard) -> str:
    os.makedirs("videos", exist_ok=True)
    unique_id = str(uuid.uuid4())
    output_path = f"videos/{PROJECT}_{unique_id}.mp4"
    expanded_video_path = os.path.expanduser(LOCAL_VIDEO_PATH)
    absolute_video_path = os.path.abspath(expanded_video_path)

    # Create a directory for temporary clip files
    temp_dir = f"videos/temp_{unique_id}"
    os.makedirs(temp_dir, exist_ok=True)

    if not os.path.exists(absolute_video_path):
        raise FileNotFoundError(f"Video file not found: {absolute_video_path}")

    # Create a list to store paths to individual clip files
    clip_files = []

    print(f"Extracting individual clips...")
    for idx, s in enumerate(storyboard.storyboard):
        highlight_description = s.highlight_description
        if highlight_description not in CACHED_SEARCH_TO_CLIPS:
            print(f"No clips found for: {highlight_description}")
            continue

        search_results = CACHED_SEARCH_TO_CLIPS[highlight_description]
        print(f"Processing clips for: {highlight_description}")

        # Check each result until we find a non-overlapping one
        clip_added = False
        for result in search_results.data:
            start, end = result.start, result.end
            if end - start > 6:  # Shorten long clips
                end = start + 6

            # Create a unique key for this clip
            clip_key = f"{result.video_id}_{start}_{end}"

            # Check for overlap with already used clips
            overlap = False
            for used_key, time_ranges in CLIPS_USED.items():
                for used_start, used_end in time_ranges:
                    if start < used_end and end > used_start:
                        overlap = True
                        break
                if overlap:
                    break

            if not overlap:
                # No overlap, use this clip
                if clip_key not in CLIPS_USED:
                    CLIPS_USED[clip_key] = []
                CLIPS_USED[clip_key].append((start, end))

                # Extract the clip with proper keyframe alignment
                clip_file = os.path.join(temp_dir, f"clip_{idx}.mp4")

                # Use segment option to ensure clean cuts at keyframes
                subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        absolute_video_path,
                        "-ss",
                        str(start),
                        "-to",
                        str(end),
                        "-c:v",
                        "libx264",  # Re-encode with h264
                        "-preset",
                        "fast",  # Fast encoding
                        "-force_key_frames",
                        f"expr:gte(t,{start})",  # Force keyframe at start
                        "-c:a",
                        "aac",  # Re-encode audio
                        "-avoid_negative_ts",
                        "1",
                        clip_file,
                    ]
                )

                clip_files.append(clip_file)

                print(
                    f"Added clip for '{highlight_description}' ({start:.2f} to {end:.2f})"
                )
                clip_added = True
                break

        if not clip_added:
            print(f"Could not find non-overlapping clip for: {highlight_description}")

    print(f"Extracted {len(clip_files)} individual clips")

    # Create a file list for concatenation
    concat_list_path = os.path.join(temp_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for clip_file in clip_files:
            # Use absolute paths in the concat file
            abs_clip_path = os.path.abspath(clip_file)
            f.write(f"file '{abs_clip_path}'\n")

    # Concatenate the clips using the concat demuxer
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c",
            "copy",
            output_path,
        ]
    )

    # Clean up temporary files
    # import shutil
    # shutil.rmtree(temp_dir)

    return output_path


def combine_audio_and_video(combined_clips_path: str, audio_file_path: str) -> str:
    # Create project-specific directory under combined/
    project_dir = f"combined/{PROJECT}"
    os.makedirs(project_dir, exist_ok=True)

    # Generate unique ID for this operation
    unique_id = str(uuid.uuid4())

    # Create output file path with unique ID
    final_output_path = f"{project_dir}/{PROJECT}_final_{unique_id}.mp4"

    # Create temporary file for mixed audio
    temp_mixed_audio = f"{project_dir}/{PROJECT}_mixed_audio_{unique_id}.mp3"

    # First, mix the original audio with the voiceover with better volume control
    # Using volume detection and normalization before mixing
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                combined_clips_path,  # Original video with audio
                "-i",
                audio_file_path,  # Voiceover audio
                "-filter_complex",
                # Normalize both audio streams, then apply volume adjustments
                "[0:a]volume=0.05[a1];[1:a]volume=1.0[a2];[a1][a2]amix=inputs=2:duration=longest",
                "-c:a",
                "mp3",
                temp_mixed_audio,
            ],
            check=True,
        )

        # Then combine the mixed audio with the original video
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                combined_clips_path,  # Original video
                "-i",
                temp_mixed_audio,  # Mixed audio
                "-map",
                "0:v",  # Use video from first input
                "-map",
                "1:a",  # Use audio from second input
                "-c:v",
                "copy",  # Copy video codec
                "-c:a",
                "aac",  # Convert audio to AAC
                "-shortest",  # End when shortest input ends
                final_output_path,
            ],
            check=True,
        )

        # Clean up temporary file
        if os.path.exists(temp_mixed_audio):
            os.remove(temp_mixed_audio)

    except subprocess.CalledProcessError as e:
        print(f"Error during audio/video processing: {e}")
        if os.path.exists(temp_mixed_audio):
            os.remove(temp_mixed_audio)
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        if os.path.exists(temp_mixed_audio):
            os.remove(temp_mixed_audio)
        raise

    return final_output_path


def save_artifacts(storyboard: StoryBoard, voiceover_text: str):
    """Save project artifacts to the project directory"""

    # Create project directory if it doesn't exist
    project_dir = f"combined/{PROJECT}"
    os.makedirs(project_dir, exist_ok=True)

    # Save storyboard as JSON
    with open(f"{project_dir}/storyboard.json", "w") as f:
        f.write(storyboard.model_dump_json(indent=2))

    # Save voiceover text
    with open(f"{project_dir}/voiceover_text.txt", "w") as f:
        f.write(voiceover_text)

    # Save clips searched data
    with open(f"{project_dir}/clips_searched.json", "w") as f:
        # Convert SearchResult objects to serializable format
        serializable_clips = {}
        for key, search_result in CACHED_SEARCH_TO_CLIPS.items():
            # Convert the search result to a dict representation
            if hasattr(search_result, "model_dump"):
                serializable_clips[key] = search_result.model_dump()
            else:
                # Fallback for non-pydantic objects
                serializable_clips[key] = str(search_result)

        json.dump(serializable_clips, f, indent=2)

    # Save a copy of the project config
    with open(f"{project_dir}/project_config.py", "w") as f:
        f.write(f"# Project config saved on {datetime.now().isoformat()}\n\n")
        f.write(f"PROJECT = {repr(PROJECT)}\n")
        f.write(f"LOCAL_VIDEO_PATH = {repr(LOCAL_VIDEO_PATH)}\n")
        f.write(f"RAW_NEWS_FILE_PATH = {repr(RAW_NEWS_FILE_PATH)}\n")
        f.write(f"TWELVELABS_INDEX_ID = {repr(TWELVELABS_INDEX_ID)}\n")
        f.write(f"TWELVELABS_VIDEO_ID = {repr(TWELVELABS_VIDEO_ID)}\n")


if __name__ == "__main__":
    storyboard = create_storyboard(RAW_NEWS_FILE_PATH)
    print("finished creating storyboard")

    to_voiceover = create_voiceover_text(storyboard, RAW_NEWS_FILE_PATH)
    print("finished creating voiceover text")

    get_clips(storyboard)
    print("found clips on twelvelabs")

    combined_clips_path = combine_clips(storyboard)
    print(f"finished combining clips: {combined_clips_path}")

    audio_file_path = generate_audio(to_voiceover)
    print("finished generating audio")

    # Save all artifacts
    save_artifacts(storyboard, to_voiceover)
    print("saved project artifacts")

    final_output_path = combine_audio_and_video(combined_clips_path, audio_file_path)
    print(f"finished combining audio and video: {final_output_path}")
