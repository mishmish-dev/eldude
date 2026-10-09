"""Assertions shared by source API and handler acceptance tests."""
from eldude.handlers import run
from eldude.source_syntax import Diagnostic


class SourceAssertions:
    def compile(self, source):
        from eldude.source_pipeline import compile_source
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
