# What is this?
This repo contains scripts for running streamlink as a service in linux to actively monitor and record Twitch and Kick streams. It primarily attempts to record to an external directory you can specify, then if that fails to a fallback directory. This is useful if you have an external harddrive or mounted network drive, but the connection to it breaks for some reason. That way it ensures you don't lose a recording due to slow or faulty hardware. 

Since streamlink tends to get flagged by Kicks bot prevention system the current method in this repo uses yt-dlp and curl-impersonate to record Kick streams.

Not everything is explained in this repo so you have to lookup some things yourself.

# Install python if you don't have it and create an environment
```
sudo apt update && sudo apt upgrade
sudo apt install python3.12 python3.12-venv python3.12-dev
cd ~/streamlink
python3 -m venv venv
```
Activate environment
```
source venv/bin/activate
```
Download new environment libraries
```
pip install -r requirements.txt
```
# Download and install ffmpeg
We use the global linux system one to keep it updated
```
sudo apt update
sudo apt install ffmpeg
```

# Run manually to record directly
```
source venv/bin/activate
python record-twitch roflgator
```

# Configure settings.config and get your token and create a client ID for your "app"
You have to create a client id from https://dev.twitch.tv/console/apps
Get your token from inspecting cookies in your browser on Twitch. This is required and requires an active subscription to that channel if you want to record during ad breaks.

```
[Settings]
TwitchToken=GET_YOUR_TOKEN_FROM_TWITCH_IN_BROWSER
ClientID=CREATE_YOUR_CLIENT_ID_FROM_TWITCH_DEVELOPER_CONSOLE
RetryTime=30
RetryTimeKick = 120
ExtraArgs=--twitch-disable-ads
CurlConfig=/usr/bin/curl  # Ensure this is the correct path to curl
CurlHeaders=/home/crag/streamlink/config/chrome110.header
YtDlpArgs=--add-header "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
```

# Linux service config examples

**For recording https://twitch.tv/murdercrumpet**

Replace crag with your username. I'm using absolute paths here so adjust to yours.

```sudo nano /etc/systemd/system/record-murdercrumpet.service```

```
[Unit]
Description=Streamlink Recorder for murdercrumpet
After=network.target

[Service]
User=crag
Group=crag
WorkingDirectory=/home/crag/streamlink
ExecStart=/home/crag/streamlink/venv/bin/python /home/crag/streamlink/twitch-record.py murdercrumpet
Environment="PATH=/home/crag/streamlink/venv/bin:/usr/local/bin:/usr/bin:/bin"
Restart=always
RestartSec=10
UMask=0022

[Install]
WantedBy=multi-user.target
```

**Recording https://twitch.tv/roflgator**

Replace crag with your username and adjust paths.

```sudo nano /etc/systemd/system/record-roflgator.service```
	
```[Unit]
Description=Streamlink Recorder for roflgator
After=network.target

[Service]
User=crag
Group=crag
WorkingDirectory=/home/crag/streamlink
ExecStart=/home/crag/streamlink/venv/bin/python /home/crag/streamlink/twitch-record.py roflgator
Environment="PATH=/home/crag/streamlink/venv/bin:/usr/local/bin:/usr/bin:/bin"
Restart=always
RestartSec=10
UMask=0022

[Install]
WantedBy=multi-user.target
```

**Recording https://kick.com/roflgator**

Replace crag with your username and adjust paths.

```sudo nano /etc/systemd/system/kick-roflgator.service```
```
[Unit]
Description=Kick Recorder for roflgator 
After=network.target

[Service]
User=crag 
Group=crag
WorkingDirectory=/home/crag/streamlink
ExecStart=/home/crag/streamlink/venv/bin/python /home/crag/streamlink/kick-record.py roflgator 

Restart=always
RestartSec=10 
Environment=PATH=/home/crag/streamlink/venv/bin:/usr/bin:$PATH
Environment=PYTHONPATH=/home/crag/streamlink
UMask=0022

[Install]
WantedBy=multi-user.target
```

**Recording  https://kick.com/murdercrumpet**

Replace crag with your username and adjust paths.

```sudo nano /etc/systemd/system/kick-murdercrumpet.service```
```
[Unit]
Description=Kick Recorder for murdercrumpet
After=network.target

[Service]
User=crag
Group=crag
WorkingDirectory=/home/crag/streamlink
ExecStart=/home/crag/streamlink/venv/bin/python /home/crag/streamlink/kick-record.py murdercrumpet

Restart=always
RestartSec=10
Environment=PATH=/home/crag/streamlink/venv/bin:/usr/bin:$PATH
Environment=PYTHONPATH=/home/crag/streamlink
UMask=0022

[Install]
WantedBy=multi-user.target
```

Reload and enable services:

```
sudo systemctl daemon-reload
sudo systemctl enable record-roflgator.service
sudo systemctl start  record-roflgator.service
sudo systemctl enable record-murdercrumpet.service
sudo systemctl start  record-murdercrumpet.service
sudo systemctl enable record-kick-roflgator.service
sudo systemctl start  record-kick-roflgator.service
sudo systemctl enable record-kick-murdercrumpet.service
sudo systemctl start  record-kick-murdercrumpet.service
```

# Give permission to read and write in Linux

Replace crag with your username and adjust the paths to match yours.

```sudo chown -R crag:crag /home/crag/streamlink```

**These might also be needed**
Replace crag with your username
```
sudo chown crag:crag /home/crag/streamlink/
sudo chmod 644 /home/crag/streamlink/
sudo chown -R crag:crag /home/crag/streamlink
sudo chmod -R 755 /home/crag/streamlink
```

**Reload and restart the services in linux commands example:**
```
sudo systemctl daemon-reload
sudo systemctl restart record-roflgator
sudo systemctl start record-roflgator
```

**Disable/Enable autostart commands example:**
```
sudo systemctl disable record-roflgator
sudo systemctl enable record-roflgator
```

# Known issues

Recording is not triggered because a stream goes live, but is initiated with a timer that checks every 30 seconds for Twitch and every 120 seconds for Kick. This is also adjustable in the settings.config file. This method means that you will likely lose a part of the start of streams but this is usually not an issue as most streamers run a 5 minute intro anyway. Because of bot prevention scripts there is a risk that you may get flagged as a bot when querying too often with Kick. Due to this the script runs a curl impersonation of a browser and downloads cookies. It's not the best future proof solution but it works.
