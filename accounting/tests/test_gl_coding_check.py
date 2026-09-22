"""GL coding check — description-vs-account sanity warning (hybrid).

The local matcher flags a line 'suspect' when the description shares no
meaningful keyword with the GL account name; a clear keyword match is 'ok'.
Generic-only names or empty descriptions can't be judged → 'ok' (never warn).
When the tenant has AI on, suspect lines escalate to the LLM, which can rescue
a semantic match the lexical check missed.
"""
from __future__ import annotations

import pytest


class TestLocalMatcher:
    def test_clear_keyword_match_is_ok(self):
        from accounting.services.gl_coding_check import check_line
        r = check_line(name="Motor Vehicle Fuel", code="221012",
                       description="Diesel fuel for the generator and vehicles")
        assert r["verdict"] == "ok"

    def test_clear_mismatch_is_suspect(self):
        from accounting.services.gl_coding_check import check_line
        r = check_line(name="Bank Charges", code="221099",
                       description="Diesel fuel for the generator")
        assert r["verdict"] == "suspect"
        assert r["reason"]        # a human-readable reason is present

    def test_generic_only_account_name_is_neutral_ok(self):
        # Nothing meaningful to match against → can't assess → don't warn.
        from accounting.services.gl_coding_check import check_line
        r = check_line(name="Sundry Expenses", code="229999",
                       description="Diesel fuel for the generator")
        assert r["verdict"] == "ok"

    def test_empty_description_is_ok(self):
        from accounting.services.gl_coding_check import check_line
        r = check_line(name="Motor Vehicle Fuel", code="221012", description="")
        assert r["verdict"] == "ok"

    def test_plural_and_case_fuzz_matches(self):
        from accounting.services.gl_coding_check import check_line
        r = check_line(name="Stationery and Office Supplies", code="221008",
                       description="office STATIONERY purchase")
        assert r["verdict"] == "ok"

    def test_typo_within_edit_distance_matches(self):
        from accounting.services.gl_coding_check import check_line
        r = check_line(name="Electricity Charges", code="221004",
                       description="monthly electricty bill")   # 'electricty' typo
        assert r["verdict"] == "ok"


class TestCheckLines:
    def test_off_ai_returns_local_verdicts(self, monkeypatch):
        from accounting.services import gl_coding_check as mod
        monkeypatch.setattr(mod, "_usable_reconciliation_setting", lambda tenant: None)
        out = mod.check_lines([
            {"index": 0, "name": "Motor Vehicle Fuel", "code": "221012", "description": "diesel fuel"},
            {"index": 1, "name": "Bank Charges", "code": "221099", "description": "diesel fuel"},
        ], tenant=object(), actor=None)
        assert out["ai_used"] is False
        v = {r["index"]: r["verdict"] for r in out["results"]}
        assert v[0] == "ok" and v[1] == "suspect"

    def test_ai_rescues_semantic_mismatch(self, monkeypatch):
        from accounting.services import gl_coding_check as mod
        monkeypatch.setattr(mod, "_usable_reconciliation_setting", lambda tenant: object())
        monkeypatch.setattr(
            mod, "_ai_adjudicate",
            lambda **kw: {"verdict": "ok", "reason": "fuel is a motor running cost"},
        )
        out = mod.check_lines([
            {"index": 0, "name": "Motor Running Costs", "code": "221012", "description": "vehicle fuel"},
        ], tenant=object(), actor=None)
        assert out["ai_used"] is True
        assert out["results"][0]["verdict"] == "ok"
        assert "fuel" in out["results"][0]["reason"].lower()

    def test_ai_error_keeps_local_suspect(self, monkeypatch):
        from accounting.services import gl_coding_check as mod

        def _boom(**kw):
            raise RuntimeError("provider down")

        monkeypatch.setattr(mod, "_usable_reconciliation_setting", lambda tenant: object())
        monkeypatch.setattr(mod, "_ai_adjudicate", _boom)
        out = mod.check_lines([
            {"index": 0, "name": "Bank Charges", "code": "221099", "description": "diesel fuel"},
        ], tenant=object(), actor=None)
        # AI failed → fall back to the local (suspect) verdict; posting is
        # advisory so a warning on outage is acceptable.
        assert out["results"][0]["verdict"] == "suspect"

    def test_caps_line_count(self, monkeypatch):
        from accounting.services import gl_coding_check as mod
        monkeypatch.setattr(mod, "_usable_reconciliation_setting", lambda tenant: None)
        lines = [{"index": i, "name": "Bank Charges", "description": "diesel fuel"} for i in range(300)]
        out = mod.check_lines(lines, tenant=None, actor=None)
        assert len(out["results"]) == mod.MAX_LINES


class TestEndpoint:
    def _post(self, user, body):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from accounting.views.gl_coding_check_view import GlCodingCheckView
        factory = APIRequestFactory()
        req = factory.post("/accounting/gl-coding-check/", body, format="json")
        force_authenticate(req, user=user)
        return GlCodingCheckView.as_view()(req)

    @pytest.mark.django_db
    def test_returns_per_line_verdicts(self, superuser):
        resp = self._post(superuser, {"lines": [
            {"index": 0, "name": "Motor Vehicle Fuel", "code": "221012", "description": "diesel fuel"},
            {"index": 1, "name": "Bank Charges", "code": "221099", "description": "diesel fuel"},
        ]})
        assert resp.status_code == 200, getattr(resp, "data", resp)
        v = {r["index"]: r["verdict"] for r in resp.data["results"]}
        assert v[0] == "ok" and v[1] == "suspect"

    @pytest.mark.django_db
    def test_rejects_non_list_body(self, superuser):
        resp = self._post(superuser, {"lines": "nope"})
        assert resp.status_code == 400
