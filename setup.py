import os
import zipfile
import urllib.request
from io import BytesIO

def download_and_extract(url, bin_folder, models_folder):
    print("Downloading file from:", url)
    response = urllib.request.urlopen(url)
    zip_content = response.read()
    print("Download complete.")

    # Open the zip file from the downloaded content in memory.
    with zipfile.ZipFile(BytesIO(zip_content)) as z:
        # Define the list of files to extract to the bin folder.
        bin_files = {'realesrgan-ncnn-vulkan.exe', 'vcomp140.dll', 'vcomp140d.dll'}
        for file in z.namelist():
            basename = os.path.basename(file)
            if basename in bin_files:
                target_path = os.path.join(bin_folder, basename)
                print(f"Extracting {file} to {target_path}")
                with z.open(file) as source, open(target_path, 'wb') as target:
                    target.write(source.read())

        # Extract everything under the "models" folder in the zip to your local models folder.
        for file in z.namelist():
            if file.startswith("models/") and not file.endswith('/'):
                # Remove the leading "models/" from the path.
                rel_path = os.path.relpath(file, "models")
                target_path = os.path.join(models_folder, rel_path)
                print(f"Extracting {file} to {target_path}")
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with z.open(file) as source, open(target_path, 'wb') as target:
                    target.write(source.read())
    print("Setup completed successfully.")

if __name__ == '__main__':
    # Determine the directory where this script is located.
    script_dir = os.path.dirname(os.path.realpath(__file__))
    bin_folder = os.path.join(script_dir, "bin")
    models_folder = os.path.join(script_dir, "models")

    # Ensure the bin and models folders exist.
    os.makedirs(bin_folder, exist_ok=True)
    os.makedirs(models_folder, exist_ok=True)

    # URL for the Real-ESRGAN zip file.
    url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
    download_and_extract(url, bin_folder, models_folder)
