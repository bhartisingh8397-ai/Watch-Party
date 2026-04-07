import shutil
import os

log_file = "copy_assets.log"
with open(log_file, "w") as log:
    log.write("Asset Movement Log\n")
    try:
        src_logo = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\watch_party_logo_v1_1775481916342.png"
        src_hero = r"C:\Users\bharti\.gemini\antigravity\brain\1920caaf-930d-47ea-b99d-91378fb8d645\prime_video_hero_posters_v2_1775479016384.png"
        
        dest_dir = r"static\images"
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            log.write(f"Created directory: {dest_dir}\n")
        
        # Check source existence
        log.write(f"Logo Source Exists: {os.path.exists(src_logo)}\n")
        log.write(f"Hero Source Exists: {os.path.exists(src_hero)}\n")
        
        # Copy
        shutil.copy(src_logo, os.path.join(dest_dir, "logo.png"))
        log.write("Copied logo.png\n")
        shutil.copy(src_hero, os.path.join(dest_dir, "prime_video_hero.png"))
        log.write("Copied prime_video_hero.png\n")
        
        log.write(f"Destination contents: {os.listdir(dest_dir)}\n")
    except Exception as e:
        log.write(f"Error occurred: {str(e)}\n")

print("Asset move script completed.")
