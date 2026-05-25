"""Backfill Approval.organization from the requester's primary MDA."""
from django.db import migrations


def forwards(apps, schema_editor):
    Approval = apps.get_model('workflow', 'Approval')
    try:
        UserOrganization = apps.get_model('core', 'UserOrganization')
    except LookupError:
        return

    # Build a {user_id: organization_id} map from the first active membership.
    user_to_org = {}
    for uo in UserOrganization.objects.filter(is_active=True).order_by('user_id', 'pk'):
        user_to_org.setdefault(uo.user_id, uo.organization_id)

    qs = Approval.objects.filter(organization__isnull=True).exclude(requested_by__isnull=True)
    for approval in qs.iterator():
        org_id = user_to_org.get(approval.requested_by_id)
        if org_id:
            Approval.objects.filter(pk=approval.pk).update(organization_id=org_id)


def reverse(apps, schema_editor):
    # No-op: backfill is non-destructive.
    return


class Migration(migrations.Migration):
    dependencies = [
        ('workflow', '0011_approval_organization'),
    ]
    operations = [
        migrations.RunPython(forwards, reverse),
    ]
