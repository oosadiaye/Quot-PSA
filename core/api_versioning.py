from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.versioning import URLPathVersioning


class APIVersionMixin:
    """
    Mixin to enforce API versioning and provide version-aware behavior
    """

    def get_versioned_serializer(self, serializer_class, *args, **kwargs):
        """Get serializer with version-specific fields"""
        version = self.request.parser_context.get('kwargs', {}).get('version', 'v1')

        # Remove fields that are deprecated in current version
        deprecated_fields = {
            'v1': [],  # No deprecated fields in v1
            'v2': ['old_field_1', 'old_field_2'],  # Fields deprecated in v2
        }

        if version in deprecated_fields:
            # Filter out deprecated fields from Meta.fields
            if hasattr(serializer_class.Meta, 'fields'):
                original_fields = list(serializer_class.Meta.fields)
                for field in deprecated_fields[version]:
                    if field in original_fields:
                        original_fields.remove(field)
                serializer_class.Meta.fields = tuple(original_fields)

        return serializer_class(*args, **kwargs)

    def get_response_with_version(self, data, version=None):
        """Wrap response with version info"""
        if version is None:
            version = 'v1'

        return {
            'data': data,
            'version': version,
            'timestamp': timezone.now().isoformat()
        }


class VersionedAPIView(APIView):
    """
    Base class for versioned API views
    """
    versioning_class = URLPathVersioning

    def get_version(self):
        return self.request.version

    def get_response_with_version(self, data):
        return {
            'data': data,
            'version': self.get_version(),
            'timestamp': timezone.now().isoformat()
        }

    def versioned_response(self, data, status_code=status.HTTP_200_OK):
        """Create a versioned response"""
        return Response(
            self.get_response_with_version(data),
            status=status_code
        )


def deprecated_field(field_name, removed_in_version='v3'):
    """
    Decorator to mark fields as deprecated
    Usage:
        @deprecated_field('old_field', 'v2')
        class MySerializer(ModelSerializer):
            ...
    """
    def decorator(serializer_class):
        original_to_representation = getattr(serializer_class, 'to_representation', None)

        def to_representation(self, instance):
            data = original_to_representation(instance) if original_to_representation else {}
            # Remove deprecated field
            if field_name in data:
                del data[field_name]
            return data

        serializer_class.to_representation = to_representation
        return serializer_class

    return decorator


class VersionAwareViewSetMixin:
    """
    Mixin to add versioning awareness to ViewSets
    """

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)

        # Add version metadata
        version = self.request.version if hasattr(self.request, 'version') else 'v1'
        serializer.version = version

        return serializer

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        # Add version header
        version = request.version if hasattr(request, 'version') else 'v1'
        response['X-API-Version'] = version

        return response
