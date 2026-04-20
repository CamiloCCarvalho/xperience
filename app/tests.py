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

from app.models import (
    Client as AppClient,
    BudgetGoal,
    CompensationHistory,
    Department,
    EmployeeProfile,
    FinancialEntry,
    Membership,
    Project,
    TimeEntry,
    TimeEntryTemplate,
    UserClient,
    UserDepartment,
    UserProject,
    WorkSchedule,
    Workspace,
)
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
    profile = EmployeeProfile.objects.create(
        user=user,
        workspace=workspace,
        employment_status=EmployeeProfile.EmploymentStatus.ACTIVE,
        hire_date=date(2024, 1, 1),
        current_job_title="Contributor",
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
        self.assertEqual(fin.amount, Decimal("100.00"))
        self.assertEqual(fin.user, self.member)
        self.assertEqual(fin.project, self.project)

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
        source_entry_id = entry.pk
        entry.delete(financial_actor=self.owner)
        original.refresh_from_db()
        reversal = FinancialEntry.objects.get(reversal_of=original)
        self.assertEqual(reversal.flow_type, FinancialEntry.FlowType.INFLOW)
        self.assertEqual(reversal.amount, original.amount)
        self.assertEqual(reversal.source_time_entry_id, source_entry_id)
        self.assertEqual(reversal.created_by, self.owner)

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

    def test_admin_config_creates_budget_goal(self):
        response = self.client.post(
            reverse("admin-config"),
            {
                "action": "create_budget_goal",
                "client": self.client_ref.pk,
                "project": self.project.pk,
                "minimum_target_amount": "1000.00",
                "minimum_target_date": "2026-08-01",
                "desired_target_amount": "2000.00",
                "desired_target_date": "2026-09-01",
                "description": "Meta do trimestre",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        goal = BudgetGoal.objects.get(project=self.project)
        self.assertEqual(goal.created_by, self.admin_user)


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
