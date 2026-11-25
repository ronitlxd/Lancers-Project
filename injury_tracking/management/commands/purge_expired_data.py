"""
Apply the retention rules.

UWindsor IT review, finding 5.  Run on a schedule, and ALSO after any restore
from backup: IT Services confirmed deletions do not propagate to backups
(their response, 1.8), so a restore resurrects data that was already purged.
Because these rules are deterministic, re-running this command re-applies
every retention-driven purge.  Anything deleted OUTSIDE the rules needs
`replay_purge_ledger` instead.

    python manage.py purge_expired_data --dry-run     # report only
    python manage.py purge_expired_data               # apply

The periods come from settings and are PROPOSALS pending CHPH and University
Records Management.  See RETENTION_* in lancer_project/settings.py.
"""

import os
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from django.contrib.auth import get_user_model
from django.db.models import Q

from injury_tracking.models import (
    Appointment, InjuryRecord, PurgeLedgerEntry, WellnessCheckIn,
)
from injury_tracking.retention import (
    PLACEHOLDER_PREFIX,
    anonymise_appointment,
    anonymise_injury_record,
    anonymise_wellness_checkin,
    clear_emergency_contacts,
    delete_injury_photo,
    record_ledger,
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Apply data retention rules (anonymise expired records, delete expired photos).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.')
        parser.add_argument(
            '--actor', default='system',
            help='Who to record in the ledger (default: system).')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        actor = options['actor']
        now = timezone.now()

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - nothing will be written.'))

        counts = {
            'records_anonymised': self._anonymise_expired(now, actor, dry_run),
            'photos_deleted': self._delete_expired_photos(now, actor, dry_run),
            'checkins_anonymised': self._anonymise_wellness(now, actor, dry_run),
            'appointments_anonymised': self._anonymise_appointments(now, actor, dry_run),
            'emergency_contacts_cleared': self._clear_emergency_contacts(now, actor, dry_run),
            'orphan_files_deleted': self._delete_orphan_uploads(now, actor, dry_run),
        }

        self.stdout.write('')
        for label, value in counts.items():
            self.stdout.write(f'{label.replace("_", " ")}: {value}')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                'Dry run complete - re-run without --dry-run to apply.'))
        else:
            self.stdout.write(self.style.SUCCESS('Retention run complete.'))

    # -- rules ---------------------------------------------------------------

    def _anonymise_expired(self, now, actor, dry_run):
        """Records untouched for longer than the record retention period.

        Keyed on updated_at ("last activity") rather than injury_date, so a
        long-running chronic case is not anonymised while it is still being
        treated.  Already-anonymised rows are excluded, so this cannot loop
        even though anonymising writes to updated_at.
        """
        years = settings.RETENTION_INJURY_RECORD_YEARS
        cutoff = now - timedelta(days=365 * years)
        reason = f'Retention: no activity for {years} years'

        queryset = (
            InjuryRecord.objects
            .select_related('player')
            .filter(anonymised_at__isnull=True, updated_at__lt=cutoff)
        )

        count = 0
        for record in queryset.iterator():
            if anonymise_injury_record(record, reason, actor=actor, dry_run=dry_run):
                count += 1
                self.stdout.write(
                    f'  anonymise InjuryRecord #{record.pk} '
                    f'(last activity {record.updated_at:%Y-%m-%d})')
        return count

    def _delete_expired_photos(self, now, actor, dry_run):
        """Photographs: one year, "or on recovery if later".

        Both conditions must hold, per the retention table agreed with CHPH on
        25 Nov 2026. A photograph of an injury still being treated after a
        year is still clinically useful, so the calendar alone does not remove
        it; the injury must also be resolved.
        """
        days = settings.RETENTION_INJURY_PHOTO_DAYS
        cutoff = (now - timedelta(days=days)).date()
        reason = f'Retention: photo older than {days} days and injury resolved'

        queryset = (
            InjuryRecord.objects
            .filter(anonymised_at__isnull=True, injury_date__lt=cutoff)
            .filter(Q(status='RECOVERED') | Q(medical_clearance=True))
            .exclude(photo='')
            .exclude(photo__isnull=True)
        )

        count = 0
        for record in queryset.iterator():
            if delete_injury_photo(record, reason, actor=actor, dry_run=dry_run):
                count += 1
                self.stdout.write(f'  delete photo for InjuryRecord #{record.pk}')
        return count

    def _anonymise_wellness(self, now, actor, dry_run):
        """Wellness check-ins, on the injury-record clock (CHPH, 25 Nov 2026).

        Scores are kept, notes are cleared, the athlete is replaced by the
        per-team placeholder. mood_score is arguably mental-health data, which
        is why the free text around it does not linger.
        """
        years = settings.RETENTION_SUPPORTING_RECORD_YEARS
        cutoff = (now - timedelta(days=365 * years)).date()
        reason = f'Retention: check-in older than {years} years'

        queryset = (
            WellnessCheckIn.objects
            .select_related('player__team')
            .filter(week_start__lt=cutoff)
            .exclude(player__username__startswith=PLACEHOLDER_PREFIX)
        )

        count = 0
        for checkin in queryset.iterator():
            if anonymise_wellness_checkin(checkin, reason, actor=actor, dry_run=dry_run):
                count += 1
                self.stdout.write(f'  anonymise WellnessCheckIn #{checkin.pk}')
        return count

    def _anonymise_appointments(self, now, actor, dry_run):
        """Appointment notes, on the injury-record clock (CHPH, 25 Nov 2026)."""
        years = settings.RETENTION_SUPPORTING_RECORD_YEARS
        cutoff = now - timedelta(days=365 * years)
        reason = f'Retention: appointment older than {years} years'

        queryset = (
            Appointment.objects
            .select_related('player__team', 'team')
            .filter(created_at__lt=cutoff)
            .exclude(player__username__startswith=PLACEHOLDER_PREFIX)
        )

        count = 0
        for appointment in queryset.iterator():
            if anonymise_appointment(appointment, reason, actor=actor, dry_run=dry_run):
                count += 1
                self.stdout.write(f'  anonymise Appointment #{appointment.pk}')
        return count

    def _clear_emergency_contacts(self, now, actor, dry_run):
        """Emergency contacts, removed when the athlete leaves.

        Nothing in the system records a departure, so a deactivated account is
        used as the proxy. PROCESS DEPENDENCY: this only fires if leavers'
        accounts are actually deactivated. Placeholder accounts are skipped -
        they are inactive by construction and hold no contact details anyway.
        """
        days = settings.RETENTION_EMERGENCY_CONTACT_DAYS
        cutoff = now - timedelta(days=days)
        reason = 'Retention: account deactivated'

        # last_login is NULL for anyone who never signed in. Without the
        # isnull branch those accounts would never match and their emergency
        # contacts would sit here indefinitely.
        queryset = (
            User.objects
            .filter(is_active=False)
            .filter(Q(last_login__lt=cutoff) | Q(last_login__isnull=True))
            .exclude(username__startswith=PLACEHOLDER_PREFIX)
        )

        count = 0
        for user in queryset.iterator():
            if clear_emergency_contacts(user, reason, actor=actor, dry_run=dry_run):
                count += 1
                self.stdout.write(f'  clear emergency contacts for user #{user.pk}')
        return count

    def _delete_orphan_uploads(self, now, actor, dry_run):
        """Clear the dead _pending_profile/ directory.

        The removed self-registration flow wrote an unauthenticated visitor's
        upload there, named after their session key, and never cleaned up.
        The flow is gone; these are its leftovers.
        """
        days = settings.RETENTION_PENDING_UPLOAD_DAYS
        folder = os.path.join(str(settings.MEDIA_ROOT), '_pending_profile')
        if not os.path.isdir(folder):
            return 0

        cutoff = (now - timedelta(days=days)).timestamp()
        count = 0
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not os.path.isfile(path) or os.path.getmtime(path) >= cutoff:
                continue
            count += 1
            self.stdout.write(f'  delete orphaned upload {name}')
            if dry_run:
                continue
            try:
                os.remove(path)
            except OSError as exc:
                self.stderr.write(f'  could not delete {name}: {exc}')
                count -= 1
                continue
            record_ledger('PendingUpload', f'_pending_profile/{name}',
                          PurgeLedgerEntry.ACTION_FILE_DELETE,
                          reason='Orphan from removed self-registration flow',
                          actor=actor)
        return count
