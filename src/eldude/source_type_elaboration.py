"""Resolve source types, generics, capture/effect contracts, and trait interfaces."""
from dataclasses import replace

from eldude.effect_rows import Row, Var, Solver
from eldude.capture_rows import Argument, Variable
from eldude.handlers import Operation, operation_type
from eldude.inference import Fn, Ty, permissions, state, capture_free, required_captures
from eldude.source_lowering import Elaborator
from eldude.source_model import Node
from eldude.source_types import UNKNOWN, OTHER_PRIMITIVES, substitute, unwrapped


class TypeElaborator(Elaborator):
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
                elif prefix == '#':
                    types[name.items[0]] = Ty('$#' + name.items[0])
            elif parameter.kind == 'constructor_parameter':
                name = parameter.items[0].items[0]
                types[name] = Ty('$' + name)
                self.generic_binders.append(('constructor', name))
        self.generic_types, self.generic_regions, self.generic_effects = types, tuple(regions), effects
        self.generic_captures = captures


    def constraints(self, nodes):
        result = []
        for node in nodes:
            if node.kind == 'type_equality':
                result.append(Ty('Equality', tuple(self.type(t) for t in node.items)))
            else:
                subject, bounds = node.items
                row_subject = subject.kind == 'capture_variable'
                effect_subject = subject.kind == 'type' and subject.items[0] in self.generic_effects
                target = self.argument_term(subject) if row_subject else Ty('Effects', (Ty('$!' + subject.items[0]),)) if effect_subject else self.type(subject)
                for bound in bounds:
                    identity = self.canonical(bound.items[0])
                    if identity not in self.traits and identity not in ('Dup', 'Discard', 'NonAbandoning'):
                        self.error('name', 'Unknown trait constraint ' + identity, bound)
                    arguments = self.trait_arguments(self.traits[identity], bound.items[1] if bound.kind == 'applied_type' else ()) if identity in self.traits else ()
                    if (row_subject and identity not in ('Dup', 'Discard') or effect_subject and identity != 'NonAbandoning'
                            or identity == 'NonAbandoning' and not effect_subject):
                        self.error('type', 'Constraint subject kind mismatch', subject)
                    result.append(Ty('Trait:' + identity, (target, *arguments)))
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
            if not labels and row.tail:
                return Ty('$!' + row.tail.name)
            return Ty('Effects', tuple(sorted(labels, key=repr)) + ((Ty('$!' + row.tail.name),) if row.tail else ()))
        if node.kind == 'capture_variable':
            name = node.items[0].items[0]
            if name in self.capture_arguments:
                row = self.capture_arguments[name]
                if len(row) == 1 and isinstance(next(iter(row)), Variable):
                    return Ty('$..' + next(iter(row)).name)
                return Ty('Captures', tuple(sorted((Ty('Region', region=c) if isinstance(c, str) else Ty('Capture:' + str(c)) for c in row), key=repr)))
            return Ty('$..' + name)
        if node.kind == 'capture_set':
            return Ty('Captures', tuple(sorted((self.argument_term(c) if c.kind in ('region_type', 'capture_variable')
                                               else Ty('Capture:' + c.items[0]) for c in node.items[0]), key=repr)))
        if node.kind in ('int', 'nat'):
            return Ty('Nat:' + str(node.items[0]))
        return self.type(node)


    def trait_arguments(self, trait, arguments):
        parameters = self.generics(trait.items[1])
        if len(parameters) != len(arguments):
            self.error('type', 'Trait argument arity mismatch', trait.items[1])
        terms = []
        for parameter, argument in zip(parameters, arguments):
            if parameter.kind == 'name':
                if argument.kind not in ('type', 'applied_type', 'tuple_type', 'fn_type', 'any_type'):
                    self.error('type', 'Trait argument kind mismatch: expected type', argument)
                terms.append(self.type_argument(argument))
            elif parameter.kind == 'constructor_parameter':
                terms.append(self.constructor_argument(parameter, argument))
            else:
                prefix = parameter.items[0]
                kinds = {'@': ('region_type',), '!': ('effect_row',), '..': ('capture_set', 'capture_variable', 'effect_row'), '#': ('int', 'nat', 'type')}
                if argument.kind not in kinds[prefix]:
                    self.error('type', 'Trait argument kind mismatch', argument)
                if prefix == '..' and argument.kind == 'effect_row':
                    if argument.items != ((), None):
                        self.error('type', 'Trait argument kind mismatch: expected capture row', argument)
                    terms.append(Ty('Captures'))
                else:
                    term = self.argument_term(argument)
                    if prefix == '#' and not term.name.startswith(('Nat:', '$#')):
                        self.error('type', 'Trait argument kind mismatch: expected natural index', argument)
                    if prefix == '@' and term.region not in self.generic_regions and term.region not in self.region_stack:
                        self.error('name', 'Unknown region argument ' + term.region, argument)
                    terms.append(term)
        return tuple(terms)


    def type_argument(self, argument):
        if argument.kind == 'type':
            name = argument.items[0]
            if name in self.generic_types:
                term = self.generic_types[name]
                kinds = dict((n, k) for k, n in self.generic_binders)
                kind = kinds.get(term.name[1:], kinds.get(name, 'type')) if term.name.startswith('$') else 'type'
                if kind != 'type' or term.name.startswith('$#'):
                    self.error('type', 'Generic argument kind mismatch: expected type', argument)
            else:
                declaration = self.named.get(self.canonical(name))
                if declaration and self.generics(declaration.items[1]):
                    self.error('type', 'Generic argument kind mismatch: expected type, got constructor', argument)
        return self.type(argument)


    def constructor_argument(self, parameter, argument):
        if argument.kind != 'type':
            self.error('type', 'Generic argument kind mismatch: expected constructor', argument)
        name = argument.items[0]
        if name in self.generic_types and self.generic_types[name].name.startswith('$'):
            if dict((n, k) for k, n in self.generic_binders).get(name) != 'constructor':
                self.error('type', 'Generic argument kind mismatch: expected constructor', argument)
            return self.generic_types[name]
        declaration = self.named.get(self.canonical(name))
        arity = len([p for p in self.generics(declaration.items[1]) if p.kind == 'name']) if declaration else 0
        if arity != len(parameter.items[1]):
            self.error('type', 'Constructor argument arity mismatch', argument)
        return Ty('Constructor:' + unwrapped(self.type(argument)).name)


    def apply_trait_arguments(self, trait, arguments):
        terms = self.trait_arguments(trait, arguments)
        for parameter, argument, term in zip(self.generics(trait.items[1]), arguments, terms):
            if parameter.kind in ('name', 'constructor_parameter'):
                name = parameter.items[0] if parameter.kind == 'name' else parameter.items[0].items[0]
                self.generic_types[name] = Ty(term.name.removeprefix('Constructor:')) if parameter.kind == 'constructor_parameter' else term
            else:
                prefix, name = parameter.items
                name = name.items[0]
                if prefix == '@':
                    self.region_arguments[name] = term.region
                elif prefix == '!':
                    entries, tail = argument.items
                    contract = Node('contract', argument.span, (Node('type', argument.span, ('Unit',)),
                                    entries + ((Node('effect_tail', tail.span, tail.items),) if tail else ())))
                    self.effect_arguments[name] = self.contract(contract)[1]
                elif prefix == '..':
                    entries = argument.items[0] if argument.kind == 'capture_set' else (argument,) if argument.kind == 'capture_variable' else ()
                    self.capture_arguments[name] = self.capture_contract(Node('contract', argument.span, (None, (), entries)))
                elif prefix == '#':
                    self.generic_types[name] = term
        return terms


    def trait_prerequisites(self, trait, arguments, target):
        keys = ('generic_types', 'region_arguments', 'effect_arguments', 'capture_arguments', 'interface_self')
        previous = {key: getattr(self, key) for key in keys}
        self.generic_types = dict(self.generic_types)
        self.region_arguments, self.effect_arguments, self.capture_arguments = {}, {}, {}
        self.apply_trait_arguments(trait, arguments)
        self.interface_self = target
        try:
            return self.constraints(trait.items[1].items[2] if len(trait.items[1].items) > 2 else ())
        finally:
            self.__dict__.update(previous)


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
        keys = ('module', 'generic_types', 'generic_regions', 'generic_effects', 'generic_captures', 'generic_binders')
        old = {key: getattr(self, key) for key in keys}
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
        self.__dict__.update(old)
        return result


    def associated_equation(self, name):
        if name in self.resolving_equations:
            self.error('semantic', 'Cyclic local associated alias', self.equation_sources[name])
        if name not in self.associated_bindings:
            self.resolving_equations.add(name)
            try:
                self.associated_bindings[name] = self.type(self.equation_sources[name])
            finally:
                self.resolving_equations.remove(name)
        return self.associated_bindings[name]


    def type(self, node):
        if node.kind == 'projection_type':
            receiver, member, arguments = node.items
            if arguments:
                self.limit('GAT projection normalization', node)
            candidates = [name for name, trait in self.traits.items()
                          if any(m.kind == 'associated_type' and m.items[0].items[0] == member.items[0] for m in trait.items[2])]
            target = self.type(receiver)
            evidence = self.function_evidence.get(self.current_function, ()) + self.projection_evidence
            nodes = self.function_constraints.get(self.current_function, ())
            if self.current_function in self.definitions:
                name = self.definitions[self.current_function].items[1]
                nodes += name.items[2] if len(name.items) > 2 else ()
            for constraint in nodes:
                if constraint.kind != 'bound' or constraint.items[0].kind == 'capture_variable':
                    continue
                subject, bounds = constraint.items
                if subject.kind == 'type' and subject.items[0] in self.generic_effects:
                    continue
                for bound in bounds:
                    name = self.canonical(bound.items[0])
                    if name in candidates:
                        terms = self.trait_arguments(self.traits[name], bound.items[1] if bound.kind == 'applied_type' else ())
                        evidence += (Ty('Trait:' + name, (self.type(subject), *terms)),)
            visible = {e.name[6:] for e in evidence if e.name.startswith('Trait:') and e.name[6:] in candidates and e.args[0] == target}
            if visible:
                candidates = sorted(visible)
            if len(candidates) != 1:
                self.error('type', 'Associated projection needs an unambiguous trait', node)
            trait = candidates[0]
            goals = [e for e in evidence if e.name == 'Trait:' + trait and e.args[0] == target]
            if not goals:
                from eldude.trait_constraints import match
                for impl in self.trait_solver.implementations:
                    if impl.head.name != 'Trait:' + trait:
                        continue
                    try:
                        types, regions = match(impl.head.args[0], target, impl.type_vars, impl.region_vars)
                    except ValueError:
                        continue
                    goals.append(substitute(impl.head, types, regions))
            terms = tuple(dict.fromkeys(g.args[1:] for g in goals))
            if len(terms) > 1 or not terms and self.generics(self.traits[trait].items[1]):
                self.error('type', 'Associated projection needs an unambiguous instantiated trait bound', node)
            return Ty('Projection:' + trait + ':' + member.items[0], (target, *(terms[0] if terms else ())))
        if node.kind == 'access_type':
            return Ty(node.items[0].title(), (self.type(node.items[1]),))
        if node.kind == 'tuple_type':
            return Ty('Tuple', tuple(self.type(t) for t in node.items[0]))
        if node.kind in ('type', 'applied_type'):
            spelling = node.items[0]
            if spelling in self.generic_types:
                template = self.generic_types[spelling]
                return replace(template, args=tuple(self.type(a) for a in node.items[1])) if node.kind == 'applied_type' else template
            if spelling == 'Self' and self.interface_self is not None:
                return self.interface_self
            if spelling.startswith('Self::') and self.interface_self is not None:
                if self.equation_sources is not None and spelling[6:] in self.equation_sources:
                    return self.associated_equation(spelling[6:])
                if spelling[6:] not in self.associated_bindings:
                    self.error('type', 'Trait is not DynCompatible: unresolved associated type ' + spelling, node)
                return substitute(self.associated_bindings[spelling[6:]], effect_variables=self.generic_effects)
            if spelling.startswith('Self::') and self.current_function in self.function_self:
                equations = self.function_self[self.current_function][1]
                return substitute(equations.get(spelling[6:], UNKNOWN), self.generic_types, effect_variables=self.generic_effects)
            if '::' in spelling and (spelling.rsplit('::', 1)[0] in self.generic_types
                    or self.canonical(spelling.rsplit('::', 1)[0]) in self.records
                    or self.canonical(spelling.rsplit('::', 1)[0]) in self.types):
                receiver, member = spelling.rsplit('::', 1)
                return self.type(Node('projection_type', node.span,
                                      (Node('type', node.span, (receiver,)), Node('name', node.span, (member,)), ())))
            if spelling == 'Self' and self.current_function in self.function_self:
                return substitute(self.function_self[self.current_function][0], self.generic_types)
            name = self.canonical(spelling)
            if name in self.named and self.named[name].kind == 'type_alias':
                declaration = self.named[name]
                if name in self.resolving_aliases:
                    self.error('semantic', 'Cyclic type alias', node)
                parameters = self.generics(declaration.items[1])
                arguments = node.items[1] if node.kind == 'applied_type' else ()
                if len(arguments) != len(parameters):
                    self.error('type', 'Generic type argument arity mismatch', node)
                keys = ('module', 'generic_types', 'region_arguments', 'effect_arguments', 'capture_arguments')
                previous = {key: getattr(self, key) for key in keys}
                self.generic_types = dict(self.generic_types)
                self.region_arguments, self.effect_arguments, self.capture_arguments = {}, {}, {}
                self.apply_trait_arguments(declaration, arguments)
                self.module = self.owners[id(declaration)]
                self.resolving_aliases.add(name)
                try:
                    return self.type(declaration.items[2])
                finally:
                    self.resolving_aliases.remove(name)
                    self.__dict__.update(previous)
            if name in self.records:
                template = self.record_type(name)
            elif name in self.types:
                template = self.types[name]
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
                        name = argument.items[0].items[0]
                        regions[parameter.items[1].items[0]] = self.region_arguments.get(name, name)
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
                if name in self.capture_arguments:
                    captures.update(self.capture_arguments[name])
                    continue
                if name not in self.generic_captures:
                    self.error('name', 'Unknown capture row ' + name, entry)
                captures.add(self.generic_captures[name])
                continue
            if entry.kind == 'region_type':
                name = entry.items[0].items[0]
                if name not in self.generic_regions and name not in self.region_stack and name not in self.region_arguments:
                    self.error('name', 'Unknown capture region ' + name, entry)
                captures.add(self.region_arguments.get(name, name))
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
        ordinary = [b for b in bounds if b.items[0] not in ('Dup', 'Discard')]
        if not ordinary:
            self.error('type', 'Existential package requires an ordinary trait', node)
        resolved = {}
        equations = {}
        for bound in ordinary:
            trait_name = self.canonical(bound.items[0])
            if trait_name not in self.traits:
                self.error('name', 'Unknown trait ' + trait_name, bound)
            trait = self.traits[trait_name]
            supplied = bound.items[1] if bound.kind == 'applied_type' else ()
            arguments = tuple(a for a in supplied if a.kind != 'type_binding')
            bindings = {}
            associated = {m.items[0].items[0]: m for m in trait.items[2] if m.kind == 'associated_type'}
            terms = self.trait_arguments(trait, arguments)
            for binding in supplied:
                if binding.kind != 'type_binding':
                    continue
                name = binding.items[0].items[0]
                if name not in associated or self.generics(associated[name].items[0]):
                    self.error('type', 'Unknown or generic associated binding ' + name, binding)
                t = self.type(binding.items[1])
                key = trait_name, terms, name
                if key in equations and equations[key] != t:
                    self.error('type', 'Conflicting associated bindings', binding)
                equations[key] = t
                bindings[name] = t
            key = trait_name, terms, tuple(sorted(bindings.items()))
            resolved[key] = trait, arguments, bindings
        canonical = tuple(sorted(resolved, key=repr))
        usage = tuple(Ty(b.items[0]) for b in bounds if b.items[0] in ('Dup', 'Discard'))
        interfaces = tuple(Ty('Interface:' + name, terms + tuple(Ty('Associated:' + n, (v,)) for n, v in bindings))
                           for name, terms, bindings in canonical)
        t = Ty('Any:' + '+'.join(sorted({name for name, _, _ in canonical})),
               tuple(sorted(set(usage), key=repr)) + interfaces)
        if t in self.dynamic_methods:
            return t
        self.interfaces[t] = canonical
        self.interface_variables[t] = (tuple(v.name[1:] for v in self.generic_types.values() if v.name.startswith('$')), self.generic_regions)
        evidence = tuple(Ty('Trait:' + name, (t, *terms)) for name, terms, _ in canonical)
        evidence += tuple(Ty('Trait:' + name, (t,)) for name in ('Dup', 'Discard') if Ty(name) in t.args)
        evidence += self.constraint_evidence
        methods = {}
        def raw_self(part):
            if isinstance(part, Node):
                return raw_self(part.items)
            if isinstance(part, tuple):
                return any(raw_self(p) for p in part)
            return part == 'Self'
        keys = ('module', 'current_function', 'generic_types', 'generic_regions', 'generic_effects',
                'generic_captures', 'generic_binders', 'capture_names', 'region_arguments',
                'effect_arguments', 'capture_arguments', 'interface_self', 'associated_bindings', 'capture_parameter_types', 'capture_usage')
        for trait_name, terms, associated in canonical:
            trait, arguments, bindings = resolved[(trait_name, terms, associated)]
            previous = {key: getattr(self, key) for key in keys}
            self.generic_types = dict(self.generic_types)
            self.region_arguments, self.effect_arguments, self.capture_arguments = {}, {}, {}
            self.apply_trait_arguments(trait, arguments)
            self.module, self.current_function = self.owners[id(trait)], None
            self.interface_self, self.associated_bindings = t, bindings
            self.capture_names = {}
            try:
                trait_constraints = self.constraints(trait.items[1].items[2] if len(trait.items[1].items) > 2 else ())
                for constraint in trait_constraints:
                    self.trait_solver.check(constraint, evidence)
                for member in trait.items[2]:
                    if member.kind != 'function':
                        continue
                    _, name, parameters, contract, _ = member.items
                    if (self.generics(name) or not parameters or parameters[0].items[0].items[0] != 'self'
                            or sum(p.items[0].items[0] == 'self' for p in parameters) != 1
                            or parameters[0].items[1] is not None or raw_self((parameters[1:], contract))):
                        self.error('type', 'Trait is not DynCompatible', member)
                    if name.items[0] in methods:
                        self.error('type', 'Ambiguous existential member ' + name.items[0], member)
                    receiver = Ty(parameters[0].items[2].title(), (t,)) if len(parameters[0].items) == 3 else t
                    rest = tuple(Ty(p.items[2].title(), (self.type(p.items[1]),)) if len(p.items) == 3
                                 else self.type(p.items[1]) for p in parameters[1:])
                    self.capture_names = {p.items[0].items[0]: Argument(i, 0, *permissions(unwrapped(part)))
                                          for i, (p, part) in enumerate(zip(parameters, (receiver, *rest)))}
                    self.capture_parameter_types = {p.items[0].items[0]: unwrapped(part)
                                                    for p, part in zip(parameters, (receiver, *rest))}
                    result, effects = self.contract(contract)
                    constraints = self.constraints(name.items[2] if len(name.items) > 2 else ())
                    for constraint in constraints:
                        self.trait_solver.check(constraint, evidence)
                    result = self.trait_solver.normalize_type(result, evidence)
                    bound = frozenset() if capture_free(result) else frozenset(f'arg:{i}' for i in range(len(parameters)))
                    methods[name.items[0]] = Fn((receiver, *rest), result, effects, bound,
                                               captures=self.capture_contract(contract))
                    self.interface_members[(t, name.items[0])] = (trait_name, terms, name.items[0])
            except ValueError as error:
                self.error('type', 'Trait is not DynCompatible: ' + str(error), node)
            finally:
                self.__dict__.update(previous)
        self.dynamic_methods[t] = methods
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
                region = entry.items[1][0].items[0].items[0]
                labels.append(state(self.region_arguments.get(region, region)))
            else:
                labels.append(self.effect_family(entry))
        return self.type(result), Row(tuple(labels), tail)


    def check_trait_signature(self, symbol, declaration):
        if symbol not in self.function_traits:
            return
        requirement, trait, applied = self.function_traits[symbol]
        keys = ('module', 'generic_types', 'generic_regions', 'generic_effects', 'region_arguments',
                'effect_arguments', 'capture_arguments', 'interface_self', 'associated_bindings', 'capture_names', 'capture_parameter_types')
        previous = {key: getattr(self, key) for key in keys}
        self.generic_types = dict(self.generic_types)
        self.region_arguments, self.effect_arguments, self.capture_arguments = {}, {}, {}
        arguments = applied.items[1] if applied.kind == 'applied_type' else ()
        self.apply_trait_arguments(trait, arguments)
        self.module = self.owners[id(trait)]
        target, equations = self.function_self[symbol]
        self.interface_self, self.associated_bindings = substitute(target, self.generic_types), equations
        expected_parameters = []
        for parameter in requirement.items[2]:
            name, annotation = parameter.items[:2]
            t = self.type(annotation) if annotation else self.interface_self
            if len(parameter.items) == 3:
                t = Ty(parameter.items[2].title(), (t,))
            expected_parameters.append(t)
        self.capture_names = {p.items[0].items[0]: Argument(i, 0, *permissions(unwrapped(t)))
                              for i, (p, t) in enumerate(zip(requirement.items[2], expected_parameters))}
        self.capture_parameter_types = {p.items[0].items[0]: unwrapped(t)
                                        for p, t in zip(requirement.items[2], expected_parameters)}
        result, effects = self.contract(requirement.items[3])
        actual = self.signatures[symbol]
        allowed = self.function_evidence.get(symbol, ())
        method_constraints = requirement.items[1].items[2] if len(requirement.items[1].items) > 2 else ()
        allowed += self.constraints(method_constraints)
        self.__dict__.update(previous)
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
