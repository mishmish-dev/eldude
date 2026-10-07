"""Checked data, library primitives and structural control for source execution."""
from dataclasses import dataclass, replace

from effect_rows import Row
from handlers import HandlerChecker, Defect, _bind, _protect_call, _Slot, _Request, _read
from inference import (Ty, Fn, Value, Binding, Context, INT, BOOL, UNIT, E, value, ambient,
                       permissions, capture_free, required_captures, InferenceError, state)

NAT, NEVER, UNKNOWN = Ty('Nat'), Ty('Never'), Ty('Unknown')


def substitute(t, types=None, regions=None):
    types, regions = types or {}, regions or {}
    if isinstance(t, Fn):
        return replace(t, parameters=tuple(substitute(p, types, regions) for p in t.parameters),
                       result=substitute(t.result, types, regions),
                       effects=Row(tuple(next((state(v) for k, v in regions.items() if label == state(k)), label)
                                         for label in t.effects.labels), t.effects.tail),
                       bound=frozenset(regions.get(c, c) for c in t.bound),
                       captures=None if t.captures is None else frozenset(regions.get(c, c) for c in t.captures))
    if t.name.startswith('$'):
        return types.get(t.name[1:], t)
    return replace(t, args=tuple(substitute(a, types, regions) for a in t.args), region=regions.get(t.region, t.region))


def compatible(left, right):
    if left in (UNKNOWN, NEVER) or right in (UNKNOWN, NEVER):
        return True
    if isinstance(left, Ty) and isinstance(right, Ty):
        return left.name == right.name and left.region == right.region and len(left.args) == len(right.args) and all(
            compatible(a, b) for a, b in zip(left.args, right.args))
    return left == right


def join_type(left, right):
    if left in (UNKNOWN, NEVER):
        return right
    if right in (UNKNOWN, NEVER):
        return left
    if not compatible(left, right):
        raise InferenceError('Branches must have the same type', code='type')
    if isinstance(left, Ty):
        return replace(left, args=tuple(join_type(a, b) for a, b in zip(left.args, right.args)))
    return left


def unwrapped(t):
    return t.args[0] if isinstance(t, Ty) and t.name in ('Linear', 'Affine', 'View', 'Mut') else t


def pattern_bindings(pattern):
    if pattern[0] == 'bind':
        return {pattern[1]}
    return set().union(*(pattern_bindings(p) for p in pattern[1:] if isinstance(p, tuple) and p and isinstance(p[0], str)))


@dataclass(frozen=True)
class Variant:
    type: object
    tag: str
    fields: tuple = ()


@dataclass
class Record:
    type: object
    fields: dict


@dataclass
class Cell:
    value: object


@dataclass
class Buffer:
    values: list


@dataclass
class Package:
    type: object
    value: object
    methods: dict


class EarlyExit(BaseException):
    def __init__(self, key, result):
        self.key, self.result = key, result


