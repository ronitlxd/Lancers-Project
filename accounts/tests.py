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
