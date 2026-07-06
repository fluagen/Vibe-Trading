"""Test opportunity-pool API endpoints — endpoint contracts and response shapes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api_server import app


def _client() -> TestClient:
    """Loopback client bypasses dev-mode auth."""
    return TestClient(app, client=("127.0.0.1", 50000))


class TestListStrategies:
    def test_returns_list(self):
        """GET /opportunity-pool/strategies should return a list of strategy names."""
        client = _client()
        resp = client.get("/opportunity-pool/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert "up_trend_structure" in data


class TestListCandidates:
    def test_returns_list(self):
        """GET /opportunity-pool/candidates returns a list (may be empty or have data from other tests)."""
        client = _client()
        resp = client.get("/opportunity-pool/candidates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Verify each item has required fields
        for item in data:
            assert "code" in item
            assert "name" in item
            assert "market" in item
            assert "source" in item


class TestCandidateCRUD:
    """Add and remove candidates via API."""

    def test_add_and_list_candidates(self):
        client = _client()

        resp = client.post("/opportunity-pool/candidates", json={
            "codes": ["600519.SH"],
            "names": ["贵州茅台"],
            "markets": ["SH"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] >= 0

        # List should include the added candidate
        resp2 = client.get("/opportunity-pool/candidates")
        assert resp2.status_code == 200
        codes = [item["code"] for item in resp2.json()]
        assert "600519.SH" in codes

    def test_remove_candidate(self):
        client = _client()

        # Ensure it exists
        client.post("/opportunity-pool/candidates", json={
            "codes": ["000001.SZ"],
            "names": ["平安银行"],
            "markets": ["SZ"],
        })

        resp = client.delete("/opportunity-pool/candidates/000001.SZ")
        assert resp.status_code == 200
        assert resp.json()["removed"] is True

        # Verify removed
        resp2 = client.get("/opportunity-pool/candidates")
        codes = [item["code"] for item in resp2.json()]
        assert "000001.SZ" not in codes

    def test_remove_nonexistent_returns_false(self):
        client = _client()
        resp = client.delete("/opportunity-pool/candidates/999999.SZ")
        assert resp.status_code == 200
        assert resp.json()["removed"] is False
