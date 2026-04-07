import shutil
import os

# Source images from the brain directory
src_dir = r"C:\Users\bharti\.gemini\antigravity\brain\16753fa1-48c4-4c22-a2f7-56241d9f0dfd"
dest_dir = r"c:\Users\bharti\Desktop\Watch Party\static\images"

images_to_copy = {
    "cyberpunk_poster_1775545819453.png": "poster1.png",
    "fantasy_poster_1775545843285.png": "poster2.png",
    "noir_poster_1775545879730.png": "poster3.png",
    "animation_poster_1775545958267.png": "poster4.png"
}

if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)

for src_name, dest_name in images_to_copy.items():
    src_path = os.path.join(src_dir, src_name)
    dest_path = os.path.join(dest_dir, dest_name)
    
    print(f"Copying {src_name} to {dest_name}...")
    if os.path.exists(src_path):
        shutil.copy(src_path, dest_path)
        print(f"Success: {dest_name} created.")
    else:
        print(f"Error: {src_name} not found at {src_path}")

print("Current files in static/images:", os.listdir(dest_dir))
