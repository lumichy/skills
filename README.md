# Claude Code Skills

Custom skills for Claude Code CLI.

## Skills

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
    ├── tts-edge/
    │   ├── SKILL.md
    │   ├── manifest.json
    │   ├── scripts/
    │   │   └── tts.py
    │   └── evals/
    │       └── evals.json
    └── tokyo-event/
        ├── SKILL.md
        ├── manifest.json
        └── evals/
            └── evals.json
```

## Installation

### For Claude Code CLI

1. Clone this repository:
```bash
git clone https://github.com/lumichy/skills.git
```

2. Copy skills to your Claude Code skills directory:
```bash
cp -r skills/tts-edge ~/.claude/skills/
cp -r skills/tokyo-event ~/.claude/skills/
```

3. Restart Claude Code to load the new skills.

### Manual Installation

You can also create symbolic links:
```bash
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
