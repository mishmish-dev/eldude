"""Bounded handler experiment over inference.py's annotated expression IR.

Named operations per family, scalar parameters/results, conditionals,
and identity or explicit return clauses. Non-Dup frame captures obey an
availability invariant at every resumption; consuming one before resuming is
conservatively rejected. Self recursion, source returns and general control-flow
inference are outside this experiment. This is not an Eldude compiler.
"""
from dataclasses import dataclass, field, replace
import operator

from eldude.core.rows import Row
from eldude.core.inference import (Binding, Checker, Context, E, Fn, INT, UNIT, Ty, InferenceError,
                       ambient, free_names, permissions, value)


class Defect(RuntimeError):
    def __init__(self, message, expression):
        super().__init__(message)
        self.expression = expression
        self.events = ()


def scalar_operation(expression, arguments):
    op = expression[1]
    if expression[0] == 'unary':
        result = arguments[0] if op == '+' else -arguments[0]
    else:
        left, right = arguments
        if op in ('/', '%'):
            if right == 0:
                raise Defect('Integer division or remainder by zero', expression)
            quotient = abs(left) // abs(right) * (-1 if (left < 0) != (right < 0) else 1)
            result = quotient if op == '/' else left - quotient * right
        else:
            operations = {'+': operator.add, '-': operator.sub, '*': operator.mul,
                          '==': operator.eq, '!=': operator.ne, '<': operator.lt,
                          '<=': operator.le, '>': operator.gt, '>=': operator.ge}
            result = operations[op](left, right)
    if expression[0] == 'binary_nat':
        if type(result) is int and result < 0:
            raise Defect('Nat arithmetic produced a negative result', expression)
        return result
    if type(result) is int and not -(2**63) <= result < 2**63:
        raise Defect('Integer arithmetic overflow', expression)
    return result


def operation_type(t):
    return isinstance(t, Ty) and (t.name in ('Int', 'Unit', 'Bool', 'Nat', 'Unknown') or
        ((t.name in ('Option', 'Result', 'Tuple') or t.name.startswith('Enum:')) and all(operation_type(a) for a in t.args)))


def preserves_handler_result(expression, source=None, *, resume=False, aliases=frozenset()):
    """Prove transfer of one opaque result without assuming Dup or Discard.

    The ordinary clause checker still checks types, effects and resources.
    This conservative identity proof additionally rejects any inspection,
    packaging, arbitrary call, duplicate use or loss of the unknown result.
    """
    aliases = aliases | ({source} if source is not None else set())

    def contains_resume(term):
        return isinstance(term, tuple) and (term[:1] == ('resume',) or any(contains_resume(item) for item in term))

    def independent(term):
        return not contains_resume(term) and not (free_names(term) & aliases)

    def transfer(term):
        return preserves_handler_result(term, source, resume=resume, aliases=aliases)

    match expression:
        case ('var', name):
            return source is not None and name == source
        case ('resume', argument):
            return resume and source is None and independent(argument)
        case ('seq', *items) if items:
            return all(independent(item) for item in items[:-1]) and transfer(items[-1])
        case ('if', condition, left, right):
            return independent(condition) and transfer(left) and transfer(right)
        case ('let', name, initial, body):
            if transfer(initial):
                return preserves_handler_result(body, name, aliases=aliases)
            return name != source and independent(initial) and transfer(body)
        case ('using', name, initial, body):
            return name != source and independent(initial) and transfer(body)
        case _:
            return False


@dataclass(frozen=True)
class Operation:
    mode: str
    result: object
    parameters: tuple = ()

    def __post_init__(self):
        if self.mode not in ('tail', 'once', 'affine') or not operation_type(self.result):
            raise InferenceError('Handler experiment requires a valid mode and scalar operation result')
        if any(not operation_type(t) for t in self.parameters):
            raise InferenceError('Implementation limit: operation parameters must be Int or Unit', code='unsupported')


@dataclass
class Frame:
    key: str
    family: str
    outside: set
    captures: dict
    sites: list = field(default_factory=list)
    opaque: bool = False
    collecting: bool = True
    may_abandon: bool = False


@dataclass
class Resumption:
    frame: Frame
    operation: Operation
    output: object
    effects: Row
    captures: dict
    pending: tuple
    used: bool = False


