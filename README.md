# Real-ESRGAN Efficient Video Upscaler
This project is a batch-based video upscaler designed to make efficient use of Real-ESRGAN-ncnn-vulkan by running concurrent batches, ensuring optimal GPU utilization.

# How It Works
The script splits a video into batches of frames, processes them concurrently, then put the video back together while maintaining audio and metadata.

# Key Features
* **Efficient GPU usage** – prevents idle time and maximizes performance;
* **Concurrent batch processing** – improves speed and efficiency;
* **Automated video queueing** – processes all videos in the input folder;
* **Automatic reassembly** – merges video with original audio seamlessly;
* **Low storage usage** – processes in chunks instead of extracting all frames at once.

# Installation

## 1. Install Dependencies

Before running the script, make sure [**FFmpeg**] installed and added to your system PATH. You can download it from: [**FFmpeg Releases**](https://github.com/BtbN/FFmpeg-Builds/releases)
Alternatively, on Windows, you can Chocolatey to install FFmpeg:

### Install Chocolatey (If not installed)
Run the following command in **Powershell** (as admin):
```
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```
Install FFmpeg via choco:
```
choco install ffmpeg
```
## 2. Download & Set Up the Script
Clone the repository and run the setup script:
```
git clone https://github.com/TargaryenWindy/esrgan-evup.git
cd esrgan-evup
python setup.py #download and unzip the ESRGAN-NCNN-vulkan and models automatically
```

# Usage
1. **Place a video or various video files into the input folder.**
2. **Run the script**:
```
python run.py
```
3. It'll start processing the video. After it finishes the upscalled video will be available in the output folder.

# Configuration
## All settings are at the beginning of the script and can be customized.
### Script setings:
```
MAX_CONCURRENT_BATCHES = 2  # Number of batches processed concurrently.
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

BATCH_SIZE = 20 # Batch size (in seconds). 0 = processes the whole video in one batch.
# Note that if set to 0, the concurrent batches will only be one,
# also if set to 0, make sure you have enough disk space since it'll
# extract all the video frames before starts processing.
# keeping it small it'll extract only what you defined at a time,
# ideal if you don't have much space. Also if you set too large and
# the video is short, it may not have enough batches to be processed
# concurrently by the set value in concurrent batches.

FINAL_FILE_FORMAT_OVERRIDE = "false" # Overrides final output file format.
# Set to ".mp4" or any other file format to force that format,
# or set to "false" to use the input file's format.
```

### ESRGAN options
```
ESRGAN_SCALE = "2"  # Value for the -s option (scale)
# This value must match the model upscaler multiplier
# otherwise esrgan will assemble the video incorrectly.

ESRGAN_TILE = "1920"  # Value for the -t option (tile size in esrgan)
# Decrease this value to a divisible integer of the video resolution you're inputting
# if you have problems with VRAM.

ESRGAN_EXTRA_ARGS = ""  # Additional ESRGAN arguments.
# Only put add something here if you know what you're doing.
```

### FFmpeg Settings:
```
FFMPEG_REASSEMBLY_ARGS = "-c:v libx264 -pix_fmt yuv420p"  # Variable for ffmpeg arguments
# Arguments for the final video encoding with ffmpeg.
# Maybe you should leave as default if you don't know what you're doing.
```

### **About linux compatibility**
This script was designed with Windows in mind, but it **should work just fine on Linux** as long as you replace the **Real-ESRGAN-ncnn-vulkan binary** with the Linux version.

### **Credits**
- **[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)** – Developed by **Xintao Wang** and contributors.
- This script **does not modify** or **distribute** the ESRGAN binaries—users must download them separately.
