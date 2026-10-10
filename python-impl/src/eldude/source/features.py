"""Check data, library primitives, and structural control in source IR."""
from dataclasses import replace

from eldude.core.rows import Row
from eldude.core.handlers import HandlerChecker
from eldude.core.inference import (Ty, Fn, Value, Binding, INT, BOOL, UNIT, E, value, ambient,
                             permissions, capture_free, required_captures, InferenceError,
                             state, Owner, Grant, joined_owner)
from eldude.core.types import NAT, NEVER, UNKNOWN, substitute, compatible, join_type, unwrapped


class FeatureChecker(HandlerChecker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.variants = {}
        self.data_parameters = {}
        self.methods = {}
        self.method_calls = {}
        self.dynamic_methods, self.trait_methods, self.impl_contracts = {}, {}, {}
        self.impl_constraints = {}
        self.packages, self.dynamic_calls = {}, {}
        self.exit_contracts = {}
        self.exit_values = {}
        self.exit_active = {}
        self.exit_outside = {}
        self.exit_temporaries = {}
        self.baselines = {}
        self.borrowed_values = {}
        self.borrowed_matches = set()
        self.iteration_steps = {}
        self.cleanup_methods = {}
        self.cleanup_targets = {}
        self.results = {}

    def _infer(self, expression, context):
        result = super()._infer(expression, context)
        self.results[id(expression)] = result
        return result

    def fields(self, t, tag):
        t = unwrapped(t)
        if t.name == 'Option':
            return () if tag == 'None' else (t.args[0],)
        if t.name == 'Result':
            return (t.args[1 if tag == 'Err' else 0],)
        declarations = self.variants.get(t.name, {})
        if tag not in declarations:
            raise InferenceError('Unknown enum variant ' + tag, code='type')
        substitutions = dict(zip(self.data_parameters.get(t.name, ()), t.args))
        return tuple(substitute(f, substitutions) for f in declarations[tag])

    def tags(self, t):
        t = unwrapped(t)
        if t.name == 'Option':
            return ('None', 'Some')
        if t.name == 'Result':
            return ('Err', 'Ok')
        return tuple(self.variants.get(t.name, {}))

    def bind_pattern(self, pattern, retained, context, borrowed=False):
        bound = {}
        def bind(p, t, whole=False):
            original = t
            t = unwrapped(t)
            kind = p[0]
            if kind == 'wild':
                if not borrowed and not permissions(original)[1]:
                    raise InferenceError('Cannot discard an owned pattern component')
            elif kind == 'bind':
                if borrowed and not permissions(original)[0]:
                    raise InferenceError('Inspection pattern binding requires Dup')
                bound[p[1]] = Binding(replace(retained, type=original, effects=Row(), grant=None) if whole
                                     else value(original, captures=retained.captures))
            elif kind == 'tuple_pat':
                if t.name != 'Tuple' or len(t.args) != len(p) - 1:
                    raise InferenceError('Tuple pattern shape mismatch', code='type')
                for child, part in zip(p[1:], t.args):
                    bind(child, part)
            elif kind == 'variant_pat':
                if t.name != p[1]:
                    raise InferenceError('Enum pattern has a different nominal type', code='type')
                fields = self.fields(t, p[2])
                if len(fields) != len(p) - 3:
                    raise InferenceError('Variant pattern arity mismatch', code='type')
                for child, part in zip(p[3:], fields):
                    bind(child, part)
            elif kind == 'record_pat':
                if t.name != p[1]:
                    raise InferenceError('Record pattern has a different nominal type', code='type')
                if len(set(p[2])) != len(p[2]):
                    raise InferenceError('Duplicate record pattern field', code='type')
                fields = {f.name: f.args[0] for f in t.args}
                if set(p[2]) != fields.keys():
                    raise InferenceError('Record pattern must cover every field', code='type')
                for name, child in zip(p[2], p[3:]):
                    bind(child, fields[name])
            elif kind == 'literal_pat':
                expected = BOOL if type(p[1]) is bool else UNIT if p[1] is None else NAT if t == NAT else INT
                if t != expected:
                    raise InferenceError('Literal pattern type mismatch', code='type')
            else:
                raise InferenceError('Implementation limit: pattern ' + kind, code='unsupported')
        bind(pattern, retained.type, True)
        return bound

    def exhaustive(self, patterns, t):
        # Constructor specialization of a pattern matrix; wildcard rows avoid
        # expanding recursive types indefinitely.
        def covered(rows, types):
            if not rows:
                return False
            if not types:
                return True
            wild = [row[1:] for row in rows if row[0][0] in ('bind', 'wild')]
            if covered(wild, types[1:]):
                return True
            head = unwrapped(types[0])
            if head.name == 'Tuple':
                alternatives = [('tuple_pat', None, head.args)]
            elif head.name.startswith('Record:'):
                alternatives = [('record_pat', head.name, tuple(f.args[0] for f in head.args))]
            elif self.tags(head):
                alternatives = [('variant_pat', tag, self.fields(head, tag)) for tag in self.tags(head)]
            elif head == BOOL:
                alternatives = [('literal_pat', False, ()), ('literal_pat', True, ())]
            elif head == UNIT:
                alternatives = [('literal_pat', None, ())]
            else:
                return False
            for kind, tag, fields in alternatives:
                specialized = []
                for row in rows:
                    p = row[0]
                    if p[0] in ('bind', 'wild'):
                        specialized.append((('wild',),) * len(fields) + row[1:])
                    elif kind == 'record_pat' and p[0] == kind and p[1] == tag:
                        named = dict(zip(p[2], p[3:]))
                        if len(named) == len(p[2]) and named.keys() == {f.name for f in head.args}:
                            specialized.append(tuple(named[f.name] for f in head.args) + row[1:])
                    elif p[0] == kind and (kind == 'tuple_pat' or p[2 if kind == 'variant_pat' else 1] == tag):
                        specialized.append(tuple(p[3:] if kind == 'variant_pat' else p[1:] if kind == 'tuple_pat' else ()) + row[1:])
                if not covered(specialized, tuple(fields) + types[1:]):
                    return False
            return True
        return covered([(p,) for p in patterns], (t,))

    def _apply(self, function, arguments, context):
        borrowed = [self.borrowed_values.get(id(argument)) for argument in arguments]
        # An absent enum payload type can be fixed by its consuming contract.
        if isinstance(function.type, Fn):
            arguments = [replace(a, type=join_type(p, a.type)) if compatible(p, a.type) and a.type != p else a
                         for p, a in zip(function.type.parameters, arguments)] if len(arguments) == len(function.type.parameters) else arguments
        previous = context.grants
        context.grants += tuple(a.grant for a in arguments if a.grant)
        try:
            result = super()._apply(function, arguments, context)
        finally:
            context.grants = previous
        retained = function.captures | frozenset().union(*(a.captures for a in arguments))
        for borrowing in borrowed:
            if borrowing is None:
                continue
            argument, binding = borrowing
            t = unwrapped(binding.value.type)
            if argument.type.name == 'Mut' and not (t.name == 'DynArray' and capture_free(t.args[0])):
                binding.value = replace(binding.value, captures=binding.value.captures | retained)
        return result

    def record_exit(self, key, retained, context):
        escaped = (retained.captures | required_captures(retained.type)) & (context.active - self.exit_active[key])
        if escaped:
            raise InferenceError('Local region or capability would escape through early return')
        self.exit_values[key].append(retained)

    def _infer_expression(self, expression, context):
        match expression:
            case ('pack', t, initial):
                t = self.resolve_type(t, context)
                retained = self._infer(initial, context)
                if retained.type == t:
                    self.packages[id(expression)] = None
                    return retained
                wanted, actual = permissions(t), permissions(retained.type)
                if any(w and not a for w, a in zip(wanted, actual)):
                    raise InferenceError('Existential usage promises require Dup/Discard of the hidden value', code='type')
                if capture_free(t) and not capture_free(retained.type):
                    raise InferenceError('Existential CaptureFree promise requires evidence for the hidden type', code='type')
                if isinstance(retained.type, Ty) and retained.type.name.startswith('Any:'):
                    if not set(self.interfaces[t]) <= set(self.interfaces[retained.type]):
                        raise InferenceError('Existential weakening requires every remaining trait bound', code='type')
                    self.packages[id(expression)] = {}
                    return value(t, retained.effects, retained.captures, owner=retained.owner)
                methods = {}
                for trait, arguments, bindings in self.interfaces[t]:
                    goal = Ty('Trait:' + trait, (retained.type, *arguments))
                    try:
                        implementation, types, regions = self.trait_solver.select_impl(goal, context.evidence)
                        if implementation is None:
                            raise ValueError('Existential package requires concrete implementation evidence')
                        for member, expected in bindings:
                            actual = substitute(implementation.equations[member], types, regions)
                            if self.trait_solver.normalize_type(actual, context.evidence) != expected:
                                raise ValueError('Existential associated binding does not match implementation')
                    except ValueError as error:
                        raise InferenceError('Existential implementation: ' + str(error), code='type') from error
                    for member, target in implementation.methods.items():
                        methods[(trait, arguments, member)] = target
                self.packages[id(expression)] = methods
                return value(t, retained.effects, retained.captures, owner=retained.owner)
            case ('definitions', _, _, _):
                from eldude.core.declarations import infer_declarations
                return infer_declarations(self, expression, context)
            case ('method_call', method, receiver, arguments, mode):
                retained = None
                if receiver[0] == 'var' and receiver[1] in context.bindings:
                    t = context.bindings[receiver[1]].value.type
                else:
                    # A temporary receiver is inferred once and retained while
                    # arguments evaluate; method resolution uses its type.
                    retained = self._infer(receiver, context)
                    t = retained.type
                dynamic = isinstance(t, Ty) and t.name.startswith('Any:')
                if dynamic:
                    signature = self.dynamic_methods[t].get(method)
                    if signature is None:
                        raise InferenceError('Unknown existential method ' + method, code='type')
                    receiver_type = signature.parameters[0]
                    receiver_type = replace(receiver_type, args=(t,)) if receiver_type.name in ('View', 'Mut') else t
                    target = (method, replace(signature, parameters=(receiver_type, *signature.parameters[1:])))
                else:
                    target = self.methods.get((unwrapped(t).name, method))
                if target is None:
                    return self.primitive_method(expression, method, receiver, arguments, mode, context, retained)
                name, signature = target
                if signature is None:
                    raise InferenceError('Ambiguous implementation member ' + method, code='type')
                parameter = signature.parameters[0]
                borrowed = isinstance(parameter, Ty) and parameter.name in ('View', 'Mut')
                if not borrowed and mode:
                    raise InferenceError(f'{method} requires consuming access')
                if borrowed:
                    if mode != parameter.name.lower() and not (receiver[0] == 'var' and context.bindings[receiver[1]].mode):
                        raise InferenceError(f'{method} requires {parameter.name.lower()} access')
                    if receiver[0] != 'var':
                        raise InferenceError('Access receiver must be a named owner')
                    first = self._infer(E('access', parameter.name.lower(), receiver[1]), context)
                elif receiver[0] == 'var':
                    first = self._infer(receiver, context)
                else:
                    first = retained
                start = len(context.temporaries)
                context.temporaries.append(first)
                values = [first]
                for argument in arguments:
                    item = self._infer(argument, context)
                    values.append(item)
                    context.temporaries.append(item)
                del context.temporaries[start:]
                result = self._apply(value(signature), values, context)
                if not dynamic:
                    self.method_calls[id(expression)] = (name, parameter.name.lower() if borrowed else '')
                else:
                    identity = self.interface_members[(t, method)]
                    targets = tuple(impl.methods[method] for impl in self.trait_solver.implementations
                                    if impl.head.name == 'Trait:' + identity[0] and method in impl.methods)
                    self.dynamic_calls[id(expression)] = (parameter.name.lower() if borrowed else '', targets, identity)
                return replace(result, effects=ambient(result.effects, *(v.effects for v in values)))
            case ('field', name, ('var', symbol)) if symbol in context.bindings:
                binding = context.bindings[symbol]
                if binding.consumed:
                    raise InferenceError(f'{symbol} was already consumed', subject=symbol)
                t = unwrapped(binding.value.type)
                if not t.name.startswith('Record:'):
                    return super()._infer_expression(expression, context)
                fields = {f.name: f.args[0] for f in t.args}
                if name not in fields:
                    raise InferenceError('Unknown record field ' + name, code='type')
                if not permissions(fields[name])[0]:
                    raise InferenceError('Field copies require Dup', code='type')
                context.references.add(binding)
                return value(fields[name], captures=binding.value.captures)
            case ('lambda', parameters, body):
                annotation = getattr(self, 'annotations', {}).get(id(expression), ())
                signature = annotation[0] if annotation and isinstance(annotation[0], Fn) else None
                if signature and signature.regions:
                    previous = context.regions, context.active
                    context.regions = context.regions | {r: r for r in signature.regions}
                    context.active |= set(signature.regions)
                    result = super()._infer_expression(expression, context)
                    context.regions, context.active = previous
                    return replace(result, type=replace(result.type, regions=signature.regions))
            case ('nat', number):
                if number < 0:
                    raise InferenceError('Nat literal must be nonnegative', code='type')
                return value(NAT)
            case ('variant', t, tag, arguments):
                fields = self.fields(t, tag)
                if len(fields) != len(arguments):
                    raise InferenceError('Variant constructor arity mismatch', code='type')
                values = []
                start = len(context.temporaries)
                for argument in arguments:
                    item = self._infer(argument, context)
                    values.append(item)
                    context.temporaries.append(item)
                del context.temporaries[start:]
                # Reuse call unification for repeated/nested generic payloads.
                constructor = Fn(fields, t, Row(), type_vars=self.data_parameters.get(unwrapped(t).name, ()))
                t = self._apply(value(constructor), values, context).type
                if t.name == 'Option' and tag == 'Some':
                    t = replace(t, args=(join_type(t.args[0], values[0].type),))
                elif t.name == 'Result':
                    args = list(t.args)
                    index = 1 if tag == 'Err' else 0
                    args[index] = join_type(args[index], values[0].type)
                    t = replace(t, args=tuple(args))
                return value(t, ambient(*(v.effects for v in values)), frozenset().union(*(v.captures for v in values)))
            case ('bindpat', pattern, initial, body):
                retained = self._infer(initial, context)
                bound = self.bind_pattern(pattern, retained, context)
                previous, start = context.bindings, len(context.live)
                context.bindings = previous | bound
                context.live.extend(bound.items())
                result = self._infer(body, context)
                for name, binding in bound.items():
                    if not binding.consumed and not permissions(binding.value.type)[1]:
                        raise InferenceError(f'Unconsumed resource {name}', subject=name)
                context.bindings = previous
                del context.live[start:]
                return replace(result, effects=ambient(retained.effects, result.effects))
            case ('match', subject, arms):
                binding = context.bindings.get(subject[1]) if subject[0] == 'var' else None
                borrowed = bool(binding and binding.mode)
                if borrowed:
                    retained = self._infer(E('access', 'view', subject[1]), context)
                    retained = replace(retained, type=binding.value.type)
                    self.borrowed_matches.add(id(expression))
                else:
                    retained = self._infer(subject, context)
                if not self.exhaustive([p for p, _ in arms], retained.type):
                    raise InferenceError('Non-exhaustive match')
                bindings = set(context.bindings.values()) | {b for _, b in context.live}
                initial = {b: b.consumed for b in bindings}
                resume = context.resumption
                used = resume.used if resume else False
                results, states, resumed = [], [], []
                for pattern, body in arms:
                    for binding, consumed in initial.items():
                        binding.consumed = consumed
                    if resume:
                        resume.used = used
                    bound = self.bind_pattern(pattern, retained, context, borrowed=borrowed)
                    previous, start = context.bindings, len(context.live)
                    context.bindings = previous | bound
                    context.live.extend(bound.items())
                    result = self._infer(body, context)
                    for name, binding in bound.items():
                        if not binding.consumed and not permissions(binding.value.type)[1]:
                            raise InferenceError(f'Unconsumed resource {name}', subject=name)
                    context.bindings = previous
                    del context.live[start:]
                    results.append(result)
                    if result.type != NEVER:
                        states.append({b: b.consumed for b in bindings})
                        resumed.append(resume.used if resume else False)
                if states and any(s[b] != states[0][b] and not permissions(b.value.type)[1]
                                  for s in states[1:] for b in bindings):
                    raise InferenceError('Match arms must agree on ownership consumption')
                if resumed and any(s != resumed[0] for s in resumed[1:]):
                    raise InferenceError('Match arms must agree on resumption use')
                if states:
                    for b in bindings:
                        b.consumed = any(s[b] for s in states)
                    if resume:
                        resume.used = resumed[0]
                t = NEVER
                for result in results:
                    t = join_type(t, result.type)
                return value(t, ambient(retained.effects, *(r.effects for r in results)),
                             frozenset().union(*(r.captures for r in results)), owner=joined_owner(*results))
            case ('exit_scope', key, expected, body, wrap):
                self.exit_contracts[key] = expected
                self.exit_values[key] = []
                self.exit_active[key] = frozenset(context.active)
                self.exit_outside[key] = {binding for _, binding in context.live} if wrap else set()
                self.exit_temporaries[key] = len(context.temporaries)
                result = self._infer(body, context)
                if wrap:
                    inferred = Ty('Result', (result.type, expected.args[1] if expected else UNKNOWN))
                else:
                    inferred = result.type
                captures = result.captures
                exits = self.exit_values.pop(key)
                if isinstance(expected, Fn) and expected.captures is None:
                    alternatives = [returned for returned in (result, *exits) if returned.type != NEVER]
                    for returned in alternatives:
                        self._apply(value(Fn((expected,), UNIT, Row())), [returned], context)
                    signatures = [returned.type for returned in alternatives]
                    t = replace(expected, bound=frozenset().union(*(s.bound for s in signatures)))
                    # Legacy contracts leave environments unknown; keep precise
                    # inferred summaries when the remaining callable shape agrees.
                    if all(s.captures is not None and s.parameters == expected.parameters and s.result == expected.result
                           for s in signatures):
                        t = replace(t, captures=frozenset().union(*(s.captures for s in signatures)))
                else:
                    t = join_type(expected, inferred) if expected else inferred
                    for exited in exits:
                        t = join_type(t, exited.type)
                captures |= frozenset().union(*(exited.captures for exited in exits))
                del self.exit_active[key]
                del self.exit_outside[key]
                del self.exit_temporaries[key]
                return value(t, result.effects, captures, owner=None if wrap else joined_owner(result, *exits))
            case ('early', key, argument):
                result = self._infer(argument, context)
                expected = self.exit_contracts[key]
                if isinstance(expected, Fn) and expected.captures is None:
                    self._apply(value(Fn((expected,), UNIT, Row())), [result], context)
                elif expected and not compatible(expected, result.type):
                    raise InferenceError('Early return type mismatch', code='type')
                for name, binding in context.live:
                    if (binding not in self.exit_outside[key] and not binding.consumed
                            and not binding.managed and not binding.mode and not permissions(binding.value.type)[1]):
                        raise InferenceError(f'Early return would abandon {name}', subject=name)
                if any(not permissions(v.type)[1] for v in context.temporaries[self.exit_temporaries[key]:]):
                    raise InferenceError('Early return would abandon an owned argument temporary')
                self.record_exit(key, result, context)
                return Value(NEVER, result.effects, result.captures)
            case ('propagate', key, argument):
                result = self._infer(argument, context)
                expected = self.exit_contracts[key]
                if not isinstance(result.type, Ty) or result.type.name != 'Result':
                    raise InferenceError('? requires Result', code='type')
                if expected and (expected.name != 'Result' or not compatible(expected.args[1], result.type.args[1])):
                    raise InferenceError('Propagation error type mismatch', code='type')
                for name, binding in context.live:
                    if (binding not in self.exit_outside[key] and not binding.consumed
                            and not binding.managed and not binding.mode and not permissions(binding.value.type)[1]):
                        raise InferenceError(f'Propagation would abandon {name}', subject=name)
                if any(not permissions(v.type)[1] for v in context.temporaries[self.exit_temporaries[key]:]):
                    raise InferenceError('Propagation would abandon an owned argument temporary')
                self.record_exit(key, value(Ty('Result', (NEVER, result.type.args[1])),
                                            captures=result.captures), context)
                return value(result.type.args[0], result.effects, result.captures)
            case ('coalesce', option, fallback):
                first = self._infer(option, context)
                if first.type.name != 'Option':
                    raise InferenceError('?? requires Option', code='type')
                states = {b: b.consumed for b in context.bindings.values()}
                second = self._infer(fallback, context)
                if any(b.consumed != consumed for b, consumed in states.items()):
                    raise InferenceError('Coalescing branches disagree on ownership consumption')
                return value(join_type(first.type.args[0], second.type), ambient(first.effects, second.effects), first.captures | second.captures)
            case ('access', mode, name):
                binding = context.bindings.get(name)
                if not binding or binding.consumed:
                    raise InferenceError(f'{name} is unavailable for {mode}', subject=name)
                context.references.add(binding)
                self._check_owner_available(binding.value, context, mode)
                incoming = binding.value.grant
                if mode == 'mut' and incoming and incoming.mode != 'mut':
                    raise InferenceError('Shared view grant cannot authorize mut access')
                if mode == 'mut' and incoming is None and (binding.value.owner is None or binding.value.owner.region is None):
                    raise InferenceError('Root mut access requires an intrinsic mutable owner')
                owner = incoming.owner if incoming else binding.value.owner or Owner(None)
                grant = Grant(owner, mode, incoming.path if incoming else (), incoming)
                effects = Row((state(owner.region),)) if mode == 'mut' and incoming is None else Row()
                result = value(Ty(mode.title(), (binding.value.type,)), effects, binding.value.captures,
                               owner=binding.value.owner, grant=grant)
                self.borrowed_values[id(result)] = (result, binding)
                return result
            case ('region', name, body):
                outside = list(context.bindings.values())
                result = super()._infer_expression(expression, context)
                for binding in outside:
                    if not binding.consumed and any(isinstance(c, str) and c.startswith(name + '#') for c in binding.value.captures):
                        raise InferenceError('Local region would escape through a mutable owner')
                return result
            case ('list_values', declared, items):
                values = []
                start = len(context.temporaries)
                for item in items:
                    retained = self._infer(item, context)
                    values.append(retained)
                    context.temporaries.append(retained)
                del context.temporaries[start:]
                t = substitute(declared, regions=context.regions, effect_variables=context.effect_variables) if declared else (values[0].type if values else UNKNOWN)
                for item in values:
                    t = join_type(t, item.type)
                return value(Ty('List', (t,)), ambient(*(v.effects for v in values)), frozenset().union(*(v.captures for v in values)))
            case ('ref_new', region, initial):
                return self._infer(E('ref', region, initial), context)
            case ('buffer_new', region, element):
                key = context.regions[region]
                element = substitute(element, regions=context.regions)
                return value(Ty('DynArray', (element,), key), Row((state(key),)), {key})
            case ('primitive_method', method, receiver, arguments, mode):
                return self.primitive_method(expression, method, receiver, arguments, mode, context)
            case ('for_each', pattern, iterable, body):
                source = self._infer(iterable, context)
                t = unwrapped(source.type)
                if t.name == 'List':
                    step, item, finite, target = source, t.args[0], True, None
                else:
                    try:
                        self.trait_solver.check(Ty('Trait:core::iter::Iterator', (source.type,)), context.evidence)
                    except ValueError as error:
                        raise InferenceError('for requires an Iterator implementation', code='type') from error
                    target, signature = self.methods.get((t.name, 'next'), (None, None))
                    if signature is None:
                        raise InferenceError('for requires an unambiguous Iterator::next', code='type')
                    step = self._apply(value(signature), [source], context)
                    result_type = unwrapped(step.type)
                    if (result_type.name != 'Enum:core::iter::Next' or len(result_type.args) != 2
                            or result_type.args[0] != source.type):
                        raise InferenceError('Iterator::next must return Next<Self, Item>', code='type')
                    item = result_type.args[1]
                    finite = target in getattr(self.elaborator, 'finite_iterators', ())
                self.iteration_steps[id(expression)] = target
                before = {b: b.consumed for b in context.bindings.values()}
                bound = self.bind_pattern(pattern, value(item, captures=step.captures), context)
                previous, start = context.bindings, len(context.live)
                context.bindings = previous | bound
                context.live.append(('iterator remainder', Binding(value(source.type, captures=step.captures))))
                context.live.extend(bound.items())
                result = self._infer(body, context)
                if result.type != UNIT:
                    raise InferenceError('Loop body must return Unit', code='type')
                for name, binding in bound.items():
                    if not binding.consumed and not permissions(binding.value.type)[1]:
                        raise InferenceError(f'Unconsumed loop binding {name}')
                if any(b.consumed != old for b, old in before.items()):
                    raise InferenceError('Repeated loop body cannot consume an outside owner')
                context.bindings = previous
                del context.live[start:]
                return value(UNIT, ambient(source.effects, step.effects, result.effects,
                                          Row() if finite else Row(('diverge',))))
            case ('taskgroup', key, body):
                old = context.group
                children = []
                context.group = (key, context.handlers, children, context.active | {key})
                context.active |= {key}
                result = self._infer(body, context)
                context.group = old
                context.active -= {key}
                if key in result.captures:
                    raise InferenceError('Task handle would escape its taskgroup')
                effects = ambient(result.effects, *children, Row(('suspend',)))
                self._control(Row(('suspend',)), replace(context, temporaries=context.temporaries + [result]))
                return replace(result, effects=effects)
            case ('spawn', closure):
                if context.group is None:
                    raise InferenceError('spawn requires an immediate lexical taskgroup')
                function = self._infer(closure, context)
                local_scopes = context.active - context.group[3]
                if (function.captures | required_captures(function.type)) & local_scopes:
                    raise InferenceError('Child captures a region or capability that does not enclose the taskgroup')
                if not permissions(function.type.result)[1]:
                    raise InferenceError('Spawned result must satisfy Discard')
                child = replace(context, handlers=context.group[1], live=[], temporaries=[], suspended=(), resumption=None)
                effects = self._resolve(function.type.effects, child)
                for family, key in context.group[1]:
                    if key in effects.labels and not self.baselines.get(key, False):
                        raise InferenceError('Inherited handler must be duplicable and preserve arbitrary child results')
                result = self._apply(function, [], child)
                context.group[2].append(result.effects)
                return value(Ty('Task', (result.type,)), function.effects, result.captures | {context.group[0]})
            case ('await', task):
                retained = self._infer(task, context)
                if retained.type.name != 'Task':
                    raise InferenceError('await requires Task', code='type')
                effects = ambient(retained.effects, Row(('suspend',)))
                self._control(effects, context)
                group_keys = {c for c in retained.captures if isinstance(c, str) and c.startswith('taskgroup:')}
                return value(retained.type.args[0], effects, retained.captures - group_keys)
        return super()._infer_expression(expression, context)

    def cleanup_contract(self, expression, retained, context):
        target = self.cleanup_methods.get(unwrapped(retained.type).name)
        if target is None:
            raise InferenceError('using requires a canonical cleanup resource')
        name, signature = target
        result = self._apply(value(signature), [retained], context)
        if result.type != UNIT:
            raise InferenceError('Cleanup must return Unit', code='type')
        if any(label not in ('suspend',) and not label.startswith('state<@') for label in result.effects.labels):
            raise InferenceError('Implementation limit: custom cleanup requires state or suspend only', code='unsupported')
        self.cleanup_targets[id(expression)] = name
        return result.effects

    def primitive_method(self, expression, method, receiver, arguments, mode, context, retained=None):
        inspected = receiver[0] == 'var' and receiver[1] in context.bindings
        binding = context.bindings.get(receiver[1]) if inspected else None
        if binding is None and retained is None:
            retained = self._infer(receiver, context)
        t = unwrapped(binding.value.type if binding else retained.type)
        access = {'length': 'view', 'get': 'view', 'with': 'view'} if t.name == 'List' else {
            'length': 'view', 'push': 'mut', 'pop': 'mut', 'withMut': 'mut'}
        required_mode = access.get(method, '')
        if mode != required_mode:
            raise InferenceError(f'{method} requires {required_mode or "consuming"} access')
        borrowed = mode in ('view', 'mut')
        if borrowed and binding:
            if binding.consumed:
                raise InferenceError(f'{receiver[1]} was already consumed', subject=receiver[1])
            retained = self._infer(E('access', mode, receiver[1]), context)
            retained = replace(retained, type=binding.value.type)
        elif retained is None:
            retained = self._infer(receiver, context)
        t = unwrapped(retained.type)
        values = []
        start = len(context.temporaries)
        context.temporaries.append(retained)
        for argument in arguments:
            actual = self._infer(argument, context)
            values.append(actual)
            context.temporaries.append(actual)
        del context.temporaries[start:]
        rows = [retained.effects, *(v.effects for v in values)]
        captures = retained.captures | frozenset().union(*(v.captures for v in values))
        if t.name in ('Ref', 'DynArray'):
            rows.append(Row((state(t.region),)))
        if method == 'get' and t.name == 'Ref' and not values:
            if not permissions(t.args[0])[0]:
                raise InferenceError('Reading Ref requires Dup')
            result = t.args[0]
        elif method == 'replace' and t.name == 'Ref' and len(values) == 1:
            if not compatible(t.args[0], values[0].type):
                raise InferenceError('Ref write type mismatch', code='type')
            from eldude.core.inference import check_ref_payload
            check_ref_payload(t.args[0])
            result = t.args[0]
        elif method == 'length' and t.name in ('List', 'DynArray') and not values:
            if mode != 'view':
                raise InferenceError('length requires view access')
            result = NAT
        elif method == 'push' and t.name == 'DynArray' and len(values) == 1:
            if mode != 'mut' or not binding:
                raise InferenceError('push requires mut access to an owner')
            if not compatible(t.args[0], values[0].type):
                raise InferenceError('Array element type mismatch', code='type')
            binding.value = replace(binding.value, captures=captures)
            result = UNIT
        elif method == 'pop' and t.name == 'DynArray' and not values:
            result = Ty('Option', t.args)
        elif method == 'withMut' and t.name == 'DynArray' and len(values) == 2:
            index, callback = values
            if index.type != INT:
                raise InferenceError('Array index must be Int', code='type')
            if not isinstance(callback.type, Fn) or not callback.type.discard:
                raise InferenceError('Conditional projection callback must satisfy Discard')
            parent = retained.grant
            projected = Grant(parent.owner, 'mut', parent.path + ('element',), parent)
            argument = value(Ty('Mut', (t.args[0],)), captures=retained.captures, grant=projected)
            mapped = self._apply(callback, [argument], context)
            if not capture_free(t.args[0]):
                binding.value = replace(binding.value, captures=captures)
            result = Ty('Option', (mapped.type,))
            rows.append(mapped.effects)
            captures |= mapped.captures
        elif method == 'freeze' and t.name == 'DynArray' and not values:
            result = Ty('List', t.args)
            if capture_free(t.args[0]):
                captures = frozenset()
        elif t.name == 'List':
            element = t.args[0]
            library_types = getattr(getattr(self, 'elaborator', None), 'types', {})
            if method == 'push' and len(values) == 1:
                if not compatible(element, values[0].type):
                    raise InferenceError('List element type mismatch', code='type')
                result = Ty('List', (join_type(element, values[0].type),))
            elif method in ('get', 'remove', 'replace') and len(values) == (2 if method == 'replace' else 1):
                if values[0].type != INT:
                    raise InferenceError('List index must be Int', code='type')
                if method == 'get':
                    if not permissions(element)[0]:
                        raise InferenceError('Reading List requires Dup')
                    result = Ty('Option', (element,))
                else:
                    if method == 'replace' and not compatible(element, values[1].type):
                        raise InferenceError('List element type mismatch', code='type')
                    if method == 'replace':
                        element = join_type(element, values[1].type)
                        t = replace(t, args=(element,))
                    error = library_types.get('collections::list::BoundsError',
                        Ty('Record:collections::list::BoundsError', (Ty('index', (INT,)), Ty('length', (NAT,)))))
                    failure = (error, t, element) if method == 'replace' else (error, t)
                    result = Ty('Result', (Ty('Tuple', (element, t)), Ty('Tuple', failure)))
            elif method in ('with', 'filter', 'partition') and len(values) == (2 if method == 'with' else 1):
                callback = values[-1]
                if method == 'with' and values[0].type != INT:
                    raise InferenceError('List index must be Int', code='type')
                if method == 'filter' and not permissions(element)[1]:
                    raise InferenceError('List filter requires Discard elements')
                if not isinstance(callback.type, Fn) or not callback.type.discard:
                    raise InferenceError('List callback must satisfy Discard')
                if method != 'with' and not callback.type.dup:
                    raise InferenceError('Repeated List callback must satisfy Dup')
                parent = retained.grant
                grant = Grant(parent.owner if parent else Owner(None), 'view',
                              (parent.path if parent else ()) + ('element',), parent)
                argument = value(Ty('View', (element,)), captures=retained.captures, grant=grant)
                mapped = self._apply(callback, [argument], context)
                if method == 'with':
                    result = Ty('Option', (mapped.type,))
                    rows.append(mapped.effects)
                    captures |= mapped.captures
                else:
                    if mapped.type != BOOL or mapped.effects != Row():
                        raise InferenceError('List predicate must be pure and return Bool', code='type')
                    result = t if method == 'filter' else Ty('Tuple', (t, t))
            elif method == 'next' and not values:
                result = replace(library_types.get('core::iter::Next', Ty('Enum:core::iter::Next')),
                                 args=(t, element))
            else:
                raise InferenceError(f'Unknown method {method} for List', code='type')
        elif method == 'cancel' and t.name == 'Task' and not values:
            result = UNIT
        else:
            raise InferenceError(f'Unknown method {method} for {t.name}', code='type')
        return value(result, ambient(*rows), captures)
