"""Persistent public suggestions never leak across robot IDs or accept invalid saves."""
import tempfile
from pathlib import Path
import unittest

from remote_yam.task_suggestions import read_suggestions, save_suggestions


class TaskSuggestionsTests(unittest.TestCase):
    def test_defaults_and_persistence_are_robot_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'suggestions.sqlite3'
            self.assertEqual(read_suggestions('yam-1', path)[0], 'Put the apple onto the plate')
            self.assertEqual(read_suggestions('yam-2', path)[-1], 'Put the towel into the bin')
            self.assertEqual(read_suggestions('other', path), [])
            self.assertFalse(path.exists())
            edited = ['Lift the apple', 'Move the cup', 'Stack two blocks']
            save_suggestions(path, 'yam-1', edited)
            self.assertEqual(read_suggestions('yam-1', Path(str(path))), edited)
            self.assertEqual(read_suggestions('yam-2', path)[0], 'Stack the blocks')

    def test_invalid_saves_preserve_prior_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'suggestions.sqlite3'
            good = ['First task', 'Second task', 'Third task']
            save_suggestions(path, 'yam-1', good)
            for invalid in ([], ['one'], ['', 'two', 'three'], ['a'*201, 'two', 'three'], ['a\nb', 'two', 'three'], [1, 'two', 'three']):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    save_suggestions(path, 'yam-1', invalid)
                self.assertEqual(read_suggestions('yam-1', path), good)