def catch_exit(compute, key, finish):
    try:
        result = compute()
    except EarlyExit as error:
        if error.key != key:
            raise
        return error.result
    if isinstance(result, _Request):
        return replace(result, continue_with=lambda supplied: catch_exit(lambda: result.continue_with(supplied), key, finish))
    return finish(result)


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
        self.baselines = {}
        self.borrowed_values = {}
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
            return (t.args[0 if tag == 'Err' else 1],)
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
        def bind(p, t):
            original = t
            t = unwrapped(t)
            kind = p[0]
            if kind == 'wild':
                if not borrowed and not permissions(original)[1]:
                    raise InferenceError('Cannot discard an owned pattern component')
            elif kind == 'bind':
                if borrowed and not permissions(original)[0]:
                    raise InferenceError('Inspection pattern binding requires Dup')
                bound[p[1]] = Binding(value(original, captures=retained.captures))
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
        bind(pattern, retained.type)
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
        result = super()._apply(function, arguments, context)
        retained = function.captures | frozenset().union(*(a.captures for a in arguments))
        for borrowing in borrowed:
            if borrowing is None:
                continue
            argument, binding = borrowing
            if argument.type.name == 'Mut':
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
                retained = self._infer(initial, context)
                if retained.type == t:
                    self.packages[id(expression)] = None
                    return retained
                wanted, actual = permissions(t), permissions(retained.type)
                if any(w and not a for w, a in zip(wanted, actual)):
                    raise InferenceError('Existential usage promises require Dup/Discard of the hidden value', code='type')
                if isinstance(retained.type, Ty) and retained.type.name == t.name:
                    self.packages[id(expression)] = {}
                    return value(t, retained.effects, retained.captures)
                trait = t.name[4:]
                concrete = unwrapped(retained.type)
                head = (trait, concrete.name if isinstance(concrete, Ty) else None)
                contract = self.impl_contracts.get(head)
                if contract is None:
                    raise InferenceError('Existential package requires a matching trait implementation', code='type')
                if self.impl_constraints.get(head):
                    raise InferenceError('Implementation limit: existential implementation constraints', code='unsupported')
                self._apply(value(contract), [retained], context)
                methods = {method: self.trait_methods[(*head, method)] for method in self.dynamic_methods[t.name]}
                self.packages[id(expression)] = methods
                return value(t, retained.effects, retained.captures)
            case ('definitions', _, _, _):
                from source_declarations import infer_declarations
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
                    signature = self.dynamic_methods[t.name].get(method)
                    if signature is None:
                        raise InferenceError('Unknown existential method ' + method, code='type')
                    receiver_type = signature.parameters[0]
                    receiver_type = replace(receiver_type, args=(t,)) if receiver_type.name == 'View' else t
                    target = (method, replace(signature, parameters=(receiver_type, *signature.parameters[1:])))
                else:
                    target = self.methods.get((unwrapped(t).name, method))
                if target is None:
                    return self.primitive_method(expression, method, receiver, arguments, mode, context, retained)
                name, signature = target
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
                    targets = tuple(symbol for (trait, _, member), symbol in self.trait_methods.items()
                                    if trait == t.name[4:] and member == method)
                    self.dynamic_calls[id(expression)] = (parameter.name.lower() if borrowed else '', targets)
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
                    index = 0 if tag == 'Err' else 1
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
                    results.append(result)
                    if result.type != NEVER:
                        states.append({b: b.consumed for b in bindings})
                        resumed.append(resume.used if resume else False)
                if states and any(s != states[0] for s in states[1:]):
                    raise InferenceError('Match arms must agree on ownership consumption')
                if resumed and any(s != resumed[0] for s in resumed[1:]):
                    raise InferenceError('Match arms must agree on resumption use')
                if states:
                    for b, consumed in states[0].items():
                        b.consumed = consumed
                    if resume:
                        resume.used = resumed[0]
                t = NEVER
                for result in results:
                    t = join_type(t, result.type)
                return value(t, ambient(retained.effects, *(r.effects for r in results)),
                             frozenset().union(*(r.captures for r in results)))
            case ('exit_scope', key, expected, body, wrap):
                self.exit_contracts[key] = expected
                self.exit_values[key] = []
                self.exit_active[key] = frozenset(context.active)
                self.exit_outside[key] = {binding for _, binding in context.live} if wrap else set()
                result = self._infer(body, context)
                if wrap:
                    inferred = Ty('Result', (expected.args[0] if expected else UNKNOWN, result.type))
                else:
                    inferred = result.type
                t = join_type(expected, inferred) if expected else inferred
                captures = result.captures
                for exited in self.exit_values.pop(key):
                    t = join_type(t, exited.type)
                    captures |= exited.captures
                del self.exit_active[key]
                del self.exit_outside[key]
                return value(t, result.effects, captures)
            case ('early', key, argument):
                result = self._infer(argument, context)
                expected = self.exit_contracts[key]
                if expected and not compatible(expected, result.type):
                    raise InferenceError('Early return type mismatch', code='type')
                for name, binding in context.live:
                    if (binding not in self.exit_outside[key] and not binding.consumed
                            and not binding.managed and not permissions(binding.value.type)[1]):
                        raise InferenceError(f'Early return would abandon {name}', subject=name)
                self.record_exit(key, result, context)
                return Value(NEVER, result.effects, result.captures)
            case ('propagate', key, argument):
                result = self._infer(argument, context)
                expected = self.exit_contracts[key]
                if not isinstance(result.type, Ty) or result.type.name != 'Result':
                    raise InferenceError('? requires Result', code='type')
                if expected and (expected.name != 'Result' or not compatible(expected.args[0], result.type.args[0])):
                    raise InferenceError('Propagation error type mismatch', code='type')
                for name, binding in context.live:
                    if (binding not in self.exit_outside[key] and not binding.consumed
                            and not binding.managed and not permissions(binding.value.type)[1]):
                        raise InferenceError(f'Propagation would abandon {name}', subject=name)
                self.record_exit(key, value(Ty('Result', (result.type.args[0], NEVER)),
                                            captures=result.captures), context)
                return value(result.type.args[1], result.effects, result.captures)
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
                result = value(Ty(mode.title(), (binding.value.type,)), captures=binding.value.captures)
                self.borrowed_values[id(result)] = (result, binding)
                return result
            case ('region', name, body):
                outside = list(context.bindings.values())
                result = super()._infer_expression(expression, context)
                for binding in outside:
                    if not binding.consumed and any(c.startswith(name + '#') for c in binding.value.captures):
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
                t = declared or (values[0].type if values else UNKNOWN)
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
                if source.type.name != 'List':
                    raise InferenceError('for requires a finite List in this profile', code='type')
                before = {b: b.consumed for b in context.bindings.values()}
                bound = self.bind_pattern(pattern, value(source.type.args[0], captures=source.captures), context)
                previous, start = context.bindings, len(context.live)
                context.bindings = previous | bound
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
                return value(UNIT, ambient(source.effects, result.effects))
            case ('taskgroup', key, body):
                old = context.group
                context.group = (key, context.handlers)
                context.active |= {key}
                result = self._infer(body, context)
                context.group = old
                context.active -= {key}
                if key in result.captures:
                    raise InferenceError('Task handle would escape its taskgroup')
                return replace(result, effects=ambient(result.effects, Row(('suspend',))))
            case ('spawn', closure):
                if context.group is None:
                    raise InferenceError('spawn requires an immediate lexical taskgroup')
                function = self._infer(closure, context)
                if not permissions(function.type.result)[1]:
                    raise InferenceError('Spawned result must satisfy Discard')
                effects = self._resolve(function.type.effects, context)
                for family, key in context.group[1]:
                    if key in effects.labels and not self.baselines.get(key, False):
                        raise InferenceError('Inherited handler must be duplicable and preserve arbitrary child results')
                result = self._apply(function, [], context)
                return value(Ty('Task', (result.type,)), effects, result.captures | {context.group[0]})
            case ('await', task):
                retained = self._infer(task, context)
                if retained.type.name != 'Task':
                    raise InferenceError('await requires Task', code='type')
                effects = ambient(retained.effects, Row(('suspend',)))
                self._control(effects, context)
                group_keys = {c for c in retained.captures if c.startswith('taskgroup:')}
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
        required_mode = {'length': 'view', 'push': 'mut'}.get(method, '')
        if mode != required_mode:
            raise InferenceError(f'{method} requires {required_mode or "consuming"} access')
        inspected = receiver[0] == 'var' and receiver[1] in context.bindings
        binding = context.bindings.get(receiver[1]) if inspected else None
        borrowed = mode in ('view', 'mut')
        if borrowed and binding:
            if binding.consumed:
                raise InferenceError(f'{receiver[1]} was already consumed', subject=receiver[1])
            context.references.add(binding)
            retained = binding.value
        elif retained is None:
            retained = self._infer(receiver, context)
        t = unwrapped(retained.type)
        values = []
        start = len(context.temporaries)
        if not borrowed:
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
        elif method in ('replace', 'set') and t.name == 'Ref' and len(values) == 1:
            if not compatible(t.args[0], values[0].type):
                raise InferenceError('Ref write type mismatch', code='type')
            self._horizon(t.region, values[0].captures)
            result = t.args[0] if method == 'replace' else UNIT
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
        elif method == 'freeze' and t.name == 'DynArray' and not values:
            result = Ty('List', t.args)
            if capture_free(t.args[0]):
                captures = frozenset()
        elif method == 'remove' and t.name == 'List' and len(values) == 1:
            if values[0].type != INT:
                raise InferenceError('List index must be Int', code='type')
            result = Ty('Result', (Ty('Tuple', (Ty('BoundsError'), t)), Ty('Tuple', (t.args[0], t))))
        elif method == 'map' and t.name in ('Option', 'Result') and len(values) == 1:
            callback = values[0]
            if not isinstance(callback.type, Fn) or not callback.type.discard:
                raise InferenceError('Optional callback must satisfy Discard')
            mapped = self._apply(callback, [value(t.args[-1], captures=retained.captures)], context)
            result = replace(t, args=t.args[:-1] + (mapped.type,))
            rows.append(mapped.effects)
        elif method == 'cancel' and t.name == 'Task' and not values:
            result = UNIT
        else:
            raise InferenceError(f'Unknown method {method} for {t.name}', code='type')
        return value(result, ambient(*rows), captures)


