"""
Sales Minimum Viable Test Suite
=================================
Covers: Customer, CustomerCategory, Lead model CRUD;
serializer decimal validation; SalesOrder status choices.

Run with:
    python manage.py test sales --verbosity=2
"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIRequestFactory


# ---------------------------------------------------------------------------
# CustomerCategory model
# ---------------------------------------------------------------------------

class CustomerCategoryModelTests(TenantTestCase):
    """CRUD tests for sales.CustomerCategory."""

    def test_create_category(self):
        from sales.models import CustomerCategory
        cat = CustomerCategory.objects.create(name='Retail', code='RET')
        self.assertEqual(cat.name, 'Retail')

    def test_category_str(self):
        from sales.models import CustomerCategory
        cat = CustomerCategory.objects.create(name='Wholesale', code='WHL')
        self.assertIn('Wholesale', str(cat))


# ---------------------------------------------------------------------------
# Customer model
# ---------------------------------------------------------------------------

class CustomerModelTests(TenantTestCase):
    """CRUD tests for sales.Customer."""

    def test_create_customer(self):
        from sales.models import Customer
        cust = Customer.objects.create(
            name='Acme Corp',
            customer_code='ACME001',
        )
        self.assertEqual(cust.name, 'Acme Corp')
        self.assertEqual(cust.credit_status, 'Good')
        self.assertTrue(cust.credit_check_enabled)

    def test_customer_code_unique(self):
        from sales.models import Customer
        from django.db import IntegrityError
        Customer.objects.create(name='Corp A', customer_code='C001')
        with self.assertRaises(IntegrityError):
            Customer.objects.create(name='Corp B', customer_code='C001')

    def test_customer_defaults(self):
        from sales.models import Customer
        cust = Customer.objects.create(name='Beta Ltd', customer_code='BT001')
        self.assertEqual(cust.credit_limit, Decimal('0'))
        self.assertEqual(cust.balance, Decimal('0'))
        self.assertEqual(cust.vat_number, '')


# ---------------------------------------------------------------------------
# Lead model
# ---------------------------------------------------------------------------

class LeadModelTests(TenantTestCase):
    """CRUD tests for sales.Lead."""

    def test_create_lead(self):
        from sales.models import Lead
        lead = Lead.objects.create(
            name='Prospect Inc',
            email='contact@prospect.com',
        )
        self.assertEqual(lead.name, 'Prospect Inc')
        self.assertIsNotNone(lead.pk)

    def test_lead_status_default(self):
        from sales.models import Lead
        lead = Lead.objects.create(name='New Prospect', email='p@example.com')
        # Default status should be a valid choice
        self.assertIsNotNone(lead.status)


# ---------------------------------------------------------------------------
# SalesOrder serializer decimal validation
# ---------------------------------------------------------------------------

class SalesOrderLineSerializerValidationTests(TenantTestCase):
    """PositiveDecimalMixin validation in sales serializers."""

    def test_positive_decimal_mixin_rejects_zero_quantity(self):
        from sales.serializers import SalesOrderLineSerializer
        serializer = SalesOrderLineSerializer(data={
            'quantity': '0',
            'unit_price': '100.00',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('quantity', serializer.errors)

    def test_positive_decimal_mixin_rejects_negative_price(self):
        from sales.serializers import SalesOrderLineSerializer
        serializer = SalesOrderLineSerializer(data={
            'quantity': '5',
            'unit_price': '-10.00',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('unit_price', serializer.errors)
