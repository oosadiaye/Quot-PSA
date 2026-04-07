"""
Service Minimum Viable Test Suite
====================================
Covers: ServiceAsset, Technician, ServiceTicket model CRUD;
Technician.active_tickets property; ticket status transitions.

Run with:
    python manage.py test service --verbosity=2
"""
from django_tenants.test.cases import TenantTestCase


# ---------------------------------------------------------------------------
# ServiceAsset model
# ---------------------------------------------------------------------------

class ServiceAssetModelTests(TenantTestCase):
    """CRUD tests for service.ServiceAsset."""

    def test_create_asset(self):
        from service.models import ServiceAsset
        asset = ServiceAsset.objects.create(
            name='Laptop Dell XPS', serial_number='SN-DELL-001',
        )
        self.assertEqual(asset.name, 'Laptop Dell XPS')
        self.assertEqual(asset.serial_number, 'SN-DELL-001')

    def test_asset_serial_unique(self):
        from service.models import ServiceAsset
        from django.db import IntegrityError
        ServiceAsset.objects.create(name='Asset A', serial_number='SN-DUP')
        with self.assertRaises(IntegrityError):
            ServiceAsset.objects.create(name='Asset B', serial_number='SN-DUP')

    def test_asset_str(self):
        from service.models import ServiceAsset
        asset = ServiceAsset.objects.create(name='Printer HP', serial_number='SN-HP-002')
        self.assertIn('SN-HP-002', str(asset))


# ---------------------------------------------------------------------------
# Technician model
# ---------------------------------------------------------------------------

class TechnicianModelTests(TenantTestCase):
    """CRUD tests for service.Technician."""

    def test_create_technician(self):
        from service.models import Technician
        tech = Technician.objects.create(
            name='John Doe',
            employee_code='TECH001',
            email='john@example.com',
            phone='+1234567890',
        )
        self.assertEqual(tech.name, 'John Doe')
        self.assertTrue(tech.is_active)
        self.assertTrue(tech.is_available)

    def test_technician_str(self):
        from service.models import Technician
        tech = Technician.objects.create(
            name='Jane Smith', employee_code='TECH002',
            email='jane@example.com', phone='+0987654321',
        )
        self.assertIn('TECH002', str(tech))

    def test_employee_code_unique(self):
        from service.models import Technician
        from django.db import IntegrityError
        Technician.objects.create(
            name='Tech 1', employee_code='TC-DUP',
            email='t1@example.com', phone='123',
        )
        with self.assertRaises(IntegrityError):
            Technician.objects.create(
                name='Tech 2', employee_code='TC-DUP',
                email='t2@example.com', phone='456',
            )

    def test_active_tickets_property_empty(self):
        """active_tickets returns 0 when no tickets assigned."""
        from service.models import Technician
        tech = Technician.objects.create(
            name='Free Tech', employee_code='TECH-FREE',
            email='free@example.com', phone='000',
        )
        self.assertEqual(tech.active_tickets, 0)


# ---------------------------------------------------------------------------
# ServiceTicket model
# ---------------------------------------------------------------------------

class ServiceTicketModelTests(TenantTestCase):
    """CRUD tests for service.ServiceTicket."""

    def _make_ticket(self, **kwargs):
        from service.models import ServiceTicket
        defaults = dict(
            ticket_number=f'TKT-{ServiceTicket.objects.count() + 1:04d}',
            subject='Test Issue',
            description='Description of the test issue.',
        )
        defaults.update(kwargs)
        return ServiceTicket.objects.create(**defaults)

    def test_create_ticket(self):
        ticket = self._make_ticket()
        self.assertEqual(ticket.status, 'Open')
        self.assertEqual(ticket.priority, 'Medium')

    def test_ticket_number_unique(self):
        from django.db import IntegrityError
        self._make_ticket(ticket_number='TKT-DUP')
        with self.assertRaises(IntegrityError):
            self._make_ticket(ticket_number='TKT-DUP')

    def test_ticket_optional_fields_null(self):
        ticket = self._make_ticket()
        self.assertIsNone(ticket.asset)
        self.assertIsNone(ticket.technician)
        self.assertIsNone(ticket.due_date)
        self.assertIsNone(ticket.service_revenue_account)
        self.assertIsNone(ticket.service_expense_account)

    def test_ticket_status_transition_to_in_progress(self):
        ticket = self._make_ticket()
        ticket.status = 'In Progress'
        ticket.save()
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'In Progress')

    def test_ticket_priority_choices(self):
        """All defined priority values can be stored."""
        for prio in ('Low', 'Medium', 'High', 'Critical'):
            ticket = self._make_ticket(priority=prio)
            self.assertEqual(ticket.priority, prio)
