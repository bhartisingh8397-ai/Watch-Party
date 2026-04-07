import shutil
import os

log_file = "asset_fix.log"
with open(log_file, "w") as f:
    f.write("Starting asset fix...\n")
    try:
        src_logo = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\watch_party_logo_v1_1775481916342.png"
        src_hero = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\prime_video_hero_posters_v2_1775479016384.png"
        
        dest_dir = r"static"
        
        f.write(f"Source logo exists: {os.path.exists(src_logo)}\n")
        f.write(f"Source hero exists: {os.path.exists(src_hero)}\n")
        
        if os.path.exists(src_logo):
            shutil.copy(src_logo, os.path.join(dest_dir, "logo.png"))
            f.write("Copied logo.png to static/\n")
            
        if os.path.exists(src_hero):
            shutil.copy(src_hero, os.path.join(dest_dir, "prime_video_hero.png"))
            f.write("Copied prime_video_hero.png to static/\n")
            
        f.write(f"Final contents of {dest_dir}: {os.listdir(dest_dir)}\n")
    except Exception as e:
        f.write(f"Error occurred: {str(e)}\n")

print("Asset fix script completed. Check asset_fix.log for details.")
