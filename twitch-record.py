#!/usr/bin/env python3
import os
import sys
import time
import logging
import configparser
import subprocess
import re
import json
from logging.handlers import RotatingFileHandler

# ─── 1. Compute script directory ───────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── 2. Argument parsing ────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <streamer_name>")
    sys.exit(1)
streamer_name = sys.argv[1]

# ─── 3. Paths ────────────────────────────────────────────────────────────────────
# Logs go to /tmp with rotation to limit size
log_dir      = "/tmp/twitch-record-logs"
external_dir = "/mnt/NAS/Videos/Twitch"
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
extra_args   = config.get("Settings", "ExtraArgs",   fallback="") or ""

# Parse optional quality-check settings
target_qualities_raw = config.get("Settings", "RestartStreamIfBetterQualityIsAvailable", fallback="").strip()
target_qualities     = [q.strip().lower() for q in target_qualities_raw.split(",") if q.strip()] if target_qualities_raw else []
quality_check_delay  = config.getint("Settings", "RestartStreamIfBetterQualityCheckDelayTime", fallback=60)

if twitch_token and client_id:
    extra_args += (
        f' --twitch-api-header "Authorization=OAuth {twitch_token}"'
        f' --twitch-api-header "Client-ID={client_id}"'
    )
elif twitch_token:
    extra_args += f' --twitch-api-header "Authorization=OAuth {twitch_token}"'

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

def check_target_quality_available():
    """Queries Streamlink JSON metadata to verify if any target resolution is live."""
    if not target_qualities:
        return True, "online"

    cmd = f'streamlink --json {stream_url} {extra_args}'
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0 or not res.stdout.strip():
            return False, "offline"

        data = json.loads(res.stdout)
        streams = data.get("streams", {})
        if not streams:
            return False, "offline"

        # Match any quality key against the target qualities list
        has_target = any(
            any(q in key.lower() for q in target_qualities)
            for key in streams.keys()
        )
        return has_target, "online"
    except Exception as e:
        logger.warning(f"Failed to parse Streamlink JSON metadata: {e}")
        return False, "error"

def run_streamlink(path: str):
    cmd = f'streamlink {stream_url} best -o "{path}" {extra_args}'
    logger.info("Running: " + hide_token(cmd))
    return subprocess.run(cmd, shell=True), cmd

# ─── 9. Main loop ───────────────────────────────────────────────────────────────
def record_stream():
    waited_for_quality = False

    while True:
        # Check target quality if configured and we haven't already waited once
        if target_qualities and not waited_for_quality:
            has_quality, status = check_target_quality_available()

            if status == "offline":
                logger.info(f"Stream is offline. Sleeping {retry_time}s")
                waited_for_quality = False
                time.sleep(retry_time)
                continue
            elif status == "error":
                logger.warning(f"Error checking stream metadata. Sleeping {retry_time}s")
                time.sleep(retry_time)
                continue

            if not has_quality:
                logger.warning(
                    f"Stream is live, but target quality ({', '.join(target_qualities)}) is unavailable. "
                    f"Waiting {quality_check_delay}s to re-check before recording anyway..."
                )
                time.sleep(quality_check_delay)
                waited_for_quality = True

                # Re-check once after the delay
                has_quality_now, status_after_delay = check_target_quality_available()
                if status_after_delay == "offline":
                    logger.info(f"Stream went offline during delay. Sleeping {retry_time}s")
                    waited_for_quality = False
                    time.sleep(retry_time)
                    continue

                if has_quality_now:
                    logger.info("Target quality became available during delay!")
                else:
                    logger.warning("Target quality still unavailable after delay. Proceeding to record best available quality.")

        # Determine target output path
        ts = get_timestamp()
        filename = f"{streamer_name}-{ts}.mp4"

        # Determine the best available path BEFORE running streamlink
        # We check os.path.ismount or os.access to see if the NAS is actually there
        if os.path.exists(external_dir) and os.access(external_dir, os.W_OK):
            target_path = os.path.join(external_dir, filename)
            logger.info(f"→ Primary (NAS): {target_path}")
        else:
            target_path = os.path.join(fallback_dir, filename)
            logger.warning(f"→ NAS unavailable, using Fallback: {target_path}")

        # Run streamlink recording
        result, _ = run_streamlink(target_path)

        # Reset flag for the next stream session once recording stops
        waited_for_quality = False

        # Handle recording completion
        if result.returncode == 0:
            logger.info("Recording finished successfully.")
        else:
            logger.info(f"Streamlink exited with code {result.returncode}. (likely offline)")

        logger.info(f"Sleeping {retry_time}s")
        time.sleep(retry_time)

# ─── 10. Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        record_stream()
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        sys.exit(0)

