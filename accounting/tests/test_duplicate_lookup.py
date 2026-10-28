"""Master-data duplicate lookup + GL "adopt existing" suggestions.

Pure scoring tests need no DB; ``find_matches`` / endpoint / suggestion tests
run inside the test tenant (the ``db`` fixture is requested explicitly because
the tenant-schema switch in ``conftest.py`` keys off it, not the marker).
"""
from __future__ import annotations

import pytest


class TestNameSimilarity:
    def test_legal_suffixes_and_case_are_ignored(self):
        from core.services.duplicate_lookup import name_similarity
        assert name_similarity("Acme Nig. Ltd", "ACME NIGERIA LIMITED") == 1.0

    def test_typo_is_still_likely(self):
        from core.services.duplicate_lookup import LIKELY_THRESHOLD, name_similarity
        assert name_similarity("Dangote Cement Plc", "Dangoten Cement") >= LIKELY_THRESHOLD

    def test_word_order_does_not_matter(self):
        from core.services.duplicate_lookup import name_similarity
        assert name_similarity("Works Ministry of", "Ministry of Works") == 1.0

    def test_different_entities_do_not_match(self):
        from core.services.duplicate_lookup import SIMILAR_THRESHOLD, name_similarity
        assert name_similarity("Ministry of Health", "Ministry of Works") < SIMILAR_THRESHOLD

    def test_containment_of_multiword_name_is_similar(self):
        from core.services.duplicate_lookup import SIMILAR_THRESHOLD, name_similarity
        assert name_similarity("Ministry of Health", "Ministry of Health and Works") >= SIMILAR_THRESHOLD

    def test_single_generic_word_does_not_match_everything(self):
        from core.services.duplicate_lookup import SIMILAR_THRESHOLD, name_similarity
        assert name_similarity("Ministry", "Ministry of Works and Housing") < SIMILAR_THRESHOLD

    def test_empty_is_zero(self):
        from core.services.duplicate_lookup import name_similarity
        assert name_similarity("", "Acme") == 0.0
        assert name_similarity("Ltd", "Plc") == 0.0      # nothing but legal form


@pytest.mark.usefixtures("db")
class TestFindMatches:
    def test_unknown_entity_and_empty_values(self):
        from core.services.duplicate_lookup import find_matches
        assert find_matches("nope", {"name": "x"}) == []
        assert find_matches("account", {}) == []

    def test_account_same_code_is_exact(self):
        from accounting.models import Account
        from core.services.duplicate_lookup import find_matches
        Account.objects.create(code="22101001", name="Motor Vehicle Fuel", account_type="Expense")
        m = find_matches("account", {"code": "2210-1001", "name": "Something else"})
        assert [x["level"] for x in m] == ["exact"]
        assert "Same code" in m[0]["reasons"]

    def test_account_similar_name_different_code(self):
        from accounting.models import Account
        from core.services.duplicate_lookup import find_matches
        Account.objects.create(code="22101001", name="Motor Vehicle Fuel", account_type="Expense")
        Account.objects.create(code="22101002", name="Bank Charges", account_type="Expense")
        m = find_matches("account", {"code": "22109999", "name": "Motor Vehicles Fuel"})
        assert len(m) == 1 and m[0]["code"] == "22101001"
        assert m[0]["level"] in {"likely", "similar"}
        assert m[0]["extra"] == {"account_type": "Expense"}

    def test_exclude_id_omits_the_record_being_edited(self):
        from accounting.models import Account
        from core.services.duplicate_lookup import find_matches
        a = Account.objects.create(code="22101001", name="Motor Vehicle Fuel", account_type="Expense")
        assert find_matches("account", {"name": "Motor Vehicle Fuel"}, exclude_id=a.id) == []

    def test_mda_short_name_and_name(self):
        from accounting.models import MDA
        from core.services.duplicate_lookup import find_matches
        MDA.objects.create(code="0100", name="Ministry of Works", short_name="MOW", mda_type="MINISTRY")
        by_short = find_matches("mda", {"name": "Totally Different", "short_name": "mow"})
        assert by_short and by_short[0]["level"] == "exact"
        by_name = find_matches("mda", {"name": "Ministry of Works & Transport"})
        assert by_name and by_name[0]["code"] == "0100"

    def test_vendor_identifiers_and_name(self):
        from procurement.models import Vendor
        from core.services.duplicate_lookup import find_matches
        Vendor.objects.create(
            name="Acme Nigeria Limited", code="V001", tax_id="TIN-123456", phone="+234 803 123 4567",
            email="Sales@Acme.com",
        )
        # Different name, but same TIN / phone / e-mail → exact on each identifier.
        m = find_matches("vendor", {
            "name": "Unrelated Name", "tax_id": "tin123456",
            "phone": "0803 123 4567", "email": "sales@acme.com",
        })
        assert len(m) == 1 and m[0]["level"] == "exact"
        assert {"Same Tax ID", "Same phone number", "Same e-mail"} <= set(m[0]["reasons"])
        # Same company typed differently.
        m2 = find_matches("vendor", {"name": "ACME Nig. Ltd"})
        assert m2 and m2[0]["level"] == "likely" and "Same name" in m2[0]["reasons"]

    def test_limit_and_ordering_exact_first(self):
        from accounting.models import Account
        from core.services.duplicate_lookup import find_matches
        for i in range(8):
            Account.objects.create(code=f"2210{i}", name=f"Office Stationery {i}", account_type="Expense")
        Account.objects.create(code="99999", name="Office Stationery", account_type="Expense")
        m = find_matches("account", {"code": "99999", "name": "Office Stationery"}, limit=3)
        assert len(m) == 3 and m[0]["level"] == "exact" and m[0]["code"] == "99999"


