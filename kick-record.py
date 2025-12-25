#!/usr/bin/env python3
import os
import sys
import time
import logging
import configparser
import subprocess
import shlex
from logging.handlers import RotatingFileHandler

PYTHON = sys.executable

# ─── 1. Compute script directory ───────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── 2. Argument parsing ───────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <streamer_name>")
    sys.exit(1)
streamer_name = sys.argv[1]

# ─── 3. Paths ────────────────────────────────────────────────────────────────────
log_dir      = "/tmp/kick-record-logs"
external_dir = "/mnt/DAS/Videos/Kick"
base_dir     = SCRIPT_DIR
kick_dir     = os.path.join(base_dir, "kick")
cookies_file = os.path.join(base_dir, "kickcomcookies.txt")
config_path  = os.path.join(base_dir, "settings.config")

# ─── 4. Ensure directories exist ───────────────────────────────────────────────
for path in (kick_dir, log_dir):
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
logger.setLevel(logging.DEBUG)

try:
    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
except Exception as e:
    print(f"[WARNING] Could not open rotating log file {log_file}: {e}")

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
use_external = False
try:
    os.makedirs(external_dir, exist_ok=True)
    use_external = True
    logger.info(f"External storage OK: {external_dir}")
except Exception as e:
    logger.warning(f"Unable to use external storage, falling back: {e}")

# ─── 8. Helpers ─────────────────────────────────────────────────────────────────
def get_timestamp():
    return time.strftime("%Y%m%d-%H%M%S")

def refresh_cookies():
    if not curl_config or not curl_headers:
        logger.warning("Skipping cookie refresh because CurlConfig or CurlHeaders is not set.")
        return

    logger.info("Refreshing Kick.com cookies...")
    if os.path.exists(cookies_file):
        try:
            os.remove(cookies_file)
        except Exception:
            logger.debug("Failed to remove old cookies file; continuing.")

    cmd = [
        "curl",
        "--config", curl_config,
        "--header", f"@{curl_headers}",
        "https://kick.com/",
        "-c", cookies_file,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"Cookie refresh failed ({result.returncode}): {result.stderr.strip()}")

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
        out = os.path.join(external_dir if use_external else kick_dir, filename)
        logger.info(f"→ {'External' if use_external else 'Fallback'}: {out}")

        # Use shlex.split to handle quoted ytdlp args correctly
        extra_args = shlex.split(ytdlp_args) if ytdlp_args else []

        cmd = [
            PYTHON,
            "-m", "yt_dlp",
            *extra_args,
            "--cookies", cookies_file,
            stream_url,
            "-o", out,
        ]

        # log a safely quoted representation
        logger.debug("Running: " + " ".join(shlex.quote(a) for a in cmd))

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            stderr = result.stderr or ""
            logger.warning(f"yt-dlp failed ({result.returncode}): {stderr.strip()}")
            if use_external:
                logger.info("Switching to fallback due to error.")
                fallback_out = os.path.join(kick_dir, filename)

                fallback_cmd = cmd.copy()
                # last element is the output filename in our layout; replace it
                fallback_cmd[-1] = fallback_out

                logger.debug("Fallback running: " + " ".join(shlex.quote(a) for a in fallback_cmd))
                fb_res = subprocess.run(
                    fallback_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if fb_res.returncode != 0:
                    logger.error(f"Fallback failed ({fb_res.returncode}): {fb_res.stderr.strip()}")

        logger.info(f"Sleeping {retry_time}s...")
        time.sleep(retry_time)

# ─── 10. Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        record_stream()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
        sys.exit(0)
