"""Check and execute actual source; expected results do not come from IR builders."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from effect_rows import Row
from inference import INT, UNIT
from handlers import run
from source_syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'examples/07_source_pipeline'
REJECT = ROOT / 'examples/reject/semantics/source_pipeline'


class SourcePipelineTests(unittest.TestCase):
    def compile(self, source):
        from source_pipeline import compile_source
        return compile_source(source, 'test.eld')

    def execute(self, source):
        return run(self.compile(source).program)

    def reject(self, source, code, message, at):
        with self.assertRaises(Diagnostic) as caught:
            self.compile(source)
        diagnostic = caught.exception
        self.assertEqual(diagnostic.code, code, str(diagnostic))
        self.assertRegex(diagnostic.message, message)
        self.assertEqual(source[diagnostic.span.start:diagnostic.span.end], at)
        return diagnostic

    def test_scalar_functions_forward_references_and_calls_execute_bodies(self):
        source = '''module m;
pub fn main()->Int { identity(answer()) }
fn identity(value:Int)->Int { value }
fn answer()->Int { 42 }
'''
        checked = self.compile(source)
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertEqual(run(checked.program).value, 42)

    def test_closure_bodies_and_computed_calls(self):
        self.assertEqual(self.execute('''module m;
pub fn main()->Int {
    let captured = 42;
    let get = fn()->Int { captured };
    (fn(f:fn()->Int) => f)(get)()
}''').value, 42)

    def test_semicolon_makes_unit_and_block_bindings_do_not_escape(self):
        self.assertIsNone(self.execute('module m; pub fn main()->Unit { 42; }').value)
        self.reject('module m; pub fn main()->Int { { let x=1; }; x }',
                    'name', 'Unknown value', 'x')

    def test_annotations_and_unused_functions_are_checked(self):
        self.reject('module m; pub fn main()->Int { 42 } fn bad()->Unit { 1 }',
                    'type', 'Type mismatch', '1')
        self.reject('module m; pub fn main()->Int { let x:Unit=1; 42 }',
                    'type', 'Type mismatch', '1')
        self.reject('module m; fn f(x:Unit)->Int { 1 } pub fn main()->Int { f(2) }',
                    'type', 'Type mismatch', 'f(2)')

    def test_effect_annotations_are_admitted_contracts(self):
        self.reject('''module m;
effect Read { tail value()->Int; }
pub fn main()->Int { !Read::value() }''', 'effect', 'Effect mismatch', '!Read::value()')
        self.reject('''module m;
import eldude::fixture::{acquire, close};
fn maySuspend()->{suspend} Unit { () }
pub fn main()->{suspend} Unit {
    let file=acquire(); maySuspend(); close(file)
}''', 'semantic', 'abandon.*file', 'maySuspend()')

    def test_no_implicit_fixture_prelude_or_magic_user_functions(self):
        self.reject('module m; pub fn main()->Unit { yield() }', 'name', 'Unknown value', 'yield')
        self.assertEqual(self.execute('module m; fn acquire()->Int { 9 } pub fn main()->Int { acquire() }').value, 9)

    def test_fixture_import_aliases_and_resource_cleanup(self):
        result = self.execute('''module m;
import eldude::fixture::{acquire as open, close as finish, File};
fn release(file:File)->Unit { finish(file) }
pub fn main()->Int { let file:File=open(); release(file); 42 }
''')
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('acquire', 'File', 1), ('close', 1, 'explicit')))

    def test_duplicate_declarations_unknown_types_and_recursion(self):
        for source, code, message, at in (
            ('module m; fn f()->Int { 1 } fn f()->Int { 2 } pub fn main()->Int { 3 }', 'name', 'Duplicate', 'f'),
            ('module m; pub fn main()->Missing { 1 }', 'name', 'Unknown type', 'Missing'),
            ('module m; pub fn main()->Int { main() }', 'unsupported', 'recursion', 'main'),
        ):
            with self.subTest(source=source):
                self.reject(source, code, message, at)

    def test_nested_function_result_keeps_declared_effects(self):
        self.reject('''module m;
import eldude::fixture::{acquire, close};
fn callback()->fn()->{suspend} Unit { fn()=>() }
pub fn main()->{suspend} Unit {
    let f=callback();
    let file=acquire(); f(); close(file)
}''', 'semantic', 'abandon.*file', 'f()')

    def test_multiple_using_acquisitions_cleanup_in_reverse_order(self):
        result = self.execute('''module m;
import eldude::fixture::{acquire, close};
pub fn main()->Int {
    using(a=acquire(), b=acquire(), c=acquire()) { close(b); 42 }
}''')
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('acquire', 'File', 2), ('acquire', 'File', 3),
            ('close', 2, 'explicit'), ('close', 3, 'cleanup'), ('close', 1, 'cleanup')))

    def test_binding_annotation_does_not_replace_inner_function_contract(self):
        self.reject('''module m;
import eldude::fixture::{yield};
pub fn main()->Unit {
    let callback:fn()->{suspend} Unit = fn()->Unit { yield() };
    ()
}''', 'effect', 'Effect mismatch', 'yield()')

    def test_qualified_function_name_ignores_local_shadow(self):
        self.assertEqual(self.execute('''module m;
fn answer()->Int { 42 }
pub fn main()->Int { let answer=fn()=>1; m::answer() }
''').value, 42)

    def test_handler_and_value_shadowing_keep_binding_identity(self):
        result = self.execute('''module m;
effect Read { tail value()->Int; }
pub fn main()->Int {
    let answer=42;
    let get=fn()=>answer;
    let answer=0;
    handle {
        let fixed=fn()=>!h::value();
        handle { fixed(); !h::value() } with h=handler Read { value()=>get(); }
    } with h=handler Read { value()=>10; }
}''')
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('dispatch', 'Read', 'h'), ('resume', 'h', 10),
                                         ('dispatch', 'Read', 'h'), ('resume', 'h', 42)))

    def test_ownership_shadowing_does_not_hide_live_outer_obligation(self):
        diagnostic = self.reject('''module m;
import eldude::fixture::{acquire, close, yield};
pub fn main()->{suspend} Unit {
    let file=acquire();
    { let file=(); yield(); };
    close(file)
}''', 'semantic', 'abandon live resource file', 'yield()')
        self.assertEqual(diagnostic.related[0][1].line, 4)

    def test_owned_argument_temporary_is_checked_at_later_argument(self):
        self.reject('''module m;
import eldude::fixture::{acquire, close, yield, File};
fn consume(file:File, ignored:Unit)->Unit { close(file) }
pub fn main()->{suspend} Unit { consume(acquire(), yield()) }
''', 'semantic', 'argument temporary', 'yield()')

    def test_named_dispatch_and_handler_completeness(self):
        cases = (
            ('!unknown::value()', 'Unknown effect or handler instance'),
            ('!Read::missing()', 'Unknown operation'),
        )
        for call, message in cases:
            with self.subTest(call=call):
                self.reject('module m; effect Read { tail value()->Int; } pub fn main()->Int { '+call+' }',
                            'name', message, call[1:-2])
        self.reject('''module m;
effect Read { tail value()->Int; }
pub fn main()->Int { handle { 42 } with handler Read { } }
''', 'semantic', 'Incomplete handler', 'Read')
        self.reject('''module m;
effect Read { tail value()->Int; }
pub fn main()->Int {
    handle { !Read::value() } with h=handler Read { value()=>!h::value(); }
}''', 'name', 'Unknown effect or handler instance h', 'h::value')

    def test_fixture_type_and_host_contracts(self):
        self.reject('''module m; import eldude::fixture::{close};
pub fn main()->Unit { close(1) }''', 'type', 'Type mismatch', 'close(1)')
        self.reject('''module m; import eldude::fixture::{acquire};
pub fn main()->Unit { acquire(1); }''', 'type', 'arity', 'acquire(1)')
        self.reject('''module m; import eldude::fixture::{acquire};
pub fn main()->Unit { let _=acquire(); }''', 'semantic', 'discard', 'acquire()')
        result = self.execute('''module m;
import eldude::fixture::{acquireAsync, closeAsync, yield};
pub fn main()->{suspend} Int {
    using(file=acquireAsync()) { yield(); closeAsync(file); 42 }
}''')
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('acquire', 'AsyncFile', 1), ('suspend', False),
                                         ('suspend', False), ('close', 1, 'explicit')))

    def test_valid_broader_syntax_is_always_an_explicit_limit(self):
        from source_syntax import grammar
        sources = [
            'module m; pub fn main()->Int { return 42; }',
            'module m; fn f<!e>()->{|e}Unit { () } pub fn main()->Unit { () }',
            'module m; effect E<T>{tail value()->T;} pub fn main()->Int {42}',
            'module m; effect E{tail a()->Int;tail b()->Int;} pub fn main()->Int {42}',
            'module m; effect E{tail a(x:Int)->Int;} pub fn main()->Int {42}',
            'module m; let global=42; pub fn main()->Int {global}',
            'module m; fn externOnly()->Int; pub fn main()->Int {42}',
            'module m; pub fn main()->Int { let f=fn(x)=>x; f(42) }',
            'module m; pub fn main()->Unit { while true {} }',
            'module m; import core::result::{Result}; pub fn main()->Int {42}',
            'module m; pub fn main()->Int { let pair=(1,2); 42 }',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(grammar().accepts(source))
                with self.assertRaises(Diagnostic) as caught:
                    self.compile(source)
                self.assertEqual(caught.exception.code, 'unsupported')
                self.assertIn('Implementation limit', caught.exception.message)

    def test_int_literal_range_and_spellings(self):
        for literal in ('42', '4_2int', '42i64', '0x2a', '0b101010', '0o52', '+42'):
            with self.subTest(literal=literal):
                self.assertEqual(self.execute('module m; pub fn main()->Int { '+literal+' }').value, 42)
        self.assertEqual(self.execute('module m; pub fn main()->Int { -(9223372036854775808) }').value,
                         -9223372036854775808)
        self.reject('module m; pub fn main()->Int { 9223372036854775808 }',
                    'type', 'Int64 range', '9223372036854775808')

    def test_handler_scalar_restrictions_and_known_primitive_limits(self):
        for source in (
            'module m; effect R{tail get()->Int;} pub fn main()->Int {let f=handle {fn()=>42} with handler R{get()=>1;};f()}',
            'module m; effect R{tail get()->Int;} pub fn main()->Int {let f=handle {42} with handler R{get()=>1;return x=>fn()=>x;};f()}',
            'module m; fn f(x:UInt8)->Unit {()} pub fn main()->Unit {()}',
        ):
            with self.subTest(source=source), self.assertRaises(Diagnostic) as caught:
                self.compile(source)
            self.assertEqual(caught.exception.code, 'unsupported')
            self.assertIn('Implementation limit', caught.exception.message)

    def test_normal_return_clause_rejects_unqualified_same_family(self):
        self.reject('''module m;
effect Read {tail value()->Int;}
pub fn main()->Int {
    handle {
        handle {1} with handler Read {value()=>1; return x=>!Read::value();}
    } with handler Read {value()=>42;}
}''', 'semantic', 'unqualified same-family', '!Read::value()')

    def test_source_call_arity_is_a_type_error(self):
        self.reject('module m; fn f(x:Int)->Int {x} pub fn main()->Int {f()}',
                    'type', 'arity', 'f()')

    def test_public_contract_cannot_expose_private_effect(self):
        self.reject('''module m;
effect Read {tail value()->Int;}
pub fn exported()->{Read}Int {!Read::value()}
pub fn main()->Int {42}
''', 'name', 'Public contract.*private effect', 'Read')

    def test_unhandled_root_effect_points_at_operation(self):
        self.reject('module m; pub effect Read{tail value()->Int;} pub fn main()->{Read}Int {!Read::value()}',
                    'effect', 'unhandled', '!Read::value()')

    def test_higher_order_and_returned_closures_keep_fixed_evidence(self):
        result = self.execute('''module m;
effect Read {tail value()->Int;}
pub fn main()->Int {
    handle {
        let make = fn()=>fn()=>!outer::value();
        let invoke = fn(f:fn()->{Read}Int)=>f();
        let fixed = make();
        handle { invoke(fn()=>!Read::value()); fixed() }
            with handler Read {value()=>20;}
    } with outer=handler Read {value()=>10;}
}''')
        self.assertEqual(result.value, 10)
        self.assertEqual([e for e in result.events if e[0] == 'dispatch'],
                         [('dispatch', 'Read', 'Read'), ('dispatch', 'Read', 'outer')])

    def test_enclosing_resume_in_nested_return_is_an_explicit_limit(self):
        self.reject('''module m;
effect A {once a()->Unit;}
effect B {tail b()->Unit;}
pub fn main()->Unit {
    handle {!A::a()} with handler A {
        a()=>handle {()} with handler B {b()=>(); return x=>resume(());};
    }
}''', 'unsupported', 'Implementation limit:.*nested normal-return', 'resume(())')


class SourceFixtureTests(unittest.TestCase):
    def fixture(self, name):
        from source_pipeline import compile_file
        return compile_file(FIXTURES / (name + '.eld'))

    def test_existing_literal_and_source_functions(self):
        from source_pipeline import execute_file
        self.assertEqual(execute_file(ROOT / 'examples/01_values/literal.eld').value, 42)
        self.assertEqual(run(self.fixture('functions').program).value, 42)

    def test_tail_cleanup_precedes_resumption(self):
        result = run(self.fixture('tail_cleanup').program)
        self.assertEqual(result.value, 40)
        self.assertEqual(result.events, (
            ('dispatch', 'Read', 'read'), ('acquire', 'File', 1),
            ('close', 1, 'cleanup'), ('resume', 'read', 40),
            ('acquire', 'File', 2), ('close', 2, 'explicit')))
        output = self.fixture('tail_output')
        self.assertEqual(output.inferred.type, UNIT)
        self.assertEqual(run(output.program).events,
                         (('dispatch', 'Read', 'read'), ('resume', 'read', 40)))

    def test_deep_once_moves_and_closes_one_frame_obligation(self):
        result = run(self.fixture('once_deep').program)
        self.assertEqual(result.value, 99)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'), ('resume', 'step', None),
            ('dispatch', 'Step', 'step'), ('resume', 'step', None), ('close', 1, 'explicit')))

    def test_clause_local_resource_survives_resume(self):
        result = run(self.fixture('clause_local').program)
        self.assertIsNone(result.value)
        self.assertEqual(result.events, (
            ('dispatch', 'Step', 'step'), ('acquire', 'File', 1),
            ('resume', 'step', None), ('close', 1, 'explicit')))

    def test_affine_abandonment_preserves_outside_and_masks_async_cleanup(self):
        result = run(self.fixture('affine_scope').program)
        self.assertEqual(result.value, 7)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('acquire', 'File', 2), ('acquire', 'File', 3),
            ('dispatch', 'Stop', 'stop'), ('close', 2, 'explicit'), ('abandon', 'stop'),
            ('close', 3, 'cleanup'), ('close', 1, 'explicit')))
        checked = self.fixture('affine_async')
        self.assertEqual(checked.inferred.effects, Row(('suspend',)))
        self.assertEqual(run(checked.program).events, (
            ('acquire', 'AsyncFile', 1), ('dispatch', 'Stop', 'stop'), ('abandon', 'stop'),
            ('suspend', True), ('close', 1, 'cleanup')))

    def test_forwarding_retains_outer_slot_and_callbacks_choose_evidence(self):
        checked = self.fixture('forwarding')
        self.assertEqual(checked.inferred.effects, Row())
        self.assertEqual(len(checked.handled_rows['inner'].labels), 1)
        self.assertIn('outer', checked.handled_rows['inner'].labels[0])
        self.assertEqual(run(checked.program).value, 42)
        self.assertEqual(run(checked.program).events, (
            ('dispatch', 'Read', 'inner'), ('dispatch', 'Read', 'outer'),
            ('resume', 'outer', 42), ('resume', 'inner', 42)))
        result = run(self.fixture('callbacks').program)
        self.assertEqual(result.value, 20)
        self.assertEqual([e for e in result.events if e[0] == 'dispatch'],
                         [('dispatch', 'Read', 'outer'), ('dispatch', 'Read', 'inner')])

    def test_combined_nested_handlers_forward_resume_and_cleanup(self):
        checked = self.fixture('combined')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertTrue(checked.program.origins)
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('acquire', 'File', 2),
            ('dispatch', 'Step', 'step'), ('resume', 'step', None),
            ('dispatch', 'Step', 'step'), ('resume', 'step', None),
            ('dispatch', 'Read', 'inner'), ('dispatch', 'Read', 'outer'),
            ('acquire', 'File', 3), ('close', 3, 'cleanup'),
            ('resume', 'outer', 42), ('resume', 'inner', 42),
            ('close', 1, 'explicit'), ('acquire', 'File', 4), ('close', 4, 'cleanup'),
            ('acquire', 'File', 5), ('close', 5, 'cleanup'), ('close', 2, 'cleanup')))

    def test_unsafe_source_fixtures_are_static_located_rejections(self):
        from source_pipeline import compile_file
        from source_syntax import grammar
        cases = {
            'wrong_operation_result': ('operation result', 5, 20),
            'tail_resume': ('Explicit resume.*tail', 5, 20),
            'missing_resume': ('once clause must resume exactly once', 5, 19),
            'repeated_resume': ('more than once', 7, 13),
            'escaping_resume': ('resume.*only inside an operation clause', 6, 33),
            'frame_transfer': ('file was already consumed', 9, 19),
            'clause_local': ('Unconsumed resource local', 7, 13),
            'unsafe_affine': ('abandon live resource file', 7, 9),
            'skipped_outer_resume': ('skip an enclosing resume', 7, 13),
            'skipped_consumption': ('skip consumption of file', 7, 9),
            'outward_pending': ('abandon live resource file', 12, 25),
            'deep_residual': ('abandon live resource local', 10, 17),
            'post_resume': ('abandon live resource file', 9, 37),
            'same_family': ('unqualified same-family', 5, 20),
        }
        self.assertEqual(set(cases), {p.stem for p in REJECT.glob('*.eld')})
        for name, (message, line, column) in cases.items():
            path = REJECT / (name + '.eld')
            with self.subTest(name=name):
                self.assertTrue(grammar().accepts(path.read_text(encoding='utf-8')))
                # Compile only. A runtime leak assertion cannot satisfy this test.
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                diagnostic = caught.exception
                self.assertEqual(diagnostic.code, 'semantic', str(diagnostic))
                self.assertRegex(diagnostic.message, message)
                self.assertEqual((diagnostic.span.filename, diagnostic.span.line, diagnostic.span.column),
                                 (str(path), line, column))
                if name in ('frame_transfer', 'unsafe_affine', 'post_resume', 'deep_residual'):
                    self.assertTrue(diagnostic.related)
                if name == 'frame_transfer':
                    self.assertEqual([span.line for _, span in diagnostic.related], [5, 8])

    def test_cli_success_syntax_semantic_and_unsupported_failure(self):
        cases = (
            (FIXTURES / 'combined.eld', 0, '42\n', ''),
            (ROOT / 'examples/reject/syntax/source_pipeline/missing_semicolon.eld', 1, '', ':syntax:'),
            (REJECT / 'tail_resume.eld', 1, '', ':semantic:'),
            (FIXTURES / 'unsupported/branch.eld', 1, '', ':unsupported:'),
        )
        for path, status, stdout, category in cases:
            with self.subTest(path=path):
                result = subprocess.run([sys.executable, str(ROOT / 'tools/run_eldude.py'), str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(result.stdout, stdout)
                if category:
                    self.assertIn(category, result.stderr.replace(' ', ''))
                    self.assertIn(str(path) + ':', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                else:
                    self.assertEqual(result.stderr, '')

    def test_cli_reports_unknown_names_and_annotation_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.eld'
            for source, category in (
                ('module m; pub fn main()->Int { missing() }', 'name'),
                ('module m; pub fn main()->Int { () }', 'type'),
            ):
                with self.subTest(category=category):
                    path.write_text(source, encoding='utf-8')
                    result = subprocess.run([sys.executable, str(ROOT / 'tools/run_eldude.py'), str(path)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, '')
                    self.assertIn(f'{path}:1:', result.stderr)
                    self.assertIn(f': {category}:', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
