"""
injury_tracking/tests.py - Tests for export views, permission guards,
photo validation, and injury CRUD access control.
"""
import io
import csv
import zlib
import struct
import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Team
from injury_tracking.models import InjuryRecord, InjuryType, BodyPart, InjurySeverity
from injury_tracking.forms import _validate_and_resize_photo, PHOTO_MAX_SIZE_MB

User = get_user_model()


# -- Helpers -------------------------------------------------------------------

def make_team(name="Lancers"):
    return Team.objects.create(name=name)


def make_user(role, username, team=None, password="testpass123"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password=password,
        role=role,
        team=team,
        is_registration_complete=True,
    )


def make_severity(name):
    return InjurySeverity.objects.create(name=name, color_code="#FF0000")


def make_injury(player, body_part, injury_type, severity, status="ACTIVE", reported_by=None):
    return InjuryRecord.objects.create(
        player=player,
        reported_by=reported_by or player,
        injury_date=datetime.date(2025, 1, 15),
        body_part=body_part,
        injury_type=injury_type,
        severity=severity,
        status=status,
        description="Test injury description.",
    )


def minimal_png():
    """Programmatically generate a valid 1x1 RGB PNG (correct CRC checksums)."""
    def make_chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    # PNG signature (8 bytes)
    sig = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    # IHDR: width=1, height=1, bit_depth=8, color_type=2 (RGB), compress=0, filter=0, interlace=0
    ihdr = make_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    # IDAT: filter_byte=0, R=255, G=0, B=0 (red pixel)
    raw_pixel = bytes([0, 255, 0, 0])
    idat = make_chunk(b"IDAT", zlib.compress(raw_pixel))
    iend = make_chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


# -- Photo Validation ----------------------------------------------------------

class PhotoValidationTests(TestCase):
    def _make_file(self, name, content, content_type="image/png"):
        return SimpleUploadedFile(name, content, content_type=content_type)

    def test_valid_png_passes(self):
        f = self._make_file("photo.png", minimal_png())
        result = _validate_and_resize_photo(f)
        self.assertIsNotNone(result)

    def test_invalid_extension_rejected(self):
        from django.forms import ValidationError
        f = self._make_file("photo.exe", b"fake data", "application/octet-stream")
        with self.assertRaises(ValidationError) as ctx:
            _validate_and_resize_photo(f)
        self.assertIn("Unsupported file type", str(ctx.exception))

    def test_oversized_file_rejected(self):
        from django.forms import ValidationError
        big = b"X" * (PHOTO_MAX_SIZE_MB * 1024 * 1024 + 1)
        f = self._make_file("big.png", big)
        with self.assertRaises(ValidationError) as ctx:
            _validate_and_resize_photo(f)
        self.assertIn("too large", str(ctx.exception))

    def test_corrupt_image_rejected(self):
        from django.forms import ValidationError
        f = self._make_file("bad.png", b"not a real png at all")
        with self.assertRaises(ValidationError):
            _validate_and_resize_photo(f)

    def test_none_returns_none(self):
        self.assertIsNone(_validate_and_resize_photo(None))


# -- Export Views: access control ----------------------------------------------

