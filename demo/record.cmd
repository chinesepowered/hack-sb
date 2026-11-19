@echo off
rem Records the live onsen run (desktop capture) and muxes it with the voiceover.
cd /d %~dp0
if not exist out mkdir out
curl -s -X POST http://127.0.0.1:8000/api/reset >nul
start "" chrome --new-window --start-maximized --app=http://127.0.0.1:8000/
timeout /t 5 >nul
start "" /b ffmpeg -y -loglevel error -f gdigrab -framerate 30 -t 90 -i desktop -vf "scale=1920:-2" -c:v libx264 -preset ultrafast -pix_fmt yuv420p out\screen.mp4
timeout /t 18 >nul
curl -s -X POST http://127.0.0.1:8000/api/say -H "Content-Type: application/json" -d "{\"text\":\"I have a bio exam Friday, I'm moving apartments Saturday, and it's my mom's birthday Sunday. I'm so overwhelmed.\"}" >nul
timeout /t 42 >nul
curl -s -X POST http://127.0.0.1:8000/api/say -H "Content-Type: application/json" -d "{\"text\":\"yes, that feels okay!\"}" >nul
timeout /t 34 >nul
ffmpeg -y -loglevel error -i out\screen.mp4 -i out\voiceover.mp3 -map 0:v -map 1:a -c:v copy -c:a aac -shortest out\capy-onsen-demo.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 out\capy-onsen-demo.mp4
