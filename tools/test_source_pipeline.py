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
MULTI_REJECT = ROOT / 'examples/reject/semantics/multi_operations'
MULTI_FAILURES = {
    'incomplete': ('semantic', 'Incomplete handler.*stop'),
    'duplicate_declaration': ('name', 'Duplicate operation declaration'),
    'duplicate_clause': ('name', 'Duplicate handler operation'),
    'duplicate_forward': ('name', 'Duplicate handler operation'),
    'duplicate_fallback': ('name', 'Duplicate forwarding clause'),
    'unknown_clause': ('name', 'Unknown handler operation'),
    'unknown_forward': ('name', 'Unknown handler operation'),
    'unknown_call': ('name', 'Unknown operation'),
    'call_arity': ('type', 'Operation arity'),
    'clause_arity': ('type', 'Operation clause arity'),
    'argument_type': ('type', 'Type mismatch'),
    'tail_result': ('semantic', 'operation result'),
    'once_result': ('semantic', 'operation result'),
    'affine_result': ('semantic', 'handler output'),
    'same_family_sibling': ('semantic', 'unqualified same-family'),
    'tail_resume': ('semantic', 'Explicit resume.*tail'),
    'missing_resume': ('semantic', 'once clause must resume exactly once'),
    'repeated_resume': ('semantic', 'more than once'),
    'escaping_resume': ('semantic', 'resume.*only inside an operation clause'),
    'frame_transfer': ('semantic', 'frame was already consumed'),
    'clause_local': ('semantic', 'Unconsumed resource local'),
    'unsafe_affine': ('semantic', 'abandon live resource file'),
    'skipped_consumption': ('semantic', 'skip consumption of outside'),
    'skipped_enclosing_resume': ('semantic', 'skip an enclosing resume'),
    'post_resume_outward': ('semantic', 'abandon live resource outside'),
    'opaque_affine_family': ('semantic', 'abandon live resource file'),
    'argument_effect': ('effect', 'exceeds its declared effect row'),
    'argument_abandonment': ('semantic', 'abandon live resource file'),
    'sibling_residual': ('semantic', 'abandon live resource local'),
}


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

    def test_empty_family_and_handler(self):
        result = self.execute('module m; effect Empty {} pub fn main()->Int {handle {42} with handler Empty {}}')
        self.assertEqual((result.value, result.events), (42, ()))

    def test_multiple_operations_share_one_admitted_family_slot(self):
        checked = self.compile('''module m;
effect E {tail a()->Int; once b()->Unit;}
fn request()->{E}Int {!E::b(); !E::a()}
pub fn main()->Int {handle {request()} with handler E {b()=>resume(()); a()=>42;}}
''')
        self.assertEqual(checked.functions['request'].effects, Row(('E',)))
        self.assertEqual(checked.inferred.effects, Row())
        self.assertEqual(run(checked.program).value, 42)

    def test_operation_spelling_is_scoped_to_its_family(self):
        result = self.execute('''module m;
effect A {tail get(x:Int)->Int; once tick()->Unit;}
effect B {once get(x:Unit)->Unit; tail tick()->Int;}
pub fn main()->Int {
    handle {
        handle {!B::get(()); !A::tick(); !A::get(!B::tick())}
            with handler B {tick()=>42; get(x)=>resume(x);}
    } with handler A {get(x)=>x; tick()=>resume(());}
}''')
        self.assertEqual(result.value, 42)
        self.assertEqual([e for e in result.events if e[0]=='dispatch'], [
            ('dispatch', 'B', 'B', 'get'), ('dispatch', 'A', 'A', 'tick'),
            ('dispatch', 'B', 'B', 'tick'), ('dispatch', 'A', 'A', 'get')])

    def test_selective_forwarding_keeps_arguments_callbacks_and_outer_slot(self):
        source = '''module m;
import eldude::fixture::{acquire};
effect Multi {tail read(first:Int, second:Int)->Int; once step()->Unit; tail mark(x:Int)->Int;}
pub fn main()->Int {
    handle {
        let fixed=fn()=>!outer::mark(7);
        let ambient=fn()=>!Multi::mark(42);
        handle {
            !Multi::step();
            !Multi::read(using(a=acquire()){fixed()}, using(b=acquire()){ambient()})
        } with inner=handler Multi {
            forward read;
            forward ..;
            step()=>resume(());
        }
    } with outer=handler Multi {mark(x)=>x; read(a,b)=>b; step()=>resume(());}
}'''
        # Declaration and fallback position must not affect resolution.
        for text in (source, source.replace('tail read(first:Int, second:Int)->Int; once step()->Unit; tail mark(x:Int)->Int;',
                                           'tail mark(x:Int)->Int; once step()->Unit; tail read(first:Int, second:Int)->Int;')):
            with self.subTest(source=text):
                checked = self.compile(text)
                self.assertEqual(checked.inferred.effects, Row())
                self.assertEqual(len(checked.handled_rows['inner'].labels), 1)
                self.assertIn('outer', checked.handled_rows['inner'].labels[0])
                result = run(checked.program)
                self.assertEqual(result.value, 42)
                self.assertEqual(result.events, (
                    ('dispatch', 'Multi', 'inner', 'step'), ('resume', 'inner', None),
                    ('acquire', 'File', 1), ('dispatch', 'Multi', 'outer', 'mark'),
                    ('resume', 'outer', 7), ('close', 1, 'cleanup'),
                    ('acquire', 'File', 2), ('dispatch', 'Multi', 'inner', 'mark'),
                    ('dispatch', 'Multi', 'outer', 'mark'), ('resume', 'outer', 42),
                    ('resume', 'inner', 42), ('close', 2, 'cleanup'),
                    ('dispatch', 'Multi', 'inner', 'read'), ('dispatch', 'Multi', 'outer', 'read'),
                    ('resume', 'outer', 42), ('resume', 'inner', 42)))

    def test_clause_can_name_outer_instance_for_a_different_operation(self):
        result = self.execute('''module m;
effect E {tail read(x:Int)->Int; tail other(x:Int)->Int;}
pub fn main()->Int {
    handle {
        handle {!E::read(42)} with handler E {read(x)=>!outer::other(x); other(x)=>x;}
    } with outer=handler E {read(x)=>0; other(x)=>x;}
}''')
        self.assertEqual(result.value, 42)
        self.assertEqual([e for e in result.events if e[0]=='dispatch'], [
            ('dispatch', 'E', 'E', 'read'), ('dispatch', 'E', 'outer', 'other')])

    def test_multi_operation_argument_and_sibling_clause_effect_origins(self):
        for body in ('!E::read(!Other::get())',
                     'handle {42} with handler E {step()=>resume(()); read(x)=>!Other::get();}'):
            self.reject('''module m;
effect E {tail read(x:Int)->Int; once step()->Unit;}
effect Other {tail get()->Int;}
fn bad()->{E}Int {'''+body+'''}
pub fn main()->Int {42}
''', 'effect', 'exceeds its declared effect row', '!Other::get()')

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

    def test_operation_arguments_evaluate_once_left_to_right_before_dispatch(self):
        result = self.execute('''module m;
import eldude::fixture::{acquire};
effect Pick {tail pick(first:Int, second:Int)->Int;}
effect Mark {tail mark(value:Int)->Int;}
pub fn main()->Int {
    handle {
        handle {
            !Pick::pick(using(first=acquire()){!Mark::mark(7)},
                        using(second=acquire()){!Mark::mark(42)})
        } with handler Pick {pick(first, second)=>second;}
    } with handler Mark {mark(value)=>value;}
}''')
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Mark', 'Mark'),
            ('resume', 'Mark', 7), ('close', 1, 'cleanup'),
            ('acquire', 'File', 2), ('dispatch', 'Mark', 'Mark'),
            ('resume', 'Mark', 42), ('close', 2, 'cleanup'),
            ('dispatch', 'Pick', 'Pick'), ('resume', 'Pick', 42)))

    def test_argument_callbacks_capture_values_and_select_fixed_or_ambient_evidence(self):
        result = self.execute('''module m;
effect Echo {tail echo(value:Int)->Int;}
pub fn main()->Int {
    handle {
        let seed=42;
        let fixed=fn()=>!outer::echo(seed);
        let ambient=fn()=>!Echo::echo(seed);
        handle {fixed(); ambient()} with inner=handler Echo {echo(value)=>20;}
    } with outer=handler Echo {echo(value)=>value;}
}''')
        self.assertEqual(result.value, 20)
        self.assertEqual(result.events, (('dispatch', 'Echo', 'outer'), ('resume', 'outer', 42),
                                        ('dispatch', 'Echo', 'inner'), ('resume', 'inner', 20)))

    def test_affine_argument_clause_can_abandon_and_once_can_reuse_its_scalar_parameter(self):
        template = '''module m;
import eldude::fixture::{acquire};
effect Choose {MODE choose(value:Int)->Int;}
pub fn main()->Int {
    handle {using(file=acquire()){!Choose::choose(42)}} with handler Choose {
        choose(value)=>BODY;
    }
}'''
        for mode, body, control in (
            ('tail', 'value', ('resume', 'Choose', 42)),
            ('once', '{resume(value); value}', ('resume', 'Choose', 42)),
            ('affine', 'value', ('abandon', 'Choose')),
        ):
            with self.subTest(mode=mode):
                result = self.execute(template.replace('MODE', mode).replace('BODY', body))
                self.assertEqual(result.value, 42)
                self.assertEqual(result.events, (('acquire', 'File', 1), ('dispatch', 'Choose', 'Choose'),
                                                control, ('close', 1, 'cleanup')))

    def test_operation_parameters_validate_names_scope_and_supported_types(self):
        cases = (
            ('effect E{tail op(x:Int,x:Unit)->Int;}', 'handle {42} with handler E {op(a,b)=>42;}',
             'name', 'Duplicate operation parameter', 'x'),
            ('effect E{tail op(x:Int,y:Unit)->Int;}', 'handle {42} with handler E {op(a,a)=>42;}',
             'name', 'Duplicate operation clause parameter', 'a'),
            ('effect E{tail op(x:Int)->Int;}', 'handle {42} with handler E {op(x)=>x; return y=>x;}',
             'name', 'Unknown value x', 'x'),
            ('effect E{tail op(x:Int)->Int;}', 'handle {42} with handler E {op(x)=>!E::op(x);}',
             'semantic', 'unqualified same-family', '!E::op(x)'),
            ('effect E{tail op(x:File)->Int;}', '42',
             'unsupported', 'operation parameters must currently be scalar data', 'File'),
            ('effect E{tail op(x:Missing)->Int;}', '42',
             'name', 'Unknown type Missing', 'Missing'),
        )
        for declaration, body, code, message, at in cases:
            with self.subTest(declaration=declaration, body=body):
                self.reject('module m; import eldude::fixture::{File}; '+declaration+
                            ' pub fn main()->Int {'+body+'}', code, message, at)
        result = self.execute('''module m;
effect E {tail op(_:Int, _:Unit)->Int;}
pub fn main()->Int {handle {!E::op(7,())} with handler E {op(_,_)=>42;}}
''')
        self.assertEqual(result.value, 42)

    def test_operation_argument_effects_are_part_of_the_source_contract(self):
        self.reject('''module m;
effect Echo {tail echo(value:Int)->Int;}
effect Read {tail value()->Int;}
fn bad()->{Echo}Int {!Echo::echo(!Read::value())}
pub fn main()->Int {42}
''', 'effect', 'exceeds its declared effect row', '!Read::value()')
        self.reject('''module m;
effect Echo {tail echo(value:Int)->Int;}
effect Read {tail value()->Int;}
fn bad()->Int {
    handle {!Echo::echo(42)} with handler Echo {echo(value)=>!Read::value();}
}
pub fn main()->Int {42}
''', 'effect', 'exceeds its declared effect row', '!Read::value()')

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

    def test_nested_return_resumes_the_lexically_enclosing_operation(self):
        source = '''module m;
effect A {MODE a()->Unit;}
effect B {once b()->Int;}
pub fn main()->Unit {
    handle {!A::a()} with handler A {
        a()=>handle {!B::b()} with handler B {b()=>resume(7); return x=>resume(());};
    }
}'''
        for mode in ('once', 'affine'):
            with self.subTest(mode=mode):
                result = self.execute(source.replace('MODE', mode))
                self.assertIsNone(result.value)
                self.assertEqual(result.events, (
                    ('dispatch', 'A', 'A'), ('dispatch', 'B', 'B'),
                    ('resume', 'B', 7), ('resume', 'A', None)))

    def test_nested_return_transfers_frame_before_outward_effects(self):
        result = self.execute('''module m;
import eldude::fixture::{acquire, close};
effect Step {once step()->Unit;}
effect Read {tail value()->Int;}
effect Stop {affine stop()->Unit;}
pub fn main()->Unit {
    handle {
        let frame = acquire();
        handle {!Step::step()} with handler Step {
            step()=>handle {!Read::value()} with handler Read {
                value()=>7;
                return x=>resume(());
            };
            return x=>{close(frame); !Stop::stop()};
        }
    } with handler Stop {stop()=>();}
}''')
        self.assertIsNone(result.value)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'Step'),
            ('dispatch', 'Read', 'Read'), ('resume', 'Read', 7),
            ('resume', 'Step', None), ('close', 1, 'explicit'),
            ('dispatch', 'Stop', 'Stop'), ('abandon', 'Stop')))

    def test_nested_returns_keep_one_capability_across_multiple_delimiters(self):
        result = self.execute('''module m;
effect A {once a()->Unit;}
effect B {tail b()->Int;}
pub fn main()->Int {
    handle {!A::a(); 42} with handler A {
        a()=>handle {1} with handler B {
            b()=>7;
            return x=>handle {2} with handler B {
                b()=>8;
                return y=>resume(());
            };
        };
    }
}''')
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('dispatch', 'A', 'A'), ('resume', 'A', None)))

    def test_nested_return_preserves_resumption_mode_scope_and_local_ownership(self):
        template = '''module m;
import eldude::fixture::{acquire};
effect A {MODE a()->Unit;}
effect B {tail b()->Int;}
pub fn main()->Unit {
    handle {!A::a()} with handler A {
        a()=>handle {1} with handler B {b()=>7; return x=>RETURN;};
    }
}'''
        cases = (
            ('tail', 'resume(())', 'Explicit resume.*tail', 'resume(())'),
            ('once', 'resume(7)', 'Incorrect operation result', 'resume(7)'),
            ('once', '{let f=fn()=>resume(()); f()}', 'resume.*only inside an operation clause', 'resume(())'),
            ('once', '{let local=acquire(); resume(())}', 'Unconsumed resource local', 'let local=acquire();'),
        )
        for mode, returning, message, at in cases:
            with self.subTest(returning=returning, mode=mode):
                self.reject(template.replace('MODE', mode).replace('RETURN', returning),
                            'semantic', message, at)

    def test_nested_return_preserves_pending_argument_obligations(self):
        self.reject('''module m;
import eldude::fixture::{File, acquire, close};
effect A {once a()->Unit;}
effect B {tail b()->Int;}
effect Stop {affine stop()->Unit;}
fn consume(file:File, done:Unit)->Unit {close(file)}
pub fn main()->Unit {
    handle {
        handle {!A::a()} with handler A {
            a()=>consume(acquire(), handle {1} with handler B {
                b()=>7;
                return x=>{!Stop::stop(); resume(())};
            });
        }
    } with handler Stop {stop()=>();}
}''', 'semantic', 'abandon live resource argument temporary', '!Stop::stop()')


