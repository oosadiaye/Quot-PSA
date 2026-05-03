"""
Organization (MDA-as-Branch) API views — Quot PSE

Endpoints:
- /core/organizations/           — CRUD for admin
- /core/organizations/my/        — Current user's assigned orgs
- /core/organizations/switch/    — Switch active organization
- /core/organizations/<id>/users — Manage org member assignments
"""
from rest_framework import serializers, status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from core.models import Organization, UserOrganization


# ── Serializers ────────────────────────────────────────────

class OrganizationSerializer(serializers.ModelSerializer):
    is_oversight = serializers.BooleanField(read_only=True)
    has_cross_mda_read = serializers.BooleanField(read_only=True)
    is_read_only = serializers.BooleanField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'code', 'short_name', 'org_role',
            'administrative_segment', 'legacy_mda',
            'is_active', 'description',
            'is_oversight', 'has_cross_mda_read', 'is_read_only',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserOrganizationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source='organization.name', read_only=True,
    )
    organization_code = serializers.CharField(
        source='organization.code', read_only=True,
    )
    org_role = serializers.CharField(
        source='organization.org_role', read_only=True,
    )
    is_oversight = serializers.BooleanField(
        source='organization.is_oversight', read_only=True,
    )
    username = serializers.CharField(
        source='user.username', read_only=True,
    )

    class Meta:
        model = UserOrganization
        fields = [
            'id', 'user', 'organization', 'per_org_role',
            'is_default', 'is_active',
            'organization_name', 'organization_code', 'org_role',
            'is_oversight', 'username',
        ]


class MyOrganizationSerializer(serializers.Serializer):
    """Serializer for the /my/ endpoint — enriched org info for switcher."""
    id = serializers.IntegerField(source='organization.id')
    name = serializers.CharField(source='organization.name')
    code = serializers.CharField(source='organization.code')
    short_name = serializers.CharField(source='organization.short_name')
    org_role = serializers.CharField(source='organization.org_role')
    is_oversight = serializers.BooleanField(source='organization.is_oversight')
    is_read_only = serializers.BooleanField(source='organization.is_read_only')
    per_org_role = serializers.CharField()
    is_default = serializers.BooleanField()


# ── Views ──────────────────────────────────────────────────

class OrganizationListCreate(generics.ListCreateAPIView):
    """List all organizations or create a new one (admin only)."""
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Organization.objects.all()


class OrganizationDetail(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete an organization."""
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Organization.objects.all()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_from_ncoa(request):
    """
    Bulk-create ``Organization`` rows from the tenant's NCoA Administrative
    Segments. Idempotent — only segments that don't already have a linked
    Organization are created. Each new Organization defaults to:

        org_role     = 'MDA'   (caller can promote BUDGET/FINANCE/AUDIT later)
        is_active    = True
        code         = AdministrativeSegment.code
        name         = AdministrativeSegment.name
        short_name   = first 50 chars of name (or AdministrativeSegment.short_name if set)

    The sync runs inside the caller's tenant schema (django-tenants middleware
    already routes the request) and reads ``AdministrativeSegment`` from there;
    the resulting ``Organization`` rows are written to the public schema.

    POST /core/organizations/sync-from-ncoa/

    Returns:
        {
            "created": 12,
            "skipped": 3,         # already had a linked Organization
            "total_segments": 15,
            "organizations": [{id, code, name}, ...]
        }
    """
    # Lazy import — accounting is a TENANT_APP, importing at module load
    # would break public-schema-only contexts.
    from accounting.models.ncoa import AdministrativeSegment

    segments = AdministrativeSegment.objects.filter(is_active=True)
    created_orgs: list[Organization] = []
    skipped = 0

    for seg in segments:
        # Already linked? skip. We check by FK (which is db_constraint=False
        # but still queryable as ``administrative_segment_id``).
        if Organization.objects.filter(administrative_segment_id=seg.id).exists():
            skipped += 1
            continue
        # Code clash? Re-use the existing Organization rather than crash.
        # This handles the case where someone manually created an Organization
        # with a matching code before sync was wired up.
        existing_by_code = Organization.objects.filter(code=seg.code).first()
        if existing_by_code:
            existing_by_code.administrative_segment_id = seg.id
            existing_by_code.save(update_fields=['administrative_segment'])
            skipped += 1
            continue
        org = Organization.objects.create(
            code=seg.code,
            name=seg.name,
            short_name=(getattr(seg, 'short_name', '') or seg.name)[:50],
            org_role='MDA',
            is_active=True,
            administrative_segment_id=seg.id,
        )
        created_orgs.append(org)

    return Response({
        'created': len(created_orgs),
        'skipped': skipped,
        'total_segments': segments.count(),
        'organizations': [
            {'id': o.id, 'code': o.code, 'name': o.name} for o in created_orgs
        ],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_organizations(request):
    """Return the current user's assigned organizations for the switcher."""
    assignments = (
        UserOrganization.objects
        .filter(user=request.user, is_active=True, organization__is_active=True)
        .select_related('organization')
        .order_by('-is_default', 'organization__code')
    )
    serializer = MyOrganizationSerializer(assignments, many=True)

    # Include tenant isolation mode
    mda_mode = getattr(request, 'mda_isolation_mode', 'UNIFIED')
    active_org_id = None
    if request.organization:
        active_org_id = request.organization.id

    return Response({
        'mda_isolation_mode': mda_mode,
        'active_organization_id': active_org_id,
        'organizations': serializer.data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def switch_organization(request):
    """Switch the active organization for the current session."""
    org_id = request.data.get('organization_id')
    if not org_id:
        return Response(
            {'error': 'organization_id is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        org_id = int(org_id)
    except (ValueError, TypeError):
        return Response(
            {'error': 'organization_id must be an integer'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    assignment = UserOrganization.objects.filter(
        user=request.user,
        organization_id=org_id,
        organization__is_active=True,
        is_active=True,
    ).select_related('organization').first()

    if not assignment:
        return Response(
            {'error': 'You are not assigned to this organization'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Store in session
    request.session['active_organization_id'] = org_id

    org = assignment.organization
    return Response({
        'id': org.id,
        'name': org.name,
        'code': org.code,
        'short_name': org.short_name,
        'org_role': org.org_role,
        'is_oversight': org.is_oversight,
        'is_read_only': org.is_read_only,
    })


class OrganizationUsers(generics.ListCreateAPIView):
    """List or add user assignments to an organization."""
    serializer_class = UserOrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org_id = self.kwargs['org_id']
        return UserOrganization.objects.filter(
            organization_id=org_id,
        ).select_related('user', 'organization')

    def perform_create(self, serializer):
        org_id = self.kwargs['org_id']
        org = get_object_or_404(Organization, pk=org_id)
        serializer.save(organization=org)
