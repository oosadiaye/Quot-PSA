"""Setup wizard API endpoints for tenant onboarding."""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def setup_profile(request):
    """Get or update the tenant's setup profile.

    GET  — returns the current profile (creates one if missing)
    PUT  — partial update of profile fields + optional step progression
    """
    from core.models import TenantSetupProfile

    profile = TenantSetupProfile.objects.first()
    if not profile:
        profile = TenantSetupProfile.objects.create()

    if request.method == 'GET':
        return Response(_serialize_profile(profile))

    # PUT — partial update
    data = request.data
    updatable_fields = [
        'company_name', 'company_email', 'company_phone', 'company_address',
        'company_city', 'company_state', 'company_country', 'company_website',
        'tax_id', 'registration_number', 'fiscal_year_start', 'default_currency',
        'timezone', 'business_category', 'employee_count_range', 'annual_revenue_range',
    ]

    for field in updatable_fields:
        if field in data:
            setattr(profile, field, data[field])

    # Step progression
    if 'current_step' in data:
        profile.current_step = int(data['current_step'])

    if 'completed_step' in data:
        step = int(data['completed_step'])
        if step not in profile.completed_steps:
            profile.completed_steps = [*profile.completed_steps, step]

    if data.get('setup_completed'):
        profile.setup_completed = True

    profile.save()

    logger.info('Setup profile updated for user=%s', request.user.pk)
    return Response(_serialize_profile(profile))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_setup(request):
    """Mark setup as complete."""
    from core.models import TenantSetupProfile

    profile = TenantSetupProfile.objects.first()
    if not profile:
        return Response({'error': 'No setup profile found'}, status=status.HTTP_404_NOT_FOUND)

    profile.setup_completed = True
    profile.save(update_fields=['setup_completed'])

    return Response({'message': 'Setup completed successfully', 'setup_completed': True})


def _serialize_profile(profile):
    return {
        'id': profile.id,
        'setup_completed': profile.setup_completed,
        'current_step': profile.current_step,
        'completed_steps': profile.completed_steps,
        'company_name': profile.company_name,
        'company_email': profile.company_email,
        'company_phone': profile.company_phone,
        'company_address': profile.company_address,
        'company_city': profile.company_city,
        'company_state': profile.company_state,
        'company_country': profile.company_country,
        'company_website': profile.company_website,
        'tax_id': profile.tax_id,
        'registration_number': profile.registration_number,
        'fiscal_year_start': profile.fiscal_year_start,
        'default_currency': profile.default_currency,
        'timezone': profile.timezone,
        'business_category': profile.business_category,
        'employee_count_range': profile.employee_count_range,
        'annual_revenue_range': profile.annual_revenue_range,
    }
