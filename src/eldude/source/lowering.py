"""Lower source expressions and checked feature expressions to handler IR."""
from dataclasses import dataclass

from eldude.core.inference import E, INT, UNIT, BOOL
from eldude.core.model import Symbol, Node, Diagnostic


@dataclass(frozen=True)
class Host:
    name: str


HOST_FUNCTIONS = {'acquire', 'acquireAsync', 'close', 'closeAsync', 'yield'}


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
            case 'field', (base, name):
                return self.ir(node, 'field', name.items[0], self.expression(base, environment, handlers))
            case 'unary', (operator, operand):
                return self.ir(node, 'unary', operator, self.expression(operand, environment, handlers))
            case 'binary', (operator, left, right):
                return self.ir(node, 'binary', operator, self.expression(left, environment, handlers),
                               self.expression(right, environment, handlers))
            case 'path', _:
                symbol = self.lookup(node, environment)
                if isinstance(symbol, Host):
                    self.limit('fixture primitives must be called directly; wrap one in a source closure to pass it', node)
                return self.ir(node, 'var', symbol)
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


def lower_feature(expr, names, lower, checker):
    match expr:
        case ('pack', t, initial):
            methods = checker.packages[id(expr)]
            if methods is None:
                return lower(initial, names)
            return E('pack', t, tuple(methods.items()), lower(initial, names))
        case ('definitions', _, _, _):
            from eldude.core.declarations import lower_declarations
            return lower_declarations(expr, names, lower)
        case ('method_call', method, receiver, arguments, mode):
            if id(expr) in checker.dynamic_calls:
                access, _, identity = checker.dynamic_calls[id(expr)]
                first = E('access', access, receiver[1]) if access else lower(receiver, names)
                return E('dynamic_call', identity, first, tuple(lower(a, names) for a in arguments))
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
            retained = E('access', 'view', subject[1]) if id(expr) in checker.borrowed_matches else lower(subject, names)
            return E('match', retained, tuple((p, lower(b, names)) for p, b in arms))
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
            return E('for_each', pattern, lower(iterable, names), lower(body, names), checker.iteration_steps[id(expr)])
        case ('taskgroup', key, body):
            return E('taskgroup', key, lower(body, names))
        case ('spawn' | 'await' as kind, operand):
            return E(kind, lower(operand, names))
    return None
