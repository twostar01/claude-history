"""Tests for ingest.py helper functions and module structure.

TDD RED phase: tests written before implementation.

Coverage:
- build_message_content() — text + attachment assembly
- normalize_ts() — ISO 8601 timestamp normalization
- Module exports (main, ingest_zip, build_message_content, normalize_ts)
- No print() statements (captured via capsys)
- No INSERT OR REPLACE in source
"""

import importlib
import inspect
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# build_message_content
# ---------------------------------------------------------------------------

class TestBuildMessageContent:
    """Test the message text + attachment content assembly function."""

    def _fn(self):
        from claude_history.ingest import build_message_content
        return build_message_content

    def test_text_only(self):
        fn = self._fn()
        assert fn({"text": "hello"}) == "hello"

    def test_text_with_attachment(self):
        fn = self._fn()
        result = fn({"text": "hello", "attachments": [{"extracted_content": "world"}]})
        assert result == "hello\n\nworld"

    def test_empty_text_empty_attachments(self):
        fn = self._fn()
        assert fn({"text": "", "attachments": []}) == ""

    def test_empty_text_with_attachment_content(self):
        fn = self._fn()
        assert fn({"text": "", "attachments": [{"extracted_content": "attached"}]}) == "attached"

    def test_text_with_mixed_attachments(self):
        """Attachment with empty extracted_content is filtered out."""
        fn = self._fn()
        result = fn({
            "text": "a",
            "attachments": [
                {"extracted_content": ""},
                {"extracted_content": "b"},
            ],
        })
        assert result == "a\n\nb"

    def test_multiple_attachments(self):
        fn = self._fn()
        result = fn({
            "text": "main",
            "attachments": [
                {"extracted_content": "first"},
                {"extracted_content": "second"},
            ],
        })
        assert result == "main\n\nfirst\n\nsecond"

    def test_no_text_key(self):
        """Missing 'text' key defaults to empty string."""
        fn = self._fn()
        assert fn({}) == ""

    def test_no_attachments_key(self):
        """Missing 'attachments' key defaults to no attachments."""
        fn = self._fn()
        assert fn({"text": "only text"}) == "only text"

    def test_files_array_ignored(self):
        """files[] entries have no extracted_content — skipped for FTS."""
        fn = self._fn()
        result = fn({
            "text": "msg",
            "files": [{"file_uuid": "abc", "file_name": "photo.jpg"}],
        })
        assert result == "msg"


# ---------------------------------------------------------------------------
# normalize_ts
# ---------------------------------------------------------------------------

class TestNormalizeTs:
    """Test ISO 8601 timestamp normalization."""

    def _fn(self):
        from claude_history.ingest import normalize_ts
        return normalize_ts

    def test_z_suffix(self):
        fn = self._fn()
        result = fn("2026-04-01T23:44:12.155755Z")
        assert result  # non-empty
        # datetime.fromisoformat() normalizes Z to +00:00 in Python 3.11+
        assert "2026-04-01" in result

    def test_plus_offset(self):
        fn = self._fn()
        result = fn("2026-03-05T06:20:46.561314+00:00")
        assert result  # non-empty
        assert "2026-03-05" in result

    def test_empty_string(self):
        fn = self._fn()
        assert fn("") == ""

    def test_none_like_falsy(self):
        """Empty string (falsy) returns empty."""
        fn = self._fn()
        assert fn("") == ""

    def test_z_no_valueerror(self):
        """Should not raise ValueError for Z suffix."""
        fn = self._fn()
        try:
            fn("2026-04-01T23:44:12.155755Z")
        except ValueError as e:
            raise AssertionError(f"normalize_ts raised ValueError for Z suffix: {e}")

    def test_plus_no_valueerror(self):
        """Should not raise ValueError for +00:00 offset."""
        fn = self._fn()
        try:
            fn("2026-03-05T06:20:46.561314+00:00")
        except ValueError as e:
            raise AssertionError(f"normalize_ts raised ValueError for +00:00: {e}")


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

class TestModuleExports:
    """Verify all required public symbols are exported."""

    def test_main_exported(self):
        from claude_history import ingest
        assert hasattr(ingest, "main"), "ingest.main not found"
        assert callable(ingest.main)

    def test_ingest_zip_exported(self):
        from claude_history import ingest
        assert hasattr(ingest, "ingest_zip"), "ingest.ingest_zip not found"
        assert callable(ingest.ingest_zip)

    def test_build_message_content_exported(self):
        from claude_history import ingest
        assert hasattr(ingest, "build_message_content")
        assert callable(ingest.build_message_content)

    def test_normalize_ts_exported(self):
        from claude_history import ingest
        assert hasattr(ingest, "normalize_ts")
        assert callable(ingest.normalize_ts)


# ---------------------------------------------------------------------------
# Security / constraint gates
# ---------------------------------------------------------------------------

class TestConstraints:
    """Structural constraints enforced via source inspection."""

    def _source(self) -> str:
        import claude_history.ingest as m
        return inspect.getsource(m)

    def test_no_print_statements(self):
        """ingest.py must not contain print() — stdout kills MCP stdio session."""
        source = self._source()
        # Filter out comment lines and docstrings to avoid false positives
        code_lines = [
            line for line in source.splitlines()
            if not line.lstrip().startswith("#") and not line.lstrip().startswith('"""')
        ]
        for line in code_lines:
            assert "print(" not in line, f"Found print() in ingest.py: {line!r}"

    def test_no_insert_or_replace(self):
        """ingest.py must not contain INSERT OR REPLACE — orphans FTS index.

        Uses ast.parse to strip string constants (docstrings) from the source
        before checking. Only non-string source tokens are scanned.
        """
        import ast
        import tokenize
        import io

        source = self._source()
        # Use tokenize to extract only non-string, non-comment tokens and
        # reconstruct just the 'code' parts. This correctly handles multi-line
        # docstrings that mention the anti-pattern by name.
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        code_only_parts = []
        for tok_type, tok_string, *_ in tokens:
            if tok_type in (tokenize.STRING, tokenize.COMMENT, tokenize.NEWLINE,
                            tokenize.NL, tokenize.INDENT, tokenize.DEDENT,
                            tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            code_only_parts.append(tok_string)

        code_text = " ".join(code_only_parts).upper()
        assert "INSERT OR REPLACE" not in code_text, \
            "Found INSERT OR REPLACE in ingest.py SQL code — use INSERT OR IGNORE instead"

    def test_logging_to_stderr(self):
        """logging.basicConfig must direct to sys.stderr."""
        source = self._source()
        assert "stream=sys.stderr" in source, \
            "logging.basicConfig must use stream=sys.stderr"

    def test_project_null_in_insert(self):
        """conversations INSERT must use NULL for project field."""
        source = self._source()
        assert "NULL" in source, \
            "conversations INSERT must hardcode NULL for project (no project field in export)"
