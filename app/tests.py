import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import (
    Department,
    Membership,
    TimeEntry,
    TimeEntryTemplate,
    UserDepartment,
    Workspace,
)
from app.time_entry_timer import (
    assert_user_may_delete_time_entry,
    assert_user_may_edit_time_entry,
    get_active_draft,
    start_timer,
    stop_timer,
)
from app.workspace_session import SESSION_MEMBER_WORKSPACE_KEY

User = get_user_model()


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

        r = self.client.post(reverse("user-time-entry-timer-start"))
        self.assertEqual(r.status_code, 201)
        eid = r.json()["entry"]["id"]

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
            },
        )
        self.assertEqual(r.status_code, 201, r.content)
        eid = r.json()["entry"]["id"]
        te = TimeEntry.objects.get(pk=eid)
        self.assertEqual(te.entry_mode, TimeEntry.EntryMode.DURATION)
        self.assertEqual(te.hours, Decimal("2.50"))

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

    def test_month_counts_invalid_params(self):
        r = self.client.get(reverse("user-time-entry-month-counts"), {"year": 1999, "month": 4})
        self.assertEqual(r.status_code, 400)
