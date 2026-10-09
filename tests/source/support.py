"""Helpers shared by source acceptance and formatter tests."""
import re
from eldude.core.handlers import run
from eldude.source.syntax import Diagnostic


class SourceAssertions:
    def compile(self, source):
        from eldude.source.pipeline import compile_source
        return compile_source(source, 'test.eld')

    def execute(self, source):
        return run(self.compile(source).program)

    def reject(self, source, code, message, at):
        with self.assertRaises(Diagnostic) as caught:
            self.compile(source)
        diagnostic = caught.exception
        self.assertEqual(diagnostic.code, code, str(diagnostic))
        self.assertRegex(diagnostic.message, message)
        self.assertEqual(source[diagnostic.span.start:diagnostic.span.end], at)
        return diagnostic


def executable_source(path):
    source = path.read_text(encoding='utf-8')
    if not re.search(r'\bpub\s+fn\s+main\b', source):
        if re.search(r'\bfn\s+main\b', source):
            source = re.sub(r'\bfn\s+main\b', 'pub fn main', source, count=1)
        else:
            source += '\npub fn main() -> Int { 42 }\n'
    return source
