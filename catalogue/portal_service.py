"""A supplier proposes catalogue prices; the procurement office decides.

A supplier never edits the framework price list itself: prices bind the government, so a proposal waits until an approver
accepts it. Approval writes the price into the supplier's active catalogue and records it in the price history.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import CatalogueItem, CataloguePriceProposal, PriceHistory, SupplierCatalogue


class ProposalError(Exception):
    """A refusal a person can act on; the message is shown as it is."""


def current_items(vendor):
    """The prices this supplier has in force: its active catalogues' active lines."""
    return (CatalogueItem.objects.filter(catalogue__supplier=vendor, catalogue__status='active', is_active=True)
            .select_related('item', 'catalogue').order_by('item__name'))


@transaction.atomic
def propose(vendor, user, *, item, unit_price, specification: str = '') -> CataloguePriceProposal:
    """A supplier asks for a price, for one item, to go into its catalogue."""
    price = Decimal(str(unit_price))
    if price <= 0:
        raise ProposalError('A price must be more than zero.')
    if not item.is_active:
        raise ProposalError('That item is not currently bought by the government.')
    if CataloguePriceProposal.objects.filter(supplier=vendor, item=item, status='pending').exists():
        raise ProposalError('You already have a price waiting for approval on this item. Wait for it to be decided first.')
    in_force = current_items(vendor).filter(item=item).first()
    return CataloguePriceProposal.objects.create(
        supplier=vendor, item=item, proposed_price=price, specification=specification.strip(),
        current_price=in_force.unit_price if in_force else None, requested_by=user,
    )


def _supplier_catalogue(vendor) -> SupplierCatalogue:
    found = SupplierCatalogue.objects.filter(supplier=vendor, status='active').order_by('pk').first()
    return found or SupplierCatalogue.objects.create(name=f'{vendor.name} catalogue', supplier=vendor, status='active')


@transaction.atomic
def decide(proposal: CataloguePriceProposal, user, *, approve: bool, reason: str = '') -> CataloguePriceProposal:
    """Accept (the price goes into force and into the history) or reject (it does not) a proposal."""
    if proposal.status != 'pending':
        raise ProposalError(f'This proposal was already {proposal.status}.')
    if not approve and not reason.strip():
        raise ProposalError('Give a reason for rejecting a price, so the supplier knows what to change.')
    proposal.status = 'approved' if approve else 'rejected'
    proposal.decided_by, proposal.decided_at, proposal.reason = user, timezone.now(), reason.strip()
    proposal.save()
    if approve:
        today = timezone.localdate()
        line, _ = CatalogueItem.objects.get_or_create(catalogue=_supplier_catalogue(proposal.supplier), item=proposal.item)
        line.unit_price, line.price_effective_date, line.is_active = proposal.proposed_price, today, True
        if proposal.specification:
            line.specification = proposal.specification
        line.save()
        PriceHistory.objects.create(item=proposal.item, supplier=proposal.supplier, unit_price=proposal.proposed_price, effective_date=today)
    return proposal
