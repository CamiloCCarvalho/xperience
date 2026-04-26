import json
import shutil
import tempfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.financial import calculate_workspace_balance
from app.models import (
    BoardCard,
    Client as AppClient,
    BudgetGoal,
    CompensationHistory,
    Department,
    EmployeeProfile,
    FinancialEntry,
    JobRole,
    Membership,
    MuralStatusOption,
    PrivateBoardColumn,
    Project,
    Task,
    TimeEntry,
    TimeEntryTemplate,
    UserClient,
    UserDepartment,
    UserProject,
    WorkSchedule,
    Workspace,
)
from app.admin_dashboard_data import build_admin_dashboard
from app.time_entry_timer import (
    assert_user_may_delete_time_entry,
    assert_user_may_edit_time_entry,
    get_active_draft,
    start_timer,
    stop_timer,
)
from app.workspace_session import SESSION_ADMIN_WORKSPACE_KEY, SESSION_MEMBER_WORKSPACE_KEY

User = get_user_model()


def create_hourly_compensation(user, workspace, *, hourly_rate=Decimal("100.00")):
    role, _ = JobRole.objects.get_or_create(
        workspace=workspace,
        name="Contributor",
        defaults={"description": ""},
    )
    profile = EmployeeProfile.objects.create(
        user=user,
        workspace=workspace,
        employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
        hire_date=date(2024, 1, 1),
        current_job_role=role,
    )
    CompensationHistory.objects.create(
        employee_profile=profile,
        compensation_type=CompensationHistory.CompensationType.HOURLY,
        hourly_rate=hourly_rate,
        start_date=date(2024, 1, 1),
    )
    return profile


class TimerDomainTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="x",
            first_name="O",
            last_name="wner",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            password="x",
            first_name="M",
            last_name="ember",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])

        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WS1",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws)
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.dept = Department.objects.create(
            workspace=self.ws,
            name="Eng",
            time_tracking_mode=Department.TimeTrackingMode.TIMER,
        )
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )

    def test_start_then_stop(self):
        entry = start_timer(self.member, self.ws)
        self.assertEqual(entry.status, TimeEntry.Status.DRAFT)
        self.assertEqual(entry.entry_mode, TimeEntry.EntryMode.TIMER)

        stop_at = entry.timer_started_at + timezone.timedelta(minutes=30)
        saved = stop_timer(self.member, self.ws, stopped_at=stop_at)
        self.assertEqual(saved.status, TimeEntry.Status.SAVED)
        self.assertEqual(saved.duration_minutes, 30)
        self.assertTrue(saved.timer_pending_template_completion)

    def test_second_start_blocked(self):
        start_timer(self.member, self.ws)
        with self.assertRaises(ValidationError):
            start_timer(self.member, self.ws)

    def test_stop_midnight_rejected(self):
        tz = timezone.get_current_timezone()
        day = date(2026, 6, 15)
        started = timezone.make_aware(
            timezone.datetime.combine(day, time(23, 0)),
            tz,
        )
        entry = start_timer(self.member, self.ws, started_at=started)
        stopped = timezone.make_aware(
            datetime.combine(day + timedelta(days=1), time(0, 30)),
            tz,
        )
        with self.assertRaises(ValidationError):
            stop_timer(self.member, self.ws, entry_id=entry.pk, stopped_at=stopped)

    def test_saved_only_excludes_draft(self):
        start_timer(self.member, self.ws)
        self.assertEqual(TimeEntry.objects.saved_only().count(), 0)
        self.assertEqual(TimeEntry.objects.count(), 1)

    def test_department_flags_edit_delete(self):
        entry = TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date.today(),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1.00"),
        )
        self.dept.can_edit_time_entries = False
        self.dept.save(update_fields=["can_edit_time_entries"])
        with self.assertRaises(PermissionDenied):
            assert_user_may_edit_time_entry(self.member, entry)

        self.dept.can_edit_time_entries = True
        self.dept.can_delete_time_entries = False
        self.dept.save(update_fields=["can_edit_time_entries", "can_delete_time_entries"])
        assert_user_may_edit_time_entry(self.member, entry)
        with self.assertRaises(PermissionDenied):
            assert_user_may_delete_time_entry(self.member, entry)

    def test_get_active_draft(self):
        self.assertIsNone(get_active_draft(self.member, self.ws))
        e = start_timer(self.member, self.ws)
        d = get_active_draft(self.member, self.ws)
        self.assertIsNotNone(d)
        self.assertEqual(d.pk, e.pk)


class TimerHttpTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner2@example.com",
            password="x",
            first_name="O",
            last_name="2",
        )
        self.member = User.objects.create_user(
            email="member2@example.com",
            password="x",
            first_name="M",
            last_name="2",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WS2",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws)
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.dept = Department.objects.create(workspace=self.ws, name="D2")
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )
        self.client = Client()
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def test_timer_endpoints(self):
        r = self.client.get(reverse("user-time-entry-timer-draft"))
        self.assertEqual(r.status_code, 200)
        self.assertJSONEqual(r.content, {"active": False, "entry": None})

        r = self.client.post(
            reverse("user-time-entry-timer-start"),
            data=json.dumps({"is_overtime": True}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        eid = r.json()["entry"]["id"]
        self.assertTrue(TimeEntry.objects.get(pk=eid).is_overtime)

        r = self.client.get(reverse("user-time-entry-timer-draft"))
        self.assertTrue(r.json()["active"])

        started = TimeEntry.objects.get(pk=eid).timer_started_at
        assert started is not None
        stop_at = (started + timezone.timedelta(minutes=30)).isoformat()
        r = self.client.post(
            reverse("user-time-entry-timer-stop"),
            data=json.dumps({"entry_id": eid, "stopped_at": stop_at}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["entry"]["status"], TimeEntry.Status.SAVED)
        self.assertTrue(TimeEntry.objects.get(pk=eid).timer_pending_template_completion)

        r = self.client.post(
            reverse("user-time-entry-timer-discard-pending"),
            data=json.dumps({"entry_id": eid}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(TimeEntry.objects.filter(pk=eid).exists())

    def test_timer_discard_forbidden_when_cannot_delete(self):
        r = self.client.post(
            reverse("user-time-entry-timer-start"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        eid = r.json()["entry"]["id"]
        started = TimeEntry.objects.get(pk=eid).timer_started_at
        assert started is not None
        stop_at = (started + timezone.timedelta(minutes=30)).isoformat()
        r = self.client.post(
            reverse("user-time-entry-timer-stop"),
            data=json.dumps({"entry_id": eid, "stopped_at": stop_at}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.dept.can_delete_time_entries = False
        self.dept.save(update_fields=["can_delete_time_entries"])
        r2 = self.client.post(
            reverse("user-time-entry-timer-discard-pending"),
            data=json.dumps({"entry_id": eid}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 403)
        self.assertTrue(TimeEntry.objects.filter(pk=eid).exists())


class PreparedSubmitHttpTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner3@example.com",
            password="x",
            first_name="O",
            last_name="3",
        )
        self.member = User.objects.create_user(
            email="member3@example.com",
            password="x",
            first_name="M",
            last_name="3",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WS3",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws)
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.dept = Department.objects.create(workspace=self.ws, name="D3")
        tpl = TimeEntryTemplate.objects.create(
            workspace=self.ws,
            name="Tpl3",
            use_client=False,
            use_project=False,
            use_task=False,
            use_type=False,
            use_description=False,
        )
        self.dept.template = tpl
        self.dept.save(update_fields=["template"])
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )
        self.client = Client()
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def test_prepared_submit_creates_saved_entry(self):
        body = {
            "workspace_id": self.ws.pk,
            "date": "2026-04-15",
            "hours": "1.5",
            "client_id": "",
            "project_id": "",
            "task_id": "",
            "description": "",
            "entry_type": "",
            "prepared_at": "2026-04-15T12:00:00",
        }
        r = self.client.post(
            reverse("user-time-entry-prepared-submit"),
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["entry"]["date"], "2026-04-15")
        te = TimeEntry.objects.get(pk=data["entry"]["id"])
        self.assertEqual(te.status, TimeEntry.Status.SAVED)
        self.assertEqual(te.entry_mode, TimeEntry.EntryMode.DURATION)
        self.assertEqual(te.user_id, self.member.pk)


class ManualTimeEntryApiTests(TestCase):
    """Criação / edição / exclusão manual (JSON) no workspace da sessão."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="ownerm@example.com",
            password="x",
            first_name="O",
            last_name="M",
        )
        self.member = User.objects.create_user(
            email="memberm@example.com",
            password="x",
            first_name="M",
            last_name="M",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WSM",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws)
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.dept = Department.objects.create(workspace=self.ws, name="DM")
        tpl = TimeEntryTemplate.objects.create(
            workspace=self.ws,
            name="TplM",
            use_client=False,
            use_project=False,
            use_task=False,
            use_type=False,
            use_description=False,
        )
        self.dept.template = tpl
        self.dept.save(update_fields=["template"])
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )
        self.client = Client()
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def _post_json(self, url_name, data, pk=None):
        if pk is not None:
            url = reverse(url_name, kwargs={"pk": pk})
        else:
            url = reverse(url_name)
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_manual_create_duration(self):
        r = self._post_json(
            "user-time-entry-manual-create",
            {
                "entry_mode": TimeEntry.EntryMode.DURATION,
                "date": "2026-05-10",
                "hours": "2.5",
                "is_overtime": True,
            },
        )
        self.assertEqual(r.status_code, 201, r.content)
        eid = r.json()["entry"]["id"]
        te = TimeEntry.objects.get(pk=eid)
        self.assertEqual(te.entry_mode, TimeEntry.EntryMode.DURATION)
        self.assertEqual(te.hours, Decimal("2.50"))
        self.assertTrue(te.is_overtime)

    def test_manual_create_time_range(self):
        r = self._post_json(
            "user-time-entry-manual-create",
            {
                "entry_mode": TimeEntry.EntryMode.TIME_RANGE,
                "date": "2026-05-11",
                "start_time": "09:00",
                "end_time": "10:30",
            },
        )
        self.assertEqual(r.status_code, 201, r.content)
        te = TimeEntry.objects.get(pk=r.json()["entry"]["id"])
        self.assertEqual(te.entry_mode, TimeEntry.EntryMode.TIME_RANGE)
        self.assertEqual(te.duration_minutes, 90)

    def test_manual_update_respects_edit_flag(self):
        r = self._post_json(
            "user-time-entry-manual-create",
            {
                "entry_mode": TimeEntry.EntryMode.DURATION,
                "date": "2026-05-12",
                "hours": "1",
            },
        )
        eid = r.json()["entry"]["id"]
        self.dept.can_edit_time_entries = False
        self.dept.save(update_fields=["can_edit_time_entries"])
        r2 = self.client.post(
            reverse("user-time-entry-manual-update", kwargs={"pk": eid}),
            data=json.dumps(
                {
                    "entry_mode": TimeEntry.EntryMode.DURATION,
                    "date": "2026-05-12",
                    "hours": "3",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 403)

    def test_manual_delete_respects_delete_flag(self):
        r = self._post_json(
            "user-time-entry-manual-create",
            {
                "entry_mode": TimeEntry.EntryMode.DURATION,
                "date": "2026-05-13",
                "hours": "1",
            },
        )
        eid = r.json()["entry"]["id"]
        self.dept.can_delete_time_entries = False
        self.dept.save(update_fields=["can_delete_time_entries"])
        r2 = self.client.post(reverse("user-time-entry-manual-delete", kwargs={"pk": eid}))
        self.assertEqual(r2.status_code, 403)

    def test_manual_update_rejects_timer_saved(self):
        e = start_timer(self.member, self.ws)
        started = e.timer_started_at
        assert started is not None
        stop_at = started + timezone.timedelta(hours=1)
        stop_timer(self.member, self.ws, entry_id=e.pk, stopped_at=stop_at)
        e.refresh_from_db()
        self.assertEqual(e.entry_mode, TimeEntry.EntryMode.TIMER)
        r = self.client.post(
            reverse("user-time-entry-manual-update", kwargs={"pk": e.pk}),
            data=json.dumps(
                {
                    "entry_mode": TimeEntry.EntryMode.DURATION,
                    "date": str(e.date),
                    "hours": "2",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_day_detail_requires_valid_date(self):
        r = self.client.get(reverse("user-time-entry-day-detail"), {"date": "not-a-date"})
        self.assertEqual(r.status_code, 400)

    def test_day_detail_lists_entries_with_edit_payload_when_allowed(self):
        r = self._post_json(
            "user-time-entry-manual-create",
            {
                "entry_mode": TimeEntry.EntryMode.DURATION,
                "date": "2026-06-20",
                "hours": "2",
            },
        )
        self.assertEqual(r.status_code, 201, r.content)
        r2 = self.client.get(reverse("user-time-entry-day-detail"), {"date": "2026-06-20"})
        self.assertEqual(r2.status_code, 200)
        data = r2.json()
        self.assertEqual(data["date"], "2026-06-20")
        self.assertEqual(len(data["entries"]), 1)
        e0 = data["entries"][0]
        self.assertTrue(e0["can_edit"])
        self.assertTrue(e0["can_delete"])
        self.assertIn("edit", e0)
        self.assertEqual(e0["edit"]["hours"], "2.00")

    def test_day_detail_respects_department_edit_delete_flags(self):
        r = self._post_json(
            "user-time-entry-manual-create",
            {
                "entry_mode": TimeEntry.EntryMode.DURATION,
                "date": "2026-06-21",
                "hours": "1",
            },
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.dept.can_edit_time_entries = False
        self.dept.can_delete_time_entries = False
        self.dept.save(update_fields=["can_edit_time_entries", "can_delete_time_entries"])
        r2 = self.client.get(reverse("user-time-entry-day-detail"), {"date": "2026-06-21"})
        self.assertEqual(r2.status_code, 200)
        e0 = r2.json()["entries"][0]
        self.assertFalse(e0["can_edit"])
        self.assertFalse(e0["can_delete"])
        self.assertNotIn("edit", e0)

    def test_day_detail_includes_birthday_event(self):
        self.member.birth_date = date(1991, 8, 22)
        self.member.save(update_fields=["birth_date"])
        r = self.client.get(reverse("user-time-entry-day-detail"), {"date": "2026-08-22"})
        self.assertEqual(r.status_code, 200)
        events = r.json()["events"]
        self.assertTrue(any(e.get("type") == "birthday" for e in events))


class TimerCompleteFieldsHttpTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="ownertc@example.com",
            password="x",
            first_name="O",
            last_name="TC",
        )
        self.member = User.objects.create_user(
            email="membertc@example.com",
            password="x",
            first_name="M",
            last_name="TC",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WSTC",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws)
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.dept = Department.objects.create(workspace=self.ws, name="DTC")
        tpl = TimeEntryTemplate.objects.create(
            workspace=self.ws,
            name="TplTC",
            use_client=False,
            use_project=False,
            use_task=False,
            use_type=False,
            use_description=False,
        )
        self.dept.template = tpl
        self.dept.save(update_fields=["template"])
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )
        self.client = Client()
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def test_timer_complete_updates_description(self):
        e = start_timer(self.member, self.ws)
        started = e.timer_started_at
        assert started is not None
        stop_at = started + timezone.timedelta(minutes=5)
        stop_timer(self.member, self.ws, entry_id=e.pk, stopped_at=stop_at)
        e.refresh_from_db()
        r = self.client.post(
            reverse("user-time-entry-timer-complete"),
            data=json.dumps(
                {
                    "entry_id": e.pk,
                    "description": "Após stop",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        e.refresh_from_db()
        self.assertEqual(e.description, "Após stop")
        self.assertFalse(e.timer_pending_template_completion)

        r2 = self.client.post(
            reverse("user-time-entry-timer-discard-pending"),
            data=json.dumps({"entry_id": e.pk}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 400, r2.content)


class TimeEntryMonthCountsHttpTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="ownermc@example.com",
            password="x",
            first_name="O",
            last_name="MC",
        )
        self.member = User.objects.create_user(
            email="membermc@example.com",
            password="x",
            first_name="M",
            last_name="MC",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WSMC",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws)
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.dept = Department.objects.create(workspace=self.ws, name="DMC")
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )
        self.client = Client()
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def test_month_counts_saved_only_per_day(self):
        sched = WorkSchedule.objects.create(
            workspace=self.ws,
            name="Exp MC",
            working_days=["mon"],
            expected_hours_per_day=8,
        )
        self.dept.schedule = sched
        self.dept.save(update_fields=["schedule"])
        d1 = date(2026, 4, 10)
        d2 = date(2026, 4, 11)
        for _ in range(2):
            TimeEntry.objects.create(
                user=self.member,
                workspace=self.ws,
                department=self.dept,
                date=d1,
                status=TimeEntry.Status.SAVED,
                entry_mode=TimeEntry.EntryMode.DURATION,
                hours=Decimal("1.00"),
            )
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=d2,
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("0.50"),
        )
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=d2,
            status=TimeEntry.Status.DRAFT,
            entry_mode=TimeEntry.EntryMode.TIMER,
            timer_started_at=timezone.now(),
        )
        r = self.client.get(
            reverse("user-time-entry-month-counts"),
            {"year": 2026, "month": 4},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["by_date"]["2026-04-10"], 2)
        self.assertEqual(data["by_date"]["2026-04-11"], 1)
        self.assertEqual(data["expected_hours_per_day"], 8)
        self.assertEqual(data["by_date_hours"]["2026-04-10"], 2.0)
        self.assertEqual(data["by_date_hours"]["2026-04-11"], 0.5)
        self.assertEqual(data["by_date_pay"]["2026-04-10"], 200.0)
        self.assertEqual(data["by_date_pay"]["2026-04-11"], 50.0)
        self.assertIsNone(data.get("member_birthday"))
        self.assertEqual(
            data.get("schedule_weekday_visual"),
            {"working_days": ["mon"]},
        )

    def test_month_counts_includes_member_birthday_when_set(self):
        self.member.birth_date = date(1990, 4, 10)
        self.member.save(update_fields=["birth_date"])
        r = self.client.get(
            reverse("user-time-entry-month-counts"),
            {"year": 2026, "month": 4},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["member_birthday"], {"month": 4, "day": 10})

    def test_month_counts_workspace_public_birthdays_lists_colleagues_only(self):
        colleague = User.objects.create_user(
            email="colleaguebday@example.com",
            password="x",
            first_name="Colega",
            last_name="Aniv",
        )
        colleague.platform_role = User.PlatformRole.MEMBER
        colleague.save(update_fields=["platform_role"])
        colleague.birth_date = date(1985, 6, 18)
        colleague.birthday_public_in_workspace = True
        colleague.save(update_fields=["birth_date", "birthday_public_in_workspace"])
        Membership.objects.create(user=colleague, workspace=self.ws, role="user")

        hidden = User.objects.create_user(
            email="hiddenbday@example.com",
            password="x",
            first_name="Privado",
            last_name="X",
        )
        hidden.platform_role = User.PlatformRole.MEMBER
        hidden.save(update_fields=["platform_role"])
        hidden.birth_date = date(1992, 6, 20)
        hidden.birthday_public_in_workspace = False
        hidden.save(update_fields=["birth_date", "birthday_public_in_workspace"])
        Membership.objects.create(user=hidden, workspace=self.ws, role="user")

        r = self.client.get(
            reverse("user-time-entry-month-counts"),
            {"year": 2026, "month": 6},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        pub = data.get("workspace_public_birthdays") or []
        self.assertEqual(len(pub), 1)
        self.assertEqual(pub[0]["month"], 6)
        self.assertEqual(pub[0]["day"], 18)
        self.assertIn("Colega", pub[0].get("display_name", ""))

    def test_month_counts_expected_null_without_schedule(self):
        self.assertIsNone(self.dept.schedule_id)
        d1 = date(2026, 5, 5)
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=d1,
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("2.00"),
        )
        r = self.client.get(
            reverse("user-time-entry-month-counts"),
            {"year": 2026, "month": 5},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsNone(data.get("expected_hours_per_day"))
        self.assertEqual(data["by_date_hours"]["2026-05-05"], 2.0)
        self.assertEqual(data["by_date_pay"]["2026-05-05"], 200.0)
        self.assertIsNone(data.get("schedule_weekday_visual"))

    def test_month_counts_schedule_weekday_visual_null_when_folga_not_fixed(self):
        sched = WorkSchedule.objects.create(
            workspace=self.ws,
            name="Rotativo",
            working_days=["mon", "tue", "wed", "thu", "fri"],
            expected_hours_per_day=8,
            has_fixed_days=False,
        )
        self.dept.schedule = sched
        self.dept.save(update_fields=["schedule"])
        r = self.client.get(
            reverse("user-time-entry-month-counts"),
            {"year": 2026, "month": 4},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json().get("schedule_weekday_visual"))

    def test_month_counts_schedule_weekday_defaults_weekdays_when_working_days_empty(self):
        sched = WorkSchedule.objects.create(
            workspace=self.ws,
            name="Sem lista",
            working_days=[],
            expected_hours_per_day=8,
            has_fixed_days=True,
        )
        self.dept.schedule = sched
        self.dept.save(update_fields=["schedule"])
        r = self.client.get(
            reverse("user-time-entry-month-counts"),
            {"year": 2026, "month": 4},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json().get("schedule_weekday_visual"),
            {"working_days": ["mon", "tue", "wed", "thu", "fri"]},
        )

    def test_month_counts_hours_from_duration_minutes(self):
        sched = WorkSchedule.objects.create(
            workspace=self.ws,
            name="Exp DM",
            working_days=["mon"],
            expected_hours_per_day=8,
        )
        self.dept.schedule = sched
        self.dept.save(update_fields=["schedule"])
        d1 = date(2026, 6, 1)
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=d1,
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=None,
            duration_minutes=90,
        )
        r = self.client.get(
            reverse("user-time-entry-month-counts"),
            {"year": 2026, "month": 6},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["by_date"]["2026-06-01"], 1)
        self.assertEqual(data["by_date_hours"]["2026-06-01"], 1.5)
        self.assertEqual(data["by_date_pay"]["2026-06-01"], 150.0)
        self.assertEqual(
            data.get("schedule_weekday_visual"),
            {"working_days": ["mon"]},
        )

    def test_month_counts_invalid_params(self):
        r = self.client.get(reverse("user-time-entry-month-counts"), {"year": 1999, "month": 4})
        self.assertEqual(r.status_code, 400)


class UserHomeHistoryTableTests(TestCase):
    """Histórico na home do membro: colunas alinhadas ao template e dados reais."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="ownerhist@example.com",
            password="x",
            first_name="O",
            last_name="H",
        )
        self.member = User.objects.create_user(
            email="memberhist@example.com",
            password="x",
            first_name="M",
            last_name="H",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WSHist",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws)
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.dept = Department.objects.create(workspace=self.ws, name="DeptHist")
        self.tpl = TimeEntryTemplate.objects.create(
            workspace=self.ws,
            name="TplHist",
            use_client=True,
            use_project=True,
            use_task=False,
            use_type=True,
            use_description=True,
        )
        self.dept.template = self.tpl
        self.dept.save(update_fields=["template"])
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )
        self.cli = AppClient.objects.create(workspace=self.ws, name="Cliente Histórico")
        UserClient.objects.create(user=self.member, workspace=self.ws, client=self.cli)
        self.proj = Project.objects.create(
            workspace=self.ws,
            client=self.cli,
            name="Proj Histórico",
        )
        UserProject.objects.create(user=self.member, workspace=self.ws, project=self.proj)
        self.client = Client()
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def test_home_renders_saved_time_entry_row(self):
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 4, 2),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1.5"),
            description="Marcador único da linha de histórico",
            entry_type=TimeEntry.EntryType.INTERNAL,
            client=self.cli,
            project=self.proj,
            is_overtime=False,
        )
        r = self.client.get(reverse("user-home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Marcador único da linha de histórico")
        self.assertContains(r, "Cliente Histórico")
        self.assertContains(r, "Proj Histórico")

    def test_home_history_filter_by_year_excludes_other_years(self):
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2025, 1, 1),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1"),
            description="Só em 2025",
            client=self.cli,
            project=self.proj,
        )
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 1, 1),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1"),
            description="Só em 2026",
            client=self.cli,
            project=self.proj,
        )
        r = self.client.get(reverse("user-home"), {"year": "2026"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Só em 2026")
        self.assertNotContains(r, "Só em 2025")

    def test_home_history_filter_exact_year_month_day(self):
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 4, 10),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1"),
            description="Marcador dia 10 de abril",
            client=self.cli,
            project=self.proj,
        )
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 4, 11),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1"),
            description="Marcador dia 11 de abril",
            client=self.cli,
            project=self.proj,
        )
        r = self.client.get(
            reverse("user-home"),
            {"hf_year": "2026", "hf_month": "4", "hf_day": "10"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Marcador dia 10 de abril")
        self.assertNotContains(r, "Marcador dia 11 de abril")

    def test_home_history_filter_legacy_year_month_day_keys(self):
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 5, 20),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1"),
            description="Legacy filtro 20 maio",
            client=self.cli,
            project=self.proj,
        )
        r = self.client.get(
            reverse("user-home"),
            {"year": "2026", "month": "5", "day": "20"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Legacy filtro 20 maio")


class FinancialFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="ownerfin@example.com",
            password="x",
            first_name="O",
            last_name="F",
        )
        self.member = User.objects.create_user(
            email="memberfin@example.com",
            password="x",
            first_name="M",
            last_name="F",
        )
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WSFin",
            workspace_description="",
        )
        create_hourly_compensation(self.member, self.ws, hourly_rate=Decimal("50.00"))
        self.client_ref = AppClient.objects.create(workspace=self.ws, name="Cliente Fin")
        self.project = Project.objects.create(
            workspace=self.ws,
            client=self.client_ref,
            name="Projeto Fin",
        )
        UserClient.objects.create(user=self.member, workspace=self.ws, client=self.client_ref)
        UserProject.objects.create(user=self.member, workspace=self.ws, project=self.project)
        self.dept = Department.objects.create(workspace=self.ws, name="Financeiro")
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )

    def test_saved_time_entry_creates_automatic_financial_entry(self):
        entry = TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 7, 10),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("2.00"),
            client=self.client_ref,
            project=self.project,
        )
        fin = FinancialEntry.objects.get(
            time_entry=entry,
            entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST,
        )
        self.assertEqual(fin.flow_type, FinancialEntry.FlowType.OUTFLOW)
        self.assertEqual(fin.approval_status, FinancialEntry.ApprovalStatus.PENDING)
        self.assertEqual(fin.amount, Decimal("100.00"))
        self.assertEqual(fin.user, self.member)
        self.assertEqual(fin.project, self.project)
        entry.refresh_from_db()
        self.assertEqual(entry.pay_amount_snapshot, Decimal("100.00"))
        self.assertEqual(entry.effective_hourly_rate_snapshot, Decimal("50.0000"))

    def test_updating_saved_time_entry_recalculates_financial_entry(self):
        entry = TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 7, 11),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1.00"),
        )
        entry.hours = Decimal("3.00")
        entry.save(financial_actor=self.owner)
        fin = FinancialEntry.objects.get(
            source_time_entry_id=entry.pk,
            entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST,
        )
        self.assertEqual(fin.amount, Decimal("150.00"))
        self.assertEqual(fin.updated_by, self.owner)
        entry.refresh_from_db()
        self.assertEqual(entry.pay_amount_snapshot, Decimal("150.00"))

    def test_deleting_saved_time_entry_creates_reversal(self):
        entry = TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 7, 12),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1.00"),
        )
        original = FinancialEntry.objects.get(
            source_time_entry_id=entry.pk,
            entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST,
        )
        original.approval_status = FinancialEntry.ApprovalStatus.APPROVED
        original.approved_by = self.owner
        original.approved_at = timezone.now()
        original.updated_by = self.owner
        original.save()
        source_entry_id = entry.pk
        entry.delete(financial_actor=self.owner)
        original.refresh_from_db()
        reversal = FinancialEntry.objects.get(reversal_of=original)
        self.assertEqual(reversal.flow_type, FinancialEntry.FlowType.INFLOW)
        self.assertEqual(reversal.approval_status, FinancialEntry.ApprovalStatus.NOT_REQUIRED)
        self.assertEqual(reversal.amount, original.amount)
        self.assertEqual(reversal.source_time_entry_id, source_entry_id)
        self.assertEqual(reversal.created_by, self.owner)

    def test_deleting_saved_time_entry_pending_does_not_create_reversal(self):
        entry = TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 7, 13),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1.00"),
        )
        original = FinancialEntry.objects.get(
            source_time_entry_id=entry.pk,
            entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST,
        )
        self.assertEqual(original.approval_status, FinancialEntry.ApprovalStatus.PENDING)
        entry.delete(financial_actor=self.owner)
        self.assertFalse(FinancialEntry.objects.filter(reversal_of=original).exists())

    def test_budget_goal_accepts_workspace_client_and_project_scope(self):
        workspace_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            minimum_target_amount=Decimal("1000.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("2000.00"),
            desired_target_date=date(2026, 9, 1),
        )
        client_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            client=self.client_ref,
            minimum_target_amount=Decimal("500.00"),
            minimum_target_date=date(2026, 8, 5),
            desired_target_amount=Decimal("800.00"),
            desired_target_date=date(2026, 9, 5),
        )
        project_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            client=self.client_ref,
            project=self.project,
            minimum_target_amount=Decimal("200.00"),
            minimum_target_date=date(2026, 8, 10),
            desired_target_amount=Decimal("300.00"),
            desired_target_date=date(2026, 9, 10),
        )
        self.assertIsNotNone(workspace_goal.pk)
        self.assertEqual(client_goal.client, self.client_ref)
        self.assertEqual(project_goal.project, self.project)


class AdminConfigFinancialTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="adminfin@example.com",
            password="x",
            first_name="Admin",
            last_name="Fin",
        )
        self.admin_user.platform_role = User.PlatformRole.ADMIN
        self.admin_user.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.admin_user,
            workspace_name="WSAdminFin",
            workspace_description="",
        )
        self.member = User.objects.create_user(
            email="memberadminfin@example.com",
            password="x",
            first_name="Member",
            last_name="Fin",
        )
        Membership.objects.create(user=self.member, workspace=self.ws, role="manager")
        self.client_ref = AppClient.objects.create(workspace=self.ws, name="Cliente Admin Fin")
        self.project = Project.objects.create(
            workspace=self.ws,
            client=self.client_ref,
            name="Projeto Admin Fin",
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        session = self.client.session
        session[SESSION_ADMIN_WORKSPACE_KEY] = self.ws.pk
        session.save()

    def test_admin_config_creates_manual_financial_entry(self):
        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "create_financial_entry",
                "flow_type": FinancialEntry.FlowType.INFLOW,
                "occurred_on": "2026-08-01",
                "amount": "1500.00",
                "description": "Novo contrato",
                "client": self.client_ref.pk,
                "project": self.project.pk,
                "user": self.member.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        fin = FinancialEntry.objects.get(entry_kind=FinancialEntry.EntryKind.MANUAL)
        self.assertEqual(fin.created_by, self.admin_user)
        self.assertEqual(fin.client, self.client_ref)
        self.assertEqual(fin.approval_status, FinancialEntry.ApprovalStatus.NOT_REQUIRED)

    def test_manual_outflow_starts_pending(self):
        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "create_financial_entry",
                "flow_type": FinancialEntry.FlowType.OUTFLOW,
                "occurred_on": "2026-08-01",
                "amount": "450.00",
                "description": "Compra",
                "client": self.client_ref.pk,
                "project": self.project.pk,
                "user": self.member.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        fin = FinancialEntry.objects.get(entry_kind=FinancialEntry.EntryKind.MANUAL)
        self.assertEqual(fin.approval_status, FinancialEntry.ApprovalStatus.PENDING)

    def test_approve_manual_outflow_impacts_balance(self):
        fin = FinancialEntry.objects.create(
            workspace=self.ws,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.OUTFLOW,
            occurred_on=date(2026, 8, 1),
            amount=Decimal("300.00"),
            description="Compra pendente",
            created_by=self.admin_user,
            updated_by=self.admin_user,
            approval_status=FinancialEntry.ApprovalStatus.PENDING,
        )
        self.assertEqual(calculate_workspace_balance(self.ws), Decimal("0.00"))
        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "approve_financial_entry",
                "financial_entry_id": fin.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        fin.refresh_from_db()
        self.assertEqual(fin.approval_status, FinancialEntry.ApprovalStatus.APPROVED)
        self.assertEqual(calculate_workspace_balance(self.ws), Decimal("-300.00"))

    def test_reject_manual_outflow_does_not_impact_balance(self):
        fin = FinancialEntry.objects.create(
            workspace=self.ws,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.OUTFLOW,
            occurred_on=date(2026, 8, 1),
            amount=Decimal("120.00"),
            description="Compra pendente",
            created_by=self.admin_user,
            updated_by=self.admin_user,
            approval_status=FinancialEntry.ApprovalStatus.PENDING,
        )
        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "reject_financial_entry",
                "financial_entry_id": fin.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        fin.refresh_from_db()
        self.assertEqual(fin.approval_status, FinancialEntry.ApprovalStatus.REJECTED)
        self.assertEqual(calculate_workspace_balance(self.ws), Decimal("0.00"))

    def test_admin_config_creates_budget_goal(self):
        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "create_budget_goal",
                "goal_create-client": self.client_ref.pk,
                "goal_create-project": self.project.pk,
                "goal_create-minimum_target_amount": "1000.00",
                "goal_create-minimum_target_date": "2026-08-01",
                "goal_create-desired_target_amount": "2000.00",
                "goal_create-desired_target_date": "2026-09-01",
                "goal_create-visibility": BudgetGoal.Visibility.PUBLIC,
                "goal_create-description": "Meta do trimestre",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        goal = BudgetGoal.objects.get(project=self.project)
        self.assertEqual(goal.created_by, self.admin_user)

    def test_admin_config_updates_budget_goal(self):
        goal = BudgetGoal.objects.create(
            workspace=self.ws,
            client=self.client_ref,
            project=self.project,
            visibility=BudgetGoal.Visibility.PRIVATE,
            minimum_target_amount=Decimal("1000.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("2000.00"),
            desired_target_date=date(2026, 9, 1),
            description="Meta inicial",
            created_by=self.admin_user,
            updated_by=self.admin_user,
        )

        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "update_budget_goal",
                "budget_goal_id": goal.pk,
                "goal_edit-client": self.client_ref.pk,
                "goal_edit-project": self.project.pk,
                "goal_edit-minimum_target_amount": "1500.00",
                "goal_edit-minimum_target_date": "2026-08-10",
                "goal_edit-desired_target_amount": "3000.00",
                "goal_edit-desired_target_date": "2026-09-10",
                "goal_edit-visibility": BudgetGoal.Visibility.PUBLIC,
                "goal_edit-description": "Meta revisada",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.minimum_target_amount, Decimal("1500.00"))
        self.assertEqual(goal.desired_target_amount, Decimal("3000.00"))
        self.assertEqual(goal.visibility, BudgetGoal.Visibility.PUBLIC)
        self.assertEqual(goal.description, "Meta revisada")

    def test_admin_config_deletes_budget_goal(self):
        goal = BudgetGoal.objects.create(
            workspace=self.ws,
            client=self.client_ref,
            project=self.project,
            visibility=BudgetGoal.Visibility.PRIVATE,
            minimum_target_amount=Decimal("1000.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("2000.00"),
            desired_target_date=date(2026, 9, 1),
            created_by=self.admin_user,
            updated_by=self.admin_user,
        )
        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "delete_budget_goal",
                "budget_goal_id": goal.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BudgetGoal.objects.filter(pk=goal.pk).exists())


    def _png_upload(self) -> SimpleUploadedFile:
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), color=(30, 120, 90)).save(buf, format="PNG")
        buf.seek(0)
        return SimpleUploadedFile("workspace-logo.png", buf.read(), content_type="image/png")

    def test_admin_config_updates_workspace_logo(self):
        media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with self.settings(MEDIA_ROOT=str(media)):
            up = self._png_upload()
            response = self.client.post(
                reverse("admin-config"),
                {
                    "action": "update_workspace_avatar",
                    "workspace_avatar": up,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.ws.refresh_from_db()
        self.assertTrue(self.ws.workspace_avatar.name)

    def test_admin_config_removes_workspace_logo(self):
        media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with self.settings(MEDIA_ROOT=str(media)):
            up = self._png_upload()
            self.client.post(
                reverse("admin-config"),
                {
                    "action": "update_workspace_avatar",
                    "workspace_avatar": up,
                },
                follow=True,
            )
            self.ws.refresh_from_db()
            self.assertTrue(self.ws.workspace_avatar.name)
            response = self.client.post(
                reverse("admin-config"),
                {"action": "remove_workspace_avatar"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.ws.refresh_from_db()
        self.assertFalse(self.ws.workspace_avatar.name)


class BudgetGoalVisibilityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner-goal-vis@example.com",
            password="x",
            first_name="Owner",
            last_name="Goal",
        )
        self.creator = User.objects.create_user(
            email="creator-goal-vis@example.com",
            password="x",
            first_name="Creator",
            last_name="Goal",
        )
        self.other_member = User.objects.create_user(
            email="other-goal-vis@example.com",
            password="x",
            first_name="Other",
            last_name="Goal",
        )
        self.creator.platform_role = User.PlatformRole.MEMBER
        self.creator.save(update_fields=["platform_role"])
        self.other_member.platform_role = User.PlatformRole.MEMBER
        self.other_member.save(update_fields=["platform_role"])

        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WS Goal Visibility",
            workspace_description="",
        )
        Membership.objects.create(user=self.creator, workspace=self.ws, role="manager")
        Membership.objects.create(user=self.other_member, workspace=self.ws, role="user")

        self.client_ref = AppClient.objects.create(workspace=self.ws, name="Cliente Goal Visibility")
        self.project = Project.objects.create(
            workspace=self.ws,
            client=self.client_ref,
            name="Projeto Goal Visibility",
        )

    def test_creator_visualizes_private_goal(self):
        private_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            created_by=self.creator,
            visibility=BudgetGoal.Visibility.PRIVATE,
            minimum_target_amount=Decimal("100.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("200.00"),
            desired_target_date=date(2026, 9, 1),
        )

        visible_ids = set(
            BudgetGoal.visible_for_user(workspace=self.ws, user=self.creator).values_list("id", flat=True)
        )
        self.assertIn(private_goal.pk, visible_ids)

    def test_other_member_does_not_visualize_private_goal(self):
        private_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            created_by=self.creator,
            visibility=BudgetGoal.Visibility.PRIVATE,
            minimum_target_amount=Decimal("100.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("200.00"),
            desired_target_date=date(2026, 9, 1),
        )

        visible_ids = set(
            BudgetGoal.visible_for_user(workspace=self.ws, user=self.other_member).values_list("id", flat=True)
        )
        self.assertNotIn(private_goal.pk, visible_ids)

    def test_public_goal_is_visible_in_workspace(self):
        public_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            created_by=self.creator,
            visibility=BudgetGoal.Visibility.PUBLIC,
            minimum_target_amount=Decimal("100.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("200.00"),
            desired_target_date=date(2026, 9, 1),
        )

        visible_ids = set(
            BudgetGoal.visible_for_user(workspace=self.ws, user=self.other_member).values_list("id", flat=True)
        )
        public_ids = set(BudgetGoal.public_for_workspace(workspace=self.ws).values_list("id", flat=True))
        self.assertIn(public_goal.pk, visible_ids)
        self.assertIn(public_goal.pk, public_ids)

    def test_public_goal_still_respects_client_project_workspace_scope(self):
        ws2 = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WS Goal Visibility 2",
            workspace_description="",
        )
        client_other_ws = AppClient.objects.create(workspace=ws2, name="Cliente de outro WS")
        project_other_ws = Project.objects.create(
            workspace=ws2,
            client=client_other_ws,
            name="Projeto de outro WS",
        )

        with self.assertRaises(ValidationError):
            BudgetGoal.objects.create(
                workspace=self.ws,
                created_by=self.creator,
                visibility=BudgetGoal.Visibility.PUBLIC,
                client=client_other_ws,
                project=project_other_ws,
                minimum_target_amount=Decimal("100.00"),
                minimum_target_date=date(2026, 8, 1),
                desired_target_amount=Decimal("200.00"),
                desired_target_date=date(2026, 9, 1),
            )

    def test_mural_listing_uses_only_public_goals(self):
        private_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            created_by=self.creator,
            visibility=BudgetGoal.Visibility.PRIVATE,
            minimum_target_amount=Decimal("100.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("200.00"),
            desired_target_date=date(2026, 9, 1),
        )
        public_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            created_by=self.creator,
            visibility=BudgetGoal.Visibility.PUBLIC,
            minimum_target_amount=Decimal("300.00"),
            minimum_target_date=date(2026, 8, 2),
            desired_target_amount=Decimal("400.00"),
            desired_target_date=date(2026, 9, 2),
        )

        client = Client()
        client.force_login(self.creator)
        session = client.session
        session[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        session.save()

        response = client.get(reverse("user-dashboard"))
        self.assertEqual(response.status_code, 200)

        mural_goals = response.context["mural_ui"]["budgetGoals"]
        mural_goal_ids = {item["id"] for item in mural_goals}
        self.assertIn(public_goal.pk, mural_goal_ids)
        self.assertNotIn(private_goal.pk, mural_goal_ids)

    def test_mural_card_accepts_only_public_budget_goal(self):
        private_goal = BudgetGoal.objects.create(
            workspace=self.ws,
            created_by=self.creator,
            visibility=BudgetGoal.Visibility.PRIVATE,
            minimum_target_amount=Decimal("100.00"),
            minimum_target_date=date(2026, 8, 1),
            desired_target_amount=Decimal("200.00"),
            desired_target_date=date(2026, 9, 1),
        )
        with self.assertRaises(ValidationError):
            BoardCard.objects.create(
                workspace=self.ws,
                created_by=self.creator,
                updated_by=self.creator,
                visibility=BoardCard.Visibility.PUBLIC,
                public_lane=BoardCard.PublicLane.MEMBERS,
                title="Card com meta privada",
                budget_goal=private_goal,
                position=0,
            )


class JobRoleRefactorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner-jobrole@example.com",
            password="x",
            first_name="Owner",
            last_name="Role",
        )
        self.member = User.objects.create_user(
            email="member-jobrole@example.com",
            password="x",
            first_name="Member",
            last_name="Role",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])

        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WS JobRole",
            workspace_description="",
        )
        self.ws_other = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WS JobRole Other",
            workspace_description="",
        )
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")

        self.role_dev = JobRole.objects.create(workspace=self.ws, name="Dev")
        self.role_qa = JobRole.objects.create(workspace=self.ws, name="QA")
        self.role_other_ws = JobRole.objects.create(workspace=self.ws_other, name="Other WS Role")

    def test_create_job_role_for_workspace(self):
        role = JobRole.objects.create(
            workspace=self.ws,
            name="Analista",
            description="Cargo novo",
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.assertEqual(role.workspace, self.ws)
        self.assertEqual(role.name, "Analista")
        self.assertTrue(role.is_active)

    def test_employee_profile_uses_job_role_fk(self):
        profile = EmployeeProfile.objects.create(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=self.role_dev,
        )
        self.assertEqual(profile.current_job_role, self.role_dev)

    def test_job_history_uses_job_role_fk(self):
        profile = EmployeeProfile.objects.create(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=self.role_dev,
        )
        history = JobHistory.objects.create(
            employee_profile=profile,
            job_role=self.role_dev,
            start_date=date(2024, 1, 1),
        )
        self.assertEqual(history.job_role, self.role_dev)

    def test_prevents_using_role_from_other_workspace(self):
        profile = EmployeeProfile(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=self.role_other_ws,
        )
        with self.assertRaises(ValidationError):
            profile.full_clean()

        profile_ok = EmployeeProfile.objects.create(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=self.role_dev,
        )
        history = JobHistory(
            employee_profile=profile_ok,
            job_role=self.role_other_ws,
            start_date=date(2024, 2, 1),
        )
        with self.assertRaises(ValidationError):
            history.full_clean()

    def test_sync_between_active_history_and_profile_current_role(self):
        profile = EmployeeProfile.objects.create(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=self.role_dev,
        )
        JobHistory.objects.create(
            employee_profile=profile,
            job_role=self.role_qa,
            start_date=date(2024, 3, 1),
        )
        profile.refresh_from_db()
        self.assertEqual(profile.current_job_role, self.role_qa)

        active = JobHistory.objects.get(employee_profile=profile, end_date__isnull=True)
        active.end_date = date(2024, 3, 31)
        active.save()
        profile.refresh_from_db()
        self.assertIsNone(profile.current_job_role)

    def test_deactivating_role_does_not_break_existing_history(self):
        profile = EmployeeProfile.objects.create(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=self.role_dev,
        )
        history = JobHistory.objects.create(
            employee_profile=profile,
            job_role=self.role_dev,
            start_date=date(2024, 1, 1),
        )
        self.role_dev.is_active = False
        self.role_dev.save(update_fields=["is_active", "updated_at"])
        history.refresh_from_db()
        self.assertEqual(history.job_role_id, self.role_dev.pk)
        self.assertFalse(self.role_dev.is_active)


class UserAccountAvatarTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="ownerav@example.com",
            password="x",
            first_name="O",
            last_name="A",
        )
        self.member = User.objects.create_user(
            email="memberav@example.com",
            password="x",
            first_name="Mem",
            last_name="Ber",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WSAv",
            workspace_description="",
        )
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        self.client = Client()
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def _png_upload(self) -> SimpleUploadedFile:
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), color=(20, 60, 140)).save(buf, format="PNG")
        buf.seek(0)
        return SimpleUploadedFile("perfil.png", buf.read(), content_type="image/png")

    def test_post_avatar_saves_image_field(self):
        media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with self.settings(MEDIA_ROOT=str(media)):
            up = self._png_upload()
            r = self.client.post(
                reverse("user-account"),
                {"action": "update_avatar", "avatar": up},
                follow=True,
            )
        self.assertEqual(r.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.avatar.name)

    def test_post_avatar_rejects_non_image_content_type(self):
        media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with self.settings(MEDIA_ROOT=str(media)):
            bad = SimpleUploadedFile("x.bin", b"not an image", content_type="application/octet-stream")
            self.client.post(reverse("user-account"), {"action": "update_avatar", "avatar": bad})
        self.member.refresh_from_db()
        self.assertFalse(self.member.avatar.name)

    def test_post_remove_avatar_clears_image_field(self):
        media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with self.settings(MEDIA_ROOT=str(media)):
            up = self._png_upload()
            self.client.post(reverse("user-account"), {"action": "update_avatar", "avatar": up})
            self.member.refresh_from_db()
            self.assertTrue(self.member.avatar.name)
            r = self.client.post(reverse("user-account"), {"action": "remove_avatar"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.member.refresh_from_db()
        self.assertFalse(self.member.avatar.name)


class AdminAccountAvatarHttpTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="adminav@example.com",
            password="x",
            first_name="Ad",
            last_name="Min",
        )
        self.admin.platform_role = User.PlatformRole.ADMIN
        self.admin.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.admin,
            workspace_name="WSAdminAv",
            workspace_description="",
        )
        self.client = Client()
        self.client.force_login(self.admin)
        s = self.client.session
        s[SESSION_ADMIN_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def _png_upload(self) -> SimpleUploadedFile:
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), color=(40, 80, 120)).save(buf, format="PNG")
        buf.seek(0)
        return SimpleUploadedFile("gestor.png", buf.read(), content_type="image/png")

    def test_admin_post_avatar_saves_image_field(self):
        media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with self.settings(MEDIA_ROOT=str(media)):
            up = self._png_upload()
            r = self.client.post(
                reverse("admin-account"),
                {"action": "update_avatar", "avatar": up},
                follow=True,
            )
        self.assertEqual(r.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.avatar.name)

    def test_admin_post_remove_avatar_clears_image_field(self):
        media = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(media, ignore_errors=True))
        with self.settings(MEDIA_ROOT=str(media)):
            up = self._png_upload()
            self.client.post(reverse("admin-account"), {"action": "update_avatar", "avatar": up})
            self.admin.refresh_from_db()
            self.assertTrue(self.admin.avatar.name)
            r = self.client.post(reverse("admin-account"), {"action": "remove_avatar"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.avatar.name)


class CompensationPayCalculationTests(TestCase):
    """Regras centralizadas em ``app.compensation_pay`` + snapshots em ``TimeEntry``."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="ownercpay@example.com",
            password="x",
            first_name="O",
            last_name="C",
        )
        self.member = User.objects.create_user(
            email="membercpay@example.com",
            password="x",
            first_name="M",
            last_name="C",
        )
        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="WSCPay",
            workspace_description="",
        )
        role = JobRole.objects.create(workspace=self.ws, name="Dev")
        self.profile = EmployeeProfile.objects.create(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=role,
        )
        self.sched = WorkSchedule.objects.create(
            workspace=self.ws,
            name="SegSex8h",
            working_days=["mon", "tue", "wed", "thu", "fri"],
            expected_hours_per_day=8,
        )
        self.dept = Department.objects.create(
            workspace=self.ws,
            name="DeptCPay",
            schedule=self.sched,
        )
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )

    def _saved_entry(self, **kwargs):
        defaults = dict(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1.00"),
        )
        defaults.update(kwargs)
        return TimeEntry.objects.create(**defaults)

    def test_hourly_uses_rate_vigente_na_data_do_apontamento(self):
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.HOURLY,
            hourly_rate=Decimal("40.00"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.HOURLY,
            hourly_rate=Decimal("90.00"),
            start_date=date(2026, 2, 1),
        )
        e_jan = self._saved_entry(date=date(2026, 1, 15), hours=Decimal("2"))
        e_feb = self._saved_entry(date=date(2026, 2, 10), hours=Decimal("1"))
        self.assertEqual(e_jan.pay_amount_snapshot, Decimal("80.00"))
        self.assertEqual(e_feb.pay_amount_snapshot, Decimal("90.00"))

    def test_monthly_fixed_uses_expected_hours_of_month(self):
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.MONTHLY,
            monthly_salary=Decimal("4000.00"),
            monthly_salary_is_fixed=True,
            start_date=date(2026, 4, 1),
        )
        from app.compensation_pay import expected_working_hours_in_month

        expected_h = expected_working_hours_in_month(2026, 4, self.sched)
        self.assertGreater(expected_h, Decimal("0"))
        entry = self._saved_entry(date=date(2026, 4, 7), hours=Decimal("1"))
        hourly_eff = Decimal("4000.00") / expected_h
        self.assertEqual(entry.pay_amount_snapshot, (hourly_eff * Decimal("1")).quantize(Decimal("0.01")))
        self.assertEqual(entry.expected_month_hours_snapshot.quantize(Decimal("0.0001")), expected_h.quantize(Decimal("0.0001")))

    def test_monthly_non_fixed_uses_reference_hours(self):
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.MONTHLY,
            monthly_salary=Decimal("4000.00"),
            monthly_salary_is_fixed=False,
            monthly_reference_hours=Decimal("160.00"),
            start_date=date(2026, 5, 1),
        )
        entry = self._saved_entry(date=date(2026, 5, 12), hours=Decimal("2"))
        self.assertEqual(entry.pay_amount_snapshot, Decimal("50.00"))
        self.assertEqual(entry.expected_month_hours_snapshot, Decimal("160.0000"))

    def test_edit_saved_entry_recalculates_snapshot(self):
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.HOURLY,
            hourly_rate=Decimal("50.00"),
            start_date=date(2026, 6, 1),
        )
        entry = self._saved_entry(date=date(2026, 6, 3), hours=Decimal("1"))
        self.assertEqual(entry.pay_amount_snapshot, Decimal("50.00"))
        entry.hours = Decimal("3")
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.pay_amount_snapshot, Decimal("150.00"))

    def test_saved_timer_duration_minutes_pay(self):
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.HOURLY,
            hourly_rate=Decimal("60.00"),
            start_date=date(2026, 7, 1),
        )
        entry = TimeEntry(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=date(2026, 7, 2),
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.TIMER,
            hours=None,
            duration_minutes=30,
        )
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.pay_amount_snapshot, Decimal("30.00"))

    def test_delete_saved_keeps_reversal_amount_matching_snapshot(self):
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.HOURLY,
            hourly_rate=Decimal("10.00"),
            start_date=date(2026, 8, 1),
        )
        entry = self._saved_entry(date=date(2026, 8, 5), hours=Decimal("2"))
        fin = FinancialEntry.objects.get(time_entry=entry, entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST)
        self.assertEqual(fin.amount, entry.pay_amount_snapshot)
        entry.delete(financial_actor=self.owner)
        rev = FinancialEntry.objects.get(reversal_of=fin)
        self.assertEqual(rev.amount, fin.amount)


class AdminDashboardDataTests(TestCase):
    """Dashboard do gestor: agregações reais por workspace e período."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admindash@example.com",
            password="x",
            first_name="Ad",
            last_name="Dash",
        )
        self.admin.platform_role = User.PlatformRole.ADMIN
        self.admin.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.admin,
            workspace_name="WSDash",
            workspace_description="",
        )
        self.ws_other = Workspace.objects.create(
            owner=self.admin,
            workspace_name="WSDashOther",
            workspace_description="",
        )
        self.member = User.objects.create_user(
            email="memberdash@example.com",
            password="x",
            first_name="Mem",
            last_name="Dash",
        )
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        role = JobRole.objects.create(workspace=self.ws, name="Dev")
        self.profile = EmployeeProfile.objects.create(
            user=self.member,
            workspace=self.ws,
            employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
            hire_date=date(2024, 1, 1),
            current_job_role=role,
        )
        self.sched = WorkSchedule.objects.create(
            workspace=self.ws,
            name="DashSch",
            working_days=["mon", "tue", "wed", "thu", "fri"],
            expected_hours_per_day=8,
        )
        self.dept = Department.objects.create(
            workspace=self.ws,
            name="DeptDash",
            schedule=self.sched,
        )
        UserDepartment.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            is_primary=True,
        )
        CompensationHistory.objects.create(
            employee_profile=self.profile,
            compensation_type=CompensationHistory.CompensationType.HOURLY,
            hourly_rate=Decimal("100.00"),
            start_date=date(2020, 1, 1),
        )
        self.client_http = Client()
        self.client_http.force_login(self.admin)
        s = self.client_http.session
        s[SESSION_ADMIN_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def _today(self):
        return timezone.localdate()

    def test_http_dashboard_empty_workspace(self):
        r = self.client_http.get(reverse("admin-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Não há dados suficientes")

    def test_http_dashboard_shows_financial_when_manual_entry(self):
        FinancialEntry.objects.create(
            workspace=self.ws,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.INFLOW,
            occurred_on=self._today(),
            amount=Decimal("250.00"),
            description="Entrada teste",
            created_by=self.admin,
        )
        r = self.client_http.get(reverse("admin-dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Saldo atual")
        self.assertContains(r, "250,00")

    def test_daily_financial_bars_split_by_day_total(self):
        today = self._today()
        FinancialEntry.objects.create(
            workspace=self.ws,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.INFLOW,
            occurred_on=today,
            amount=Decimal("1000.00"),
            description="In",
            created_by=self.admin,
        )
        FinancialEntry.objects.create(
            workspace=self.ws,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.OUTFLOW,
            occurred_on=today,
            amount=Decimal("500.00"),
            description="Out",
            created_by=self.admin,
            updated_by=self.admin,
            approval_status=FinancialEntry.ApprovalStatus.APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
        )
        dash = build_admin_dashboard(self.ws, "7d")
        row = next(d for d in dash["daily_series"] if d["day"] == today.isoformat())
        self.assertEqual(row["pct_in"] + row["pct_out"], 100)
        self.assertEqual(row["pct_in"], 67)
        self.assertEqual(row["pct_out"], 33)

    def test_dashboard_ignores_pending_outflow_in_real_cash(self):
        today = self._today()
        FinancialEntry.objects.create(
            workspace=self.ws,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.INFLOW,
            occurred_on=today,
            amount=Decimal("1000.00"),
            description="In",
            created_by=self.admin,
        )
        FinancialEntry.objects.create(
            workspace=self.ws,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.OUTFLOW,
            occurred_on=today,
            amount=Decimal("500.00"),
            description="Out pending",
            created_by=self.admin,
            updated_by=self.admin,
            approval_status=FinancialEntry.ApprovalStatus.PENDING,
        )
        dash = build_admin_dashboard(self.ws, "7d")
        self.assertEqual(dash["current_balance"], Decimal("1000.00"))

    def test_build_dashboard_counts_saved_time_only(self):
        today = self._today()
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            date=today,
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("2.00"),
        )
        dash = build_admin_dashboard(self.ws, "7d")
        self.assertGreater(dash["total_logged_hours"], 0)
        self.assertGreater(dash["team_cost_total"], Decimal("0"))

    def test_build_dashboard_other_workspace_excluded(self):
        FinancialEntry.objects.create(
            workspace=self.ws_other,
            entry_kind=FinancialEntry.EntryKind.MANUAL,
            flow_type=FinancialEntry.FlowType.INFLOW,
            occurred_on=self._today(),
            amount=Decimal("99999.00"),
            description="Outro WS",
            created_by=self.admin,
        )
        dash = build_admin_dashboard(self.ws, "7d")
        self.assertFalse(dash["has_any_content"])

    def test_project_budget_block_when_budget_set(self):
        cli = AppClient.objects.create(workspace=self.ws, name="Cliente B")
        UserClient.objects.create(user=self.member, workspace=self.ws, client=cli)
        proj = Project.objects.create(
            workspace=self.ws,
            client=cli,
            name="Proj B",
            budget=Decimal("1000.00"),
            estimated_hours=Decimal("10.00"),
        )
        UserProject.objects.create(user=self.member, workspace=self.ws, project=proj)
        today = self._today()
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            client=cli,
            project=proj,
            date=today,
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("9.00"),
        )
        dash = build_admin_dashboard(self.ws, "7d")
        self.assertTrue(dash["show_budget_block"])
        self.assertTrue(dash["show_hours_estimate_block"])
        self.assertGreaterEqual(len(dash["risky_projects"]), 1)

    def test_project_without_budget_no_budget_section(self):
        cli = AppClient.objects.create(workspace=self.ws, name="Cliente C")
        UserClient.objects.create(user=self.member, workspace=self.ws, client=cli)
        proj_nb = Project.objects.create(
            workspace=self.ws, client=cli, name="Proj Sem Budget", budget=None
        )
        UserProject.objects.create(user=self.member, workspace=self.ws, project=proj_nb)
        today = self._today()
        TimeEntry.objects.create(
            user=self.member,
            workspace=self.ws,
            department=self.dept,
            client=cli,
            project=proj_nb,
            date=today,
            status=TimeEntry.Status.SAVED,
            entry_mode=TimeEntry.EntryMode.DURATION,
            hours=Decimal("1.00"),
        )
        dash = build_admin_dashboard(self.ws, "7d")
        rows = [r for r in dash["project_budget_rows"] if r["name"] == "Proj Sem Budget"]
        self.assertEqual(len(rows), 0)


class MuralMemberApiTests(TestCase):
    """Backend mínimo do Mural/Kanban (membro)."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.owner = User.objects.create_user(
            email="mural-owner@example.com",
            password="x",
            first_name="O",
            last_name="wner",
        )
        self.member_a = User.objects.create_user(
            email="mural-a@example.com",
            password="x",
            first_name="A",
            last_name="lpha",
        )
        self.member_b = User.objects.create_user(
            email="mural-b@example.com",
            password="x",
            first_name="B",
            last_name="ravo",
        )
        for u in (self.member_a, self.member_b):
            u.platform_role = User.PlatformRole.MEMBER
            u.save(update_fields=["platform_role"])

        self.ws = Workspace.objects.create(
            owner=self.owner,
            workspace_name="Mural WS",
            workspace_description="",
        )
        for u in (self.member_a, self.member_b):
            Membership.objects.create(user=u, workspace=self.ws, role="user")
            create_hourly_compensation(u, self.ws)

        self.dept = Department.objects.create(
            workspace=self.ws,
            name="Dept Mural",
            time_tracking_mode=Department.TimeTrackingMode.DURATION,
        )
        for u in (self.member_a, self.member_b):
            UserDepartment.objects.create(
                user=u,
                workspace=self.ws,
                department=self.dept,
                is_primary=True,
            )

        self.cli = AppClient.objects.create(workspace=self.ws, name="Cli Mural")
        for u in (self.member_a, self.member_b):
            UserClient.objects.create(user=u, workspace=self.ws, client=self.cli)
        self.proj = Project.objects.create(
            workspace=self.ws,
            client=self.cli,
            name="Proj Mural",
        )
        for u in (self.member_a, self.member_b):
            UserProject.objects.create(user=u, workspace=self.ws, project=self.proj)
        self.task = Task.objects.create(project=self.proj, name="Task Mural")

        self.ws_other = Workspace.objects.create(
            owner=self.owner,
            workspace_name="Outro WS",
            workspace_description="",
        )
        self.cli_other = AppClient.objects.create(workspace=self.ws_other, name="Cli Outro")
        self.proj_other = Project.objects.create(
            workspace=self.ws_other,
            client=self.cli_other,
            name="Proj Outro",
        )

    def _session_ws(self, user, ws: Workspace):
        self.client.force_login(user)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = ws.pk
        s.save()

    def test_mural_default_columns_created(self):
        self._session_ws(self.member_a, self.ws)
        self.assertEqual(PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).count(), 0)
        r = self.client.get(reverse("user-mural-data"))
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data["ok"])
        cols = data["mural"]["private_columns"]
        self.assertEqual(len(cols), 7)
        names = [c["name"] for c in cols]
        self.assertIn("Rascunho", names)
        self.assertIn("Concluído", names)
        self.assertEqual(
            PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).count(),
            7,
        )

    def test_private_cards_only_visible_to_creator(self):
        self._session_ws(self.member_a, self.ws)
        r0 = self.client.get(reverse("user-mural-data"))
        col_id = json.loads(r0.content)["mural"]["private_columns"][0]["id"]
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {
                    "visibility": "private",
                    "private_column_id": col_id,
                    "title": "Segredo A",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 201)
        card_id = json.loads(r1.content)["card"]["id"]

        self._session_ws(self.member_b, self.ws)
        r2 = self.client.get(reverse("user-mural-data"))
        ids = [c["id"] for c in json.loads(r2.content)["mural"]["private_cards"]]
        self.assertNotIn(card_id, ids)

        r3 = self.client.patch(
            reverse("user-mural-card-update", kwargs={"card_id": card_id}),
            data=json.dumps({"title": "Hack"}),
            content_type="application/json",
        )
        self.assertEqual(r3.status_code, 404)

    def test_public_cards_visible_to_all_members(self):
        self._session_ws(self.member_a, self.ws)
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "Anúncio"}),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 201)
        cid = json.loads(r1.content)["card"]["id"]

        self._session_ws(self.member_b, self.ws)
        r2 = self.client.get(reverse("user-mural-data"))
        pub_ids = [c["id"] for c in json.loads(r2.content)["mural"]["public_cards"]]
        self.assertIn(cid, pub_ids)

    def test_rename_private_column(self):
        self._session_ws(self.member_a, self.ws)
        self.client.get(reverse("user-mural-data"))
        col = PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).first()
        assert col is not None
        r = self.client.patch(
            reverse("user-mural-column-update", kwargs={"column_id": col.pk}),
            data=json.dumps({"name": "Ideias"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        col.refresh_from_db()
        self.assertEqual(col.name, "Ideias")

    def test_create_private_card_and_move_to_public(self):
        self._session_ws(self.member_a, self.ws)
        self.client.get(reverse("user-mural-data"))
        col = PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).first()
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {
                    "visibility": "private",
                    "private_column_id": col.pk,
                    "title": "Migrar",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 201)
        card_id = json.loads(r1.content)["card"]["id"]
        r2 = self.client.post(reverse("user-mural-card-move-to-public", kwargs={"card_id": card_id}))
        self.assertEqual(r2.status_code, 200, msg=r2.content.decode())
        card = BoardCard.objects.get(pk=card_id)
        self.assertEqual(card.visibility, BoardCard.Visibility.PUBLIC)
        self.assertIsNone(card.private_column_id)

    def test_reorder_private_card(self):
        self._session_ws(self.member_a, self.ws)
        self.client.get(reverse("user-mural-data"))
        col = PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).first()
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {"visibility": "private", "private_column_id": col.pk, "title": "Um"}
            ),
            content_type="application/json",
        )
        r2 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {"visibility": "private", "private_column_id": col.pk, "title": "Dois"}
            ),
            content_type="application/json",
        )
        c1 = json.loads(r1.content)["card"]["id"]
        c2 = json.loads(r2.content)["card"]["id"]
        r3 = self.client.post(
            reverse("user-mural-card-reposition", kwargs={"card_id": c2}),
            data=json.dumps({"insert_index": 0}),
            content_type="application/json",
        )
        self.assertEqual(r3.status_code, 200)
        cards = list(
            BoardCard.objects.filter(
                workspace=self.ws,
                visibility=BoardCard.Visibility.PRIVATE,
                private_column=col,
            ).order_by("position", "pk")
        )
        self.assertEqual([c.pk for c in cards], [c2, c1])

    def test_reorder_public_card(self):
        self._session_ws(self.member_a, self.ws)
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "P1"}),
            content_type="application/json",
        )
        r2 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "P2"}),
            content_type="application/json",
        )
        id1 = json.loads(r1.content)["card"]["id"]
        id2 = json.loads(r2.content)["card"]["id"]
        r3 = self.client.post(
            reverse("user-mural-card-reposition", kwargs={"card_id": id1}),
            data=json.dumps({"insert_index": 1}),
            content_type="application/json",
        )
        self.assertEqual(r3.status_code, 200)
        ordered = list(
            BoardCard.objects.filter(workspace=self.ws, visibility=BoardCard.Visibility.PUBLIC).order_by(
                "position", "pk"
            )
        )
        self.assertEqual([c.pk for c in ordered], [id2, id1])

    def test_card_fk_must_belong_to_workspace(self):
        self._session_ws(self.member_a, self.ws)
        self.client.get(reverse("user-mural-data"))
        col = PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).first()
        r = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {
                    "visibility": "private",
                    "private_column_id": col.pk,
                    "title": "Errado",
                    "project_id": self.proj_other.pk,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_reorder_private_columns(self):
        self._session_ws(self.member_a, self.ws)
        self.client.get(reverse("user-mural-data"))
        cols = list(
            PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).order_by("position", "pk")
        )
        self.assertGreaterEqual(len(cols), 3)
        new_order = [cols[2].pk, cols[0].pk, cols[1].pk] + [c.pk for c in cols[3:]]
        r = self.client.post(
            reverse("user-mural-columns-reorder"),
            data=json.dumps({"ordered_column_ids": new_order}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, msg=r.content.decode())
        refreshed = list(
            PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).order_by("position", "pk")
        )
        self.assertEqual([c.pk for c in refreshed], new_order)

    def test_non_creator_cannot_reposition_public_card(self):
        self._session_ws(self.member_a, self.ws)
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "Do A"}),
            content_type="application/json",
        )
        card_id = json.loads(r1.content)["card"]["id"]
        self._session_ws(self.member_b, self.ws)
        r2 = self.client.post(
            reverse("user-mural-card-reposition", kwargs={"card_id": card_id}),
            data=json.dumps({"insert_index": 0}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 403)

    def test_move_private_card_between_columns(self):
        self._session_ws(self.member_a, self.ws)
        self.client.get(reverse("user-mural-data"))
        cols = list(
            PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).order_by("position", "pk")
        )
        self.assertGreaterEqual(len(cols), 2)
        c0, c1 = cols[0], cols[1]
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {"visibility": "private", "private_column_id": c0.pk, "title": "Na coluna 0"}
            ),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 201)
        self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {"visibility": "private", "private_column_id": c1.pk, "title": "Fixo coluna 1"}
            ),
            content_type="application/json",
        )
        card_id = json.loads(r1.content)["card"]["id"]
        r3 = self.client.post(
            reverse("user-mural-card-move-private", kwargs={"card_id": card_id}),
            data=json.dumps({"private_column_id": c1.pk, "insert_index": 0}),
            content_type="application/json",
        )
        self.assertEqual(r3.status_code, 200, msg=r3.content.decode())
        card = BoardCard.objects.get(pk=card_id)
        self.assertEqual(card.private_column_id, c1.pk)
        self.assertEqual(card.visibility, BoardCard.Visibility.PRIVATE)

    def test_mural_payload_includes_creator_label_for_public(self):
        self._session_ws(self.member_a, self.ws)
        self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "Comunicado"}),
            content_type="application/json",
        )
        r = self.client.get(reverse("user-mural-data"))
        self.assertEqual(r.status_code, 200)
        pub = json.loads(r.content)["mural"]["public_cards"]
        self.assertTrue(pub)
        self.assertIn("creator_label", pub[0])
        self.assertIn("creator_avatar_url", pub[0])

    def test_member_cannot_create_public_card_in_management_lane(self):
        self._session_ws(self.member_a, self.ws)
        r = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {
                    "visibility": "public",
                    "public_lane": BoardCard.PublicLane.MANAGEMENT,
                    "title": "Não pode",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_member_moves_private_to_public_only_members_lane(self):
        self._session_ws(self.member_a, self.ws)
        self.client.get(reverse("user-mural-data"))
        col = PrivateBoardColumn.objects.filter(workspace=self.ws, user=self.member_a).first()
        assert col is not None
        r1 = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "private", "private_column_id": col.pk, "title": "Mover"}),
            content_type="application/json",
        )
        card_id = json.loads(r1.content)["card"]["id"]
        r2 = self.client.post(reverse("user-mural-card-move-to-public", kwargs={"card_id": card_id}))
        self.assertEqual(r2.status_code, 200, msg=r2.content.decode())
        card = BoardCard.objects.get(pk=card_id)
        self.assertEqual(card.public_lane, BoardCard.PublicLane.MEMBERS)

    def test_member_visualizes_public_cards_from_both_lanes(self):
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.member_a,
            updated_by=self.member_a,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MEMBERS,
            title="Publico membros",
            position=0,
        )
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.owner,
            updated_by=self.owner,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MANAGEMENT,
            title="Publico gestão",
            position=0,
        )
        self._session_ws(self.member_b, self.ws)
        r = self.client.get(reverse("user-mural-data"))
        self.assertEqual(r.status_code, 200)
        mural = json.loads(r.content)["mural"]
        self.assertEqual(len(mural["public_cards_by_lane"]["members"]), 1)
        self.assertEqual(len(mural["public_cards_by_lane"]["management"]), 1)

    def test_member_cannot_edit_or_delete_public_card_from_other_author(self):
        card = BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.member_a,
            updated_by=self.member_a,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MEMBERS,
            title="Do outro",
            position=0,
        )
        self._session_ws(self.member_b, self.ws)
        r_upd = self.client.patch(
            reverse("user-mural-card-update", kwargs={"card_id": card.pk}),
            data=json.dumps({"title": "Hack"}),
            content_type="application/json",
        )
        self.assertEqual(r_upd.status_code, 403)
        r_del = self.client.delete(reverse("user-mural-card-delete", kwargs={"card_id": card.pk}))
        self.assertEqual(r_del.status_code, 403)

    def test_copy_public_card_to_private_creates_copy_and_preserves_original(self):
        card = BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.member_a,
            updated_by=self.member_a,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MEMBERS,
            title="Original público",
            description="Desc",
            position=0,
        )
        self._session_ws(self.member_b, self.ws)
        self.client.get(reverse("user-mural-data"))
        r = self.client.post(
            reverse("user-mural-card-copy-to-private", kwargs={"card_id": card.pk}),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, msg=r.content.decode())
        copied_id = json.loads(r.content)["card"]["id"]
        copied = BoardCard.objects.get(pk=copied_id)
        card.refresh_from_db()
        self.assertEqual(copied.visibility, BoardCard.Visibility.PRIVATE)
        self.assertIsNotNone(copied.private_column_id)
        self.assertIsNone(copied.public_lane)
        self.assertEqual(copied.created_by, self.member_b)
        self.assertEqual(card.visibility, BoardCard.Visibility.PUBLIC)
        self.assertEqual(card.public_lane, BoardCard.PublicLane.MEMBERS)

    def test_mural_payload_returns_public_cards_grouped_by_lane(self):
        self._session_ws(self.member_a, self.ws)
        self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "Comum"}),
            content_type="application/json",
        )
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.owner,
            updated_by=self.owner,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MANAGEMENT,
            title="Gestão",
            position=0,
        )
        r = self.client.get(reverse("user-mural-data"))
        self.assertEqual(r.status_code, 200)
        mural = json.loads(r.content)["mural"]
        self.assertIn("public_cards_by_lane", mural)
        self.assertIn("members", mural["public_cards_by_lane"])
        self.assertIn("management", mural["public_cards_by_lane"])


class AdminMuralApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.admin = User.objects.create_user(
            email="admin-mural@example.com",
            password="x",
            first_name="Admin",
            last_name="Mural",
        )
        self.admin.platform_role = User.PlatformRole.ADMIN
        self.admin.save(update_fields=["platform_role"])
        self.member = User.objects.create_user(
            email="member-mural-admin@example.com",
            password="x",
            first_name="Member",
            last_name="Board",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.admin,
            workspace_name="WS Admin Mural",
            workspace_description="",
        )
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")

        self.ws_other = Workspace.objects.create(
            owner=self.admin,
            workspace_name="WS Outro",
            workspace_description="",
        )
        Membership.objects.create(user=self.member, workspace=self.ws_other, role="user")

    def _session_admin(self):
        self.client.force_login(self.admin)
        s = self.client.session
        s[SESSION_ADMIN_WORKSPACE_KEY] = self.ws.pk
        s.save()

    def _session_member(self, ws: Workspace):
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = ws.pk
        s.save()

    def _member_first_private_column(self) -> int:
        self._session_member(self.ws)
        r = self.client.get(reverse("user-mural-data"))
        self.assertEqual(r.status_code, 200)
        return int(json.loads(r.content)["mural"]["private_columns"][0]["id"])

    def test_admin_mural_route_and_menu(self):
        self._session_admin()
        r = self.client.get(reverse("admin-mural"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, reverse("admin-mural"))

    def test_admin_mural_data_has_two_public_lanes_and_private_board(self):
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.admin,
            updated_by=self.admin,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MANAGEMENT,
            title="Gestão",
            position=0,
        )
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.member,
            updated_by=self.member,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MEMBERS,
            title="Membros",
            position=0,
        )
        self._session_admin()
        r = self.client.get(reverse("admin-mural-data"))
        self.assertEqual(r.status_code, 200)
        mural = json.loads(r.content)["mural"]
        self.assertIn("members", mural["public_cards_by_lane"])
        self.assertIn("management", mural["public_cards_by_lane"])
        self.assertGreaterEqual(len(mural["private_columns"]), 1)

    def test_admin_lock_members_lane_blocks_member_publish_and_move(self):
        col_id = self._member_first_private_column()
        self._session_admin()
        r_lock = self.client.post(
            reverse("admin-mural-members-lane-lock"),
            data=json.dumps({"locked": True}),
            content_type="application/json",
        )
        self.assertEqual(r_lock.status_code, 200)

        self._session_member(self.ws)
        r_create_public = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "Pub bloqueado"}),
            content_type="application/json",
        )
        self.assertEqual(r_create_public.status_code, 403)

        r_private = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "private", "private_column_id": col_id, "title": "Privado"}),
            content_type="application/json",
        )
        self.assertEqual(r_private.status_code, 201)
        private_id = json.loads(r_private.content)["card"]["id"]
        r_move = self.client.post(reverse("user-mural-card-move-to-public", kwargs={"card_id": private_id}))
        self.assertEqual(r_move.status_code, 403)

    def test_admin_unlock_members_lane_restores_member_publish(self):
        self._session_admin()
        self.client.post(
            reverse("admin-mural-members-lane-lock"),
            data=json.dumps({"locked": True}),
            content_type="application/json",
        )
        self.client.post(
            reverse("admin-mural-members-lane-lock"),
            data=json.dumps({"locked": False}),
            content_type="application/json",
        )
        self._session_member(self.ws)
        r = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps({"visibility": "public", "title": "Liberado"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

    def test_admin_clear_members_lane_only_affects_members_public(self):
        member_col = self._member_first_private_column()
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.member,
            updated_by=self.member,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MEMBERS,
            title="m1",
            position=0,
        )
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.admin,
            updated_by=self.admin,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MANAGEMENT,
            title="g1",
            position=0,
        )
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.member,
            updated_by=self.member,
            visibility=BoardCard.Visibility.PRIVATE,
            private_column_id=member_col,
            title="privado",
            position=0,
        )
        self._session_admin()
        r = self.client.post(reverse("admin-mural-members-lane-clear"), data=json.dumps({}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            BoardCard.objects.filter(
                workspace=self.ws,
                visibility=BoardCard.Visibility.PUBLIC,
                public_lane=BoardCard.PublicLane.MEMBERS,
            ).exists()
        )
        self.assertTrue(
            BoardCard.objects.filter(
                workspace=self.ws,
                visibility=BoardCard.Visibility.PUBLIC,
                public_lane=BoardCard.PublicLane.MANAGEMENT,
            ).exists()
        )
        self.assertTrue(
            BoardCard.objects.filter(
                workspace=self.ws,
                visibility=BoardCard.Visibility.PRIVATE,
                created_by=self.member,
            ).exists()
        )

    def test_admin_lock_is_workspace_isolated(self):
        self._session_admin()
        self.client.post(
            reverse("admin-mural-members-lane-lock"),
            data=json.dumps({"locked": True}),
            content_type="application/json",
        )
        self.ws.refresh_from_db()
        self.ws_other.refresh_from_db()
        self.assertTrue(self.ws.mural_members_lane_locked)
        self.assertFalse(self.ws_other.mural_members_lane_locked)


class MuralStatusPaletteTests(TestCase):
    """Status configuráveis e paleta fixa (colunas/cards)."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.admin = User.objects.create_user(
            email="mural-palette-admin@example.com",
            password="x",
            first_name="Ad",
            last_name="Min",
        )
        self.admin.platform_role = User.PlatformRole.ADMIN
        self.admin.save(update_fields=["platform_role"])
        self.member = User.objects.create_user(
            email="mural-palette-member@example.com",
            password="x",
            first_name="Mem",
            last_name="Ber",
        )
        self.member.platform_role = User.PlatformRole.MEMBER
        self.member.save(update_fields=["platform_role"])
        self.ws = Workspace.objects.create(
            owner=self.admin,
            workspace_name="WS Palette",
            workspace_description="",
        )
        self.ws_other = Workspace.objects.create(
            owner=self.admin,
            workspace_name="WS Palette Outro",
            workspace_description="",
        )
        Membership.objects.create(user=self.member, workspace=self.ws, role="user")
        Membership.objects.create(user=self.member, workspace=self.ws_other, role="user")

    def _session_admin(self, ws: Workspace | None = None):
        self.client.force_login(self.admin)
        s = self.client.session
        s[SESSION_ADMIN_WORKSPACE_KEY] = (ws or self.ws).pk
        s.save()

    def _session_member(self, ws: Workspace):
        self.client.force_login(self.member)
        s = self.client.session
        s[SESSION_MEMBER_WORKSPACE_KEY] = ws.pk
        s.save()

    def test_admin_creates_status_and_mural_payload_includes_palette_fields(self):
        self._session_admin()
        r = self.client.post(
            reverse("admin-mural-status-create"),
            data=json.dumps({"name": "Em revisão", "color_key": "blue"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, msg=r.content.decode())
        body = json.loads(r.content)
        self.assertEqual(body["status"]["color_hex"], "#2772cd")
        r2 = self.client.get(reverse("admin-mural-data"))
        mural = json.loads(r2.content)["mural"]
        self.assertIn("mural_statuses_all", mural)
        self.assertEqual(len(mural["mural_statuses_all"]), 1)
        self.assertEqual(len(mural["mural_statuses"]), 1)

    def test_member_payload_only_lists_active_statuses(self):
        MuralStatusOption.objects.create(
            workspace=self.ws,
            name="Ativo",
            position=0,
            is_active=True,
            color_key="green",
            created_by=self.admin,
            updated_by=self.admin,
        )
        MuralStatusOption.objects.create(
            workspace=self.ws,
            name="Legado",
            position=1,
            is_active=False,
            color_key="red",
            created_by=self.admin,
            updated_by=self.admin,
        )
        self._session_member(self.ws)
        r = self.client.get(reverse("user-mural-data"))
        mural = json.loads(r.content)["mural"]
        self.assertEqual(len(mural["mural_statuses"]), 1)
        self.assertEqual(mural["mural_statuses"][0]["name"], "Ativo")
        self.assertNotIn("mural_statuses_all", mural)

    def test_admin_reorders_statuses(self):
        self._session_admin()
        a = json.loads(
            self.client.post(
                reverse("admin-mural-status-create"),
                data=json.dumps({"name": "A", "color_key": "red"}),
                content_type="application/json",
            ).content
        )["status"]["id"]
        b = json.loads(
            self.client.post(
                reverse("admin-mural-status-create"),
                data=json.dumps({"name": "B", "color_key": "blue"}),
                content_type="application/json",
            ).content
        )["status"]["id"]
        r = self.client.post(
            reverse("admin-mural-status-reorder"),
            data=json.dumps({"ordered_status_ids": [b, a]}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, msg=r.content.decode())
        mural = json.loads(self.client.get(reverse("admin-mural-data")).content)["mural"]
        names = [s["name"] for s in mural["mural_statuses_all"]]
        self.assertEqual(names, ["B", "A"])

    def test_card_rejects_mural_status_from_other_workspace(self):
        st_other = MuralStatusOption.objects.create(
            workspace=self.ws_other,
            name="Outro WS",
            position=0,
            is_active=True,
            color_key="aqua",
            created_by=self.admin,
            updated_by=self.admin,
        )
        self._session_member(self.ws)
        r0 = self.client.get(reverse("user-mural-data"))
        col_id = json.loads(r0.content)["mural"]["private_columns"][0]["id"]
        r = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {
                    "visibility": "private",
                    "private_column_id": col_id,
                    "title": "X",
                    "mural_status_id": st_other.pk,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_column_rejects_invalid_color_key(self):
        self._session_member(self.ws)
        r0 = self.client.get(reverse("user-mural-data"))
        col_id = json.loads(r0.content)["mural"]["private_columns"][0]["id"]
        r = self.client.patch(
            reverse("user-mural-column-update", kwargs={"column_id": col_id}),
            data=json.dumps({"name": "Renomeado", "color_key": "not-a-palette-key"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_member_cannot_assign_inactive_status_on_new_card(self):
        st = MuralStatusOption.objects.create(
            workspace=self.ws,
            name="Inativo",
            position=0,
            is_active=False,
            color_key="purple",
            created_by=self.admin,
            updated_by=self.admin,
        )
        self._session_member(self.ws)
        r0 = self.client.get(reverse("user-mural-data"))
        col_id = json.loads(r0.content)["mural"]["private_columns"][0]["id"]
        r = self.client.post(
            reverse("user-mural-card-create"),
            data=json.dumps(
                {
                    "visibility": "private",
                    "private_column_id": col_id,
                    "title": "Novo",
                    "mural_status_id": st.pk,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_public_card_serializes_status_and_color_for_display(self):
        st = MuralStatusOption.objects.create(
            workspace=self.ws,
            name="Publicado",
            position=0,
            is_active=True,
            color_key="orange",
            created_by=self.admin,
            updated_by=self.admin,
        )
        BoardCard.objects.create(
            workspace=self.ws,
            created_by=self.member,
            updated_by=self.member,
            visibility=BoardCard.Visibility.PUBLIC,
            public_lane=BoardCard.PublicLane.MEMBERS,
            title="Com status",
            position=0,
            mural_status=st,
            color_key="green",
        )
        self._session_member(self.ws)
        r = self.client.get(reverse("user-mural-data"))
        self.assertEqual(r.status_code, 200)
        cards = json.loads(r.content)["mural"]["public_cards"]
        self.assertTrue(cards)
        c0 = cards[0]
        self.assertEqual(c0["mural_status_name"], "Publicado")
        self.assertEqual(c0["mural_status_color_hex"], "#e15319")
        self.assertEqual(c0["color_hex"], "#20b153")
