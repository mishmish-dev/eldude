"""Located source records and binding identities shared with IR artifacts."""
from dataclasses import dataclass


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
class SourceProgram:
    ast: Node
    expression: tuple
    program: object
    functions: dict
    handled_rows: dict

    @property
    def inferred(self):
        return self.program.inferred
