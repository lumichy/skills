# Claude Code Skills

Custom skills for Claude Code CLI and AI Coding Agents.

## Skills

### agnes-local-generation

Generate text, images, image edits, and videos with Agnes AI, then save completed media locally.

**Features:**
- Downloads generated images and videos to local files
- Supports local image inputs for image editing
- Supports text-to-video, image-to-video, multi-image, and keyframe workflows
- Resumes asynchronous video tasks
- Uses only the Python standard library

**Usage:**
```bash
/agnes-local-generation Generate an image of a floating city and save it locally.
```

**Requirements:** An Agnes AI API key in `AGNES_API_KEY`, `AGNES_API_TOKEN`, or `APIHUB_AGNES_API_KEY`.

---

### comfyui-generator

Connect to local or remote ComfyUI servers, automatically discover workflows, and execute image / video generations.

**Features:**
- Discovers workflows via ComfyUI server `/api/userdata` endpoint or local directories
- Auto-classifies workflows into `image`, `video` (text-to-video), and `i2v` (image-to-video)
- Supports remote servers over HTTP/HTTPS with optional API token authentication
- Flexible parameters for prompt, negative prompt, dimensions, and seed
- Uses only the Python standard library

**Usage:**
```bash
/comfyui-generator Generate an image of a futuristic cyberpunk city.
```

**Directory structure:**
```
skills/comfyui-generator/
├── SKILL.md          # Skill definition
├── README.md         # Detailed guide
├── manifest.json     # Metadata
├── scripts/
│   └── comfy_engine.py  # ComfyUI API engine
└── evals/
    └── evals.json    # Evaluation cases
```

**Requirements:** A running ComfyUI server (`COMFYUI_HOST`, default `127.0.0.1:8000`).

---

### tts-edge

Convert text to speech using Edge-TTS (Microsoft Edge's online TTS service).

**Features:**
- Supports English, Chinese (Mandarin), and Japanese
- High-quality natural neural voices
- Auto language detection
- Cross-platform audio playback

**Usage:**
```
/tts-edge Read this aloud: Hello, world!
```

**Directory structure:**
```
skills/tts-edge/
├── SKILL.md          # Skill definition
├── manifest.json     # Metadata
├── scripts/
│   └── tts.py        # TTS wrapper script
└── evals/
    └── evals.json    # Evaluation cases
```

---

### tokyo-event

Query Tokyo events for a specific date.

**Features:**
- Search events from 7+ priority venues (Yoyogi Park, Ueno Park, Odaiba, etc.)
- Support for concerts, exhibitions, festivals, sports events
- Multi-language queries (Chinese, Japanese, English)
- Smart date range detection for long-term exhibitions

**Usage:**
```
/tokyo-event 6月15日东京有什么活动？
/tokyo-event Tokyo events on June 20, 2026
```

**Directory structure:**
```
skills/tokyo-event/
├── SKILL.md          # Skill definition
├── manifest.json     # Metadata
└── evals/
    └── evals.json    # Evaluation cases
```

**Dependencies:** Requires `web-search` skill (Brave Search API) for optimal results.

---

## Directory Structure

```
.
├── README.md
└── skills/
    ├── agnes-local-generation/
    │   ├── SKILL.md
    │   ├── README.md
    │   ├── manifest.json
    │   ├── agents/
    │   ├── evals/
    │   ├── references/
    │   ├── scripts/
    │   └── tests/
    ├── comfyui-generator/
    │   ├── SKILL.md
    │   ├── README.md
    │   ├── manifest.json
    │   ├── scripts/
    │   │   └── comfy_engine.py
    │   └── evals/
    │       └── evals.json
    ├── tokyo-event/
    │   ├── SKILL.md
    │   ├── manifest.json
    │   └── evals/
    │       └── evals.json
    └── tts-edge/
        ├── SKILL.md
        ├── manifest.json
        ├── scripts/
        │   └── tts.py
        └── evals/
            └── evals.json
```

## Installation

### For Claude Code CLI / AI Agents

1. Clone this repository:
```bash
git clone https://github.com/lumichy/skills.git
```

2. Copy skills to your skills directory:
```bash
cp -r skills/agnes-local-generation ~/.claude/skills/
cp -r skills/comfyui-generator ~/.claude/skills/
cp -r skills/tts-edge ~/.claude/skills/
cp -r skills/tokyo-event ~/.claude/skills/
```

3. Restart your agent to load the new skills.

### Manual Installation

You can also create symbolic links:
```bash
ln -s $(pwd)/skills/agnes-local-generation ~/.claude/skills/agnes-local-generation
ln -s $(pwd)/skills/comfyui-generator ~/.claude/skills/comfyui-generator
ln -s $(pwd)/skills/tts-edge ~/.claude/skills/tts-edge
ln -s $(pwd)/skills/tokyo-event ~/.claude/skills/tokyo-event
```

## Skill Format

Each skill follows this structure:

```
skill-name/
├── SKILL.md          # Required: Skill definition with frontmatter
├── manifest.json     # Optional: Metadata (version, category, dependencies)
├── scripts/          # Optional: Helper scripts
│   └── *.py / *.sh
└── evals/            # Optional: Evaluation cases
    └── evals.json
```

### SKILL.md Format

```markdown
---
name: skill-name
description: Short description of when to use this skill
---

# Skill Title

Detailed instructions for the skill...
```

### manifest.json Format

```json
{
  "name": "skill-name",
  "version": "1.0.0",
  "category": "Category",
  "description": "Detailed description",
  "homepage": "",
  "compat": ["claude-code", "claude-ai", "cursor", "codex-cli", "gemini-cli"],
  "dependencies": []
}
```

## License

MIT License
