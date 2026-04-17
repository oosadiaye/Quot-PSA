"""Stub app config — production module deleted for Quot PSE public sector.
Kept only for migration history compatibility."""
from django.apps import AppConfig

class ProductionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'production'
    verbose_name = 'Production (Deprecated — Public Sector)'
