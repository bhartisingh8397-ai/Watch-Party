import sqlite3
import os

db_path = r"c:\Users\bharti\Desktop\Watch Party\watchparty.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path, timeout=20)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE video ADD COLUMN poster_filename VARCHAR(500);")
        conn.commit()
        print("Column 'poster_filename' added successfully!")
    except sqlite3.OperationalError as e:
        print(f"Error (maybe column exists?): {e}")
    finally:
        conn.close()
else:
    print(f"Error: Database file not found at {db_path}")
