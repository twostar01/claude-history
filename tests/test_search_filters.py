"""Tests for search.py filter extensions — Phase 5 SRCH-01 and SRCH-02.

TDD RED phase: Tests written before implementation. These verify:
  - _passes_date_filter helper (new function)
  - _fts_rows accepts role parameter (updated signature)
  - search_conversations accepts date_from, date_to, role_filter (updated signature)
"""
import sqlite3
import inspect

import pytest


def get_search_module():
    """Import search lazily so import errors fail the test, not collection."""
    from claude_history import search
    return search


class TestPassesDateFilter:
    """_passes_date_filter applies inclusive boundary comparison using [:10] prefix."""

    def test_same_day_both_bounds_returns_true(self):
        """Inclusive: same day as date_from and date_to must return True."""
        search = get_search_module()
        result = search._passes_date_filter(
            "2026-03-05T04:12:59+00:00", "2026-03-05", "2026-03-05"
        )
        assert result is True, "Same-day inclusive failed"

    def test_before_date_from_returns_false(self):
        """Conversation earlier than date_from must be excluded."""
        search = get_search_module()
        result = search._passes_date_filter(
            "2026-03-05T04:12:59+00:00", "2026-03-06", None
        )
        assert result is False, "date_from exclusion failed"

    def test_after_date_to_returns_false(self):
        """Conversation later than date_to must be excluded."""
        search = get_search_module()
        result = search._passes_date_filter(
            "2026-03-05T04:12:59+00:00", None, "2026-03-04"
        )
        assert result is False, "date_to exclusion failed"

    def test_empty_created_at_passes_through(self):
        """NULL/empty created_at: include defensively."""
        search = get_search_module()
        assert search._passes_date_filter("", None, None) is True
        assert search._passes_date_filter("", "2026-01-01", "2026-12-31") is True

    def test_no_filter_passes_through(self):
        """Both date_from and date_to None: always return True."""
        search = get_search_module()
        result = search._passes_date_filter(
            "2026-03-05T04:12:59.485807+00:00", None, None
        )
        assert result is True

    def test_full_iso_timestamp_same_day_date_to(self):
        """Critical: ISO timestamp with timezone must pass same-day date_to check.

        Direct string comparison '2026-03-05T...' > '2026-03-05' would fail.
        The [:10] prefix avoids this pitfall.
        """
        search = get_search_module()
        # This is the critical pitfall from the research: direct comparison returns False
        result = search._passes_date_filter(
            "2026-03-05T04:12:59.485807+00:00", None, "2026-03-05"
        )
        assert result is True, (
            "Same-day date_to check failed — likely missing [:10] prefix comparison"
        )

    def test_within_range_returns_true(self):
        """Date within both bounds passes."""
        search = get_search_module()
        result = search._passes_date_filter(
            "2026-03-10T12:00:00+00:00", "2026-03-01", "2026-03-31"
        )
        assert result is True

    def test_date_from_boundary_inclusive(self):
        """date_from itself must be included (>=, not >)."""
        search = get_search_module()
        result = search._passes_date_filter(
            "2026-03-01T00:00:00+00:00", "2026-03-01", None
        )
        assert result is True

    def test_date_to_boundary_inclusive(self):
        """date_to itself must be included (<=, not <)."""
        search = get_search_module()
        result = search._passes_date_filter(
            "2026-03-31T23:59:59+00:00", None, "2026-03-31"
        )
        assert result is True


class TestFtsRowsRoleParam:
    """_fts_rows accepts optional role parameter."""

    def test_fts_rows_signature_has_role_param(self):
        """_fts_rows must accept a role keyword argument."""
        search = get_search_module()
        sig = inspect.signature(search._fts_rows)
        assert "role" in sig.parameters, (
            f"role missing from _fts_rows signature: {list(sig.parameters.keys())}"
        )

    def test_fts_rows_role_default_is_none(self):
        """role must default to None for backward compatibility."""
        search = get_search_module()
        sig = inspect.signature(search._fts_rows)
        assert sig.parameters["role"].default is None


class TestSearchConversationsSignature:
    """search_conversations accepts the three new optional parameters."""

    def test_has_date_from_param(self):
        search = get_search_module()
        sig = inspect.signature(search.search_conversations)
        assert "date_from" in sig.parameters, (
            f"date_from missing: {list(sig.parameters.keys())}"
        )

    def test_has_date_to_param(self):
        search = get_search_module()
        sig = inspect.signature(search.search_conversations)
        assert "date_to" in sig.parameters, (
            f"date_to missing: {list(sig.parameters.keys())}"
        )

    def test_has_role_filter_param(self):
        search = get_search_module()
        sig = inspect.signature(search.search_conversations)
        assert "role_filter" in sig.parameters, (
            f"role_filter missing: {list(sig.parameters.keys())}"
        )

    def test_date_from_default_none(self):
        search = get_search_module()
        sig = inspect.signature(search.search_conversations)
        assert sig.parameters["date_from"].default is None

    def test_date_to_default_none(self):
        search = get_search_module()
        sig = inspect.signature(search.search_conversations)
        assert sig.parameters["date_to"].default is None

    def test_role_filter_default_none(self):
        search = get_search_module()
        sig = inspect.signature(search.search_conversations)
        assert sig.parameters["role_filter"].default is None


class TestSearchConversationsFunctional:
    """Functional tests for search_conversations with new filter params.

    These require a real DB populated with data, so some may be skipped
    if history.db is not available in the test environment.
    """

    def test_no_new_params_returns_list(self):
        """Existing call without new params still works — backward compatibility."""
        search = get_search_module()
        from claude_history.config import DB_PATH
        if not DB_PATH.exists():
            pytest.skip("history.db not available")
        results = search.search_conversations("the")
        assert isinstance(results, list)

    def test_future_date_returns_empty(self):
        """date_from in the far future must yield no results."""
        search = get_search_module()
        from claude_history.config import DB_PATH
        if not DB_PATH.exists():
            pytest.skip("history.db not available")
        results = search.search_conversations("the", date_from="2099-01-01")
        assert results == [], f"Expected [], got {results!r}"

    def test_role_filter_human_returns_list(self):
        """role_filter='human' must return a list (possibly empty)."""
        search = get_search_module()
        from claude_history.config import DB_PATH
        if not DB_PATH.exists():
            pytest.skip("history.db not available")
        results = search.search_conversations("the", role_filter="human")
        assert isinstance(results, list)

    def test_bogus_role_returns_empty(self):
        """Malformed role_filter returns [] without raising an exception."""
        search = get_search_module()
        from claude_history.config import DB_PATH
        if not DB_PATH.exists():
            pytest.skip("history.db not available")
        results = search.search_conversations("the", role_filter="bogus_role")
        assert results == [], f"Expected [], got {results!r}"
