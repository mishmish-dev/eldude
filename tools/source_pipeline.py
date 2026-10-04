"""Resolve located Eldude source into the existing checked/executable expression IR.

The only external module executed here is the explicit eldude::fixture profile.
This is single-file, nonrecursive elaboration, not general module loading.
"""
from dataclasses import dataclass, replace
from pathlib import Path

from effect_rows import Row, Solver
from handlers import HandlerChecker, Operation, compile_program, run
from inference import Context, E, Fn, INT, UNIT, Ty, InferenceError, capture_free, value
from source_syntax import Diagnostic, Node, parse_source


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
    for part in expression[1:]:
        if isinstance(part, tuple) and part and isinstance(part[0], str):
            yield part


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
                       effects=declared.effects)
    return actual


class SourceChecker(HandlerChecker):
    """Annotation adapter; all type/row/ownership rules remain in the core checker."""
    def __init__(self, elaborator):
        super().__init__(operations=elaborator.operations,
                         imports={'close_async': Fn((ASYNC_FILE,), UNIT, Row(('suspend',)))})
        self.annotations = elaborator.annotations
        self.results = {}

    def effect_origin(self, expression, labels):
        for child in children(expression):
            result = self.results.get(id(child))
            if result and set(result.effects.labels) & labels:
                return self.effect_origin(child, labels)
        return expression

    def _infer_expression(self, expression, context):
        result = super()._infer_expression(expression, context)
        self.results[id(expression)] = result
        for expected in self.annotations.get(id(expression), ()):
            result = self.annotate(expression, result, expected)
        self.results[id(expression)] = result
        return result

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
            if result.captures:
                raise InferenceError('Capture annotation omits retained obligations', code='type')
            result = replace(result, type=admitted_type(actual, expected))
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
        self.values, self.types = {}, {'Int': INT, 'Int64': INT, 'Unit': UNIT}
        self.effects, self.operations, self.definitions = {}, {}, {}
        self.origins, self.annotations, self.declarations = {}, {}, {}
        self.references = {}
        self.current_function = None

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

    def collect(self):
        declared = {}
        def reserve(name):
            spelling = name.items[0]
            if spelling in declared or spelling in ('Int', 'Int64', 'Unit'):
                related = [('Previous declaration', declared[spelling])] if spelling in declared else []
                self.error('name', f'Duplicate declaration {spelling}', name, related)
            declared[spelling] = name.span

        for declaration in self.ast.items[1]:
            if declaration.kind == 'import':
                _, path, names = declaration.items
                if path.items[0] != 'eldude::fixture':
                    self.limit('only imports from eldude::fixture execute', path)
                for original, alias in names:
                    reserve(alias)
                    name = original.items[0]
                    if name in HOST_TYPES:
                        self.types[alias.items[0]] = HOST_TYPES[name]
                    elif name in HOST_FUNCTIONS:
                        self.values[alias.items[0]] = Host(name)
                    else:
                        self.error('name', f'Unknown fixture export {name}', original)
            else:
                name = declaration.items[1]
                reserve(name)
                if declaration.kind == 'effect':
                    self.effects[name.items[0]] = declaration
                else:
                    symbol = self.symbol(name)
                    self.values[name.items[0]] = symbol
                    self.definitions[symbol] = declaration

        for family, declaration in self.effects.items():
            operations = declaration.items[2]
            names = set()
            for operation in operations:
                name = operation.items[1]
                if name.items[0] in names:
                    self.error('name', 'Duplicate operation declaration', name)
                names.add(name.items[0])
            if len(operations) != 1:
                self.limit('exactly one operation per family is supported', operations[1] if len(operations) > 1 else declaration)
            mode, name, parameters, result = operations[0].items
            if parameters:
                self.limit('operation parameters are not implemented', parameters[0])
            result_type = self.type(result)
            if result_type not in (INT, UNIT):
                self.limit('operation results must currently be Int or Unit', result)
            self.operations[family] = Operation(mode, result_type)

    def type(self, node):
        if node.kind == 'type':
            name = self.local_name(node)
            if name not in self.types:
                if name in OTHER_PRIMITIVES:
                    self.limit(f'type {name} does not execute in this slice', node)
                self.error('name', f'Unknown type {name}', node)
            return self.types[name]
        parameters, contract = node.items
        result, effects = self.contract(contract)
        bound = frozenset() if capture_free(result) else frozenset({'env'} | {f'arg:{i}' for i in range(len(parameters))})
        return Fn(tuple(self.type(p) for p in parameters), result, effects, bound)

    def contract(self, node):
        result, entries = node.items
        effects = []
        for entry in entries:
            name = self.local_name(entry)
            if name not in self.effects and name not in ('suspend', 'diverge'):
                self.error('name', f'Unknown effect {name}', entry)
            effects.append(name)
        return self.type(result), Row(tuple(effects))

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

    def lookup(self, node, environment):
        name = self.local_name(node)
        if node.items[0].startswith(self.module + '::'):
            environment = self.values
        if name not in environment or name == '_':
            self.error('name', f'Unknown value {name}', node)
        symbol = environment[name]
        if symbol in self.definitions and self.current_function is not None:
            self.references[self.current_function].setdefault(symbol, node)
        return symbol

    def function(self, node, parameters, contract, body, environment, handlers):
        local, typed, names = dict(environment), [], set()
        for parameter in parameters:
            name, annotation = parameter.items
            if name.items[0] in names:
                self.error('name', 'Duplicate parameter', name)
            names.add(name.items[0])
            if annotation is None:
                self.limit('closure parameters require type annotations', name)
            symbol = self.symbol(name)
            local[name.items[0]] = symbol
            typed.append((symbol, self.type(annotation)))
        expression = self.ir(node, 'lambda', tuple(typed), self.expression(body, local, handlers))
        if contract is not None:
            result, effects = self.contract(contract)
            self.annotations.setdefault(id(expression), []).append(Fn(tuple(t for _, t in typed), result, effects))
        return expression

    def expression(self, node, environment, handlers):
        match node.kind, node.items:
            case 'int', (number,):
                if not -(2**63) <= number < 2**63:
                    self.error('type', 'Integer literal is outside the Int64 range', node)
                return self.ir(node, 'int', number)
            case 'unit', ():
                return self.ir(node, 'unit')
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
                if arguments:
                    self.limit('operation arguments are not implemented', node)
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
                declared = self.effects[family].items[2][0].items[1].items[0]
                if operation != declared:
                    self.error('name', f'Unknown operation {operation} for {family}', path)
                return self.ir(node, 'perform', family, *named)
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
                family = self.local_name(family_node)
                if family not in self.effects:
                    self.error('name', f'Unknown effect family {family}', family_node)
                symbol = self.symbol(name or Node('name', family_node.span, (family,)))
                inner = handlers | ({name.items[0]: (family, symbol)} if name else {})
                handled = self.expression(body, environment, inner)
                operation = self.effects[family].items[2][0].items[1].items[0]
                operation_clause = returning = fallback = None
                for clause in clauses:
                    if clause.kind == 'returning':
                        if returning is not None:
                            self.error('name', 'Duplicate return clause', clause)
                        returning = clause
                    elif clause.kind == 'forward' and clause.items[0].items[0] == '..':
                        if fallback:
                            self.error('name', 'Duplicate forwarding clause', clause)
                        fallback = clause
                    else:
                        if clause.items[0].items[0] != operation:
                            self.error('name', f'Unknown handler operation for {family}', clause.items[0])
                        if operation_clause is not None:
                            self.error('name', 'Duplicate handler operation', clause.items[0])
                        operation_clause = clause
                operation_clause = operation_clause or fallback
                if operation_clause is None:
                    self.error('semantic', f'Incomplete handler: missing {operation}', family_node)
                if operation_clause.kind == 'forward':
                    operation_body = self.ir(operation_clause, 'forward')
                else:
                    _, parameters, clause_body = operation_clause.items
                    if parameters:
                        self.limit('operation clause parameters are not implemented', parameters[0])
                    operation_body = self.expression(clause_body, environment, handlers)
                if returning:
                    result, result_body = returning.items
                    result_symbol = self.symbol(result)
                    returned = self.expression(result_body, environment | {result.items[0]: result_symbol}, handlers)
                else:
                    result_symbol = self.symbol(Node('name', node.span, ('answer',)))
                    returned = self.ir(node, 'var', result_symbol)
                return self.ir(node, 'handle', family, symbol, handled, operation_body,
                               self.ir(returning or node, 'returning', result_symbol, returned))
        self.limit(f'{node.kind} is not implemented', node)

    def compile(self):
        self.collect()
        expressions = {}
        for symbol, declaration in self.definitions.items():
            self.current_function = symbol
            self.references[symbol] = {}
            public, _, parameters, contract, body = declaration.items
            if public:
                self.public_contract((parameters, contract))
            expressions[symbol] = self.function(declaration, parameters, contract, body, self.values, {})
        self.current_function = None
        order, visiting, done = [], set(), set()
        def visit(symbol):
            if symbol in done:
                return
            visiting.add(symbol)
            for dependency, node in self.references[symbol].items():
                if dependency in visiting:
                    self.limit('recursion between source functions is not implemented', node)
                visit(dependency)
            visiting.remove(symbol)
            done.add(symbol)
            order.append(symbol)
        for symbol in expressions:
            visit(symbol)
        main = self.values.get('main')
        if main not in self.definitions or not self.definitions[main].items[0]:
            self.error('entry', 'Fixture runner requires an exported main function', self.ast)
        declaration = self.definitions[main]
        if declaration.items[2]:
            self.error('entry', 'Fixture main must have no parameters', declaration.items[1])
        if self.annotations[id(expressions[main])][0].result not in (INT, UNIT):
            self.limit('fixture main must return Int or Unit', declaration.items[3])
        expression = self.ir(declaration.items[1], 'call', main)
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
            body = expressions[main][2]
            origin = checker.effect_origin(body, set(program.inferred.effects.labels))
            span = self.origins.get(id(origin), declaration.items[3].span)
            raise Diagnostic('effect', 'Fixture main requires closed handler evidence; an operation remains unhandled', span)
        functions = {str(symbol): checker.results[id(body)].type for symbol, body in expressions.items()}
        return SourceProgram(self.ast, expression, program, functions,
                             {str(name): row for name, row in checker.handled_rows.items()})


def compile_source(text, filename='<source>'):
    return Elaborator(parse_source(text, filename)).compile()


def compile_file(path):
    path = Path(path)
    return compile_source(path.read_text(encoding='utf-8'), str(path))


def execute_file(path):
    return run(compile_file(path).program)
