#!/usr/bin/env python3
import os
import sys
import time
import logging
import configparser
import subprocess
import re

# ─── 1. Compute script directory ───────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── 2. Argument parsing ───────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <streamer_name>")
    sys.exit(1)
streamer_name = sys.argv[1]

# ─── 3. Paths (relative to script folder) ──────────────────────────────────────
external_dir = "/media/crag/Gargantua/Videos/Kick"
base_dir     = SCRIPT_DIR
kick_dir     = os.path.join(base_dir, "kick")
log_dir      = os.path.join(base_dir, "logs")
cookies_file = os.path.join(base_dir, "kickcomcookies.txt")
config_path  = os.path.join(base_dir, "settings.config")

# ─── 4. Ensure directories exist ───────────────────────────────────────────────
for path in (kick_dir, log_dir):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print(f"[ERROR] Cannot create directory {path}: {e}")
        sys.exit(1)

# ─── 5. Logging setup ──────────────────────────────────────────────────────────
log_file = os.path.join(log_dir, f"kick_{streamer_name}.log")
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # capture all, handlers will filter

# File handler
fh = logging.FileHandler(log_file)
# Use INFO level for file by default
fh.setLevel(logging.INFO)
fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(ch)

logger.info("=== Starting kick-record ===")

# ─── 6. Read settings.config ───────────────────────────────────────────────────
if not os.path.isfile(config_path):
    logger.error(f"Config not found: {config_path}")
    sys.exit(1)
config = configparser.ConfigParser()
config.read(config_path)

retry_time = config.getint("Settings", "RetryTimeKick", fallback=120)
curl_config = config.get("Settings", "CurlConfig", fallback=None)
curl_headers = config.get("Settings", "CurlHeaders", fallback=None)
ytdlp_args = config.get("Settings", "YtDlpArgs", fallback="")

if not curl_config or not curl_headers:
    logger.warning("Curl config or headers not set; cookie refresh may fail.")

stream_url = f"https://www.kick.com/{streamer_name}"
logger.info(f"Stream URL: {stream_url}")

# ─── 7. Detect external storage availability ───────────────────────────────────
external_parent = os.path.dirname(external_dir)
use_external = False
if os.path.isdir(external_parent) and os.access(external_parent, os.W_OK):
    try:
        os.makedirs(external_dir, exist_ok=True)
        use_external = True
        logger.info(f"External storage OK: {external_dir}")
    except PermissionError:
        logger.warning(f"External exists but not writable: {external_parent}")
else:
    logger.info(f"External not present or unwritable: {external_parent}")

# ─── 8. Helpers ─────────────────────────────────────────────────────────────────
def get_timestamp():
    return time.strftime("%Y%m%d-%H%M%S")

def refresh_cookies():
    """Fetch fresh cookies for Kick.com using curl."""
    logger.info("Refreshing Kick.com cookies...")
    if os.path.exists(cookies_file):
        try:
            os.remove(cookies_file)
        except Exception:
            logger.debug("Failed to remove old cookies file; continuing.")
    cmd = f"curl --config {curl_config} --header @{curl_headers} https://kick.com/ -c {cookies_file}"
    result = subprocess.run(
        cmd, shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        stderr = result.stderr.decode('utf-8', errors='replace')
        logger.error(f"Cookie refresh failed ({result.returncode}): {stderr.strip()}")

# ─── 9. Main recording loop ────────────────────────────────────────────────────
def record_stream():
    cookie_counter = 0
    while True:
        cookie_counter += 1
        if cookie_counter == 1:
            refresh_cookies()
            cookie_counter = -2

        ts = get_timestamp()
        filename = f"{streamer_name}-{ts}.mp4"

        # Choose path
        if use_external:
            out = os.path.join(external_dir, filename)
            logger.info(f"→ External: {out}")
        else:
            out = os.path.join(kick_dir, filename)
            logger.info(f"→ Fallback: {out}")

        # Record with yt-dlp
        cmd = f"yt-dlp {ytdlp_args} --cookies {cookies_file} {stream_url} -o \"{out}\""
        logger.debug(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')
            logger.warning(f"yt-dlp failed ({result.returncode}): {stderr.strip()}")
            # Fallback if external
            if use_external:
                logger.info("Switching to fallback due to error.")
                out = os.path.join(kick_dir, filename)
                logger.info(f"→ Fallback: {out}")
                cmd = f"yt-dlp {ytdlp_args} --cookies {cookies_file} {stream_url} -o \"{out}\""
                logger.debug(f"Running: {cmd}")
                result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    logger.error(f"Fallback failed ({result.returncode})")

        logger.info(f"Sleeping {retry_time}s...")
        time.sleep(retry_time)

# ─── 10. Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        record_stream()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
        sys.exit(0)
