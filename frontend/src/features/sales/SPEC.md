# Sales Module Specification

> **Project:** DTSG ERP
> **Module:** Sales Management
> **Version:** 1.0.0
> **Last Updated:** 2026-03-01

---

## 1. Module Overview

The Sales Management module provides comprehensive sales cycle management including CRM, quotations, sales orders, delivery notes, automated invoicing, and customer credit management.

### Key Features
- CRM Lite - Lead and opportunity management
- Quotations - Sales quotes with conversion to orders
- Sales Orders - Order processing and fulfillment
- Delivery Notes - Goods delivery tracking
- Automated Invoicing - Convert orders to invoices
- Customer Credit Management - Credit limits and tracking

---

## 2. File Structure

```
frontend/src/features/sales/
├── SalesDashboard.tsx              # Main sales dashboard
├── layout/
│   └── SalesLayout.tsx           # Layout wrapper
├── pages/
│   ├── CRMLite.tsx              # CRM - Leads & Opportunities
│   ├── CustomerForm.tsx          # Customer create/edit
│   ├── Quotations.tsx            # Quotations list
│   ├── SalesOrders.tsx           # Sales orders list
│   ├── DeliveryNotesList.tsx    # Delivery notes
│   ├── AutomatedInvoicing.tsx    # Invoice automation
│   └── CustomerCreditLimits.tsx # Credit limits
├── hooks/
│   └── useSales.ts              # All sales API hooks
└── SPEC.md                      # This file
```

---

## 3. Pages/Components

### 3.1 SalesDashboard
**Route:** `/sales/dashboard`

Features:
- Summary cards: Total Sales, Orders, Quotations, Customers
- Quick action buttons
- Recent activities
- Sales pipeline overview

### 3.2 CRMLite (Leads & Opportunities)
**Route:** `/sales/crm`

Features:
- Tabs: Leads, Opportunities, Customers
- Lead management (create, update, convert)
- Opportunity pipeline
- Customer directory
- Status tracking (New, Contacted, Qualified, Won, Lost)

**Lead Fields:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Lead name |
| company | string | Company name |
| email | string | Email address |
| phone | string | Phone number |
| source | select | Lead source (Website, Referral, Campaign, etc.) |
| status | select | Status (New, Contacted, Qualified, Converted, Lost) |
| assigned_to | FK | Sales rep |
| notes | text | Notes |

**Opportunity Fields:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Opportunity name |
| customer | FK | Customer |
| lead | FK | Related lead |
| value | decimal | Opportunity value |
| stage | select | Stage (Prospecting, Qualification, Proposal, Negotiation, Closed Won, Closed Lost) |
| probability | number | Win probability % |
| expected_close | date | Expected close date |
| assigned_to | FK | Sales rep |

### 3.3 CustomerForm
**Route:** `/sales/customer/new` | `/sales/customer/:id`

**Customer Fields:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Customer name * |
| code | string | Customer code |
| customer_type | select | Type (Business, Individual, Government, Non-Profit) |
| email | string | Email address |
| phone | string | Phone number |
| address | string | Street address |
| city | string | City |
| state | string | State/Province |
| postal_code | string | Postal code |
| country | string | Country |
| tax_id | string | Tax ID / VAT number |
| credit_limit | number | Credit limit |
| payment_terms | select | Terms (NET0, NET15, NET30, NET45, NET60) |
| currency | select | Default currency |
| is_active | boolean | Active status |

### 3.4 Quotations
**Route:** `/sales/quotations`

Features:
- List all quotations with status
- Create quotation from customer
- Convert quotation to sales order
- Validity period tracking
- Send to customer

**Quotation Fields:**
| Field | Type | Description |
|-------|------|-------------|
| quotation_number | string | Auto-generated |
| customer | FK | Customer * |
| quotation_date | date | Quote date |
| valid_until | date | Expiry date |
| status | select | Draft, Sent, Accepted, Rejected, Expired, Converted |
| sales_person | FK | Sales representative |
| terms | text | Terms & conditions |
| notes | text | Internal notes |
| subtotal | decimal | Calculated |
| tax_amount | decimal | Tax |
| total | decimal | Grand total |

