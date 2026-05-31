---
name: tts-edge
description: |
  Convert text to speech using Edge-TTS (Microsoft Edge's online TTS service).
  Use this skill whenever the user wants to:
  - Read text aloud / speak / say something
  - Convert text to audio / voice / speech
  - Generate voice from text
  - Play text as audio
  Supports English, Chinese (Mandarin), and Japanese with high-quality natural voices.
  Uses Python implementation (more stable than Node.js version).
---

# Edge-TTS Text-to-Speech

Convert text to natural-sounding speech using Microsoft Edge's free TTS service.

## When to use

Use this skill when the user asks to:
- Read/speak/say text aloud
- Convert text to audio/voice/speech
- Generate voice from text
- Play text as audio

## Supported Languages

| Language | Code | Default Voice |
|----------|------|---------------|
| English | `en` | en-US-AvaNeural |
| Chinese | `zh` | zh-CN-XiaoxiaoNeural |
| Japanese | `ja` | ja-JP-NanamiNeural |

## Workflow

### Step 1: Detect or ask for language

Ask the user which language to use (en/zh/ja) if not obvious from the text.
Default to the detected language of the input text.

### Step 2: Ensure dependencies

```bash
pip3 show edge-tts 2>/dev/null || pip3 install --break-system-packages edge-tts
```

### Step 3: Run TTS

Use Python script with:
- `--text "the text to speak"`
- `--lang en|zh|ja` (optional, auto-detect if not provided)
- `--voice "voice-name"` (optional, use default if not provided)
- `--output "path.mp3"` (optional, use temp file if not provided)

Example:
```bash
python3 scripts/tts.py --text "你好世界" --lang zh
```

### Step 4: Play the audio

After generating the MP3 file, play it:
- Linux: `mpv --no-video output.mp3` or `ffplay -nodisp output.mp3`
- macOS: `afplay output.mp3`
- Windows: `powershell -c "(New-Object Media.SoundPlayer 'output.mp3').PlaySync()"`

## Script Usage

```bash
python3 scripts/tts.py --text "你好世界" --lang zh
```

## Voice Options

**English:**
- `en-US-AvaNeural` (female, default)
- `en-US-AndrewNeural` (male)
- `en-GB-SoniaNeural` (British female)

**Chinese:**
- `zh-CN-XiaoxiaoNeural` (female, default)
- `zh-CN-YunxiNeural` (male)
- `zh-CN-YunyangNeural` (male, news style)

**Japanese:**
- `ja-JP-NanamiNeural` (female, default)
- `ja-JP-KeitaNeural` (male)

## Example

User: "Read this in Chinese: 你好，今天天气不错"

Response:
1. Detect language: zh (Chinese)
2. Ensure edge-tts is installed
3. Run: `python3 scripts/tts.py --text "你好，今天天气不错" --lang zh`
4. Play the output file with available player
