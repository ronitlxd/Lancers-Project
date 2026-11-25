"""
injury_tracking/permissions.py

Single home for authorization decisions about injury records and their
attachments.  Keeping these in one module means there is exactly one place to
read when answering "who can see clinical data?", and exactly one place to
change when CHPH or University IT revise the rules.

Context (UWindsor IT deployment review, Nov 2026):

* Finding 1 - injury photos were reachable without an authorization check.
* Finding 3 - role assignment was built for a demo environment.

Two deliberate differences from the previous inline checks:

1.  A user whose ``team`` is NULL no longer receives blanket access.  The old
    rule (``user.team is None or user.team == injury.player.team``) meant any
    therapist or coach without a team assignment could read every athlete's
    records - and because ``CustomUser.team`` is ``on_delete=SET_NULL``,
    deleting a Team silently promoted all of its staff.  Legitimate multi-team
    access now goes through ``TeamPermission``, which carries an admin approval
    workflow (``TeamPermissionRequest``).

2.  Coaches are not granted access to clinical images.  Coaches need
    availability and training restrictions, not wound photographs.

    PENDING: CHPH decision B1 has not been returned.  If Dr. Sutherland decides
    coaches should see injury photos, add a COACH branch to
    ``can_view_injury_photo`` mirroring the DOCTOR branch with scope 'COACH'.
"""

from accounts.models import TeamPermission


def _has_team_access(user, team_id, scope):
    """True if ``user`` may act on ``team_id`` under ``scope``.

    ``scope`` is a ``TeamPermission.ROLE_SCOPE_CHOICES`` value ('COACH',
    'DOCTOR', 'ADMIN').  A NULL team never grants access.
    """
    if team_id is None:
        return False
    if user.team_id == team_id:
        return True
    return TeamPermission.objects.filter(
        user=user, team_id=team_id, role_scope=scope
    ).exists()


def can_view_injury_photo(user, injury) -> bool:
    """Authorize access to the photograph attached to an injury record.

    Callers must treat a False result as "not found" rather than "forbidden",
    so the response does not confirm that the photo exists.
    """
    if not user.is_authenticated:
        return False
    if user.role == 'ADMIN':
        return True
    if user.role == 'PLAYER':
        return injury.player_id == user.id
    if user.role == 'DOCTOR':
        return _has_team_access(user, injury.player.team_id, 'DOCTOR')
    return False


def can_view_injury(user, injury) -> bool:
    """Authorize access to an injury record's non-image detail.

    Wider than ``can_view_injury_photo``: coaches need to know who is injured
    and what they cannot do, which is why they are permitted here and excluded
    above.
    """
    if not user.is_authenticated:
        return False
    if user.role == 'ADMIN':
        return True
    if user.role == 'PLAYER':
        return injury.player_id == user.id
    if user.role in ('DOCTOR', 'COACH'):
        return _has_team_access(user, injury.player.team_id, user.role)
    return False
