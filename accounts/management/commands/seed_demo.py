"""
Management command: seed_demo
Creates realistic demo data for LancersPulse — one team, four users
(one per role), a set of injury records, follow-ups, and notifications.

Usage:
    python manage.py seed_demo           # idempotent — skips existing objects
    python manage.py seed_demo --flush   # wipe then reseed
"""
import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed demo data (team, users, injuries, notifications)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing demo data before seeding',
        )

    def handle(self, *args, **options):
        from accounts.models import Team, Notification
        from injury_tracking.models import (
            InjuryRecord, InjuryType, BodyPart, InjurySeverity,
            InjuryFollowUp, TeamRoster,
        )

        if options['flush']:
            self.stdout.write(self.style.WARNING('Flushing demo data...'))
            Notification.objects.all().delete()
            InjuryFollowUp.objects.all().delete()
            InjuryRecord.objects.all().delete()
            TeamRoster.objects.all().delete()
            User.objects.filter(username__in=[
                'demo_admin', 'demo_doctor', 'demo_coach',
                'demo_player1', 'demo_player2',
            ]).delete()
            Team.objects.filter(name='Lancers FC Demo').delete()

        # ── Team ──────────────────────────────────────────────────────────────
        team, _ = Team.objects.get_or_create(
            name='Lancers FC Demo',
            defaults={},
        )
        self.stdout.write(f'  Team: {team}')

        # ── Reference data ────────────────────────────────────────────────────
        injury_types = {
            'Sprain': InjuryType.objects.get_or_create(name='Sprain')[0],
            'Strain': InjuryType.objects.get_or_create(name='Strain')[0],
            'Fracture': InjuryType.objects.get_or_create(name='Fracture')[0],
            'Concussion': InjuryType.objects.get_or_create(name='Concussion')[0],
            'Contusion': InjuryType.objects.get_or_create(name='Contusion')[0],
        }
        body_parts = {
            'Ankle': BodyPart.objects.get_or_create(name='Ankle')[0],
            'Knee': BodyPart.objects.get_or_create(name='Knee')[0],
            'Shoulder': BodyPart.objects.get_or_create(name='Shoulder')[0],
            'Head': BodyPart.objects.get_or_create(name='Head')[0],
            'Hamstring': BodyPart.objects.get_or_create(name='Hamstring')[0],
        }
        severities = {
            'Mild': InjurySeverity.objects.get_or_create(name='Mild', defaults={'color_code': '#28a745'})[0],
            'Moderate': InjurySeverity.objects.get_or_create(name='Moderate', defaults={'color_code': '#ffc107'})[0],
            'Severe': InjurySeverity.objects.get_or_create(name='Severe', defaults={'color_code': '#dc3545'})[0],
        }

        # ── Users ─────────────────────────────────────────────────────────────
        def get_or_create_user(username, role, first, last, password='Demo1234!'):
            u, created = User.objects.get_or_create(
                username=username,
                defaults=dict(
                    email=f'{username}@lancerspulse.demo',
                    first_name=first,
                    last_name=last,
                    role=role,
                    team=team,
                    is_registration_complete=True,
                    is_staff=(role == 'ADMIN'),
                    is_superuser=(role == 'ADMIN'),
                ),
            )
            if created:
                u.set_password(password)
                u.save()
                self.stdout.write(f'  Created {role}: {username} / {password}')
            else:
                self.stdout.write(f'  Skipped (exists): {username}')
            return u

        admin  = get_or_create_user('demo_admin',   'ADMIN',  'Alex',  'Admin')
        doctor = get_or_create_user('demo_doctor',  'DOCTOR', 'Dana',  'Doctor')
        coach  = get_or_create_user('demo_coach',   'COACH',  'Chris', 'Coach')
        player1 = get_or_create_user('demo_player1', 'PLAYER', 'Pat',   'Player')
        player2 = get_or_create_user('demo_player2', 'PLAYER', 'Sam',   'Striker')

        # ── Team roster ───────────────────────────────────────────────────────
        for p in [player1, player2]:
            TeamRoster.objects.get_or_create(team=team, player=p)

        # ── Injury records ────────────────────────────────────────────────────
        today = datetime.date.today()

        injuries_data = [
            # (player, date offset, body_part, inj_type, severity, status, description)
            (player1, -45, 'Ankle',    'Sprain',    'Moderate', 'ACTIVE',
             'Grade II ankle sprain sustained during a training match. Physio treatment ongoing.'),
            (player1, -120, 'Knee',    'Strain',    'Mild',     'RECOVERED',
             'Minor quadriceps strain from overuse. Fully recovered after rest and physio.'),
            (player2, -10, 'Shoulder', 'Contusion', 'Mild',     'ACTIVE',
             'Shoulder contusion after a collision. Ice treatment and rest prescribed.'),
            (player2, -200, 'Head',    'Concussion', 'Severe',  'RECOVERED',
             'Mild concussion sustained in a heading duel. Graduated return-to-play protocol completed.'),
            (player1, -7,  'Hamstring', 'Strain',   'Moderate', 'UNDER_REVIEW',
             'Hamstring tightness developed during warm-up. MRI scheduled.'),
        ]

        created_injuries = []
        for player, day_offset, bp_name, it_name, sev_name, status, desc in injuries_data:
            inj, created = InjuryRecord.objects.get_or_create(
                player=player,
                injury_date=today + datetime.timedelta(days=day_offset),
                injury_type=injury_types[it_name],
                defaults=dict(
                    body_part=body_parts[bp_name],
                    severity=severities[sev_name],
                    status=status,
                    description=desc,
                    reported_by=doctor,
                    medical_clearance=(status == 'RECOVERED'),
                ),
            )
            if created:
                self.stdout.write(f'  Injury: {inj}')
            created_injuries.append(inj)

        # ── Follow-ups ────────────────────────────────────────────────────────
        active_injuries = [i for i in created_injuries if i.status == 'ACTIVE']
        for inj in active_injuries:
            InjuryFollowUp.objects.get_or_create(
                injury=inj,
                follow_up_date=inj.injury_date + datetime.timedelta(days=7),
                defaults=dict(
                    notes='Initial follow-up: responding well to treatment. Continue physio.',
                    status_update='ACTIVE',
                    created_by=doctor,
                ),
            )

        # ── Notifications ─────────────────────────────────────────────────────
        notif_data = [
            (player1, 'Your ankle sprain has been reviewed by Dr. Doctor.', 'INJURY', True),
            (player1, 'Follow-up appointment scheduled for your hamstring strain.', 'APPOINTMENT', False),
            (player2, 'Your shoulder contusion has been logged. Rest and ice recommended.', 'INJURY', True),
            (player2, 'Medical clearance granted for your concussion recovery.', 'CLEARANCE', True),
            (doctor,  'New injury report submitted by Pat Player (Hamstring Strain).', 'INJURY', False),
            (coach,   'Sam Striker has been flagged with an active shoulder injury.', 'INJURY', False),
            (admin,   'Injury report #1 requires admin review.', 'EVENT', True),
        ]

        for user, msg, ntype, is_read in notif_data:
            n, created = Notification.objects.get_or_create(
                user=user,
                message=msg,
                defaults=dict(notification_type=ntype, is_read=is_read),
            )
            if created:
                self.stdout.write(f'  Notification -> {user.username}: {msg[:50]}...')

        self.stdout.write(self.style.SUCCESS('\nDemo data seeded successfully!'))
        self.stdout.write('\nDemo credentials (all passwords: Demo1234!):')
        self.stdout.write('  Admin:  demo_admin')
        self.stdout.write('  Doctor: demo_doctor')
        self.stdout.write('  Coach:  demo_coach')
        self.stdout.write('  Player: demo_player1, demo_player2')
