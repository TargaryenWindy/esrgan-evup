import os
import subprocess
import threading
import time
import math
import tempfile
import shutil
import glob
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# -------------------- CONFIGURATION VARIABLES --------------------
# Those settings are set to my machine and to process very low res video. (about 640x480),
# Using the settings below I get about 20 fps at this resolution using about 8gb of VRAM.
# So you may want to play with the settings to find the sweet spot to your system.
# For comparison basis, my system:
# Ryzen 9 5950x
# 64gb 3200 MT/s
# RTX 3060 12gb (It's mostly bottle necked by GPU)
# Windows 11 Pro Version 24H2 Build 26100.3194

MAX_CONCURRENT_BATCHES = 5  # Number of batches processed concurrently.
# Depending on your system and your input video resolution, you may wanna lower this value.

MODEL_NAME = "realesr-animevideov3-x2"  # Upscaler model to use with RealESRGAN.
# If you change from x2 to 3x or 4x,
# also change the ESRGAN_SCALE variable to
# match the scale with the model.

STAGGER_DELAY = 10  # Delay in seconds between starting each batch's extraction and processing.
# The sweet spot here is somewhere between when a batch is close to finishing;
# This helps smoothing GPU usage and to not cause a surge in system use.
# To higher res you should increase this value to something about 15-30
# depending on your BATCH_SIZE variable.

# Variables for ESRGAN options:
ESRGAN_SCALE = "2"  # Value for the -s option (scale)
# This value must match the model upscaler multiplier
# otherwise esrgan will assemble the video incorrectly.

ESRGAN_TILE = "1920"  # Value for the -t option (tile size in esrgan)
# Decrease this value to a divisible integer of the video resolution you're inputting
# if you have problems with VRAM.

ESRGAN_EXTRA_ARGS = ""  # Additional ESRGAN arguments.
# Only put add something here if you know what you're doing.

BATCH_SIZE = 20 # Batch size (in seconds). 0 = processes the whole video in one batch.
# Note that if set to 0, the concurrent batches will only be one,
# also if set to 0, make sure you have enough disk space since it'll
# extract all the video frames before starts processing.
# keeping it small it'll extract only what you defined at a time,
# ideal if you don't have much space. Also if you set too large and
# the video is short, it may not have enough batches to be processed
# concurrently by the set value in concurrent batches...

FFMPEG_REASSEMBLY_ARGS = "-c:v libx265 -pix_fmt yuv420p"  # Variable for ffmpeg arguments
# Arguments for the final video encoding with ffmpeg.
# Maybe you should leave as default if you don't know what you're doing.

FINAL_FILE_FORMAT_OVERRIDE = ".mkv" # Overrides final output file format.
# Set to ".mp4" or any other file format to force that format,
# or set to "false" to use the input file's format.

# ------------------------------------------------------------------

def is_integer_fps(fps: float, tol: float = 1e-6) -> bool:
    """Return True if 'fps' is within a small tolerance of an integer."""
    return abs(fps - round(fps)) < tol


