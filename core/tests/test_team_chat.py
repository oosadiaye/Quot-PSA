"""Team chat: message the other users of your workspace, share a file up to 2 MB,
see who is online.

Online means signed in (a live session seen recently): signing out ends the
session at once, so they go offline. Driven through the real HTTP endpoints
against the pytest tenant schema.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import ChatMessage, UserSession, chat_attachment_storage
from core.services import chat
from tenants.models import Client, UserTenantRole

BASE = '/api/v1/core/chat/'
DOMAIN = 'pytest.localhost'
MB = 1024 * 1024

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _private_storage(tmp_path, monkeypatch):
    """Keep test uploads out of the real private_media folder."""
    storage = FileSystemStorage(location=str(tmp_path))
    monkeypatch.setattr(ChatMessage._meta.get_field('attachment'), 'storage', storage)
    return tmp_path


@pytest.fixture
def tenant():
    return Client.objects.get(schema_name='pytest_schema')


@pytest.fixture
def make_user(tenant):
    def _make(username, first='', last='', member=True, active_role=True):
        user = User.objects.create_user(
            username, f'{username}@t.test', 'Pass-1234-xyz', first_name=first, last_name=last,
        )
        if member:
            UserTenantRole.objects.create(user=user, tenant=tenant, role='user', is_active=active_role)
        return user
    return _make


@pytest.fixture
def alice(make_user):
    return make_user('chat_alice', 'Alice', 'Ngozi')


@pytest.fixture
def bob(make_user):
    return make_user('chat_bob', 'Bob', 'Okafor')


@pytest.fixture
def cara(make_user):
    return make_user('chat_cara', 'Cara', 'Eze')


def client_for(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def open_session(user, seen=None, active=True):
    # Sessions live in the public schema (the auth code writes them there), though
    # core also has a — never read — copy of the table in every tenant schema.
    with schema_context('public'):
        token, _ = Token.objects.get_or_create(user=user)
        session, _ = UserSession.objects.get_or_create(user=user, token_key=token.key)
        # last_activity is auto_now, so only a queryset update can backdate it.
        UserSession.objects.filter(pk=session.pk).update(
            is_active=active, last_activity=seen or timezone.now(),
        )
    return session


def send(client, recipient, body='hello', upload=None):
    data = {'recipient': recipient.pk, 'body': body}
    if upload is not None:
        data['attachment'] = upload
    return client.post(f'{BASE}messages/', data, format='multipart')


def pdf(size, name='report.pdf', content_type='application/pdf'):
    return SimpleUploadedFile(name, b'x' * size, content_type=content_type)


def contacts_of(user):
    rows = client_for(user).get(f'{BASE}contacts/').json()['contacts']
    return {c['username']: c for c in rows}


class TestContactsAndPresence:
    def test_you_see_the_other_active_users_of_your_workspace_and_nobody_else(self, alice, bob, cara, make_user):
        make_user('chat_outsider', 'Out', 'Sider', member=False)
        make_user('chat_gone', 'Gone', 'User', active_role=False)
        assert set(contacts_of(alice)) == {'chat_bob', 'chat_cara'}

    def test_a_user_with_a_live_session_is_online(self, alice, bob, cara):
        open_session(bob)
        people = contacts_of(alice)
        assert people['chat_bob']['online'] is True
        assert people['chat_cara']['online'] is False

    def test_signing_out_makes_them_offline_at_once(self, alice, bob):
        open_session(bob)
        assert contacts_of(alice)['chat_bob']['online'] is True
        # Logout is a public-path route: the tenant comes from the Host header, not X-Tenant-Domain,
        # and under test only 'testserver' is an allowed host, so allow the tenant's.
        sign_out = client_for(bob)
        sign_out.defaults['HTTP_HOST'] = DOMAIN
        with override_settings(ALLOWED_HOSTS=[*settings.ALLOWED_HOSTS, DOMAIN]):
            response = sign_out.post('/api/v1/core/auth/logout/')
        assert response.status_code == 200, response.content
        # Signing out must really end the login, not just look like it: the token is revoked,
        # so the session cannot be used again. (An ordinary role used to be refused here by the
        # default model-permission check, leaving the token valid and the user "online".)
        assert not Token.objects.filter(user=bob).exists()
        assert contacts_of(alice)['chat_bob']['online'] is False

    def test_a_session_not_seen_for_a_while_reads_as_offline(self, alice, bob):
        open_session(bob, seen=timezone.now() - chat.ONLINE_WINDOW - timedelta(minutes=1))
        assert contacts_of(alice)['chat_bob']['online'] is False

    def test_a_revoked_session_is_offline(self, alice, bob):
        open_session(bob, active=False)
        assert contacts_of(alice)['chat_bob']['online'] is False

    def test_online_people_are_listed_first(self, alice, bob, cara):
        open_session(cara)
        order = [c['username'] for c in client_for(alice).get(f'{BASE}contacts/').json()['contacts']]
        assert order[0] == 'chat_cara'

    def test_the_summary_counts_unread_and_online(self, alice, bob):
        open_session(bob)
        send(client_for(bob), alice, 'ping')
        body = client_for(alice).get(f'{BASE}summary/').json()
        assert (body['unread_total'], body['online_count']) == (1, 1)

    def test_a_token_is_required(self, alice):
        anonymous = APIClient(HTTP_X_TENANT_DOMAIN=DOMAIN)
        assert anonymous.get(f'{BASE}contacts/').status_code in (401, 403)

    def test_the_tenant_header_is_required(self, alice):
        token, _ = Token.objects.get_or_create(user=alice)
        no_tenant = APIClient()
        no_tenant.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        assert no_tenant.get(f'{BASE}contacts/').status_code in (400, 403, 404)


class TestMessaging:
    def test_a_message_reaches_the_recipient_and_counts_as_unread(self, alice, bob):
        response = send(client_for(alice), bob, 'Are you free at 3?')
        assert response.status_code == 201, response.content
        row = contacts_of(bob)['chat_alice']
        assert row['unread'] == 1
        assert row['last_message']['preview'] == 'Are you free at 3?'

    def test_opening_the_conversation_marks_it_read(self, alice, bob):
        send(client_for(alice), bob, 'one')
        bob_client = client_for(bob)
        rows = bob_client.get(f'{BASE}messages/?with={alice.pk}&read=1').json()['messages']
        assert [m['body'] for m in rows] == ['one']
        assert bob_client.get(f'{BASE}summary/').json()['unread_total'] == 0

    def test_polling_with_after_returns_only_newer_messages(self, alice, bob):
        alice_client = client_for(alice)
        first = send(alice_client, bob, 'a').json()
        send(alice_client, bob, 'b')
        rows = alice_client.get(f'{BASE}messages/?with={bob.pk}&after={first["id"]}').json()['messages']
        assert [m['body'] for m in rows] == ['b']

    def test_each_side_sees_the_same_conversation_marked_mine_or_not(self, alice, bob):
        send(client_for(alice), bob, 'hi')
        send(client_for(bob), alice, 'hello')
        rows = client_for(alice).get(f'{BASE}messages/?with={bob.pk}').json()['messages']
        assert [(m['body'], m['mine']) for m in rows] == [('hi', True), ('hello', False)]

    def test_a_third_person_never_sees_the_conversation(self, alice, bob, cara):
        send(client_for(alice), bob, 'private')
        rows = client_for(cara).get(f'{BASE}messages/?with={alice.pk}').json()['messages']
        assert rows == []

    def test_you_cannot_message_someone_outside_the_workspace(self, alice, make_user):
        outsider = make_user('chat_out2', 'Out', 'Two', member=False)
        assert send(client_for(alice), outsider, 'hi').status_code == 400
        assert not ChatMessage.objects.exists()

    def test_you_cannot_message_yourself(self, alice):
        assert send(client_for(alice), alice).status_code == 400

    def test_an_empty_message_is_refused(self, alice, bob):
        response = send(client_for(alice), bob, body='   ')
        assert response.status_code == 400
        assert 'attach' in response.json()['error'].lower()

    def test_a_very_long_message_is_refused(self, alice, bob):
        response = send(client_for(alice), bob, body='x' * (chat.MAX_BODY_CHARS + 1))
        assert response.status_code == 400

    def test_reading_a_thread_with_someone_outside_the_workspace_is_refused(self, alice, make_user):
        outsider = make_user('chat_out3', 'Out', 'Three', member=False)
        assert client_for(alice).get(f'{BASE}messages/?with={outsider.pk}').status_code == 400


class TestAttachments:
    def test_a_file_of_exactly_2_mb_is_accepted(self, alice, bob):
        response = send(client_for(alice), bob, 'see attached', pdf(2 * MB))
        assert response.status_code == 201, response.content
        attachment = response.json()['attachment']
        assert (attachment['name'], attachment['size']) == ('report.pdf', 2 * MB)

    def test_a_file_over_2_mb_is_refused_and_nothing_is_stored(self, alice, bob):
        response = send(client_for(alice), bob, 'big', pdf(2 * MB + 1))
        assert response.status_code == 400
        assert '2 MB' in response.json()['error']
        assert not ChatMessage.objects.exists()

    def test_a_far_larger_upload_is_refused_before_the_body_is_parsed(self, alice, bob, monkeypatch):
        # DRF's multipart parser reads the whole body first; the header check must stop a huge upload
        # before chat.send (and therefore request.FILES) is ever reached.
        def _must_not_run(*args, **kwargs):
            raise AssertionError('the oversized request reached chat.send')
        monkeypatch.setattr(chat, 'send', _must_not_run)
        response = send(client_for(alice), bob, 'huge', pdf(3 * MB))
        assert response.status_code == 400
        assert '2 MB' in response.json()['error']

    def test_a_file_can_be_sent_with_no_text(self, alice, bob):
        response = send(client_for(alice), bob, '', pdf(1000, 'photo.png', 'image/png'))
        assert response.status_code == 201, response.content
        assert response.json()['attachment']['is_image'] is True

    @pytest.mark.parametrize('name', ['setup.exe', 'run.bat', 'page.html', 'logo.svg', 'x.js', 'tool.ps1', 'a.PHP'])
    def test_files_that_can_run_or_carry_a_script_are_refused(self, alice, bob, name):
        response = send(client_for(alice), bob, 'f', pdf(100, name, 'application/octet-stream'))
        assert response.status_code == 400, name

    def test_an_empty_file_is_refused(self, alice, bob):
        assert send(client_for(alice), bob, 'f', pdf(0)).status_code == 400

    def test_the_file_name_is_cleaned_and_the_stored_path_is_unguessable(self, alice, bob):
        response = send(client_for(alice), bob, 'f', pdf(100, '../../etc/passwd report.txt', 'text/plain'))
        assert response.status_code == 201, response.content
        message = ChatMessage.objects.get()
        assert message.attachment_name == 'passwd report.txt'
        assert message.attachment.name.startswith('tenants/pytest_schema/chat/')
        assert 'passwd' not in message.attachment.name

    def test_production_storage_is_private_with_no_public_url(self):
        storage = chat_attachment_storage()
        private_root = settings.PRIVATE_MEDIA_ROOT.resolve()
        assert str(storage.location) == str(private_root)
        # Not inside MEDIA_ROOT, which the web server may expose directly under /media/.
        assert settings.MEDIA_ROOT.resolve() not in private_root.parents
        assert private_root != settings.MEDIA_ROOT.resolve()
        # And there is no URL to hand out: a bare link cannot be built for a stored file.
        with pytest.raises(ValueError):
            storage.url('tenants/x/chat/abc.pdf')

    def test_the_sender_and_recipient_can_download_but_nobody_else(self, alice, bob, cara):
        sent = send(client_for(alice), bob, 'f', pdf(300, 'notes.txt', 'text/plain')).json()
        url = f'{BASE}attachments/{sent["id"]}/'
        for who, expected in ((alice, 200), (bob, 200), (cara, 404)):
            response = client_for(who).get(url)
            assert response.status_code == expected, who.username
            if expected == 200:
                assert b''.join(response.streaming_content) == b'x' * 300
                assert 'attachment' in response['Content-Disposition']
                assert response['X-Content-Type-Options'] == 'nosniff'

    def test_a_message_without_a_file_has_no_download(self, alice, bob):
        sent = send(client_for(alice), bob, 'just text').json()
        assert client_for(bob).get(f'{BASE}attachments/{sent["id"]}/').status_code == 404

    def test_the_send_throttle_scope_has_a_configured_rate(self):
        # DRF raises on a throttled request whose scope has no rate; this is the guard for that.
        assert settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['chat_send']


class TestOnlyMembersMayUseChat:
    """Chat views are IsAuthenticated only, and the tenant-access middleware cannot see a token-authenticated
    user, so a signed-in user of ANOTHER tenant (or one whose role here was removed) could send the tenant
    header and read this workspace's directory, message its people, and store files on its disk."""

    @pytest.fixture
    def outsider(self, make_user):
        return make_user('chat_outsider2', 'Out', 'Sider', member=False)

    def _blocked(self, response):
        assert response.status_code == 403, (response.status_code, response.content[:200])

    def test_a_signed_in_user_with_no_role_here_gets_nothing(self, alice, bob, outsider):
        client = client_for(outsider)
        self._blocked(client.get(f'{BASE}summary/'))
        self._blocked(client.get(f'{BASE}contacts/'))
        self._blocked(client.get(f'{BASE}messages/?with={alice.pk}'))
        self._blocked(send(client, bob, 'hello from outside'))
        assert not ChatMessage.objects.exists()

    def test_the_outsider_learns_nothing_about_who_is_in_the_workspace(self, alice, outsider):
        body = client_for(outsider).get(f'{BASE}contacts/').content
        assert b'chat_alice' not in body and b'Alice' not in body

    def test_a_removed_member_loses_access_including_to_their_old_files(self, make_user, bob, tenant):
        ex = make_user('chat_ex_member', 'Ex', 'Member')
        sent = send(client_for(ex), bob, 'f', pdf(300, 'old.txt', 'text/plain')).json()
        UserTenantRole.objects.filter(user=ex, tenant=tenant).update(is_active=False)

        client = client_for(ex)
        self._blocked(client.get(f'{BASE}contacts/'))
        self._blocked(client.get(f'{BASE}attachments/{sent["id"]}/'))
        self._blocked(send(client, bob, 'still here?'))

    def test_a_deactivated_user_account_is_refused(self, alice, bob):
        User.objects.filter(pk=bob.pk).update(is_active=False)
        assert client_for(bob).get(f'{BASE}summary/').status_code in (401, 403)

    def test_members_are_unaffected(self, alice, bob):
        assert client_for(alice).get(f'{BASE}contacts/').status_code == 200