class ExportAccessTests(TestCase):
    def setUp(self):
        self.team = make_team()
        self.admin  = make_user("ADMIN",  "admin1")
        self.doctor = make_user("DOCTOR", "doc1",   team=self.team)
        self.coach  = make_user("COACH",  "coach1",  team=self.team)
        self.player = make_user("PLAYER", "player1", team=self.team)

        bp = BodyPart.objects.create(name="Knee")
        it = InjuryType.objects.create(name="Sprain")
        sv = make_severity("Mild")
        make_injury(self.player, bp, it, sv)

        self.csv_url = reverse("tracking:export_injuries_csv")
        self.pdf_url = reverse("tracking:export_injuries_pdf")

    def _login(self, user):
        c = Client()
        c.force_login(user)   # bypasses axes backend
        return c

    def test_admin_can_export_csv(self):
        resp = self._login(self.admin).get(self.csv_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")

    def test_doctor_can_export_csv(self):
        resp = self._login(self.doctor).get(self.csv_url)
        self.assertEqual(resp.status_code, 200)

    def test_coach_can_export_csv(self):
        resp = self._login(self.coach).get(self.csv_url)
        self.assertEqual(resp.status_code, 200)

    def test_player_cannot_export_csv(self):
        resp = self._login(self.player).get(self.csv_url)
        self.assertEqual(resp.status_code, 302)

    def test_unauthenticated_redirected(self):
        resp = self.client.get(self.csv_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_csv_content_has_header_row(self):
        resp = self._login(self.admin).get(self.csv_url)
        content = resp.content.decode("utf-8")
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        self.assertIn("Player", header)
        self.assertIn("Status", header)
        self.assertIn("Body Part", header)

    def test_admin_can_export_pdf(self):
        resp = self._login(self.admin).get(self.pdf_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_player_cannot_export_pdf(self):
        resp = self._login(self.player).get(self.pdf_url)
        self.assertEqual(resp.status_code, 302)


# -- Doctor team-scoping on exports --------------------------------------------

class ExportScopingTests(TestCase):
    def setUp(self):
        self.team_a = make_team("Team A")
        self.team_b = make_team("Team B")
        self.doctor_a = make_user("DOCTOR", "doc_a", team=self.team_a)
        self.player_a = make_user("PLAYER", "play_a", team=self.team_a)
        self.player_b = make_user("PLAYER", "play_b", team=self.team_b)

        bp = BodyPart.objects.create(name="Ankle")
        it = InjuryType.objects.create(name="Fracture")
        sv = make_severity("Severe")
        make_injury(self.player_a, bp, it, sv)
        make_injury(self.player_b, bp, it, sv)

    def test_doctor_sees_only_own_team_in_csv(self):
        c = Client()
        c.force_login(self.doctor_a)
        resp = c.get(reverse("tracking:export_injuries_csv"))
        content = resp.content.decode("utf-8")
        self.assertIn("play_a", content)
        self.assertNotIn("play_b", content)


# -- Injury view permission guards ---------------------------------------------

class InjuryPermissionTests(TestCase):
    def setUp(self):
        self.team = make_team()
        self.doctor = make_user("DOCTOR", "doc",  team=self.team)
        self.player = make_user("PLAYER", "play", team=self.team)
        make_user("PLAYER", "otherplay")

        bp = BodyPart.objects.create(name="Shoulder")
        it = InjuryType.objects.create(name="Dislocation")
        sv = make_severity("Moderate")
        self.injury = make_injury(self.player, bp, it, sv)

    def test_player_can_view_own_injury(self):
        c = Client()
        c.force_login(self.player)
        resp = c.get(reverse("tracking:injury_detail", kwargs={"pk": self.injury.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_doctor_can_view_team_injury(self):
        c = Client()
        c.force_login(self.doctor)
        resp = c.get(reverse("tracking:injury_detail", kwargs={"pk": self.injury.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirected_from_injury_list(self):
        resp = self.client.get(reverse("tracking:injury_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])


# -- Protected injury photos (UWindsor IT review, findings 1 and 3) ------------

class InjuryPhotoAccessTests(TestCase):
    """Every read of a clinical photograph must pass the permission check.

    Denials are expected to be 404 rather than 403: a 403 would confirm that a
    photo exists for that injury, which is itself a disclosure.
    """

    def setUp(self):
        self.client = Client()
        self.team_a = make_team("Team A")
        self.team_b = make_team("Team B")

        self.admin = make_user("ADMIN", "admin_p")
        self.player = make_user("PLAYER", "player_a", team=self.team_a)
        self.other_player = make_user("PLAYER", "player_b", team=self.team_b)
        self.doctor_a = make_user("DOCTOR", "doc_team_a", team=self.team_a)
        self.doctor_b = make_user("DOCTOR", "doc_team_b", team=self.team_b)
        self.doctor_noteam = make_user("DOCTOR", "doc_noteam", team=None)
        self.coach_a = make_user("COACH", "coach_team_a", team=self.team_a)

        body_part = BodyPart.objects.create(name="Knee")
        injury_type = InjuryType.objects.create(name="Sprain")
        severity = make_severity("Moderate")
        self.injury = make_injury(self.player, body_part, injury_type, severity)
        self.injury.photo.save("original.png", SimpleUploadedFile(
            "original.png", minimal_png(), content_type="image/png"), save=True)

        self.url = reverse("serve_injury_photo", kwargs={"injury_id": self.injury.pk})

    def _get_as(self, user):
        self.client.force_login(user)
        return self.client.get(self.url)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_admin_may_view(self):
        self.assertEqual(self._get_as(self.admin).status_code, 200)

    def test_owning_player_may_view(self):
        self.assertEqual(self._get_as(self.player).status_code, 200)

    def test_other_player_may_not_view(self):
        self.assertEqual(self._get_as(self.other_player).status_code, 404)

    def test_doctor_on_same_team_may_view(self):
        self.assertEqual(self._get_as(self.doctor_a).status_code, 200)

    def test_doctor_on_other_team_may_not_view(self):
        self.assertEqual(self._get_as(self.doctor_b).status_code, 404)

    def test_doctor_without_team_may_not_view(self):
        """Regression: the old rule was `user.team is None or user.team == ...`,
        so a therapist with no team assignment could read every athlete's
        photos. Because CustomUser.team is on_delete=SET_NULL, deleting a Team
        silently promoted all of its staff to that level."""
        self.assertEqual(self._get_as(self.doctor_noteam).status_code, 404)

    def test_coach_may_not_view_clinical_image(self):
        """Coaches get restrictions and availability, not wound photographs.
        Pending CHPH decision B1; reverse here if that decision differs."""
        self.assertEqual(self._get_as(self.coach_a).status_code, 404)

    def test_doctor_with_granted_team_permission_may_view(self):
        from accounts.models import TeamPermission
        TeamPermission.objects.create(
            user=self.doctor_b, team=self.team_a, role_scope="DOCTOR")
        self.assertEqual(self._get_as(self.doctor_b).status_code, 200)

    def test_response_is_not_sniffable(self):
        response = self._get_as(self.admin)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Content-Type"], "image/png")

    def test_missing_photo_is_404_not_500(self):
        self.injury.photo = ""
        self.injury.save(update_fields=["photo"])
        self.assertEqual(self._get_as(self.admin).status_code, 404)

    def test_stored_filename_is_a_uuid(self):
        """The uploader's filename is discarded: it made URLs enumerable and
        could leak the athlete's name in the path."""
        import re
        self.assertRegex(
            self.injury.photo.name,
            r"^injury_photos/[0-9a-f]{32}\.(png|jpg|jpeg|webp)$",
        )
        self.assertNotIn("original", self.injury.photo.name)


class RawMediaPathTests(TestCase):
    """With DEBUG off, MEDIA_URL must not be routed at all."""

    def test_raw_media_path_is_not_served(self):
        # The test runner forces DEBUG=False, so urls.py registers no
        # static() route for MEDIA_URL.
        response = self.client.get("/media/injury_photos/anything.png")
        self.assertEqual(response.status_code, 404)


class SelfRegistrationRemovedTests(TestCase):
    """Public self-registration assigned roles from an unverified email address
    and wrote unauthenticated uploads into MEDIA_ROOT. Both routes are gone."""

    def test_register_is_gone(self):
        self.assertEqual(self.client.get("/register/").status_code, 404)
        self.assertEqual(self.client.post("/register/", {}).status_code, 404)

    def test_register_step2_is_gone(self):
        self.assertEqual(self.client.get("/register/step2/").status_code, 404)


class PhotoReEncodingTests(TestCase):
    """Uploads are always re-encoded, which strips EXIF (phone photos carry GPS
    and a device id) and means stored bytes are never client-supplied bytes."""

    def test_small_image_is_still_re_encoded(self):
        from django.core.files.uploadedfile import InMemoryUploadedFile
        original = SimpleUploadedFile(
            "tiny.png", minimal_png(), content_type="image/png")
        result = _validate_and_resize_photo(original)
        self.assertIsInstance(result, InMemoryUploadedFile)

    def test_exif_is_dropped(self):
        from PIL import Image
        buffer = io.BytesIO()
        image = Image.new("RGB", (32, 32), (120, 10, 10))
        exif = image.getexif()
        exif[0x010F] = "ACME Phone Co"      # Make
        image.save(buffer, format="JPEG", exif=exif)
        buffer.seek(0)
        self.assertIn(b"ACME Phone Co", buffer.getvalue())

        cleaned = _validate_and_resize_photo(
            SimpleUploadedFile("p.jpg", buffer.getvalue(), content_type="image/jpeg"))
        cleaned.seek(0)
        data = cleaned.read()
        self.assertNotIn(b"ACME Phone Co", data)
        self.assertFalse(Image.open(io.BytesIO(data)).getexif().get(0x010F))


# -- Retention and purge (UWindsor IT review, finding 5) ----------------------

import json
import os
import tempfile
from io import StringIO
from datetime import timedelta

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from injury_tracking.models import PurgeLedgerEntry


class RetentionPurgeTests(TestCase):
    def setUp(self):
        self.team = make_team("Purge FC")
        self.player = make_user("PLAYER", "purge_player", team=self.team)
        self.body_part = BodyPart.objects.create(name="Ankle")
        self.injury_type = InjuryType.objects.create(name="Strain")
        self.severity = make_severity("Mild")

    def _injury(self, with_photo=True, injury_date=None):
        injury = make_injury(
            self.player, self.body_part, self.injury_type, self.severity)
        injury.description = "Rolled it badly in the second half."
        injury.symptoms = "Swelling, bruising."
        injury.treatment_notes = "Ice and elevation."
        if injury_date:
            injury.injury_date = injury_date
        injury.save()
        if with_photo:
            injury.photo.save("p.png", SimpleUploadedFile(
                "p.png", minimal_png(), content_type="image/png"), save=True)
        return injury

    @staticmethod
    def _age(injury, days):
        """Backdate updated_at, which is auto_now and cannot be set normally."""
        InjuryRecord.objects.filter(pk=injury.pk).update(
            updated_at=timezone.now() - timedelta(days=days))

    def _run(self, *args):
        out = StringIO()
        call_command('purge_expired_data', *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    # -- the rules -----------------------------------------------------------

    def test_dry_run_changes_nothing(self):
        injury = self._injury()
        self._age(injury, days=365 * 9)
        output = self._run('--dry-run')

        injury.refresh_from_db()
        self.assertIsNone(injury.anonymised_at)
        self.assertTrue(injury.photo)
        self.assertEqual(injury.description, "Rolled it badly in the second half.")
        self.assertEqual(PurgeLedgerEntry.objects.count(), 0)
        self.assertIn('DRY RUN', output)

    def test_recent_record_is_left_alone(self):
        injury = self._injury(injury_date=timezone.localdate())
        self._run()
        injury.refresh_from_db()
        self.assertIsNone(injury.anonymised_at)
        self.assertTrue(injury.photo)

    def test_expired_record_is_anonymised(self):
        injury = self._injury()
        self._age(injury, days=365 * 9)
        self._run()

        injury.refresh_from_db()
        self.assertIsNotNone(injury.anonymised_at)
        self.assertEqual(injury.description, '')
        self.assertEqual(injury.symptoms, '')
        self.assertEqual(injury.treatment_notes, '')
        self.assertFalse(injury.photo)
        self.assertNotEqual(injury.player_id, self.player.pk)
        self.assertEqual(injury.player.first_name, 'Anonymised')
        self.assertFalse(injury.player.is_active)

    def test_anonymised_record_keeps_its_analytics(self):
        """The whole point of anonymising rather than deleting: team, body
        part, severity, season and missed time must survive."""
        injury = self._injury()
        injury.missed_games = 4
        injury.save()
        season = injury.season_year
        self._age(injury, days=365 * 9)
        self._run()

        injury.refresh_from_db()
        self.assertEqual(injury.player.team_id, self.team.pk,
                         'team must survive via the per-team placeholder, or '
                         'the record drops out of team analytics')
        self.assertEqual(injury.body_part_id, self.body_part.pk)
        self.assertEqual(injury.severity_id, self.severity.pk)
        self.assertEqual(injury.missed_games, 4)
        self.assertEqual(injury.season_year, season)

    def test_one_placeholder_per_team_is_reused(self):
        first, second = self._injury(), self._injury()
        self._age(first, days=365 * 9)
        self._age(second, days=365 * 9)
        self._run()

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.player_id, second.player_id)

    def test_expired_photo_deleted_without_anonymising_record(self):
        injury = self._injury(
            injury_date=timezone.localdate() - timedelta(days=400))
        self._run()

        injury.refresh_from_db()
        self.assertFalse(injury.photo, 'photo past its shorter clock')
        self.assertIsNone(injury.anonymised_at, 'record itself is not expired')
        self.assertEqual(injury.description, "Rolled it badly in the second half.")

    @override_settings(RETENTION_INJURY_PHOTO_DAYS=36500)
    def test_photo_retention_period_is_configurable(self):
        injury = self._injury(
            injury_date=timezone.localdate() - timedelta(days=400))
        self._run()
        injury.refresh_from_db()
        self.assertTrue(injury.photo)

    # -- the ledger ----------------------------------------------------------

    def test_ledger_records_each_action(self):
        injury = self._injury()
        self._age(injury, days=365 * 9)
        self._run()

        actions = set(PurgeLedgerEntry.objects.filter(
            target_id=str(injury.pk)).values_list('action', flat=True))
        self.assertIn(PurgeLedgerEntry.ACTION_ANONYMISE, actions)
        self.assertIn(PurgeLedgerEntry.ACTION_PHOTO_DELETE, actions)

    def test_running_twice_is_idempotent(self):
        injury = self._injury()
        self._age(injury, days=365 * 9)
        self._run()
        before = PurgeLedgerEntry.objects.count()
        self._run()
        self.assertEqual(PurgeLedgerEntry.objects.count(), before)


class PurgeLedgerReplayTests(TestCase):
    """After a restore, deletions have to be re-applied (IT response, 1.8)."""

    def setUp(self):
        self.team = make_team("Replay United")
        self.player = make_user("PLAYER", "replay_player", team=self.team)
        self.injury = make_injury(
            self.player,
            BodyPart.objects.create(name="Shoulder"),
            InjuryType.objects.create(name="Dislocation"),
            make_severity("Severe"),
        )
        self.injury.description = "Identifiable clinical detail."
        self.injury.save()

    def test_export_then_replay_reapplies_the_action(self):
        # An action taken outside the retention rules, e.g. an erasure request.
        from injury_tracking.retention import anonymise_injury_record
        anonymise_injury_record(self.injury, 'Erasure request', actor='admin')

        path = os.path.join(tempfile.mkdtemp(), 'ledger.json')
        call_command('replay_purge_ledger', '--export', path, stdout=StringIO())
        with open(path, encoding='utf-8') as fh:
            exported = json.load(fh)
        self.assertTrue(any(e['action'] == PurgeLedgerEntry.ACTION_ANONYMISE
                            for e in exported))

        # Simulate the restore: the record comes back, and so does the ledger
        # row, because the backup predates the purge.
        InjuryRecord.objects.filter(pk=self.injury.pk).update(
            anonymised_at=None,
            player=self.player,
            description='Identifiable clinical detail.',
        )
        PurgeLedgerEntry.objects.all().delete()

        call_command('replay_purge_ledger', '--from-file', path,
                     stdout=StringIO())

        self.injury.refresh_from_db()
        self.assertIsNotNone(self.injury.anonymised_at)
        self.assertEqual(self.injury.description, '')

    def test_replay_dry_run_changes_nothing(self):
        from injury_tracking.retention import anonymise_injury_record
        anonymise_injury_record(self.injury, 'Erasure request', actor='admin')
        path = os.path.join(tempfile.mkdtemp(), 'ledger.json')
        call_command('replay_purge_ledger', '--export', path, stdout=StringIO())

        InjuryRecord.objects.filter(pk=self.injury.pk).update(
            anonymised_at=None, description='Back from backup.')

        call_command('replay_purge_ledger', '--from-file', path, '--dry-run',
                     stdout=StringIO())
        self.injury.refresh_from_db()
        self.assertIsNone(self.injury.anonymised_at)
        self.assertEqual(self.injury.description, 'Back from backup.')

    def test_replay_tolerates_a_missing_target(self):
        path = os.path.join(tempfile.mkdtemp(), 'ledger.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump([{'target_type': 'InjuryRecord', 'target_id': '999999',
                        'action': PurgeLedgerEntry.ACTION_ANONYMISE,
                        'reason': 'gone'}], fh)
        out = StringIO()
        call_command('replay_purge_ledger', '--from-file', path, stdout=out)
        self.assertIn('target no longer present: 1', out.getvalue())
