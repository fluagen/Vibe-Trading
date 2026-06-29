"""Tests for sector_flow_tool: envelope shape, parsing, sort dispatch, validation.

All HTTP is mocked at ``src.tools.sector_flow_tool.get_json``, so no test
touches a live Eastmoney endpoint.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from src.tools.sector_flow_tool import SectorFlowTool

_BOARD_FLOW_PAYLOAD = {
    "data": {
        "diff": [
            {
                "f12": "BK0477",
                "f14": "白酒",
                "f3": 3.4,
                "f2": 12345.0,
                "f6": 45120000000.0,
                "f62": 5250000000.0,
                "f8": 4.2,
                "f104": 18,
                "f105": 2,
                "f140": "贵州茅台",
            },
            {
                "f12": "BK0727",
                "f14": "银行",
                "f3": 1.1,
                "f2": 6789.0,
                "f6": 28900000000.0,
                "f62": -1200000000.0,
                "f8": 1.8,
                "f104": 30,
                "f105": 12,
                "f140": "-",
            },
            {
                "f12": "BK0815",
                "f14": "酿酒行业",
                "f3": -0.5,
                "f2": "-",
                "f6": "-",
                "f62": None,
                "f8": "",
                "f104": 10,
                "f105": 20,
                "f140": "-",
            },
            {"f14": "missing-code"},  # dropped: no f12
        ]
    }
}


class TestSectorFlowEnvelope:
    """The ok envelope carries board_type, sort_by, and parsed boards."""

    def test_flow_parses_boards(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            text = SectorFlowTool().execute(
                board_type="industry", sort_by="amount", limit=20
            )

        url = mock_get.call_args[0][0]
        assert "clist/get" in url
        params = mock_get.call_args.kwargs["params"]
        assert params["fs"] == "m:90+t:2"
        assert params["fid"] == "f6"

        payload = json.loads(text)
        assert payload["ok"] is True
        assert payload["market"] == "stock"
        assert payload["source"] == "eastmoney"
        assert payload["data"]["board_type"] == "industry"
        assert payload["data"]["sort_by"] == "amount"

        boards = payload["data"]["boards"]
        assert len(boards) == 3  # the f12-less row is dropped

        # First board: all fields populated.
        b0 = boards[0]
        assert b0["board_code"] == "BK0477"
        assert b0["board_name"] == "白酒"
        assert b0["change_pct"] == 3.4
        assert b0["index"] == 12345.0
        assert b0["turnover"] == 45120000000.0
        assert b0["main_net_inflow"] == 5250000000.0
        assert b0["turnover_rate"] == 4.2
        assert b0["up_count"] == 18.0
        assert b0["down_count"] == 2.0
        assert b0["leader"] == "贵州茅台"

    def test_leader_coerced_to_none(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ):
            payload = json.loads(SectorFlowTool().execute())

        # BK0727 has f140 = "-" → leader is None.
        assert payload["data"]["boards"][1]["leader"] is None

    def test_missing_fields_coerced_to_none(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ):
            payload = json.loads(SectorFlowTool().execute())

        # BK0815 has "-", None, "" for various fields → all coerced to None.
        b2 = payload["data"]["boards"][2]
        assert b2["change_pct"] == -0.5
        assert b2["index"] is None
        assert b2["turnover"] is None
        assert b2["main_net_inflow"] is None
        assert b2["turnover_rate"] is None


class TestSortAndBoardType:
    """sort_by and board_type map to the correct fid and fs parameters."""

    def test_sort_by_amount_uses_f6(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute(sort_by="amount")

        assert mock_get.call_args.kwargs["params"]["fid"] == "f6"

    def test_sort_by_net_inflow_uses_f62(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute(sort_by="net_inflow")

        assert mock_get.call_args.kwargs["params"]["fid"] == "f62"

    def test_sort_by_change_pct_uses_f3(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute(sort_by="change_pct")

        assert mock_get.call_args.kwargs["params"]["fid"] == "f3"

    def test_concept_board_universe(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute(board_type="concept")

        assert mock_get.call_args.kwargs["params"]["fs"] == "m:90+t:3"

    def test_default_board_type_is_industry(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute()

        assert mock_get.call_args.kwargs["params"]["fs"] == "m:90+t:2"

    def test_default_sort_by_is_change_pct(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute()

        assert mock_get.call_args.kwargs["params"]["fid"] == "f3"


class TestLimitCapping:
    """limit is validated and capped at the defensive maximum."""

    def test_limit_capped_to_max(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute(limit=10_000)

        assert mock_get.call_args.kwargs["params"]["pz"] == "100"

    def test_default_limit(self):
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock_get:
            SectorFlowTool().execute()

        assert mock_get.call_args.kwargs["params"]["pz"] == "30"


class TestDiffAsDict:
    """Some push2 responses key diff rows by string index instead of a list."""

    def test_diff_as_dict_is_handled(self):
        dict_payload = {
            "data": {"diff": {"0": _BOARD_FLOW_PAYLOAD["data"]["diff"][0]}}
        }
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=dict_payload
        ):
            payload = json.loads(SectorFlowTool().execute())

        assert len(payload["data"]["boards"]) == 1


class TestErrorHandling:
    """Validation and request failures return the ok=false envelope."""

    def test_invalid_board_type_rejected(self):
        payload = json.loads(SectorFlowTool().execute(board_type="etf"))
        assert payload["ok"] is False
        assert "board_type" in payload["error"]

    def test_invalid_sort_by_rejected(self):
        payload = json.loads(SectorFlowTool().execute(sort_by="volume"))
        assert payload["ok"] is False
        assert "sort_by" in payload["error"]

    def test_non_positive_limit_rejected(self):
        payload = json.loads(SectorFlowTool().execute(limit=0))
        assert payload["ok"] is False
        assert "limit" in payload["error"]

    def test_bool_limit_rejected(self):
        payload = json.loads(SectorFlowTool().execute(limit=True))
        assert payload["ok"] is False
        assert "limit" in payload["error"]

    def test_http_failure_error_envelope(self):
        with patch(
            "src.tools.sector_flow_tool.get_json",
            side_effect=RuntimeError("HTTP 429"),
        ):
            payload = json.loads(SectorFlowTool().execute())
        assert payload["ok"] is False
        assert "429" in payload["error"]


class TestRetry:
    """Transient failures trigger retries before returning an error."""

    def test_retry_on_failure_then_succeed(self):
        """Fail on attempts 1 and 2, succeed on 3 — verify all 3 calls made."""
        call_count = 0

        def flaky_get_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"transient failure #{call_count}")
            return _BOARD_FLOW_PAYLOAD

        with patch("src.tools.sector_flow_tool.get_json", side_effect=flaky_get_json) as mock:
            payload = json.loads(SectorFlowTool().execute())

        assert mock.call_count == 3
        assert payload["ok"] is True
        assert len(payload["data"]["boards"]) == 3

    def test_retry_exhaustion_returns_error(self):
        """After 3 failures, return an error envelope mentioning attempts."""
        with patch(
            "src.tools.sector_flow_tool.get_json",
            side_effect=TimeoutError("connection timed out"),
        ) as mock:
            payload = json.loads(SectorFlowTool().execute())

        assert mock.call_count == 3  # noqa: PLR2004
        assert payload["ok"] is False
        assert "after 3 attempts" in payload["error"]

    def test_success_on_first_attempt_no_retry(self):
        """First-attempt success makes exactly one call — no sleeping or retrying."""
        with patch(
            "src.tools.sector_flow_tool.get_json", return_value=_BOARD_FLOW_PAYLOAD
        ) as mock:
            payload = json.loads(SectorFlowTool().execute())

        assert mock.call_count == 1
        assert payload["ok"] is True
