"""
Seed the four supported AI providers.

Migration 0012 created the table and the ``key`` choices, but nothing ever
wrote a row. So the superadmin AI page was empty on every environment
except a machine where someone had inserted a provider by hand — which
made the feature look broken rather than unconfigured, and left no way at
all to reach Claude, OpenAI or Gemini.

Every row lands **disabled and without a credential**. Seeding a catalogue
is not the same as switching anything on: ``is_usable`` stays False until
an operator adds a key and flips the toggle, so this migration cannot
cause a single call to leave the tenant.

``base_url`` ends at the provider's version segment for all four, which is
what lets ``/models`` resolve uniformly for the connection test. Each was
checked against the live endpoint — a correct path answers 401/403, a
wrong one answers 404:

    https://api.anthropic.com/v1/models                      401
    https://api.anthropic.com/models                         404   (why /v1 is in the base)
    https://api.openai.com/v1/models                         401
    https://generativelanguage.googleapis.com/v1beta/models  403
"""
from django.db import migrations

PROVIDERS = [
    {
        "key": "anthropic",
        "display_name": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1",
        "sort_order": 0,
        "retains_data": False,
        "is_broker": False,
        "data_policy_url": "https://www.anthropic.com/legal/privacy",
    },
    {
        "key": "openai",
        "display_name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "sort_order": 1,
        "retains_data": False,
        "is_broker": False,
        "data_policy_url": "https://openai.com/policies/privacy-policy",
    },
    {
        "key": "gemini",
        "display_name": "Google (Gemini)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "sort_order": 2,
        # Flagged True deliberately. Google's free Gemini tier uses
        # submitted content to improve its products; the paid tier does
        # not. An operator on a government tenant cannot tell which tier a
        # pasted key belongs to from this screen, and on a data-residency
        # control the honest default is the one that over-warns. Whoever
        # confirms a paid tier can clear the flag.
        "retains_data": True,
        "is_broker": False,
        "data_policy_url": "https://ai.google.dev/gemini-api/terms",
    },
    {
        "key": "openrouter",
        "display_name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "sort_order": 3,
        "retains_data": False,
        # Routes to upstream providers, so its data policy is the union of
        # theirs. Surfaced as a badge next to the toggle.
        "is_broker": True,
        "data_policy_url": "https://openrouter.ai/privacy",
    },
]


def seed(apps, schema_editor):
    AIProvider = apps.get_model("superadmin", "AIProvider")
    for row in PROVIDERS:
        # get_or_create, not update_or_create: an existing row may already
        # hold a live credential, a synced model catalogue and an operator's
        # deliberate base_url override for a proxy or regional endpoint.
        # Overwriting those to "fix" a default would be a worse bug than the
        # one this migration exists to fix.
        AIProvider.objects.get_or_create(
            key=row["key"],
            defaults={
                **row,
                "is_enabled": False,
                "api_key_encrypted": "",
                "available_models": [],
                "sends_document_images": True,
                "sends_ledger_amounts": True,
            },
        )


def unseed(apps, schema_editor):
    AIProvider = apps.get_model("superadmin", "AIProvider")
    # Only rows this migration could have created: no credential, never
    # enabled. A configured provider is an operator's work, not ours to
    # delete on a rollback.
    AIProvider.objects.filter(
        key__in=[r["key"] for r in PROVIDERS],
        api_key_encrypted="",
        is_enabled=False,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("superadmin", "0013_alter_aicall_cost_usd"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
