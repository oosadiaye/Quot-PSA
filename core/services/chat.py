"""Team chat rules: who can talk to whom, who is online, what may be attached,
and the queries behind the widget.

Scope is one tenant: you can chat with the other active users of the tenant you
are working in, and with nobody else.

"Online" means the user has a live session (they are signed in) that was seen
recently. Signing out ends the session at once, so they drop to offline
immediately; closing the tab without signing out drops them after
``ONLINE_WINDOW``.
"""
from __future__ import annotations

import os
import re
from datetime import timedelta
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_tenants.utils import schema_context

#: Largest file that may be attached to a message.
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_BODY_CHARS = 4000
#: A signed-in user not seen for longer than this reads as offline (tab closed, device asleep).
ONLINE_WINDOW = timedelta(minutes=5)
#: Largest total of attachments one person may send in 24 hours (about 50 full-size files).
MAX_DAILY_ATTACHMENT_BYTES = 100 * 1024 * 1024
#: Files that can run, carry a script or macro, or open an active document on the recipient's machine are not
#: accepted at all. A blocklist can never be complete, so this covers what is actually dangerous in an office.
BLOCKED_EXTENSIONS = frozenset({
    # programs and installers
    'exe', 'msi', 'bat', 'cmd', 'com', 'scr', 'pif', 'dll', 'lnk', 'reg', 'jar', 'apk', 'app', 'dmg', 'pkg',
    'command', 'cpl', 'inf', 'msc', 'msp', 'jnlp', 'gadget', 'appref-ms', 'xll', 'iqy', 'scf', 'url',
    # scripts
    'js', 'mjs', 'jse', 'vbs', 'vbe', 'wsf', 'wsh', 'wsc', 'ps1', 'psm1', 'ps1xml', 'psc1', 'sh', 'py', 'pyw',
    'pyc', 'rb', 'pl', 'hta',
    # web pages and server-side code
    'html', 'htm', 'xhtml', 'xht', 'shtml', 'shtm', 'svg', 'xml', 'php', 'php3', 'php4', 'php5', 'php7',
    'phtml', 'phar', 'jsp', 'jspx', 'asp', 'aspx', 'cgi', 'swf',
    # macro-enabled Office documents and disk images / compiled help
    'docm', 'xlsm', 'pptm', 'dotm', 'chm', 'iso', 'img', 'vhd',
})
IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')


class ChatError(ValueError):
    """A message cannot be sent; the text is meant for the user."""


def display_name(user) -> str:
    return (user.get_full_name() or '').strip() or user.username


# ---- who is in this tenant, who is online --------------------------------------------------------------

def member_ids(tenant) -> set:
    """Ids of the active users who belong to ``tenant``."""
    from tenants.models import UserTenantRole
    with schema_context('public'):
        return set(UserTenantRole.objects.filter(tenant=tenant, is_active=True, user__is_active=True)
                   .values_list('user_id', flat=True))


def is_member(tenant, user_id) -> bool:
    from tenants.models import UserTenantRole
    with schema_context('public'):
        return UserTenantRole.objects.filter(
            tenant=tenant, user_id=user_id, is_active=True, user__is_active=True).exists()


def online_ids(user_ids: Iterable[int], now=None) -> set:
    """Of ``user_ids``, those signed in and seen within the window."""
    from core.models import UserSession
    now = now or timezone.now()
    with schema_context('public'):
        return set(UserSession.objects.filter(
            user_id__in=list(user_ids), is_active=True, last_activity__gte=now - ONLINE_WINDOW,
        ).values_list('user_id', flat=True))


# ---- attachments ------------------------------------------------------------------------------------------

def clean_filename(name: str) -> str:
    """The base name only, with anything awkward replaced, so it is safe to show and to put in a header."""
    base = os.path.basename((name or '').replace('\\', '/')).strip()
    base = re.sub(r'[^\w.\- ()\[\]]+', '_', base, flags=re.UNICODE)[:150].strip(' .')
    return base or 'file'


def validate_attachment(upload) -> None:
    """Raise ``ChatError`` unless the file is acceptable: not empty, at most 2 MB, and not an executable type."""
    if upload is None:
        return
    size = getattr(upload, 'size', 0) or 0
    if size <= 0:
        raise ChatError('That file is empty.')
    if size > MAX_ATTACHMENT_BYTES:
        raise ChatError('Files are limited to 2 MB. Choose a smaller file.')
    extension = os.path.splitext(clean_filename(upload.name))[1].lstrip('.').lower()
    if extension in BLOCKED_EXTENSIONS:
        raise ChatError(f'.{extension} files cannot be sent in chat.')


# ---- queries ----------------------------------------------------------------------------------------------

