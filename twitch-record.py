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

# ─── 2. Argument parsing ────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <streamer_name>")
    sys.exit(1)
streamer_name = sys.argv[1]

# ─── 3. Paths (all relative to script folder) ───────────────────────────────────
external_dir = "/media/crag/Gargantua/Videos/Twitch"
base_dir     = SCRIPT_DIR
log_dir      = os.path.join(base_dir, "logs")
fallback_dir = os.path.join(base_dir, "twitch")
config_path  = os.path.join(base_dir, "settings.config")

# ─── 4. Ensure log + fallback directories exist ────────────────────────────────
try:
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(fallback_dir, exist_ok=True)
except Exception as e:
    print(f"[ERROR] Could not create dirs under {base_dir}: {e}")
    sys.exit(1)

# ─── 5. Logging setup ──────────────────────────────────────────────────────────
log_file = os.path.join(log_dir, f"{streamer_name}.log")
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler(log_file)
fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(fh)

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

        # 9a. Try external if available
        if use_external:
            primary = os.path.join(external_dir, filename)
            logger.info(f"→ External: {primary}")
            result, _ = run_streamlink(primary)
            if result.returncode == 0:
                logger.info("✓ Written external")
            else:
                logger.warning("✗ External failed, fallback next")
        else:
            result = None

        # 9b. Fallback if needed
        if not use_external or (result and result.returncode != 0):
            fb = os.path.join(fallback_dir, filename)
            logger.info(f"→ Fallback: {fb}")
            result, _ = run_streamlink(fb)
            if result.returncode == 0:
                logger.info("✓ Written fallback")
            else:
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
