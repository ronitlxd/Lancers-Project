"""
accounts/tests.py — Unit + integration tests for notification system,
auth views, and the notify() utility.
"""
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import Notification, Team
from accounts.utils import notify, notify_team

User = get_user_model()


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_user(role='PLAYER', username='testplayer', team=None, **kwargs):
    u = User.objects.create_user(
        username=username,
        email=f'{username}@test.com',
        password='testpass123',
        role=role,
        team=team,
        is_registration_complete=True,
        **kwargs,
    )
    return u


# ── notify() utility ───────────────────────────────────────────────────────────

class NotifyUtilTests(TestCase):
    def setUp(self):
        self.player = make_user('PLAYER', 'player1')

    def test_creates_notification(self):
        n = notify(self.player, 'Test message', notification_type='INJURY')
        self.assertIsNotNone(n)
        self.assertEqual(Notification.objects.filter(user=self.player).count(), 1)
        self.assertEqual(n.message, 'Test message')
        self.assertEqual(n.notification_type, 'INJURY')
        self.assertFalse(n.is_read)

    def test_noop_for_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        result = notify(AnonymousUser(), 'Should not save')
        self.assertIsNone(result)
        self.assertEqual(Notification.objects.count(), 0)

    def test_noop_for_none(self):
        result = notify(None, 'Should not save')
        self.assertIsNone(result)

    def test_notify_team_bulk(self):
        p2 = make_user('PLAYER', 'player2')
        results = notify_team([self.player, p2], 'Team message', notification_type='EVENT')
        self.assertEqual(len(results), 2)
        self.assertEqual(Notification.objects.count(), 2)

    def test_notify_with_link(self):
        n = notify(self.player, 'Linked', link='/tracking/injuries/1/')
        self.assertEqual(n.link, '/tracking/injuries/1/')


# ── Notification API endpoints ─────────────────────────────────────────────────

class NotificationAPITests(TestCase):
    def setUp(self):
        self.player = make_user('PLAYER', 'apiplayer')
        self.client = Client()
        self.client.force_login(self.player)  # bypass axes backend in tests
        # Pre-create 3 notifications (2 unread, 1 read)
        notify(self.player, 'Unread 1', notification_type='INJURY')
        notify(self.player, 'Unread 2', notification_type='APPOINTMENT')
        n = notify(self.player, 'Read one', notification_type='EVENT')
        n.is_read = True
        n.save()

    def test_get_notifications_returns_json(self):
        url = reverse('get_notifications')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('unread_count', data)
        self.assertIn('notifications', data)
        self.assertEqual(data['unread_count'], 2)
        self.assertLessEqual(len(data['notifications']), 10)

    def test_get_notifications_requires_login(self):
        self.client.logout()
        url = reverse('get_notifications')
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 403])

    def test_mark_notification_read(self):
        n = Notification.objects.filter(user=self.player, is_read=False).first()
        url = reverse('mark_notification_read', kwargs={'pk': n.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_notification_read_wrong_user(self):
        other = make_user('PLAYER', 'other')
        n = notify(other, 'Other notification')
        url = reverse('mark_notification_read', kwargs={'pk': n.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)

    def test_mark_all_read(self):
        url = reverse('mark_all_notifications_read')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(user=self.player, is_read=False).count(), 0
        )

    def test_notifications_page_renders(self):
        url = reverse('notifications_page')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'accounts/notifications.html')

    def test_notifications_page_marks_all_read_on_visit(self):
        url = reverse('notifications_page')
        self.client.get(url)
        self.assertEqual(
            Notification.objects.filter(user=self.player, is_read=False).count(), 0
        )

    def test_notifications_page_requires_login(self):
        self.client.logout()
        url = reverse('notifications_page')
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 403])


# ── Custom error pages ─────────────────────────────────────────────────────────

class ErrorPageTests(TestCase):
    def test_404_page(self):
        resp = self.client.get('/this-url-definitely-does-not-exist-xyz/')
        self.assertEqual(resp.status_code, 404)


# ── Entra SSO (UWindsor IT review, finding 4) ─────────────────────────────────

from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware

from allauth.socialaccount.models import SocialAccount, SocialLogin

from accounts.adapters import (
    EntraSocialAccountAdapter,
    NoSelfSignupAccountAdapter,
)

try:
    from allauth.core.exceptions import ImmediateHttpResponse
except ImportError:  # pragma: no cover
    from allauth.exceptions import ImmediateHttpResponse


def _graph_payload(oid='00000000-0000-0000-0000-00000000abcd',
                   upn='uwinid@uwindsor.ca',
                   mail='uwinid@uwindsor.ca'):
    """Shape of what the Microsoft provider puts in extra_data."""
    return {'id': oid, 'userPrincipalName': upn, 'mail': mail,
            'displayName': 'Test Person'}


def _social_login(payload):
    account = SocialAccount(provider='microsoft', uid=payload['id'],
                            extra_data=payload)
    return SocialLogin(user=User(email=payload.get('mail', '')), account=account)


def _request():
    request = RequestFactory().get('/accounts/microsoft/login/callback/')
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


