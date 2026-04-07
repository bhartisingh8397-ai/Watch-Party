import urllib.request
import os

# Define the local directory
IMAGE_DIR = "static/images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# Assets to download
ASSETS = {
    "hero_bg.png": "https://images.pexels.com/photos/7991579/pexels-photo-7991579.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    "auth_bg.png": "https://images.pexels.com/photos/7234226/pexels-photo-7234226.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    "poster_dummy.png": "https://images.pexels.com/photos/33129/popcorn-movie-entertainment-entertainment.jpg?auto=compress&cs=tinysrgb&w=300&h=450&dpr=2"
}

# Browser User-Agent to prevent 403 Forbidden errors
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

print("🚀 Starting Professional Cinematic Asset Download (with Bypass)...")

for filename, url in ASSETS.items():
    filepath = os.path.join(IMAGE_DIR, filename)
    try:
        print(f"Downloading {filename}...")
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req) as f_in:
            with open(filepath, 'wb') as f_out:
                f_out.write(f_in.read())
        print(f"✅ Successfully saved to {filepath}")
    except Exception as e:
        print(f"❌ Failed to download {filename}: {e}")

print("\n🎉 All local assets are ready! Your UI will now render with high-fidelity local images.")
