"""Located AST for the executable slice of Eldude's normative source grammar.

Full grammar recognition precedes subset parsing, so a subset boundary is never
reported as invalid Eldude syntax. No declaration lookup participates in parsing.
"""
from dataclasses import dataclass
from functools import cache

from check_grammar import GRAMMAR, Grammar, LexError, Token


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
        if self.token.kind != 'IDENT':
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

    def parameters(self, anonymous=False):
        self.take('(')
        def parameter():
            start = self.token.start
            name = self.name()
            annotation = self.type() if self.eat(':') else None
            if annotation is None and not anonymous:
                self.limit('untyped named parameter')
            return self.node('parameter', start, name, annotation)
        return self.separated(')', parameter)

    def type(self):
        start = self.token.start
        if self.eat('fn'):
            self.take('(')
            parameters = self.separated(')', self.type)
            return self.node('fn_type', start, parameters, self.contract())
        if self.eat('('):
            if self.eat(')'):
                return self.node('type', start, 'Unit')
            result = self.type()
            self.take(')')
            return result
        path = self.path()
        if self.token.value == '<':
            self.limit('applied types')
        return self.node('type', start, path.items[0])

    def contract(self):
        start = self.take('->').start
        effects = []
        if self.eat('{'):
            def effect():
                if self.token.value in ('suspend', 'diverge'):
                    token = self.take()
                    return self.node('path', token.start, token.value)
                return self.path()
            effects = self.separated('}', effect)
        result = self.type()
        if self.eat('captures'):
            self.take('{')
            if not self.eat('}'):
                self.limit('nonempty capture annotations')
        return self.node('contract', start, result, tuple(effects))

    def module(self):
        start = self.take('module').start
        path = self.path()
        self.take(';')
        declarations = []
        while self.token.kind != 'EOF':
            begin = self.token.start
            public = self.eat('pub')
            if self.eat('import'):
                imported = self.path()
                self.take('::')
                self.take('{')
                def alias():
                    name = self.name()
                    return (name, self.name() if self.eat('as') else name)
                names = self.separated('}', alias)
                self.take(';')
                declarations.append(self.node('import', begin, public, imported, names))
            elif self.eat('fn'):
                name = self.name()
                if self.token.value == '<':
                    self.limit('generic functions')
                params, contract = self.parameters(), self.contract()
                body = self.block()
                declarations.append(self.node('function', begin, public, name, params, contract, body))
            elif self.eat('effect'):
                name = self.name()
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
                declarations.append(self.node('effect', begin, public, name, tuple(operations)))
            else:
                self.limit('this declaration')
        return self.node('module', start, path, tuple(declarations))

    def block(self):
        start = self.take('{').start
        statements = []
        while self.token.value != '}':
            begin = self.token.start
            if self.eat('let'):
                name = self.name()
                annotation = self.type() if self.eat(':') else None
                self.take('=')
                initializer = self.expression()
                self.take(';')
                statements.append(self.node('let', begin, name, annotation, initializer))
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
        return self.separated(')', self.expression)

    def expression(self):
        start = self.token.start
        expression = self.primary()
        while self.token.value == '(':
            expression = self.node('call', start, expression, self.arguments())
        if self.token.value in ('+', '-', '*', '/', '%', '==', '!=', '<', '<=', '>', '>=', '??', '.', '.?', '[', '?', '::'):
            self.limit('operators, projections, or generic application')
        return expression

    def primary(self):
        start, spelling = self.token.start, self.token.value
        if spelling in ('+', '-'):
            sign = self.take()
            # Only a signed literal (possibly parenthesized) is in this slice;
            # general unary computation still needs operator elaboration.
            if self.token.value in ('+', '-'):
                self.limit('nested numeric operators')
            operand = self.primary()
            if (operand.kind != 'int' or self.token.value == '('
                    or self.text[operand.span.start] in ('+', '-')):
                raise Diagnostic('unsupported', 'Implementation limit: numeric prefix requires a literal in this slice',
                                 self.span(sign.start, sign.end))
            return self.node('int', start, operand.items[0] if spelling == '+' else -operand.items[0])
        if self.token.kind == 'INT_LITERAL':
            self.take()
            digits = spelling.removesuffix('int').removesuffix('i64').replace('_', '')
            try:
                number = int(digits, 0 if digits.startswith(('0x', '0o', '0b')) else 10)
            except ValueError:
                raise Diagnostic('unsupported', 'Implementation limit: only Int integer literals execute', self.span(start, self.tokens[self.index - 1].end))
            return self.node('int', start, number)
        if spelling == '{':
            return self.block()
        if self.eat('('):
            if self.eat(')'):
                return self.node('unit', start)
            expression = self.expression()
            self.take(')')
            return expression
        if self.eat('fn'):
            parameters = self.parameters(anonymous=True)
            contract = self.contract() if self.token.value == '->' else None
            body = self.expression() if self.eat('=>') else self.block()
            return self.node('lambda', start, parameters, contract, body)
        if self.eat('!'):
            path = self.path()
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
            family = self.path()
            self.take('{')
            clauses = []
            while not self.eat('}'):
                begin = self.token.start
                if self.eat('forward'):
                    operation = self.node('name', self.take('..').start, '..') if self.token.value == '..' else self.name()
                    self.take(';')
                    clauses.append(self.node('forward', begin, operation))
                elif self.eat('return'):
                    result = self.name()
                    self.take('=>')
                    clauses.append(self.node('returning', begin, result, self.expression()))
                    self.eat(';')
                else:
                    operation = self.name()
                    self.take('(')
                    parameters = self.separated(')', self.name)
                    self.take('=>')
                    clauses.append(self.node('clause', begin, operation, parameters, self.expression()))
                    self.eat(';')
            return self.node('handle', start, family, name, body, tuple(clauses))
        if self.token.kind == 'IDENT':
            return self.path()
        self.limit()


def parse_source(text, filename='<source>'):
    return Parser(text, filename).module()
