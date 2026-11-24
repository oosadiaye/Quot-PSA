"""Assert every ViewSet belonging to a gated module declares ``module_key``.

FUTURE_MODULES §2: wire this into CI so a new endpoint cannot silently
escape the gate.  A ViewSet whose app label matches a registered module
but lacks ``module_key`` is a compliance violation.

Exit codes:
    0  — all gated ViewSets are accounted for.
    1  — violations found (prints each one).

Usage::

    python manage.py audit_module_gating
    python manage.py audit_module_gating --strict   # also warn on legacy
"""

from __future__ import annotations

import importlib
import inspect
import sys

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from rest_framework import viewsets

from tenants.models import AVAILABLE_MODULES


# Map Django app labels to their canonical module key.
# Only apps whose label appears here are checked.  Apps not listed are
# treated as cross-cutting infrastructure (core, tenants, superadmin, etc.)
_APP_LABEL_TO_MODULE: dict[str, str] = {}

for _key, _title, _desc in AVAILABLE_MODULES:
    # The convention is that the app label equals the module key.  If a
    # module's code lives inside a differently-named app, add an explicit
    # mapping here.
    _APP_LABEL_TO_MODULE[_key] = _key

# Override / extend for known mismatches:
_APP_LABEL_TO_MODULE.update({
    # 'reporting' views live inside the accounting app
    'reporting': 'accounting',
    # 'treasury' views live inside the accounting app
    'treasury': 'accounting',
    # 'revenue' views live inside the accounting app
    'revenue': 'accounting',
})


def _discover_viewsets() -> list[tuple[str, type]]:
    """Walk every installed app's ``views`` package and collect ViewSet classes."""
    found: list[tuple[str, type]] = []

    for app_config in apps.get_app_configs():
        label = app_config.label
        if label not in _APP_LABEL_TO_MODULE:
            continue

        try:
            views_module = importlib.import_module(f'{app_config.name}.views')
        except ImportError:
            # App has no views module — fine, nothing to check.
            continue

        # Handle both flat views.py and views/ package.
        if hasattr(views_module, '__path__'):
            # It's a package — walk its sub-modules.
            import pkgutil
            for _importer, modname, _ispkg in pkgutil.walk_packages(
                views_module.__path__, prefix=views_module.__name__ + '.',
            ):
                try:
                    sub = importlib.import_module(modname)
                except ImportError:
                    continue
                for _name, obj in inspect.getmembers(sub, inspect.isclass):
                    if (
                        issubclass(obj, viewsets.ViewSetMixin)
                        and obj is not viewsets.ViewSetMixin
                        and not inspect.isabstract(obj)
                    ):
                        found.append((modname, obj))
        else:
            for _name, obj in inspect.getmembers(views_module, inspect.isclass):
                if (
                    issubclass(obj, viewsets.ViewSetMixin)
                    and obj is not viewsets.ViewSetMixin
                    and not inspect.isabstract(obj)
                ):
                    found.append((views_module.__name__, obj))

    return found


class Command(BaseCommand):
    help = (
        'Audit that every ViewSet belonging to a gated module declares '
        'module_key.  Fails if any gated ViewSet is missing the attribute.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Also warn about legacy modules that lack module_key (informational).',
        )

    def handle(self, *args, strict=False, **options):
        viewsets_found = _discover_viewsets()
        violations: list[str] = []
        warnings: list[str] = []

        for module_path, vs_cls in viewsets_found:
            module_key = getattr(vs_cls, 'module_key', None)
            # Determine which module this ViewSet belongs to.
            app_label = vs_cls.__module__.split('.')[0]
            owning_module = _APP_LABEL_TO_MODULE.get(app_label, app_label)

            if module_key is None:
                msg = (
                    f'  VIOLATION: {vs_cls.__name__} '
                    f'({module_path}) — app "{app_label}" belongs to '
                    f'module "{owning_module}" but has no module_key'
                )
                if owning_module in _LEGACY_KEYS and not strict:
                    warnings.append(msg)
                else:
                    violations.append(msg)
            elif module_key != owning_module:
                msg = (
                    f'  MISMATCH: {vs_cls.__name__} '
                    f'({module_path}) — module_key="{module_key}" '
                    f'but app label suggests "{owning_module}"'
                )
                violations.append(msg)

        if warnings:
            self.stdout.write(self.style.WARNING(
                f'\n{len(warnings)} legacy module ViewSet(s) without module_key '
                '(informational — legacy modules fail open):\n'
            ))
            for w in warnings:
                self.stdout.write(self.style.WARNING(w))

        if violations:
            self.stdout.write(self.style.ERROR(
                f'\n{len(violations)} violation(s) found:\n'
            ))
            for v in violations:
                self.stdout.write(self.style.ERROR(v))
            self.stderr.write(
                '\nFix: add module_key = "<key>" to each flagged ViewSet class.\n'
                'See FUTURE_MODULES.md §2 for the specification.\n'
            )
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS(
            f'\nOK — {len(viewsets_found)} gated ViewSet(s) checked, '
            f'{len(violations)} violation(s), {len(warnings)} warning(s).\n'
        ))


# Legacy module keys — these are expected to lack module_key during the
# migration period and are only flagged in --strict mode.
_LEGACY_KEYS = frozenset({
    'dimensions', 'accounting', 'budget', 'treasury', 'revenue',
    'procurement', 'contracts', 'inventory', 'hrm', 'workflow',
    'reporting', 'audit',
})
