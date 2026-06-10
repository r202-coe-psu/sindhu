"""
MongoDB Backup Script

How to restore the backup:
To restore the backup created by this script, use the `mongorestore` command.
Since the backup is a gzipped archive, you must use the `--archive` and `--gzip` flags.
You may also want to use the `--drop` flag if you want to drop existing collections before restoring.

Example Command:
    mongorestore --uri="mongodb://localhost:27017/sindhu" --archive=backups/sindhu_backup_YYYYMMDD_HHMMSS.archive.gz --gzip --drop
"""

import os
import subprocess
import datetime
from dotenv import load_dotenv

def backup_mongodb():
    # Load environment variables from .env file
    load_dotenv()
    
    # Get MongoDB URI (default to localhost sindhu if not set)
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/sindhu")
    
    # Ensure backups directory exists
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    
    # Generate timestamp for the backup filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = os.path.join(backup_dir, f"sindhu_backup_{timestamp}.archive.gz")
    
    print("=" * 60)
    print("Starting MongoDB backup...")
    print(f"Destination: {backup_filename}")
    print("=" * 60)
    
    # Construct mongodump command
    # --archive: Outputs to a single archive file
    # --gzip: Compresses the archive
    command = [
        "mongodump",
        "--uri", mongodb_uri,
        f"--archive={backup_filename}",
        "--gzip"
    ]
    
    import threading
    import sys
    import time
    
    event = threading.Event()
    
    def progress_monitor():
        chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        i = 0
        while not event.is_set():
            size_mb = 0
            if os.path.exists(backup_filename):
                size_mb = os.path.getsize(backup_filename) / (1024 * 1024)
            sys.stdout.write(f"\r\033[K[ {chars[i % len(chars)]} ] Backing up... Archive size: {size_mb:.2f} MB")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
            
    t = threading.Thread(target=progress_monitor)
    t.start()
    
    try:
        # Execute the mongodump command
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        event.set()
        t.join()
        
        sys.stdout.write("\r\033[K") # Clear the progress line
        print("✅ Backup completed successfully!")
        print(f"📁 Backup saved to: {os.path.abspath(backup_filename)}")
        
        # Print final file size
        file_size_bytes = os.path.getsize(backup_filename)
        file_size_mb = file_size_bytes / (1024 * 1024)
        print(f"📦 File size: {file_size_mb:.2f} MB")
        
    except subprocess.CalledProcessError as e:
        event.set()
        t.join()
        sys.stdout.write("\r\033[K")
        print("\n❌ Backup failed!")
        print("Error Output:")
        print(e.stderr)
        
    except FileNotFoundError:
        event.set()
        t.join()
        sys.stdout.write("\r\033[K")
        print("\n❌ Error: 'mongodump' command not found.")
        print("Please ensure MongoDB Database Tools are installed on your system.")
        print("You can install them via: sudo apt-get install mongodb-database-tools (for Ubuntu/Debian)")

if __name__ == "__main__":
    backup_mongodb()