class HandlerChecker(Checker):
    def __init__(self, *, operations=None, **kwargs):
        super().__init__(**kwargs)
        declared = {'Log': Operation('tail', UNIT), 'Abort': Operation('affine', UNIT)} | (operations or {})
        self.operations = {family: {None: contract} if isinstance(contract, Operation) else dict(contract)
                           for family, contract in declared.items()}
        if any(not isinstance(op, Operation) for ops in self.operations.values() for op in ops.values()):
            raise InferenceError('Invalid operation contract')
        # Opaque calls admit the entire family, regardless of declaration order.
        # Retain once too: the inherited inference-only delimiter is tail-only.
        self.modes = {family: 'affine' if any(op.mode == 'affine' for op in ops.values()) else
                             'once' if any(op.mode == 'once' for op in ops.values()) else 'tail'
                      for family, ops in self.operations.items()}
        self.frames = {}
        self.in_call = False

    def sole_operation(self, family):
        if family not in self.operations:
            raise InferenceError('Unknown effect family')
        if len(self.operations[family]) != 1:
            raise InferenceError('Ambiguous legacy operation: use an explicit operation name')
        return next(iter(self.operations[family]))

    def _obligations(self, context):
        # Snapshot identities as well as values: later straight-line consumption
        # must not retroactively discharge an earlier suspended segment.
        entries = [(name, b.value, b.managed, id(b)) for name, b in context.live if not b.consumed]
        entries.extend(('argument temporary', v, False, id(v)) for v in context.temporaries)
        entries.extend(('active access', value(Ty(g.mode.title(), (UNIT,)), grant=g), False, id(g)) for g in context.grants)
        entries.extend(context.suspended)
        if context.resumption is not None and not context.resumption.used:
            entries.extend(context.resumption.pending)
        return tuple(entries)

    def _control(self, row, context, *, mode=None):
        obligations = self._obligations(context)
        for label in row.labels:
            frame = self.frames.get(label)
            if frame and frame.collecting:
                frame.sites.extend(obligations)
                frame.opaque |= self.in_call
        unknown = row.tail and not self.non_abandoning(Row((), row.tail), context.evidence)
        for label in (*row.labels, *(['unknown tail'] if unknown else [])):
            family = self.handler_ids[label][0] if label in self.handler_ids else label
            if family not in ('suspend', 'unknown tail') and (mode or self.modes.get(family)) != 'affine':
                continue
            frame = self.frames.get(label)
            if frame and frame.collecting:
                frame.may_abandon = True
            outside = frame.outside if frame else set()
            for name, retained, managed, identity in obligations:
                if identity not in outside and not managed and not permissions(retained.type)[1]:
                    raise InferenceError(f'Effects may abandon live resource {name}', subject=name)

    def _apply(self, function, arguments, context):
        previous, self.in_call = self.in_call, True
        try:
            return super()._apply(function, arguments, context)
        finally:
            self.in_call = previous

    def _resume(self, supplied, context, implicit=False):
        resume = context.resumption
        if resume is None:
            raise InferenceError('resume is available only inside an operation clause')
        if resume.operation.mode == 'tail' and not implicit:
            raise InferenceError('Explicit resume is forbidden in a tail clause')
        if resume.used:
            raise InferenceError('Cannot resume more than once')
        if supplied.type != resume.operation.result:
            raise InferenceError('Incorrect operation result supplied to resumption')
        for name, binding in resume.captures.items():
            if not permissions(binding.value.type)[0]:
                if binding.consumed:
                    raise InferenceError(f'Frame capture {name} was consumed before transfer', subject=name)
                binding.consumed = True
                self.transfers[name] = self.current_expression
        resume.used = True
        self._control(resume.effects, context)
        return value(resume.output, ambient(supplied.effects, resume.effects))

    def _clause_context(self, outer, frame):
        copies = {name: replace(b, consumed=False, managed=False) for name, b in frame.captures.items()}
        return Context(bindings=dict(copies), live=list(copies.items()), regions=dict(outer.regions),
                       handlers=outer.handlers, names=dict(outer.names), active=outer.active,
                       trace=False, evidence=outer.evidence, grants=outer.grants,
                       effect_variables=outer.effect_variables), copies

    @staticmethod
    def _discharge(bindings):
        for name, binding in bindings.items():
            if not binding.consumed and not permissions(binding.value.type)[1]:
                raise InferenceError(f'Unconsumed handler obligation {name}', subject=name)

    def _handler(self, family, name, body, clauses, returning, context):
        if family not in self.operations:
            raise InferenceError('Unknown effect family')
        operations = self.operations[family]
        seen = set()
        for operation_name, clause in clauses:
            if operation_name in seen:
                raise InferenceError('Duplicate handler operation', expression=clause)
            if operation_name not in operations:
                raise InferenceError(f'Unknown operation {operation_name} for {family}', expression=clause)
            seen.add(operation_name)
            parameters = clause[1] if clause[0] == 'clause' else ()
            if clause != E('forward') and len(parameters) != len(operations[operation_name].parameters):
                raise InferenceError('Operation clause arity mismatch', expression=clause, code='type')
            if len(set(parameters)) != len(parameters):
                raise InferenceError('Duplicate operation clause parameter', expression=clause)
        if seen != operations.keys():
            raise InferenceError('Incomplete handler: missing operations')
        if len(returning) != 3 or returning[0] != 'returning':
            raise InferenceError('Expected a return clause')
        _, result_name, result_body = returning
        free = free_names(returning) | set().union(*(free_names(clause) for _, clause in clauses))
        captures = {}
        for captured in sorted(free & context.bindings.keys()):
            original = context.bindings[captured]
            if original.mode:
                raise InferenceError('Access grants cannot be captured by a handler')
            if original.consumed:
                raise InferenceError(f'{captured} was already consumed', subject=captured)
            captures[captured] = replace(original, managed=False)
            context.references.add(original)
            if not permissions(original.value.type)[0]:
                original.consumed = True
        key = f'{family}@handler:{self.fresh(name)}'
        self.handler_ids[key] = (family, name)
        outside = {entry[3] for entry in self._obligations(context)} | {id(b) for b in captures.values()}
        frame = Frame(key, family, outside, captures)
        self.frames[key] = frame
        if hasattr(self, 'baselines'):
            self.baselines[key] = (
                all(permissions(b.value.type)[0] for b in captures.values())
                and preserves_handler_result(result_body, result_name)
                and all(clause == E('forward') or operations[op].mode == 'tail'
                        or preserves_handler_result(clause[2] if clause[0] == 'clause' else clause, resume=True)
                        for op, clause in clauses))
        old_handlers, old_names, old_active = context.handlers, context.names, context.active
        context.handlers += ((family, key),)
        context.names = context.names | {name: key}
        context.active |= {key}
        start = len(context.live)
        incoming = [(n, b) for n, b in context.live if not b.consumed and not permissions(b.value.type)[1]]
        previously_resumed = context.resumption.used if context.resumption else False
        context.live.extend(captures.items())
        normal = self._infer(body, context)
        del context.live[start:]
        context.handlers, context.names, context.active = old_handlers, old_names, old_active
        frame.collecting = False
        if frame.may_abandon:
            if context.resumption and context.resumption.used != previously_resumed:
                raise InferenceError('Affine completion may skip an enclosing resume')
            for outer_name, binding in incoming:
                if binding.consumed:
                    raise InferenceError(f'Affine completion may skip consumption of {outer_name}', subject=outer_name, expression=body)
        if not operation_type(normal.type):
            raise InferenceError('Implementation limit: handler body results must be Int or Unit',
                                 expression=body, code='unsupported')
        labels = list(normal.effects.labels)
        if key in labels:
            labels.remove(key)
        body_effects = Row(tuple(labels), normal.effects.tail)

        returned_context, returned_captures = self._clause_context(context, frame)
        returned_context.blocked_family = family
        # A normal-return clause keeps the enclosing lexical capability. Share
        # its usage state and live bindings so transfer removes its own frame
        # obligations without dropping outside resources or suspended segments.
        returned_context.resumption = context.resumption
        returned_context.live.extend(context.live)
        returned_context.temporaries = list(context.temporaries)
        returned_context.suspended = context.suspended
        result_binding = Binding(replace(normal, effects=Row()))
        returned_context.bindings[result_name] = result_binding
        returned_context.live.append((result_name, result_binding))
        returned = self._infer(result_body, returned_context)
        if (frame.may_abandon
                and context.resumption and context.resumption.used != previously_resumed):
            raise InferenceError('Affine completion may skip an enclosing resume', expression=result_body)
        try:
            self._discharge(returned_captures)
        except InferenceError as error:
            error.expression = result_body
            raise
        if not operation_type(returned.type):
            raise InferenceError('Implementation limit: handler output must be Int or Unit',
                                 expression=result_body, code='unsupported')

        own_ids = {id(b) for b in captures.values()}
        pending = tuple(entry for entry in frame.sites if entry[3] not in own_ids)

        def check_clause_body(operation_name, clause, residual):
            operation = operations[operation_name]
            parameters, clause_body = clause[1:] if clause[0] == 'clause' else ((), clause)
            clause_context, clause_captures = self._clause_context(context, frame)
            for parameter, declared in zip(parameters, operation.parameters):
                binding = Binding(value(declared))
                clause_context.bindings[parameter] = binding
                clause_context.live.append((parameter, binding))
            # Resources outside this delimiter survive a successful resume.
            clause_context.suspended = self._obligations(context)
            clause_pending = pending
            if frame.opaque and operation.mode != 'affine':
                unknown = value(Ty('Owned', (Ty('Continuation'),)))
                clause_pending += (('opaque suspended continuation', unknown, False, id(frame)),)
            resume = Resumption(frame, operation, returned.type,
                                residual, clause_captures, clause_pending)
            clause_context.resumption = resume
            clause_context.blocked_family = family
            if clause == E('forward'):
                effects = self._resolve(Row((family,)), clause_context)
                self._control(effects, clause_context, mode=operation.mode)
                handled = self._resume(value(resume.operation.result, effects), clause_context, implicit=True)
            else:
                handled = self._infer(clause_body, clause_context)
                if resume.operation.mode == 'tail':
                    handled = self._resume(handled, clause_context, implicit=True)
            if resume.operation.mode == 'once' and not resume.used:
                raise InferenceError('A once clause must resume exactly once')
            if handled.type != returned.type:
                raise InferenceError('Operation clause must produce the handler output')
            self._discharge(clause_captures)
            return ambient(residual, handled.effects)

        def check_clause(operation_name, clause, residual):
            previous, self.current_expression = self.current_expression, clause
            # Diagnostic transfers belong to this alternative's fresh usage
            # state, not normal return or a successful preliminary clause pass.
            transfers = self.transfers
            self.transfers = {n: origin for n, origin in transfers.items() if n not in frame.captures}
            try:
                result = check_clause_body(operation_name, clause, residual)
            except InferenceError as error:
                if error.expression is None:
                    error.expression = clause
                raise
            else:
                self.transfers = transfers
                return result
            finally:
                self.current_expression = previous

        residual = ambient(body_effects, returned.effects)
        effects = ambient(residual, *(check_clause(op, clause, residual) for op, clause in clauses))
        # Resume adds its supplied row; both conditional branches are checked.
        # Union ALL clauses first, then validate every resume
        # against that complete row with fresh bindings/capabilities per clause.
        # Nested handlers follow the same rule. Refuse any unstabilized result.
        if effects != residual:
            checked = ambient(effects, *(check_clause(op, clause, effects) for op, clause in clauses))
            if checked != effects:
                raise InferenceError('Implementation limit: handler residual did not stabilize', code='unsupported')
        self.handled_rows[name] = effects
        return value(returned.type, effects)

    def _operation(self, family, operation_name, named, expressions, context):
        if family not in self.operations:
            raise InferenceError('Unknown effect family')
        if context.blocked_family == family and not named:
            raise InferenceError('An unqualified same-family operation is forbidden inside its clause')
        if named == ['self']:
            raise InferenceError('Self recursion is outside the handler experiment')
        if operation_name not in self.operations[family]:
            raise InferenceError(f'Unknown operation {operation_name} for {family}')
        operation = self.operations[family][operation_name]
        if len(expressions) != len(operation.parameters):
            raise InferenceError('Operation arity mismatch', code='type')
        start = len(context.temporaries)
        arguments = []
        for expression in expressions:
            argument = self._infer(expression, context)
            arguments.append(argument)
            context.temporaries.append(argument)
        del context.temporaries[start:]
        # Reuse call contract matching without marking a direct operation's
        # continuation as opaque. Arguments finish before operation dispatch.
        super()._apply(value(Fn(operation.parameters, operation.result, Row())), arguments, context)
        effects = self._operation_effects(family, named, context)
        self._control(effects, context, mode=operation.mode)
        return value(operation.result, ambient(*(a.effects for a in arguments), effects))

    def _infer_expression(self, expression, context):
        match expression:
            case ('handle', family, name, body, clause, returning):
                return self._handler(family, name, body, ((self.sole_operation(family), clause),), returning, context)
            case ('handle_ops', family, name, body, clauses, returning):
                return self._handler(family, name, body, clauses, returning, context)
            case ('resume', argument):
                return self._resume(self._infer(argument, context), context)
            case ('perform', family, *named):
                return self._operation(family, self.sole_operation(family), named, (), context)
            case ('perform_args', family, arguments, *named):
                return self._operation(family, self.sole_operation(family), named, arguments, context)
            case ('perform_op', family, operation_name, arguments, *named):
                return self._operation(family, operation_name, named, arguments, context)
            case _:
                return super()._infer_expression(expression, context)


