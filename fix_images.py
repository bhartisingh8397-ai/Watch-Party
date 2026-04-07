import shutil
import os

# Source Artifacts
src_logo = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\logo_png_1775497668128.png"
src_hero = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\hero_bg_png_1775497923918.png"

# Destination Directory
dest_dir = r"c:\Users\bharti\Desktop\Watch Party\static\images"
os.makedirs(dest_dir, exist_ok=True)

try:
    if os.path.exists(src_logo):
        shutil.copy(src_logo, os.path.join(dest_dir, "logo.png"))
        print("Logo restored.")
    else:
        print("Source logo not found.")

    if os.path.exists(src_hero):
        shutil.copy(src_hero, os.path.join(dest_dir, "hero_bg.png"))
        print("Hero background restored.")
    else:
        print("Source hero not found.")

except Exception as e:
    print(f"Migration error: {e}")
