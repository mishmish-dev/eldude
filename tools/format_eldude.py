"""Semantic formatting for Eldude source files."""
import argparse
import os
from pathlib import Path
import stat
import sys
import tempfile

from check_grammar import LexError, SyntaxNode
from source_syntax import Diagnostic, Span, grammar


def diagnostic(text, filename, offset, message, code='syntax'):
    return Diagnostic(code, message, Span(filename, offset, offset + 1,
                      text.count('\n', 0, offset) + 1, offset - text.rfind('\n', 0, offset)))


def source_tree(text, filename):
    try:
        retained = grammar().lex_spanned(text, comments=True)
    except LexError as error:
        raise diagnostic(text, filename, error.offset, str(error)) from error
    tokens = [t for t in retained if not t.kind.endswith('_COMMENT')]
    tree, failure = grammar().parse_tokens([(t.kind, t.value) for t in tokens])
    if failure is not None:
        offset = tokens[failure].start if failure < len(tokens) else len(text)
        value = tokens[failure].value if failure < len(tokens) else '<end of file>'
        raise diagnostic(text, filename, offset, f'Unexpected {value!r}')
    return retained, tokens, tree


def nodes(tree):
    yield tree
    for child in tree.children:
        if isinstance(child, SyntaxNode):
            yield from nodes(child)


class Writer:
    def __init__(self):
        self.parts, self.indent, self.column, self.newlines = [], 0, 0, 0

    def emit(self, value, space=''):
        prefix = ' ' * (4 * self.indent) if not self.column else space
        self.parts.extend((prefix, value))
        self.column = (len(value.rsplit('\n', 1)[-1]) if '\n' in value
                       else self.column + len(prefix) + len(value))
        self.newlines = 0

    def line(self, count=1):
        if self.parts and count > self.newlines:
            self.parts.append('\n' * (count - self.newlines))
            self.newlines = count
            self.column = 0

    def finish(self):
        return ''.join(self.parts).rstrip('\n') + '\n'


