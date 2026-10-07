"""Located source diagnostics and handler lowering shared by source elaboration."""
from dataclasses import dataclass, replace
from pathlib import Path

from effect_rows import Row, Solver
from handlers import Defect, HandlerChecker, Operation, compile_program, run
from inference import Context, E, Fn, INT, UNIT, BOOL, Ty, InferenceError, capture_free, permissions, value
from source_syntax import Diagnostic, Node, parse_source
from source_features import FeatureChecker, substitute


class Symbol(str):
    """Unique binding key whose diagnostic spelling stays source-level."""
    def __new__(cls, spelling, serial):
        result = super().__new__(cls, f'{spelling}#{serial}')
        result.spelling = spelling
        return result

    def __str__(self):
        return self.spelling

    def __format__(self, spec):
        return format(self.spelling, spec)


@dataclass(frozen=True)
class Host:
    name: str


FILE = Ty('Owned', (Ty('File'),))
ASYNC_FILE = Ty('Owned', (Ty('AsyncFile'),))
HOST_TYPES = {'File': FILE, 'AsyncFile': ASYNC_FILE}
HOST_FUNCTIONS = {'acquire', 'acquireAsync', 'close', 'closeAsync', 'yield'}
OTHER_PRIMITIVES = {'Bool', 'Never', 'Text', 'Nat', 'UInt', 'Char', 'Bytes', 'Byte',
                    'Int8', 'Int16', 'Int32', 'Int128', 'Float32', 'Float64',
                    'UInt8', 'UInt16', 'UInt32', 'UInt64', 'UInt128'}


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
        self.trait_methods = getattr(elaborator, 'trait_methods', {})
        self.impl_contracts = getattr(elaborator, 'impl_contracts', {})
        self.impl_constraints = getattr(elaborator, 'impl_constraints', {})
        self.cleanup_methods = getattr(elaborator, 'cleanup_methods', {})
        self.structural_functions = getattr(elaborator, 'recursive_allowed', set())
        self.annotations = elaborator.annotations
        self.results = {}

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
            context = replace(context, regions=context.regions | {r: r for r in regions},
                              active=context.active | set(regions))
            parameters = tuple((name, self.resolve_type(t, context)) for name, t in expression[1])
            result = self._function(parameters, expression[2], context)
            result = replace(result, type=replace(result.type, regions=regions,
                             captures=self.closed_captures(result.captures) - set(regions)))
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

    def resolve_type(self, t, context):
        t = substitute(t, regions=context.regions)
        if not isinstance(t, Fn):
            return replace(t, args=tuple(self.resolve_type(a, context) for a in t.args))
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
        for c in sorted(captures):
            if c in self.handler_ids:
                fixed.setdefault(self.handler_ids[c][0], []).append(c)
        return replace(t, parameters=tuple(self.resolve_type(p, context) for p in t.parameters),
                       result=self.resolve_type(t.result, context), dup=dup, discard=discard,
                       effects=Row(tuple(c for label in t.effects.labels for c in fixed.get(label, (label,))), t.effects.tail),
                       captures=frozenset(captures) if t.captures is not None else None)

    def annotate(self, expression, result, expected):
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
            if self.closed_captures(result.captures) - set(expected.regions) - set(expected.captures or ()):
                raise InferenceError('Capture annotation omits retained obligations', code='type')
            result = replace(result, type=replace(admitted_type(actual, expected), type_vars=expected.type_vars,
                                                 regions=expected.regions, effect_vars=expected.effect_vars),
                             captures=result.captures - set(expected.regions))
        return result


@dataclass(frozen=True)
class SourceProgram:
    ast: Node
    expression: tuple
    program: object
    functions: dict
    handled_rows: dict

    @property
    def inferred(self):
        return self.program.inferred


