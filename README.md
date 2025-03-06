# Real-ESRGAN Efficient Video Upscaler
This project is a batch-based video upscaler designed to make efficient use of Real-ESRGAN-ncnn-vulkan by running concurrent batches, ensuring optimal GPU utilization.

# How It Works
The script splits a video into batches of frames, processes them concurrently, then put the video back together while maintaining audio and metadata.

# Key Features
* Efficient GPU usage;
* Concurrent batches;
* Queue all videos in the input folder;
* Automatically reassembly of audio and video;
* Low storage usage

# Installation