def contacts(user, tenant) -> list:
    """The tenant's other users, online first, each with their unread count and the last message exchanged."""
    from core.models import ChatMessage
    ids = member_ids(tenant) - {user.pk}
    if not ids:
        return []
    people = {u.pk: u for u in get_user_model().objects.filter(pk__in=ids)}
    online = online_ids(ids)
    unread = dict(ChatMessage.objects.filter(recipient=user, read_at__isnull=True, sender_id__in=ids)
                  .values_list('sender_id').annotate(n=Count('pk')))
    last = {}
    recent = (ChatMessage.objects.filter(Q(sender=user, recipient_id__in=ids) | Q(recipient=user, sender_id__in=ids))
              .order_by('-id')[:400])
    for message in recent:
        other = message.recipient_id if message.sender_id == user.pk else message.sender_id
        last.setdefault(other, message)
    rows = []
    for pk, person in people.items():
        message = last.get(pk)
        rows.append({
            'id': pk, 'name': display_name(person), 'username': person.username, 'online': pk in online,
            'unread': unread.get(pk, 0),
            'last_message': None if message is None else {
                'preview': (message.body or f'\U0001F4CE {message.attachment_name}')[:80],
                'at': message.created_at.isoformat(), 'mine': message.sender_id == user.pk,
            },
        })
    # Online first, then the most recent conversation, then by name (each sort is stable, so apply them in reverse).
    rows.sort(key=lambda r: r['name'].lower())
    rows.sort(key=lambda r: (r['last_message'] or {}).get('at', ''), reverse=True)
    rows.sort(key=lambda r: not r['online'])
    return rows


def summary(user, tenant) -> dict:
    """The two numbers the closed widget shows: unread messages and people online."""
    from core.models import ChatMessage
    ids = member_ids(tenant) - {user.pk}
    return {
        'unread_total': ChatMessage.objects.filter(recipient=user, read_at__isnull=True, sender_id__in=ids).count(),
        'online_count': len(online_ids(ids)) if ids else 0,
    }


def thread(user, other_id, *, after=0, limit=100, mark_read=False):
    """Messages between ``user`` and ``other_id`` newer than ``after``, oldest first (the newest ``limit``)."""
    from core.models import ChatMessage
    qs = ChatMessage.objects.filter(
        Q(sender=user, recipient_id=other_id) | Q(sender_id=other_id, recipient=user), id__gt=after)
    rows = list(qs.order_by('-id')[:limit])[::-1]
    if mark_read:
        ChatMessage.objects.filter(sender_id=other_id, recipient=user, read_at__isnull=True,
                                   id__in=[m.pk for m in rows]).update(read_at=timezone.now())
    return rows


def send(user, tenant, recipient_id, body, upload=None):
    """Create the message, or raise ``ChatError`` saying why not."""
    from core.models import ChatMessage
    if recipient_id == user.pk:
        raise ChatError('You cannot send a message to yourself.')
    if not is_member(tenant, recipient_id):
        raise ChatError('That person is not in this workspace.')
    body = body.strip() if isinstance(body, str) else ''
    if len(body) > MAX_BODY_CHARS:
        raise ChatError(f'Messages are limited to {MAX_BODY_CHARS} characters.')
    if not body and upload is None:
        raise ChatError('Write a message or attach a file.')
    validate_attachment(upload)
    if upload is not None:
        _enforce_daily_quota(user, upload.size)
    message = ChatMessage(sender=user, recipient_id=recipient_id, body=body)
    if upload is not None:
        message.attachment_name = clean_filename(upload.name)
        message.attachment_size = upload.size
        message.attachment_type = (getattr(upload, 'content_type', '') or '')[:100]
        message.attachment = upload
    try:
        message.save()
    except Exception:
        # The file is written before the row; if the row fails, do not leave the file orphaned on disk.
        if message.attachment and message.attachment.name:
            message.attachment.storage.delete(message.attachment.name)
        raise
    return message


def _enforce_daily_quota(user, incoming_bytes: int) -> None:
    """Refuse a file that would take this sender past their 24-hour attachment allowance."""
    from core.models import ChatMessage
    sent = (ChatMessage.objects.filter(sender=user, created_at__gte=timezone.now() - timedelta(hours=24))
            .aggregate(total=Sum('attachment_size'))['total'] or 0)
    if sent + incoming_bytes > MAX_DAILY_ATTACHMENT_BYTES:
        raise ChatError('You have reached the limit for files sent today. Try again tomorrow, or share it another way.')


def serialize(message, viewer) -> dict:
    attachment = None
    if message.attachment:
        attachment = {
            'name': message.attachment_name, 'size': message.attachment_size,
            'is_image': message.attachment_type in IMAGE_TYPES,
            'url': f'/core/chat/attachments/{message.pk}/',
        }
    return {
        'id': message.pk, 'sender': message.sender_id, 'recipient': message.recipient_id,
        'mine': message.sender_id == viewer.pk, 'body': message.body, 'created_at': message.created_at.isoformat(),
        'read': message.read_at is not None, 'attachment': attachment,
    }