@dataclass(frozen=True)
class Evidence:
    family: str
    instance: int | None = None


@dataclass(frozen=True)
class Program:
    core: tuple
    inferred: object
    operations: dict
    origins: dict = field(default_factory=dict)


def compile_program(expression, *, operations=None, checker=None, origins=None):
    """Check first, then lower dispatch and hidden evidence arguments explicitly."""
    checker = checker or HandlerChecker(operations=operations)
    inferred = checker.infer(expression)
    serial = 0
    hidden = {target[0] for target in getattr(checker, 'method_calls', {}).values()}
    hidden.update(getattr(checker, 'cleanup_targets', {}).values())
    hidden.update(name for methods in getattr(checker, 'packages', {}).values()
                  if methods for name in methods.values())

    def evidence_used(term):
        if isinstance(term, Evidence):
            return {term}
        if isinstance(term, tuple):
            return set().union(*(evidence_used(part) for part in term))
        return set()

    lowered_origins = {}

    def lower(expr, names):
        core = lower_expression(expr, names)
        if origins and id(expr) in origins:
            lowered_origins[id(core)] = origins[id(expr)]
        return core

    def lower_expression(expr, names):
        nonlocal serial
        match expr:
            case ('int', _) | ('bool', _) | ('unit',) | ('var', _) | ('acquire', _):
                return expr
            case ('unary' | 'binary' as kind, operator, *operands):
                if kind == 'binary' and getattr(checker, 'results', {}).get(id(operands[0]), None) is not None:
                    if checker.results[id(operands[0])].type == Ty('Nat'):
                        kind = 'binary_nat'
                return E(kind, operator, *(lower(item, names) for item in operands))
            case ('if' | 'while' as kind, *items):
                return E(kind, *(lower(item, names) for item in items))
            case ('seq', *items):
                return E('seq', *(lower(item, names) for item in items))
            case ('tuple', *items):
                return E('tuple', *(lower(item, names) for item in items))
            case ('record', t, fields, *items):
                return E('record', t, fields, *(lower(item, names) for item in items))
            case ('field', name, base):
                return E('field', name, lower(base, names))
            case ('specialize', callee, _):
                return lower(callee, names)
            case ('unpack', pattern, initial, body):
                return E('unpack', pattern, lower(initial, names), lower(body, names))
            case ('let' | 'using' as kind, name, initial, body):
                target = getattr(checker, 'cleanup_targets', {}).get(id(expr))
                if target is not None:
                    return E('using_method', name, lower(initial, names), lower(body, names), target)
                return E(kind, name, lower(initial, names), lower(body, names))
            case ('call', name, *arguments):
                return E('invoke', name, E('evidence'), tuple(lower(a, names) for a in arguments))
            case ('lambda', parameters, body):
                core = lower(body, names)
                fixed = tuple(sorted(evidence_used(core) & set(names.values()),
                                     key=lambda e: (e.family, e.instance)))
                captures = tuple(sorted(free_names(body, {name for name, _ in parameters}) | hidden))
                return E('closure', tuple(name for name, _ in parameters), captures, fixed, core)
            case ('perform', family, *named):
                return lower_expression(E('perform_op', family, checker.sole_operation(family), (), *named), names)
            case ('perform_args', family, arguments, *named):
                return lower_expression(E('perform_op', family, checker.sole_operation(family), arguments, *named), names)
            case ('perform_op', family, operation_name, arguments, *named):
                selected = names[named[0]] if named else Evidence(family)
                return E('dispatch', selected, operation_name, tuple(lower(a, names) for a in arguments))
            case ('clause', parameters, body):
                return E('clause', parameters, lower(body, names))
            case ('resume', supplied):
                return E('resume', lower(supplied, names))
            case ('handle', family, name, body, clause, returning):
                return lower_expression(E('handle_ops', family, name, body,
                                         ((checker.sole_operation(family), clause),), returning), names)
            case ('handle_ops', family, name, body, clauses, ('returning', result_name, result_body)):
                serial += 1
                selected = Evidence(family, serial)
                captures = tuple(sorted(free_names(E('returning', result_name, result_body)) |
                                        set().union(*(free_names(clause) for _, clause in clauses)) |
                                        hidden))
                clause_cores = []
                for operation_name, clause in clauses:
                    forwarding = clause == E('forward')
                    if forwarding:
                        parameters = tuple(f'$argument:{i}' for i in range(len(checker.operations[family][operation_name].parameters)))
                        dispatch = E('dispatch', Evidence(family), operation_name, tuple(E('var', p) for p in parameters))
                        clause_core = E('clause', parameters, dispatch)
                        if origins and id(clause) in origins:
                            lowered_origins[id(clause_core)] = origins[id(clause)]
                            lowered_origins[id(dispatch)] = origins[id(clause)]
                    else:
                        clause_core = lower(clause, names)
                    clause_cores.append((operation_name, clause_core, forwarding))
                return E('install', selected, name, captures,
                         lower(body, names | {name: selected}), tuple(clause_cores),
                         result_name, lower(result_body, names))
            case _:
                from eldude.source.lowering import lower_feature
                extended = lower_feature(expr, names, lower, checker)
                if extended is not None:
                    return extended
                raise InferenceError(f'Expression is outside the executable handler fragment: {expr[0]}')

    return Program(lower(expression, {}), inferred, checker.operations, lowered_origins)