class Elaborator:
    def __init__(self, ast):
        self.ast = ast
        self.module = ast.items[0].items[0]
        self.serial = 0
        self.values, self.types = {}, {'Int': INT, 'Int64': INT, 'Unit': UNIT, 'Bool': BOOL}
        self.effects, self.operations, self.definitions = {}, {}, {}
        self.origins, self.annotations, self.declarations = {}, {}, {}
        self.references = {}
        self.current_function = None
        self.records = {}
        self.resolving_records = set()

    def error(self, code, message, node, related=()):
        raise Diagnostic(code, message, node.span, related)

    def limit(self, message, node):
        self.error('unsupported', 'Implementation limit: ' + message, node)

    def symbol(self, name):
        self.serial += 1
        symbol = Symbol(name.items[0], self.serial)
        self.declarations[symbol] = name.span
        return symbol

    def ir(self, node, kind, *parts):
        expression = E(kind, *parts)
        self.origins[id(expression)] = node.span
        return expression

    def local_name(self, path):
        name = path.items[0]
        prefix = self.module + '::'
        return name[len(prefix):] if name.startswith(prefix) else name

    def public_contract(self, item):
        if isinstance(item, Node):
            if item.kind == 'contract':
                for entry in item.items[1]:
                    family = self.effects.get(self.local_name(entry))
                    if family is not None and not family.items[0]:
                        self.error('name', 'Public contract exposes a private effect', entry)
            self.public_contract(item.items)
        elif isinstance(item, tuple):
            for child in item:
                self.public_contract(child)

    def expression(self, node, environment, handlers):
        match node.kind, node.items:
            case 'int', (number,):
                if not -(2**63) <= number < 2**63:
                    self.error('type', 'Integer literal is outside the Int64 range', node)
                return self.ir(node, 'int', number)
            case 'unit', ():
                return self.ir(node, 'unit')
            case 'bool', (boolean,):
                return self.ir(node, 'bool', boolean)
            case 'tuple', (items,):
                return self.ir(node, 'tuple', *(self.expression(item, environment, handlers) for item in items))
            case 'record', (path, fields):
                name = self.local_name(path)
                if name not in self.records:
                    self.error('name', 'Unknown record ' + name, path)
                t = self.types[name]
                names = [name.items[0] for name, _ in fields]
                if len(set(names)) != len(names) or set(names) != {f.name for f in t.args}:
                    self.error('type', 'Record fields must match the declaration exactly', node)
                # Source order governs evaluation, even when fields are reordered.
                expression = self.ir(node, 'record', t, tuple(names),
                                     *(self.expression(item, environment, handlers) for _, item in fields))
                return expression
            case 'field', (base, name):
                return self.ir(node, 'field', name.items[0], self.expression(base, environment, handlers))
            case 'specialize', (callee, arguments):
                return self.ir(node, 'specialize', self.expression(callee, environment, handlers),
                               tuple(self.type(t) for t in arguments))
            case 'unary', (operator, operand):
                return self.ir(node, 'unary', operator, self.expression(operand, environment, handlers))
            case 'binary', (operator, left, right):
                return self.ir(node, 'binary', operator, self.expression(left, environment, handlers),
                               self.expression(right, environment, handlers))
            case 'if', branches:
                return self.ir(node, 'if', *(self.expression(b, environment, handlers) for b in branches))
            case 'path', _:
                symbol = self.lookup(node, environment)
                if isinstance(symbol, Host):
                    self.limit('fixture primitives must be called directly; wrap one in a source closure to pass it', node)
                return self.ir(node, 'var', symbol)
            case 'block', (statements, result):
                def sequence(index, local):
                    if index == len(statements):
                        return self.expression(result, local, handlers)
                    statement = statements[index]
                    if statement.kind == 'let':
                        name, annotation, initializer = statement.items
                        initial = self.expression(initializer, local, handlers)
                        if annotation:
                            self.annotations.setdefault(id(initial), []).append(self.type(annotation))
                        if name.kind == 'tuple_pattern':
                            local = dict(local)
                            names = set()
                            def pattern(node):
                                if node.kind == 'tuple_pattern':
                                    return tuple(pattern(p) for p in node.items[0])
                                spelling = node.items[0]
                                if spelling != '_' and spelling in names:
                                    self.error('name', 'Duplicate pattern binding', node)
                                names.add(spelling)
                                symbol = self.symbol(node)
                                local[spelling] = symbol
                                return symbol
                            bound = pattern(name)
                            return self.ir(statement, 'unpack', bound, initial, sequence(index + 1, local))
                        if name.items[0] == '_':
                            return self.ir(statement, 'seq', initial, sequence(index + 1, local))
                        symbol = self.symbol(name)
                        return self.ir(statement, 'let', symbol, initial,
                                       sequence(index + 1, local | {name.items[0]: symbol}))
                    expression = self.expression(statement.items[0], local, handlers)
                    return self.ir(statement, 'seq', expression, sequence(index + 1, local))
                return sequence(0, environment)
            case 'lambda', (parameters, contract, body):
                return self.function(node, parameters, contract, body, environment, handlers)
            case 'call', (callee, arguments):
                if callee.kind == 'path':
                    symbol = self.lookup(callee, environment)
                    args = tuple(self.expression(a, environment, handlers) for a in arguments)
                    if isinstance(symbol, Host):
                        name = symbol.name
                        arity = 1 if name in ('close', 'closeAsync') else 0
                        if len(args) != arity:
                            self.error('type', 'Callable arity mismatch', node)
                        if name in ('acquire', 'acquireAsync'):
                            return self.ir(node, 'acquire', 'File' if name == 'acquire' else 'AsyncFile')
                        return self.ir(node, 'call', 'close_async' if name == 'closeAsync' else name, *args)
                    return self.ir(node, 'call', symbol, *args)
                initial = self.expression(callee, environment, handlers)
                temporary = self.symbol(Node('name', callee.span, ('callable',)))
                arguments = tuple(self.expression(a, environment, handlers) for a in arguments)
                return self.ir(node, 'let', temporary, initial, self.ir(node, 'call', temporary, *arguments))
            case 'resume', (arguments,):
                if len(arguments) != 1:
                    self.error('type', 'resume requires exactly one operation result', node)
                return self.ir(node, 'resume', self.expression(arguments[0], environment, handlers))
            case 'perform', (path, arguments):
                name = self.local_name(path)
                if '::' not in name:
                    self.error('name', 'Operation requires an effect family or instance qualifier', path)
                qualifier, operation = name.rsplit('::', 1)
                named = ()
                if qualifier == 'self':
                    self.limit('self recursion is not implemented', node)
                if qualifier in handlers and not path.items[0].startswith(self.module + '::'):
                    family, symbol = handlers[qualifier]
                    named = (symbol,)
                else:
                    family = qualifier
                    if family not in self.effects:
                        self.error('name', f'Unknown effect or handler instance {family}', path)
                if operation not in self.operations[family]:
                    self.error('name', f'Unknown operation {operation} for {family}', path)
                args = tuple(self.expression(a, environment, handlers) for a in arguments)
                return self.ir(node, 'perform_op', family, operation, args, *named)
            case 'using', (acquisitions, body):
                def acquire(index, local):
                    if index == len(acquisitions):
                        return self.expression(body, local, handlers)
                    acquisition = acquisitions[index]
                    name, initializer = acquisition.items
                    initial = self.expression(initializer, local, handlers)
                    symbol = self.symbol(name)
                    return self.ir(acquisition, 'using', symbol, initial,
                                   acquire(index + 1, local | {name.items[0]: symbol}))
                return acquire(0, environment)
            case 'handle', (family_node, name, body, clauses):
                family = self.effect_family(family_node) if hasattr(self, 'effect_family') else self.local_name(family_node)
                if family not in self.effects:
                    self.error('name', f'Unknown effect family {family}', family_node)
                symbol = self.symbol(name or Node('name', family_node.span, (family,)))
                inner = handlers | ({name.items[0]: (family, symbol)} if name else {})
                handled = self.expression(body, environment, inner)
                operation_clauses = {}
                returning = fallback = None
                for clause in clauses:
                    if clause.kind == 'returning':
                        if returning is not None:
                            self.error('name', 'Duplicate return clause', clause)
                        returning = clause
                    elif clause.kind == 'forward' and clause.items[0].items[0] == '..':
                        if fallback is not None:
                            self.error('name', 'Duplicate forwarding clause', clause)
                        fallback = clause
                    else:
                        operation = clause.items[0].items[0]
                        if operation not in self.operations[family]:
                            self.error('name', f'Unknown handler operation for {family}', clause.items[0])
                        if operation in operation_clauses:
                            self.error('name', 'Duplicate handler operation', clause.items[0])
                        operation_clauses[operation] = clause
                checked_clauses = []
                for operation, signature in self.operations[family].items():
                    operation_clause = operation_clauses.get(operation, fallback)
                    if operation_clause is None:
                        self.error('semantic', f'Incomplete handler: missing {operation}', family_node)
                    if operation_clause.kind == 'forward':
                        operation_body = self.ir(operation_clause, 'forward')
                    else:
                        _, parameters, clause_body = operation_clause.items
                        if len(parameters) != len(signature.parameters):
                            self.error('type', 'Operation clause arity mismatch', operation_clause.items[0])
                        local, bound, names = dict(environment), [], set()
                        for parameter in parameters:
                            spelling = parameter.items[0]
                            if spelling != '_' and spelling in names:
                                self.error('name', 'Duplicate operation clause parameter', parameter)
                            names.add(spelling)
                            parameter_symbol = self.symbol(parameter)
                            local[spelling] = parameter_symbol
                            bound.append(parameter_symbol)
                        operation_body = (self.clause_expression(clause_body, local, handlers, signature)
                                          if hasattr(self, 'clause_expression') else self.expression(clause_body, local, handlers))
                        if bound:
                            operation_body = self.ir(clause_body, 'clause', tuple(bound), operation_body)
                    checked_clauses.append((operation, operation_body))
                if returning:
                    result, result_body = returning.items
                    result_symbol = self.symbol(result)
                    returned = self.expression(result_body, environment | {result.items[0]: result_symbol}, handlers)
                else:
                    result_symbol = self.symbol(Node('name', node.span, ('answer',)))
                    returned = self.ir(node, 'var', result_symbol)
                return self.ir(node, 'handle_ops', family, symbol, handled, tuple(checked_clauses),
                               self.ir(returning or node, 'returning', result_symbol, returned))
        self.limit(f'{node.kind} is not implemented', node)



def compile_source(text, filename='<source>'):
    from source_elaboration import SourceElaborator
    return SourceElaborator(parse_source(text, filename)).compile()


def compile_file(path):
    path = Path(path)
    return compile_source(path.read_text(encoding='utf-8'), str(path))


def execute_file(path):
    program = compile_file(path)
    try:
        return run(program.program)
    except Defect as error:
        span = program.program.origins.get(id(error.expression), program.ast.span)
        raise Diagnostic('defect', str(error), span) from error
