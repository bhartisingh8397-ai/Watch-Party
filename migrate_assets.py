import shutil
import os

# Source Artifacts
src_hero = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\hero_bg_png_1775502736122.png"
src_auth = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\auth_bg_png_1775502778306.png"
src_poster = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\poster_dummy_png_1775502805003.png"

# Destination
dest_dir = r"c:\Users\bharti\Desktop\Watch Party\static\images"
os.makedirs(dest_dir, exist_ok=True)

try:
    if os.path.exists(src_hero):
        shutil.copy(src_hero, os.path.join(dest_dir, "hero_bg.png"))
        print("Hero background copied.")
    if os.path.exists(src_auth):
        shutil.copy(src_auth, os.path.join(dest_dir, "auth_bg.png"))
        print("Auth background copied.")
    if os.path.exists(src_poster):
        shutil.copy(src_poster, os.path.join(dest_dir, "poster_dummy.png"))
        print("Poster placeholder copied.")
    print("Migration COMPLETE.")
except Exception as e:
    print(f"Error: {e}")