@dataclass
class _Slot:
    value: object
    consumed: bool = False


@dataclass
class _Resource:
    name: str
    identity: int
    closed: bool = False


@dataclass
class _Closure:
    parameters: tuple
    body: tuple
    environment: dict
    fixed: dict


@dataclass(eq=False)
class _Handler:
    evidence: Evidence
    name: str
    captures: dict
    outer_evidence: dict
    clauses: dict
    result_name: str
    result_body: tuple
    enclosing_resume: object


@dataclass
class _Request:
    target: _Handler
    operation: object
    continue_with: object
    abandon: object
    arguments: tuple


@dataclass(frozen=True)
class Execution:
    value: object
    events: tuple


def _dup(retained):
    from eldude.runtime.features import Variant, Record, Cell, Buffer, Package
    from eldude.runtime.tasks import TaskHandle
    if isinstance(retained, (Buffer, TaskHandle)):
        return False
    if isinstance(retained, Cell):
        return True
    if isinstance(retained, Package):
        return permissions(retained.type)[0]
    if isinstance(retained, Record):
        # Constructor types can retain generic placeholders; the actual fields
        # determine structural usage, while nominal restrictions remain binding.
        return retained.type.name not in ('Linear', 'Affine') and all(_dup(v) for v in retained.fields.values())
    if isinstance(retained, Variant):
        return (retained.type is None or retained.type.name not in ('Linear', 'Affine')) and all(_dup(v) for v in retained.fields)
    from eldude.core.declarations import DeclarationClosure
    if isinstance(retained, DeclarationClosure):
        return True
    if isinstance(retained, tuple):
        return all(_dup(item) for item in retained)
    if isinstance(retained, dict):
        return all(_dup(item) for item in retained.values())
    if isinstance(retained, _Resource):
        return False
    if isinstance(retained, _Closure):
        from eldude.core.declarations import GlobalSlot
        return all(isinstance(s, GlobalSlot) or _dup(s.value) for s in retained.environment.values())
    return True


