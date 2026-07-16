from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('injury_tracking', '0005_injuryrecord_context_injuryrecord_could_continue_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WellnessCheckIn',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_start', models.DateField(help_text='Monday of the week this check-in covers.')),
                ('sleep_score', models.PositiveSmallIntegerField(
                    choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')],
                    help_text='Sleep quality this week (1=very poor, 5=excellent).',
                )),
                ('pain_score', models.PositiveSmallIntegerField(
                    choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')],
                    help_text='Overall pain / soreness level (1=none, 5=severe).',
                )),
                ('mood_score', models.PositiveSmallIntegerField(
                    choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')],
                    help_text='Overall mood / mental wellbeing (1=very low, 5=great).',
                )),
                ('notes', models.TextField(blank=True, help_text='Any other comments.')),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('player', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='wellness_checkins',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-week_start'],
                'unique_together': {('player', 'week_start')},
            },
        ),
    ]