def convert_if_needed(video_file, fps, script_dir):
    """
    If the video is already integer fps AND in MP4 format, skip conversion.
    If fps is integer but container is not MP4, remux with -c copy (no re-encode).
    Otherwise, re-encode to MP4 with forced integer fps.
    Returns the path to the resulting file.
    """
    base_name = os.path.splitext(os.path.basename(video_file))[0]
    input_ext = os.path.splitext(video_file)[1].lower()
    output_fps = int(round(fps))
    temp_dir = tempfile.gettempdir()
    converted_path = os.path.join(temp_dir, base_name + "_converted.mp4")

    if is_integer_fps(fps) and input_ext == ".mp4":
        print(f"Skipping conversion (integer fps & already MP4): {video_file}")
        return video_file

    if is_integer_fps(fps):
        if input_ext != ".mp4":
            print(f"Remuxing from {input_ext} to .mp4 (no re-encode).")
            cmd_remux = [
                "ffmpeg",
                "-hide_banner", "-loglevel", "error",
                "-y",
                "-i", video_file,
                "-c", "copy",
                converted_path
            ]
            subprocess.run(cmd_remux, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return converted_path
        else:
            return video_file
    else:
        print(f"Re-encoding {video_file} to MP4 with fps={output_fps}")
        cmd_encode = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-y",
            "-i", video_file,
            "-r", str(output_fps),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            converted_path
        ]
        subprocess.run(cmd_encode, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return converted_path


def get_video_info(video_file):
    """
    Uses ffprobe to get average frame rate, duration, and time_base.
    Returns (fps, duration, time_base).
    Falls back to format metadata if needed.
    """
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate,duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_file
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        lines = result.stdout.splitlines()
        if len(lines) < 2:
            raise ValueError("ffprobe output incomplete.")
        fps_str = lines[0].strip()
        duration_str = lines[1].strip()

        if duration_str == "N/A":
            cmd_format = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_file
            ]
            result_format = subprocess.run(cmd_format, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                           check=True)
            duration_str = result_format.stdout.strip()

        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = float(num) / float(den)
        else:
            fps = float(fps_str)
        duration = float(duration_str)

        cmd_tb = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=time_base",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_file
        ]
        result_tb = subprocess.run(cmd_tb, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        time_base_str = result_tb.stdout.strip()
        if '/' in time_base_str:
            num_tb, den_tb = time_base_str.split('/')
            time_base = float(num_tb) / float(den_tb)
        else:
            time_base = float(time_base_str)
        return fps, duration, time_base
    except Exception as e:
        print(f"Error getting video info for {video_file}: {e}")
        return 24.0, 0.0, 1.0 / 1000


def process_batch(video_file, batch_index, start_time, duration, output_fps, time_base, script_dir, ffmpeg_extra_args,
                  update_progress):
    """
    Processes a single batch:
      - Extracts frames from the converted video at output_fps into one folder.
      - If too few frames are extracted, creates a placeholder segment.
      - Otherwise, starts a polling thread to update progress while calling RealESRGAN once on the folder.
      - Reassembles the processed frames into a video segment using a concat file.
    Returns the path to the segment.
    """
    temp_dir = tempfile.gettempdir()
    base_name = os.path.splitext(os.path.basename(video_file))[0]
    batch_id = f"{base_name}_batch_{batch_index}_{int(time.time())}"
    extraction_dir = os.path.join(temp_dir, batch_id + "_extraction")
    processed_dir = os.path.join(temp_dir, batch_id + "_processed")
    os.makedirs(extraction_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    # Extraction Phase
    cmd_extract = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-ss", str(start_time),
        "-t", str(duration),
        "-y",
        "-i", video_file,
        "-r", str(output_fps),
        os.path.join(extraction_dir, "frame_%06d.png")
    ]
    try:
        subprocess.run(cmd_extract, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"Error extracting frames for batch {batch_index}: {e}")
    time.sleep(2)

    extracted_frames = glob.glob(os.path.join(extraction_dir, "frame_*.png"))
    if len(extracted_frames) < 2:
        print(f"Batch {batch_index}: too few extracted frames ({len(extracted_frames)}). Creating placeholder segment.")
        placeholder_segment = os.path.join(temp_dir, batch_id + "_placeholder.mp4")
        cmd_placeholder = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s=1280x720:d={duration}",
            "-r", str(output_fps),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            placeholder_segment
        ]
        try:
            subprocess.run(cmd_placeholder, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            shutil.rmtree(extraction_dir, ignore_errors=True)
            shutil.rmtree(processed_dir, ignore_errors=True)
            update_progress(len(extracted_frames))
            return placeholder_segment
        except subprocess.CalledProcessError as e:
            print(f"Error generating placeholder segment for batch {batch_index}: {e}")
            return None

    # Processing Phase
    progress_event = threading.Event()

    def poll_progress():
        last_count = 0
        while not progress_event.is_set():
            current_count = len(glob.glob(os.path.join(processed_dir, "frame_*.png")))
            if current_count > last_count:
                delta = current_count - last_count
                update_progress(delta)
                last_count = current_count
            time.sleep(0.5)

    poll_thread = threading.Thread(target=poll_progress)
    poll_thread.start()

    realesrgan_bin = os.path.join(script_dir, "bin", "realesrgan-ncnn-vulkan")
    # Build ESRGAN command with configurable options:
    cmd_esrgan = [
        realesrgan_bin,
        "-i", extraction_dir,
        "-o", processed_dir,
        "-n", MODEL_NAME,
        "-s", ESRGAN_SCALE,
        "-t", ESRGAN_TILE
    ]
    if ESRGAN_EXTRA_ARGS.strip() != "":
        cmd_esrgan.extend(ESRGAN_EXTRA_ARGS.strip().split())
    ESRGAN_TIMEOUT = 600 # Timeout in case some ESRGAN instance staggers.
    max_attempts = 3
    attempt = 0
    success = False
    while attempt < max_attempts and not success:
        try:
            subprocess.run(cmd_esrgan, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=ESRGAN_TIMEOUT)
            success = True
        except subprocess.TimeoutExpired as e:
            attempt += 1
            print(
                f"Timeout: RealESRGAN for batch {batch_index} didn't finish in {ESRGAN_TIMEOUT}s, attempt {attempt}. Retrying...")
            time.sleep(5)
        except subprocess.CalledProcessError as e:
            attempt += 1
            print(f"Error processing frames with RealESRGAN for batch {batch_index}, attempt {attempt}: {e}")
            time.sleep(5)
    progress_event.set()
    poll_thread.join()

    if not success:
        print(f"RealESRGAN failed for batch {batch_index} after {max_attempts} attempts. Creating placeholder segment.")
        placeholder_segment = os.path.join(temp_dir, batch_id + "_placeholder.mp4")
        cmd_placeholder = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s=1280x720:d={duration}",
            "-r", str(output_fps),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            placeholder_segment
        ]
        try:
            subprocess.run(cmd_placeholder, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            shutil.rmtree(extraction_dir, ignore_errors=True)
            shutil.rmtree(processed_dir, ignore_errors=True)
            return placeholder_segment
        except subprocess.CalledProcessError as e:
            print(f"Error generating placeholder segment for batch {batch_index}: {e}")
            return None

    # Reassembly Phase
    if MAX_CONCURRENT_BATCHES == 1:
        # In single batch mode, decouple reassembly into a separate thread to avoid GPU idle time.
        # Move the processed frames to a separate folder for reassembly.
        reassembly_dir = processed_dir + "_for_reassembly"
        shutil.move(processed_dir, reassembly_dir)
        def do_reassembly():
            frame_files = sorted(glob.glob(os.path.join(reassembly_dir, "frame_*.png")))
            if not frame_files:
                print(f"No processed frames found for batch {batch_index}. Creating a placeholder segment.")
                placeholder_segment = os.path.join(temp_dir, batch_id + "_placeholder.mp4")
                cmd_placeholder = [
                    "ffmpeg",
                    "-hide_banner", "-loglevel", "error",
                    "-y",
                    "-f", "lavfi",
                    "-i", f"color=c=black:s=1280x720:d={duration}",
                    "-r", str(output_fps),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    placeholder_segment
                ]
                try:
                    subprocess.run(cmd_placeholder, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    return placeholder_segment
                except subprocess.CalledProcessError as e:
                    print(f"Error generating placeholder segment for batch {batch_index}: {e}")
                    return None
            frames = []
            for filepath in frame_files:
                filename = os.path.basename(filepath)
                try:
                    frame_num = int(filename.split("frame_")[1].split(".png")[0])
                    timestamp = (frame_num - 1) / output_fps
                    frames.append((filepath, timestamp))
                except Exception as e:
                    print(f"Error parsing frame index from {filename}: {e}")
            frames.sort(key=lambda x: x[1])
            concat_list_path = os.path.join(temp_dir, batch_id + "_frames.txt")
            with open(concat_list_path, "w", encoding="utf-8") as f:
                f.write("ffconcat version 1.0\n")
                for i, (filepath, timestamp) in enumerate(frames):
                    if i < len(frames) - 1:
                        duration_sec = 1.0 / output_fps
                        f.write(f"file '{filepath.replace('\\', '\\\\')}'\n")
                        f.write(f"duration {duration_sec:.6f}\n")
                    else:
                        f.write(f"file '{filepath.replace('\\', '\\\\')}'\n")
                        f.write("duration 0.000000\n")
            segment_output = os.path.join(temp_dir, batch_id + "_segment.mp4")
            cmd_concat = [
                "ffmpeg",
                "-hide_banner", "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path,
                "-r", str(output_fps)
            ]
            if FFMPEG_REASSEMBLY_ARGS.strip() != "":
                cmd_concat.extend(FFMPEG_REASSEMBLY_ARGS.strip().split())
            cmd_concat.extend(["-y", "-c:v", "libx264", "-pix_fmt", "yuv420p", segment_output])
            try:
                subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                print(f"Error reassembling video segment for batch {batch_index}: {e}")
            if os.path.exists(concat_list_path):
                os.remove(concat_list_path)
            shutil.rmtree(reassembly_dir, ignore_errors=True)
            return segment_output
        result_container = [None]
        reassembly_thread = threading.Thread(target=lambda: result_container.__setitem__(0, do_reassembly()))
        reassembly_thread.start()
        shutil.rmtree(extraction_dir, ignore_errors=True)
        # Return a tuple containing the result container and the reassembly thread.
        return (result_container, reassembly_thread)
    else:
        # Original reassembly Phase code.
        frame_files = sorted(glob.glob(os.path.join(processed_dir, "frame_*.png")))
        if not frame_files:
            print(f"No processed frames found for batch {batch_index}. Creating a placeholder segment.")
            placeholder_segment = os.path.join(temp_dir, batch_id + "_placeholder.mp4")
            cmd_placeholder = [
                "ffmpeg",
                "-hide_banner", "-loglevel", "error",
                "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s=1280x720:d={duration}",
                "-r", str(output_fps),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                placeholder_segment
            ]
            try:
                subprocess.run(cmd_placeholder, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                shutil.rmtree(extraction_dir, ignore_errors=True)
                shutil.rmtree(processed_dir, ignore_errors=True)
                update_progress(len(extracted_frames))
                return placeholder_segment
            except subprocess.CalledProcessError as e:
                print(f"Error generating placeholder segment for batch {batch_index}: {e}")
                return None
        frames = []
        for filepath in frame_files:
            filename = os.path.basename(filepath)
            try:
                frame_num = int(filename.split("frame_")[1].split(".png")[0])
                timestamp = (frame_num - 1) / output_fps
                frames.append((filepath, timestamp))
            except Exception as e:
                print(f"Error parsing frame index from {filename}: {e}")
        frames.sort(key=lambda x: x[1])
        concat_list_path = os.path.join(temp_dir, batch_id + "_frames.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for i, (filepath, timestamp) in enumerate(frames):
                if i < len(frames) - 1:
                    duration_sec = 1.0 / output_fps
                    f.write(f"file '{filepath.replace('\\', '\\\\')}'\n")
                    f.write(f"duration {duration_sec:.6f}\n")
                else:
                    f.write(f"file '{filepath.replace('\\', '\\\\')}'\n")
                    f.write("duration 0.000000\n")
        segment_output = os.path.join(temp_dir, batch_id + "_segment.mp4")
        cmd_concat = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-r", str(output_fps)
        ]
        if FFMPEG_REASSEMBLY_ARGS.strip() != "":
            cmd_concat.extend(FFMPEG_REASSEMBLY_ARGS.strip().split())
        cmd_concat.extend(["-y", segment_output])
        try:
            subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"Error reassembling video segment for batch {batch_index}: {e}")
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)
        shutil.rmtree(extraction_dir, ignore_errors=True)
        shutil.rmtree(processed_dir, ignore_errors=True)
        return segment_output


def process_video(video_file, script_dir, ffmpeg_extra_args, video_index, total_videos):
    """
    Processes a single video:
      1. Converts the video only if needed (or remuxes) to MP4 with normalized fps.
      2. Splits the resulting video into batches (in seconds defined by BATCH_SIZE; 0 means all at once).
      3. Processes each batch concurrently.
      4. Concatenates the batches and merges with the original audio.
      5. Final output uses the override format if specified, otherwise the input file format.
    """
    print(f"\nProcessing video: {video_file}")
    fps, duration, time_base = get_video_info(video_file)
    if duration <= 0:
        print(f"Skipping {video_file} due to zero duration.")
        return

    video_start_time = time.time()

    # Convert or remux only if needed.
    converted_video = convert_if_needed(video_file, fps, script_dir)

    output_fps = int(round(fps))
    total_frames = int(math.ceil(duration * output_fps))
    if BATCH_SIZE == 0:
        batch_duration = duration
        num_batches = 1
    else:
        batch_duration = BATCH_SIZE
        num_batches = math.ceil(duration / BATCH_SIZE)

    progress_lock = threading.Lock()
    frames_processed = [0]
    batches_completed = [0]
    start_time_progress = time.time()
    progress_done = threading.Event()

    def update_progress(delta):
        with progress_lock:
            frames_processed[0] += delta

    def progress_bar():
        while not progress_done.is_set():
            with progress_lock:
                current = frames_processed[0]
                batches = batches_completed[0]
            elapsed = time.time() - start_time_progress
            proc_fps = current / elapsed if elapsed > 0 else 0
            percentage = (current / total_frames) * 100
            remaining_frames = total_frames - current
            eta_minutes = (remaining_frames / proc_fps) / 60 if proc_fps > 0 else float('inf')
            print(
                f"\rVideo {video_index}/{total_videos} | Batches: {batches}/{num_batches} | Progress: {percentage:6.2f}% ({current}/{total_frames} frames) | Speed: {proc_fps:6.2f} fps | ETA: {eta_minutes:6.1f} min",
                end='', flush=True)
            time.sleep(1)
        with progress_lock:
            current = frames_processed[0]
            batches = batches_completed[0]
        elapsed = time.time() - start_time_progress
        proc_fps = current / elapsed if elapsed > 0 else 0
        percentage = (current / total_frames) * 100
        print(
            f"\rVideo {video_index}/{total_videos} | Batches: {batches}/{num_batches} | Progress: {percentage:6.2f}% ({current}/{total_frames} frames) | Speed: {proc_fps:6.2f} fps | ETA: 0.0 min",
            flush=True)

    progress_thread = threading.Thread(target=progress_bar)
    progress_thread.start()

    segment_files = [None] * num_batches
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BATCHES) as executor:
        future_to_index = {}
        for batch_index in range(num_batches):
            time.sleep(STAGGER_DELAY)  # Stagger batch extraction start.
            start_time_batch = batch_index * batch_duration
            current_duration = min(batch_duration, duration - start_time_batch)
            future = executor.submit(
                process_batch,
                converted_video,
                batch_index,
                start_time_batch,
                current_duration,
                output_fps,
                time_base,
                script_dir,
                ffmpeg_extra_args,
                update_progress
            )
            future_to_index[future] = batch_index
        for future in as_completed(future_to_index):
            batch_index = future_to_index[future]
            try:
                result = future.result()
                segment_files[batch_index] = result
                with progress_lock:
                    batches_completed[0] += 1
            except Exception as exc:
                print(f"\nBatch {batch_index + 1} generated an exception: {exc}")

    progress_done.set()
    progress_thread.join()

    # If any batch returned a tuple (due to decoupled reassembly), join the thread to get the segment output.
    for i, seg in enumerate(segment_files):
        if isinstance(seg, tuple):
            result_container, reassembly_thread = seg
            reassembly_thread.join()
            segment_files[i] = result_container[0]

    if converted_video != video_file and os.path.exists(converted_video):
        os.remove(converted_video)

    # Concatenate segments.
    temp_dir = tempfile.gettempdir()
    concat_list_file = os.path.join(temp_dir, f"{os.path.splitext(os.path.basename(video_file))[0]}_segments.txt")
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for seg in segment_files:
            if seg is not None:
                f.write(f"file '{seg.replace('\\', '\\\\')}'\n")
            else:
                print("Warning: A batch segment is missing and will be skipped.")
    video_no_audio = os.path.join(temp_dir, f"{os.path.splitext(os.path.basename(video_file))[0]}_no_audio.mp4")
    cmd_concat = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-f", "concat",
        "-safe", "0",
        "-y",
        "-i", concat_list_file,
        "-c", "copy",
        video_no_audio
    ]
    try:
        subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"Error concatenating video segments: {e}")
        return

    # Determine final output file format.
    if FINAL_FILE_FORMAT_OVERRIDE.lower() != "false":
        final_ext = FINAL_FILE_FORMAT_OVERRIDE
    else:
        final_ext = os.path.splitext(video_file)[1]

    output_dir = os.path.join(script_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, os.path.splitext(os.path.basename(video_file))[0] + final_ext)
    cmd_merge = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", video_no_audio,
        "-i", video_file,
        "-map", "0:v",
        "-map", "1:a",
        "-c", "copy",
        "-map_metadata", "1",
        output_file
    ]
    try:
        subprocess.run(cmd_merge, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"Error merging audio and video: {e}")
        return

    for seg in segment_files:
        if seg and os.path.exists(seg):
            os.remove(seg)
    if os.path.exists(concat_list_file):
        os.remove(concat_list_file)
    if os.path.exists(video_no_audio):
        os.remove(video_no_audio)

    video_elapsed = time.time() - video_start_time
    minutes = int(video_elapsed // 60)
    seconds = video_elapsed % 60
    print(f"\nFinished processing {video_file}. Output saved to {output_file}")
    print(f"Elapsed time for this video: {minutes} min {seconds:4.1f} sec\n")
    return video_elapsed


def main():
    print("Script started!")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(script_dir, "input")
    print(f"Looking for videos in: {input_dir}")
    ffmpeg_extra_args = []  # Extra ffmpeg arguments if needed.

    video_files = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            video_files.append(os.path.join(root, file))
    total_videos = len(video_files)
    if total_videos == 0:
        print("No video files found in input folder.")
        return

    total_elapsed = 0
    processed_videos = 0
    for i, video_path in enumerate(video_files, start=1):
        print(f"\n--- Processing video {i}/{total_videos} ---")
        elapsed = process_video(video_path, script_dir, ffmpeg_extra_args, i, total_videos)
        if elapsed is not None:
            processed_videos += 1
            total_elapsed += elapsed
            print(f"Global progress: {processed_videos}/{total_videos} videos processed.")
    if processed_videos > 0:
        total_minutes = int(total_elapsed // 60)
        total_seconds = total_elapsed % 60
        print(f"\nTotal elapsed time for all videos: {total_minutes} min {total_seconds:4.1f} sec")
    else:
        print("No videos were processed.")


if __name__ == "__main__":
    print("Running script...")
    main()
    print("Script completed!")
