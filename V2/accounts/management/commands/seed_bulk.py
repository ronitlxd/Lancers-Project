"""
Management command: seed_bulk
Creates 5 teams, 40 players, 5 coaches, 5 doctors, injury records,
follow-ups, and notifications for a realistic demo dataset.

Usage:
    python manage.py seed_bulk
    python manage.py seed_bulk --flush   # wipe all bulk data and reseed
"""
import datetime
import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

TEAMS = [
    ('Basketball', 'M'),
    ('Soccer',     'M'),
    ('Hockey',     'W'),
    ('Football',   'M'),
    ('Track',      'W'),
]

# 8 players per team = 40 total
PLAYERS = {
    'Basketball': [
        ('James', 'Carter'),  ('Marcus', 'Reed'),   ('Tyler', 'Brooks'),
        ('Devon', 'Hayes'),   ('Jordan', 'Price'),  ('Malik', 'Stone'),
        ('Aaron', 'Flynn'),   ('Cody',   'Nash'),
    ],
    'Soccer': [
        ('Liam',  'Murphy'),  ('Noah',   'Walsh'),  ('Ethan', 'Clarke'),
        ('Lucas', 'Bennett'), ('Logan',  'Hunt'),   ('Mason', 'Bell'),
        ('Owen',  'Foster'),  ('Ryan',   'Perry'),
    ],
    'Hockey': [
        ('Emma',   'Wright'), ('Olivia', 'Scott'),  ('Ava',   'Green'),
        ('Sophia', 'Adams'),  ('Mia',    'Baker'),  ('Chloe', 'Nelson'),
        ('Grace',  'Hill'),   ('Lily',   'Evans'),
    ],
    'Football': [
        ('Aiden',  'Cooper'), ('Bryce',  'Morgan'), ('Cole',  'Ross'),
        ('Derek',  'Ward'),   ('Evan',   'Cox'),    ('Finn',  'Diaz'),
        ('Grant',  'Powell'), ('Hunter', 'Torres'),
    ],
    'Track': [
        ('Zoe',    'Rivera'), ('Nora',   'Collins'),('Ella',  'Stewart'),
        ('Maya',   'Sanchez'),('Aria',   'Morris'), ('Luna',  'Rogers'),
        ('Hazel',  'Reed'),   ('Violet', 'Cook'),
    ],
}

COACHES = {
    'Basketball': ('Brian',   'Simmons'),
    'Soccer':     ('Patrick', 'Doyle'),
    'Hockey':     ('Sandra',  'Lowe'),
    'Football':   ('Greg',    'Warner'),
    'Track':      ('Diana',   'Marsh'),
}

DOCTORS = {
    'Basketball': ('Dr. Kevin',  'Patel'),
    'Soccer':     ('Dr. Sarah',  'Kim'),
    'Hockey':     ('Dr. Robert', 'Nguyen'),
    'Football':   ('Dr. Angela', 'Chen'),
    'Track':      ('Dr. James',  'Liu'),
}

INJURY_DATA = [
    ('Sprain',     'Ankle',    'Moderate', 'ACTIVE',       -14,
     'Grade II ankle sprain during practice. Physio ongoing.'),
    ('Strain',     'Hamstring','Mild',     'RECOVERING',   -30,
     'Mild hamstring pull. Responding well to rest and physio.'),
    ('Fracture',   'Wrist',    'Severe',   'ACTIVE',       -7,
     'Stress fracture confirmed by X-ray. Cast applied.'),
    ('Concussion', 'Head',     'Severe',   'UNDER_REVIEW', -5,
     'Concussion from contact during match. Neurological evaluation pending.'),
    ('Contusion',  'Knee',     'Mild',     'RECOVERED',    -60,
     'Knee bruise from a fall. Fully healed.'),
    ('Strain',     'Shoulder', 'Moderate', 'ACTIVE',       -10,
     'Rotator cuff strain. MRI scheduled.'),
    ('Sprain',     'Knee',     'Severe',   'ACTIVE',       -20,
     'ACL partial tear suspected. Awaiting MRI results.'),
    ('Fracture',   'Ankle',    'Moderate', 'RECOVERING',   -45,
     'Hairline fracture in lateral malleolus. Boot fitted.'),
    ('Contusion',  'Shoulder', 'Mild',     'RECOVERED',    -90,
     'Shoulder bruise from collision. Recovered with ice and rest.'),
    ('Strain',     'Back',     'Moderate', 'UNDER_REVIEW', -3,
     'Lower back strain from heavy training. Physio assessment booked.'),
    ('Sprain',     'Wrist',    'Mild',     'RECOVERED',    -75,
     'Minor wrist sprain. Healed after two weeks rest.'),
    ('Concussion', 'Head',     'Moderate', 'RECOVERING',   -18,
     'Mild concussion. Following graduated return-to-play protocol.'),
]

