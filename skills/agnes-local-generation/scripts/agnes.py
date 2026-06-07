#!/usr/bin/env python3
"""Generate Agnes AI media and save completed results locally."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_URL = "https://apihub.agnes-ai.com"
TEXT_MODEL = "agnes-2.0-flash"
IMAGE_MODEL = "agnes-image-2.1-flash"
VIDEO_MODEL = "agnes-video-v2.0"
SIZE_RE = re.compile(r"^[1-9]\d*x[1-9]\d*$")
TERMINAL_VIDEO_STATES = {"completed", "failed"}


def api_key() -> str:
    for name in ("AGNES_API_KEY", "AGNES_API_TOKEN", "APIHUB_AGNES_API_KEY"):
        if value := os.environ.get(name):
            return value
    raise SystemExit(
        "Missing API key. Set AGNES_API_KEY, AGNES_API_TOKEN, "
        "or APIHUB_AGNES_API_KEY."
    )


def request_json(
    method: str, path: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
            "User-Agent": "agnes-local-generation/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Agnes API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach Agnes API: {exc.reason}") from exc


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def local_input(value: str) -> str:
    if value.startswith(("http://", "https://", "data:")):
        return value
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"Input file does not exist: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def video_input(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value
    raise SystemExit(
        "Agnes video generation requires an HTTP(S) image URL. "
        "Local data URLs are not accepted by the current video endpoint."
    )


def needs_translation(prompt: str) -> bool:
    return any(ord(character) > 127 for character in prompt)


def translate_prompt(prompt: str) -> str:
    response = request_json(
        "POST",
        "/v1/chat/completions",
        {
            "model": TEXT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate the user's image or video prompt into fluent English. "
                        "Preserve subjects, visual details, style, lighting, composition, "
                        "motion, camera instructions, and constraints. Return only the prompt."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 1000,
        },
    )
    try:
        result = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise SystemExit(f"Prompt translation failed: {json.dumps(response)}") from exc
    if not result:
        raise SystemExit("Prompt translation returned an empty result.")
    return result


def prepared_prompt(prompt: str, translate: bool) -> tuple[str, str | None]:
    if translate and needs_translation(prompt):
        translated = translate_prompt(prompt)
        return translated, translated
    return prompt, None


def collect_urls(value: Any, media: str) -> list[str]:
    image_keys = {"url", "image_url"}
    video_keys = {"url", "video_url", "remixed_from_video_id"}
    keys = image_keys if media == "image" else video_keys
    found: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if (
                    key in keys
                    and isinstance(child, str)
                    and child.startswith(("http://", "https://"))
                ):
                    found.append(child)
                else:
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return list(dict.fromkeys(found))


def extension_for(url: str, content_type: str | None, media: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix and len(suffix) <= 6:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    return ".png" if media == "image" else ".mp4"


def download_media(
    urls: list[str],
    output_dir: str,
    media: str,
    filename: str | None = None,
) -> list[str]:
    if filename and len(urls) != 1:
        raise SystemExit("--filename requires exactly one media URL.")
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    files: list[str] = []

    for index, url in enumerate(urls, start=1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "agnes-local-generation/1.0"}
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type")
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise SystemExit(f"Could not download generated media from {url}: {exc}") from exc

        extension = extension_for(url, content_type, media)
        name = filename or f"{media}-{stamp}-{index}{extension}"
        path = destination / name
        path.write_bytes(data)
        files.append(str(path))
    return files


def result(
    kind: str,
    raw: dict[str, Any],
    *,
    media: str | None = None,
    output_dir: str = "outputs",
    filename: str | None = None,
    download: bool = True,
    prompt_used: str | None = None,
    translated_prompt: str | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    urls = collect_urls(raw, media) if media else []
    files = (
        download_media(urls, output_dir, media, filename)
        if media and download and urls
        else []
    )
    value: dict[str, Any] = {"type": kind}
    if raw.get("id") is not None:
        value["task_id"] = str(raw["id"])
    if raw.get("status") is not None:
        value["status"] = str(raw["status"])
    if files:
        value["files"] = files
    if urls:
        value["urls"] = urls
    if prompt_used:
        value["prompt_used"] = prompt_used
    if translated_prompt:
        value["translated_prompt"] = translated_prompt
    if include_raw:
        value["raw"] = raw
    return value


def validate_size(size: str) -> None:
    if not SIZE_RE.match(size):
        raise SystemExit("--size must use WIDTHxHEIGHT, for example 1024x768.")


def validate_video(args: argparse.Namespace) -> None:
    if args.num_frames > 441 or (args.num_frames - 1) % 8:
        raise SystemExit("--num-frames must be <= 441 and satisfy 8n + 1.")
    if not 1 <= args.frame_rate <= 60:
        raise SystemExit("--frame-rate must be between 1 and 60.")
    if (args.width is None) != (args.height is None):
        raise SystemExit("Set both --width and --height together.")
    if args.width is not None and (args.width <= 0 or args.height <= 0):
        raise SystemExit("--width and --height must be positive.")


def cmd_text(args: argparse.Namespace) -> None:
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": args.prompt})
    raw = request_json(
        "POST",
        "/v1/chat/completions",
        {
            "model": TEXT_MODEL,
            "messages": messages,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        },
    )
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    value = {"type": "text", "content": content}
    if args.raw:
        value["raw"] = raw
    print_json(value)


def cmd_image(args: argparse.Namespace) -> None:
    validate_size(args.size)
    prompt, translated = prepared_prompt(args.prompt, not args.no_translate)
    extra: dict[str, Any] = {"response_format": "url"}
    if args.input:
        inputs = [local_input(value) for value in args.input]
        extra["image"] = inputs[0] if len(inputs) == 1 else inputs
    raw = request_json(
        "POST",
        "/v1/images/generations",
        {
            "model": IMAGE_MODEL,
            "prompt": prompt,
            "size": args.size,
            "extra_body": extra,
        },
    )
    if not collect_urls(raw, "image"):
        raise SystemExit(
            f"Image response did not include a downloadable URL: {json.dumps(raw)}"
        )
    print_json(
        result(
            "image-edit" if args.input else "image",
            raw,
            media="image",
            output_dir=args.output_dir,
            filename=args.filename,
            download=not args.keep_urls_only,
            prompt_used=prompt,
            translated_prompt=translated,
            include_raw=args.raw,
        )
    )


def video_payload(args: argparse.Namespace) -> tuple[dict[str, Any], str, str | None]:
    validate_video(args)
    prompt, translated = prepared_prompt(args.prompt, not args.no_translate)
    payload: dict[str, Any] = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "num_frames": args.num_frames,
        "frame_rate": args.frame_rate,
    }
    for key in ("width", "height", "seed", "negative_prompt"):
        if (value := getattr(args, key)) is not None:
            payload[key] = value
    if args.input:
        inputs = [video_input(value) for value in args.input]
        if len(inputs) == 1 and args.mode is None:
            payload["image"] = inputs[0]
        else:
            payload["extra_body"] = {"image": inputs}
            if args.mode == "keyframes":
                payload["extra_body"]["mode"] = "keyframes"
    elif args.mode:
        raise SystemExit("--mode requires at least one --input.")
    return payload, prompt, translated


def poll_video(task_id: str, timeout: int, interval: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        latest = request_json("GET", f"/v1/videos/{task_id}")
        status = str(latest.get("status", "")).lower()
        print(
            f"Agnes video {task_id}: {status or 'unknown'}",
            file=sys.stderr,
        )
        if latest.get("error") or status == "failed":
            raise SystemExit(f"Video task failed: {json.dumps(latest)}")
        if status in TERMINAL_VIDEO_STATES:
            return latest
        time.sleep(interval)
    raise SystemExit(
        f"Timed out waiting for video task {task_id}. "
        "Run the status command later to resume."
    )


def cmd_video(args: argparse.Namespace) -> None:
    payload, prompt, translated = video_payload(args)
    created = request_json("POST", "/v1/videos", payload)
    task_id = created.get("id")
    if not task_id:
        raise SystemExit(f"Video response did not include a task id: {json.dumps(created)}")
    raw = (
        poll_video(str(task_id), args.timeout, args.interval)
        if not args.no_wait
        else created
    )
    if not args.no_wait and not collect_urls(raw, "video"):
        raise SystemExit(
            f"Completed video response did not include a downloadable URL: {json.dumps(raw)}"
        )
    print_json(
        result(
            "video" if not args.no_wait else "video-task",
            raw,
            media="video",
            output_dir=args.output_dir,
            filename=args.filename,
            download=not args.keep_urls_only and not args.no_wait,
            prompt_used=prompt,
            translated_prompt=translated,
            include_raw=args.raw,
        )
    )


def cmd_status(args: argparse.Namespace) -> None:
    raw = (
        poll_video(args.task_id, args.timeout, args.interval)
        if args.wait
        else request_json("GET", f"/v1/videos/{args.task_id}")
    )
    status = str(raw.get("status", "")).lower()
    if status == "completed" and not collect_urls(raw, "video"):
        raise SystemExit(
            f"Completed video response did not include a downloadable URL: {json.dumps(raw)}"
        )
    print_json(
        result(
            "video",
            raw,
            media="video",
            output_dir=args.output_dir,
            filename=args.filename,
            download=not args.keep_urls_only and status == "completed",
            include_raw=args.raw,
        )
    )


def add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--filename")
    parser.add_argument(
        "--keep-urls-only",
        action="store_true",
        help="Do not download generated media.",
    )
    parser.add_argument("--raw", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Agnes AI media and save it locally."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    text = commands.add_parser("text", help="Generate text.")
    text.add_argument("--prompt", required=True)
    text.add_argument("--system")
    text.add_argument("--temperature", type=float, default=0.7)
    text.add_argument("--max-tokens", type=int, default=1024)
    text.add_argument("--raw", action="store_true")
    text.set_defaults(func=cmd_text)

    image = commands.add_parser("image", help="Generate or edit an image.")
    image.add_argument("--prompt", required=True)
    image.add_argument("--input", action="append", help="Local path or URL. Repeatable.")
    image.add_argument("--size", default="1024x768")
    image.add_argument("--no-translate", action="store_true")
    add_output_options(image)
    image.set_defaults(func=cmd_image)

    video = commands.add_parser("video", help="Generate a video.")
    video.add_argument("--prompt", required=True)
    video.add_argument("--input", action="append", help="Local path or URL. Repeatable.")
    video.add_argument("--mode", choices=("multi-image", "keyframes"))
    video.add_argument("--width", type=int)
    video.add_argument("--height", type=int)
    video.add_argument("--num-frames", type=int, default=121)
    video.add_argument("--frame-rate", type=float, default=24)
    video.add_argument("--seed", type=int)
    video.add_argument("--negative-prompt")
    video.add_argument("--no-translate", action="store_true")
    video.add_argument("--no-wait", action="store_true")
    video.add_argument("--timeout", type=int, default=900)
    video.add_argument("--interval", type=int, default=10)
    add_output_options(video)
    video.set_defaults(func=cmd_video)

    status = commands.add_parser("status", help="Retrieve a video task.")
    status.add_argument("task_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--timeout", type=int, default=900)
    status.add_argument("--interval", type=int, default=10)
    add_output_options(status)
    status.set_defaults(func=cmd_status)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
