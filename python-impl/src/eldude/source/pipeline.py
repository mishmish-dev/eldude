"""Public source checking, compilation, and execution API."""
from pathlib import Path

from eldude.core.handlers import Defect, run
from eldude.source.elaboration import SourceElaborator
from eldude.core.model import Diagnostic, SourceProgram, Symbol
from eldude.source.modules import load_modules
from eldude.source.syntax import parse_source


def compile_source(text, filename='<source>'):
    return SourceElaborator(parse_source(text, filename)).compile()


def compile_file(path):
    path = Path(path)
    return compile_source(path.read_text(encoding='utf-8', newline=''), str(path))


def check_source(text, filename='<source>', *, sources=None, import_allowed=None):
    """Check an ordinary module and its imports without an execution root."""
    ast = parse_source(text, filename)
    graph = load_modules(ast, sources=sources, import_allowed=import_allowed)
    return SourceElaborator(ast, graph).compile(entry=None)


def check_file(path, **kwargs):
    path = Path(path)
    return check_source(path.read_text(encoding='utf-8', newline=''), str(path), **kwargs)


def execute_file(path):
    program = compile_file(path)
    try:
        return run(program.program)
    except Defect as error:
        span = program.program.origins.get(id(error.expression), program.ast.span)
        raise Diagnostic('defect', str(error), span,
                         [(note, span) for note in getattr(error, '__notes__', ())]) from error