class Command(BaseCommand):
    help = 'Seed 40 players across 5 teams with realistic injury data'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true',
                            help='Delete bulk seed data before reseeding')

    def handle(self, *args, **options):
        from accounts.models import Team, Notification
        from injury_tracking.models import (
            InjuryRecord, InjuryType, BodyPart, InjurySeverity, InjuryFollowUp, TeamRoster,
        )

        if options['flush']:
            self.stdout.write(self.style.WARNING('Flushing bulk seed data...'))
            bulk_usernames = []
            for sport, players in PLAYERS.items():
                for fn, ln in players:
                    bulk_usernames.append(f"{fn.lower()}_{ln.lower()}")
            for sport, (fn, ln) in COACHES.items():
                bulk_usernames.append(f"coach_{fn.lower()}_{ln.lower()}")
            for sport, (fn, ln) in DOCTORS.items():
                bulk_usernames.append(f"doc_{fn.lower()}_{ln.lower()}")
            User.objects.filter(username__in=bulk_usernames).delete()
            team_names = [f'Lancers {sport}' for sport, _ in TEAMS]
            Team.objects.filter(name__in=team_names).delete()
            self.stdout.write(self.style.SUCCESS('Flushed.'))

        # ── Reference data ────────────────────────────────────────────────────
        inj_types = {n: InjuryType.objects.get_or_create(name=n)[0]
                     for n in ['Sprain','Strain','Fracture','Concussion','Contusion']}
        body_parts = {n: BodyPart.objects.get_or_create(name=n)[0]
                      for n in ['Ankle','Hamstring','Wrist','Head','Knee','Shoulder','Back']}
        severities = {
            'Mild':     InjurySeverity.objects.get_or_create(name='Mild',     defaults={'color_code': '#28a745'})[0],
            'Moderate': InjurySeverity.objects.get_or_create(name='Moderate', defaults={'color_code': '#ffc107'})[0],
            'Severe':   InjurySeverity.objects.get_or_create(name='Severe',   defaults={'color_code': '#dc3545'})[0],
        }

        today = datetime.date.today()
        injury_pool = INJURY_DATA.copy()

        for sport, gender in TEAMS:
            team_name = f'Lancers {sport}'
            team, _ = Team.objects.get_or_create(name=team_name, defaults={'gender': gender})
            self.stdout.write(f'\nTeam: {team}')

            # Coach
            c_first, c_last = COACHES[sport]
            c_uname = f"coach_{c_first.lower()}_{c_last.lower()}"
            coach, created = User.objects.get_or_create(username=c_uname, defaults=dict(
                email=f'{c_uname}@lancers.demo', first_name=c_first, last_name=c_last,
                role='COACH', team=team, is_registration_complete=True,
            ))
            if created:
                coach.set_password('Demo1234!')
                coach.save()
                self.stdout.write(f'  Coach: {c_uname}')

            # Doctor
            d_first, d_last = DOCTORS[sport]
            d_uname = f"doc_{d_first.lower().replace('dr. ', '')}_{d_last.lower()}"
            doctor, created = User.objects.get_or_create(username=d_uname, defaults=dict(
                email=f'{d_uname}@lancers.demo', first_name=d_first, last_name=d_last,
                role='DOCTOR', team=team, is_registration_complete=True,
            ))
            if created:
                doctor.set_password('Demo1234!')
                doctor.save()
                self.stdout.write(f'  Doctor: {d_uname}')

            # Players
            for fn, ln in PLAYERS[sport]:
                uname = f"{fn.lower()}_{ln.lower()}"
                player, created = User.objects.get_or_create(username=uname, defaults=dict(
                    email=f'{uname}@lancers.demo', first_name=fn, last_name=ln,
                    role='PLAYER', team=team, is_registration_complete=True,
                ))
                if created:
                    player.set_password('Demo1234!')
                    player.save()

                TeamRoster.objects.get_or_create(team=team, player=player)

                # Give ~60% of players an injury
                if random.random() < 0.6:
                    inj_info = random.choice(injury_pool)
                    it_name, bp_name, sev_name, status, day_offset, desc = inj_info
                    inj_date = today + datetime.timedelta(days=day_offset)

                    inj, inj_created = InjuryRecord.objects.get_or_create(
                        player=player,
                        injury_date=inj_date,
                        injury_type=inj_types[it_name],
                        defaults=dict(
                            body_part=body_parts[bp_name],
                            severity=severities[sev_name],
                            status=status,
                            description=desc,
                            reported_by=doctor,
                            medical_clearance=(status == 'RECOVERED'),
                        ),
                    )

                    if inj_created:
                        self.stdout.write(f'    Injury: {fn} {ln} — {it_name} ({status})')

                        # Follow-up for non-recovered injuries
                        if status != 'RECOVERED':
                            InjuryFollowUp.objects.get_or_create(
                                injury=inj,
                                follow_up_date=inj_date + datetime.timedelta(days=7),
                                defaults=dict(
                                    notes='Initial review: treatment commenced. Monitor progress.',
                                    status_update=status,
                                    created_by=doctor,
                                ),
                            )

                        # Notification to player
                        Notification.objects.get_or_create(
                            user=player,
                            message=f'Your {it_name.lower()} injury on {inj_date} has been recorded.',
                            defaults=dict(notification_type='INJURY', is_read=False),
                        )

                        # Notification to coach
                        Notification.objects.get_or_create(
                            user=coach,
                            message=f'{fn} {ln} has been reported with a {sev_name.lower()} {it_name.lower()}.',
                            defaults=dict(notification_type='INJURY', is_read=False),
                        )

        self.stdout.write(self.style.SUCCESS('\nBulk seed complete!'))
        self.stdout.write('All passwords: Demo1234!')
        self.stdout.write('\nCoach logins:')
        for sport, (fn, ln) in COACHES.items():
            self.stdout.write(f'  coach_{fn.lower()}_{ln.lower()} ({sport})')
        self.stdout.write('\nDoctor logins:')
        for sport, (fn, ln) in DOCTORS.items():
            uname = f"doc_{fn.lower().replace('dr. ', '')}_{ln.lower()}"
            self.stdout.write(f'  {uname} ({sport})')
