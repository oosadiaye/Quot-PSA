# Adds the ``secret_encrypted`` flag, widens ``secret`` to hold Fernet
# ciphertext, and re-encrypts any pre-existing plaintext rows in place.

from django.db import migrations, models


def encrypt_existing_secrets(apps, schema_editor):
    """Re-encrypt any plaintext UserMFA.secret values produced before
    the encryption-at-rest rollout. Safe to re-run: rows already marked
    ``secret_encrypted=True`` are skipped.
    """
    UserMFA = apps.get_model('core', 'UserMFA')
    # Local import — ``apps.get_model`` returns the historical model
    # without methods, so we use the helper directly.
    from core.security.mfa_crypto import encrypt_secret

    qs = UserMFA.objects.filter(secret_encrypted=False).exclude(secret='')
    for row in qs.iterator():
        row.secret = encrypt_secret(row.secret)
        row.secret_encrypted = True
        row.save(update_fields=['secret', 'secret_encrypted'])


def noop_reverse(apps, schema_editor):
    """No safe reverse — decryption would require knowing the prior
    SECRET_KEY. Migration is a forward-only data fix."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_permission_catalog_and_sod_rules'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermfa',
            name='secret_encrypted',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='usermfa',
            name='secret',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.RunPython(encrypt_existing_secrets, noop_reverse),
    ]
