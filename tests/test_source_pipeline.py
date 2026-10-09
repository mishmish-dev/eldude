"""Public source API, annotations, entry conventions, and located diagnostics."""
import unittest

from eldude.effect_rows import Row
from eldude.handlers import run
from eldude.inference import INT, UNIT
from eldude.source_syntax import Diagnostic
from source_support import SourceAssertions


class LibraryCheckingTests(unittest.TestCase):
    def test_library_needs_no_entry_and_does_not_execute_initializers(self):
        from eldude.source_pipeline import check_source
        checked = check_source('module lib; let value: Int = 1 / 0; pub fn answer()->Int { value }')
        self.assertEqual(checked.inferred.type, UNIT)
        self.assertTrue(checked.functions)
        check_source('module empty;')

    def test_unused_and_generic_bodies_are_still_checked(self):
        from eldude.source_pipeline import check_source
        for body in ('fn unused()->Int { true }', 'fn unused<T>(x:T)->Int { true }'):
            with self.subTest(body=body), self.assertRaises(Diagnostic) as caught:
                check_source('module lib; ' + body)
            self.assertIn(caught.exception.code, ('type', 'semantic'))

    def test_library_effects_do_not_need_a_host(self):
        from eldude.source_pipeline import check_source
        check_source('module lib; pub effect Ask { tail ask()->Int; } '
                     'pub fn ask()->{Ask} Int { !Ask::ask() }')



class SourcePipelineTests(SourceAssertions, unittest.TestCase):
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
            ('module m; pub fn main()->Int { main() }', 'effect', 'Recursive.*diverge', 'pub fn main()->Int { main() }'),
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
        from eldude.source_syntax import grammar
        sources = [
            'module m; effect E{tail a(x:fn()->Int)->Int;} pub fn main()->Int {42}',
            'module m; fn externOnly()->Int; pub fn main()->Int {42}',
            'module m; pub fn main()->Int { let f=fn(x)=>x; f(42) }',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(grammar().accepts(source))
                with self.assertRaises(Diagnostic) as caught:
                    self.compile(source)
                self.assertEqual(caught.exception.code, 'unsupported')
                self.assertIn('Implementation limit', caught.exception.message)

    def test_new_source_forms_cross_the_old_subset_boundary(self):
        for source, expected in (
            ('module m; pub fn main()->Int { return 42; }', 42),
            ('module m; fn f<!e>()->{|e}Unit { () } pub fn main()->Unit { () }', None),
            ('module m; effect E<T>{tail value()->T;} pub fn main()->Int {42}', 42),
            ('module m; let global=42; pub fn main()->Int {global}', 42),
            ('module m; import core::result::{Result}; pub fn main()->Int {42}', 42),
        ):
            with self.subTest(source=source):
                self.assertEqual(self.execute(source).value, expected)
        with self.assertRaises(Diagnostic) as caught:
            self.compile('module m; pub fn main()->Unit { while true {} }')
        self.assertNotEqual(caught.exception.code, 'unsupported')

    def test_int_literal_range_and_spellings(self):
        for literal in ('42', '4_2int', '42i64', '0x2a', '0b101010', '0o52', '+42'):
            with self.subTest(literal=literal):
                self.assertEqual(self.execute('module m; pub fn main()->Int { '+literal+' }').value, 42)
        self.assertEqual(self.execute('module m; pub fn main()->Int { -(9223372036854775808) }').value,
                         -9223372036854775808)
        self.reject('module m; pub fn main()->Int { 9223372036854775808 }',
                    'type', 'Int64 range', '9223372036854775808')

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



if __name__ == '__main__':
    unittest.main()
