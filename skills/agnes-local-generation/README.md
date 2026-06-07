# Agnes Local Generation Skill

An Agent Skill for generating text, images, and videos with Agnes AI. Unlike URL-only wrappers, this skill downloads completed images and videos to your local filesystem by default.

Inspired by [Yacey/agnes-ai-generation-skill](https://github.com/Yacey/agnes-ai-generation-skill), with a smaller command surface, local file output, local image inputs, clearer JSON results, and offline unit tests.

## Features

- Text generation with `agnes-2.0-flash`
- Text-to-image and image editing with `agnes-image-2.1-flash`
- Text-to-video, image-to-video, multi-image, and keyframe video generation with `agnes-video-v2.0`
- Automatic download of generated images and videos
- Local image inputs through data URLs
- Automatic translation of non-English visual prompts
- Resumable asynchronous video tasks
- No third-party Python dependencies

## Requirements

- Python 3.10 or newer
- An Agnes AI API key from [platform.agnes-ai.com](https://platform.agnes-ai.com/)

Set one of these environment variables:

```powershell
$env:AGNES_API_KEY = "YOUR_API_KEY"
```

The CLI also recognizes `AGNES_API_TOKEN` and `APIHUB_AGNES_API_KEY`.

Do not commit API keys, paste them into source files, or include them in screenshots.

## Installation

Install the repository as an Agent Skill, or copy the `agnes-local-generation` directory into your agent's skills directory.

Run all commands from the skill directory:

```powershell
cd agnes-local-generation
```

## Quick Start

Generate an image:

```powershell
python scripts/agnes.py image --prompt "A detailed floating city at sunrise"
```

The image is downloaded to `outputs/`. The command prints structured JSON:

```json
{
  "type": "image",
  "files": ["C:\\path\\to\\outputs\\image-20260607-120000.png"],
  "urls": ["https://..."],
  "prompt_used": "A detailed floating city at sunrise"
}
```

Generate and download a video:

```powershell
python scripts/agnes.py video --prompt "A cinematic tracking shot through a futuristic market"
```

Edit a local image:

```powershell
python scripts/agnes.py image --prompt "Make it a rainy cyberpunk night" --input .\photo.png
```

Animate an image URL:

```powershell
python scripts/agnes.py video --prompt "Add a slow camera push and subtle wind" --input https://example.com/photo.png
```

Local image inputs are supported for image editing. The current Agnes video endpoint
requires a reachable HTTP(S) image URL and rejects local data URLs. You can reuse the
`urls` value returned by the preceding image command.

## Output Control

Choose an output directory:

```powershell
python scripts/agnes.py image --prompt "Minimal blue poster" --output-dir .\artifacts
```

Choose a filename:

```powershell
python scripts/agnes.py image --prompt "Minimal blue poster" --filename poster.png
```

Use `--keep-urls-only` to skip downloads.

## Asynchronous Video

Video generation waits for completion by default. To create a task and return immediately:

```powershell
python scripts/agnes.py video --prompt "Ocean waves at sunrise" --no-wait
```

Download the completed result later:

```powershell
python scripts/agnes.py status TASK_ID
```

## Multi-Image and Keyframes

Use multiple local files or URLs:

```powershell
python scripts/agnes.py video `
  --prompt "Create a smooth transition between these frames" `
  --input .\start.png `
  --input .\end.png `
  --mode keyframes
```

## Useful Options

```text
--output-dir PATH       Local media destination (default: outputs)
--filename NAME         Filename for a single downloaded result
--keep-urls-only        Do not download returned media
--no-translate          Keep a non-English visual prompt unchanged
--raw                   Include the complete provider response
```

Use `python scripts/agnes.py COMMAND --help` for command-specific options.

## Testing

The tests mock network requests and do not require an API key:

```powershell
python -m unittest discover -s tests -v
```

## Project Structure

```text
agnes-local-generation/
|-- SKILL.md
|-- README.md
|-- LICENSE
|-- agents/
|   `-- openai.yaml
|-- references/
|   `-- api.md
|-- scripts/
|   `-- agnes.py
`-- tests/
    `-- test_agnes.py
```

## License

MIT. See `LICENSE`.
