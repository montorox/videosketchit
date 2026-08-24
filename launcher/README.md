# VideoSketchIt by AIDB

VideoSketchIt turns scripts and narration into animated sketch and infographic videos. The current provider uses a supported ChatGPT login through Codex for storyboarding and image generation, followed by local alignment, animation, and FFmpeg rendering. The provider layer can expand in future releases. The active path does not require or call OpenLux.

## Use the app

1. Open this `launcher` folder in Pinokio.
2. Select **Install** once.
3. Select **Start**, then open **VideoSketchIt**.
4. Open **Connections** and select **Sign in with ChatGPT** if the app does not already recognize your Codex login.

For the fastest setup, choose **Upload Finished Narration**. Upload the complete voiceover and paste its matching script; this path skips local voice cloning and does not require Qwen3-TTS or IndexTTS. A compatible local Gradio voice server is only required when **Clone a Reference Voice** is selected.
5. Configure the local IndexTTS address, upload reference audio, paste a script, and generate.

The app has its own ports (`13010` and `18775`) and its own `.videosketchit` data directory. Older `.cs-board-codex` data is migrated automatically. It does not replace or share job history with the original CS Board installation.

## Local API

The backend listens at `http://127.0.0.1:18775` while the launcher is running.

### JavaScript

```js
const status = await fetch("http://127.0.0.1:18775/api/codex/status").then(r => r.json());
console.log(status.signed_in, status.plan_type, status.rate_limits);
```

### Python

```python
import requests

status = requests.get("http://127.0.0.1:18775/api/codex/status").json()
print(status["signed_in"], status.get("plan_type"))
```

### curl

```bash
curl http://127.0.0.1:18775/api/codex/status
curl -X POST -H 'Content-Type: application/json' \
  -d '{"mode":"browser"}' http://127.0.0.1:18775/api/codex/login
```

Video jobs use the existing multipart `POST /api/jobs` endpoint. See the parent project README for the pipeline, rendering, and asset formats.