def match_value(pattern, retained, output):
    kind = pattern[0]
    if kind == 'wild':
        return True
    if kind == 'bind':
        output[pattern[1]] = _Slot(retained)
        return True
    if kind == 'literal_pat':
        return type(retained) is type(pattern[1]) and retained == pattern[1]
    if kind == 'tuple_pat':
        return isinstance(retained, tuple) and len(retained) == len(pattern)-1 and all(match_value(p, v, output) for p, v in zip(pattern[1:], retained))
    if kind == 'variant_pat':
        return isinstance(retained, Variant) and retained.tag == pattern[2] and len(retained.fields) == len(pattern)-3 and all(match_value(p, v, output) for p, v in zip(pattern[3:], retained.fields))
    if kind == 'record_pat':
        fields = retained.fields if isinstance(retained, Record) else retained
        return all(match_value(p, fields[n], output) for n, p in zip(pattern[2], pattern[3:]))
    return False


def lower_feature(expr, names, lower, checker):
    match expr:
        case ('pack', t, initial):
            methods = checker.packages[id(expr)]
            if methods is None:
                return lower(initial, names)
            return E('pack', t, tuple(methods.items()), lower(initial, names))
        case ('definitions', _, _, _):
            from source_declarations import lower_declarations
            return lower_declarations(expr, names, lower)
        case ('method_call', method, receiver, arguments, mode):
            if id(expr) in checker.dynamic_calls:
                access, _ = checker.dynamic_calls[id(expr)]
                first = E('access', access, receiver[1]) if access else lower(receiver, names)
                return E('dynamic_call', method, first, tuple(lower(a, names) for a in arguments))
            target = checker.method_calls.get(id(expr))
            if target:
                name, access = target
                first = E('access', access, receiver[1]) if access else lower(receiver, names)
                return E('invoke', name, E('evidence'), (first, *(lower(a, names) for a in arguments)))
            return E('primitive_method', method, lower(receiver, names), tuple(lower(a, names) for a in arguments), mode)
        case ('nat', _):
            return expr
        case ('variant', t, tag, args):
            return E('variant', checker.results[id(expr)].type, tag, tuple(lower(a, names) for a in args))
        case ('bindpat', pattern, initial, body):
            return E('bindpat', pattern, lower(initial, names), lower(body, names))
        case ('match', subject, arms):
            return E('match', lower(subject, names), tuple((p, lower(b, names)) for p, b in arms))
        case ('exit_scope', key, expected, body, wrap):
            return E('exit_scope', key, expected, lower(body, names), wrap)
        case ('early' | 'propagate' as kind, key, operand):
            return E(kind, key, lower(operand, names))
        case ('coalesce', first, second):
            return E('coalesce', lower(first, names), lower(second, names))
        case ('access', _, _):
            return expr
        case ('region', _, body):
            return lower(body, names)
        case ('list_values', t, items):
            return E('list_values', t, tuple(lower(item, names) for item in items))
        case ('ref_new', region, initial):
            return E('ref_new', region, lower(initial, names))
        case ('buffer_new', _, _):
            return expr
        case ('primitive_method', method, receiver, arguments, mode):
            return E('primitive_method', method, lower(receiver, names), tuple(lower(a, names) for a in arguments), mode)
        case ('for_each', pattern, iterable, body):
            return E('for_each', pattern, lower(iterable, names), lower(body, names))
        case ('taskgroup', key, body):
            return E('taskgroup', key, lower(body, names))
        case ('spawn' | 'await' as kind, operand):
            return E(kind, lower(operand, names))
    return None


