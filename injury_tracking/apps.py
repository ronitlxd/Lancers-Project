import os

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


class InjuryTrackingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'injury_tracking'

    def ready(self):
        self._check_media_root()
        # Importing the signal handlers registers the audit hooks for
        # authentication events (see lancer_project/audit.py).
        from lancer_project import audit_signals  # noqa: F401

    @staticmethod
    def _check_media_root():
        """Fail at start-up if MEDIA_ROOT is unusable.

        Injury photos are written here.  On Kubernetes MEDIA_ROOT points at a
        mounted persistent volume; if the mount is missing or the non-root
        container user cannot write to it, we want the deployment to fail
        immediately rather than to accept uploads that vanish on restart.
        """
        from django.conf import settings

        media_root = str(settings.MEDIA_ROOT)
        try:
            os.makedirs(media_root, exist_ok=True)
        except OSError as exc:
            raise ImproperlyConfigured(
                f'MEDIA_ROOT {media_root!r} does not exist and cannot be '
                f'created ({exc}). On Kubernetes, check that the persistent '
                f'volume for uploaded files is mounted.'
            ) from exc

        if not os.access(media_root, os.W_OK):
            raise ImproperlyConfigured(
                f'MEDIA_ROOT {media_root!r} is not writable by this process. '
                f'The container runs as a non-root user; check the volume '
                f'ownership and permissions.'
            )