**Line Items:**
| Field | Type | Description |
|-------|------|-------------|
| item | FK | Product/Service |
| description | string | Line description |
| quantity | number | Qty |
| unit_price | decimal | Price per unit |
| discount | decimal | Discount % |
| tax | FK | Tax code |
| amount | decimal | Line total |

### 3.5 SalesOrders
**Route:** `/sales/orders`

Features:
- List all sales orders
- Create order from quotation or manually
- Post order (create journal entry)
- Convert to invoice
- Track fulfillment status

**Sales Order Fields:**
| Field | Type | Description |
|-------|------|-------------|
| order_number | string | Auto-generated |
| customer | FK | Customer * |
| quotation | FK | Source quotation |
| order_date | date | Order date |
| delivery_date | date | Expected delivery |
| status | select | Draft, Pending, Approved, Rejected, Fulfilled, Cancelled |
| sales_person | FK | Sales rep |
| payment_terms | select | NET0, NET15, NET30, etc. |
| currency | select | Currency |

### 3.6 DeliveryNotesList
**Route:** `/sales/delivery-notes`

Features:
- Create delivery note from sales order
- Track delivery status
- Record recipient information
- Vehicle and driver tracking

**Delivery Note Fields:**
| Field | Type | Description |
|-------|------|-------------|
| delivery_number | string | Auto-generated |
| sales_order | FK | Source order * |
| customer | FK | Customer |
| delivery_date | date | Delivery date |
| recipient_name | string | Recipient name |
| recipient_contact | string | Contact phone |
| vehicle_number | string | Vehicle/plate number |
| driver_name | string | Driver name |
| status | select | Draft, Issued, Received, Returned, Cancelled |
| notes | text | Notes |

### 3.7 AutomatedInvoicing
**Route:** `/sales/invoicing`

Features:
- Auto-generate invoices from delivered orders
- Invoice templates
- Send to customer
- Track payment status
- Partial invoicing support

### 3.8 CustomerCreditLimits
**Route:** `/sales/credit-limits`

Features:
- Set credit limits per customer
- Track credit usage
- Alert on credit exceeded
- Payment history

---

## 4. API Endpoints

### Customers
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sales/customers/` | GET, POST | List/Create customers |
| `/api/sales/customers/:id/` | GET, PATCH, DELETE | CRUD operations |

### Leads
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sales/leads/` | GET, POST | List/Create leads |
| `/api/sales/leads/:id/` | GET, PATCH, DELETE | CRUD operations |

### Opportunities
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sales/opportunities/` | GET, POST | List/Create opportunities |
| `/api/sales/opportunities/:id/` | GET, PATCH, DELETE | CRUD operations |

### Quotations
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sales/quotations/` | GET, POST | List/Create quotations |
| `/api/sales/quotations/:id/` | GET, PATCH, DELETE | CRUD operations |
| `/api/sales/quotations/:id/convert_to_order/` | POST | Convert to order |

### Sales Orders
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sales/orders/` | GET, POST | List/Create orders |
| `/api/sales/orders/:id/` | GET, PATCH, DELETE | CRUD operations |
| `/api/sales/orders/:id/post_order/` | POST | Post to GL |
| `/api/sales/orders/:id/convert_to_invoice/` | POST | Convert to invoice |

### Delivery Notes
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sales/delivery-notes/` | GET, POST | List/Create delivery notes |
| `/api/sales/delivery-notes/:id/` | GET, PATCH, DELETE | CRUD operations |

### Sales Invoices
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sales/invoices/` | GET, POST | List/Create invoices |
| `/api/sales/invoices/:id/` | GET, PATCH, DELETE | CRUD operations |
| `/api/sales/invoices/:id/post_invoice/` | POST | Post to GL |

---

## 5. Frontend Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/sales/dashboard` | SalesDashboard | Main dashboard |
| `/sales` | SalesOrders | Default sales view |
| `/sales/crm` | CRMLite | CRM & Leads |
| `/sales/customer/new` | CustomerForm | Create customer |
| `/sales/customer/:id` | CustomerForm | Edit customer |
| `/sales/quotations` | Quotations | Quotations list |
| `/sales/orders` | SalesOrders | Sales orders |
| `/sales/delivery-notes` | DeliveryNotesList | Delivery notes |
| `/sales/invoicing` | AutomatedInvoicing | Invoice automation |
| `/sales/credit-limits` | CustomerCreditLimits | Credit limits |

