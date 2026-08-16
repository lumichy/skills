---
name: comfyui-generator
description: Automatically identify existing ComfyUI workflows (on the local machine or on a remote ComfyUI server) and generate images or videos according to user requests.
---

# ComfyUI Media Generator Skill

This skill allows the AI agent to connect to a ComfyUI server (which may run **on the same machine or on a different / remote server**), discover existing workflows (via the server's `/api/userdata` API and/or local workflow directories), classify them as **image** or **video** workflows, and execute image/video generation based on user instructions.

## When to Use

Use this skill when the user asks to:
- Generate an image using ComfyUI (e.g. "画像を作って", "ComfyUIでイラストを出力して")
- Generate a video using ComfyUI (e.g. "動画を作って", "Short video to video generation")
- List available ComfyUI workflows or use a specific existing workflow.

## Server Configuration

The engine talks to a single ComfyUI server over its HTTP API. The server is
configured via environment variables (recommended) or CLI flags:

| Setting                | Env var              | CLI flag      | Default           |
|------------------------|----------------------|---------------|-------------------|
| Host `host:port`       | `COMFYUI_HOST`       | `--host`      | `127.0.0.1:8000`  |
| URL scheme             | `COMFYUI_SCHEME`     | `--scheme`    | `http`            |
| Bearer token (auth)    | `COMFYUI_API_TOKEN`  | `--api-token` | *(none)*          |
| Workflow folder on server | `COMFYUI_USERDATA_DIR` | -         | `workflows`       |

Examples for a **remote server**:

```bash
# Remote server over plain HTTP
export COMFYUI_HOST="192.168.1.50:8188"
export COMFYUI_SCHEME="http"

# Remote server over HTTPS with an API token (e.g. started with --auth)
export COMFYUI_HOST="comfy.example.com"
export COMFYUI_SCHEME="https"
export COMFYUI_API_TOKEN="<token>"

# Or pass them per command instead of env vars:
python scripts/comfy_engine.py --list --host 192.168.1.50:8188 --scheme http
python scripts/comfy_engine.py --list --host comfy.example.com --scheme https --api-token "<token>"
```

### How workflow discovery works

- The engine first lists workflows stored on the **ComfyUI server** using the
  `/api/userdata?dir=workflows&recurse=true&full_info=true` endpoint and fetches
  each workflow JSON from the server. This works whether the server is local or remote.
- If the server cannot be reached, it **falls back to local workflow directories**
  (see `WORKFLOW_DIRS` in `scripts/comfy_engine.py`).
- Entries are shown with a `[SERVER]` or `[LOCAL]` tag in `--list`.

## Commands

All operations are driven by the python engine at:
`scripts/comfy_engine.py`

### 1. List Workflows

Shows the configured server URL, reachability, and all discovered workflows with
their classified media types (`[IMAGE]` / `[VIDEO]`) and source (`[SERVER]` / `[LOCAL]`):

```bash
python scripts/comfy_engine.py --list
```

### 2. Generate Image

To generate an image based on a user's prompt (automatically picks an `image` workflow such as Qwen Image):

```bash
python scripts/comfy_engine.py --media-type image --prompt "<PROMPT_TEXT>" --width 768 --height 1024
```

### 3. Generate Video (Text-to-Video)

To generate a video from a text prompt (picks a `video` workflow such as MiniMax / Wan):

```bash
python scripts/comfy_engine.py --media-type video --prompt "<PROMPT_TEXT>"
```

### 4. Generate Video from Image (Image-to-Video / i2v)

To generate a video using an input reference image and motion prompt (automatically uploads image to the server and picks an `i2v` workflow):

```bash
python scripts/comfy_engine.py --media-type i2v --input-image "<IMAGE_PATH>" --prompt "<MOTION_PROMPT>"
```

### 5. Use Specific Workflow

To force using a specific workflow (matched by name, e.g. `text2image_qwen.json`, or a local file path):

```bash
python scripts/comfy_engine.py --workflow "text2image_qwen.json" --prompt "<PROMPT_TEXT>"
```

## Options & Arguments

- `--media-type`: Target `image`, `video`, or `i2v`.
- `--input-image`: Path to reference image for Image-to-Video generation.
- `--workflow`: Specific workflow JSON filename (server or local) or a local path.
- `--prompt`: Positive prompt text.
- `--negative-prompt`: Negative prompt text.
- `--width` / `--height`: Output width/height pixels.
- `--seed`: Integer seed for reproducibility.
- `--output-dir`: Output directory for generated media (defaults to current directory).
- `--host` / `--scheme` / `--api-token`: Override server connection (see table above).

## Output Handling

**Always pass `--output-dir` pointing to the user's working directory (project root), not the skill directory.**
The engine defaults to `.` (current directory), so if the command is run from inside this skill folder the files would be saved there. Example:

```bash
python scripts/comfy_engine.py --media-type image --prompt "<PROMPT_TEXT>" --output-dir "<USER_WORKING_DIR>"
```

After the command completes:
1. Verify the saved file path printed in stdout (`Saved: <path>`).
2. Present the generated file to the user (embed image/video preview in markdown walkthrough or direct response).
