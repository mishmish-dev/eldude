"""Documentation checks must catch broken navigation and stale maps/results."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eldude.check_docs import check


class DocumentationTests(unittest.TestCase):
    def test_links_anchors_maps_and_example_expectations(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                'README.md': (
                    '# Home\n[duplicate](docs/reference.md#repeat-1)\n'
                    '[legacy](docs/reference.md#old-id)\n'
                    '[encoded](docs/with%20space.md#caf%C3%A9)\n'
                    '[web](https://example.invalid/missing)\n'
                    '`[code](missing.md)`\n'
                    '````md\n[code](missing.md)\n```\n## Hidden\n````\n'
                    '~~~md\n[code](missing.md)\n~~~\n'
                ),
                'docs/index.md': '[chapter](language-spec/01-foundations.md)\n',
                'docs/language-spec/01-foundations.md': '# Foundations\n',
                'docs/reference.md': '# Repeat\n## Repeat\n<a id="old-id"></a>\n',
                'docs/with space.md': '# Café\n',
                'docs/implementation.md': '[module](../src/eldude/runner.py)\n[test](../tests/test_runner.py)\n',
                'src/eldude/runner.py': '',
                'tests/test_runner.py': '',
                'examples/README.md': '| [value](value.eld) | `42` | Integer |\n',
                'examples/value.eld': '',
                'examples/manifest.json': json.dumps({'runnable': {'value.eld': 42}, 'pending': {}}),
            }
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            self.assertEqual(check(root), [])

            # Removing any validation below must make its corresponding case fail.
            cases = [
                ('README.md', '[missing](gone.md)\n', 'gone.md'),
                ('README.md', files['README.md'] + '[missing](#hidden)\n', '#hidden'),
                ('README.md', '[missing](docs/reference.md#absent)\n', '#absent'),
                ('docs/index.md', '', '01-foundations.md'),
                ('docs/implementation.md', '', 'runner.py'),
                ('docs/implementation.md', '[module](../src/eldude/runner.py)\n', 'test_runner.py'),
                ('examples/README.md', '', 'value.eld'),
                ('examples/README.md', files['examples/README.md'] * 2, 'value.eld'),
                ('examples/README.md', '| [value](value.eld) | `7` | Wrong |\n', 'value.eld'),
                ('examples/README.md', '| [value](value.eld) | `oops` | Invalid |\n', 'value.eld'),
            ]
            for name, content, expected in cases:
                with self.subTest(name=name, content=content):
                    (root / name).write_text(content, encoding='utf-8')
                    errors = check(root)
                    self.assertTrue(any(expected in error for error in errors), errors)
                    (root / name).write_text(files[name], encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
