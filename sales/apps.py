"""Stub app config — sales module deleted for Quot PSE public sector.
Kept only for migration history compatibility."""
from django.apps import AppConfig

class SalesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sales'
    verbose_name = 'Sales (Deprecated — Public Sector)'
