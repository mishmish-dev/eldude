"""Source handler contracts, dispatch, forwarding, and lexical resumptions."""
import unittest

from eldude.core.rows import Row
from eldude.core.handlers import run
from eldude.core.inference import INT, UNIT
from eldude.source.syntax import Diagnostic
from .support import SourceAssertions


class SourceHandlerTests(SourceAssertions, unittest.TestCase):
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



if __name__ == '__main__':
    unittest.main()
