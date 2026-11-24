"""Team chat API: message the other users of your workspace and share a file (up to 2 MB).

    GET  /api/v1/core/chat/summary/                  unread count and people online (the closed widget polls this)
    GET  /api/v1/core/chat/contacts/                 the workspace's other users, online first, with unread counts
    GET  /api/v1/core/chat/messages/?with=<id>       the conversation with one person (&after=<id> for only newer)
    POST /api/v1/core/chat/messages/                 send: multipart ``recipient``, ``body``, optional ``attachment``
    GET  /api/v1/core/chat/attachments/<id>/         download a file (only the two people in the conversation)

Any signed-in tenant user may use it; there is no per-module permission because it is not business data. Every query is
confined to the tenant's own schema and to its active members, and a message is only ever visible to its sender and
recipient.
"""
from django.db import connection
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from core.services import chat

DEFAULT_LIMIT = 100
MAX_LIMIT = 200
#: A send request is the file plus the text and multipart framing. Anything bigger than this cannot be a valid
#: message, so it is refused from the header alone, before the body is read.
MAX_REQUEST_BYTES = chat.MAX_ATTACHMENT_BYTES + 256 * 1024


class ChatReadThrottle(UserRateThrottle):
    """Chat reads have their own allowance. The widget polls (about 1,260 requests an hour with one conversation
    open), so sharing the app-wide 'user' bucket of 1,000/hour would lock a person out of the whole API."""
    scope = 'chat_read'


class ChatSendThrottle(UserRateThrottle):
    """Sending is bounded per user so a script cannot flood a colleague."""
    scope = 'chat_send'

    def allow_request(self, request, view):
        # Only sending is limited here; the conversation is polled every few seconds and must not trip it.
        return True if request.method != 'POST' else super().allow_request(request, view)


def _tenant(request):
    tenant = getattr(request, 'tenant', None) or getattr(connection, 'tenant', None)
    if tenant is None or getattr(tenant, 'schema_name', 'public') == 'public':
        return None
    return tenant


def _guard(request):
    """``(tenant, None)`` for a member of this workspace, else ``(None, <error Response>)``.

    These views are IsAuthenticated only, and the tenant middleware cannot see a token-authenticated user, so
    without this a user of ANOTHER tenant (or one whose role here was removed) could send the tenant header and
    read the directory, message people and store files here. Everyone must hold an active role in the workspace.
    """
    tenant = _tenant(request)
    if tenant is None:
        return None, _no_tenant()
    if not chat.is_member(tenant, request.user.pk):
        return None, Response({'error': 'You are not a member of this workspace.'}, status=status.HTTP_403_FORBIDDEN)
    return tenant, None


def _no_tenant():
    return Response({'error': 'Tenant context required. Send X-Tenant-Domain header.'},
                    status=status.HTTP_400_BAD_REQUEST)


def _int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatReadThrottle])
def chat_summary(request):
    tenant, denied = _guard(request)
    if denied is not None:
        return denied
    return Response(chat.summary(request.user, tenant))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatReadThrottle])
def chat_contacts(request):
    tenant, denied = _guard(request)
    if denied is not None:
        return denied
    rows = chat.contacts(request.user, tenant)
    return Response({
        'contacts': rows,
        'unread_total': sum(r['unread'] for r in rows),
        'online_count': sum(1 for r in rows if r['online']),
        'limits': {'max_attachment_bytes': chat.MAX_ATTACHMENT_BYTES, 'max_body_chars': chat.MAX_BODY_CHARS},
    })


def _list_messages(request, tenant):
    other = _int(request.query_params.get('with'))
    if not other or not chat.is_member(tenant, other):
        return Response({'error': 'Choose someone from your workspace.'}, status=status.HTTP_400_BAD_REQUEST)
    limit = min(_int(request.query_params.get('limit'), DEFAULT_LIMIT) or DEFAULT_LIMIT, MAX_LIMIT)
    rows = chat.thread(request.user, other, after=_int(request.query_params.get('after')), limit=limit,
                       mark_read=request.query_params.get('read') in ('1', 'true'))
    return Response({'messages': [chat.serialize(m, request.user) for m in rows]})


def _send_message(request, tenant):
    # Refuse an oversized request before DRF parses it: the multipart parser reads the whole body first, so
    # checking only the file's size afterwards would still make the server swallow an arbitrarily large upload.
    # A chunked upload carries no Content-Length, so the check below could not see its size. Browsers always send
    # one for a form, so a request without it is refused rather than read to the end.
    if not request.META.get('CONTENT_LENGTH'):
        return Response({'error': 'The upload must state its size.'}, status=status.HTTP_411_LENGTH_REQUIRED)
    if _int(request.META.get('CONTENT_LENGTH')) > MAX_REQUEST_BYTES:
        return Response({'error': 'Files are limited to 2 MB. Choose a smaller file.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        message = chat.send(
            request.user, tenant, _int(request.data.get('recipient')),
            request.data.get('body', ''), request.FILES.get('attachment'))
    except chat.ChatError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(chat.serialize(message, request.user), status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatReadThrottle, ChatSendThrottle])
def chat_messages(request):
    tenant, denied = _guard(request)
    if denied is not None:
        return denied
    if request.method == 'POST':
        return _send_message(request, tenant)
    return _list_messages(request, tenant)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatReadThrottle])
def chat_attachment(request, message_id):
    """Stream a file to the sender or the recipient only. Never a bare media URL, and never inline: a download."""
    from core.models import ChatMessage
    tenant, denied = _guard(request)
    if denied is not None:
        return denied
    message = ChatMessage.objects.filter(pk=message_id).first()
    if (message is None or not message.attachment
            or request.user.pk not in (message.sender_id, message.recipient_id)):
        raise Http404
    try:
        handle = message.attachment.open('rb')
    except OSError:
        raise Http404
    response = FileResponse(handle, as_attachment=True, filename=message.attachment_name or 'file')
    response['X-Content-Type-Options'] = 'nosniff'
    return response
