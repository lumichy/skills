---
name: agnes-local-generation
description: Generate text, images, image edits, and videos with the Agnes AI API, then save image and video results as local files. Use when the user mentions Agnes AI, Agnes Image, Agnes Video, apihub.agnes-ai.com, text-to-image, image-to-image, text-to-video, image-to-video, keyframes, or asks to download Agnes generation results locally.
---

# Agnes Local Generation

Use `scripts/agnes.py` for Agnes API calls. Do not recreate requests manually.

## Workflow

1. Check that `AGNES_API_KEY`, `AGNES_API_TOKEN`, or `APIHUB_AGNES_API_KEY` is set. Never print the value.
2. Run commands from this skill directory.
3. Save generated media locally. The default output directory is `outputs/`.
4. Return the absolute paths from the command's `files` field.
5. Read `references/api.md` only when endpoint or parameter details are needed.

## Commands

Generate an image and download it:

```bash
python scripts/agnes.py image --prompt "A luminous city above the clouds"
```

Edit a local image:

```bash
python scripts/agnes.py image --prompt "Change the scene to a rainy night" --input photo.png
```

Generate a video, wait for completion, and download it:

```bash
python scripts/agnes.py video --prompt "A slow cinematic push through a neon market"
```

Animate a local image:

```bash
python scripts/agnes.py video --prompt "Add subtle camera movement and natural wind" --input https://example.com/photo.png
```

Create a task without waiting:

```bash
python scripts/agnes.py video --prompt "Ocean waves at sunrise" --no-wait
```

Resume and download a task:

```bash
python scripts/agnes.py status TASK_ID
```

Generate text:

```bash
python scripts/agnes.py text --prompt "Write a concise product tagline."
```

## Rules

- Prefer English visual prompts. The script translates non-ASCII image and video prompts unless `--no-translate` is set.
- Use `--output-dir` when the user names a destination.
- Use `--filename` only for a single expected media file.
- Image editing accepts local inputs encoded as data URLs.
- Video image inputs must be reachable HTTP(S) URLs; the current Agnes video endpoint rejects local data URLs. Reuse the `urls` value from a preceding Agnes image result when available.
- Video generation is asynchronous. The `video` command waits by default; use `--no-wait` only when requested.
- For multiple video inputs, use `--mode keyframes` for start/end keyframes or `--mode multi-image` for references.
- Report provider errors without exposing credentials.
- Warn before video generation only when the user did not explicitly request a video; it can be slow or billable.

## Verification

Run local tests without making API calls:

```bash
python -m unittest discover -s tests -v
```

Run a live text check only when credentials are available and the user accepts API usage:

```bash
python scripts/agnes.py text --prompt "Reply with exactly: Agnes OK"
```