class SignupIsClosedTests(TestCase):
    """Neither adapter may ever create an account.

    Anyone with a UWin account can authenticate against Entra, so if signup
    were open, authenticating would hand out access by itself.
    """

    def test_local_signup_closed(self):
        self.assertFalse(
            NoSelfSignupAccountAdapter().is_open_for_signup(_request()))

    def test_social_signup_closed(self):
        adapter = EntraSocialAccountAdapter()
        self.assertFalse(adapter.is_open_for_signup(
            _request(), _social_login(_graph_payload())))


class EntraUserMatchingTests(TestCase):
    """Identifier precedence: object ID, then UPN, then email, then username."""

    def test_matches_on_object_id_first(self):
        by_oid = make_user(username='by_oid')
        by_oid.entra_oid = 'OID-1'
        by_oid.save()
        make_user(username='decoy')
        found = EntraSocialAccountAdapter._find_local_user(
            'OID-1', 'someone-else@uwindsor.ca', 'someone-else@uwindsor.ca')
        self.assertEqual(found, by_oid)

    def test_matches_on_upn_when_no_oid_stored(self):
        user = make_user(username='by_upn')
        user.entra_upn = 'by.upn@uwindsor.ca'
        user.save()
        found = EntraSocialAccountAdapter._find_local_user(
            'UNKNOWN-OID', 'BY.UPN@uwindsor.ca', '')
        self.assertEqual(found, user)

    def test_matches_on_email(self):
        user = make_user(username='by_email')
        user.email = 'real.person@uwindsor.ca'
        user.save()
        found = EntraSocialAccountAdapter._find_local_user(
            'UNKNOWN-OID', 'real.person@uwindsor.ca', 'real.person@uwindsor.ca')
        self.assertEqual(found, user)

    def test_matches_on_username_as_last_resort(self):
        user = make_user(username='uwinid')
        found = EntraSocialAccountAdapter._find_local_user(
            'UNKNOWN-OID', 'uwinid@uwindsor.ca', '')
        self.assertEqual(found, user)

    def test_no_match_returns_none(self):
        self.assertIsNone(EntraSocialAccountAdapter._find_local_user(
            'NOPE', 'stranger@uwindsor.ca', 'stranger@uwindsor.ca'))


class EntraPreSocialLoginTests(TestCase):
    def setUp(self):
        self.adapter = EntraSocialAccountAdapter()

    def test_unprovisioned_identity_is_refused(self):
        """Authenticating against Entra must not create or admit a user."""
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(
                _request(), _social_login(_graph_payload()))
        self.assertFalse(User.objects.filter(
            email='uwinid@uwindsor.ca').exists())

    def test_inactive_account_is_refused(self):
        user = make_user(username='disabled')
        user.email = 'disabled@uwindsor.ca'
        user.is_active = False
        user.save()
        payload = _graph_payload(upn='disabled@uwindsor.ca',
                                 mail='disabled@uwindsor.ca')
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _social_login(payload))

    def test_provisioned_account_is_linked_and_identifiers_stored(self):
        user = make_user(username='provisioned')
        user.email = 'provisioned@uwindsor.ca'
        user.save()
        payload = _graph_payload(oid='OID-PROVISIONED',
                                 upn='provisioned@uwindsor.ca',
                                 mail='provisioned@uwindsor.ca')
        sociallogin = _social_login(payload)

        self.adapter.pre_social_login(_request(), sociallogin)

        user.refresh_from_db()
        # Matched on email, since nothing was stored on the account yet.
        self.assertEqual(user.entra_oid, 'OID-PROVISIONED')
        self.assertEqual(user.entra_upn, 'provisioned@uwindsor.ca')
        self.assertEqual(sociallogin.user.pk, user.pk)

    def test_upn_change_does_not_break_an_existing_link(self):
        """A UWinID change rewrites the UPN but never the object ID, which is
        why we key on the object ID (IT response, section 3.3)."""
        user = make_user(username='renamed')
        user.entra_oid = 'OID-STABLE'
        user.entra_upn = 'old.name@uwindsor.ca'
        user.save()
        payload = _graph_payload(oid='OID-STABLE',
                                 upn='new.name@uwindsor.ca',
                                 mail='new.name@uwindsor.ca')

        self.adapter.pre_social_login(_request(), _social_login(payload))

        user.refresh_from_db()
        self.assertEqual(user.entra_upn, 'new.name@uwindsor.ca')


class DeploymentEndpointTests(TestCase):
    def test_healthz_is_public_and_cheap(self):
        response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'OK')

    def test_password_reset_routes_are_gone(self):
        """Entra owns credentials now; a local reset flow would be a second,
        weaker way in, and it was the only feature needing Gmail SMTP."""
        for path in ('/password-reset/', '/password-reset/done/',
                     '/reset/complete/'):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_allauth_routes_are_mounted(self):
        # The provider login entry point should exist (GET is refused because
        # SOCIALACCOUNT_LOGIN_ON_GET is False, but it must not be a 404).
        self.assertNotEqual(
            self.client.get('/accounts/microsoft/login/').status_code, 404)
