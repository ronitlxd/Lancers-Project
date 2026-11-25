"""
Stop collecting the student ID photo, and delete the images already held.

UWindsor IT review, finding 2: player ID photographs were reachable by direct
link with no access control. Asked whether the image was needed at all, CHPH
answered that collection can stop (25 Nov 2026), so the finding is closed by
removal rather than by adding access control around data nobody uses.

The stored files are deleted before the column is dropped. Once the column is
gone the paths are unrecoverable, so the order matters.

Note for the privacy review: deleted files persist in backups until those age
out. IT Services confirmed application deletions do not propagate to backup
copies (their response, section 1.8).
"""

from django.db import migrations


def delete_player_id_images(apps, schema_editor):
    PlayerProfile = apps.get_model('accounts', 'PlayerProfile')
    from django.core.files.storage import default_storage

    deleted = 0
    for profile in PlayerProfile.objects.exclude(photo_id='').exclude(
            photo_id__isnull=True).iterator():
        name = profile.photo_id.name
        if not name:
            continue
        try:
            if default_storage.exists(name):
                default_storage.delete(name)
                deleted += 1
        except OSError:
            # A file we cannot remove here is reported rather than silently
            # skipped: the column is about to be dropped, so this is the last
            # chance to act on it from the application.
            print(f'  WARNING: could not delete {name}; remove it manually')
    if deleted:
        print(f'  deleted {deleted} student ID image(s)')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_customuser_entra_oid_customuser_entra_upn'),
    ]

    operations = [
        migrations.RunPython(delete_player_id_images, migrations.RunPython.noop),
        migrations.RemoveField(model_name='playerprofile', name='photo_id'),
    ]
