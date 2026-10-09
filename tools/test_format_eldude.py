"""Syntax-directed layout, semantic contracts, and source round trips."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from handlers import run
from source_pipeline import compile_source
from source_syntax import Diagnostic, grammar
from format_eldude import format_source

ROOT = Path(__file__).resolve().parents[1]


class FormatterTests(unittest.TestCase):
    def layout(self, source):
        return format_source(source)

    def test_blocks_rows_and_operators_have_distinct_layout(self):
        source = ('module m;fn f<T,!e>(x:T,cb:fn(T)->{|e}Int)->{Log,Log|e}Int '
                  'where T:Dup+Discard {let n=cb(x);if n<0{-n}else{n+1}}')
        expected = '''module m;

fn f<T, !e>(x: T, cb: fn(T) ->{| e} Int) ->{Log, Log | e} Int where T: Dup + Discard {
    let n = cb(x);
    if n < 0 {
        -n
    } else {
        n + 1
    }
}
'''
        self.assertEqual(self.layout(source), expected)

    def test_full_grammar_literals_and_lexical_boundaries(self):
        source = ('module m;type X<T> = T;extern "C"{pub unsafe fn f(p:*const UInt8)->Int;}'
                  'let x=(1<2)==true;let s="// /* \\n";let c=\'é\';let n=1.25e-2f32;')
        result = self.layout(source)
        self.assertIn('type X<T> = T;', result)
        self.assertIn('p: *const UInt8', result)
        self.assertIn('(1 < 2) == true', result)
        self.assertEqual(grammar().lex(source, 'source_file'), grammar().lex(result, 'source_file'))
        self.assertEqual(self.layout(result), result)

    def test_extern_declarations_start_separate_lines_with_their_modifiers(self):
        source = 'module m; extern "C"{pub unsafe fn a()->Int;pub fn b()->Int;fn c()->Int;}'
        expected = '''module m;

extern "C" {
    pub unsafe fn a() -> Int;
    pub fn b() -> Int;
    fn c() -> Int;
}
'''
        self.assertEqual(self.layout(source), expected)

    def test_other_comma_delimited_forms_wrap_at_item_boundaries(self):
        sources = (
            'module m; fn f()->Unit{using(first_resource_owner=acquireFirstResource(),'
            'second_resource_owner=acquireSecondResource(),third_resource_owner=acquireThirdResource()) {}}',
            'module m; enum E {Case(FirstVeryLongTypeName,SecondVeryLongTypeName,'
            'ThirdVeryLongTypeName,FourthVeryLongTypeName)}',
            'module m; fn f()->Int{handle{42}with handler E{operation(first_long_parameter_name,'
            'second_long_parameter_name,third_long_parameter_name,fourth_long_parameter_name)=>42;}}',
        )
        for source in sources:
            with self.subTest(source=source):
                result = self.layout(source)
                self.assertTrue(all(len(line) <= 100 for line in result.splitlines()), result)
                self.assertEqual(self.layout(result), result)

    def test_comments_survive_at_token_boundaries(self):
        source = ('// header\r\nmodule m; // module\r\n'
                  'fn f()->Int{/* open */let x=1;// value\r\n'
                  '// standalone\r\nx/* result */} // end')
        result = self.layout(source)
        self.assertIn('module m; // module\n', result)
        self.assertIn('let x = 1; // value\n', result)
        self.assertIn('    // standalone\n    x /* result */', result)
        self.assertTrue(result.endswith('} // end\n'))
        self.assertEqual(self.layout(result), result)
        tokens = lambda text: [(t.kind, t.value) for t in grammar().lex_spanned(text, comments=True)]
        self.assertEqual(tokens(result), tokens(source))

    def test_block_comments_keep_standalone_lines_and_comment_only_bodies(self):
        source = '/* header */\nmodule m; fn f()->Unit {\n/* explanation */\n} '
        expected = '/* header */\nmodule m;\n\nfn f() -> Unit {\n    /* explanation */\n}\n'
        self.assertEqual(self.layout(source), expected)
        self.assertEqual(self.layout(expected), expected)

    def test_comments_inside_short_lists_force_indentation(self):
        source = 'module m; fn f(a:Int,// first\n b:Int)->Int{a+b}'
        expected = '''module m;

fn f(
    a: Int, // first
    b: Int
) -> Int {
    a + b
}
'''
        self.assertEqual(self.layout(source), expected)
        self.assertEqual(self.layout(expected), expected)

    def test_postfix_operators_do_not_merge_into_coalescing(self):
        self.assertIn('x? ? ?? 0', self.layout('module m; let result=x ? ? ?? 0;'))
        self.assertIn('Some(Int)', self.layout('module m; enum E {Some(Int)}'))

    def test_invalid_syntax_reports_locations(self):
        for source, line, column in (('module m;\n$', 2, 1),
                                     ('module m;\nfn f()->Int{', 2, 13)):
            with self.subTest(source=source), self.assertRaises(Diagnostic) as caught:
                format_source(source, 'broken.eld')
            self.assertEqual(caught.exception.code, 'syntax')
            self.assertEqual((caught.exception.span.filename, caught.exception.span.line,
                              caught.exception.span.column), ('broken.eld', line, column))

    def test_contracts_are_not_rewritten_and_do_not_require_import_resolution(self):
        source = ('module m;import missing::{Log};pub fn f<T,!e,..C>(cb:fn()->{Log|e}Int '
                  'captures {..C})->{Log,Log,diverge|e}Int where T:Discard+Dup,..C:Discard {42}')
        result = self.layout(source)
        self.assertIn('->{Log, Log, diverge | e} Int where T: Discard + Dup, ..C: Discard', result)
        self.assertEqual(grammar().lex(source, 'source_file'), grammar().lex(result, 'source_file'))

    def test_formatted_acceptance_programs_keep_results_and_event_order(self):
        expected = json.loads((ROOT / 'examples/manifest.json').read_text())['runnable']
        for name, value in expected.items():
            path = ROOT / 'examples' / name
            with self.subTest(example=name):
                source = path.read_text(encoding='utf-8')
                before = run(compile_source(source, str(path)).program)
                after = run(compile_source(format_source(source, str(path)), str(path)).program)
                self.assertEqual(after.value, value)
                self.assertEqual(after.events, before.events)

    def test_formatting_retains_ownership_lifetime_effect_and_constraint_diagnostics(self):
        from test_source_semantic_examples import executable_source
        cases = {
            'linear_discard': ('semantic', 'Unconsumed resource ticket'),
            'region_escape': ('semantic', 'region would escape'),
            'while_without_diverge': ('effect', 'declared effect row'),
            'trait_missing_prerequisite': ('semantic', 'Missing trait evidence'),
        }
        for name, (code, message) in cases.items():
            path = ROOT / 'examples/reject/semantics' / (name + '.eld')
            source = executable_source(path)
            for text in (source, format_source(source, str(path))):
                with self.subTest(example=name), self.assertRaises(Diagnostic) as caught:
                    compile_source(text, str(path))
                self.assertEqual(caught.exception.code, code)
                self.assertIn(message, caught.exception.message)

    def test_long_lists_break_at_existing_commas(self):
        source = ('module m;fn f(first_parameter:Int,second_parameter:Int,'
                  'third_parameter:Int,fourth_parameter:Int)->Int{first_parameter}')
        expected = '''module m;

fn f(
    first_parameter: Int,
    second_parameter: Int,
    third_parameter: Int,
    fourth_parameter: Int
) -> Int {
    first_parameter
}
'''
        self.assertEqual(self.layout(source), expected)

    def test_list_width_includes_indentation_at_the_start_of_a_line(self):
        for count in (32, 33):
            source = 'module m; fn f()->Unit {[' + ','.join('1' for _ in range(count)) + ']}'
            result = self.layout(source)
            with self.subTest(count=count):
                self.assertTrue(all(len(line) <= 100 for line in result.splitlines()), result)
                self.assertEqual('    [\n' in result, count == 33)
                self.assertEqual(self.layout(result), result)

    def test_layout_is_lossless_and_idempotent_across_source_corpus(self):
        paths = [p for directory in ('examples', 'stdlib') for p in (ROOT / directory).rglob('*.eld')
                 if 'syntax' not in p.parts]
        for path in sorted(paths):
            with self.subTest(path=str(path.relative_to(ROOT))):
                source = path.read_text(encoding='utf-8')
                result = self.layout(source)
                tokens = lambda text: [(t.kind, t.value) for t in grammar().lex_spanned(text, comments=True)]
                self.assertEqual(tokens(result), tokens(source))
                self.assertTrue(grammar().accepts(result))
                self.assertEqual(self.layout(result), result)


class FormatterCLITests(unittest.TestCase):
    source = 'module m;pub fn main()->Int{42}'
    formatted = 'module m;\n\npub fn main() -> Int {\n    42\n}\n'

    def cli(self, *args, source=None):
        return subprocess.run([sys.executable, str(ROOT / 'tools/format_eldude.py'), *map(str, args)],
                              input=source, capture_output=True, text=True, cwd=ROOT.parent)

    def test_stdin_and_file_stdout_leave_input_unchanged(self):
        result = self.cli(source=self.source)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, self.formatted, ''))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.eld'
            path.write_text(self.source)
            result = self.cli(path)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, self.formatted, ''))
            self.assertEqual(path.read_text(), self.source)

    def test_check_write_permissions_and_unchanged_file_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.eld'
            path.write_text(self.source)
            path.chmod(0o640)
            result = self.cli('--check', path)
            self.assertEqual(result.returncode, 1)
            self.assertIn(str(path), result.stdout)
            self.assertEqual(path.read_text(), self.source)
            result = self.cli('--write', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_text(), self.formatted)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            before = path.stat()
            self.assertEqual(self.cli('--write', path).returncode, 0)
            self.assertEqual((path.stat().st_ino, path.stat().st_mtime_ns), (before.st_ino, before.st_mtime_ns))
            result = self.cli('--check', path)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_write_validates_every_input_before_editing(self):
        with tempfile.TemporaryDirectory() as directory:
            good, bad = Path(directory) / 'good.eld', Path(directory) / 'bad.eld'
            good.write_text(self.source)
            bad.write_text('module bad; fn broken(')
            result = self.cli('--write', good, bad)
            self.assertEqual(result.returncode, 2)
            self.assertIn(f'{bad}:1:', result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(good.read_text(), self.source)
            self.assertEqual(bad.read_text(), 'module bad; fn broken(')

    def test_write_deduplicates_repeated_file_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.eld'
            path.write_text(self.source)
            alias = str(path.parent) + '/./' + path.name
            result = self.cli('--write', path, path, alias)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [str(path)])
            self.assertEqual(path.read_text(), self.formatted)

    def test_write_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            target, link = Path(directory) / 'target.eld', Path(directory) / 'link.eld'
            target.write_text(self.source)
            link.symlink_to(target)
            result = self.cli('--write', link)
            self.assertEqual(result.returncode, 2)
            self.assertIn('symlink', result.stderr)
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_text(), self.source)

    def test_atomic_replace_failure_and_stale_input_preserve_the_file(self):
        from format_eldude import write_file
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.eld'
            path.write_text(self.source)
            with patch('format_eldude.os.replace', side_effect=OSError('replacement failed')):
                with self.assertRaisesRegex(OSError, 'replacement failed'):
                    write_file(path, self.source.encode(), self.formatted.encode(), path.stat().st_mode)
            self.assertEqual(path.read_text(), self.source)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            with self.assertRaisesRegex(OSError, 'source changed'):
                write_file(path, b'stale contents', self.formatted.encode(), path.stat().st_mode)
            self.assertEqual(path.read_text(), self.source)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_errors_and_invalid_flag_combinations_are_nonzero(self):
        for args in (('--write', '-'), ('--write', '--check', 'missing.eld'),
                     ('a.eld', 'b.eld'), ('missing.eld',)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(result.stderr)
                self.assertEqual(result.stdout, '')
        result = self.cli(source='module m;\n$')
        self.assertEqual(result.returncode, 2)
        self.assertIn('<stdin>:2:1: syntax:', result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.eld'
            path.write_bytes(b'\xff')
            result = self.cli('--write', path)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(path.read_bytes(), b'\xff')

    def test_check_detects_crlf_and_write_normalizes_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'crlf.eld'
            path.write_bytes(self.formatted.replace('\n', '\r\n').encode())
            self.assertEqual(self.cli('--check', path).returncode, 1)
            self.assertEqual(self.cli('--write', path).returncode, 0)
            self.assertEqual(path.read_bytes(), self.formatted.encode())


if __name__ == '__main__':
    unittest.main()
