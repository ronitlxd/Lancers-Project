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
