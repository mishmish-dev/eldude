"""Module and data elaboration layered over the existing handler source lowering."""
from dataclasses import replace
from pathlib import Path

from effect_rows import Row, Var, Solver
from capture_rows import Argument, Variable
from trait_constraints import TraitSolver, Implementation
from handlers import Operation, compile_program, operation_type
from inference import E, Fn, Ty, INT, UNIT, BOOL, InferenceError, capture_free, state, permissions, required_captures
from source_features import NAT, UNKNOWN, substitute, unwrapped
from source_modules import load_modules, STDLIB
from source_pipeline import (Elaborator, SourceChecker, SourceProgram, Host, HOST_TYPES,
                             HOST_FUNCTIONS, OTHER_PRIMITIVES)
from source_syntax import Node, Diagnostic


class SourceElaborator(Elaborator):
    def __init__(self, ast):
        super().__init__(ast)
        self.root_module = self.module
        self.graph = load_modules(ast)
        self.scopes = {m: {} for m in self.graph.modules}
        self.aliases = {m: {} for m in self.graph.modules}
        self.owners, self.named, self.enums, self.traits = {}, {}, {}, {}
        self.variants, self.data_parameters, self.methods, self.cleanup_methods = {}, {}, {}, {}
        self.function_modules, self.function_generics, self.function_self = {}, {}, {}
        self.function_traits, self.effect_arguments = {}, {}
        self.impl_heads, self.impl_contracts = {}, {}
        self.impl_constraints = {}
        self.trait_solver = TraitSolver()
        self.function_constraints = {}
        self.dynamic_methods, self.trait_methods = {}, {}
        self.capture_names = {}
        self.capture_parameter_types = {}
        self.globals, self.global_modules, self.signatures = [], {}, {}
        self.generic_types, self.generic_regions, self.generic_effects = {}, (), {}
        self.generic_captures, self.capture_usage = {}, {}
        self.exit_stack, self.region_stack = [], []
        self.recursive_allowed = set()
        self.types['Nat'] = NAT

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

    def bind_generics(self, parameters):
        types, regions, effects, captures = {}, [], {}, {}
        self.generic_binders = []
        for parameter in parameters:
            if parameter.kind == 'name':
                name = parameter.items[0]
                if name in types:
                    self.error('name', 'Duplicate type parameter', parameter)
                types[name] = Ty('$' + name)
                self.generic_binders.append(('type', name))
            elif parameter.kind == 'generic_parameter':
                prefix, name = parameter.items
                self.generic_binders.append(({'@': 'region', '!': 'effect', '..': 'capture', '#': 'nat'}[prefix], name.items[0]))
                if prefix == '@':
                    regions.append(name.items[0])
                elif prefix == '!':
                    effects[name.items[0]] = Var(name.items[0], rigid=True)
                elif prefix == '..':
                    captures[name.items[0]] = Variable(name.items[0])
        self.generic_types, self.generic_regions, self.generic_effects = types, tuple(regions), effects
        self.generic_captures = captures

    def is_library(self, module):
        path = Path(self.graph.modules[module].span.filename)
        return path.is_relative_to(STDLIB)

    def constraints(self, nodes):
        result = []
        for node in nodes:
            if node.kind == 'type_equality':
                result.append(Ty('Equality', tuple(self.type(t) for t in node.items)))
            elif node.items[0].kind != 'capture_variable':
                subject, bounds = node.items
                for bound in bounds:
                    identity = self.canonical(bound.items[0])
                    if identity not in self.traits and identity not in ('Dup', 'Discard', 'NonAbandoning'):
                        self.error('name', 'Unknown trait constraint ' + identity, bound)
                    arguments = tuple(self.argument_term(a) for a in bound.items[1]) if bound.kind == 'applied_type' else ()
                    result.append(Ty('Trait:' + identity, (self.type(subject), *arguments)))
        return tuple(result)

    def argument_term(self, node):
        if node.kind == 'region_type':
            return Ty('Region', region=node.items[0].items[0])
        if node.kind == 'effect_row':
            entries, tail = node.items
            contract = Node('contract', node.span, (Node('type', node.span, ('Unit',)),
                            entries + ((Node('effect_tail', tail.span, tail.items),) if tail else ())))
            row = self.contract(contract)[1]
            labels = tuple(Ty('state', region=l[7:-1]) if l.startswith('state<@') else Ty(l) for l in row.labels)
            return Ty('Effects', tuple(sorted(labels, key=repr)) + ((Ty('$!' + row.tail.name),) if row.tail else ()))
        if node.kind == 'capture_variable':
            return Ty('$..' + node.items[0].items[0])
        if node.kind == 'capture_set':
            return Ty('Captures', tuple(sorted((self.argument_term(c) if c.kind in ('region_type', 'capture_variable')
                                               else Ty('Capture:' + c.items[0]) for c in node.items[0]), key=repr)))
        if node.kind in ('int', 'nat'):
            return Ty('Nat:' + str(node.items[0]))
        return self.type(node)

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
                if spelling in self.aliases[module] or spelling in ('Int', 'Int64', 'Bool', 'Unit', 'Nat'):
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
                    if self.is_library(module) and kind == 'function':
                        self.scopes[module][spelling] = Host(module + '::' + spelling)
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
        self.infer_enum_usage()
        for identity, declaration in tuple(self.effects.items()):
            if not self.generics(declaration.items[1]):
                self.instantiate_effect(identity, ())
        # Source impl bodies become ordinary named functions; opaque library methods
        # use the explicit primitive contracts in FeatureChecker.
        for module in self.graph.order:
            if self.is_library(module):
                continue
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
                    parameter_name = parameter.items[0] if parameter.kind == 'name' else parameter.items[1].items[0]
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
                    arguments = tuple(self.argument_term(a) for a in trait.items[1]) if trait.kind == 'applied_type' else ()
                    impl = Implementation(Ty('Trait:' + trait_name, (target, *arguments)),
                                          tuple(self.generic_types), self.generic_regions, self.constraints(constraints))
                    try:
                        self.trait_solver.add(impl)
                    except ValueError as error:
                        self.error('semantic', str(error), implementation)
                if trait and head in self.impl_heads:
                    previous_target = self.impl_heads[head]
                    if previous_target != target:
                        self.limit('multiple specialized implementations of one trait and nominal type', implementation)
                    self.error('semantic', 'Duplicate trait implementation', implementation)
                if trait:
                    self.impl_heads[head] = target
                    self.impl_contracts[head] = Fn((target,), UNIT, Row(),
                                                  type_vars=tuple(self.generic_types), regions=self.generic_regions)
                    self.impl_constraints[head] = constraints
                equations = {m.items[0].items[0]: self.type(m.items[1]) for m in members if m.kind == 'associated_type'}
                for method in members:
                    if method.kind != 'function':
                        continue
                    symbol = self.symbol(method.items[1])
                    self.definitions[symbol] = method
                    self.function_modules[symbol] = module
                    self.function_generics[symbol] = parameters + self.generics(method.items[1])
                    self.function_self[symbol] = (target, equations)
                    self.function_constraints[symbol] = constraints
                    if impl is not None:
                        impl.methods[method.items[1].items[0]] = symbol
                        impl.equations = equations
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
                        if self.function_self[previous_symbol][0] != target:
                            self.limit('multiple specialized methods for one nominal type', method)
                        self.error('semantic', 'Duplicate or ambiguous implementation method', method.items[1])
                    self.methods[method_key] = (symbol, None)
        self.module = self.root_module
        self.values = self.scopes[self.module]
        self.bind_generics(())

    def infer_enum_usage(self):
        # Concrete payload obligations propagate through recursive nominal
        # declarations. Generic obligations remain represented by Enum.args.
        usage = {}
        for identity, declaration in self.enums.items():
            nominal = unwrapped(self.types[identity]).name
            modifier = declaration.items[3] if len(declaration.items) > 3 else None
            usage[nominal] = (modifier not in ('linear', 'affine'), modifier != 'linear')

        def payload_permissions(t):
            if isinstance(t, Fn):
                return permissions(t)
            if t.name.startswith('Any:'):
                return permissions(t)
            if t.name.startswith('$'):
                return True, True
            if t.name in usage:
                parts = [payload_permissions(a) for a in t.args]
                return (usage[t.name][0] and all(p[0] for p in parts),
                        usage[t.name][1] and all(p[1] for p in parts))
            if t.name.startswith('Record:'):
                parts = [payload_permissions(f.args[0]) for f in t.args]
            elif t.name in ('Owned', 'Linear'):
                return False, False
            elif t.name in ('Ref', 'View', 'Mut'):
                return True, True
            else:
                parts = [payload_permissions(a) for a in t.args]
            return (t.name not in ('Affine', 'Task', 'DynArray') and all(p[0] for p in parts),
                    all(p[1] for p in parts))

        changed = True
        while changed:
            changed = False
            for nominal, variants in self.variants.items():
                parts = [payload_permissions(field) for fields in variants.values() for field in fields]
                previous = usage[nominal]
                inferred = (previous[0] and all(p[0] for p in parts), previous[1] and all(p[1] for p in parts))
                if inferred != previous:
                    usage[nominal] = inferred
                    changed = True

        def refresh(t):
            if isinstance(t, Fn):
                return replace(t, parameters=tuple(refresh(p) for p in t.parameters), result=refresh(t.result))
            result = replace(t, args=tuple(refresh(a) for a in t.args))
            if result.name in ('Linear', 'Affine') and result.args[0].name in ('Linear', 'Affine'):
                modifier = 'Linear' if 'Linear' in (result.name, result.args[0].name) else 'Affine'
                return Ty(modifier, (unwrapped(result.args[0]),))
            if result.name in usage and result.name not in ('Option', 'Result'):
                dup, discard = usage[result.name]
                if not discard:
                    return Ty('Linear', (result,))
                if not dup:
                    return Ty('Affine', (result,))
            return result
        self.types = {name: refresh(t) for name, t in self.types.items()}
        self.variants = {name: {tag: tuple(refresh(t) for t in fields) for tag, fields in variants.items()}
                         for name, variants in self.variants.items()}

    def record_type(self, identity):
        if identity in self.types:
            return self.types[identity]
        declaration = self.records[identity]
        module = self.owners[id(declaration)]
        if module in ('state::ref', 'collections::dyn_array', 'collections::list', 'task') and declaration.items[2] is None:
            name = declaration.items[1].items[0]
            parameters = self.generics(declaration.items[1])
            args = tuple(Ty('$' + p.items[0]) for p in parameters if p.kind == 'name')
            region = next((p.items[1].items[0] for p in parameters if p.kind == 'generic_parameter' and p.items[0] == '@'), None)
            self.types[identity] = Ty(name, args, region)
            return self.types[identity]
        if identity in self.resolving_records:
            self.limit('recursive record representations', declaration)
        old = self.module, self.generic_types, self.generic_regions, self.generic_effects
        self.module = module
        self.bind_generics(self.generics(declaration.items[1]))
        self.resolving_records.add(identity)
        fields = []
        for member in declaration.items[2] or ():
            name, annotation = member[:2]
            if name.items[0] in {f.name for f in fields}:
                self.error('name', 'Duplicate record field', name)
            fields.append(Ty(name.items[0], (self.type(annotation),)))
        result = Ty('Record:' + self.nominal(identity), tuple(fields))
        if len(declaration.items) > 3:
            result = Ty(declaration.items[3].title(), (result,))
        self.types[identity] = result
        self.resolving_records.remove(identity)
        self.module, self.generic_types, self.generic_regions, self.generic_effects = old
        return result

    def type(self, node):
        if node.kind == 'projection_type':
            receiver, member, arguments = node.items
            if arguments:
                self.limit('GAT projection normalization', node)
            candidates = [name for name, trait in self.traits.items()
                          if any(m.kind == 'associated_type' and m.items[0].items[0] == member.items[0] for m in trait.items[2])]
            if len(candidates) != 1:
                self.error('type', 'Associated projection needs an unambiguous trait', node)
            return Ty('Projection:' + candidates[0] + ':' + member.items[0], (self.type(receiver),))
        if node.kind == 'access_type':
            return Ty(node.items[0].title(), (self.type(node.items[1]),))
        if node.kind == 'tuple_type':
            return Ty('Tuple', tuple(self.type(t) for t in node.items[0]))
        if node.kind in ('type', 'applied_type'):
            spelling = node.items[0]
            if spelling in self.generic_types:
                return self.generic_types[spelling]
            if spelling.startswith('Self::') and self.current_function in self.function_self:
                equations = self.function_self[self.current_function][1]
                return equations.get(spelling[6:], UNKNOWN)
            if '::' in spelling and spelling.split('::')[0] in self.generic_types:
                receiver, member = spelling.rsplit('::', 1)
                return self.type(Node('projection_type', node.span,
                                      (Node('type', node.span, (receiver,)), Node('name', node.span, (member,)), ())))
            if spelling == 'Self' and self.current_function in self.function_self:
                return self.function_self[self.current_function][0]
            name = self.canonical(spelling)
            if name in self.records:
                template = self.record_type(name)
            elif name in self.types:
                template = self.types[name]
            elif name in self.named and self.named[name].kind == 'type_alias':
                template = self.type(self.named[name].items[2])
            else:
                if name in OTHER_PRIMITIVES:
                    self.limit('type ' + name + ' does not execute in this profile', node)
                self.error('name', 'Unknown type ' + name, node)
            if node.kind == 'applied_type':
                declaration = self.named.get(name)
                parameters = self.generics(declaration.items[1]) if declaration else ()
                arguments = node.items[1]
                if len(arguments) != len(parameters):
                    self.error('type', 'Generic type argument arity mismatch', node)
                types, regions = {}, {}
                for parameter, argument in zip(parameters, arguments):
                    if parameter.kind == 'name':
                        types[parameter.items[0]] = self.type(argument)
                    elif parameter.items[0] == '@':
                        if argument.kind != 'region_type':
                            self.error('type', 'Expected region argument', argument)
                        regions[parameter.items[1].items[0]] = argument.items[0].items[0]
                return substitute(template, types, regions)
            return template
        if node.kind == 'fn_type':
            parameters, contract = node.items
            previous = self.capture_names
            self.capture_names = {name: replace(source, depth=source.depth + 1) if isinstance(source, Argument) else source
                                  for name, source in previous.items()}
            result, effects = self.contract(contract)
            self.capture_names = previous
            captures = self.capture_contract(contract)
            bound = frozenset() if capture_free(result) else frozenset({'env'} | {f'arg:{i}' for i in range(len(parameters))})
            return Fn(tuple(self.type(p) for p in parameters), result, effects, bound,
                      dup=all(c.dup if isinstance(c, Argument) else 'Dup' in self.capture_usage.get(c.name, ())
                              for c in captures if isinstance(c, (Argument, Variable))),
                      discard=all(c.discard if isinstance(c, Argument) else 'Discard' in self.capture_usage.get(c.name, ())
                                  for c in captures if isinstance(c, (Argument, Variable))), captures=captures)
        if node.kind == 'any_type':
            return self.existential_type(node)
        self.limit('type form ' + node.kind, node)

    def capture_contract(self, node):
        captures = set()
        for entry in node.items[2] if len(node.items) > 2 else ():
            if entry.kind == 'capture_variable':
                name = entry.items[0].items[0]
                if name not in self.generic_captures:
                    self.error('name', 'Unknown capture row ' + name, entry)
                captures.add(self.generic_captures[name])
                continue
            if entry.kind == 'region_type':
                name = entry.items[0].items[0]
                if name not in self.generic_regions and name not in self.region_stack:
                    self.error('name', 'Unknown capture region ' + name, entry)
                captures.add(name)
            else:
                name = entry.items[0]
                if name not in self.capture_names:
                    self.error('name', 'Unknown capture ' + name, entry)
                source = self.capture_names[name]
                if not isinstance(source, (str, Argument)):
                    self.limit('fixture primitives in capture contracts', entry)
                captures.add(source)
                if isinstance(source, Argument):
                    captures.update(required_captures(self.capture_parameter_types[name]))
        return frozenset(captures)

    def existential_type(self, node):
        bounds = node.items[0]
        trait_name = self.canonical(bounds[0].items[0])
        if trait_name not in self.traits:
            self.error('name', 'Unknown trait ' + trait_name, bounds[0])
        usage = [b.items[0] for b in bounds[1:]]
        if any(b.kind != 'type' or b.items[0] not in ('Dup', 'Discard') for b in bounds[1:]):
            self.limit('existential packages require one trait plus Dup/Discard', node)
        t = Ty('Any:' + trait_name, tuple(Ty(u) for u in sorted(set(usage))))
        trait = self.traits[trait_name]
        if bounds[0].kind != 'type' or self.generics(trait.items[1]):
            self.limit('generic existential trait interfaces', node)
        if any(m.kind != 'function' for m in trait.items[2]):
            self.limit('existential associated types', node)
        if len(trait.items[1].items) > 2:
            self.limit('existential trait constraints', node)
        if t.name in self.dynamic_methods:
            return t
        methods = {}
        self.dynamic_methods[t.name] = methods
        def mentions_self(part):
            if isinstance(part, Node):
                return mentions_self(part.items)
            if isinstance(part, tuple):
                return any(mentions_self(p) for p in part)
            return isinstance(part, str) and (part == 'Self' or part.startswith('Self::'))
        previous = (self.module, self.current_function, self.generic_types,
                    self.generic_regions, self.generic_effects, self.capture_names)
        self.module = self.owners[id(trait)]
        self.current_function = None
        self.bind_generics(())
        self.capture_names = {}
        for member in trait.items[2]:
            _, name, parameters, contract, _ = member.items
            if (self.generics(name) or not parameters or parameters[0].items[0].items[0] != 'self'
                    or sum(p.items[0].items[0] == 'self' for p in parameters) != 1
                    or parameters[0].items[1] is not None or mentions_self((parameters[1:], contract, name))):
                self.error('type', 'Trait is not DynCompatible', member)
            if len(name.items) > 2:
                self.limit('existential method constraints', member)
            receiver = Ty(parameters[0].items[2].title(), (t,)) if len(parameters[0].items) == 3 else t
            if isinstance(receiver, Ty) and receiver.name == 'Mut':
                self.limit('existential mut receivers', member)
            rest = tuple(Ty(p.items[2].title(), (self.type(p.items[1]),)) if len(p.items) == 3
                         else self.type(p.items[1]) for p in parameters[1:])
            result, effects = self.contract(contract)
            bound = frozenset() if capture_free(result) else frozenset(f'arg:{i}' for i in range(len(parameters)))
            methods[name.items[0]] = Fn((receiver, *rest), result, effects, bound,
                                       captures=self.capture_contract(contract))
        (self.module, self.current_function, self.generic_types,
         self.generic_regions, self.generic_effects, self.capture_names) = previous
        return t

    def instantiate_effect(self, identity, arguments):
        declaration = self.effects[identity]
        key = identity if not arguments else identity + '<' + ','.join(repr(t) for t in arguments) + '>'
        if key in self.operations:
            return key
        parameters = self.generics(declaration.items[1])
        if len(parameters) != len(arguments):
            self.error('type', 'Effect type argument arity mismatch', declaration.items[1])
        old = self.module, self.generic_types
        self.module = self.owners[id(declaration)]
        self.generic_types = dict(zip((p.items[0] for p in parameters), arguments))
        operations = {}
        for operation in declaration.items[2]:
            mode, name, parameters, result = operation.items
            if name.items[0] in operations:
                self.error('name', 'Duplicate operation declaration', name)
            names, parameter_types = set(), []
            for parameter in parameters:
                parameter_name, annotation = parameter.items[:2]
                if parameter_name.items[0] != '_' and parameter_name.items[0] in names:
                    self.error('name', 'Duplicate operation parameter', parameter_name)
                names.add(parameter_name.items[0])
                t = self.type(annotation)
                if not self.operation_data(t):
                    self.limit('operation parameters must currently be scalar data', annotation)
                parameter_types.append(t)
            result_type = self.type(result)
            if not self.operation_data(result_type):
                self.limit('operation results must currently be scalar data', result)
            operations[name.items[0]] = Operation(mode, result_type, tuple(parameter_types))
        self.operations[key] = operations
        self.effects[key] = declaration
        self.module, self.generic_types = old
        return key

    def effect_family(self, node):
        identity = self.canonical(node.items[0])
        if identity not in self.effects:
            self.error('name', 'Unknown effect family ' + identity, node)
        args = tuple(self.type(t) for t in node.items[1]) if node.kind == 'applied_type' else ()
        return self.instantiate_effect(identity, args)

    def contract(self, node):
        result, entries = node.items[:2]
        labels, tail = [], None
        for entry in entries:
            name = entry.items[0]
            if entry.kind == 'effect_tail':
                if name in self.effect_arguments:
                    row = self.effect_arguments[name]
                    labels.extend(row.labels)
                    tail = row.tail
                    continue
                if name not in self.generic_effects:
                    self.error('name', 'Unknown effect row variable ' + name, entry)
                tail = self.generic_effects[name]
            elif name in ('suspend', 'diverge'):
                labels.append(name)
            elif name == 'state' and entry.kind == 'applied_type':
                labels.append(state(entry.items[1][0].items[0].items[0]))
            else:
                labels.append(self.effect_family(entry))
        return self.type(result), Row(tuple(labels), tail)

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
            name = node.items[1]
            for constraint in name.items[2] if len(name.items) > 2 else ():
                if constraint.kind == 'bound' and constraint.items[0].kind == 'capture_variable':
                    subject, bounds = constraint.items
                    self.capture_usage[subject.items[0].items[0]] = {b.items[0] for b in bounds}
        name = node.items[1] if node.kind == 'function' else None
        constraints = self.constraints(self.function_constraints.get(self.current_function, ()) +
                                       (name.items[2] if name and len(name.items) > 2 else ())) if node.kind == 'function' else ()
        local, typed, names = dict(environment), [], set()
        for parameter in parameters:
            name, annotation = parameter.items[:2]
            if name.items[0] in names:
                self.error('name', 'Duplicate parameter', name)
            names.add(name.items[0])
            if annotation is None:
                if name.items[0] == 'self' and self.current_function in self.function_self:
                    t = self.function_self[self.current_function][0]
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
                           type_vars=tuple(self.generic_types) if node.kind == 'function' else (),
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
                return E('variant_pat', unwrapped(self.types[family]).name, tag,
                         *(self.pattern(p, environment) for p in fields))
            if identity in self.records:
                t = unwrapped(self.record_type(identity))
                return E('record_pat', t.name, tuple(f.items[0] for f, _ in fields),
                         *(self.pattern(p, environment) for _, p in fields))
            family, _, tag = identity.rpartition('::')
            if family not in self.enums:
                self.error('name', 'Unknown pattern constructor ' + identity, path)
            declaration = next((v for v in self.enums[family].items[2] if v.items[1].items[0] == tag), None)
            if declaration is None or declaration.items[3] != 'record':
                self.error('type', 'Expected record variant pattern', path)
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
            for argument in arguments:
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
                    row = Row(tuple(self.effect_entry(e) for e in labels), self.generic_effects[tail.items[0]] if tail else None)
                    resolved.append(('effect', row))
                else:
                    resolved.append(('type', self.type(argument)))
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
                        return self.variant(node, path, tuple(provided[f[0].items[0]] for f in declaration.items[2]), environment, handlers, expected)
                self.error('name', 'Unknown record ' + identity, path)
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
                        region = t.region or (self.region_stack[-1] if self.region_stack else None)
                        if region is None:
                            self.error('type', 'Ref::new needs a region', node)
                        return self.ir(node, 'ref_new', region, self.expression(arguments[0], environment, handlers, t.args[0]))
                    if t.name == 'DynArray':
                        if arguments:
                            self.error('type', 'DynArray::new expects no arguments', node)
                        region = t.region or (self.region_stack[-1] if self.region_stack else None)
                        return self.ir(node, 'buffer_new', region, t.args[0])
                    if t.name == 'List':
                        return self.ir(node, 'list_values', t.args[0], ())
                symbol = environment.get(callee.items[0])
                if isinstance(symbol, Host) and symbol.name == 'task::join2':
                    if len(arguments) != 2:
                        self.error('type', 'join2 expects two callables', node)
                    left, right = (self.symbol(Node('name', node.span, (n,))) for n in ('left', 'right'))
                    a, b = (self.symbol(Node('name', node.span, (n,))) for n in ('first', 'second'))
                    key = 'taskgroup:' + str(self.serial)
                    body = self.ir(node, 'tuple', self.ir(node, 'await', self.ir(node, 'var', a)), self.ir(node, 'await', self.ir(node, 'var', b)))
                    body = self.ir(node, 'let', b, self.ir(node, 'spawn', self.ir(node, 'var', right)), body)
                    body = self.ir(node, 'let', a, self.ir(node, 'spawn', self.ir(node, 'var', left)), body)
                    body = self.ir(node, 'taskgroup', key, body)
                    body = self.ir(node, 'let', right, self.expression(arguments[1], environment, handlers), body)
                    return self.ir(node, 'let', left, self.expression(arguments[0], environment, handlers), body)
        return super().expression(node, environment, handlers)

    def method(self, node, mode, receiver, method, arguments, environment, handlers):
        name = method.items[0]
        primitive = name in ('get', 'replace', 'set', 'length', 'push', 'freeze', 'remove', 'map', 'cancel')
        kind = 'primitive_method' if primitive and not any(key[1] == name for key in self.methods) else 'method_call'
        return self.ir(node, kind, name, self.expression(receiver, environment, handlers),
                       tuple(self.expression(a, environment, handlers) for a in arguments), mode or '')

    def compile(self):
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
        for key, (symbol, _) in tuple(self.methods.items()):
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
        main = self.values.get('main')
        if main not in self.definitions or not self.definitions[main].items[0]:
            self.error('entry', 'Fixture runner requires an exported main function', self.ast)
        declaration = self.definitions[main]
        if self.generics(declaration.items[1]):
            self.error('entry', 'Fixture main cannot be generic', declaration.items[1])
        if declaration.items[2]:
            self.error('entry', 'Fixture main must have no parameters', declaration.items[1])
        if self.signatures[main].result not in (INT, UNIT, BOOL, NAT):
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
        if program.inferred.effects.tail or any(label not in ('suspend', 'diverge') for label in program.inferred.effects.labels):
            origin = checker.effect_origin(expressions[main][2], set(program.inferred.effects.labels))
            raise Diagnostic('effect', 'Fixture main requires closed handler evidence; an operation remains unhandled',
                             self.origins.get(id(origin), declaration.items[3].span))
        functions = {str(s): checker.results[id(body)].type for s, body in expressions.items()}
        return SourceProgram(self.ast, expression, program, functions, {str(n): r for n, r in checker.handled_rows.items()})

    def check_trait_signature(self, symbol, declaration):
        if symbol not in self.function_traits:
            return
        requirement, trait, applied = self.function_traits[symbol]
        previous_module, previous_types, previous_rows = self.module, self.generic_types, self.effect_arguments
        arguments = applied.items[1] if applied.kind == 'applied_type' else ()
        parameters = self.generics(trait.items[1])
        if len(parameters) != len(arguments):
            self.error('type', 'Trait argument arity mismatch', applied)
        mapped_types, mapped_rows = {}, {}
        for parameter, argument in zip(parameters, arguments):
            if parameter.kind == 'name':
                mapped_types[parameter.items[0]] = self.type(argument)
            elif parameter.kind == 'generic_parameter' and parameter.items[0] == '!':
                if argument.kind != 'effect_row':
                    self.error('type', 'Trait expects an effect row', argument)
                entries, tail = argument.items
                if tail:
                    entries += (Node('effect_tail', tail.span, tail.items),)
                contract = Node('contract', argument.span, (Node('type', argument.span, ('Unit',)), entries))
                mapped_rows[parameter.items[1].items[0]] = self.contract(contract)[1]
        self.module = self.owners[id(trait)]
        self.generic_types = previous_types | mapped_types
        self.effect_arguments = previous_rows | mapped_rows
        expected_parameters = []
        for parameter in requirement.items[2]:
            name, annotation = parameter.items[:2]
            t = self.type(annotation) if annotation else self.function_self[symbol][0]
            if len(parameter.items) == 3:
                t = Ty(parameter.items[2].title(), (t,))
            expected_parameters.append(t)
        result, effects = self.contract(requirement.items[3])
        actual = self.signatures[symbol]
        self.module, self.generic_types, self.effect_arguments = previous_module, previous_types, previous_rows
        allowed = self.constraints(self.function_constraints.get(symbol, ()))
        method_constraints = requirement.items[1].items[2] if len(requirement.items[1].items) > 2 else ()
        allowed += self.constraints(method_constraints)
        for constraint in actual.constraints:
            try:
                self.trait_solver.check(constraint, allowed)
            except ValueError:
                self.error('semantic', 'Implementation method has stronger prerequisites than its trait declaration', declaration.items[1])
        if actual.parameters != tuple(expected_parameters) or actual.result != result:
            self.error('type', 'Method signature does not match its trait declaration', declaration.items[3])
        solver = Solver()
        try:
            solver.unify(effects, solver.weaken(actual.effects))
        except ValueError:
            self.error('effect', 'Method effects exceed its trait declaration', declaration.items[3])

    def operation_data(self, t, seen=frozenset()):
        if not operation_type(t):
            return False
        if t in seen:
            return True
        fields = self.variants.get(t.name)
        if fields is not None:
            types = dict(zip(self.data_parameters.get(t.name, ()), t.args))
            return all(self.operation_data(substitute(field, types), seen | {t})
                       for payload in fields.values() for field in payload)
        return all(self.operation_data(argument, seen | {t}) for argument in t.args)

    def structurally_recursive(self, expression, function):
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
            elif kind == 'call' and term[1] == function:
                possible = set()
                arguments = term[2:]
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
