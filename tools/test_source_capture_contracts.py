"""Capture annotations and existential erasure preserve ownership and provenance."""
import unittest
from pathlib import Path

from handlers import run
from inference import Fn
from source_pipeline import compile_source
from source_syntax import Diagnostic


class SourceCaptureContractTests(unittest.TestCase):
    def test_review_composition_programs(self):
        root = Path(__file__).resolve().parents[1] / 'examples/02_ownership'
        for name in ('associated_only', 'associated_decrease', 'associated_alias', 'generic_alias',
                     'generic_projection', 'existential_effect_row', 'capture_trait_bounds',
                     'existential_callback_factory', 'generic_kinds', 'nonabandoning'):
            with self.subTest(program=name):
                path = root / (name + '.eld')
                checked = compile_source(path.read_text(), str(path))
                execution = run(checked.program)
                self.assertEqual(execution.value, 42)
                for signature in checked.functions.values():
                    imported = Fn.loads(signature.dumps())
                    self.assertEqual(imported.dumps(), signature.dumps())
                    if imported.effect_vars and imported.effects.tail:
                        self.assertIs(imported.effects.tail, imported.effect_vars[0])
                        if imported.parameters and isinstance(imported.parameters[0], Fn):
                            self.assertIs(imported.parameters[0].effects.tail, imported.effect_vars[0])
                    if imported.effect_vars and isinstance(imported.result, Fn) and imported.result.effects.tail:
                        self.assertIs(imported.result.effects.tail, imported.effect_vars[0])
                if name == 'nonabandoning':
                    self.assertEqual([e for e in execution.events if e[0] in ('acquire', 'close')],
                                     [('acquire', 'File', 1), ('close', 1, 'explicit')])

    def test_static_member_collision_rejects_both_declaration_orders(self):
        path = Path(__file__).resolve().parents[1] / 'examples/reject/semantics/static_member_collision.eld'
        source = path.read_text()
        lines = source.splitlines()
        first, second = [i for i, line in enumerate(lines) if line.startswith('impl ')]
        lines[first], lines[second] = lines[second], lines[first]
        for text in (source, '\n'.join(lines)):
            with self.assertRaises(Diagnostic) as caught:
                compile_source(text, str(path))
            self.assertEqual(caught.exception.code, 'type')
            self.assertIn('Ambiguous implementation member', caught.exception.message)
            self.assertEqual(caught.exception.span.filename, str(path))

    def test_dynamic_mutation_and_integration_programs(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        for name, expected in (('05_state_and_collections/existential_mut', 1),
                               ('05_state_and_collections/existential_projected_mut', 42),
                               ('06_tasks/capture_rows', 42),
                               ('07_source_pipeline/capture_trait_integration', 42)):
            path = root / (name + '.eld')
            checked = compile_source(path.read_text(), str(path))
            execution = run(checked.program)
            self.assertEqual(execution.value, expected)
            if 'integration' in name:
                self.assertEqual(execution.events, (('acquire', 'File', 1), ('close', 1, 'explicit')))
            for signature in checked.functions.values():
                self.assertEqual(Fn.loads(signature.dumps()), signature)
    def test_mutable_grant_programs(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        for name, expected in (('forwarded_mut', 1), ('projected_mut', 42), ('mut_suspension', 42), ('mut_exit_paths', 42)):
            path = root / '05_state_and_collections' / (name + '.eld')
            execution = run(compile_source(path.read_text(), str(path)).program)
            self.assertEqual(execution.value, expected)
            if name == 'mut_suspension':
                self.assertTrue(any(event[0] == 'dispatch' for event in execution.events))
            if name == 'mut_exit_paths':
                self.assertTrue(any(event[0] == 'abandon' for event in execution.events))
    def test_instantiated_existential_programs(self):
        root = Path(__file__).resolve().parents[1] / 'examples/02_ownership'
        for name in ('arguments', 'associated', 'constraints', 'traits'):
            path = root / ('existential_' + name + '.eld')
            source = path.read_text()
            checked = compile_source(source, str(path))
            self.assertEqual(run(checked.program).value, 42)
            if name == 'arguments':
                first, second = [node.span for node in checked.ast.items[1]
                                 if node.kind == 'impl' and node.items[1] and node.items[1].items[0] == 'Read']
                reordered = (source[:first.start] + source[second.start:second.end]
                             + source[first.end:second.start] + source[first.start:first.end]
                             + source[second.end:])
                self.assertEqual(run(compile_source(reordered, str(path)).program).value, 42)

    def test_region_arguments_and_inference_programs(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        for name in ('inferred_regions', 'explicit_regions'):
            path = root / '05_state_and_collections' / (name + '.eld')
            self.assertEqual(run(compile_source(path.read_text(), str(path)).program).value, 42)
        for name, code, message in (
                ('ambiguous_callback_regions', 'type', 'unambiguous'),
                ('generic_argument_kind', 'type', 'kind'),
                ('generic_argument_scope', 'name', 'Unknown'),
                ('generic_argument_arity', 'type', 'arity')):
            path = root / 'reject/semantics' / (name + '.eld')
            with self.assertRaises(Diagnostic) as caught:
                compile_source(path.read_text(), str(path))
            self.assertEqual(caught.exception.code, code)
            self.assertIn(message, caught.exception.message)
            self.assertEqual(caught.exception.span.filename, str(path))

    def test_parameter_capture_programs(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        for folder in ('02_ownership', '05_state_and_collections'):
            path = root / folder / 'parameter_capture.eld'
            checked = compile_source(path.read_text(), str(path))
            execution = run(checked.program)
            self.assertEqual(execution.value, 42)
            if folder == '02_ownership':
                self.assertEqual(execution.events, (('acquire', 'File', 1), ('close', 1, 'explicit')))
            self.assertEqual(Fn.loads(checked.functions['make'].dumps()), checked.functions['make'])
        for name, message in (('twice', 'already consumed'), ('escape', 'region would escape')):
            path = root / 'reject/semantics' / ('parameter_capture_' + name + '.eld')
            with self.assertRaises(Diagnostic) as caught:
                compile_source(path.read_text(), str(path))
            self.assertEqual(caught.exception.code, 'semantic')
            self.assertIn(message, caught.exception.message)
            self.assertEqual(caught.exception.span.filename, str(path))

    def test_parameter_names_do_not_change_canonical_contracts(self):
        source = '''module m; import eldude::fixture::{File,close};
fn make(file:File)->fn()->Unit captures {file} {fn(){close(file);}}
pub fn main()->Int {42}'''
        left = compile_source(source).functions['make']
        right = compile_source(source.replace('file', 'resource')).functions['make']
        self.assertEqual(left.dumps(), right.dumps())
        self.assertEqual(Fn.loads(left.dumps()), left)

    def test_region_contracts_survive_higher_order_calls(self):
        source = '''module m;
import state::ref::{Ref};
fn relay<@r>(f:fn()->{state<@r>}Int captures {@r})
    ->fn()->{state<@r>}Int captures {@r} {f}
pub fn main()->Int {
    region local {
        let cell:Ref<Int,@local> = Ref::new(42);
        let f:fn()->{state<@local>}Int captures {cell} =
            fn()->{state<@local>}Int captures {@local} {cell.get()};
        let g=relay(f);
        g()
    }
}'''
        checked = compile_source(source)
        self.assertEqual(run(checked.program).value, 42)
        signature = checked.functions['relay']
        self.assertEqual(Fn.loads(signature.dumps()), signature)
        self.assertIn('arg:0', signature.bound)

    def test_closure_factory_keeps_region_and_argument_bounds(self):
        source = '''module m; import state::ref::{Ref};
fn make<@r>(cell:Ref<Int,@r>)->fn()->{state<@r>}Int captures {@r} {
    fn()->{state<@r>}Int captures {cell} {cell.get()}
}
pub fn main()->Int {region local {let cell:Ref<Int,@local> = Ref::new(42);let f=make(cell);f()}}'''
        checked = compile_source(source)
        self.assertEqual(run(checked.program).value, 42)
        self.assertIn('arg:0', checked.functions['make'].bound)

    def test_named_handler_capture_keeps_its_selected_instance(self):
        source = '''module m; effect Read {tail read()->Int;}
pub fn main()->Int {
handle {
    let f:fn()->{Read}Int captures {outer}=fn(){!outer::read()};
    handle {f()} with inner=handler Read {read()=>0;return x=>x;}
} with outer=handler Read {read()=>42;return x=>x;}
}'''
        self.assertEqual(run(compile_source(source).program).value, 42)

    def test_named_linear_capture_is_consumed_once(self):
        prefix = 'module m; import eldude::fixture::{File,acquire,close}; '
        body = 'let file=acquire(); let f:fn()->Unit captures {file}=fn(){close(file);}; '
        checked = compile_source(prefix + 'pub fn main()->Int {' + body + 'f();42}')
        self.assertEqual(run(checked.program).events, (('acquire', 'File', 1), ('close', 1, 'explicit')))
        for tail, message in (('42', 'Unconsumed resource f'), ('f();f();42', 'already consumed')):
            with self.subTest(tail=tail), self.assertRaisesRegex(Diagnostic, message):
                compile_source(prefix + 'pub fn main()->Int {' + body + tail + '}')

    def test_omitted_or_wrong_capture_contract_cannot_erase_obligations(self):
        sources = (
            '''module m; import eldude::fixture::{acquire,close};
pub fn main()->Int {let file=acquire();let f:fn()->Unit=fn(){close(file);}; f();42}''',
            '''module m; import state::ref::{Ref};
fn call(f:fn()->Int)->Int {f()}
pub fn main()->Int {region r {let cell:Ref<Int,@r> = Ref::new(0);
let f=fn(){let copy=cell;42};call(f)}}''',
            '''module m; import state::ref::{Ref};
pub fn main()->Int {region outer {let cell:Ref<Int,@outer> = Ref::new(0);
region inner {let other:Ref<Int,@inner> = Ref::new(0);
let f:fn()->Int captures {cell}=fn(){let copy=other;42};f()}}}''',
        )
        for source in sources:
            with self.subTest(source=source), self.assertRaisesRegex(Diagnostic, '[Cc]apture|[Cc]allback'):
                compile_source(source)

    def test_annotations_preserve_region_escape_and_validate_names(self):
        source = '''module m; import state::ref::{Ref};
pub fn main()->Int {
let escaped=region r {let cell:Ref<Int,@r> = Ref::new(42);
fn()->{state<@r>}Int captures {cell} {cell.get()}};
escaped()
}'''
        with self.assertRaisesRegex(Diagnostic, 'region would escape'):
            compile_source(source)
        for capture in ('missing', '@missing'):
            with self.subTest(capture=capture), self.assertRaisesRegex(Diagnostic, 'Unknown.*capture|Unknown.*region'):
                compile_source('module m; pub fn main()->Int {let f=fn()->Int captures {' + capture + '}{42};f()}')

    def test_capture_row_programs_preserve_usage(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        for name in ('02_ownership/capture_rows.eld', '05_state_and_collections/affine_capture_row.eld'):
            path = root / name
            execution = run(compile_source(path.read_text(), str(path)).program)
            self.assertEqual(execution.value, 42)
            if name.startswith('02_'):
                self.assertEqual(execution.events, (('acquire', 'File', 1), ('close', 1, 'explicit')))
        for name in ('capture_row_duplicate', 'capture_row_discard'):
            path = root / 'reject/semantics' / (name + '.eld')
            with self.assertRaises(Diagnostic) as caught:
                compile_source(path.read_text(), str(path))
            self.assertEqual(caught.exception.code, 'semantic')
            self.assertIn('Callback must', caught.exception.message)
            self.assertEqual(caught.exception.span.filename, str(path))

    def test_erased_methods_dispatch_through_a_shared_interface(self):
        source = '''module m;
trait Read {fn read(view self)->Int;}
struct A {number:Int} struct B {number:Int}
impl Read for A {fn read(view self)->Int {self.number}}
impl Read for B {fn read(view self)->Int {self.number+1}}
fn read(view item:any Read+Discard)->Int {view item.read()}
fn choose(flag:Bool)->any Read+Discard {
    if flag {let x:any Read+Discard=A{number:21};x}
    else {let x:any Read+Discard=B{number:20};x}
}
pub fn main()->Int {let a=choose(true);let b=choose(false);read(view a)+read(view b)}'''
        self.assertEqual(run(compile_source(source).program).value, 42)

    def test_erasure_preserves_hidden_regions_and_usage_promises(self):
        source = '''module m; import state::ref::{Ref};
trait Read {fn read(view self)->Int;}
struct Holder<@r> {cell:Ref<Int,@r>}
impl<@r> Read for Holder<@r> {fn read(view self)->Int {42}}
pub fn main()->Int {
    region local {let cell:Ref<Int,@local> = Ref::new(0);
        let item:any Read+Dup+Discard=Holder{cell:cell};
        let copy=item; view copy.read()}
}'''
        self.assertEqual(run(compile_source(source).program).value, 42)
        escaped = source.replace('region local {', 'let escaped=region local {').replace(
            'let copy=item; view copy.read()}','item};view escaped.read()')
        with self.assertRaisesRegex(Diagnostic, 'region would escape'):
            compile_source(escaped)

        prefix = '''module m; trait Read {fn read(view self)->Int;}
linear struct Ticket {} impl Read for Ticket {fn read(view self)->Int {42}}
pub fn main()->Int {let item:any Read'''
        for promise in ('+Dup', '+Discard'):
            with self.subTest(promise=promise), self.assertRaisesRegex(Diagnostic, 'usage|Dup|Discard'):
                compile_source(prefix + promise + '=Ticket{};view item.read()}')
        with self.assertRaisesRegex(Diagnostic, 'Unconsumed resource item'):
            compile_source(prefix + '=Ticket{};view item.read()}')

    def test_packaging_requires_an_impl_and_a_dynamic_interface(self):
        with self.assertRaisesRegex(Diagnostic, 'implementation'):
            compile_source('module m; trait Read {fn read(view self)->Int;} struct A{} '
                           'pub fn main()->Int {let x:any Read+Discard=A{};42}')
        with self.assertRaisesRegex(Diagnostic, 'implementation'):
            compile_source('module m; trait Read {fn read(view self)->Int;} '
                           'pub fn main()->Int {let x:any Read+Discard=fn(){42};42}')
        for member in ('fn create()->Int;', 'fn read<T>(view self,x:T)->Int;',
                       'fn same(view self,x:Self)->Int;'):
            source = 'module m; trait Read {' + member + '} fn use(view x:any Read)->Int {42} pub fn main()->Int {42}'
            with self.subTest(member=member), self.assertRaisesRegex(Diagnostic, 'DynCompatible'):
                compile_source(source)

    def test_existing_access_and_usage_weakening_preserve_dispatch(self):
        source = '''module m;
trait Read {fn read(view self)->Int;}
struct A {} impl Read for A {fn read(view self)->Int {21}}
fn twice(view item:any Read+Discard)->Int {item.read()+item.read()}
pub fn main()->Int {let a:any Read+Dup+Discard=A{};let b:any Read+Discard=a;twice(view b)}'''
        self.assertEqual(run(compile_source(source).program).value, 42)

    def test_erasure_cannot_hide_constraints_or_invalid_type_arguments(self):
        base = '''module m; trait Read {fn read(view self)->Int;}
struct A {} impl Read for A {fn read(view self)->Int {42}}
fn inspect(view item:any Read+Discard)->Int {view item.read()}
pub fn main()->Int {let a:any Read%s+Discard=A{};view a.read()}'''
        for arguments in ('<Int>', '<Item=Int>'):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(Diagnostic, 'arity|associated binding'):
                compile_source(base % arguments)
        method = base.replace('fn read(view self)->Int;', 'fn read(view self)->Int where Self:Dup;')
        with self.assertRaisesRegex(Diagnostic, 'DynCompatible'):
            compile_source(method % '')
        implementation = base.replace('impl Read for A {', 'impl Read for A where A:Dup {')
        self.assertEqual(run(compile_source(implementation % '').program).value, 42)
        implementation = base.replace('fn read(view self)->Int {42}', 'fn read(view self)->Int where A:Dup {42}')
        self.assertEqual(run(compile_source(implementation % '').program).value, 42)

    def test_dynamic_consumption_and_enum_wrapping_preserve_linear_usage(self):
        prefix = '''module m; trait Take {fn take(self)->Int;}
struct Ticket {} impl Take for Ticket {fn take(self)->Int {let Ticket{}=self;42}}
enum Wrapped {Item(any Take)}
pub fn main()->Int {let item:any Take=Ticket{};'''
        self.assertEqual(run(compile_source(prefix + 'item.take()}').program).value, 42)
        for tail in ('let wrapped=Wrapped::Item(item);42', 'let first=item.take();item.take()'):
            with self.subTest(tail=tail), self.assertRaisesRegex(Diagnostic, 'Unconsumed|already consumed'):
                compile_source(prefix + tail + '}')

    def test_dynamic_dispatch_cannot_hide_recursion(self):
        source = '''module m; trait Read {fn read(self)->Int;}
struct A {} impl Read for A {fn read(self)->Int {let again:any Read=self;again.read()}}
pub fn main()->Int {42}'''
        with self.assertRaisesRegex(Diagnostic, 'structural descent or diverge'):
            compile_source(source)

    def test_package_dictionary_is_available_in_handler_clauses(self):
        source = '''module m; effect Get {tail get()->Int;}
trait Read {fn read(view self)->Int;} struct A {}
impl Read for A {fn read(view self)->Int {42}}
pub fn main()->Int {handle {!Get::get()} with handler Get {
    get()=>{let item:any Read+Discard=A{};view item.read()};return x=>x;
}}'''
        self.assertEqual(run(compile_source(source).program).value, 42)


if __name__ == '__main__':
    unittest.main()
