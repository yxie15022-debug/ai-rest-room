"""Animation assets: the cat frame sets the window and room page play."""

import os
import struct
import unittest
from pathlib import Path
from unittest import mock

from app.services.report import mascot_animal, mascot_clips

ROOT = Path(__file__).resolve().parents[1]
APP_CAT = ROOT / 'app' / 'static' / 'mascot' / 'cat'
PLUGIN_CAT = ROOT / 'plugin' / 'frames' / 'mascot' / 'cat'
APP_STUDIO = ROOT / 'app' / 'static' / 'mascot' / 'studio'
PLUGIN_STUDIO = ROOT / 'plugin' / 'frames' / 'mascot' / 'studio'
PREVIEW = ROOT / 'docs' / 'preview'
SCENES = ('enter', 'sleep', 'sit', 'study', 'chat')


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b'\x89PNG\r\n\x1a\n', path
    return struct.unpack('>II', head[16:24])


class CatAnimationTest(unittest.TestCase):
    def test_app_frames_exist_and_are_square(self):
        for scene in SCENES:
            frames = sorted((APP_CAT / scene).glob('*.png'))
            self.assertGreaterEqual(len(frames), 10, scene)
            for frame in frames:
                self.assertEqual(png_size(frame), (512, 512), frame)

    def test_plugin_mirror_matches(self):
        for scene in SCENES:
            app_count = len(list((APP_CAT / scene).glob('*.png')))
            plugin_count = len(list((PLUGIN_CAT / scene).glob('*.png')))
            self.assertEqual(app_count, plugin_count, scene)

    def test_mascot_clips_counts_cat(self):
        clips = mascot_clips('cat')
        for scene in SCENES:
            self.assertGreaterEqual(clips.get(scene, 0), 10, scene)

    def test_env_override_picks_animal(self):
        with mock.patch.dict(os.environ, {'AI_REST_ROOM_MASCOT': 'cat'}):
            self.assertEqual(mascot_animal(), 'cat')
        with mock.patch.dict(os.environ, {'AI_REST_ROOM_MASCOT': 'dragon'}):
            self.assertEqual(mascot_animal(), 'rabbit')

    def test_previews_and_reference_exist(self):
        self.assertTrue((PREVIEW / 'cat-contact.png').is_file())
        for scene in ('sleep', 'sit', 'study', 'chat'):
            gif = PREVIEW / f'{scene}.gif'
            self.assertTrue(gif.is_file(), gif)
            self.assertTrue(gif.read_bytes().startswith(b'GIF89a'), gif)
        self.assertGreater((ROOT / 'docs' / 'reference' / 'cat-lowpoly-sleep-ref.jpg').stat().st_size, 1000)


class StudioAnimationTest(unittest.TestCase):
    def test_studio_frames_and_mirror(self):
        for scene in SCENES:
            app_frames = sorted((APP_STUDIO / scene).glob('*.png'))
            plugin_frames = sorted((PLUGIN_STUDIO / scene).glob('*.png'))
            self.assertGreaterEqual(len(app_frames), 10, scene)
            self.assertEqual(len(app_frames), len(plugin_frames), scene)
            self.assertEqual(png_size(app_frames[0]), (512, 512), app_frames[0])

    def test_studio_clips_and_previews(self):
        clips = mascot_clips('studio')
        for scene in SCENES:
            self.assertGreaterEqual(clips.get(scene, 0), 10, scene)
        self.assertTrue((PREVIEW / 'studio-contact.png').is_file())
        for scene in SCENES:
            gif = PREVIEW / f'studio-{scene}.gif'
            self.assertTrue(gif.is_file(), gif)
            self.assertTrue(gif.read_bytes().startswith(b'GIF89a'), gif)


if __name__ == '__main__':
    unittest.main()