class TestChatPollingDoesNotUseUpTheWholeApiAllowance:
    """The app-wide 'user' throttle is 1000 requests/hour. One open conversation polls ~1,260/hour, so chat
    sharing that bucket would lock the person out of the entire app after about 48 minutes."""

    @pytest.mark.parametrize('view', ['chat_summary', 'chat_contacts', 'chat_messages', 'chat_attachment'])
    def test_chat_views_do_not_count_against_the_global_user_bucket(self, view):
        from core.views import chat as chat_views
        classes = getattr(chat_views, view).cls.throttle_classes
        assert classes, view
        assert all(getattr(c, 'scope', None) != 'user' for c in classes), [c.__name__ for c in classes]

    def test_the_chat_read_scope_allows_a_full_hour_of_open_polling(self):
        rate = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['chat_read']
        per_hour = int(rate.split('/')[0]) * {'second': 3600, 'minute': 60, 'hour': 1, 'day': 1 / 24}[rate.split('/')[1].rstrip('s')]
        assert per_hour >= 3 * 1260  # three open tabs, with headroom


class TestUploadHardening:
    def test_a_send_with_no_content_length_is_refused(self, alice, bob):
        # A chunked upload has no Content-Length, so the size pre-check could not see it.
        client = client_for(alice)
        data = {'recipient': bob.pk, 'body': 'hi'}
        response = client.post(f'{BASE}messages/', data, format='multipart', CONTENT_LENGTH='')
        assert response.status_code == 411, (response.status_code, response.content[:200])

    @pytest.mark.parametrize('name', [
        'macro.docm', 'macro.xlsm', 'disc.iso', 'help.chm', 'link.url', 'page.aspx', 'run.py', 'cfg.xml',
        'shell.phtml', 'app.jnlp', 'x.JSE', 'tool.scf', 'installer.pkg',
    ])
    def test_more_runnable_and_macro_types_are_refused(self, alice, bob, name):
        response = send(client_for(alice), bob, 'f', pdf(100, name, 'application/octet-stream'))
        assert response.status_code == 400, name

    def test_ordinary_office_files_are_still_accepted(self, alice, bob):
        for name in ('minutes.docx', 'budget.xlsx', 'deck.pptx', 'scan.pdf', 'logo.png', 'data.csv', 'notes.txt', 'bundle.zip'):
            assert send(client_for(alice), bob, 'f', pdf(100, name, 'application/octet-stream')).status_code == 201, name

    def test_a_sender_cannot_exceed_the_daily_attachment_quota(self, alice, bob, monkeypatch):
        monkeypatch.setattr(chat, 'MAX_DAILY_ATTACHMENT_BYTES', 5 * 1000)
        client = client_for(alice)
        assert send(client, bob, 'a', pdf(2000, 'a.txt', 'text/plain')).status_code == 201
        assert send(client, bob, 'b', pdf(2000, 'b.txt', 'text/plain')).status_code == 201
        refused = send(client, bob, 'c', pdf(2000, 'c.txt', 'text/plain'))
        assert refused.status_code == 400
        assert 'today' in refused.json()['error'].lower()
        # Plain text messages are not counted against the file quota.
        assert send(client, bob, 'still can talk').status_code == 201

    def test_deleting_a_message_deletes_its_file(self, alice, bob):
        sent = send(client_for(alice), bob, 'f', pdf(300, 'gone.txt', 'text/plain')).json()
        message = ChatMessage.objects.get(pk=sent['id'])
        storage, name = message.attachment.storage, message.attachment.name
        assert storage.exists(name)
        message.delete()
        assert not storage.exists(name)

    def test_the_stored_extension_is_limited_to_safe_characters(self):
        from core.models import chat_attachment_path
        for raw, expected_suffix in (('a.txt:evil', ''), ('x.tar.gz', '.gz'), ('r.PDF', '.pdf'), ('n/a', ''),
                                     ('weird.ex e', ''), ('long.abcdefghijkl', '')):
            path = chat_attachment_path(None, raw)
            assert path.startswith('tenants/'), path
            assert path.endswith(expected_suffix), (raw, path)
            assert ':' not in path and ' ' not in path


def test_the_browser_side_blocklist_matches_the_servers():
    """chatFormat.ts mirrors BLOCKED_EXTENSIONS so people are told before uploading. If the two drift, either a
    file is refused only after a pointless upload, or the browser blocks something the server accepts."""
    import re
    from pathlib import Path

    ts = (Path(settings.BASE_DIR) / 'frontend' / 'src' / 'features' / 'chat' / 'chatFormat.ts').read_text(encoding='utf-8')
    block = re.search(r'const BLOCKED = new Set\(\[(.*?)\]\);', ts, re.S).group(1)
    assert set(re.findall(r"'([a-z0-9\-]+)'", block)) == set(chat.BLOCKED_EXTENSIONS)
