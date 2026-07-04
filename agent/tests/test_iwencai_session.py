"""Test iwencai_session — skill ID rotation, throttling, and retry logic."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from src.api.iwencai_session import (
    SkillExhaustedError,
    _get_api_key,
    _get_skill_id,
    _handle_rate_limit,
    _init_skill_ids,
    iwencai_paginate,
    iwencai_query,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _reset_skill_state():
    """Reset module-level globals between tests."""
    import src.api.iwencai_session as mod

    mod._skill_ids = []
    mod._current_skill_index = 0
    mod._exhausted = set()


@pytest.fixture(autouse=True)
def _clean_state():
    _reset_skill_state()
    yield
    _reset_skill_state()


# ═══════════════════════════════════════════════════════════════════════════════
# _init_skill_ids
# ═══════════════════════════════════════════════════════════════════════════════


class TestInitSkillIds:
    def test_default_when_no_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            _init_skill_ids()
        import src.api.iwencai_session as mod

        assert mod._skill_ids == ["hithink-sector-selector"]
        assert mod._current_skill_index == 0
        assert mod._exhausted == set()

    def test_single_skill_id_env(self):
        with mock.patch.dict(os.environ, {"IWENCAI_SKILL_ID": "my-custom-id"}, clear=True):
            _init_skill_ids()
        import src.api.iwencai_session as mod

        assert mod._skill_ids == ["my-custom-id"]

    def test_multiple_skill_ids_env(self):
        with mock.patch.dict(
            os.environ, {"IWENCAI_SKILL_IDS": "id-a, id-b ,id-c"}, clear=True
        ):
            _init_skill_ids()
        import src.api.iwencai_session as mod

        assert mod._skill_ids == ["id-a", "id-b", "id-c"]

    def test_skill_ids_takes_priority_over_single(self):
        with mock.patch.dict(
            os.environ,
            {"IWENCAI_SKILL_IDS": "id-a,id-b", "IWENCAI_SKILL_ID": "ignored"},
            clear=True,
        ):
            _init_skill_ids()
        import src.api.iwencai_session as mod

        assert mod._skill_ids == ["id-a", "id-b"]

    def test_whitespace_only_skill_id_falls_back(self):
        with mock.patch.dict(os.environ, {"IWENCAI_SKILL_ID": "   "}, clear=True):
            _init_skill_ids()
        import src.api.iwencai_session as mod

        assert mod._skill_ids == ["hithink-sector-selector"]

    def test_skill_ids_resets_exhausted(self):
        import src.api.iwencai_session as mod

        mod._exhausted = {0, 1}
        mod._current_skill_index = 3
        with mock.patch.dict(
            os.environ, {"IWENCAI_SKILL_IDS": "id-a,id-b,id-c"}, clear=True
        ):
            _init_skill_ids()

        assert mod._exhausted == set()
        assert mod._current_skill_index == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _get_skill_id
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetSkillId:
    def test_lazy_init(self):
        _reset_skill_state()
        import src.api.iwencai_session as mod

        assert mod._skill_ids == []
        with mock.patch.dict(os.environ, {"IWENCAI_SKILL_ID": "lazy-id"}, clear=True):
            sid = _get_skill_id()
        assert sid == "lazy-id"
        assert mod._skill_ids == ["lazy-id"]

    def test_returns_current_index(self):
        import src.api.iwencai_session as mod

        mod._skill_ids = ["a", "b", "c"]
        mod._current_skill_index = 2
        assert _get_skill_id() == "c"


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_rate_limit
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleRateLimit:
    def test_switches_to_next_available(self):
        import src.api.iwencai_session as mod

        mod._skill_ids = ["id-0", "id-1", "id-2"]
        mod._current_skill_index = 0
        mod._exhausted = set()

        with mock.patch("time.sleep", return_value=None):
            _handle_rate_limit()

        assert 0 in mod._exhausted
        assert mod._current_skill_index == 1

    def test_skips_already_exhausted(self):
        import src.api.iwencai_session as mod

        mod._skill_ids = ["id-0", "id-1", "id-2"]
        mod._current_skill_index = 0
        mod._exhausted = {1}

        with mock.patch("time.sleep", return_value=None):
            _handle_rate_limit()

        assert mod._current_skill_index == 2  # skipped id-1

    def test_wraps_around_circularly(self):
        import src.api.iwencai_session as mod

        mod._skill_ids = ["id-0", "id-1", "id-2"]
        mod._current_skill_index = 2
        mod._exhausted = {0}

        with mock.patch("time.sleep", return_value=None):
            _handle_rate_limit()

        assert mod._current_skill_index == 1  # wrapped around

    def test_raises_when_all_exhausted(self):
        import src.api.iwencai_session as mod

        # Only 1 ID, so exhausting it leaves none available
        mod._skill_ids = ["only-one"]
        mod._current_skill_index = 0
        mod._exhausted = set()

        with mock.patch("time.sleep", return_value=None):
            with pytest.raises(RuntimeError, match="今日配额已用完"):
                _handle_rate_limit()


# ═══════════════════════════════════════════════════════════════════════════════
# _get_api_key
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetApiKey:
    def test_env_var_first(self):
        with mock.patch.dict(os.environ, {"IWENCAI_API_KEY": "env-key"}, clear=True):
            assert _get_api_key() == "env-key"

    def test_falls_back_to_nonexistent_env_file(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("pathlib.Path.exists", return_value=False):
                with pytest.raises(RuntimeError, match="IWENCAI_API_KEY 未设置"):
                    _get_api_key()

    def test_reads_from_dotenv_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('IWENCAI_API_KEY="file-key"\n')

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("pathlib.Path.exists", return_value=True):
                with mock.patch(
                    "pathlib.Path.read_text", return_value=env_file.read_text()
                ):
                    key = _get_api_key()
                    assert key == "file-key"


# ═══════════════════════════════════════════════════════════════════════════════
# iwencai_query skill exhaustion
# ═══════════════════════════════════════════════════════════════════════════════


class TestIwencaiQuerySkillExhaustion:

    def test_401_quota_exhausted_rotates_and_raises_skill_exhausted(self):
        import urllib.error
        import src.api.iwencai_session as mod

        mod._skill_ids = ["id-0", "id-1"]
        mod._current_skill_index = 0

        http_error = urllib.error.HTTPError(
            url="https://test/", code=401, msg="Unauthorized", hdrs={}, fp=None
        )

        with mock.patch.dict(os.environ, {"IWENCAI_API_KEY": "test-key"}, clear=True):
            with mock.patch.object(mod._THROTTLE, "wait", return_value=None):
                with mock.patch("urllib.request.urlopen") as mock_urlopen:
                    mock_urlopen.side_effect = http_error
                    with mock.patch.object(
                        http_error, "read", return_value='{"msg":"次数已用完"}'.encode()
                    ):
                        with mock.patch("time.sleep", return_value=None):
                            with pytest.raises(SkillExhaustedError):
                                iwencai_query("test query")

        assert 0 in mod._exhausted
        assert mod._current_skill_index == 1

    def test_other_http_error_raises_runtime_error(self):
        import urllib.error
        import src.api.iwencai_session as mod

        http_error = urllib.error.HTTPError(
            url="https://test/", code=500, msg="Server Error", hdrs={}, fp=None
        )

        with mock.patch.dict(os.environ, {"IWENCAI_API_KEY": "test-key"}, clear=True):
            with mock.patch.object(mod._THROTTLE, "wait", return_value=None):
                with mock.patch("urllib.request.urlopen") as mock_urlopen:
                    mock_urlopen.side_effect = http_error
                    with mock.patch.object(
                        http_error, "read", return_value=b"Server error body"
                    ):
                        with pytest.raises(RuntimeError, match="问财 API HTTP 500"):
                            iwencai_query("test query")


# ═══════════════════════════════════════════════════════════════════════════════
# iwencai_paginate retry behavior
# ═══════════════════════════════════════════════════════════════════════════════


MOCK_PAGE_DATA = {"datas": [{"code": "000001"}], "code_count": 1}


class TestIwencaiPaginateRetry:

    def test_retries_same_page_on_skill_exhausted(self):
        call_count = [0]

        def mock_query(query, page=1, limit=200):
            call_count[0] += 1
            if call_count[0] == 1:
                raise SkillExhaustedError("quota exhausted")
            return MOCK_PAGE_DATA

        with mock.patch("src.api.iwencai_session.iwencai_query", side_effect=mock_query):
            with mock.patch("time.sleep", return_value=None):
                rows = iwencai_paginate("test query", max_pages=1, label="test")

        assert len(rows) == 1
        assert call_count[0] == 2  # first raised, second succeeded

    def test_skips_page_on_general_error(self):
        call_count = [0]

        def mock_query(query, page=1, limit=200):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient network error")
            return MOCK_PAGE_DATA

        with mock.patch("src.api.iwencai_session.iwencai_query", side_effect=mock_query):
            with mock.patch("time.sleep", return_value=None):
                rows = iwencai_paginate("test query", max_pages=2, label="test")

        assert len(rows) == 1
        assert call_count[0] == 2

    def test_all_skill_ids_exhausted_stops_pagination(self):
        import urllib.error
        import src.api.iwencai_session as mod

        mod._skill_ids = ["only-one"]
        mod._current_skill_index = 0

        http_error = urllib.error.HTTPError(
            url="https://test/", code=401, msg="Unauthorized", hdrs={}, fp=None
        )
        error_body = '{"msg":"次数已用完"}'.encode()

        with mock.patch.dict(os.environ, {"IWENCAI_API_KEY": "test-key"}, clear=True):
            with mock.patch.object(mod._THROTTLE, "wait", return_value=None):
                with mock.patch("urllib.request.urlopen") as mock_urlopen:
                    mock_urlopen.side_effect = http_error
                    with mock.patch.object(http_error, "read", return_value=error_body):
                        with mock.patch("time.sleep", return_value=None):
                            rows = iwencai_paginate(
                                "test query", max_pages=1, label="test"
                            )

        # Single ID exhausted → _handle_rate_limit raises RuntimeError
        # → iwencai_query propagates it (not SkillExhaustedError)
        # → paginate skips page → returns empty
        assert rows == []