@pytest.mark.usefixtures("db")
class TestEndpoint:
    def _post(self, user, body):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from core.views.duplicate_check import DuplicateCheckView
        req = APIRequestFactory().post("/core/duplicate-check/", body, format="json")
        force_authenticate(req, user=user)
        return DuplicateCheckView.as_view()(req)

    def test_returns_matches(self, superuser):
        from accounting.models import Account
        Account.objects.create(code="22101001", name="Motor Vehicle Fuel", account_type="Expense")
        resp = self._post(superuser, {"entity": "account", "values": {"name": "Motor Vehicle Fuel"}})
        assert resp.status_code == 200, getattr(resp, "data", resp)
        assert resp.data["matches"][0]["code"] == "22101001"

    def test_rejects_bad_input(self, superuser):
        assert self._post(superuser, {"entity": "nope", "values": {}}).status_code == 400
        assert self._post(superuser, {"entity": "vendor", "values": "x"}).status_code == 400

    def test_user_without_a_tenant_role_is_forbidden(self, maker_user, monkeypatch):
        # The lookup reads the master list, so it needs the same right as
        # listing it — an authenticated user with no role must not probe it.
        import core.permissions as perms
        monkeypatch.setattr(perms, "_get_tenant_role", lambda user, tenant: None)
        resp = self._post(maker_user, {"entity": "vendor", "values": {"name": "Acme"}})
        assert resp.status_code == 403

    def test_requires_authentication(self):
        from rest_framework.test import APIRequestFactory
        from core.views.duplicate_check import DuplicateCheckView
        req = APIRequestFactory().post("/core/duplicate-check/", {"entity": "vendor", "values": {}}, format="json")
        assert DuplicateCheckView.as_view()(req).status_code in (401, 403)


@pytest.mark.usefixtures("db")
class TestGlSuggestions:
    def test_suspect_line_gets_fitting_account_suggested(self, superuser):
        from accounting.models import Account
        from accounting.services.gl_coding_check import check_lines
        Account.objects.create(code="22101001", name="Motor Vehicle Fuel", account_type="Expense")
        Account.objects.create(code="22109999", name="Bank Charges", account_type="Expense")
        Account.objects.create(code="10101001", name="Cash at Bank", account_type="Asset")
        out = check_lines([
            {"index": 0, "name": "Bank Charges", "code": "22109999", "description": "Fuel for vehicles"},
        ])
        r = out["results"][0]
        assert r["verdict"] == "suspect"
        assert [s["code"] for s in r["suggestions"]] == ["22101001"]
        assert r["suggestions"][0]["source"] == "name"

    def test_ok_line_has_no_suggestions_and_header_accounts_never_suggested(self):
        from accounting.models import Account
        from accounting.services.gl_coding_check import check_lines
        Account.objects.create(code="22101001", name="Motor Vehicle Fuel", account_type="Expense")
        Account.objects.create(code="2210", name="Fuel Group", account_type="Expense", is_postable=False)
        Account.objects.create(code="22109999", name="Bank Charges", account_type="Expense")
        out = check_lines([
            {"index": 0, "name": "Motor Vehicle Fuel", "code": "22101001", "description": "diesel fuel"},
            {"index": 1, "name": "Bank Charges", "code": "22109999", "description": "fuel"},
        ])
        ok, bad = out["results"]
        assert ok["verdict"] == "ok" and ok["suggestions"] == []
        assert [s["code"] for s in bad["suggestions"]] == ["22101001"]     # not the header "Fuel Group"

    def test_suggestions_stay_within_account_type(self):
        from accounting.models import Account
        from accounting.services.gl_coding_check import check_lines
        Account.objects.create(code="22109999", name="Bank Charges", account_type="Expense")
        Account.objects.create(code="30101001", name="Fuel Sales", account_type="Income")
        out = check_lines([{"index": 0, "name": "Bank Charges", "code": "22109999", "description": "fuel sales"}])
        assert out["results"][0]["suggestions"] == []

    def test_endpoint_includes_suggestions(self, superuser):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from accounting.models import Account
        from accounting.views.gl_coding_check_view import GlCodingCheckView
        Account.objects.create(code="22101001", name="Motor Vehicle Fuel", account_type="Expense")
        Account.objects.create(code="22109999", name="Bank Charges", account_type="Expense")
        req = APIRequestFactory().post("/accounting/gl-coding-check/", {"lines": [
            {"index": 3, "name": "Bank Charges", "code": "22109999", "description": "diesel fuel"},
        ]}, format="json")
        force_authenticate(req, user=superuser)
        resp = GlCodingCheckView.as_view()(req)
        assert resp.status_code == 200
        assert resp.data["results"][0]["suggestions"][0]["id"] is not None
