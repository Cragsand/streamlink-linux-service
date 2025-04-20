# What is this?
This repo contains scripts for running streamlink as a service in linux to actively monitor and record Twitch and Kick streams.
Not everything is explained so you have to lookup some things.

# Create python environment
```
cd ~/streamlink
python3 -m venv venv
```
# Activate environment
```
source venv/bin/activate
```
# Download new environment libraries
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

# Linux service config example for recording murdercrumpet:
Replace crag with your username. I'm using absolute paths here so adjust to yours.

sudo nano /etc/systemd/system/record-murdercrumpet.service

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
StandardOutput=append:/home/crag/streamlink/logs/murdercrumpet_service.log
StandardError=append:/home/crag/streamlink/logs/murdercrumpet_service.log
UMask=0022

[Install]
WantedBy=multi-user.target
```
# Linux service example for recording roflgator:
Replace crag with your username and adjust paths.

sudo nano /etc/systemd/system/record-roflgator.service
	
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
StandardOutput=append:/home/crag/streamlink/logs/roflgator_service.log
StandardError=append:/home/crag/streamlink/logs/roflgator_service.log
UMask=0022

[Install]
WantedBy=multi-user.target
```

# Service example for recording for recording kick.com/roflgator 
Replace crag with your username and adjust paths.

sudo nano /etc/systemd/system/kick-roflgator.service
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
StandardOutput=append:/home/crag/streamlink/logs/kick_roflgator.log
StandardError=append:/home/crag/streamlink/logs/kick_roflgator.log
Environment=PATH=/home/crag/streamlink/venv/bin:/usr/bin:$PATH
Environment=PYTHONPATH=/home/crag/streamlink
UMask=0022

[Install]
WantedBy=multi-user.target
```

# Service for kick murdercrumpet 
Replace crag with your username and adjust paths.

sudo nano /etc/systemd/system/kick-murdercrumpet.service
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
StandardOutput=append:/home/crag/streamlink/logs/kick_murdercrumpet.log
StandardError=append:/home/crag/streamlink/logs/kick_murdercrumpet.log
Environment=PATH=/home/crag/streamlink/venv/bin:/usr/bin:$PATH
Environment=PYTHONPATH=/home/crag/streamlink
UMask=0022

[Install]
WantedBy=multi-user.target
```
# Give permission to read and write
Replace crag with your username and adjust paths.

```sudo chown -R crag:crag /home/crag/streamlink/logs```

# These might also be needed
Replace crag with your username
```
sudo chown crag:crag /home/crag/streamlink/logs/kick_roflgator.log
sudo chmod 644 /home/crag/streamlink/logs/kick_roflgator.log
sudo chown -R crag:crag /home/crag/streamlink/logs
sudo chmod -R 755 /home/crag/streamlink/logs
```
# Reload and restart the services in linux commands example:
```
sudo systemctl daemon-reload
sudo systemctl restart record-roflgator
sudo systemctl start record-roflgator
```

# Disable/Enable autostart commands example:
```
sudo systemctl disable record-roflgator
sudo systemctl enable record-roflgator
```
