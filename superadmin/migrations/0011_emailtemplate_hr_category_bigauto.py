"""
Reconcile EmailTemplate with two model-vs-schema drifts that were
generating spurious operations on every ``makemigrations`` run:

1. ``category`` — model was extended with ``('hr', 'Human Resources')``
   after migration 0010 was written; the choices list in the schema
   was 6 entries while the model now declares 7. This is a metadata-
   only change at the database level (CharField + choices), but
   Django still tracks it as a field alteration so it surfaces as
   drift until reconciled.

2. ``id`` — the EmailTemplate table was created with ``AutoField``
   (Django's pre-3.2 default), but the project sets
   ``DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'`` and the
   ``superadmin`` AppConfig declares ``BigAutoField`` as well. The
   model therefore implicitly carries ``BigAutoField`` while the
   schema has int4 — a real type change that will need to land
   eventually as the row count grows.

Applied across all tenant schemas (this is in SHARED_APPS), so it
touches the public schema only — django-tenants routes superadmin
tables there.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin', '0010_emailtemplate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailtemplate',
            name='category',
            field=models.CharField(
                choices=[
                    ('auth', 'Authentication'),
                    ('billing', 'Billing & Subscription'),
                    ('support', 'Support'),
                    ('notification', 'Notification'),
                    ('marketing', 'Marketing'),
                    ('system', 'System'),
                    ('hr', 'Human Resources'),
                ],
                default='notification',
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='emailtemplate',
            name='id',
            field=models.BigAutoField(
                auto_created=True, primary_key=True,
                serialize=False, verbose_name='ID',
            ),
        ),
    ]
