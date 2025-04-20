import os
os.environ["FFMPEG_BINARY"] = "/usr/bin/ffmpeg"
import sys
import time
import logging
import configparser
import subprocess
import ffmpeg

DEBUG_MODE = False  # Set to True when you want to see full output from subprocesses

# Check for command-line argument
if len(sys.argv) < 2:
    print("Usage: python kick-record.py <streamer_name>")
    sys.exit(1)

streamer_name = sys.argv[1]

# Paths
external_dir = "/media/PATH_TO_YOUR_HARDDRIVE/Kick"
base_dir = os.path.expanduser("~/streamlink") #local path
kick_dir = os.path.join(base_dir, "kick") #local fallback path if there is a writing error to harddrive
log_dir = os.path.join(base_dir, "logs")
cookies_file = os.path.join(base_dir, "kickcomcookies.txt") #save cookies from curl impersonate here
config_path = os.path.join(base_dir, "settings.config")

# Ensure directories exist
os.makedirs(kick_dir, exist_ok=True)
os.makedirs(log_dir, exist_ok=True)

# Set up logging after log paths exist and streamer_name is known
log_file = os.path.join(log_dir, f"kick_{streamer_name}.log")
log_level = logging.DEBUG if DEBUG_MODE else logging.WARNING
logging.basicConfig(
    filename=log_file,
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Read settings
config = configparser.ConfigParser()
config.read(config_path)

retry_time = config.getint("Settings", "RetryTimeKick", fallback=120)
curl_config = config.get("Settings", "CurlConfig", fallback="config/chrome110.config")
curl_headers = config.get("Settings", "CurlHeaders", fallback="config/chrome110.header")
ytdlp_args = config.get("Settings", "YtDlpArgs", fallback="--add-header User-Agent:\"Mozilla/5.0" \
    "(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36\" ")

stream_url = f"https://www.kick.com/{streamer_name}"

def get_timestamp():
    return time.strftime("%Y%m%d-%H%M%S")

def refresh_cookies():
    logging.info("Refreshing Kick.com cookies...")
    if os.path.exists(cookies_file):
        os.remove(cookies_file)
    
    # Construct the curl command
    cmd = f"curl --config {curl_config} --header @{curl_headers} https://kick.com/ -c {cookies_file}"
    
    # Conditionally suppress output based on DEBUG_MODE
    if DEBUG_MODE:
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        result = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if result.returncode != 0:
        # Safely handle stderr being None
        stderr_output = result.stderr.decode('utf-8', errors='replace') if result.stderr else 'No error output available'
        logging.error(f"Cookie refresh failed with code {result.returncode}:\n{stderr_output}")

    if DEBUG_MODE:
        # Safely handle stdout and stderr being None
        stdout_output = result.stdout.decode('utf-8', errors='replace') if result.stdout else 'No stdout output available'
        stderr_output = result.stderr.decode('utf-8', errors='replace') if result.stderr else 'No stderr output available'
        
        logging.debug(f"curl stdout:\n{stdout_output}")
        logging.debug(f"curl stderr:\n{stderr_output}")

def record_stream():
    counter = 0

    while True:
        counter += 1
        if counter == 1:
            refresh_cookies()
            counter = -2

        timestamp = get_timestamp()
        filename = f"{streamer_name}-{timestamp}.mp4"
        external_path = os.path.join(external_dir, filename)
        fallback_path = os.path.join(kick_dir, filename)

        # Try recording to first path
        output_path = external_path
        cmd = f"yt-dlp {ytdlp_args} --cookies {cookies_file} {stream_url} -o \"{output_path}\""
        logging.info(f"Trying external drive: {cmd}")
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')
            logging.warning(f"yt-dlp failed on external drive with code {result.returncode}:\n{stderr.strip()}")

            # Check for disk write errors or retry on any error
            if "No space left on device" in stderr or "Permission denied" in stderr or "Input/output error" in stderr:
                logging.warning("Falling back to local path due to external drive write issue.")
            else:
                logging.info("Retrying on local path in case of unknown error.")
            
            output_path = fallback_path
            cmd = f"yt-dlp {ytdlp_args} --cookies {cookies_file} {stream_url} -o \"{output_path}\""
            logging.info(f"Retrying on fallback local path: {cmd}")
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0:
                logging.error(f"yt-dlp failed again on local path with code {result.returncode}:\n{result.stderr.decode('utf-8', errors='replace').strip()}")

        if DEBUG_MODE:
            logging.debug(f"yt-dlp stdout:\n{result.stdout.decode('utf-8', errors='replace').strip()}")
            logging.debug(f"yt-dlp stderr:\n{result.stderr.decode('utf-8', errors='replace').strip()}")

        logging.info(f"Stream ended or errored, retrying in {retry_time} seconds...")
        time.sleep(retry_time)

if __name__ == "__main__":
    record_stream()
