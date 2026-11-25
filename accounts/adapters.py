"""
accounts/adapters.py

django-allauth adapters for Microsoft Entra sign-in.

UWindsor IT review, findings 3 and 4.  IT Services' answer set the shape of
this (their response, sections 1.2, 1.3, 3.3, 3.6 and 3.7):

* Entra AUTHENTICATES.  Django AUTHORIZES.  There are no Entra security groups
  for the dashboard roles and none are planned.
* Anyone with a UWin account can authenticate against Entra, so authenticating
  must not by itself grant any access here.  The application grants nothing by
  default and admits only users an administrator has already provisioned.
* IT expects the UPN at sign-in but has not confirmed whether the Entra object
  ID should be the persistent key.  We store both and prefer the object ID,
  which never changes, so either answer works without re-linking accounts.

This replaces the old self-registration flow, which derived a user's role from
the email address they typed into a public form with no verification step.
"""

from django.contrib import messages
from django.shortcuts import redirect

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

try:  # allauth >= 65
    from allauth.core.exceptions import ImmediateHttpResponse
except ImportError:  # pragma: no cover - older allauth
    from allauth.exceptions import ImmediateHttpResponse

from lancer_project.audit import audit

DENIED_MESSAGE = (
    'Your University sign-in worked, but there is no LancersPulse account for '
    'you yet. Accounts are created by the Centre for Human Performance & '
    'Health - please contact your administrator.'
)

INACTIVE_MESSAGE = (
    'Your LancersPulse account is disabled. Please contact your administrator.'
)


class NoSelfSignupAccountAdapter(DefaultAccountAdapter):
    """Closes local self-registration permanently."""

    def is_open_for_signup(self, request):
        return False


class EntraSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Links an Entra identity to an already-provisioned local account."""

    def is_open_for_signup(self, request, sociallogin):
        # Never create a user from an Entra identity alone.
        return False

    # -- identity extraction -------------------------------------------------

    @staticmethod
    def _identity(sociallogin):
        """Pull (oid, upn, email) out of whatever the provider returned.

        The Microsoft provider populates extra_data from Graph /me, but key
        names differ between Graph and raw id_token claims, so check both.
        IT Services asked us to verify the real claim set against a staging
        token before relying on it (their response, section 3.4).
        """
        data = dict(getattr(sociallogin.account, 'extra_data', {}) or {})

        oid = (
            data.get('id')
            or data.get('oid')
            or getattr(sociallogin.account, 'uid', None)
        )
        upn = (
            data.get('userPrincipalName')
            or data.get('preferred_username')
            or data.get('upn')
            or ''
        )
        email = (
            data.get('mail')
            or data.get('email')
            or getattr(sociallogin.user, 'email', '')
            or ''
        )
        return (oid or ''), upn.strip(), email.strip()

    @staticmethod
    def _find_local_user(oid, upn, email):
        """Locate the provisioned account, most reliable identifier first."""
        from .models import CustomUser

        if oid:
            user = CustomUser.objects.filter(entra_oid=oid).first()
            if user:
                return user
        if upn:
            user = CustomUser.objects.filter(entra_upn__iexact=upn).first()
            if user:
                return user
        for candidate in (upn, email):
            if candidate:
                user = CustomUser.objects.filter(email__iexact=candidate).first()
                if user:
                    return user
        # Last resort: an administrator who provisioned the account using the
        # bare UWinID as the username.
        local_part = (upn or email).split('@')[0]
        if local_part:
            return CustomUser.objects.filter(username__iexact=local_part).first()
        return None

    @staticmethod
    def _store_identifiers(user, oid, upn):
        """Backfill the identifiers so later sign-ins match on the object ID."""
        changed = []
        if oid and user.entra_oid != oid:
            user.entra_oid = oid
            changed.append('entra_oid')
        if upn and user.entra_upn != upn:
            user.entra_upn = upn
            changed.append('entra_upn')
        if changed:
            user.save(update_fields=changed)

    # -- the hook itself -----------------------------------------------------

    def pre_social_login(self, request, sociallogin):
        oid, upn, email = self._identity(sociallogin)

        if sociallogin.is_existing:
            # Already linked: keep the stored identifiers current and let the
            # normal login proceed.
            self._store_identifiers(sociallogin.user, oid, upn)
            return

        user = self._find_local_user(oid, upn, email)

        if user is None:
            audit(
                'SSO_SIGN_IN',
                actor=None,
                request=request,
                outcome='FAILURE',
                reason='no_local_account',
                attempted_upn=upn or email or None,
            )
            messages.error(request, DENIED_MESSAGE)
            raise ImmediateHttpResponse(redirect('login'))

        if not user.is_active:
            audit(
                'SSO_SIGN_IN',
                actor=user,
                request=request,
                outcome='FAILURE',
                reason='inactive_account',
            )
            messages.error(request, INACTIVE_MESSAGE)
            raise ImmediateHttpResponse(redirect('login'))

        # Work out how we matched BEFORE backfilling, or the answer is always
        # 'oid' once _store_identifiers has run.
        if oid and user.entra_oid == oid:
            matched_on = 'oid'
        elif upn and user.entra_upn and user.entra_upn.lower() == upn.lower():
            matched_on = 'upn'
        else:
            matched_on = 'email_or_username'

        self._store_identifiers(user, oid, upn)
        audit(
            'SSO_ACCOUNT_LINK',
            actor=user,
            request=request,
            matched_on=matched_on,
        )
        sociallogin.connect(request, user)
