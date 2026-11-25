"""
Re-apply retention actions after a restore from backup.

UWindsor IT review, finding 5.  IT Services: "Application deletions are not
expected to propagate to backup copies, so deletions may need to be reapplied
after a restore" (their response, section 1.8).

Order of operations after restoring a backup:

  1.  python manage.py purge_expired_data
          Re-applies everything the retention rules imply.  Deterministic, so
          it needs no memory of what was purged before.

  2.  python manage.py replay_purge_ledger --from-file ledger.json
          Re-applies actions the rules do NOT imply: an erasure request, or an
          early deletion agreed with CHPH.  Those cannot be recomputed, and a
          backup taken before them also rolls back the ledger rows describing
          them - which is why the export exists and why every ledger entry is
          mirrored to the audit log.

Export the ledger regularly so a current copy exists outside the database:

    python manage.py replay_purge_ledger --export ledger.json

Running with neither flag replays the ledger rows found in the database, which
is useful only when the restore postdates the purge.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from injury_tracking.models import InjuryRecord, PurgeLedgerEntry
from injury_tracking.retention import (
    anonymise_injury_record,
    delete_injury_photo,
)


class Command(BaseCommand):
    help = 'Export the purge ledger, or replay it after restoring a backup.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--export', metavar='PATH',
            help='Write the ledger to a JSON file and exit.')
        parser.add_argument(
            '--from-file', metavar='PATH',
            help='Replay entries from a JSON export instead of the database.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be re-applied without writing anything.')

    def handle(self, *args, **options):
        if options['export']:
            return self._export(options['export'])

        entries = (
            self._load_file(options['from_file'])
            if options['from_file']
            else self._load_db()
        )
        self._replay(entries, dry_run=options['dry_run'])

    # -- export --------------------------------------------------------------

    def _export(self, path):
        rows = [
            {
                'target_type': e.target_type,
                'target_id': e.target_id,
                'action': e.action,
                'reason': e.reason,
                'performed_at': e.performed_at.isoformat(),
                'performed_by': e.performed_by,
            }
            for e in PurgeLedgerEntry.objects.all().order_by('performed_at')
        ]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(rows, fh, indent=2)
        self.stdout.write(self.style.SUCCESS(
            f'Exported {len(rows)} ledger entries to {path}'))

    # -- loading -------------------------------------------------------------

    def _load_db(self):
        self.stdout.write(
            'Replaying ledger entries from the database. Note that a restore '
            'predating a purge also rolls back its ledger rows - use '
            '--from-file with an export taken before the restore.')
        return [
            {'target_type': e.target_type, 'target_id': e.target_id,
             'action': e.action, 'reason': e.reason}
            for e in PurgeLedgerEntry.objects.all()
        ]

    def _load_file(self, path):
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise CommandError(f'Could not read ledger export {path}: {exc}')
        if not isinstance(data, list):
            raise CommandError(f'{path} does not contain a list of entries.')
        return data

    # -- replay --------------------------------------------------------------

    def _replay(self, entries, dry_run):
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - nothing will be written.'))

        applied = skipped = missing = 0

        for entry in entries:
            action = entry.get('action')
            target_type = entry.get('target_type')
            target_id = entry.get('target_id')
            reason = entry.get('reason') or 'Replayed after restore'

            if target_type != 'InjuryRecord':
                # FILE_DELETE entries refer to files that a database restore
                # does not bring back, so there is nothing to re-apply.
                skipped += 1
                continue

            record = InjuryRecord.objects.filter(pk=target_id).first()
            if record is None:
                missing += 1
                continue

            if action == PurgeLedgerEntry.ACTION_ANONYMISE:
                changed = anonymise_injury_record(
                    record, reason, actor='replay', dry_run=dry_run)
            elif action == PurgeLedgerEntry.ACTION_PHOTO_DELETE:
                changed = delete_injury_photo(
                    record, reason, actor='replay', dry_run=dry_run)
            else:
                skipped += 1
                continue

            if changed:
                applied += 1
                self.stdout.write(f'  re-applied {action} to InjuryRecord #{target_id}')
            else:
                skipped += 1

        self.stdout.write('')
        self.stdout.write(f're-applied: {applied}')
        self.stdout.write(f'already correct or not replayable: {skipped}')
        self.stdout.write(f'target no longer present: {missing}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run complete.'))
        else:
            self.stdout.write(self.style.SUCCESS('Replay complete.'))
