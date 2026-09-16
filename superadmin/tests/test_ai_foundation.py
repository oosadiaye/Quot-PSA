"""
AI credential encryption and payload redaction.

No database. Both modules are pure functions over strings, and both sit
on the path where a State's ledger content leaves the tenant — so the
cases worth pinning are the ones where a mistake is silent:

  * a credential store that quietly stops encrypting;
  * a rotation path that loses every key;
  * a redactor that removes so much the model cannot do the task, or so
    little that an account number travels anyway;
  * a redactor whose tokens collide, so restoring produces the wrong
    value in a proposal an operator will act on.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken
from django.test import SimpleTestCase, override_settings

from superadmin.ai_crypto import (
    AIKeyNotConfigured,
    CURRENT_VERSION,
    decrypt_ai_secret,
    encrypt_ai_secret,
    is_encrypted,
    mask,
)
from superadmin.ai_redaction import redact, redact_payload, restore

KEK_A = "a" * 64          # 32 bytes of hex
KEK_B = "b" * 64


@override_settings(AI_KEK_HEX=KEK_A)
class CredentialEncryptionTests(SimpleTestCase):

    def test_round_trip(self):
        secret = "sk-ant-api03-not-a-real-key"
        assert decrypt_ai_secret(encrypt_ai_secret(secret)) == secret

    def test_ciphertext_does_not_contain_the_secret(self):
        # The assertion that actually matters: an envelope that happened
        # to be reversible without the key would still round-trip.
        secret = "sk-ant-api03-not-a-real-key"
        stored = encrypt_ai_secret(secret)
        assert secret not in stored
        assert stored.startswith(f"{CURRENT_VERSION}:")

    def test_same_secret_encrypts_differently_each_time(self):
        # Fernet includes a random IV. Identical ciphertexts would let
        # anyone with table access tell which tenants share a key.
        secret = "sk-openai-abc"
        assert encrypt_ai_secret(secret) != encrypt_ai_secret(secret)

    def test_empty_stays_empty(self):
        # "No credential set" is a real state for a provider row created
        # but not yet configured; encrypting it would make unset look set.
        assert encrypt_ai_secret("") == ""
        assert decrypt_ai_secret("") == ""

    def test_is_encrypted_recognises_its_own_envelope(self):
        assert is_encrypted(encrypt_ai_secret("x")) is True
        assert is_encrypted("sk-plaintext") is False
        assert is_encrypted("") is False

    def test_a_plaintext_value_is_refused_not_guessed(self):
        # Silently returning the input would mean a credential that was
        # never encrypted reads back fine and nobody ever finds out.
        with pytest.raises(InvalidToken):
            decrypt_ai_secret("sk-ant-plaintext-that-was-never-encrypted")

    def test_a_value_from_the_other_key_store_is_refused(self):
        # superadmin/encryption.py writes a 'fernet:' prefix. Accepting it
        # here would blur the two key domains, which is the whole point of
        # having a separate KEK.
        with pytest.raises(InvalidToken):
            decrypt_ai_secret("fernet:gAAAAABn0000")


class MissingKeyTests(SimpleTestCase):

    @override_settings(AI_KEK_HEX=None)
    def test_encrypt_without_a_key_raises(self):
        # Never a silent fallback to plaintext. A store that quietly stops
        # encrypting is discovered by an attacker; one that refuses is
        # discovered by an operator.
        with pytest.raises(AIKeyNotConfigured):
            encrypt_ai_secret("sk-test")

    @override_settings(AI_KEK_HEX="not-hex-at-all")
    def test_malformed_key_names_the_setting(self):
        with pytest.raises(AIKeyNotConfigured) as exc:
            encrypt_ai_secret("sk-test")
        assert "AI_KEK_HEX" in str(exc.value)

    @override_settings(AI_KEK_HEX="abcd")
    def test_short_key_is_refused(self):
        with pytest.raises(AIKeyNotConfigured) as exc:
            encrypt_ai_secret("sk-test")
        assert "32 bytes" in str(exc.value)


class KeyRotationTests(SimpleTestCase):
    """Rotation must be a background task, not an outage."""

    def test_a_secret_written_under_the_old_key_still_reads(self):
        with override_settings(AI_KEK_HEX=KEK_A):
            stored = encrypt_ai_secret("sk-written-before-rotation")
        with override_settings(AI_KEK_HEX=KEK_B, AI_KEK_HEX_OLD=KEK_A):
            assert decrypt_ai_secret(stored) == "sk-written-before-rotation"

    def test_without_the_old_key_it_fails_loudly(self):
        with override_settings(AI_KEK_HEX=KEK_A):
            stored = encrypt_ai_secret("sk-written-before-rotation")
        with override_settings(AI_KEK_HEX=KEK_B, AI_KEK_HEX_OLD=None):
            with pytest.raises(InvalidToken):
                decrypt_ai_secret(stored)

    def test_new_writes_use_the_current_key_only(self):
        # After re-wrapping, dropping the old key must not break anything
        # written since the rotation.
        with override_settings(AI_KEK_HEX=KEK_B, AI_KEK_HEX_OLD=KEK_A):
            stored = encrypt_ai_secret("sk-written-after-rotation")
        with override_settings(AI_KEK_HEX=KEK_B, AI_KEK_HEX_OLD=None):
            assert decrypt_ai_secret(stored) == "sk-written-after-rotation"


class MaskTests(SimpleTestCase):

    def test_shows_the_tail_not_the_head(self):
        # The head of a provider key identifies the provider and account
        # and is the guessable part; the tail distinguishes which key.
        masked = mask("sk-ant-api03-abcdefgh")
        assert masked == "...efgh"
        assert "sk-ant" not in masked

    def test_short_values_disclose_nothing(self):
        assert mask("abc") == "***"

    def test_empty(self):
        assert mask("") == ""


class RedactionTests(SimpleTestCase):

    def test_account_number_is_replaced(self):
        out = redact("Transfer to 0123456789 completed")
        assert "0123456789" not in out.text
        assert "[ACCT_1]" in out.text

    def test_the_same_value_gets_the_same_token(self):
        # This is what preserves the task: a model asked whether two
        # lines refer to one account answers from the repeated token.
        out = redact("from 0123456789 to 9876543210 then 0123456789 again")
        assert out.text.count("[ACCT_1]") == 2
        assert "[ACCT_2]" in out.text
        assert out.redacted_count == 2

    def test_amounts_survive(self):
        # Redacting the amounts would remove the reconciliation task.
        out = redact("Paid NGN 4,770,750.44 to 0123456789 on 2026-09-13")
        assert "4,770,750.44" in out.text
        assert "2026-09-13" in out.text

    def test_document_references_survive(self):
        # PB/2026/0001 is the thing a matcher matches on.
        out = redact("Batch PB/2026/0001 credited 0123456789")
        assert "PB/2026/0001" in out.text

    def test_an_eleven_digit_bvn_is_tokenised_whole(self):
        # Named for what it checks. An earlier version claimed to prove
        # that BVN must be matched before ACCT; mutation testing showed
        # swapping that order changes nothing, because the lookarounds
        # already refuse a 10-digit match inside an 11-digit run. What
        # is worth pinning is the outcome: the identifier leaves whole,
        # not split into an account plus a stray digit.
        out = redact("BVN 12345678901 holder")
        assert "12345678901" not in out.text
        assert "[BVN_1]" in out.text
        # Not 'no digits' - tokens are numbered, so [BVN_1] contains
        # one by design. What must not survive is a long digit run,
        # which is what an identifier actually is.
        import re as _re
        assert _re.search(r"\d{7,}", out.text) is None

    def test_a_long_card_like_run_leaves_no_digits_behind(self):
        # The real overlap risk: a 16-digit run could in principle be
        # partly consumed, leaving a recognisable remainder in the
        # payload. Whole-or-nothing is the property that matters.
        import re as _re
        out = redact("card 4111111111111111 charged")
        assert "4111111111111111" not in out.text
        assert _re.search(r"\d{7,}", out.text) is None

    def test_tin_email_and_phone(self):
        out = redact("TIN 12345678-0001, mail a.b@example.gov.ng, tel +234 803 123 4567")
        assert "12345678-0001" not in out.text
        assert "a.b@example.gov.ng" not in out.text
        assert "803" not in out.text

    def test_restore_puts_the_original_back(self):
        out = redact("credit 0123456789")
        proposal = f"Matched {out.text} to invoice INV-1"
        assert "0123456789" in restore(proposal, out.mapping)

    def test_restore_is_not_confused_by_a_token_prefix(self):
        # [ACCT_1] is a prefix of [ACCT_11]. Replacing shortest-first
        # would corrupt the eleventh into "<value of 1>1".
        mapping = {"[ACCT_1]": "1111111111", "[ACCT_11]": "9999999999"}
        assert restore("[ACCT_11]", mapping) == "9999999999"

    def test_empty_input(self):
        out = redact("")
        assert out.text == ""
        assert out.mapping == {}


class PayloadRedactionTests(SimpleTestCase):

    def test_nested_structures_are_walked(self):
        payload = {
            "vendor": {"name": "Acme Ltd", "account": "0123456789"},
            "lines": [{"memo": "paid to 0123456789"}],
        }
        out, mapping = redact_payload(payload)
        assert out["vendor"]["account"] == "[ACCT_1]"
        # Same account in a different field must share one token, or the
        # model cannot tell that they are the same account.
        assert out["lines"][0]["memo"] == "paid to [ACCT_1]"
        assert mapping["[ACCT_1]"] == "0123456789"

    def test_numbers_pass_through(self):
        payload = {"total": 4770750.44, "count": 3, "posted": True, "note": None}
        out, mapping = redact_payload(payload)
        assert out == payload
        assert mapping == {}

    def test_distinct_accounts_get_distinct_tokens(self):
        payload = {"a": "0123456789", "b": "9876543210"}
        out, mapping = redact_payload(payload)
        assert out["a"] != out["b"]
        assert len(mapping) == 2
