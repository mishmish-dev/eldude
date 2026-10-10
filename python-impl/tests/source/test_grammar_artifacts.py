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
from eldude.source import grammar as check_grammar
from eldude.source.grammar import Grammar

class ArtifactTests(unittest.TestCase):
    def test_checker_uses_utf8_in_c_locale(self):
        environment = dict(os.environ, LC_ALL='C', PYTHONUTF8='0', PYTHONCOERCECLOCALE='0', PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-m', 'eldude.source.grammar'], env=environment, capture_output=True, text=True, encoding='utf-8')
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
        interface = 'module m; pub struct Box<T>; semantic { representation=opaque; usage { Dup=(T:Dup); Discard=(T:Discard); } } pub fn f<T,U,!e>(x:(T,U))->{Store<T>,Store<T> | e} T; semantic { result-captures <= {captures(parameter(0))}; ffi-contract { parameter(0) { pointer { retention=call_scoped; } } } } pub fn push<T>(mut box:Box<T>,value:T)->Unit; semantic { result-captures <= {}; } impl<T> Iterator for Box<T> { type Item=T; fn next(self)->Next<Box<T>,T>; } semantic { finite-iteration=true; }'
        for entry, example in [('source_file', source), ('interface_file', interface)]:
            self.assertTrue(exported.accepts(example, entry))
            self.assertFalse(exported.accepts(example[:-1], entry))
        self.assertFalse(exported.accepts(interface, 'source_file'))

    def test_checker_rejects_stale_markdown_and_json(self):
        self.assertTrue(hasattr(check_grammar, 'FORMAL'), 'Standalone Markdown is not checked')
        self.assertTrue(hasattr(check_grammar, 'MACHINE'), 'Machine-readable grammar is not checked')
        self.assertTrue(hasattr(check_grammar, 'FOUNDATIONS'), 'Grammar generation must read the foundations chapter')
        self.assertTrue(hasattr(check_grammar, 'INTERFACES'), 'Grammar generation must read the interfaces chapter')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            grammar = root/'eldude.ebnf'
            formal, machine = root/'formal.md', root/'eldude-grammar.json'
            grammar.write_text(check_grammar.GRAMMAR.read_text(encoding='utf-8'), encoding='utf-8')
            (root/'language-spec').mkdir()
            sources = {}
            originals = {}
            for name in ('FOUNDATIONS', 'INTERFACES'):
                source = getattr(check_grammar, name)
                target = root/'language-spec'/source.name
                target.write_bytes(source.read_bytes())
                os.utime(target, (1, 1))
                sources[name] = target
                originals[target] = (target.read_bytes(), target.stat().st_mtime_ns)
            with patch.multiple(check_grammar, GRAMMAR=grammar, FORMAL=formal, MACHINE=machine, **sources), contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys, 'argv', ['check_grammar.py', '--write']):
                    check_grammar.main()
                for source, (content, mtime) in originals.items():
                    self.assertEqual(source.read_bytes(), content)
                    self.assertEqual(source.stat().st_mtime_ns, mtime)
                with patch.object(sys, 'argv', ['check_grammar.py']):
                    check_grammar.main()
                    for target in (formal, machine):
                        original = target.read_text(encoding='utf-8')
                        target.write_text(original+'stale\n', encoding='utf-8')
                        with self.assertRaisesRegex(SystemExit, 'stale'):
                            check_grammar.main()
                        target.write_text(original, encoding='utf-8')
                    for name, sentence in (
                        ('FOUNDATIONS', 'Source is UTF-8.'),
                        ('INTERFACES', 'A deterministic formatter is part of the standard toolchain.'),
                    ):
                        target = sources[name]
                        original = target.read_text(encoding='utf-8')
                        self.assertIn(sentence, original)
                        target.write_text(original.replace(sentence, sentence+' Changed source contract.'), encoding='utf-8')
                        with self.assertRaisesRegex(SystemExit, 'stale'):
                            check_grammar.main()
                        target.write_text(original, encoding='utf-8')

    def test_excerpt_links_resolve_from_publication_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'language-spec').mkdir()
            chapter = root/'language-spec'/'foundations.md'
            chapter.write_text(
                '### 2.8 Parsing\n\n'
                '[grammar](../eldude.ebnf), [local](#rule), '
                '[contracts](interfaces.md#72), [web](https://example.com/rules).\n\n'
                '### 2.9 Next\n\nNot part of the excerpt.\n', encoding='utf-8')
            with patch.object(check_grammar, 'FORMAL', root/'formal.md'):
                excerpt = check_grammar.section(chapter, '2.8')
            self.assertEqual(excerpt,
                '[grammar](eldude.ebnf), [local](language-spec/foundations.md#rule), '
                '[contracts](language-spec/interfaces.md#72), [web](https://example.com/rules).')

if __name__ == '__main__':
    unittest.main()
