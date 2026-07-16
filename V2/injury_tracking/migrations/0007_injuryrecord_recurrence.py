from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('injury_tracking', '0006_wellnesscheckin'),
    ]

    operations = [
        migrations.AddField(
            model_name='injuryrecord',
            name='is_recurrence',
            field=models.BooleanField(
                default=False,
                help_text='True if this injury affects the same body part as a previous injury for this player.',
            ),
        ),
        migrations.AddField(
            model_name='injuryrecord',
            name='previous_injury',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recurrences',
                to='injury_tracking.injuryrecord',
                help_text='Earlier injury this is considered a recurrence of.',
            ),
        ),
    ]
