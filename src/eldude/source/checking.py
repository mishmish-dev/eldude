"""Adapt written source contracts to the expression checker."""
from dataclasses import replace

from eldude.core.rows import Row, Solver
from eldude.core.inference import Context, Fn, UNIT, Ty, InferenceError, permissions, value, required_captures
from eldude.source.features import FeatureChecker
from eldude.core.model import Symbol
from eldude.core.types import ASYNC_FILE, substitute


def children(expression):
    if expression[0] in ('perform_args', 'perform_op'):
        yield from expression[2 if expression[0] == 'perform_args' else 3]
        return
    if expression[0] == 'handle_ops':
        yield expression[3]
        for _, clause in expression[4]:
            yield clause[2] if clause[0] == 'clause' else clause
        yield expression[5]
        return
    for part in expression[1:]:
        if isinstance(part, tuple) and part and isinstance(part[0], str):
            yield part[2] if part[0] == 'clause' else part


def result_expression(expression):
    match expression:
        case ('let' | 'using', _, _, body):
            return result_expression(body)
        case ('seq', *items):
            return result_expression(items[-1])
        case _:
            return expression


def admitted_type(actual, declared):
    """Keep inferred whole-value bounds while honoring every written call row."""
    if isinstance(actual, Fn) and isinstance(declared, Fn):
        return replace(actual, result=admitted_type(actual.result, declared.result),
                       effects=declared.effects, captures=declared.captures,
                       dup=declared.dup, discard=declared.discard)
    return actual


