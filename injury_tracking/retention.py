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

# Placeholder accounts are identified by this username prefix.  Used to keep
# already-anonymised rows out of the purge queries without adding an
# `anonymised_at` column to every supporting model.
PLACEHOLDER_PREFIX = 'anonymised_'


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


def anonymise_wellness_checkin(checkin, reason, actor='system', dry_run=False):
    """Strip the free text from a wellness check-in, keep the scores.

    Agreed with CHPH on 25 Nov 2026: same clock as injury records.  The sleep,
    pain and mood scores are the analytic value and survive; the notes are
    where a person describes themselves and do not.
    """
    if checkin.player.username.startswith(PLACEHOLDER_PREFIX):
        return False
    if dry_run:
        return True

    placeholder = placeholder_athlete_for(checkin.player.team)
    checkin.player = placeholder
    checkin.notes = ''
    checkin.save(update_fields=['player', 'notes'])

    record_ledger('WellnessCheckIn', checkin.pk,
                  PurgeLedgerEntry.ACTION_ANONYMISE,
                  reason=reason, actor=actor)
    return True


def anonymise_appointment(appointment, reason, actor='system', dry_run=False):
    """Strip the free text from an appointment and detach the athlete."""
    if appointment.player.username.startswith(PLACEHOLDER_PREFIX):
        return False
    if dry_run:
        return True

    placeholder = placeholder_athlete_for(appointment.team or appointment.player.team)
    appointment.player = placeholder
    appointment.note = ''
    appointment.save(update_fields=['player', 'note'])

    record_ledger('Appointment', appointment.pk,
                  PurgeLedgerEntry.ACTION_ANONYMISE,
                  reason=reason, actor=actor)
    return True


def clear_emergency_contacts(user, reason, actor='system', dry_run=False):
    """Remove emergency contact details from a departed athlete's account.

    These describe a THIRD PARTY who never used the system and was never asked,
    which is why they go as soon as the athlete leaves rather than on the
    longer clinical clock.
    """
    fields = (
        'emergency_contact_name',
        'emergency_contact_phone',
        'emergency_contact_relationship',
        'emergency_contact_email',
    )
    if not any(getattr(user, f, '') for f in fields):
        return False
    if dry_run:
        return True

    for field in fields:
        setattr(user, field, '')
    user.save(update_fields=list(fields))

    record_ledger('CustomUser', user.pk,
                  PurgeLedgerEntry.ACTION_ANONYMISE,
                  reason=reason, actor=actor)
    return True
