import os
import sys
import time
import logging
import configparser
import subprocess
import re

# Check for command-line argument
if len(sys.argv) < 2:
    print("Usage: python record.py <streamer_name>")
    sys.exit(1)

streamer_name = sys.argv[1]

# Paths
external_dir = "/media/PATH_TO_YOUR_HARDDRIVE/Twitch"
base_dir = os.path.expanduser("~/streamlink") #local path
log_dir = os.path.join(base_dir, "logs")
fallback_dir = os.path.join(base_dir, "twitch") #local fallback path if there is a writing error to harddrive
config_path = os.path.join(base_dir, "settings.config")

# Ensure directories exist
os.makedirs(log_dir, exist_ok=True)
os.makedirs(fallback_dir, exist_ok=True)
os.makedirs(external_dir, exist_ok=True)

# Logging setup
log_file = os.path.join(log_dir, f"{streamer_name}.log")
logging.basicConfig(
    filename=log_file, level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Read settings
config = configparser.ConfigParser()
config.read(config_path)

twitch_token = config.get("Settings", "TwitchToken", fallback=None)
client_id = config.get("Settings", "ClientID", fallback=None)
retry_time = config.getint("Settings", "RetryTime", fallback=30)
extra_args = config.get("Settings", "ExtraArgs", fallback="--twitch-disable-ads")

if twitch_token:
    extra_args += f' --twitch-api-header "Authorization=OAuth {twitch_token}" --twitch-api-header "Client-ID={client_id}"'

stream_url = f"https://www.twitch.tv/{streamer_name}"

def get_timestamp():
    return time.strftime("%Y%m%d-%H%M%S")

def hide_token(cmd):
    return re.sub(r'--twitch-api-header\s+"Authorization=OAuth\s+\S+"', '--twitch-api-header "Authorization=OAuth HIDDEN_TOKEN"', cmd)

def run_streamlink(output_path):
    cmd = f'streamlink {stream_url} best -o "{output_path}" {extra_args}'
    safe_cmd = hide_token(cmd)
    logging.info(f"Running: {safe_cmd}")
    return subprocess.run(cmd, shell=True), cmd

def record_stream():
    while True:
        timestamp = get_timestamp()
        filename = f"{streamer_name}-{timestamp}.mp4"
        external_path = os.path.join(external_dir, filename)
        fallback_path = os.path.join(fallback_dir, filename)

        # Try writing to external drive
        result, cmd = run_streamlink(external_path)

        if result.returncode == 0:
            logging.info(f"Stream ended successfully. Retrying in {retry_time} seconds...")
        else:
            logging.warning(f"Streamlink failed on external drive with code {result.returncode}. Attempting fallback...")

            # Try fallback
            result, fallback_cmd = run_streamlink(fallback_path)

            if result.returncode == 0:
                logging.info("Fallback to local path successful.")
            else:
                logging.error(f"Streamlink also failed on fallback path with code {result.returncode}.")

        time.sleep(retry_time)

if __name__ == "__main__":
    try:
        record_stream()
    except KeyboardInterrupt:
        print("Recording stopped.")
        sys.exit(0)
