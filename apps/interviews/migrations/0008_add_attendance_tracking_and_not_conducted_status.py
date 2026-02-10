# Generated migration for attendance tracking and not_conducted status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interviews', '0007_interviewerfeedback_unique_interviewer_feedback'),
    ]

    operations = [
        # Add sender_joined_at field for tracking when sender (attender) joined
        migrations.AddField(
            model_name='interviewrequest',
            name='sender_joined_at',
            field=models.DateTimeField(
                blank=True, 
                null=True, 
                help_text='When the sender (attender) joined the interview room'
            ),
        ),
        # Add receiver_joined_at field for tracking when receiver (taker) joined
        migrations.AddField(
            model_name='interviewrequest',
            name='receiver_joined_at',
            field=models.DateTimeField(
                blank=True, 
                null=True, 
                help_text='When the receiver (taker) joined the interview room'
            ),
        ),
        # Update status choices to include 'not_conducted' status
        migrations.AlterField(
            model_name='interviewrequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('accepted', 'Accepted'),
                    ('rejected', 'Rejected'),
                    ('cancelled', 'Cancelled'),
                    ('completed', 'Completed'),
                    ('not attended', 'Not attended'),
                    ('not_conducted', 'Not Conducted'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
        # Add index for Celery expiry task optimization
        migrations.AddIndex(
            model_name='interviewrequest',
            index=models.Index(
                fields=['status', 'accepted_at'], 
                name='idx_interview_expiry_check'
            ),
        ),
    ]
