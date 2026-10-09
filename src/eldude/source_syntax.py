"""Located AST for Eldude source programs and standard-library declarations.

Full grammar recognition precedes subset parsing, so a subset boundary is never
reported as invalid Eldude syntax. No declaration lookup participates in parsing.
"""
from dataclasses import dataclass
from functools import cache

from eldude.check_grammar import GRAMMAR, Grammar, LexError, Token


@dataclass(frozen=True)
class Span:
    filename: str
    start: int
    end: int
    line: int
    column: int


class Diagnostic(ValueError):
    def __init__(self, code, message, span, related=()):
        super().__init__(message)
        self.code, self.message, self.span = code, message, span
        self.related = tuple(related)

    def __str__(self):
        s = self.span
        lines = [f'{s.filename}:{s.line}:{s.column}: {self.code}: {self.message}']
        for message, s in self.related:
            lines.append(f'{s.filename}:{s.line}:{s.column}: note: {message}')
        return '\n'.join(lines)


@dataclass(frozen=True)
class Node:
    kind: str
    span: Span
    items: tuple = ()


@cache
def grammar():
    return Grammar(GRAMMAR.read_text(encoding='utf-8'))


class Parser:
    def __init__(self, text, filename):
        self.text, self.filename, self.index = text, filename, 0
        try:
            self.tokens = grammar().lex_spanned(text)
        except LexError as error:
            raise Diagnostic('syntax', str(error), self.span(error.offset, error.offset + 1)) from error
        failure = grammar().syntax_failure([(t.kind, t.value) for t in self.tokens])
        self.tokens.append(Token('EOF', '<end of file>', len(text), len(text)))
        if failure is not None:
            token = self.tokens[failure]
            raise Diagnostic('syntax', f'Unexpected {token.value!r}', self.span(token.start, token.end))

    def span(self, start, end):
        return Span(self.filename, start, end, self.text.count('\n', 0, start) + 1,
                    start - self.text.rfind('\n', 0, start))

    @property
    def token(self):
        return self.tokens[self.index]

    def node(self, kind, start, *items):
        return Node(kind, self.span(start, self.tokens[self.index - 1].end), tuple(items))

    def limit(self, feature=None):
        token = self.token
        raise Diagnostic('unsupported', f'Implementation limit: {feature or token.value} is outside the executable source subset',
                         self.span(token.start, token.end))

    def take(self, spelling=None):
        if spelling is not None and self.token.value != spelling:
            self.limit(f'construct beginning with {self.token.value!r}')
        token = self.token
        self.index += 1
        return token

    def eat(self, spelling):
        if self.token.value == spelling:
            self.take()
            return True
        return False

    def name(self):
        if self.token.kind != 'IDENT' and self.token.value != 'self':
            self.limit('this binding pattern or receiver')
        token = self.take()
        return self.node('name', token.start, token.value)

    def path(self):
        start, parts = self.token.start, []
        while True:
            if self.token.kind != 'IDENT' and self.token.value != 'self':
                self.limit('qualified name')
            parts.append(self.take().value)
            if self.token.value != '::' or self.tokens[self.index + 1].value in ('{', '<'):
                break
            self.take('::')
        return self.node('path', start, '::'.join(parts))

    def separated(self, end, parse):
        items = []
        if not self.eat(end):
            while True:
                items.append(parse())
                if self.eat(end):
                    break
                self.take(',')
                if self.eat(end):
                    break
        return tuple(items)

    def generic_parameter(self):
        start = self.token.start
        if self.token.value in ('@', '!', '..', '#'):
            prefix = self.take().value
            return self.node('generic_parameter', start, prefix, self.name())
        name = self.name()
        if self.eat('<'):
            return self.node('constructor_parameter', start, name, self.separated('>', self.name))
        return name

    def generic_name(self):
        name = self.name()
        if self.eat('<'):
            return self.node('generic_name', name.span.start, name.items[0],
                             self.separated('>', self.generic_parameter))
        return name

    def where(self):
        if not self.eat('where'):
            return ()
        constraints = []
        while True:
            start = self.token.start
            subject = self.type_argument() if self.token.value == '..' else self.type()
            if self.eat(':'):
                bounds = [self.type()]
                while self.eat('+'):
                    bounds.append(self.type())
                constraints.append(self.node('bound', start, subject, tuple(bounds)))
            else:
                self.take('=')
                constraints.append(self.node('type_equality', start, subject, self.type()))
            if not self.eat(',') or self.token.value in ('{', ';', '='):
                return tuple(constraints)

    def constrained_name(self, name):
        constraints = self.where()
        if constraints:
            params = name.items[1] if name.kind == 'generic_name' else ()
            return self.node('generic_name', name.span.start, name.items[0], params, constraints)
        return name

    def parameters(self, anonymous=False):
        self.take('(')
        def parameter():
            start = self.token.start
            mode = self.take().value if self.token.value in ('view', 'mut') else None
            name = self.name()
            annotation = self.type() if self.eat(':') else None
            if annotation is None and not anonymous and name.items[0] != 'self':
                self.limit('untyped named parameter')
            items = (name, annotation) + ((mode,) if mode else ())
            return self.node('parameter', start, *items)
        return self.separated(')', parameter)

    def pattern(self):
        start = self.token.start
        patterns = [self.pattern_atom()]
        while self.eat('|'):
            patterns.append(self.pattern_atom())
        return patterns[0] if len(patterns) == 1 else self.node('or_pattern', start, tuple(patterns))

    def pattern_atom(self):
        start = self.token.start
        if self.eat('('):
            if self.eat(')'):
                return self.node('tuple_pattern', start, ())
            first = self.pattern()
            if self.eat(')'):
                return first
            self.take(',')
            return self.node('tuple_pattern', start, (first,) + self.separated(')', self.pattern))
        if self.token.kind.endswith('_LITERAL') or self.token.value in ('true', 'false', '+', '-'):
            return self.node('literal_pattern', start, self.prefix())
        path = self.path()
        if self.eat('('):
            return self.node('variant_pattern', start, path, self.separated(')', self.pattern))
        if self.eat('{'):
            def field():
                name = self.name()
                return name, self.pattern() if self.eat(':') else name
            return self.node('record_pattern', start, path, self.separated('}', field))
        if '::' in path.items[0]:
            return self.node('variant_pattern', start, path, ())
        return Node('name', path.span, path.items)

    def type_argument(self, minimum=0):
        start = self.token.start
        if self.token.value in ('@', '..'):
            prefix = self.take().value
            return self.node('region_type' if prefix == '@' else 'capture_variable', start, self.name())
        if self.token.value == '{':
            if self.tokens[self.index + 1].value in ('@', '..'):
                return self.capture_set()
            return self.effect_row()
        if self.token.kind == 'INT_LITERAL':
            value = self.primary()
        else:
            value = self.type()
        if self.eat('='):
            return self.node('type_binding', start, value, self.type())
        precedence = {'+': 1, '*': 2}
        while self.token.value in precedence and precedence[self.token.value] >= minimum:
            operator = self.take().value
            value = self.node('nat_binary', start, operator, value,
                              self.type_argument(precedence[operator] + 1))
        return value

    def applied_type(self):
        start = self.token.start
        path = self.path()
        result = self.node('type', start, path.items[0])
        if self.eat('<'):
            result = self.node('applied_type', start, path.items[0], self.separated('>', self.type_argument))
        while self.eat('::'):
            name = self.name()
            args = self.separated('>', self.type_argument) if self.eat('<') else ()
            result = self.node('projection_type', start, result, name, args)
        return result

    def type(self):
        start = self.token.start
        if self.eat('fn'):
            self.take('(')
            def mode_type():
                begin = self.token.start
                if self.token.value in ('view', 'mut'):
                    return self.node('access_type', begin, self.take().value, self.type())
                return self.type()
            parameters = self.separated(')', mode_type)
            return self.node('fn_type', start, parameters, self.contract())
        if self.eat('forall'):
            self.take('<')
            params = self.separated('>', self.generic_parameter)
            self.take('.')
            return self.node('forall_type', start, params, self.type())
        if self.eat('*'):
            return self.node('pointer_type', start, self.take().value, self.type())
        if self.eat('any'):
            bounds = [self.applied_type()]
            while self.eat('+'):
                bounds.append(self.applied_type())
            return self.node('any_type', start, tuple(bounds))
        if self.eat('<'):
            subject = self.type()
            self.take('as')
            trait = self.applied_type()
            self.take('>')
            self.take('::')
            name = self.name()
            args = self.separated('>', self.type_argument) if self.eat('<') else ()
            return self.node('qualified_type', start, subject, trait, name, args)
        if self.eat('('):
            if self.eat(')'):
                return self.node('type', start, 'Unit')
            result = self.type()
            if self.eat(','):
                return self.node('tuple_type', start, (result,) + self.separated(')', self.type))
            self.take(')')
            return result
        return self.applied_type()

    def effect_row(self):
        start = self.take('{').start
        entries, tail = [], None
        while self.token.value not in ('}', '|'):
            if self.token.value in ('suspend', 'diverge'):
                token = self.take()
                entries.append(self.node('path', token.start, token.value))
            else:
                effect = self.applied_type()
                entries.append(Node('path', effect.span, effect.items) if effect.kind == 'type' else effect)
            if not self.eat(','):
                break
        if self.eat('|'):
            tail = self.name()
        self.take('}')
        return self.node('effect_row', start, tuple(entries), tail)

    def capture_set(self):
        start = self.take('{').start
        def capture():
            if self.token.value in ('@', '..'):
                return self.type_argument()
            return self.path()
        return self.node('capture_set', start, self.separated('}', capture))

    def contract(self):
        start = self.take('->').start
        effects = []
        if self.token.value == '{':
            row = self.effect_row()
            effects = list(row.items[0])
            if row.items[1] is not None:
                effects.append(Node('effect_tail', row.items[1].span, row.items[1].items))
        result = self.type()
        captures = self.capture_set().items[0] if self.eat('captures') else ()
        return self.node('contract', start, result, tuple(effects), *((captures,) if captures else ()))

    def fields(self):
        def field():
            public = self.eat('pub')
            name = self.name()
            self.take(':')
            annotation = self.type()
            return (name, annotation, True) if public else (name, annotation)
        return self.separated('}', field)

    def let(self, begin):
        name = self.pattern()
        annotation = self.type() if self.eat(':') else None
        self.take('=')
        initializer = self.expression()
        self.take(';')
        return self.node('let', begin, name, annotation, initializer)

    def declaration(self, member=False):
        begin = self.token.start
        public = self.eat('pub')
        usage = self.take().value if self.token.value in ('linear', 'affine') else None
        intrinsic = self.eat('intrinsic')
        unsafe = self.eat('unsafe')
        if self.eat('import'):
            imported = self.path()
            self.take('::')
            self.take('{')
            def alias():
                name = self.name()
                return (name, self.name() if self.eat('as') else name)
            names = self.separated('}', alias)
            self.take(';')
            return self.node('import', begin, public, imported, names)
        if self.eat('fn'):
            name = self.generic_name()
            params, contract = self.parameters(), self.contract()
            name = self.constrained_name(name)
            body = None if self.eat(';') else self.block()
            return self.node('unsafe_function' if unsafe else 'function', begin, public, name, params, contract, body)
        if self.eat('let'):
            result = self.let(begin)
            return Node('public_let', result.span, result.items) if public else result
        if self.token.value in ('struct', 'enum'):
            kind = self.take().value
            name = self.generic_name()
            if kind == 'enum' and self.token.value == 'where' and self.tokens[self.index + 1].value == '{':
                self.take('where')
                self.take('{')
                def constructor():
                    start = self.token.start
                    pub = self.eat('pub')
                    name = self.name()
                    self.take(':')
                    return self.node('gadt_variant', start, pub, name, self.type())
                members = self.separated('}', constructor)
            else:
                name = self.constrained_name(name)
                if kind == 'struct' and self.eat(';'):
                    members = None
                else:
                    self.take('{')
                    def variant():
                        start = self.token.start
                        pub, name = self.eat('pub'), self.name()
                        if self.eat('('):
                            members, form = self.separated(')', self.type), 'tuple'
                        elif self.eat('{'):
                            members, form = self.fields(), 'record'
                        else:
                            members, form = (), 'unit'
                        return self.node('variant', start, pub, name, members, form)
                    members = self.fields() if kind == 'struct' else self.separated('}', variant)
            return self.node(kind, begin, public, name, members, *((usage,) if usage else ()))
        if self.eat('trait'):
            name = self.constrained_name(self.generic_name())
            self.take('{')
            members = []
            while not self.eat('}'):
                members.append(self.declaration(member=True))
            return self.node('trait', begin, public, name, tuple(members), *((True,) if intrinsic else ()))
        if self.eat('impl'):
            generics = self.separated('>', self.generic_parameter) if self.eat('<') else ()
            first = self.type()
            trait, target = (first, self.type()) if self.eat('for') else (None, first)
            constraints = self.where()
            self.take('{')
            members = []
            while not self.eat('}'):
                members.append(self.declaration(member=True))
            return self.node('impl', begin, generics, trait, target, constraints, tuple(members))
        if self.eat('type'):
            name = self.constrained_name(self.generic_name())
            value = self.type() if self.eat('=') else None
            self.take(';')
            return (self.node('associated_type', begin, name, value) if member
                    else self.node('type_alias', begin, public, name, value))
        if self.eat('effect'):
            name = self.generic_name()
            self.take('{')
            operations = []
            while not self.eat('}'):
                op_start = self.token.start
                mode = self.take().value
                operation = self.name()
                parameters = self.parameters()
                self.take('->')
                result = self.type()
                self.take(';')
                operations.append(self.node('operation', op_start, mode, operation, parameters, result))
            return self.node('effect', begin, public, name, tuple(operations))
        self.limit('this declaration')

    def module(self):
        start = self.take('module').start
        path = self.path()
        self.take(';')
        declarations = []
        while self.token.kind != 'EOF':
            declarations.append(self.declaration())
        return self.node('module', start, path, tuple(declarations))

    def block(self):
        start = self.take('{').start
        statements = []
        while self.token.value != '}':
            begin = self.token.start
            if self.eat('let'):
                statements.append(self.let(begin))
            elif self.eat('assert'):
                statements.append(self.node('assert', begin, self.expression()))
                self.take(';')
            else:
                expression = self.expression()
                if not self.eat(';'):
                    self.take('}')
                    return self.node('block', start, tuple(statements), expression)
                statements.append(self.node('discard', begin, expression))
        closing = self.take('}')
        return self.node('block', start, tuple(statements), Node('unit', self.span(closing.start, closing.end)))

    def arguments(self):
        self.take('(')
        def argument():
            if self.token.value in ('view', 'mut'):
                # A bare access binding is an argument, while access methods are expressions.
                if self.tokens[self.index + 2].value != '.':
                    start = self.token.start
                    return self.node('access', start, self.take().value, self.path())
            return self.expression()
        return self.separated(')', argument)

    def expression(self, minimum=0, records=True):
        start = self.token.start
        expression = self.prefix(records)
        precedence = {'??': 0, '==': 1, '!=': 1, '<': 2, '<=': 2, '>': 2, '>=': 2,
                      '+': 3, '-': 3, '*': 4, '/': 4, '%': 4}
        while self.token.value in precedence and precedence[self.token.value] >= minimum:
            operator = self.take().value
            right = self.expression(precedence[operator] + (operator != '??'), records)
            expression = self.node('binary', start, operator, expression, right)
        return expression

    def prefix(self, records=True):
        start, spelling = self.token.start, self.token.value
        if spelling in ('+', '-', 'spawn', 'await'):
            self.take()
            operand = self.prefix(records)
            if spelling in ('spawn', 'await'):
                return self.node(spelling, start, operand)
            if operand.kind == 'int' and self.text[operand.span.start] not in ('+', '-'):
                return self.node('int', start, operand.items[0] if spelling == '+' else -operand.items[0])
            return self.node('unary', start, spelling, operand)
        expression = self.primary(records)
        while self.token.value in ('(', '.', '.?', '::', '?', '['):
            if self.eat('?'):
                expression = self.node('propagate', start, expression)
            elif self.eat('['):
                index = self.expression()
                self.take(']')
                expression = self.node('index', start, expression, index)
            elif self.eat('.?'):
                expression = self.node('optional_field', start, expression, self.name())
            elif self.eat('.'):
                expression = self.node('field', start, expression, self.name())
            elif self.eat('::'):
                self.take('<')
                expression = self.node('specialize', start, expression, self.separated('>', self.type_argument))
            else:
                expression = self.node('call', start, expression, self.arguments())
        return expression

    def primary(self, records=True):
        start, spelling = self.token.start, self.token.value
        if spelling in ('true', 'false'):
            self.take()
            return self.node('bool', start, spelling == 'true')
        if self.eat('if'):
            condition = self.expression(records=False)
            then = self.block()
            otherwise = self.node('unit', start)
            if self.eat('else'):
                otherwise = self.primary() if self.token.value == 'if' else self.block()
            return self.node('if', start, condition, then, otherwise)
        if self.token.kind == 'INT_LITERAL':
            self.take()
            digits = spelling.removesuffix('nat').removesuffix('int').removesuffix('i64').replace('_', '')
            try:
                number = int(digits, 0 if digits.startswith(('0x', '0o', '0b')) else 10)
            except ValueError:
                raise Diagnostic('unsupported', 'Implementation limit: only Int integer literals execute', self.span(start, self.tokens[self.index - 1].end))
            return self.node('nat' if spelling.endswith('nat') else 'int', start, number)
        if self.eat('match'):
            subject = self.expression(records=False)
            self.take('{')
            arms = []
            while not self.eat('}'):
                begin = self.take('case').start
                pattern = self.pattern()
                guard = self.expression(records=False) if self.eat('if') else None
                self.take('=>')
                body = self.expression()
                self.take(';')
                arms.append(self.node('arm', begin, pattern, guard, body))
            return self.node('match', start, subject, tuple(arms))
        if self.eat('while'):
            condition = self.expression(records=False)
            return self.node('while', start, condition, self.block())
        if self.eat('for'):
            pattern = self.pattern()
            self.take('in')
            iterable = self.expression(records=False)
            return self.node('for', start, pattern, iterable, self.block())
        if self.eat('region'):
            name = self.name()
            return self.node('region', start, name, self.block())
        if spelling in ('try', 'taskgroup', 'unsafe'):
            self.take()
            return self.node(spelling, start, self.block())
        if self.eat('return'):
            operand = self.node('unit', start) if self.token.value in (';', '}', ')', ',') else self.expression(records=records)
            return self.node('return', start, operand)
        if spelling in ('break', 'continue'):
            self.take()
            return self.node(spelling, start)
        if self.eat('['):
            return self.node('list', start, self.separated(']', self.expression))
        if spelling in ('view', 'mut'):
            mode = self.take().value
            receiver = self.name()
            self.take('.')
            method = self.name()
            args = ()
            if self.eat('::'):
                self.take('<')
                args = self.separated('>', self.type_argument)
            return self.node('access_method', start, mode, Node('path', receiver.span, receiver.items),
                             method, args, self.arguments())
        if spelling == '{':
            return self.block()
        if self.eat('('):
            if self.eat(')'):
                return self.node('unit', start)
            expression = self.expression()
            if self.eat(','):
                return self.node('tuple', start, (expression,) + self.separated(')', self.expression))
            self.take(')')
            return expression
        if self.eat('fn'):
            parameters = self.parameters(anonymous=True)
            contract = self.contract() if self.token.value == '->' else None
            body = self.expression() if self.eat('=>') else self.block()
            return self.node('lambda', start, parameters, contract, body)
        if self.eat('!'):
            path = self.path()
            if self.eat('::'):
                self.take('<')
                family = self.node('applied_type', path.span.start, path.items[0], self.separated('>', self.type_argument))
                self.take('::')
                path = self.node('operation_path', path.span.start, family, self.name())
            return self.node('perform', start, path, self.arguments())
        if self.eat('resume'):
            return self.node('resume', start, self.arguments())
        if self.eat('using'):
            self.take('(')
            def acquisition():
                begin = self.token.start
                name = self.name()
                self.take('=')
                return self.node('acquisition', begin, name, self.expression())
            acquisitions = self.separated(')', acquisition)
            return self.node('using', start, acquisitions, self.block())
        if self.eat('handle'):
            body = self.block()
            self.take('with')
            name = None
            if self.token.value != 'handler':
                name = self.name()
                self.take('=')
            self.take('handler')
            family = self.applied_type()
            if family.kind == 'type':
                family = Node('path', family.span, family.items)
            self.take('{')
            clauses = []
            while not self.eat('}'):
                begin = self.token.start
                if self.eat('forward'):
                    operation = self.node('name', self.take('..').start, '..') if self.token.value == '..' else self.name()
                    self.take(';')
                    clauses.append(self.node('forward', begin, operation))
                elif self.eat('return'):
                    result = self.pattern()
                    self.take('=>')
                    clauses.append(self.node('returning', begin, result, self.expression()))
                    self.eat(';')
                else:
                    operation = self.name()
                    self.take('(')
                    parameters = self.separated(')', self.pattern)
                    self.take('=>')
                    clauses.append(self.node('clause', begin, operation, parameters, self.expression()))
                    self.eat(';')
            return self.node('handle', start, family, name, body, tuple(clauses))
        if self.token.kind == 'IDENT' or spelling == 'self':
            path = self.path()
            if records and self.eat('{'):
                def field():
                    name = self.name()
                    value = self.expression() if self.eat(':') else Node('path', name.span, name.items)
                    return name, value
                return self.node('record', start, path, self.separated('}', field))
            return path
        self.limit()


def parse_source(text, filename='<source>'):
    return Parser(text, filename).module()
