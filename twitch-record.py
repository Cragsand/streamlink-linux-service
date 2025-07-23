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
# Logs now go to /tmp with rotation to limit size
log_dir      = "/tmp/twitch-record-logs"
external_dir = "/mnt/DAS/Videos/Twitch"
base_dir     = SCRIPT_DIR
fallback_dir = os.path.join(base_dir, "twitch")
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
log_file = os.path.join(log_dir, f"twitch_{streamer_name}.log")
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Rotating file handler: max 1MB per file, 3 backups
try:
    fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
except Exception as e:
    print(f"[WARNING] Could not open rotating log file {log_file}: {e}")

# Console handler
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(ch)

logger.info("=== Starting twitch-record ===")

# ─── 6. Read settings.config ────────────────────────────────────────────────────
if not os.path.isfile(config_path):
    logger.error(f"Config not found: {config_path}")
    sys.exit(1)
config = configparser.ConfigParser()
config.read(config_path)

twitch_token = config.get("Settings", "TwitchToken", fallback=None)
client_id    = config.get("Settings", "ClientID",    fallback=None)
retry_time   = config.getint("Settings", "RetryTime", fallback=30)
extra_args   = config.get("Settings", "ExtraArgs",   fallback="--twitch-disable-ads")

if twitch_token and client_id:
    extra_args += (
        f' --twitch-api-header "Authorization=OAuth {twitch_token}"'
        f' --twitch-api-header "Client-ID={client_id}"'
    )

stream_url = f"https://www.twitch.tv/{streamer_name}"
logger.info(f"Stream URL: {stream_url}")

# ─── 7. Detect external storage availability ───────────────────────────────────
external_parent = os.path.dirname(external_dir)
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

def hide_token(cmd: str) -> str:
    return re.sub(
        r'--twitch-api-header\s+"Authorization=OAuth\s+\S+"',
        '--twitch-api-header "Authorization=OAuth HIDDEN_TOKEN"',
        cmd
    )

def run_streamlink(path: str):
    cmd = f'streamlink {stream_url} best -o "{path}" {extra_args}'
    logger.info("Running: " + hide_token(cmd))
    return subprocess.run(cmd, shell=True), cmd

# ─── 9. Main loop ───────────────────────────────────────────────────────────────
def record_stream():
    while True:
        ts       = get_timestamp()
        filename = f"{streamer_name}-{ts}.mp4"

        # Try external then fallback
        if use_external:
            primary = os.path.join(external_dir, filename)
            logger.info(f"→ External: {primary}")
            result, _ = run_streamlink(primary)
            if result.returncode != 0:
                logger.warning("✗ External failed, switching to fallback")
        else:
            result = None

        if not use_external or (result and result.returncode != 0):
            fb = os.path.join(fallback_dir, filename)
            logger.info(f"→ Fallback: {fb}")
            result, _ = run_streamlink(fb)
            if result.returncode != 0:
                logger.error("✗ Fallback failed too")

        logger.info(f"Sleeping {retry_time}s")
        time.sleep(retry_time)

# ─── 10. Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        record_stream()
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        sys.exit(0)
