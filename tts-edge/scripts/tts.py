#!/usr/bin/env python3
"""
Edge-TTS wrapper for Python
Usage: python3 tts.py --text "Hello" --lang en [--voice "voice-name"] [--output "path.wav"]
"""

import argparse
import asyncio
import os
import platform
import subprocess
import tempfile
import re

# Default voices per language
DEFAULT_VOICES = {
    'en': 'en-US-AvaNeural',
    'zh': 'zh-CN-XiaoxiaoNeural',
    'ja': 'ja-JP-NanamiNeural'
}


def detect_language(text: str) -> str:
    """Detect language from text content."""
    # Chinese characters (CJK Unified Ideographs)
    if re.search(r'[一-鿿]', text):
        return 'zh'
    # Japanese hiragana/katakana
    if re.search(r'[ぁ-ゟァ-ヿ]', text):
        return 'ja'
    # Default to English
    return 'en'


def get_player_command(filepath: str) -> tuple | None:
    """Get the appropriate audio player command for the platform."""
    system = platform.system()

    if system == 'Darwin':  # macOS
        return ('afplay', [filepath])
    elif system == 'Windows':
        return ('powershell', ['-c', f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()"])
    else:  # Linux
        # Try mpv, then aplay, then ffplay
        players = [
            ('mpv', ['--no-video', filepath]),
            ('aplay', [filepath]),
            ('ffplay', ['-nodisp', '-autoexit', filepath]),
        ]
        for cmd, args in players:
            if subprocess.run(['which', cmd], capture_output=True).returncode == 0:
                return (cmd, args)
        return None


async def run_tts(text: str, voice: str, output: str) -> str:
    """Run edge-tts to generate speech."""
    import edge_tts

    print(f"Generating speech...")
    print(f"  Text: \"{text[:50]}{'...' if len(text) > 50 else ''}\"")
    print(f"  Voice: {voice}")
    print(f"  Output: {output}")

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output)

    print(f"\nAudio saved to: {output}")
    return output


def play_audio(filepath: str) -> bool:
    """Play the audio file."""
    player_cmd = get_player_command(filepath)

    if not player_cmd:
        print(f"No audio player found. Audio file saved at: {filepath}")
        return False

    cmd, args = player_cmd
    print(f"Playing audio with: {cmd}")

    try:
        subprocess.run([cmd] + args)
        return True
    except Exception as e:
        print(f"Failed to play: {e}")
        print(f"Audio file saved at: {filepath}")
        return False


def ensure_dependencies():
    """Ensure edge-tts is installed."""
    try:
        import edge_tts
    except ImportError:
        print("Installing edge-tts...")
        subprocess.run(['pip3', 'install', 'edge-tts'], check=True)
        import edge_tts


def main():
    parser = argparse.ArgumentParser(description='Edge-TTS wrapper')
    parser.add_argument('--text', '-t', required=True, help='Text to speak')
    parser.add_argument('--lang', '-l', default=None, help='Language (en/zh/ja)')
    parser.add_argument('--voice', '-v', default=None, help='Voice name')
    parser.add_argument('--output', '-o', default=None, help='Output file path')

    args = parser.parse_args()

    # Ensure dependencies
    ensure_dependencies()

    # Detect language if not specified
    lang = args.lang or detect_language(args.text)
    voice = args.voice or DEFAULT_VOICES.get(lang, DEFAULT_VOICES['en'])

    # Create output path
    tmp_dir = os.path.join(tempfile.gettempdir(), 'edge-tts')
    os.makedirs(tmp_dir, exist_ok=True)
    output = args.output or os.path.join(tmp_dir, f'tts_{int(os.times().elapsed * 1000)}.mp3')

    # Run TTS
    asyncio.run(run_tts(args.text, voice, output))

    # Play audio
    play_audio(output)


if __name__ == '__main__':
    main()
