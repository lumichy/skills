# ComfyUI Media Generator Skill

An Agent Skill for connecting to a ComfyUI server (local or remote), automatically discovering available image and video workflows, and executing generation prompts seamlessly.

## Features

- **Automatic Workflow Discovery**: Scans workflows on the ComfyUI server (`/api/userdata`) or fallback local workflow directories.
- **Media Type Classification**: Automatically identifies whether a workflow produces images (`image`), text-to-video (`video`), or image-to-video (`i2v`).
- **Flexible Server Support**: Supports local server (`127.0.0.1:8000`), custom ports (`8188`), and remote endpoints via HTTP/HTTPS with optional API token authentication.
- **Image & Video Generation**: Handles image dimensions, seeds, positive/negative prompts, and reference images for i2v.
- **Zero Heavy Dependencies**: Uses Python standard library (`urllib`, `json`, `socket`, `argparse`).

## Requirements

- Python 3.10 or newer
- A running ComfyUI server (local or remote)

## Server Configuration

Configure the server endpoint via environment variables or command-line flags:

| Setting | Env Var | CLI Flag | Default |
|---|---|---|---|
| Host & Port | `COMFYUI_HOST` | `--host` | `127.0.0.1:8000` |
| URL Scheme | `COMFYUI_SCHEME` | `--scheme` | `http` |
| API Token | `COMFYUI_API_TOKEN` | `--api-token` | *(none)* |
| Server Workflows Dir | `COMFYUI_USERDATA_DIR` | - | `workflows` |

### Environment Variables

```powershell
$env:COMFYUI_HOST = "127.0.0.1:8188"
$env:COMFYUI_SCHEME = "http"
# For remote HTTPS with auth:
$env:COMFYUI_HOST = "comfy.example.com"
$env:COMFYUI_SCHEME = "https"
$env:COMFYUI_API_TOKEN = "your-api-token"
```

## Quick Start

### 1. List Available Workflows

```powershell
python scripts/comfy_engine.py --list
```

### 2. Generate an Image

```powershell
python scripts/comfy_engine.py --media-type image --prompt "A serene Japanese zen garden in autumn, 8k resolution" --width 1024 --height 1024
```

### 3. Generate Video (Text-to-Video)

```powershell
python scripts/comfy_engine.py --media-type video --prompt "A cinematic drone shot flying over misty mountain peaks at sunrise"
```

### 4. Generate Video from Image (Image-to-Video)

```powershell
python scripts/comfy_engine.py --media-type i2v --input-image "portrait.png" --prompt "Subtle camera push in, gentle wind blowing through hair"
```

### 5. Run a Specific Workflow

```powershell
python scripts/comfy_engine.py --workflow "text2image_qwen.json" --prompt "Cyberpunk city alley in neon rain"
```

## Project Structure

```text
comfyui-generator/
|-- SKILL.md
|-- README.md
|-- manifest.json
|-- scripts/
|   `-- comfy_engine.py
`-- evals/
    `-- evals.json
```

## License

MIT License
