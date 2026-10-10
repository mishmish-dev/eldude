"""Executable value examples and the boundaries of checked scalar evaluation."""
import unittest
from pathlib import Path

from eldude.core.handlers import run
from eldude.source.pipeline import compile_source, execute_file
from eldude.source.syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[3]


class SourceValuesTests(unittest.TestCase):
    def execute(self, body, result='Int'):
        return run(compile_source(f'module m; pub fn main()->{result} {{ {body} }}').program)

    def test_original_scalar_examples(self):
        cases = {
            '01_values/arithmetic': 14, '01_values/branches': 7,
            '01_values/closures': 42, '04_effects/handler': 42,
            '04_effects/forwarding': 42, '04_effects/nested_layers': 42,
            '04_effects/once': 42,
        }
        for name, expected in cases.items():
            with self.subTest(example=name):
                self.assertEqual(execute_file(ROOT / f'eldude-program-examples/src/{name}.eld').value, expected)

    def test_tuples_and_records(self):
        for name, expected in (('tuples', 42), ('records', 9)):
            with self.subTest(example=name):
                self.assertEqual(execute_file(ROOT / f'eldude-program-examples/src/01_values/{name}.eld').value, expected)
        self.assertEqual(self.execute('let (a, (b, _)) = (19, (23, true)); a+b').value, 42)
        source = '''module m; struct P { x:Int, y:Int }
fn sum(p:P)->Int {p.x+p.y}
pub fn main()->Int {let x=19; sum(P { y:23, x })}'''
        self.assertEqual(run(compile_source(source).program).value, 42)
        for change in ('P {x:19}', 'P {x:19,y:true}', 'P {x:19,y:23,z:0}', 'P {x:19,x:23}'):
            with self.subTest(change=change), self.assertRaises(Diagnostic):
                compile_source(source.replace('P { y:23, x }', change))
        for body in ('let (a,b)=(1,2,3); a+b', 'let (a,a)=(1,2); a',
                     'let (a,b)=42; a+b'):
            with self.subTest(body=body), self.assertRaises(Diagnostic):
                self.execute(body)

    def test_generic_functions_infer_and_accept_explicit_types(self):
        self.assertEqual(execute_file(ROOT / 'eldude-program-examples/src/01_values/generics.eld').value, 42)
        source = '''module m; fn identity<T>(x:T)->T {x}
pub fn main()->Int {let yes=identity(true); if yes {identity::<Int>(42)} else {0}}'''
        self.assertEqual(run(compile_source(source).program).value, 42)
        source = '''module m; import eldude::fixture::{File,acquire,close};
fn identity<T>(x:T)->T {x}
pub fn main()->Unit {close(identity::<File>(acquire()))}'''
        self.assertEqual(run(compile_source(source).program).events,
                         (('acquire', 'File', 1), ('close', 1, 'explicit')))
        for source in (
            'module m; fn id<T>(x:T)->T {x} pub fn main()->Int {id::<Bool>(42)}',
            'module m; fn id<T>(x:T)->T {x} pub fn main()->Int {id::<Int,Bool>(42)}',
            'module m; fn id(x:Int)->Int {x} pub fn main()->Int {id::<Int>(42)}',
            'module m; fn bad<T>(x:T)->Int {42} pub fn main()->Int {42}',
            'module m; fn bad<T>(x:T)->T {x+x} pub fn main()->Int {42}',
        ):
            with self.subTest(source=source), self.assertRaises(Diagnostic):
                compile_source(source)

    def test_record_field_names_do_not_change_ownership(self):
        for name in ('Ref', 'Int', 'Unit', 'Owned'):
            source = f'''module m; import eldude::fixture::{{File,acquire}};
struct R {{{name}:File}} pub fn main()->Int {{let r=R {{{name}:acquire()}}; 42}}'''
            with self.subTest(field=name), self.assertRaises(Diagnostic) as caught:
                compile_source(source)
            self.assertEqual(caught.exception.code, 'semantic')
        source = 'module m; struct R {Owned:Int} pub fn main()->Int {let r=R {Owned:42}; r.Owned+r.Owned}'
        self.assertEqual(run(compile_source(source).program).value, 84)

    def test_record_forward_references_inside_compound_types(self):
        source = '''module m; struct R {pair:(S,Int), get:fn()->S}
struct S {value:Int}
pub fn main()->Int {let r=R {pair:(S {value:19},23), get:fn()=>S {value:42}};
let (s,n)=r.pair; s.value+n+(r.get()).value}'''
        self.assertEqual(run(compile_source(source).program).value, 84)

    def test_scalar_operators_and_lazy_branches(self):
        for expression, expected in (
            ('20 - 6 - 2', 12), ('-(2 + 3) * +4', -20),
            ('-7 / 3', -2), ('7 / -3', -2), ('-7 % 3', -1),
            ('-9223372036854775808 % -1', 0),
            ('if 2 * 3 == 6 { 42 } else { 1 / 0 }', 42),
            ('if false { 1 / 0 } else if true { 42 } else { 0 }', 42),
            ('if () == () { 42 } else { 0 }', 42),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.execute(expression).value, expected)
        self.assertIs(self.execute('true != false', 'Bool').value, True)
        self.assertIsNone(self.execute('if false { (); }', 'Unit').value)

    def test_both_branches_and_operand_types_are_checked(self):
        for body in ('if 1 { 42 } else { 0 }', 'true + false',
                     'true < false', '1 == true', 'if true { 42 } else { () }',
                     'if true { 42 } else { true + false }'):
            with self.subTest(body=body), self.assertRaises(Diagnostic) as caught:
                self.execute(body)
            self.assertEqual(caught.exception.code, 'type')

    def test_binary_operands_dispatch_once_left_to_right(self):
        source = '''module m; effect E {tail get(x:Int)->Int;}
pub fn main()->Int {handle {!E::get(20) + !E::get(22)} with handler E {get(x)=>x;}}'''
        result = run(compile_source(source).program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('dispatch', 'E', 'E'), ('resume', 'E', 20),
                                         ('dispatch', 'E', 'E'), ('resume', 'E', 22)))

    def test_record_variant_fields_dispatch_once_in_written_order(self):
        result = execute_file(ROOT / 'eldude-program-examples/src/01_values/variant_field_order.eld')
        self.assertEqual(result.value, 12)
        self.assertEqual(result.events, (('dispatch', 'Echo', 'Echo'), ('resume', 'Echo', 2),
                                         ('dispatch', 'Echo', 'Echo'), ('resume', 'Echo', 1)))

    def test_recursive_declarations_require_finite_positive_storage(self):
        self.assertEqual(execute_file(ROOT / 'eldude-program-examples/src/02_ownership/recursive_positive_storage.eld').value, 42)
        for name in ('parameter', 'result', 'group', 'container', 'alias'):
            path = ROOT / f'eldude-program-examples/reject/semantics/recursive_callable_{name}.eld'
            with self.subTest(example=name):
                with self.assertRaises(Diagnostic) as caught:
                    compile_source(path.read_text(), str(path))
                self.assertEqual(caught.exception.code, 'type')
                self.assertIn('finite strictly positive storage', caught.exception.message)

    def test_list_new_rejects_extra_arguments_before_elaboration(self):
        path = ROOT / 'eldude-program-examples/reject/semantics/list_new_arity.eld'
        with self.assertRaises(Diagnostic) as caught:
            compile_source(path.read_text(), str(path))
        self.assertEqual(caught.exception.code, 'type')
        self.assertIn('List::new expects no arguments', caught.exception.message)

    def test_branch_consumption_and_resume_must_agree(self):
        prefix = 'module m; import eldude::fixture::{acquire,close}; '
        source = prefix + 'pub fn main()->Unit {let f=acquire(); if true {close(f)} else {close(f)}}'
        self.assertEqual(run(compile_source(source).program).events,
                         (('acquire', 'File', 1), ('close', 1, 'explicit')))
        for body in ('if true {close(f)} else {()}',
                     'if false {()} else {close(f)}'):
            with self.subTest(body=body), self.assertRaises(Diagnostic):
                compile_source(prefix + 'pub fn main()->Unit {let f=acquire(); '+body+'}')
        source = '''module m; effect E {once get()->Int;}
pub fn main()->Int {handle {!E::get()} with handler E {get()=>if true {resume(42)} else {resume(0)};}}'''
        self.assertEqual(run(compile_source(source).program).value, 42)
        with self.assertRaises(Diagnostic):
            compile_source(source.replace('resume(0)', '0'))

    def test_arithmetic_defects_are_located_and_unwind_resources(self):
        import tempfile
        for expression in ('9223372036854775807 + 1', '-(-9223372036854775808)',
                           '-9223372036854775808 / -1', '1 / 0', '1 % 0'):
            with self.subTest(expression=expression), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'defect.eld'
                source = 'module m; import eldude::fixture::{acquire};\npub fn main()->Int {using(f=acquire()){'+expression+'}}'
                path.write_text(source)
                with self.assertRaises(Diagnostic) as caught:
                    execute_file(path)
                self.assertEqual(caught.exception.code, 'defect')
                self.assertEqual(source[caught.exception.span.start:caught.exception.span.end], expression)

    def test_defects_unwind_structural_owners_in_scope_order(self):
        from eldude.core.handlers import Defect
        prefix = 'module m; import eldude::fixture::{acquire,close}; '
        cases = (
            ('pub fn main()->Int {let a=acquire(); let b=acquire(); using(x=b,y=a){1/0}}',
             (('acquire', 'File', 1), ('acquire', 'File', 2),
              ('close', 1, 'cleanup'), ('close', 2, 'cleanup'))),
            ('pub fn main()->Int {let a=acquire(); let n=1/0; close(a); n}',
             (('acquire', 'File', 1),)),
            ('effect E {tail get()->Int;} pub fn main()->Int {handle {using(a=acquire()){!E::get()}} with handler E {get()=>1/0;}}',
             (('acquire', 'File', 1), ('dispatch', 'E', 'E'), ('abandon', 'E'), ('close', 1, 'cleanup'))),
            ('effect E {tail get()->Int;} pub fn main()->Int {handle {using(a=acquire()){!E::get()/0}} with handler E {get()=>42;}}',
             (('acquire', 'File', 1), ('dispatch', 'E', 'E'), ('resume', 'E', 42), ('close', 1, 'cleanup'))),
        )
        for source, events in cases:
            with self.subTest(source=source):
                with self.assertRaises(Defect) as caught:
                    run(compile_source(prefix + source).program)
                self.assertEqual(caught.exception.events, events)


if __name__ == '__main__':
    unittest.main()