def format_source(text, filename='<source>'):
    """Lay out the full source grammar, retaining all tokens and comments."""
    retained, tokens, tree = source_tree(text, filename)
    count = len(tokens)
    spaces, breaks = [' '] * (count + 1), [0] * (count + 1)
    indents, dedents = [0] * (count + 1), [0] * (count + 1)
    comments = [[] for _ in range(count + 1)]
    position = 0
    for token in retained:
        if token.kind.endswith('_COMMENT'):
            comments[position].append(token)
        else:
            position += 1
    angles, compact, blocks, groups = set(), set(), set(), set()
    values = [t.value for t in tokens]
    for i in range(1, count):
        if (values[i] in (')', ']', ',', ';', ':', '.', '.?', '::', '?')
                or values[i - 1] in ('(', '[', '.', '.?', '::', '@', '#', '..', '!')):
            spaces[i] = ''
        if values[i - 1] == values[i] == '?':
            spaces[i] = ' '  # Two propagation operators must not become coalescing.
    for node in nodes(tree):
        direct = [c for c in node.children if isinstance(c, int)]
        if node.name in ('generic_params', 'generic_param', 'type_args', 'qualified_projection'):
            for i in direct:
                if values[i] in ('<', '>'):
                    angles.add(i)
                    spaces[i] = '' if values[i] == '>' or node.name != 'qualified_projection' else spaces[i]
                    if values[i] == '<':
                        spaces[i + 1] = ''
        if node.name in ('unary_expr', 'condition_unary', 'signed_literal', 'raw_pointer_type'):
            if direct and values[direct[0]] in ('+', '-', '*'):
                spaces[direct[0] + 1] = ''
        if node.name == 'forall_type':
            spaces[next(i for i in direct if values[i] == '.') + 1] = ' '
        if node.name in ('parameters', 'arguments', 'function_type', 'lambda', 'handler_clause', 'resume_expr'):
            for i in direct:
                if values[i] == '(':
                    spaces[i] = ''
        if node.name in ('pattern_atom', 'variant'):
            for i in direct:
                if values[i] == '(':
                    spaces[i] = ''
        if node.name == 'postfix' and values[node.start] == '[':
            spaces[node.start] = ''
        if node.name in ('effect_row', 'capture_set', 'import_decl'):
            compact.update(i for i in direct if values[i] == '{')
        if node.name == 'effect_row' and node.start and values[node.start - 1] == '->':
            spaces[node.start] = ''
        if node.name in ('block', 'struct_decl', 'enum_decl', 'trait_decl', 'impl_decl',
                         'effect_decl', 'extern_block', 'match_expr', 'handle_expr', 'variant'):
            blocks.update(i for i in direct if values[i] == '{')
        if node.name in ('statement', 'field_decl', 'variant', 'gadt_constructor',
                         'trait_member', 'impl_member', 'effect_operation', 'match_arm', 'handler_clause'):
            breaks[node.start] = max(breaks[node.start], 1)
        if node.name == 'statement':
            breaks[node.end] = max(breaks[node.end], 1)
        if node.name == 'extern_block':
            for child in node.children:
                if isinstance(child, SyntaxNode) and child.name == 'function_decl':
                    start = child.start - int(values[child.start - 1] == 'pub')
                    breaks[start] = max(breaks[start], 1)
        if node.name in ('parameters', 'arguments', 'generic_params', 'type_args', 'function_type',
                         'lambda', 'tuple_expr', 'tuple_type', 'tuple_pattern', 'list_literal',
                         'struct_literal', 'capture_set', 'effect_row', 'import_decl', 'pattern_atom',
                         'using_expr', 'handler_clause', 'variant', 'generic_param'):
            groups.update(i for i in direct if values[i] in ('(', '[', '{', '<'))
    pairs, stack = {}, []
    for i, value in enumerate(values):
        if value in ('(', '[', '{') or (i in angles and value == '<'):
            stack.append(i)
        elif value in (')', ']', '}') or (i in angles and value == '>'):
            pairs[stack.pop()] = i
    for begin, end in pairs.items():
        if begin in compact:
            spaces[begin + 1] = ''
            spaces[end] = ''
        if end == begin + 1:
            spaces[end] = ''
        if begin in blocks and (end > begin + 1 or comments[end]):
            breaks[begin + 1] = breaks[end] = 1
            indents[begin + 1] += 1
            dedents[end] += 1
    previous_import = False
    for item in tree.children:
        if isinstance(item, SyntaxNode) and item.name == 'module_item':
            is_import = item.children[0].name == 'import_decl'
            breaks[item.start] = 1 if previous_import and is_import else 2
            previous_import = is_import

    writer = Writer()
    for i in range(count + 1):
        writer.indent += indents[i]
        pending = breaks[i]
        previous_end = tokens[i - 1].end if i else 0
        for comment in comments[i]:
            gap = text[previous_end:comment.start]
            if '\n' in gap or '\r' in gap or not writer.parts:
                writer.line(max(1, pending))
                pending = 0
            writer.emit(comment.value, ' ')
            if comment.kind == 'LINE_COMMENT':
                writer.line()
            previous_end = comment.end
        if comments[i]:
            gap = text[previous_end:tokens[i].start if i < count else len(text)]
            if '\n' in gap or '\r' in gap:
                writer.line()
        writer.indent -= dedents[i]
        writer.line(pending)
        if i == count:
            break
        if i in groups and i in pairs and i not in blocks and pairs[i] > i + 1:
            end = pairs[i]
            line_end = end + 1
            while line_end < count and not breaks[line_end]:
                line_end += 1
            column = writer.column or 4 * writer.indent
            size = len(values[i]) + (len(spaces[i]) if writer.column else 0)
            size += sum(len(values[j]) + len(spaces[j]) for j in range(i + 1, line_end))
            has_comments = any(comments[j] for j in range(i + 1, end + 1))
            if column + size > 100 or has_comments:
                breaks[i + 1] = breaks[end] = 1
                indents[i + 1] += 1
                dedents[end] += 1
                cursor = i + 1
                while cursor < end:
                    if values[cursor] == ',':
                        breaks[cursor + 1] = 1
                    cursor = pairs.get(cursor, cursor) + 1
        writer.emit(values[i], spaces[i])
    result = writer.finish()
    after = grammar().lex_spanned(result, comments=True)
    if [(t.kind, t.value) for t in after] != [(t.kind, t.value) for t in retained]:
        raise diagnostic(text, filename, 0, 'Formatting changed source tokens', 'format')
    return result


def write_file(path, original, formatted, mode):
    """Replace one validated file without truncating it on write failure."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f'.{path.name}.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(formatted)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), stat.S_IMODE(mode))
        if path.is_symlink() or path.read_bytes() != original:
            raise OSError(f'{path}: source changed while formatting')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', help='source files; omit or use - for stdin')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='report files needing formatting; exit 1 if any differ')
    modes.add_argument('--write', action='store_true', help='atomically replace changed files')
    args = parser.parse_args(argv)
    files = args.files or ['-']
    if (not args.check and not args.write and len(files) != 1) or ('-' in files and len(files) != 1):
        parser.error('stdout and stdin modes accept one input; use --check or --write for multiple files')
    if args.write and '-' in files:
        parser.error('--write requires explicit files')
    pending, seen = [], set()
    try:
        for name in files:
            path = Path(name) if name != '-' else None
            filename = str(path) if path else '<stdin>'
            if args.write and path.is_symlink():
                raise OSError(f'{path}: refusing to replace a symlink')
            identity = path.resolve() if path else None
            if identity in seen:
                continue
            seen.add(identity)
            original = path.read_bytes() if path else sys.stdin.buffer.read()
            mode = path.stat().st_mode if path else 0
            formatted = format_source(original.decode('utf-8'), filename).encode('utf-8')
            pending.append((path, original, formatted, mode))
        changed = False
        for path, original, formatted, mode in pending:
            if args.check or args.write:
                if formatted != original:
                    changed = True
                    if args.write:
                        write_file(path, original, formatted, mode)
                    print(path if path else '<stdin>')
            else:
                sys.stdout.buffer.write(formatted)
        return int(args.check and changed)
    except (Diagnostic, OSError, UnicodeError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