def evaluate_feature(machine, term, environment, evidence, resume):
    def evaluate(body, local=environment):
        return machine.evaluate(body, local, evidence, resume)
    def inspect(name):
        from source_declarations import read_slot
        slot = environment[name]
        if slot.consumed:
            raise RuntimeError(f'Consumed runtime binding {name}')
        return read_slot(name, slot, term)
    match term:
        case ('pack', t, methods, initial):
            return _bind(evaluate(initial), lambda retained: replace(retained, type=t) if isinstance(retained, Package)
                         else Package(t, retained, {method: _read(name, environment) for method, name in methods}))
        case ('dynamic_call', method, receiver, arguments):
            def invoke_package(package):
                return machine.evaluate_arguments(arguments, environment, evidence, resume,
                    lambda args: machine.invoke(package.methods[method], evidence, [package.value, *args]))
            return _bind(evaluate(receiver), invoke_package)
        case ('definitions', _, _, _):
            from source_declarations import evaluate_declarations
            return evaluate_declarations(machine, term, environment, evidence, resume)
        case ('using_method', name, initial, body, cleanup):
            def enter(retained):
                slot = _Slot(retained)
                def finish():
                    if not slot.consumed:
                        slot.consumed = True
                        machine.invoke(_read(cleanup, environment), evidence, [retained])
                return _protect_call(lambda: evaluate(body, environment | {name: slot}), finish)
            return _bind(evaluate(initial), enter)
        case ('nat', number):
            return number
        case ('variant', t, tag, args):
            return machine.evaluate_arguments(args, environment, evidence, resume, lambda values: Variant(t, tag, tuple(values)))
        case ('bindpat', pattern, initial, body):
            def enter(retained):
                bindings = {}
                if not match_value(pattern, retained, bindings):
                    raise Defect('Nonmatching binding pattern', term)
                return evaluate(body, environment | bindings)
            return _bind(evaluate(initial), enter)
        case ('match', subject, arms):
            def select(retained):
                for pattern, body in arms:
                    bindings = {}
                    if match_value(pattern, retained, bindings):
                        return evaluate(body, environment | bindings)
                raise Defect('Non-exhaustive runtime match', term)
            return _bind(evaluate(subject), select)
        case ('exit_scope', key, expected, body, wrap):
            return catch_exit(lambda: evaluate(body), key,
                              lambda result: Variant(expected, 'Ok', (result,)) if wrap else result)
        case ('early', key, argument):
            def leave(result):
                raise EarlyExit(key, result)
            return _bind(evaluate(argument), leave)
        case ('propagate', key, argument):
            def propagate(result):
                if result.tag == 'Err':
                    raise EarlyExit(key, result)
                return result.fields[0]
            return _bind(evaluate(argument), propagate)
        case ('coalesce', option, fallback):
            return _bind(evaluate(option), lambda result: evaluate(fallback) if result.tag == 'None' else result.fields[0])
        case ('access', _, name):
            return inspect(name)
        case ('list_values', _, items):
            return machine.evaluate_arguments(items, environment, evidence, resume, tuple)
        case ('ref_new', _, initial):
            return _bind(evaluate(initial), Cell)
        case ('buffer_new', _, _):
            return Buffer([])
        case ('primitive_method', method, receiver, arguments, mode):
            inspected = mode in ('view', 'mut') and receiver[0] == 'var'
            first = inspect(receiver[1]) if inspected else evaluate(receiver)
            def invoke(retained):
                def apply(args):
                    if method == 'get':
                        return retained.value
                    if method in ('replace', 'set'):
                        previous, retained.value = retained.value, args[0]
                        return previous if method == 'replace' else None
                    if method == 'length':
                        return len(retained.values if isinstance(retained, Buffer) else retained)
                    if method == 'push':
                        retained.values.append(args[0])
                        return None
                    if method == 'freeze':
                        return tuple(retained.values)
                    if method == 'remove':
                        index = args[0]
                        if 0 <= index < len(retained):
                            return Variant(None, 'Ok', ((retained[index], retained[:index] + retained[index+1:]),))
                        return Variant(None, 'Err', (({'index': index, 'length': len(retained)}, retained),))
                    if method == 'map':
                        if retained.tag in ('None', 'Err'):
                            return retained
                        return _bind(machine.invoke(args[0], evidence, [retained.fields[0]]), lambda result: Variant(retained.type, retained.tag, (result,)))
                    if method == 'cancel':
                        machine.tasks.cancel(retained)
                        return None
                    raise RuntimeError('Unknown primitive method ' + method)
                return machine.evaluate_arguments(arguments, environment, evidence, resume, apply)
            return _bind(first, invoke)
        case ('for_each', pattern, iterable, body):
            def loop(items, index=0):
                if index == len(items):
                    return None
                bindings = {}
                if not match_value(pattern, items[index], bindings):
                    raise Defect('Nonmatching iteration pattern', term)
                return _bind(evaluate(body, environment | bindings), lambda _: loop(items, index+1))
            return _bind(evaluate(iterable), loop)
        case ('taskgroup', _, body):
            group = machine.tasks.enter()
            def finish(result):
                machine.tasks.leave(group)
                return result
            def shutdown():
                if not group.closed:
                    machine.tasks.leave(group, abnormal=True)
            return _protect_call(lambda: _bind(evaluate(body), finish), shutdown)
        case ('spawn', closure):
            def spawn(function):
                def child():
                    result = machine.invoke(function, evidence, [])
                    while isinstance(result, _Request):
                        result = machine.handle(result.target, result)
                    return result
                return machine.tasks.spawn(child)
            return _bind(evaluate(closure), spawn)
        case ('await', task):
            machine.events.append(('suspend', False))
            return _bind(evaluate(task), machine.tasks.await_result)
    raise RuntimeError('Unknown extended core expression ' + repr(term))
