"""
lancer_project/audit_signals.py

Authentication audit events, wired through Django's auth signals rather than
through the login view.  Signals keep firing when django-allauth takes over
sign-in for Entra SSO, so these hooks survive that change untouched.

Imported from InjuryTrackingConfig.ready().
"""

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .audit import audit


@receiver(user_logged_in)
def _on_logged_in(sender, request, user, **kwargs):
    audit('SIGN_IN', actor=user, request=request)


@receiver(user_logged_out)
def _on_logged_out(sender, request, user, **kwargs):
    audit('SIGN_OUT', actor=user, request=request)


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    # `credentials` carries the submitted password; record only the username.
    audit(
        'SIGN_IN',
        actor=None,
        request=request,
        outcome='FAILURE',
        attempted_username=(credentials or {}).get('username'),
    )
