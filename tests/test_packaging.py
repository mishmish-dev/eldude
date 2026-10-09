"""Installed entry points work without the repository on Python's import path."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class PackagingTests(unittest.TestCase):
    def test_module_entry_point_from_another_directory(self):
        with TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-m', 'eldude', '--help'],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('usage: eldude', result.stdout)

    def test_runner_loads_grammar_and_standard_library_from_another_directory(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'main.eld'
            source.write_text('module app; import core::option::{Option}; '
                              'pub fn main()->Int { match Option::Some(42) { '
                              'case Option::Some(value) => value; case Option::None => 0; } }')
            result = subprocess.run([sys.executable, '-I', '-m', 'eldude.run_eldude', str(source)],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '42\n')