def _read(name, environment, expression=None):
    if name not in environment and name in ('close', 'close_async', 'yield'):
        return name
    slot = environment[name]
    from eldude.core.declarations import GlobalSlot, read_slot
    if isinstance(slot, GlobalSlot):
        return read_slot(name, slot, expression)
    if slot.consumed:
        raise RuntimeError(f'Consumed runtime binding {name}')
    if not _dup(slot.value):
        slot.consumed = True
    return slot.value


def _bind(computation, then):
    if isinstance(computation, _Request):
        return replace(computation, continue_with=lambda result: _bind(computation.continue_with(result), then))
    return then(computation)


def _protect(computation, finish):
    if isinstance(computation, _Request):
        def abandon():
            computation.abandon()
            finish()
        return replace(computation,
                       continue_with=lambda result: _protect_call(lambda: computation.continue_with(result), finish), abandon=abandon)
    finish()
    return computation


def _protect_call(compute, finish):
    from eldude.runtime.features import EarlyExit
    from eldude.runtime.tasks import TaskCancelled
    try:
        computation = compute()
    except (Defect, EarlyExit, TaskCancelled):
        finish()
        raise
    return _protect(computation, finish)


class _Machine:
    def __init__(self, operations):
        self.operations, self.events, self.resources = operations, [], []
        from eldude.runtime.tasks import TaskScheduler
        self.tasks = TaskScheduler()

    def close(self, resource, reason):
        if not isinstance(resource, _Resource) or resource.closed:
            raise RuntimeError('Resource was closed more than once or is invalid')
        if resource.name == 'AsyncFile':
            self.events.append(('suspend', reason == 'cleanup'))
        resource.closed = True
        self.events.append(('close', resource.identity, reason))

    def dispatch(self, selected, operation, evidence, arguments):
        if selected not in evidence:
            raise RuntimeError(f'Unbound handler evidence for {selected.family}')
        target = evidence[selected]
        event = ('dispatch', selected.family, target.name)
        if len(self.operations[selected.family]) > 1:
            event += (operation,)
        self.events.append(event)
        return _Request(target, operation, lambda supplied: supplied, lambda: None, tuple(arguments))

    def invoke(self, function, evidence, arguments):
        if function in ('close', 'close_async'):
            self.close(arguments[0], 'explicit')
            return None
        if function == 'yield':
            self.events.append(('suspend', False))
            self.tasks.yield_now()
            return None
        if not isinstance(function, _Closure):
            raise RuntimeError('Unknown executable callable')
        environment = {name: replace(slot) for name, slot in function.environment.items()}
        environment.update({name: _Slot(a) for name, a in zip(function.parameters, arguments)})
        return self.evaluate(function.body, environment, evidence | function.fixed)

    def handle(self, frame, computation):
        if not isinstance(computation, _Request):
            environment = frame.captures | {frame.result_name: _Slot(computation)}
            return self.evaluate(frame.result_body, environment, frame.outer_evidence, frame.enclosing_resume)
        if computation.target is not frame:
            return replace(computation,
                           continue_with=lambda supplied: self.handle(frame, computation.continue_with(supplied)))
        clause, forwarding = frame.clauses[computation.operation]
        parameters = ()
        if clause[0] == 'clause':
            _, parameters, clause = clause
        mode = self.operations[frame.evidence.family][computation.operation].mode
        implicit = mode == 'tail' or forwarding
        clause_captures = {name: replace(slot) for name, slot in frame.captures.items()}
        clause_environment = clause_captures | {name: _Slot(a) for name, a in zip(parameters, computation.arguments)}
        resumed, abandoned = False, False

        def resume(supplied):
            nonlocal resumed
            if resumed or abandoned:
                raise RuntimeError('Runtime resumption capability already used')
            resumed = True
            frame.captures = {name: replace(slot) for name, slot in clause_captures.items()}
            for name, slot in clause_captures.items():
                if not _dup(slot.value):
                    if slot.consumed:
                        raise RuntimeError(f'Consumed frame capture {name} cannot be transferred')
                    slot.consumed = True
            self.events.append(('resume', frame.name, supplied))
            return self.handle(frame, computation.continue_with(supplied))

        def abandon():
            nonlocal abandoned
            if not resumed and not abandoned:
                abandoned = True
                self.events.append(('abandon', frame.name))
                computation.abandon()

        def evaluate_clause():
            result = self.evaluate(clause, clause_environment, frame.outer_evidence,
                                   None if implicit else resume)
            return _bind(result, resume) if implicit else result

        def completed(result):
            if mode == 'once' and not resumed:
                raise RuntimeError('Once clause completed without resuming')
            return result
        return _protect_call(lambda: _bind(evaluate_clause(), completed), abandon)

    def evaluate_arguments(self, arguments, environment, evidence, resume, then):
        def argument(index, values):
            if index == len(arguments):
                return then(values)
            return _bind(self.evaluate(arguments[index], environment, evidence, resume),
                         lambda retained: argument(index + 1, values + [retained]))
        return argument(0, [])

    def evaluate(self, term, environment, evidence, resume=None):
        # ponytail: recursive continuation closures suffice for these finite
        # examples; an explicit machine stack is needed for unbounded programs.
        match term:
            case ('int' | 'bool', number):
                return number
            case ('unary' | 'binary' | 'binary_nat', _, *operands):
                return self.evaluate_arguments(operands, environment, evidence, resume,
                                               lambda values: scalar_operation(term, values))
            case ('if', condition, then, otherwise):
                return _bind(self.evaluate(condition, environment, evidence, resume),
                             lambda condition: self.evaluate(then if condition else otherwise,
                                                             environment, evidence, resume))
            case ('while', condition, body):
                def after_test(test):
                    if test:
                        return _bind(self.evaluate(body, environment, evidence, resume), lambda _: loop())
                    return None
                def loop():
                    while True:
                        test = self.evaluate(condition, environment, evidence, resume)
                        if isinstance(test, _Request):
                            return _bind(test, after_test)
                        if not test:
                            return None
                        result = self.evaluate(body, environment, evidence, resume)
                        if isinstance(result, _Request):
                            return _bind(result, lambda _: loop())
                return loop()
            case ('unit',):
                return None
            case ('tuple', *items):
                return self.evaluate_arguments(items, environment, evidence, resume, tuple)
            case ('record', t, fields, *items):
                from eldude.runtime.features import Record
                return self.evaluate_arguments(items, environment, evidence, resume,
                                               lambda values: Record(t, dict(zip(fields, values))))
            case ('field', name, base):
                from eldude.runtime.features import Record
                source = environment[base[1]].value if base[0] == 'var' else self.evaluate(base, environment, evidence, resume)
                return _bind(source, lambda record: record.fields[name] if isinstance(record, Record) else record[name])
            case ('unpack', pattern, initial, body):
                def enter_tuple(retained):
                    local = dict(environment)
                    def bind(pattern, retained):
                        if isinstance(pattern, tuple):
                            for p, item in zip(pattern, retained):
                                bind(p, item)
                        else:
                            local[pattern] = _Slot(retained)
                    bind(pattern, retained)
                    return self.evaluate(body, local, evidence, resume)
                return _bind(self.evaluate(initial, environment, evidence, resume), enter_tuple)
            case ('var', name):
                return _read(name, environment, term)
            case ('evidence',):
                return evidence
            case ('acquire', name):
                resource = _Resource(name, len(self.resources) + 1)
                self.resources.append(resource)
                self.events.append(('acquire', name, resource.identity))
                return resource
            case ('closure', parameters, captures, fixed, body):
                from eldude.core.declarations import GlobalSlot
                retained = {name: environment[name] if isinstance(environment[name], GlobalSlot) else _Slot(_read(name, environment))
                            for name in captures if name in environment}
                return _Closure(parameters, body, retained, {key: evidence[key] for key in fixed})
            case ('let' | 'using' as kind, name, initial, body):
                def enter(retained):
                    def evaluate_body():
                        return self.evaluate(body, environment | {name: _Slot(retained)}, evidence, resume)
                    if kind == 'using':
                        def cleanup():
                            if not retained.closed:
                                self.close(retained, 'cleanup')
                        return _protect_call(evaluate_body, cleanup)
                    return evaluate_body()
                return _bind(self.evaluate(initial, environment, evidence, resume), enter)
            case ('seq', first, *rest):
                result = self.evaluate(first, environment, evidence, resume)
                return _bind(result, lambda _: self.evaluate(E('seq', *rest), environment, evidence, resume)) if rest else result
            case ('invoke', name, supplied_evidence, arguments):
                function = _read(name, environment)
                passed = self.evaluate(supplied_evidence, environment, evidence, resume)
                return self.evaluate_arguments(arguments, environment, evidence, resume,
                                               lambda values: self.invoke(function, passed, values))
            case ('dispatch', selected, operation, arguments):
                return self.evaluate_arguments(arguments, environment, evidence, resume,
                                               lambda values: self.dispatch(selected, operation, evidence, values))
            case ('resume', supplied):
                if resume is None:
                    raise RuntimeError('No runtime resumption capability')
                return _bind(self.evaluate(supplied, environment, evidence, resume), resume)
            case ('install', selected, name, captures, body, clauses, result_name, result_body):
                from eldude.core.declarations import GlobalSlot
                retained = {n: environment[n] if isinstance(environment[n], GlobalSlot) else _Slot(_read(n, environment))
                            for n in captures if n in environment}
                frame = _Handler(selected, str(name), retained, evidence,
                                 {op: (clause, forwarding) for op, clause, forwarding in clauses},
                                 result_name, result_body, resume)
                inner = evidence | {selected: frame, Evidence(selected.family): frame}
                return self.handle(frame, self.evaluate(body, environment, inner, resume))
            case _:
                from eldude.runtime.features import evaluate_feature
                return evaluate_feature(self, term, environment, evidence, resume)


def run(program):
    """Execute a checked closed program; events expose dispatch and real cleanup."""
    if program.inferred.effects.tail or any(label not in ('suspend', 'diverge')
                                           for label in program.inferred.effects.labels):
        raise InferenceError('Execution requires closed handler evidence')
    machine = _Machine(program.operations)
    try:
        result = machine.evaluate(program.core, {}, {})
    except Defect as error:
        error.events = tuple(machine.events)
        raise
    if isinstance(result, _Request):
        result.abandon()
        raise RuntimeError('Unhandled runtime evidence target')
    if any(not resource.closed for resource in machine.resources):
        raise RuntimeError('An owned resource was leaked')
    return Execution(result, tuple(machine.events))
