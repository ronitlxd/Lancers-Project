"""
injury_tracking/retention.py

Retention operations shared by the purge and replay commands.

UWindsor IT review, finding 5.  IT Services supports anonymising rather than
deleting so year-over-year injury trends survive, and deleting identifying
photographs when the related record is anonymised (their response, 3.16).

Anonymising repoints the record at a PER-TEAM placeholder athlete rather than
a single global one.  That is deliberate: the analytics group by
``player__team``, so a single placeholder would silently drop every anonymised
record out of team reporting - exactly the history the exercise is meant to
preserve.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from lancer_project.audit import audit

from .models import PurgeLedgerEntry

User = get_user_model()

ANON_FIRST_NAME = 'Anonymised'
ANON_LAST_NAME = 'Athlete'


def placeholder_athlete_for(team):
    """Return (creating if needed) the placeholder athlete for a team."""
    username = f'anonymised_team_{team.id}' if team else 'anonymised_no_team'
    user, _created = User.objects.get_or_create(
        username=username,
        defaults={
            'first_name': ANON_FIRST_NAME,
            'last_name': ANON_LAST_NAME,
            'role': 'PLAYER',
            'team': team,
            'is_active': False,          # can never sign in
            'is_registration_complete': True,
            'email': '',
        },
    )
    return user


def record_ledger(target_type, target_id, action, reason='', actor='system'):
    """Write the ledger row and emit the matching audit event.

    The audit event is the copy that survives a database restore: it is
    written to stderr and forwarded off the host to the University SIEM,
    whereas ledger rows live in the database that gets rolled back.
    """
    entry, created = PurgeLedgerEntry.objects.get_or_create(
        target_type=target_type,
        target_id=str(target_id),
        action=action,
        defaults={'reason': reason, 'performed_by': actor},
    )
    if created:
        audit(
            'RETENTION_ACTION',
            actor=None,
            request=None,
            retention_action=action,
            target_type=target_type,
            target_id=str(target_id),
            reason=reason,
            performed_by=actor,
        )
    return created


def delete_injury_photo(record, reason, actor='system', dry_run=False):
    """Delete the photograph attached to an injury record."""
    if not record.photo:
        return False
    if dry_run:
        return True
    name = record.photo.name
    record.photo.delete(save=False)
    record.photo = ''
    record.save(update_fields=['photo'])
    record_ledger('InjuryRecord', record.pk,
                  PurgeLedgerEntry.ACTION_PHOTO_DELETE,
                  reason=f'{reason} (file {name})', actor=actor)
    return True


def anonymise_injury_record(record, reason, actor='system', dry_run=False):
    """Strip personal detail from an injury record, keeping its analytics.

    Removed: the athlete and reporter links, every free-text field, and the
    photograph.  Kept: team (via the placeholder), body part, injury type,
    severity, dates, contact type, missed games and practices, season.
    """
    if record.anonymised_at:
        return False
    if dry_run:
        return True

    team = record.player.team if record.player_id else None
    placeholder = placeholder_athlete_for(team)

    delete_injury_photo(record, reason=f'{reason} (record anonymised)',
                        actor=actor)

    record.player = placeholder
    record.reported_by = placeholder
    record.description = ''
    record.symptoms = ''
    record.treatment_notes = ''
    record.follow_up_notes = ''
    record.is_confidential = False
    record.anonymised_at = timezone.now()
    record.save()

    record_ledger('InjuryRecord', record.pk,
                  PurgeLedgerEntry.ACTION_ANONYMISE,
                  reason=reason, actor=actor)
    return True
