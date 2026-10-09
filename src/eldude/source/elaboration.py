"""Module and data elaboration layered over the existing handler source lowering."""
from dataclasses import replace
from pathlib import Path

from eldude.core.rows import Row
from eldude.core.captures import Argument
from eldude.core.traits import TraitSolver, Implementation
from eldude.core.handlers import compile_program
from eldude.core.inference import E, Fn, Ty, INT, UNIT, BOOL, InferenceError, permissions, capture_free
from eldude.core.types import NAT, UNKNOWN, HOST_TYPES, substitute, unwrapped
from eldude.source.modules import load_modules, STDLIB
from eldude.source.checking import SourceChecker
from eldude.source.lowering import Host, HOST_FUNCTIONS
from eldude.source.type_elaboration import TypeElaborator
from eldude.core.model import SourceProgram
from eldude.source.syntax import Node, Diagnostic


RUNTIME_FUNCTIONS = {'task::yield': 'yield'}
RUNTIME_METHODS = {
    ('state::ref', 'Ref'): {'new', 'get', 'replace'},
    ('collections::list', 'List'): {'new', 'length', 'push', 'get', 'remove', 'replace', 'with', 'filter', 'partition', 'next'},
    ('collections::dyn_array', 'DynArray'): {'new', 'length', 'push', 'pop', 'withMut', 'freeze'},
    ('task', 'Task'): {'cancel'},
}


