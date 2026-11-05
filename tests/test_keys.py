"""The visitor's own DeepSeek key: where it lives, and where it must not."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import main
from app.services import keys, llm

ROOT = Path(__file__).resolve().parents[1]


class KeyStoreTest(unittest.TestCase):
    """Saving, masking and clearing the key from the settings page."""

    def setUp(self) -> None:
        self.dir = Path(__file__).resolve().parent / '_keyscratch'
        self.dir.mkdir(exist_ok=True)
        self.path = self.dir / keys.FILENAME
        self.addCleanup(self._cleanup)
        patcher = mock.patch.object(keys, 'key_path', return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cleanup(self) -> None:
        if self.path.is_file():
            self.path.unlink()
        if self.dir.is_dir() and not any(self.dir.iterdir()):
            self.dir.rmdir()

    def test_a_saved_key_comes_back(self):
        keys.save_key('sk-abcdefghijklmnop')
        self.assertEqual(keys.saved_key(), 'sk-abcdefghijklmnop')
        self.assertEqual(keys.origin(), 'saved')

    def test_an_empty_key_is_refused(self):
        with self.assertRaises(ValueError):
            keys.save_key('   ')
        self.assertIsNone(keys.saved_key())

    def test_clearing_removes_it(self):
        keys.save_key('sk-abcdefghijklmnop')
        keys.clear_key()
        self.assertIsNone(keys.saved_key())

    def test_masking_never_shows_enough_to_use(self):
        # A made-up key with the same shape: the mask must not reveal the whole.
        key = 'sk-0000example0000notarealkey0000'
        shown = keys.mask(key)
        self.assertNotIn(key, shown)
        self.assertTrue(shown.startswith('sk-000'))
        self.assertTrue(shown.endswith('0000'))
        self.assertLess(len(shown), len(key))


class KeyNeverLeaksTest(unittest.TestCase):
    """The key must not reach the database, the report, or a log line."""

    def test_llm_error_is_logged_without_the_key(self):
        """A provider can echo the key back in its error body.

        The log line outlives the request, so the key has to be scrubbed out of
        it before it is written.
        """
        secret = 'sk-live0123456789abcdef'
        noisy = RuntimeError(f'401 invalid api key: {secret} for request x')
        with mock.patch.object(llm, 'OpenAI', side_effect=noisy), \
             mock.patch.object(llm.keys_store, 'saved_key', return_value=None), \
             mock.patch.object(llm, 'log') as log:
            result = llm.complete('s', 'u', role='chat', api_key=secret)
        self.assertIsNone(result)
        logged = ' '.join(str(call) for call in log.warning.call_args_list)
        self.assertNotIn(secret, logged)
        self.assertIn('***', logged)

    def test_a_caller_key_beats_the_saved_one(self):
        with mock.patch.object(llm.keys_store, 'saved_key', return_value='sk-saved'), \
             mock.patch.object(llm, 'OpenAI') as openai:
            openai.return_value.chat.completions.create.return_value = mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content='hi'))]
            )
            llm.complete('s', 'u', role='chat', api_key='sk-caller')
        self.assertEqual(openai.call_args.kwargs['api_key'], 'sk-caller')

    def test_the_saved_key_is_used_when_the_caller_gives_none(self):
        with mock.patch.object(llm.keys_store, 'saved_key', return_value='sk-saved'), \
             mock.patch.object(llm, 'OpenAI') as openai:
            openai.return_value.chat.completions.create.return_value = mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content='hi'))]
            )
            llm.complete('s', 'u', role='chat')
        self.assertEqual(openai.call_args.kwargs['api_key'], 'sk-saved')

    def test_a_key_is_never_part_of_the_prompt(self):
        """The prompt is what gets stored and shown; the key must not ride along."""
        with mock.patch.object(llm.keys_store, 'saved_key', return_value=None), \
             mock.patch.object(llm, 'OpenAI') as openai:
            openai.return_value.chat.completions.create.return_value = mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content='hi'))]
            )
            llm.complete('system text', 'user text', role='chat', api_key='sk-secret-value')
            sent = openai.return_value.chat.completions.create.call_args.kwargs['messages']
        self.assertNotIn('sk-secret-value', json.dumps(sent, ensure_ascii=False))


class SettingsPageTest(unittest.TestCase):
    """The write surface for a key has to be local-only."""

    def setUp(self) -> None:
        self.dir = Path(__file__).resolve().parent / '_keyscratch_page'
        self.dir.mkdir(exist_ok=True)
        self.path = self.dir / keys.FILENAME
        self.addCleanup(self._cleanup)
        patcher = mock.patch.object(keys, 'key_path', return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cleanup(self) -> None:
        if self.path.is_file():
            self.path.unlink()
        if self.dir.is_dir() and not any(self.dir.iterdir()):
            self.dir.rmdir()

    def test_the_page_explains_the_key_is_optional(self):
        page = TestClient(main.app).get('/settings')
        self.assertEqual(page.status_code, 200)
        self.assertIn('不自带任何 key', page.text)
        self.assertIn('不填也能用', page.text)

    def test_the_key_file_is_gitignored(self):
        ignored = (ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('data/deepseek.json', ignored)

    def test_settings_page_is_refused_to_the_network(self):
        """No login, so a remote caller must not be able to write the key."""
        with mock.patch.object(main, '_is_local', return_value=False):
            response = TestClient(main.app).get('/settings')
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
