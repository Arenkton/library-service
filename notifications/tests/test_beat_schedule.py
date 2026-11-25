from celery.schedules import crontab
from django.test import SimpleTestCase

from config.celery import app


class CeleryBeatScheduleTests(SimpleTestCase):
    def test_overdue_borrowings_scheduled_daily(self):
        schedule_config = app.conf.beat_schedule[
            "check-overdue-borrowings-daily"
        ]

        self.assertEqual(
            schedule_config["task"],
            "notifications.tasks.notify_overdue_borrowings",
        )

        schedule = schedule_config["schedule"]

        self.assertIsInstance(schedule, crontab)
        self.assertEqual(schedule.hour, {9})
        self.assertEqual(schedule.minute, {0})
        self.assertEqual(
            schedule.day_of_week,
            set(range(7)),
        )
