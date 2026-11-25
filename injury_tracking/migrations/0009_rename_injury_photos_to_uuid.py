"""
Rename existing injury photographs to unguessable UUID filenames.

Before this migration, ``upload_to='injury_photos/'`` kept whatever filename
the uploader's device supplied.  That made photo URLs enumerable and could
disclose the athlete in the path itself.  Migration 0008 changed the field to
use ``injury_photo_path``; this one brings already-stored files into line.

Safe to run with no media present: rows whose file is missing from storage are
left untouched rather than pointed at a path that does not exist.
Irreversible by design - the original filenames are what we are removing.
"""

import re
import uuid
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import migrations

UUID_NAME = re.compile(r'^injury_photos/[0-9a-f]{32}\.(jpg|jpeg|png|webp)$')
ALLOWED_EXT = ('.jpg', '.jpeg', '.png', '.webp')


def rename_to_uuid(apps, schema_editor):
    InjuryRecord = apps.get_model('injury_tracking', 'InjuryRecord')

    qs = InjuryRecord.objects.exclude(photo='').exclude(photo__isnull=True)
    for record in qs.iterator():
        old_name = record.photo.name
        if not old_name or UUID_NAME.match(old_name):
            continue
        if not default_storage.exists(old_name):
            # Row references a file that is not in storage; leave it alone so
            # the inconsistency stays visible instead of being papered over.
            continue

        ext = PurePosixPath(old_name).suffix.lower()
        if ext not in ALLOWED_EXT:
            ext = '.jpg'
        new_name = f'injury_photos/{uuid.uuid4().hex}{ext}'

        with default_storage.open(old_name, 'rb') as fh:
            saved_name = default_storage.save(new_name, ContentFile(fh.read()))

        record.photo.name = saved_name
        record.save(update_fields=['photo'])

        try:
            default_storage.delete(old_name)
        except OSError:
            # The new copy and the database are already consistent; a stale
            # original is a cleanup problem, not a failed migration.
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('injury_tracking', '0008_alter_injuryrecord_photo'),
    ]

    operations = [
        migrations.RunPython(rename_to_uuid, migrations.RunPython.noop),
    ]
