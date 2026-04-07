import shutil
import os

src_logo = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\watch_party_logo_v1_1775481916342.png"
src_hero = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\prime_video_hero_posters_v2_1775479016384.png"

dest_dir = r"c:\Users\bharti\Desktop\Watch Party\static\images"
if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)

print(f"Copying logo from: {src_logo}")
if os.path.exists(src_logo):
    shutil.copy(src_logo, os.path.join(dest_dir, "logo.png"))
else:
    print(f"Error: Source logo not found: {src_logo}")

print(f"Copying hero from: {src_hero}")
if os.path.exists(src_hero):
    shutil.copy(src_hero, os.path.join(dest_dir, "prime_video_hero.png"))
else:
    print(f"Error: Source hero not found: {src_hero}")

print("Current contents of static/images:", os.listdir(dest_dir))
