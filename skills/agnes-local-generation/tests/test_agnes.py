import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "agnes.py"
SPEC = importlib.util.spec_from_file_location("agnes", SCRIPT)
agnes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agnes)


class FakeResponse:
    def __init__(self, data, content_type="application/octet-stream"):
        self.data = data
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


class AgnesTests(unittest.TestCase):
    def test_local_input_becomes_data_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.png"
            path.write_bytes(b"png-data")
            value = agnes.local_input(str(path))
        self.assertTrue(value.startswith("data:image/png;base64,"))

    def test_video_input_rejects_local_path(self):
        with self.assertRaises(SystemExit):
            agnes.video_input("sample.png")

    def test_collect_urls_finds_nested_media(self):
        data = {
            "data": [{"image_url": "https://example.com/a.png"}],
            "ignored": "https://example.com/no.txt",
        }
        self.assertEqual(
            agnes.collect_urls(data, "image"),
            ["https://example.com/a.png"],
        )

    def test_download_media_writes_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                agnes.urllib.request,
                "urlopen",
                return_value=FakeResponse(b"video", "video/mp4"),
            ):
                files = agnes.download_media(
                    ["https://example.com/result"], directory, "video"
                )
            self.assertEqual(Path(files[0]).read_bytes(), b"video")
            self.assertEqual(Path(files[0]).suffix, ".mp4")

    def test_invalid_video_frame_count_is_rejected(self):
        args = type(
            "Args",
            (),
            {
                "num_frames": 100,
                "frame_rate": 24,
                "width": None,
                "height": None,
            },
        )()
        with self.assertRaises(SystemExit):
            agnes.validate_video(args)

    def test_multi_image_mode_does_not_send_unknown_provider_mode(self):
        args = type(
            "Args",
            (),
            {
                "prompt": "Transition",
                "no_translate": True,
                "num_frames": 121,
                "frame_rate": 24,
                "width": None,
                "height": None,
                "seed": None,
                "negative_prompt": None,
                "input": ["https://example.com/a.png", "https://example.com/b.png"],
                "mode": "multi-image",
            },
        )()
        payload, _, _ = agnes.video_payload(args)
        self.assertNotIn("mode", payload["extra_body"])

    def test_request_json_uses_environment_key(self):
        response = FakeResponse(json.dumps({"ok": True}).encode("utf-8"))
        with patch.dict(os.environ, {"AGNES_API_KEY": "secret"}, clear=True):
            with patch.object(agnes.urllib.request, "urlopen", return_value=response):
                self.assertEqual(agnes.request_json("GET", "/test"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