class SourceFixtureTests(unittest.TestCase):
    def fixture(self, name):
        from source_pipeline import compile_file
        return compile_file(FIXTURES / (name + '.eld'))

    def test_multi_operations_dispatch_cleanup_and_complete_residual(self):
        from source_syntax import grammar
        self.assertTrue(grammar().accepts((FIXTURES / 'multi_operations.eld').read_text()))
        checked = self.fixture('multi_operations')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertEqual(len(checked.handled_rows['inner'].labels), 1)
        self.assertIn('outer', checked.handled_rows['inner'].labels[0])
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Multi', 'inner', 'step'),
            ('resume', 'inner', None), ('dispatch', 'Multi', 'inner', 'read'),
            ('dispatch', 'Multi', 'outer', 'read'), ('acquire', 'File', 2),
            ('close', 2, 'cleanup'), ('resume', 'outer', 42), ('resume', 'inner', 42),
            ('close', 1, 'cleanup')))

    def test_named_dispatch_and_generated_forwarding_keep_source_origins(self):
        checked = self.fixture('multi_operations')
        text = (FIXTURES / 'multi_operations.eld').read_text()
        def dispatches(term):
            if isinstance(term, tuple):
                if term and term[0] == 'dispatch':
                    yield term
                for part in term:
                    yield from dispatches(part)
        origins = []
        for dispatch in dispatches(checked.program.core):
            self.assertIn(id(dispatch), checked.program.origins)
            span = checked.program.origins[id(dispatch)]
            origins.append(text[span.start:span.end])
        self.assertCountEqual(origins, ['!Multi::step()', '!Multi::read(42)', 'forward ..;', 'forward ..;'])

    def test_multi_operation_deep_reentry_shares_one_frame_and_fresh_check_states(self):
        checked = self.fixture('multi_operations_deep')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertEqual(len(checked.handled_rows['shared'].labels), 1)
        self.assertIn('mark', checked.handled_rows['shared'].labels[0])
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Multi', 'shared', 'step'),
            ('resume', 'shared', None), ('dispatch', 'Multi', 'inner', 'step'),
            ('resume', 'inner', None), ('dispatch', 'Multi', 'inner', 'read'),
            ('dispatch', 'Multi', 'shared', 'read'),
            ('acquire', 'File', 2), ('dispatch', 'Mark', 'mark'), ('resume', 'mark', None),
            ('close', 2, 'cleanup'), ('resume', 'shared', 42), ('resume', 'inner', 42),
            ('close', 1, 'explicit'),
            ('acquire', 'File', 3), ('close', 3, 'cleanup')))

    def test_multi_operation_affine_forwarding_unwinds_and_preserves_outside(self):
        checked = self.fixture('multi_operations_affine')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        result = run(checked.program)
        self.assertEqual(result.value, 7)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('acquire', 'File', 2),
            ('dispatch', 'Multi', 'inner', 'step'), ('resume', 'inner', None),
            ('dispatch', 'Multi', 'inner', 'stop'), ('dispatch', 'Multi', 'outer', 'stop'),
            ('abandon', 'outer'), ('abandon', 'inner'),
            ('close', 2, 'cleanup'), ('close', 1, 'explicit')))

    def test_multi_operation_rejection_fixtures_parse_and_fail_at_marked_source(self):
        from source_pipeline import compile_file
        from source_syntax import grammar
        self.assertEqual(set(MULTI_FAILURES), {p.stem for p in MULTI_REJECT.glob('*.eld')})
        for name, (code, message) in MULTI_FAILURES.items():
            path = MULTI_REJECT / (name + '.eld')
            source = path.read_text()
            with self.subTest(name=name):
                self.assertTrue(grammar().accepts(source))
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                diagnostic = caught.exception
                self.assertEqual(diagnostic.code, code, str(diagnostic))
                self.assertRegex(diagnostic.message, message)
                offset = source.index('/*error*/') + len('/*error*/')
                while source[offset].isspace():
                    offset += 1
                self.assertEqual((diagnostic.span.filename, diagnostic.span.start,
                                  diagnostic.span.line, diagnostic.span.column),
                                 (str(path), offset, source.count('\n', 0, offset) + 1,
                                  offset - source.rfind('\n', 0, offset)))
                if name in ('frame_transfer', 'clause_local', 'unsafe_affine', 'skipped_consumption',
                            'post_resume_outward', 'opaque_affine_family', 'argument_abandonment',
                            'sibling_residual'):
                    self.assertTrue(diagnostic.related, str(diagnostic))
                if name == 'frame_transfer':
                    self.assertEqual([message for message, _ in diagnostic.related],
                                     ['Binding declared here', 'Ownership transferred here'])

    def test_residual_recheck_diagnostics_do_not_retain_a_later_transfer(self):
        from source_pipeline import compile_file
        with self.assertRaises(Diagnostic) as caught:
            compile_file(MULTI_REJECT / 'sibling_residual.eld')
        self.assertRegex(caught.exception.message, 'abandon live resource local')
        self.assertEqual([message for message, _ in caught.exception.related], ['Binding declared here'])

    def test_existing_literal_and_source_functions(self):
        from source_pipeline import execute_file
        self.assertEqual(execute_file(ROOT / 'examples/01_values/literal.eld').value, 42)
        self.assertEqual(run(self.fixture('functions').program).value, 42)

    def test_operation_arguments_forward_and_resume_through_source_functions(self):
        checked = self.fixture('operation_arguments')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertEqual(checked.functions['request'].effects, Row(('Echo',)))
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'),
            ('dispatch', 'Echo', 'inner'), ('dispatch', 'Echo', 'outer'),
            ('acquire', 'File', 2), ('close', 2, 'cleanup'),
            ('resume', 'outer', 7), ('resume', 'inner', 7), ('resume', 'step', 7),
            ('dispatch', 'Step', 'step'), ('dispatch', 'Echo', 'inner'),
            ('dispatch', 'Echo', 'outer'), ('acquire', 'File', 3), ('close', 3, 'cleanup'),
            ('resume', 'outer', 42), ('resume', 'inner', 42), ('resume', 'step', 42),
            ('close', 1, 'explicit'), ('acquire', 'File', 4), ('close', 4, 'cleanup'),
            ('acquire', 'File', 5), ('close', 5, 'cleanup')))

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

    def test_nested_return_threads_frame_ownership_through_deep_reentry(self):
        checked = self.fixture('nested_return')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'),
            ('acquire', 'File', 2), ('dispatch', 'Read', 'read'),
            ('resume', 'read', 7), ('close', 2, 'cleanup'), ('resume', 'step', None),
            ('dispatch', 'Step', 'step'), ('acquire', 'File', 3),
            ('dispatch', 'Read', 'read'), ('resume', 'read', 7),
            ('close', 3, 'cleanup'), ('resume', 'step', None), ('close', 1, 'explicit'),
            ('acquire', 'File', 4), ('close', 4, 'cleanup'),
            ('acquire', 'File', 5), ('close', 5, 'cleanup')))

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
            'wrong_operation_result': ('operation result', 11, 20),
            'tail_resume': ('Explicit resume.*tail', 11, 20),
            'missing_resume': ('once clause must resume exactly once', 11, 19),
            'repeated_resume': ('more than once', 13, 13),
            'escaping_resume': ('resume.*only inside an operation clause', 12, 33),
            'frame_transfer': ('file was already consumed', 16, 19),
            'clause_local': ('Unconsumed resource local', 14, 13),
            'unsafe_affine': ('abandon live resource file', 12, 9),
            'skipped_outer_resume': ('skip an enclosing resume', 16, 13),
            'skipped_consumption': ('skip consumption of file', 12, 9),
            'outward_pending': ('abandon live resource file', 21, 17),
            'deep_residual': ('abandon live resource local', 21, 17),
            'post_resume': ('abandon live resource file', 21, 17),
            'same_family': ('unqualified same-family', 11, 20),
            'nested_return_affine_skip': ('skip an enclosing resume', 20, 30),
            'nested_return_repeated': ('more than once', 22, 13),
            'nested_return_frame_transfer': ('frame was already consumed', 26, 19),
            'nested_return_outward': ('abandon live resource outside', 29, 21),
            'nested_return_residual': ('abandon live resource local', 30, 21),
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
                if name in ('frame_transfer', 'unsafe_affine', 'post_resume', 'deep_residual',
                            'nested_return_frame_transfer', 'nested_return_outward', 'nested_return_residual'):
                    self.assertTrue(diagnostic.related)
                if name == 'frame_transfer':
                    self.assertEqual([span.line for _, span in diagnostic.related], [10, 15])
                if name == 'nested_return_frame_transfer':
                    self.assertEqual([span.line for _, span in diagnostic.related], [14, 24])

    def test_operation_argument_failures_are_static_located_rejections(self):
        from source_pipeline import compile_file
        from source_syntax import grammar
        directory = ROOT / 'examples/reject/semantics/operation_arguments'
        cases = {
            'type': ('type', 'Type mismatch', 9, 9),
            'arity': ('type', 'Operation arity mismatch', 9, 9),
            'clause_arity': ('type', 'Operation clause arity mismatch', 11, 9),
            'abandonment': ('semantic', 'abandon live resource file', 12, 25),
        }
        self.assertEqual(set(cases), {p.stem for p in directory.glob('*.eld')})
        for name, (code, message, line, column) in cases.items():
            path = directory / (name + '.eld')
            with self.subTest(name=name):
                self.assertTrue(grammar().accepts(path.read_text(encoding='utf-8')))
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                diagnostic = caught.exception
                self.assertEqual(diagnostic.code, code)
                self.assertRegex(diagnostic.message, message)
                self.assertEqual((diagnostic.span.filename, diagnostic.span.line, diagnostic.span.column),
                                 (str(path), line, column))
                if name == 'abandonment':
                    self.assertEqual(diagnostic.related[0][1].line, 10)

    def test_cli_success_syntax_semantic_and_unsupported_failure(self):
        cases = (
            (FIXTURES / 'combined.eld', 0, '42\n', ''),
            (FIXTURES / 'nested_return.eld', 0, '42\n', ''),
            (FIXTURES / 'operation_arguments.eld', 0, '42\n', ''),
            (FIXTURES / 'multi_operations.eld', 0, '42\n', ''),
            (FIXTURES / 'multi_operations_deep.eld', 0, '42\n', ''),
            (FIXTURES / 'multi_operations_affine.eld', 0, '7\n', ''),
            (MULTI_REJECT / 'argument_type.eld', 1, '', ':type:'),
            (MULTI_REJECT / 'sibling_residual.eld', 1, '', ':semantic:'),
            (MULTI_REJECT / 'frame_transfer.eld', 1, '', ':semantic:'),
            (ROOT / 'examples/reject/syntax/source_pipeline/missing_semicolon.eld', 1, '', ':syntax:'),
            (REJECT / 'tail_resume.eld', 1, '', ':semantic:'),
            (REJECT / 'nested_return_affine_skip.eld', 1, '', ':semantic:'),
            (ROOT / 'examples/reject/semantics/operation_arguments/type.eld', 1, '', ':type:'),
            (FIXTURES / 'branch.eld', 0, '42\n', ''),
            (ROOT / 'examples/06_tasks/join.eld', 0, '42\n', ''),
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
                    self.assertRegex(result.stderr, r'\.eld:\d+:\d+:')
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