class SourceElaborator(TypeElaborator):
    def __init__(self, ast, graph=None):
        super().__init__(ast)
        self.root_module = self.module
        self.graph = graph if graph is not None else load_modules(ast)
        self.scopes = {m: {} for m in self.graph.modules}
        self.aliases = {m: {} for m in self.graph.modules}
        self.owners, self.named, self.enums, self.traits = {}, {}, {}, {}
        self.variants, self.data_parameters, self.methods, self.cleanup_methods = {}, {}, {}, {}
        self.function_modules, self.function_generics, self.function_self = {}, {}, {}
        self.function_traits, self.effect_arguments = {}, {}
        self.impl_heads, self.impl_contracts = {}, {}
        self.impl_constraints = {}
        self.trait_solver = TraitSolver()
        self.trait_solver.operations = self.operations
        self.function_constraints = {}
        self.function_evidence = {}
        self.dynamic_methods, self.trait_methods = {}, {}
        self.interfaces, self.interface_members = {}, {}
        self.interface_variables = {}
        self.region_arguments, self.capture_arguments = {}, {}
        self.interface_self, self.associated_bindings = None, {}
        self.capture_names = {}
        self.capture_parameter_types = {}
        self.globals, self.global_modules, self.signatures = [], {}, {}
        self.generic_types, self.generic_regions, self.generic_effects = {}, (), {}
        self.generic_captures, self.capture_usage = {}, {}
        self.generic_binders = []
        self.resolving_aliases = set()
        self.equation_sources = None
        self.resolving_equations = set()
        self.projection_evidence = ()
        self.constraint_evidence = ()
        self.exit_stack, self.region_stack = [], []
        self.recursive_allowed = set()
        self.expression_modules, self.nominal_identities, self.inherent_members = {}, {}, {}
        self.types['Nat'] = NAT

    def ir(self, node, kind, *parts):
        expression = super().ir(node, kind, *parts)
        self.expression_modules[id(expression)] = self.module
        return expression

    def canonical(self, spelling, module=None):
        module = module or self.module
        if spelling.startswith(module + '::'):
            spelling = spelling[len(module) + 2:]
        head, separator, suffix = spelling.partition('::')
        identity = self.aliases[module].get(head, head)
        return identity + (separator + suffix if separator else '')

    def identity(self, module, name):
        return name if module == self.root_module else module + '::' + name

    def nominal(self, identity):
        return identity if '::' in identity else self.root_module + '::' + identity

    def local_name(self, node):
        return self.canonical(node.items[0])

    def generics(self, name):
        return name.items[1] if name.kind == 'generic_name' else ()

    def is_library(self, module):
        path = Path(self.graph.modules[module].span.filename)
        return path.is_relative_to(STDLIB)

    def collect(self):
        # Allocate identities before resolving imports, recursive types or function bodies.
        for module in self.graph.order:
            self.module = module
            for declaration in self.graph.modules[module].items[1]:
                if declaration.kind in ('import', 'impl'):
                    continue
                name = declaration.items[0] if declaration.kind in ('let', 'public_let') else declaration.items[1]
                if name.kind not in ('name', 'generic_name'):
                    self.limit('module initialization currently requires a named binding', name)
                spelling = name.items[0]
                if spelling in self.aliases[module] or spelling in ('Int', 'Int64', 'Bool', 'Unit', 'Nat', 'CaptureFree'):
                    self.error('name', 'Duplicate declaration ' + spelling, name)
                identity = self.identity(module, spelling)
                self.aliases[module][spelling] = identity
                self.owners[id(declaration)] = module
                self.named[identity] = declaration
                kind = declaration.kind
                if kind == 'effect':
                    self.effects[identity] = declaration
                elif kind == 'struct':
                    self.records[identity] = declaration
                elif kind == 'enum':
                    self.enums[identity] = declaration
                elif kind == 'trait':
                    self.traits[identity] = declaration
                elif kind in ('function', 'let', 'public_let'):
                    if self.is_library(module) and kind == 'function' and declaration.items[-1] is None:
                        binding = RUNTIME_FUNCTIONS.get(module + '::' + spelling)
                        if binding is None:
                            self.limit('bodyless library function has no runtime binding', declaration)
                        self.scopes[module][spelling] = Host(binding)
                        continue
                    symbol = self.symbol(name)
                    self.scopes[module][spelling] = symbol
                    if kind == 'function':
                        self.definitions[symbol] = declaration
                        self.function_modules[symbol] = module
                        self.function_generics[symbol] = self.generics(name)
                    else:
                        self.globals.append((symbol, declaration))
                        self.global_modules[symbol] = module
        for module in self.graph.order:
            self.module = module
            for declaration in self.graph.modules[module].items[1]:
                if declaration.kind != 'import':
                    continue
                _, path, names = declaration.items
                for original, alias in names:
                    spelling = alias.items[0]
                    if spelling in self.aliases[module]:
                        self.error('name', 'Duplicate declaration ' + spelling, alias)
                    if path.items[0] == 'eldude::fixture':
                        exported = original.items[0]
                        self.aliases[module][spelling] = exported
                        if exported in HOST_TYPES:
                            self.types[exported] = HOST_TYPES[exported]
                        elif exported in HOST_FUNCTIONS:
                            self.scopes[module][spelling] = Host(exported)
                        else:
                            self.error('name', 'Unknown fixture export ' + exported, original)
                    else:
                        target = self.graph.exports[path.items[0]][original.items[0]]
                        owner = self.owners[id(target)]
                        target_name = target.items[0] if target.kind in ('let', 'public_let') else target.items[1]
                        identity = self.identity(owner, target_name.items[0])
                        self.aliases[module][spelling] = identity
                        if target_name.items[0] in self.scopes[owner]:
                            self.scopes[module][spelling] = self.scopes[owner][target_name.items[0]]
        for identity in self.enums:
            declaration = self.enums[identity]
            module = self.owners[id(declaration)]
            self.module = module
            self.bind_generics(self.generics(declaration.items[1]))
            if module in ('core::option', 'core::result'):
                nominal = 'Option' if module == 'core::option' else 'Result'
            else:
                nominal = 'Enum:' + self.nominal(identity)
            enum_type = Ty(nominal, tuple(self.generic_types.values()))
            self.types[identity] = Ty(declaration.items[3].title(), (enum_type,)) if len(declaration.items) > 3 else enum_type
            self.data_parameters[nominal] = tuple(self.generic_types)
        for identity, declaration in self.enums.items():
            self.module = self.owners[id(declaration)]
            self.bind_generics(self.generics(declaration.items[1]))
            variants = {}
            for variant in declaration.items[2]:
                _, name, members, form = variant.items
                if name.items[0] in variants:
                    self.error('name', 'Duplicate enum variant', name)
                variants[name.items[0]] = tuple(self.type(m[1] if form == 'record' else m) for m in members)
            self.variants[unwrapped(self.types[identity]).name] = variants
        for identity in self.records:
            self.record_type(identity)
        self.validate_recursive_storage()
        self.infer_enum_usage()
        self.infer_enum_capture_free()
        self.validate_ref_declarations()
        self.nominal_identities = {unwrapped(self.types[name]).name: name for name in self.records | self.enums}
        for identity, declaration in tuple(self.effects.items()):
            if not self.generics(declaration.items[1]):
                self.instantiate_effect(identity, ())
        # Source impl bodies become ordinary named functions; opaque library methods
        # use the explicit primitive contracts in FeatureChecker.
        for module in self.graph.order:
            self.module = module
            for implementation in self.graph.modules[module].items[1]:
                if implementation.kind != 'impl':
                    continue
                parameters, trait, target_node, constraints, members = implementation.items
                self.bind_generics(parameters)
                def mentioned(value):
                    if isinstance(value, Node):
                        return mentioned(value.items)
                    if isinstance(value, tuple):
                        return set().union(*(mentioned(v) for v in value))
                    return {value} if isinstance(value, str) else set()
                covered = mentioned((trait, target_node))
                for parameter in parameters:
                    parameter_name = parameter.items[0] if parameter.kind == 'name' else parameter.items[0].items[0] if parameter.kind == 'constructor_parameter' else parameter.items[1].items[0]
                    if parameter_name not in covered:
                        self.error('semantic', 'Uncovered implementation parameter ' + parameter_name, parameter)
                target = self.type(target_node)
                if trait:
                    trait_name = self.canonical(trait.items[0])
                    local_trait = trait_name in self.traits and self.owners[id(self.traits[trait_name])] == module
                    target_name = self.canonical(target_node.items[0]) if target_node.kind in ('type', 'applied_type') else None
                    local_type = target_name in self.named and self.owners[id(self.named[target_name])] == module
                    if not local_trait and not local_type:
                        self.error('semantic', 'Uncovered trait implementation', implementation)
                    if trait_name not in self.traits:
                        self.error('name', 'Unknown trait ' + trait_name, trait)
                    required = {m.items[1].items[0] for m in self.traits[trait_name].items[2] if m.kind == 'function'}
                    supplied = {m.items[1].items[0] for m in members if m.kind == 'function'}
                    if not required <= supplied:
                        self.error('type', 'Trait implementation is missing a method', implementation)
                    associated = {m.items[0].items[0] for m in self.traits[trait_name].items[2] if m.kind == 'associated_type'}
                    equations = {m.items[0].items[0] for m in members if m.kind == 'associated_type'}
                    if not associated <= equations:
                        self.error('type', 'Trait implementation is missing an associated type', implementation)
                head = (self.canonical(trait.items[0]) if trait else None, unwrapped(target).name)
                impl = None
                if trait:
                    arguments = self.trait_arguments(self.traits[trait_name], trait.items[1] if trait.kind == 'applied_type' else ())
                    prerequisites = self.constraints(constraints) + self.trait_prerequisites(
                        self.traits[trait_name], trait.items[1] if trait.kind == 'applied_type' else (), target)
                    impl = Implementation(Ty('Trait:' + trait_name, (target, *arguments)),
                                          tuple(t.name[1:] for t in self.generic_types.values()) +
                                          tuple('!' + n for n in self.generic_effects) + tuple('..' + n for n in self.generic_captures),
                                          self.generic_regions, prerequisites)
                if trait:
                    self.impl_heads[head] = target
                    self.impl_contracts[head] = Fn((target,), UNIT, Row(),
                                                  type_vars=tuple(self.generic_types), regions=self.generic_regions)
                    self.impl_constraints[head] = constraints
                old = (self.interface_self, self.associated_bindings, self.equation_sources, self.projection_evidence, self.capture_usage)
                self.interface_self, self.associated_bindings = target, {}
                self.equation_sources = {m.items[0].items[0]: m.items[1] for m in members if m.kind == 'associated_type'}
                self.projection_evidence = impl.prerequisites if impl is not None else ()
                self.capture_usage = {}
                for prerequisite in self.projection_evidence:
                    if prerequisite.name in ('Trait:Dup', 'Trait:Discard') and prerequisite.args[0].name.startswith('$..'):
                        self.capture_usage.setdefault(prerequisite.args[0].name[3:], set()).add(prerequisite.name[6:])
                try:
                    equations = {name: self.associated_equation(name) for name in self.equation_sources}
                finally:
                    self.interface_self, self.associated_bindings, self.equation_sources, self.projection_evidence, self.capture_usage = old
                if impl is not None:
                    impl.equations = equations
                    try:
                        self.trait_solver.add(impl)
                    except ValueError as error:
                        self.error('semantic', str(error), implementation)
                for method in members:
                    if method.kind != 'function':
                        continue
                    if self.is_library(module) and method.items[-1] is None:
                        if method.items[1].items[0] not in RUNTIME_METHODS.get((module, unwrapped(target).name), ()):
                            self.limit('bodyless library method has no runtime binding', method)
                        continue
                    symbol = self.symbol(method.items[1])
                    self.definitions[symbol] = method
                    self.function_modules[symbol] = module
                    self.function_generics[symbol] = parameters + self.generics(method.items[1])
                    self.function_self[symbol] = (target, equations)
                    self.function_constraints[symbol] = constraints
                    self.function_evidence[symbol] = impl.prerequisites if impl is not None else self.constraints(constraints)
                    if not trait:
                        self.inherent_members[symbol] = (module, method.items[0])
                    if impl is not None:
                        impl.methods[method.items[1].items[0]] = symbol
                    if trait:
                        requirement = next((m for m in self.traits[trait_name].items[2]
                                            if m.kind == 'function' and m.items[1].items[0] == method.items[1].items[0]), None)
                        if requirement:
                            self.function_traits[symbol] = (requirement, self.traits[trait_name], trait)
                            self.trait_methods[(trait_name, unwrapped(target).name, method.items[1].items[0])] = symbol
                            if len(method.items[1].items) > 2:
                                self.impl_constraints[head] += method.items[1].items[2]
                    method_key = (unwrapped(target).name, method.items[1].items[0])
                    if method_key in self.methods:
                        previous_symbol = self.methods[method_key][0]
                        if previous_symbol is None:
                            continue
                        if self.function_self[previous_symbol][0] != target:
                            self.limit('multiple specialized methods for one nominal type', method)
                        if not trait:
                            self.error('semantic', 'Duplicate or ambiguous implementation method', method.items[1])
                        self.methods[method_key] = (None, None)
                    else:
                        self.methods[method_key] = (symbol, None)
        self.module = self.root_module
        self.values = self.scopes[self.module]
        self.bind_generics(())

    def lookup(self, node, environment):
        spelling = node.items[0]
        if spelling.startswith(self.module + '::'):
            spelling = spelling[len(self.module) + 2:]
            environment = self.scopes[self.module]
        if spelling not in environment or spelling == '_':
            self.error('name', 'Unknown value ' + spelling, node)
        symbol = environment[spelling]
        if symbol in self.definitions and self.current_function is not None:
            self.references[self.current_function].setdefault(symbol, node)
        return symbol

    def has_exit(self, node):
        if isinstance(node, Node):
            if node.kind in ('return', 'propagate'):
                return True
            if node.kind in ('lambda', 'try'):
                return False
            return self.has_exit(node.items)
        return isinstance(node, tuple) and any(self.has_exit(n) for n in node)

    def scoped_body(self, node, environment, handlers, expected, wrap=False):
        key = self.symbol(Node('name', node.span, ('exit',)))
        self.exit_stack.append((key, expected))
        body = self.expression(node, environment, handlers, expected.args[1] if wrap and expected else expected)
        self.exit_stack.pop()
        return self.ir(node, 'exit_scope', key, expected, body, wrap)

    def clause_expression(self, body, environment, handlers, signature):
        expected = signature.result if signature.mode == 'tail' else None
        if self.has_exit(body):
            return self.scoped_body(body, environment, handlers, expected)
        return self.expression(body, environment, handlers, expected)

    def function(self, node, parameters, contract, body, environment, handlers):
        previous_captures = self.capture_names
        previous_types = self.capture_parameter_types
        if node.kind == 'function':
            self.capture_usage = {}
            self.constraint_evidence = ()
            name = node.items[1]
            for constraint in name.items[2] if len(name.items) > 2 else ():
                if constraint.kind == 'bound' and constraint.items[0].kind == 'capture_variable':
                    subject, bounds = constraint.items
                    self.capture_usage[subject.items[0].items[0]] = {b.items[0] for b in bounds}
        name = node.items[1] if node.kind == 'function' else None
        constraints = self.constraints(self.function_constraints.get(self.current_function, ()) +
                                       (name.items[2] if name and len(name.items) > 2 else ())) if node.kind == 'function' else ()
        constraints = tuple(dict.fromkeys(constraints + self.function_evidence.get(self.current_function, ())))
        self.constraint_evidence = constraints
        for constraint in constraints:
            if constraint.name in ('Trait:Dup', 'Trait:Discard') and constraint.args[0].name.startswith('$..'):
                self.capture_usage.setdefault(constraint.args[0].name[3:], set()).add(constraint.name[6:])
        for constraint in constraints:
            if constraint.name in ('Trait:Dup', 'Trait:Discard', 'Trait:CaptureFree') and constraint.args[0].name.startswith('$'):
                subject = constraint.args[0]
                key = next((n for n, t in self.generic_types.items() if t.name == subject.name), None)
                if key:
                    t = self.generic_types[key]
                    self.generic_types[key] = replace(t, args=tuple(sorted(set(t.args) | {Ty(constraint.name[6:])}, key=repr)))
        local, typed, names = dict(environment), [], set()
        for parameter in parameters:
            name, annotation = parameter.items[:2]
            if name.items[0] in names:
                self.error('name', 'Duplicate parameter', name)
            names.add(name.items[0])
            if annotation is None:
                if name.items[0] == 'self' and self.current_function in self.function_self:
                    t = substitute(self.function_self[self.current_function][0], self.generic_types)
                else:
                    self.limit('closure parameters require type annotations', name)
            else:
                t = self.type(annotation)
            if len(parameter.items) == 3:
                t = Ty(parameter.items[2].title(), (t,))
            symbol = self.symbol(name)
            local[name.items[0]] = symbol
            typed.append((symbol, t))
        self.capture_names = previous_captures | {
            p.items[0].items[0]: Argument(i, 0, *permissions(unwrapped(t)))
            for i, (p, (_, t)) in enumerate(zip(parameters, typed))}
        self.capture_parameter_types = previous_types | {
            p.items[0].items[0]: unwrapped(t) for p, (_, t) in zip(parameters, typed)}
        expected, effects = self.contract(contract) if contract else (None, None)
        captures = self.capture_contract(contract) if contract else None
        self.capture_names = previous_captures
        self.capture_parameter_types = previous_types
        previous = self.exit_stack
        self.exit_stack = []
        lowered = (self.scoped_body(body, local, handlers, expected) if self.has_exit(body)
                   else self.expression(body, local, handlers, expected))
        self.exit_stack = previous
        expression = self.ir(node, 'lambda', tuple(typed), lowered)
        if contract:
            signature = Fn(tuple(t for _, t in typed), expected, effects,
                           bound=frozenset() if capture_free(expected) else frozenset({'env', *(f'arg:{i}' for i in range(len(typed)))}),
                           type_vars=tuple(t.name[1:] for t in self.generic_types.values() if t.name.startswith('$')) if node.kind == 'function' else (),
                           regions=self.generic_regions if node.kind == 'function' else (),
                           effect_vars=tuple(self.generic_effects.values()) if node.kind == 'function' else (),
                           captures=captures,
                           capture_vars=tuple(self.generic_captures.values()) if node.kind == 'function' else (),
                           generic_binders=tuple(self.generic_binders) if node.kind == 'function' else (), constraints=constraints)
            self.annotations.setdefault(id(expression), []).append(signature)
        return expression

    def pattern(self, node, environment):
        if node.kind == 'name':
            spelling = node.items[0]
            if spelling == '_':
                return E('wild')
            symbol = self.symbol(node)
            if spelling in self.pattern_names:
                self.error('name', 'Duplicate pattern binding', node)
            self.pattern_names.add(spelling)
            environment[spelling] = symbol
            return E('bind', symbol)
        if node.kind == 'tuple_pattern':
            return E('tuple_pat', *(self.pattern(p, environment) for p in node.items[0]))
        if node.kind == 'literal_pattern':
            return E('literal_pat', node.items[0].items[0])
        if node.kind in ('variant_pattern', 'record_pattern'):
            path, fields = node.items
            identity = self.canonical(path.items[0])
            if node.kind == 'variant_pattern':
                family, tag = identity.rsplit('::', 1)
                if family not in self.enums:
                    self.error('name', 'Unknown enum ' + family, path)
                self.member_visibility(family, tag, path)
                return E('variant_pat', unwrapped(self.types[family]).name, tag,
                         *(self.pattern(p, environment) for p in fields))
            if identity in self.records:
                names = tuple(f.items[0] for f, _ in fields)
                if len(set(names)) != len(names):
                    self.error('type', 'Duplicate record pattern field', node)
                self.member_visibility(identity, None, path)
                t = unwrapped(self.record_type(identity))
                return E('record_pat', t.name, names,
                         *(self.pattern(p, environment) for _, p in fields))
            family, _, tag = identity.rpartition('::')
            if family not in self.enums:
                self.error('name', 'Unknown pattern constructor ' + identity, path)
            declaration = next((v for v in self.enums[family].items[2] if v.items[1].items[0] == tag), None)
            if declaration is None or declaration.items[3] != 'record':
                self.error('type', 'Expected record variant pattern', path)
            self.member_visibility(family, tag, path)
            ordered = dict((n.items[0], p) for n, p in fields)
            if len(ordered) != len(fields) or set(ordered) != {f[0].items[0] for f in declaration.items[2]}:
                self.error('type', 'Variant pattern fields must match its declaration', node)
            return E('variant_pat', unwrapped(self.types[family]).name, tag,
                     *(self.pattern(ordered[f[0].items[0]], environment) for f in declaration.items[2]))
        self.limit('pattern ' + node.kind, node)

    def bind_pattern(self, node, environment):
        self.pattern_names = set()
        return self.pattern(node, environment)

    def variant(self, node, path, arguments, environment, handlers, expected):
        identity = self.canonical(path.items[0])
        if '::' not in identity:
            return None
        family, tag = identity.rsplit('::', 1)
        if family not in self.enums:
            return None
        self.member_visibility(family, tag, path)
        t = self.types[family]
        if isinstance(expected, Ty) and unwrapped(expected).name == unwrapped(t).name:
            t = expected
        elif t.name in ('Option', 'Result'):
            t = replace(t, args=(UNKNOWN,) * len(t.args))
        values = tuple(self.expression(a, environment, handlers) for a in arguments)
        return self.ir(node, 'variant', t, tag, values)

    def expression(self, node, environment, handlers, expected=None):
        if node.kind == 'specialize':
            callee, arguments = node.items
            resolved = []
            symbol = environment.get(callee.items[0]) if callee.kind == 'path' else None
            parameters = self.function_generics.get(symbol, ())
            for index, argument in enumerate(arguments):
                parameter = parameters[index] if index < len(parameters) else None
                if argument.kind == 'region_type':
                    name = argument.items[0].items[0]
                    if name not in self.region_stack and name not in self.generic_regions:
                        self.error('name', 'Unknown region argument ' + name, argument)
                    resolved.append(('region', name))
                elif argument.kind in ('capture_set', 'capture_variable'):
                    entries = argument.items[0] if argument.kind == 'capture_set' else (argument,)
                    contract = Node('contract', argument.span, (None, (), entries))
                    resolved.append(('capture', self.capture_contract(contract)))
                elif argument.kind == 'effect_row':
                    labels, tail = argument.items
                    if parameter is not None and parameter.kind == 'generic_parameter' and parameter.items[0] == '..' and not labels and tail is None:
                        resolved.append(('capture', frozenset()))
                        continue
                    entries = labels + ((Node('effect_tail', tail.span, tail.items),) if tail else ())
                    row = self.contract(Node('contract', argument.span, (Node('type', argument.span, ('Unit',)), entries)))[1]
                    resolved.append(('effect', row))
                elif argument.kind in ('int', 'nat') or (argument.kind == 'type' and argument.items[0] in self.generic_types and self.generic_types[argument.items[0]].name.startswith('$#')):
                    resolved.append(('nat', self.argument_term(argument)))
                elif parameter is not None and parameter.kind == 'constructor_parameter':
                    term = self.constructor_argument(parameter, argument)
                    resolved.append(('constructor', Ty(term.name.removeprefix('Constructor:'))))
                else:
                    resolved.append(('type', self.type_argument(argument)))
            return self.ir(node, 'specialize', self.expression(callee, environment, handlers), tuple(resolved))
        previous = self.capture_names
        self.capture_names = environment | {name: pair[1] for name, pair in handlers.items()}
        try:
            if isinstance(expected, Ty) and expected.name.startswith('Any:'):
                return self.ir(node, 'pack', expected, self._expression(node, environment, handlers))
            return self._expression(node, environment, handlers, expected)
        finally:
            self.capture_names = previous

    def _expression(self, node, environment, handlers, expected=None):
        kind, items = node.kind, node.items
        if kind == 'nat':
            return self.ir(node, 'nat', items[0])
        if kind == 'block':
            statements, result = items
            def sequence(index, local):
                self.capture_names = local | {name: pair[1] for name, pair in handlers.items()}
                if index == len(statements):
                    return self.expression(result, local, handlers, expected)
                statement = statements[index]
                if statement.kind == 'let':
                    pattern, annotation, initializer = statement.items
                    t = self.type(annotation) if annotation else None
                    initial = self.expression(initializer, local, handlers, t)
                    if t:
                        self.annotations.setdefault(id(initial), []).append(t)
                    if pattern.kind == 'name':
                        if pattern.items[0] == '_':
                            return self.ir(statement, 'seq', initial, sequence(index + 1, local))
                        symbol = self.symbol(pattern)
                        return self.ir(statement, 'let', symbol, initial,
                                       sequence(index + 1, local | {pattern.items[0]: symbol}))
                    inner = dict(local)
                    bound = self.bind_pattern(pattern, inner)
                    return self.ir(statement, 'bindpat', bound, initial, sequence(index + 1, inner))
                lowered = self.expression(statement.items[0], local, handlers)
                if statement.kind == 'assert':
                    lowered = self.ir(statement, 'assert', lowered)
                return self.ir(statement, 'seq', lowered, sequence(index + 1, local))
            return sequence(0, environment)
        if kind == 'if':
            condition, left, right = items
            return self.ir(node, 'if', self.expression(condition, environment, handlers),
                           self.expression(left, environment, handlers, expected),
                           self.expression(right, environment, handlers, expected))
        if kind == 'match':
            subject, arms = items
            lowered = []
            for arm in arms:
                pattern, guard, body = arm.items
                if guard:
                    self.limit('match guards', guard)
                local = dict(environment)
                bound = self.bind_pattern(pattern, local)
                lowered.append((bound, self.expression(body, local, handlers, expected)))
            return self.ir(node, 'match', self.expression(subject, environment, handlers), tuple(lowered))
        if kind == 'record':
            path, fields = items
            identity = self.canonical(path.items[0])
            if identity not in self.records:
                family, _, tag = identity.rpartition('::')
                if family in self.enums:
                    declaration = next((v for v in self.enums[family].items[2] if v.items[1].items[0] == tag), None)
                    if declaration:
                        provided = {n.items[0]: v for n, v in fields}
                        if declaration.items[3] != 'record' or len(provided) != len(fields) or set(provided) != {f[0].items[0] for f in declaration.items[2]}:
                            self.error('type', 'Variant fields must match its declaration', node)
                        variant = self.variant(node, path, tuple(v for _, v in fields), environment, handlers, expected)
                        symbols = {n.items[0]: self.symbol(n) for n, _ in fields}
                        result = self.ir(node, 'variant', variant[1], variant[2],
                                         tuple(self.ir(node, 'var', symbols[f[0].items[0]]) for f in declaration.items[2]))
                        for (name, _), value in reversed(tuple(zip(fields, variant[3]))):
                            result = self.ir(node, 'let', symbols[name.items[0]], value, result)
                        return result
                self.error('name', 'Unknown record ' + identity, path)
            self.member_visibility(identity, None, path)
            template = self.record_type(identity)
            if expected is not None and (not isinstance(expected, Ty) or unwrapped(expected).name != unwrapped(template).name):
                self.error('type', 'Record constructor does not match the expected nominal type', path)
            t = expected or template
            names = tuple(n.items[0] for n, _ in fields)
            if len(set(names)) != len(names) or set(names) != {f.name for f in unwrapped(t).args}:
                self.error('type', 'Record fields must match the declaration exactly', node)
            return self.ir(node, 'record', t, names, *(self.expression(v, environment, handlers) for _, v in fields))
        if kind == 'path':
            variant = self.variant(node, node, (), environment, handlers, expected)
            if variant is not None:
                return variant
        if kind == 'perform' and items[0].kind == 'operation_path':
            path, arguments = items
            family = self.effect_family(path.items[0])
            return self.ir(node, 'perform_op', family, path.items[1].items[0],
                           tuple(self.expression(a, environment, handlers) for a in arguments))
        if kind in ('region', 'taskgroup'):
            if kind == 'region':
                name, body = items
                self.region_stack.append(name.items[0])
                result = self.expression(body, environment, handlers, expected)
                self.region_stack.pop()
                return self.ir(node, 'region', name.items[0], result)
            self.serial += 1
            key = 'taskgroup:' + str(self.serial)
            return self.ir(node, 'taskgroup', key, self.expression(items[0], environment, handlers, expected))
        if kind == 'try':
            return self.scoped_body(items[0], environment, handlers, expected, True)
        if kind in ('return', 'propagate'):
            if not self.exit_stack:
                self.error('semantic', 'Exit expression has no enclosing return scope', node)
            key, target = self.exit_stack[-1]
            return self.ir(node, 'early' if kind == 'return' else 'propagate', key,
                           self.expression(items[0], environment, handlers, target if kind == 'return' else None))
        if kind == 'binary' and items[0] == '??':
            return self.ir(node, 'coalesce', self.expression(items[1], environment, handlers),
                           self.expression(items[2], environment, handlers, expected))
        if kind == 'spawn':
            closure = self.ir(node, 'lambda', (), self.expression(items[0], environment, handlers))
            return self.ir(node, 'spawn', closure)
        if kind == 'await':
            return self.ir(node, 'await', self.expression(items[0], environment, handlers))
        if kind == 'list':
            element = expected.args[0] if expected and expected.name == 'List' else None
            return self.ir(node, 'list_values', element, tuple(self.expression(x, environment, handlers, element) for x in items[0]))
        if kind == 'for':
            pattern, iterable, body = items
            local = dict(environment)
            bound = self.bind_pattern(pattern, local)
            return self.ir(node, 'for_each', bound, self.expression(iterable, environment, handlers), self.expression(body, local, handlers))
        if kind == 'while':
            return self.ir(node, 'while', *(self.expression(x, environment, handlers) for x in items))
        if kind == 'access':
            mode, path = items
            return self.ir(node, 'access', mode, self.lookup(path, environment))
        if kind == 'access_method':
            mode, receiver, method, typeargs, arguments = items
            return self.method(node, mode, receiver, method, arguments, environment, handlers)
        if kind == 'call':
            callee, arguments = items
            if callee.kind == 'field':
                receiver, method = callee.items
                field_names = {f[0].items[0] for d in self.records.values() for f in d.items[2] or ()}
                if method.items[0] not in field_names:
                    return self.method(node, None, receiver, method, arguments, environment, handlers)
            if callee.kind == 'path':
                variant = self.variant(node, callee, arguments, environment, handlers, expected)
                if variant is not None:
                    return variant
                identity = self.canonical(callee.items[0])
                owner, _, method = identity.rpartition('::')
                if owner in self.records and method == 'new':
                    t = expected or self.record_type(owner)
                    if t.name == 'Ref':
                        if len(arguments) != 1:
                            self.error('type', 'Ref::new expects one argument', node)
                        region = expected.region if expected else (self.region_stack[-1] if self.region_stack else None)
                        if region is None:
                            self.error('type', 'Ref::new needs a region', node)
                        return self.ir(node, 'ref_new', region, self.expression(arguments[0], environment, handlers,
                                                                               t.args[0] if expected else None))
                    if t.name == 'DynArray':
                        if arguments:
                            self.error('type', 'DynArray::new expects no arguments', node)
                        region = t.region or (self.region_stack[-1] if self.region_stack else None)
                        return self.ir(node, 'buffer_new', region, t.args[0])
                    if t.name == 'List':
                        if arguments:
                            self.error('type', 'List::new expects no arguments', node)
                        return self.ir(node, 'list_values', t.args[0], ())
        return super().expression(node, environment, handlers)

    def method(self, node, mode, receiver, method, arguments, environment, handlers):
        name = method.items[0]
        primitive = name in ('get', 'replace', 'set', 'length', 'push', 'freeze', 'remove', 'map', 'cancel')
        kind = 'primitive_method' if primitive and not any(key[1] == name for key in self.methods) else 'method_call'
        return self.ir(node, kind, name, self.expression(receiver, environment, handlers),
                       tuple(self.expression(a, environment, handlers) for a in arguments), mode or '')

    def compile(self, entry='main', *, fixture=True):
        self.collect()
        expressions = {}
        for symbol, declaration in self.definitions.items():
            self.module = self.function_modules[symbol]
            self.values = self.scopes[self.module]
            self.current_function = symbol
            self.references[symbol] = {}
            self.bind_generics(self.function_generics[symbol])
            public, name, parameters, contract, body = declaration.items
            if body is None:
                self.limit('bodyless user function', declaration)
            if public:
                self.public_contract((parameters, contract))
            expression = self.function(declaration, parameters, contract, body, self.values, {})
            expressions[symbol] = expression
            self.signatures[symbol] = self.annotations[id(expression)][0]
            self.check_trait_signature(symbol, declaration)
            if self.structurally_recursive(expression, symbol):
                self.recursive_allowed.add(symbol)
        self.finite_iterators = {symbol for (_, member), (symbol, _) in self.methods.items()
                                 if member == 'next' and symbol in expressions
                                 and self.finite_iterator(expressions[symbol])}
        for key, (symbol, _) in tuple(self.methods.items()):
            if symbol is None:
                continue
            signature = self.signatures[symbol]
            self.methods[key] = (symbol, signature)
            if key[1] == 'cleanup':
                self.cleanup_methods[key[0]] = (symbol, signature)
        self.current_function = None
        globals_ir = []
        for symbol, declaration in self.globals:
            self.module = self.global_modules[symbol]
            self.values = self.scopes[self.module]
            self.bind_generics(())
            _, annotation, initializer = declaration.items
            expected = self.type(annotation) if annotation else UNKNOWN
            initial = self.expression(initializer, self.values, {}, None if expected == UNKNOWN else expected)
            if annotation:
                self.annotations.setdefault(id(initial), []).append(expected)
            globals_ir.append((symbol, expected, initial))
        self.module = self.root_module
        self.values = self.scopes[self.module]
        self.bind_generics(())
        main = self.values.get(entry) if entry is not None else None
        if entry is None:
            expression = self.ir(self.ast, 'unit')
        else:
            label = 'Fixture main' if fixture else f'Python entry {entry}'
            if main not in self.definitions or not self.definitions[main].items[0]:
                self.error('entry', 'Fixture runner requires an exported main function' if fixture else
                           f'Python host requires an exported function {entry}', self.ast)
            declaration = self.definitions[main]
            if self.generics(declaration.items[1]):
                self.error('entry', label + ' cannot be generic', declaration.items[1])
            if declaration.items[2]:
                self.error('entry', label + ' must have no parameters', declaration.items[1])
            if not fixture and self.signatures[main].result != INT:
                self.error('entry', label + ' must return Int', declaration.items[3])
            if fixture and self.signatures[main].result not in (INT, UNIT, BOOL, NAT):
                self.limit('fixture main must return Int, Nat, Bool or Unit', declaration.items[3])
            expression = self.ir(declaration.items[1], 'call', main)
        order, visiting, done, cyclic = [], set(), set(), False
        def visit(symbol):
            nonlocal cyclic
            if symbol in visiting:
                cyclic = True
                return
            if symbol in done:
                return
            visiting.add(symbol)
            for dependency in self.references[symbol]:
                visit(dependency)
            visiting.remove(symbol)
            done.add(symbol)
            order.append(symbol)
        for symbol in expressions:
            visit(symbol)
        if cyclic:
            for symbol in expressions:
                pending, seen = list(self.references[symbol]), set()
                while pending:
                    dependency = pending.pop()
                    if dependency == symbol:
                        if symbol not in self.recursive_allowed and 'diverge' not in self.signatures[symbol].effects.labels:
                            self.error('effect', 'Recursive function requires structural descent or diverge', self.definitions[symbol])
                        break
                    if dependency not in seen:
                        seen.add(dependency)
                        pending.extend(self.references.get(dependency, ()))
        if globals_ir or cyclic or self.methods:
            functions = tuple((s, expressions[s], self.signatures[s]) for s in order)
            expression = self.ir(self.ast, 'definitions', functions, tuple(globals_ir), expression)
        else:
            for symbol in reversed(order):
                expression = self.ir(self.definitions[symbol], 'let', symbol, expressions[symbol], expression)
        checker = SourceChecker(self)
        try:
            program = compile_program(expression, checker=checker, origins=self.origins)
        except InferenceError as error:
            span = self.origins.get(id(error.expression), self.ast.span)
            related = []
            if error.subject in self.declarations:
                related.append(('Binding declared here', self.declarations[error.subject]))
                transferred = checker.transfers.get(error.subject)
                if id(transferred) in self.origins:
                    related.append(('Ownership transferred here', self.origins[id(transferred)]))
            raise Diagnostic(error.code, str(error), span, related) from error
        if entry is not None and (program.inferred.effects.tail or any(
                label not in ('suspend', 'diverge') for label in program.inferred.effects.labels)):
            origin = checker.effect_origin(expressions[main][2], set(program.inferred.effects.labels))
            raise Diagnostic('effect', label + ' requires closed handler evidence; an operation remains unhandled',
                             self.origins.get(id(origin), declaration.items[3].span))
        functions = {str(s): checker.results[id(body)].type for s, body in expressions.items()}
        return SourceProgram(self.ast, expression, program, functions, {str(n): r for n, r in checker.handled_rows.items()})

    def structurally_recursive(self, expression, function, methods=None):
        # Prove descent on one fixed parameter; all other parameters must be
        # unchanged. IR symbols make this independent of source-name shadowing.
        parameters = tuple(name for name, _ in expression[1])
        candidates, invalid = [], False

        def bind(pattern, source, origins, depth=0):
            if source is None:
                return
            if pattern[0] == 'bind':
                origins[pattern[1]] = (source[0], source[1] or depth > 0)
            else:
                children = pattern[3:] if pattern[0] in ('variant_pat', 'record_pat') else pattern[1:]
                for child in children:
                    if isinstance(child, tuple):
                        bind(child, source, origins, depth + 1)

        def walk(term, origins):
            nonlocal invalid
            if not isinstance(term, tuple) or not term:
                return
            if not isinstance(term[0], str):
                for child in term:
                    walk(child, origins)
                return
            kind = term[0]
            if kind == 'var' and term[1] == function:
                invalid = True  # Higher-order recursion needs another proof.
            elif kind == 'for_each' and methods and methods.get(id(term), (None,))[0] == function:
                invalid = True
            elif (kind == 'call' and term[1] == function or
                  kind == 'method_call' and methods and methods.get(id(term), (None,))[0] == function):
                possible = set()
                arguments = (term[2], *term[3]) if kind == 'method_call' else term[2:]
                if len(arguments) == len(parameters):
                    for index, argument in enumerate(arguments):
                        if (argument[0] == 'var' and origins.get(argument[1]) == (index, True)
                                and all(i == index or actual == ('var', parameters[i])
                                        for i, actual in enumerate(arguments))):
                            possible.add(index)
                candidates.append(possible)
                for argument in arguments:
                    walk(argument, origins)
            elif kind == 'match':
                subject, arms = term[1:]
                walk(subject, origins)
                source = origins.get(subject[1]) if subject[0] == 'var' else None
                for pattern, body in arms:
                    local = dict(origins)
                    bind(pattern, source, local)
                    walk(body, local)
            elif kind == 'bindpat':
                pattern, initial, body = term[1:]
                walk(initial, origins)
                local = dict(origins)
                bind(pattern, origins.get(initial[1]) if initial[0] == 'var' else None, local)
                walk(body, local)
            elif kind == 'let':
                name, initial, body = term[1:]
                walk(initial, origins)
                local = dict(origins)
                if initial[0] == 'var' and initial[1] in origins:
                    local[name] = origins[initial[1]]
                walk(body, local)
            else:
                for child in term[1:]:
                    walk(child, origins)
        walk(expression[2], {name: (index, False) for index, name in enumerate(parameters)})
        return bool(candidates) and not invalid and bool(set.intersection(*candidates))

    def finite_iterator(self, expression):
        """Certify only steps whose Item successor is a stored input subterm."""
        if len(expression[1]) != 1:
            return False

        def bind(pattern, origin, known, nested=False):
            if origin is None:
                return
            if pattern[0] == 'bind':
                known[pattern[1]] = origin or nested
            else:
                parts = pattern[3:] if pattern[0] in ('variant_pat', 'record_pat') else pattern[1:]
                for part in parts:
                    if isinstance(part, tuple):
                        bind(part, origin, known, True)

        def returns(term, known):
            kind = term[0]
            if kind == 'variant' and unwrapped(term[1]).name == 'Enum:core::iter::Next':
                if term[2] == 'Done':
                    return True
                return (term[2] == 'Item' and len(term[3]) == 2 and term[3][1][0] == 'var'
                        and known.get(term[3][1][1], False))
            if kind == 'match':
                subject, arms = term[1:]
                origin = known.get(subject[1]) if subject[0] == 'var' else None
                for pattern, body in arms:
                    local = dict(known)
                    bind(pattern, origin, local)
                    if not returns(body, local):
                        return False
                return True
            if kind == 'let':
                name, initial, body = term[1:]
                local = dict(known)
                if initial[0] == 'var' and initial[1] in known:
                    local[name] = known[initial[1]]
                return returns(body, local)
            if kind == 'bindpat':
                pattern, initial, body = term[1:]
                local = dict(known)
                bind(pattern, known.get(initial[1]) if initial[0] == 'var' else None, local)
                return returns(body, local)
            if kind == 'seq':
                return returns(term[-1], known)
            return False

        return returns(expression[2], {expression[1][0][0]: False})