---

## 6. Custom Hooks

### Query Hooks
| Hook | Returns |
|------|---------|
| `useCustomers(filters)` | Customer list |
| `useCustomer(id)` | Single customer |
| `useLeads(filters)` | Lead list |
| `useOpportunities(filters)` | Opportunity list |
| `useQuotations(filters)` | Quotation list |
| `useQuotation(id)` | Single quotation |
| `useSalesOrders(filters)` | Order list |
| `useSalesOrder(id)` | Single order |
| `useDeliveryNotes(filters)` | Delivery note list |
| `useSalesInvoices(filters)` | Invoice list |

### Mutation Hooks
| Hook | Purpose |
|------|---------|
| `useCreateCustomer()` | Create customer |
| `useUpdateCustomer()` | Update customer |
| `useDeleteCustomer()` | Delete customer |
| `useUpdateCustomerCreditLimit()` | Update credit limit |
| `useCreateLead()` | Create lead |
| `useUpdateLead()` | Update lead |
| `useCreateOpportunity()` | Create opportunity |
| `useUpdateOpportunity()` | Update opportunity |
| `useCreateQuotation()` | Create quotation |
| `useUpdateQuotation()` | Update quotation |
| `useDeleteQuotation()` | Delete quotation |
| `useConvertQuotationToOrder()` | Convert quote to order |
| `useCreateSalesOrder()` | Create order |
| `useUpdateSalesOrder()` | Update order |
| `useDeleteSalesOrder()` | Delete order |
| `usePostSalesOrder()` | Post order to GL |
| `useConvertOrderToInvoice()` | Convert order to invoice |
| `useCreateDeliveryNote()` | Create delivery note |
| `useUpdateDeliveryNote()` | Update delivery note |
| `useCreateSalesInvoice()` | Create invoice |
| `usePostSalesInvoice()` | Post invoice to GL |
| `useCreateFromQuotation()` | Create order from quotation |

---

## 7. Sidebar Menu Structure

```
Sales
├── CRM Lite (/sales/crm)
├── Quotations (/sales/quotations)
├── Sales Orders (/sales/orders)
├── Delivery Notes (/sales/delivery-notes)
├── Automated Invoicing (/sales/invoicing)
└── Credit Limits (/sales/credit-limits)
```

---

## 8. Order to Invoice Flow

```
Quotation → Sales Order → Delivery Note → Sales Invoice → Posted to GL
     ↓            ↓              ↓              ↓
  Accept     Approve        Issue         Post
```

---

## 9. Design System Compliance

All components follow the MASTER.md design system:
- Colors: CSS variables (--color-primary, --color-success, etc.)
- Typography: IBM Plex Sans
- Icons: Lucide React
- Spacing: Token system
- Dark mode: Supported

---

## 10. Status Definitions

### Lead Status
- **New** - Newly created lead
- **Contacted** - Initial contact made
- **Qualified** - Meets criteria
- **Converted** - Converted to customer
- **Lost** - Not pursuing

### Opportunity Stage
- **Prospecting** - Identifying potential
- **Qualification** - Assessing fit
- **Proposal** - Quote submitted
- **Negotiation** - Finalizing terms
- **Closed Won** - Deal won
- **Closed Lost** - Deal lost

### Quotation Status
- **Draft** - Not sent
- **Sent** - Delivered to customer
- **Accepted** - Customer accepted
- **Rejected** - Customer rejected
- **Expired** - Past validity
- **Converted** - Turned to order

### Sales Order Status
- **Draft** - Not approved
- **Pending** - Awaiting approval
- **Approved** - Ready for fulfillment
- **Rejected** - Not approved
- **Fulfilled** - Delivered
- **Cancelled** - Cancelled

### Delivery Note Status
- **Draft** - Not issued
- **Issued** - Out for delivery
- **Received** - Delivered to customer
- **Returned** - Goods returned
- **Cancelled** - Cancelled

---

*End of Specification*
