#!/usr/bin/env python3
import os
import sys
import time
import logging
import configparser
import subprocess
import re
from logging.handlers import RotatingFileHandler

# ─── 1. Compute script directory ───────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── 2. Argument parsing ────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <streamer_name>")
    sys.exit(1)
streamer_name = sys.argv[1]

# ─── 3. Paths ────────────────────────────────────────────────────────────────────
log_dir      = "/tmp/kick-record-logs"
external_dir = "/mnt/NAS/Videos/Kick"
base_dir     = SCRIPT_DIR
fallback_dir = os.path.join(base_dir, "kick")
cookies_file = os.path.join(base_dir, "kickcomcookies.txt")
config_path  = os.path.join(base_dir, "settings.config")

# ─── 4. Ensure directories exist ───────────────────────────────────────────────
for path in (fallback_dir, log_dir):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        if path == log_dir:
            print(f"[WARNING] Cannot create log directory {path}: {e} — continuing without file logging.")
        else:
            print(f"[ERROR] Cannot create directory {path}: {e}")
            sys.exit(1)

# ─── 5. Logging setup ──────────────────────────────────────────────────────────
log_file = os.path.join(log_dir, f"kick_{streamer_name}.log")
logger = logging.getLogger()
logger.setLevel(logging.DEBUG) # Catch everything

# Rotating file handler: max 1MB per file, 3 backups
try:
    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
except Exception as e:
    print(f"[WARNING] Could not open rotating log file {log_file}: {e}")

# Console handler (always)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(ch)

logger.info("=== Starting kick-record ===")

# ─── 6. Read settings.config ────────────────────────────────────────────────────
config = configparser.ConfigParser()
if not os.path.isfile(config_path):
    logger.error(f"Config not found: {config_path}")
    sys.exit(1)
config.read(config_path)

retry_time    = config.getint("Settings", "RetryTimeKick", fallback=120)
curl_bin      = config.get("Settings", "CurlConfig", fallback="/usr/bin/curl")
curl_headers  = config.get("Settings", "CurlHeaders", fallback=None)
ytdlp_args    = config.get("Settings", "YtDlpArgs", fallback="")
streamlink_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

if not curl_bin or not curl_headers:
    logger.warning("Curl config or headers not set; cookie refresh may fail.")

stream_url = f"https://www.kick.com/{streamer_name}"
logger.info(f"Stream URL: {stream_url}")

# ─── 7. Helpers ─────────────────────────────────────────────────────────────────
def get_timestamp():
    return time.strftime("%Y%m%d-%H%M%S")

def refresh_cookies_curl():
    logger.info("Refreshing cookies via Curl...")
    if not curl_headers:
        logger.error("No CurlHeaders defined in settings.config.")
        return
    cmd = f"{curl_bin} --header @{curl_headers} https://kick.com/ -c {cookies_file}"
    logger.debug(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Curl Refresh failed (Code {result.returncode}): {result.stderr.strip()}")

def refresh_cookies_ytdlp():
    logger.info("Attempting heavy yt-dlp cookie refresh...")
    cmd = f"yt-dlp --cookies {cookies_file} --impersonate chrome --cookies-from-browser chrome https://kick.com --preview"
    logger.debug(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        logger.debug(f"yt-dlp refresh output: {result.stderr.strip()}")

def run_streamlink(path):
    """Attempt recording with Streamlink"""
    cmd = [
        "streamlink",
        stream_url,
        "best",
        "-o", path,
        "--http-header", f"User-Agent={streamlink_ua}",
    ]
    if os.path.exists(cookies_file):
        cmd.extend(["--http-cookies", cookies_file])
    
    logger.debug(f"Running Streamlink: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)

def run_ytdlp(path):
    cmd = f"yt-dlp {ytdlp_args} --cookies {cookies_file} {stream_url} -o \"{path}\""
    logger.debug(f"Running yt-dlp Fallback: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

# ─── 8. Main loop ───────────────────────────────────────────────────────────────
def record_stream():
    while True:
        ts = get_timestamp()
        filename = f"{streamer_name}-{ts}.mp4"

        # --- NAS FALLBACK CHECK ---
        if os.path.exists(external_dir) and os.access(external_dir, os.W_OK):
            target_path = os.path.join(external_dir, filename)
            logger.info(f"→ Primary (NAS): {target_path}")
        else:
            target_path = os.path.join(fallback_dir, filename)
            logger.warning(f"→ NAS OFFLINE! Fallback to: {target_path}")

        # 1. PRIMARY ATTEMPT
        sl_result = run_streamlink(target_path)
        
        if sl_result.returncode == 0:
            logger.info("Recording finished successfully.")
        else:
            sl_err = (sl_result.stdout + sl_result.stderr).lower()
            logger.debug(f"Streamlink Exit Code: {sl_result.returncode}")
            
            # 2. EVALUATE ERROR
            if "403" in sl_err or "forbidden" in sl_err:
                logger.warning(f"BLOCKED (403). Full error: {sl_result.stderr.strip()[:200]}")
                refresh_cookies_curl() 
                
                # Try yt-dlp fallback
                yt_result = run_ytdlp(target_path)
                if yt_result.returncode == 0:
                    logger.info("yt-dlp fallback recording successful.")
                else:
                    yt_err = yt_result.stderr.lower()
                    logger.debug(f"yt-dlp Exit Code: {yt_result.returncode}")
                    
                    if "403" in yt_err:
                        logger.error("yt-dlp also blocked. Triggering heavy refresh.")
                        refresh_cookies_ytdlp()
                    elif "offline" in yt_err or "not live" in yt_err:
                        logger.info("Streamer is offline.")
                    else:
                        logger.error(f"Fallback failure: {yt_result.stderr.strip()[:200]}")
            else:
                # If it's not a 403, it's usually just 'No streams found' (Offline)
                logger.info("Streamer appears to be offline.")
                # Log the first bit of error just in case it's something else
                if sl_result.stderr:
                    logger.debug(f"Streamlink info: {sl_result.stderr.strip()[:100]}")

        logger.info(f"Sleeping {retry_time}s...")
        time.sleep(retry_time)

# ─── 9. Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        record_stream()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
        sys.exit(0)


