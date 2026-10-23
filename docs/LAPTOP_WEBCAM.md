# Use your laptop webcam as a camera

You do not need a server or a real CCTV camera. Your laptop runs the app and sends its own webcam into it.

## One-time setup

1. **Get the code.** Open https://github.com/yuyank-code/crowd-flow-intelligence, click **Code**, **Download ZIP**, and unzip it. Open a terminal in that folder
   (Windows: open the folder, click the address bar, type `powershell`, press Enter. Mac: right-click the folder, "New Terminal at Folder").
2. **Install Docker Desktop** from https://www.docker.com/products/docker-desktop and start it (wait until it says it is running).
3. **Install ffmpeg.**
   - Windows (PowerShell): `winget install Gyan.FFmpeg`, then close and reopen PowerShell.
   - Mac: `brew install ffmpeg` (install Homebrew from https://brew.sh first if you don't have it).
   - Linux (Ubuntu/Debian): `sudo apt install ffmpeg`
4. **Create your settings file** (makes the passwords for you and prints your operator key; copy it):
   - Windows: `powershell -ExecutionPolicy Bypass -File scripts\make-env.ps1`
   - Mac/Linux: `./scripts/make-env.sh`

## Every time you want to use it

1. **Start the app** (first run takes a few minutes):
   `docker compose --profile laptop up --build`
   Leave this window open. Open http://localhost:8080 in your browser when it settles.
2. **Start the webcam feed** in a second terminal in the same folder:
   - Windows: `powershell -ExecutionPolicy Bypass -File scripts\webcam\start-webcam.ps1`
   - Mac/Linux: `./scripts/webcam/start-webcam.sh`
   Leave it running. Mac: click **Allow** if it asks for camera access. The camera light should turn on.
3. **Add the camera in the dashboard.** Open the **CAMERAS** tab, type your operator key, then add a camera:
   - Name: anything (e.g. Laptop webcam)
   - Type: RTSP
   - Endpoint: `rtsp://mediamtx-laptop:8554/webcam`
   - Playback path: `webcam`
4. Press **Test connection** (should say Reachable), then **Start stream**. Your webcam appears in the preview.

Stop: Ctrl+C in each terminal, then `docker compose --profile laptop down`.

## If something goes wrong

| Problem | Fix |
|---|---|
| `ffmpeg not found` | Reopen the terminal after installing it. |
| Windows: no camera found | Settings > Privacy & security > Camera > allow desktop apps. Or list names with `ffmpeg -list_devices true -f dshow -i dummy` and use `-Device "Name"`. |
| Mac: input/device error | List cameras: `ffmpeg -f avfoundation -list_devices true -i ""`, then `./scripts/webcam/start-webcam.sh 1` (use the number shown). |
| Test connection says Offline | The webcam script is not running, or it printed an error. Check its window. |
| Start stream says gateway not serving | Wait 5 seconds after the webcam script starts, then try again. |
| Docker says `OPERATOR_API_KEY` is not set | Run step 4 of the setup first, from the repo folder. |

## No webcam handy?
`TEST_PATTERN=1 ./scripts/webcam/start-webcam.sh` (Mac/Linux) or `scripts\webcam\start-webcam.ps1 -TestPattern` (Windows) sends a test picture instead.

## Status
The Docker flow (stack, publishing with credentials, camera test, token-protected playback, decode) is checked automatically on GitHub with a test picture. The Windows PowerShell scripts and the real webcam capture commands could not be run by me; they have not been tried on real Windows or Mac hardware yet.
