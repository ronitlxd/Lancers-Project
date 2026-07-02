"""Small cross-app utilities (kept here to avoid circular imports)."""
from .models import Notification


def notify(user, message, notification_type='INJURY', link='', send_email=False, subject=None):
    """Create an in-app Notification row. Optionally send an email too.

    Args:
        user:              The recipient CustomUser. No-op if missing/anonymous.
        message:           Notification body text.
        notification_type: One of INJURY, APPOINTMENT, CLEARANCE, EVENT.
        link:              Optional URL the notification links to.
        send_email:        If True, also send a Django email to user.email.
        subject:           Email subject (defaults to first 80 chars of message).

    Returns:
        The Notification instance, or None if user is invalid.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    notif = Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type,
        link=link or '',
    )

    if send_email and getattr(user, 'email', None):
        _send_notification_email(user, message, subject, link)

    return notif


def _send_notification_email(user, message, subject, link):
    """Send a plain-text notification email. Failures are silent."""
    from django.core.mail import send_mail
    from django.conf import settings

    email_subject = subject or f'LancersPulse: {message[:80]}'
    site_url = getattr(settings, 'SITE_URL', '')

    body_lines = [
        f'Hi {user.get_full_name() or user.username},',
        '',
        message,
    ]
    if link:
        full_link = f'{site_url}{link}' if link.startswith('/') else link
        body_lines += ['', f'View details: {full_link}']

    body_lines += [
        '',
        '--- The LancersPulse Team',
        '',
        'You are receiving this email because you have an account on LancersPulse.',
    ]

    try:
        send_mail(
            subject=email_subject,
            message='\n'.join(body_lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass


def notify_team(users, message, notification_type='INJURY', link='', send_email=False, subject=None):
    """Bulk notify a queryset or list of users.

    Returns a list of created Notification instances.
    """
    return [
        notify(u, message, notification_type=notification_type,
               link=link, send_email=send_email, subject=subject)
        for u in users
        if u and getattr(u, 'is_authenticated', False)
    ]