class SourceChecker(FeatureChecker):
    """Annotation adapter; all type/row/ownership rules remain in the core checker."""
    def __init__(self, elaborator):
        super().__init__(operations=elaborator.operations,
                         imports={'close_async': Fn((ASYNC_FILE,), UNIT, Row(('suspend',)))})
        self.variants = getattr(elaborator, 'variants', {})
        self.data_parameters = getattr(elaborator, 'data_parameters', {})
        self.methods = getattr(elaborator, 'methods', {})
        self.dynamic_methods = getattr(elaborator, 'dynamic_methods', {})
        self.interfaces = getattr(elaborator, 'interfaces', {})
        self.interface_members = getattr(elaborator, 'interface_members', {})
        self.interface_variables = getattr(elaborator, 'interface_variables', {})
        self.trait_methods = getattr(elaborator, 'trait_methods', {})
        self.impl_contracts = getattr(elaborator, 'impl_contracts', {})
        self.impl_constraints = getattr(elaborator, 'impl_constraints', {})
        self.cleanup_methods = getattr(elaborator, 'cleanup_methods', {})
        self.structural_functions = getattr(elaborator, 'recursive_allowed', set())
        self.annotations = elaborator.annotations
        self.results = {}
        self.trait_solver = getattr(elaborator, 'trait_solver', None)
        self.origins = elaborator.origins

    def _infer(self, expression, context):
        try:
            return super()._infer(expression, context)
        except InferenceError as error:
            if id(error.expression) not in self.origins and id(expression) in self.origins:
                error.expression = expression
            raise

    def effect_origin(self, expression, labels):
        for child in children(expression):
            result = self.results.get(id(child))
            if result and set(result.effects.labels) & labels:
                return self.effect_origin(child, labels)
        return expression

    def _infer_expression(self, expression, context):
        annotations = self.annotations.get(id(expression), ())
        if expression[0] == 'lambda':
            signature = annotations[0] if annotations and isinstance(annotations[0], Fn) else None
            regions = signature.regions if signature else ()
            capture_vars = signature.capture_vars if signature else ()
            context = replace(context, regions=context.regions | {r: r for r in regions},
                              active=context.active | set(regions),
                              evidence=context.evidence + (signature.constraints if signature else ()),
                              effect_variables=context.effect_variables | {v.name: v for v in signature.effect_vars} if signature else context.effect_variables)
            parameters = tuple((name, self.resolve_type(t, context)) for name, t in expression[1])
            result = self._function(parameters, expression[2], context)
            retained = self.closed_captures(result.captures) - set(regions) - set(capture_vars)
            result = replace(result, type=replace(result.type, regions=regions, capture_vars=capture_vars,
                             captures=retained), captures=result.captures - set(capture_vars))
        else:
            result = super()._infer_expression(expression, context)
        self.results[id(expression)] = result
        for expected in annotations:
            result = self.annotate(expression, result, self.resolve_type(expected, context))
        self.results[id(expression)] = result
        return result

    def closed_captures(self, captures):
        """Expand closed annotations without narrowing whole-argument bounds."""
        return frozenset().union(*(self.capture_sources.get(c, {c}) for c in captures))

    def _apply(self, function, arguments, context):
        result = super()._apply(function, arguments, context)
        if isinstance(result.type, Ty) and result.type.name.startswith('Any:'):
            result = replace(result, type=self.resolve_type(result.type, context))
        return result

    def resolve_type(self, t, context):
        original = t
        t = substitute(t, regions=context.regions, effect_variables=context.effect_variables)
        if not isinstance(t, Fn):
            t = replace(t, args=tuple(self.resolve_type(a, context) for a in t.args))
            mapping_types, mapping_regions = {}, context.regions
            if t.name.startswith('Any:') and original not in self.dynamic_methods:
                from eldude.core.traits import match
                for template in tuple(self.dynamic_methods):
                    if template.name != t.name:
                        continue
                    type_vars, region_vars = self.interface_variables.get(template, ((), ()))
                    try:
                        mapping_types, mapping_regions = match(template, t, type_vars, region_vars)
                    except ValueError:
                        continue
                    original = template
                    break
            if original in self.dynamic_methods and t not in self.dynamic_methods:
                self.dynamic_methods[t] = {name: substitute(signature, mapping_types, mapping_regions, context.effect_variables)
                                           for name, signature in self.dynamic_methods[original].items()}
                self.interfaces[t] = tuple((name, tuple(substitute(a, mapping_types, mapping_regions) for a in arguments),
                                           tuple((n, substitute(v, mapping_types, mapping_regions)) for n, v in bindings))
                                          for name, arguments, bindings in self.interfaces[original])
                for name in self.dynamic_methods[t]:
                    trait, arguments, member = self.interface_members[(original, name)]
                    self.interface_members[(t, name)] = (trait, tuple(substitute(a, mapping_types, mapping_regions) for a in arguments), member)
            if self.trait_solver:
                try:
                    t = self.trait_solver.normalize_type(t, context.evidence)
                except ValueError as error:
                    raise InferenceError(str(error)) from error
            return t
        captures, dup, discard = set(), t.dup, t.discard
        for source in t.captures or ():
            if isinstance(source, Symbol):
                if source in context.bindings:
                    binding = context.bindings[source]
                    if binding.mode:
                        raise InferenceError('Access grants cannot appear in capture contracts')
                    captures.update(self.closed_captures(binding.value.captures))
                    d, s = permissions(binding.value.type)
                    dup, discard = dup and d, discard and s
                elif source in context.names:
                    captures.add(context.names[source])
                else:
                    raise InferenceError('Unknown capture ' + str(source), code='name')
            else:
                captures.add(source)
        fixed = {}
        for c in sorted(captures, key=str):
            if c in self.handler_ids:
                fixed.setdefault(self.handler_ids[c][0], []).append(c)
        return replace(t, parameters=tuple(self.resolve_type(p, context) for p in t.parameters),
                       result=self.resolve_type(t.result, context), dup=dup, discard=discard,
                       effects=Row(tuple(c for label in t.effects.labels for c in fixed.get(label, (label,))), t.effects.tail),
                       captures=frozenset(captures) if t.captures is not None else None)

    def annotate(self, expression, result, expected):
        if isinstance(expected, Fn):
            expected = self.resolve_type(expected, Context(regions={r: r for r in expected.regions},
                                                         active=frozenset(expected.regions), evidence=expected.constraints,
                                                         effect_variables={v.name: v for v in expected.effect_vars}))
        actual = result.type
        if isinstance(expected, Fn) and isinstance(actual, Fn):
            solver = Solver()
            try:
                solver.unify(expected.effects, solver.weaken(actual.effects))
            except ValueError as error:
                body = expression[2] if expression[0] == 'lambda' else expression
                origin = self.effect_origin(body, set(actual.effects.labels) - set(expected.effects.labels))
                raise InferenceError('Effect mismatch: body exceeds its declared effect row',
                                     expression=origin, code='effect') from error
            # ResultCaptureBound is inferred semantic metadata, not a source
            # capture clause. An annotation must not erase the inferred bound.
            expected = replace(expected, bound=actual.bound)
        try:
            self._apply(value(Fn((expected,), UNIT, Row())), [result], Context())
        except InferenceError as error:
            error.expression = result_expression(expression[2]) if expression[0] == 'lambda' else expression
            if error.code == 'semantic':
                error.code = 'type'
            raise
        if isinstance(expected, Fn):
            if self.closed_captures(result.captures) - set(expected.regions) - set(expected.captures or ()) - set(required_captures(expected)):
                raise InferenceError('Capture annotation omits retained obligations', code='type')
            result = replace(result, type=replace(admitted_type(actual, expected), type_vars=expected.type_vars,
                                                 regions=expected.regions, effect_vars=expected.effect_vars,
                                                 capture_vars=expected.capture_vars, generic_binders=expected.generic_binders,
                                                 constraints=expected.constraints),
                             captures=result.captures - set(expected.regions))
        return result
