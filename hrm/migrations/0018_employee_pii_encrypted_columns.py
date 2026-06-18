"""Add encrypted-state flags, widen PII columns, and add HMAC hash columns.

Step 1 of the at-rest PII encryption rollout. Additive only — no plaintext
columns are dropped. Accessor methods on ``Employee`` use the per-row
``<field>_encrypted`` flag to transparently handle dual-state (plaintext
during the backfill, ciphertext after).

Fernet ciphertext for short inputs is ~140 bytes; widening the targeted
``CharField``\\s to ``max_length=255`` makes room without disturbing
existing form validation.
"""

from django.db import migrations, models


PII_FIELDS = [
    'national_id_number',
    'tax_identification_number',
    'social_security_number',
    'bank_account',
    'bank_routing',
]

SEARCHABLE_FIELDS = [
    'national_id_number',
    'tax_identification_number',
    'bank_account',
]


def _flag_field(name):
    return migrations.AddField(
        model_name='employee',
        name=f'{name}_encrypted',
        field=models.BooleanField(default=False),
    )


def _widen_field(name, help_text=''):
    kwargs = {'max_length': 255, 'blank': True}
    if help_text:
        kwargs['help_text'] = help_text
    return migrations.AlterField(
        model_name='employee',
        name=name,
        field=models.CharField(**kwargs),
    )


def _hash_field(name):
    return migrations.AddField(
        model_name='employee',
        name=f'{name}_hash',
        field=models.CharField(blank=True, db_index=True, default='', max_length=64),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0017_backfill_employee_organization'),
    ]

    operations = [
        # Encrypted-state flags (one per PII field).
        *[_flag_field(name) for name in PII_FIELDS],

        # Widen plaintext columns so Fernet ciphertext fits in-place.
        _widen_field('national_id_number', help_text='National ID Card Number'),
        _widen_field('tax_identification_number', help_text='Tax ID / TIN'),
        _widen_field('social_security_number', help_text='SSN / Social Security Number'),
        _widen_field('bank_account'),
        _widen_field('bank_routing'),

        # HMAC-hash columns for exact-match lookup on searchable PII.
        *[_hash_field(name) for name in SEARCHABLE_FIELDS],
    ]
