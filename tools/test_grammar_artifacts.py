"""Portable grammar export and generated-publication synchronization checks."""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import check_grammar
from check_grammar import Grammar

class ArtifactTests(unittest.TestCase):
    def test_checker_uses_utf8_in_c_locale(self):
        environment = dict(os.environ, LC_ALL='C', PYTHONUTF8='0', PYTHONCOERCECLOCALE='0', PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, str(Path(check_grammar.__file__).resolve())], env=environment, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_json_round_trip_recognizes_both_entry_points(self):
        grammar = Grammar(check_grammar.GRAMMAR.read_text(encoding='utf-8'))
        self.assertTrue(hasattr(grammar, 'machine_format'), 'Grammar has no portable JSON export')
        data = json.loads(json.dumps(grammar.machine_format()))
        self.assertEqual(data['format'], 'eldude-grammar')
        self.assertEqual(data['entry_points'], {'source': 'source_file', 'interface': 'interface_file'})
        exported = Grammar('source_file ::= "placeholder";')
        exported.patterns = {item['name']: re.compile(item['pattern']) for item in data['lexical']['tokens']}
        exported.skips = {item['name']: re.compile(item['pattern']) for item in data['lexical']['skip']}
        exported.keywords = set(data['lexical']['reserved_words'])
        exported.bnf = {name: [tuple(symbol['rule'] if 'rule' in symbol else tuple(next(iter(symbol.items()))) for symbol in rhs) for rhs in options] for name, options in data['productions'].items()}
        source = 'module m; pub fn f(x:Int)->Int { x+1 }'
        interface = 'module m; pub fn f(x:T)->U; semantic { result-captures <= {captures(x)}; ffi-contract { parameter(0) { pointer { retention=call_scoped; } } } }'
        for entry, example in [('source_file', source), ('interface_file', interface)]:
            self.assertTrue(exported.accepts(example, entry))
            self.assertFalse(exported.accepts(example[:-1], entry))
        self.assertFalse(exported.accepts(interface, 'source_file'))

    def test_checker_rejects_stale_markdown_and_json(self):
        self.assertTrue(hasattr(check_grammar, 'FORMAL'), 'Standalone Markdown is not checked')
        self.assertTrue(hasattr(check_grammar, 'MACHINE'), 'Machine-readable grammar is not checked')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            grammar, spec = root/'eldude.ebnf', root/'spec.md'
            formal, machine = root/'formal.md', root/'eldude-grammar.json'
            grammar.write_text(check_grammar.GRAMMAR.read_text(encoding='utf-8'), encoding='utf-8')
            spec.write_text(check_grammar.SPEC.read_text(encoding='utf-8'), encoding='utf-8')
            with patch.multiple(check_grammar, GRAMMAR=grammar, SPEC=spec, FORMAL=formal, MACHINE=machine), contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys, 'argv', ['check_grammar.py', '--write']):
                    check_grammar.main()
                with patch.object(sys, 'argv', ['check_grammar.py']):
                    check_grammar.main()
                    for target in (formal, machine):
                        original = target.read_text(encoding='utf-8')
                        target.write_text(original+'stale\n', encoding='utf-8')
                        with self.assertRaisesRegex(SystemExit, 'stale'):
                            check_grammar.main()
                        target.write_text(original, encoding='utf-8')

if __name__ == '__main__':
    unittest.main()
