import calendar
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from app.avatar import handle_user_avatar_upload, user_avatar_url, workspace_avatar_url
from app.decorators import member_active_workspace_required, platform_member_required
from app.forms import UserBirthDateForm
from app.models import (
    Client,
    CompensationHistory,
    EmployeeProfile,
    JobHistory,
    Project,
    Task,
    TimeEntry,
    User,
    UserClient,
    UserDepartment,
    UserProject,
    Workspace,
)
from app.workspace_session import (
    member_workspaces_queryset,
    resolve_member_workspace,
    set_member_workspace,
)

page_user = "xperience/pages/user/"

_HISTORY_LIST_LIMIT = 200

_MONTH_NAMES_PT = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


def _calendar_month_context(year: int, month: int) -> dict[str, object]:
    """Grade do mês com semanas começando no domingo (Dom–Sáb)."""
    cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
    weeks = cal.monthdayscalendar(year, month)
    calendar_days: list[list[Optional[int]]] = [
        [None if d == 0 else d for d in week] for week in weeks
    ]
    return {
        "current_year": year,
        "current_month": month,
        "calendar_days": calendar_days,
        "calendar_heading": f"{_MONTH_NAMES_PT[month - 1]} {year}",
    }


def _history_filter_context(today: date) -> dict[str, object]:
    """Opções estáticas para os filtros de data na home (GET na mesma página)."""
    months = [(m, _MONTH_NAMES_PT[m - 1]) for m in range(1, 13)]
    return {
        "history_filter_years": list(range(today.year - 5, today.year + 2)),
        "history_filter_months": months,
        "history_filter_days": list(range(1, 32)),
    }


def _parse_optional_positive_int(raw: str | None) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        v = int(str(raw).strip())
    except ValueError:
        return None
    if v <= 0:
        return None
    return v


def _parse_int_between(raw: str | None, lo: int, hi: int) -> int | None:
    v = _parse_optional_positive_int(raw)
    if v is None:
        return None
    if v < lo or v > hi:
        return None
    return v


def _normalize_history_overtime_param(raw: str | None) -> str:
    s = (raw or "").strip()
    return s if s in ("", "0", "1") else ""


def _history_table_colspan(entry_form: dict[str, Any]) -> int:
    n = 1  # data
    if entry_form.get("use_client"):
        n += 1
    if entry_form.get("use_project"):
        n += 1
    if entry_form.get("use_task"):
        n += 1
    if entry_form.get("use_description"):
        n += 1
    if entry_form.get("use_type"):
        n += 1
    n += 5  # modo, início, fim, horas, hora extra
    return n


def _time_entry_hours_label(entry: TimeEntry) -> str:
    if entry.hours is not None:
        return f"{entry.hours.normalize()} h"
    if entry.duration_minutes:
        h = (Decimal(entry.duration_minutes) / Decimal(60)).quantize(Decimal("0.01"))
        return f"{h} h"
    return "—"


def _apply_history_date_filters(
    qs,
    y: int | None,
    mo: int | None,
    d: int | None,
):
    """
    Restringe queryset por ano/mês/dia conforme combinações usuais nos filtros GET.
    Usa o ano civil atual quando mês+dia forem informados sem ano (comportamento previsível).
    """
    today = timezone.localdate()

    # Mês + dia sem ano → assume o ano atual (ex.: ver todos os apontamentos do dia 15 de março do ano corrente)
    if y is None and mo is not None and d is not None:
        y = today.year

    # Só mês (sem ano, sem dia) → mês no ano atual
    if y is None and mo is not None and d is None:
        return qs.filter(date__year=today.year, date__month=mo)

    # Ano + dia do mês sem mês → todos os dias "d" em qualquer mês daquele ano (ex.: todo dia 10)
    if y is not None and mo is None and d is not None:
        return qs.filter(date__year=y, date__day=d)

    # Apenas dia (sem ano e sem mês) → dia no mês/ano atuais, se existir no calendário
    if y is None and mo is None and d is not None:
        try:
            return qs.filter(date=date(today.year, today.month, d))
        except ValueError:
            return qs.none()

    if y is not None and mo is not None and d is not None:
        try:
            return qs.filter(date=date(y, mo, d))
        except ValueError:
            return qs.filter(date__year=y, date__month=mo)

    if y is not None and mo is not None:
        return qs.filter(date__year=y, date__month=mo)

    if y is not None:
        return qs.filter(date__year=y)

    return qs


def _member_history_entries(
    request,
    user: User,
    ws: Workspace,
    entry_form: dict[str, Any],
) -> tuple[list[TimeEntry], dict[str, Any]]:
    """
    Apontamentos salvos do membro no workspace, com filtros via querystring.
    Retorna (lista limitada, metadados para o template).
    """
    get = request.GET

    def _g(*keys: str) -> str | None:
        for key in keys:
            v = get.get(key)
            if v is not None and str(v).strip() != "":
                return str(v).strip()
        return None

    client_ids = set(
        UserClient.objects.filter(user=user, workspace=ws).values_list("client_id", flat=True)
    )
    project_ids = set(
        UserProject.objects.filter(user=user, workspace=ws).values_list("project_id", flat=True)
    )
    task_ids_allowed = set(
        Task.objects.filter(project_id__in=project_ids, is_active=True).values_list("pk", flat=True)
    )

    selection: dict[str, Any] = {
        "year": _parse_int_between(_g("hf_year", "year"), 2000, 2100),
        "month": _parse_int_between(_g("hf_month", "month"), 1, 12),
        "day": _parse_int_between(_g("hf_day", "day"), 1, 31),
        "overtime_param": _normalize_history_overtime_param(
            _g("hf_overtime", "is_overtime")
        ),
        "client_id": None,
        "project_id": None,
        "task_id": None,
        "entry_type": "",
        "description_query": "",
    }

    if entry_form.get("use_client"):
        cid = _parse_optional_positive_int(_g("hf_client_id", "client_id"))
        if cid is not None and cid in client_ids:
            selection["client_id"] = cid
    if entry_form.get("use_project"):
        pid = _parse_optional_positive_int(_g("hf_project_id", "project_id"))
        if pid is not None and pid in project_ids:
            selection["project_id"] = pid
    if entry_form.get("use_task"):
        tid = _parse_optional_positive_int(_g("hf_task_id", "task_id"))
        if tid is not None and tid in task_ids_allowed:
            selection["task_id"] = tid
    if entry_form.get("use_type"):
        et = (_g("hf_entry_type", "entry_type") or "").strip()
        if et in (TimeEntry.EntryType.INTERNAL, TimeEntry.EntryType.EXTERNAL):
            selection["entry_type"] = et
    if entry_form.get("use_description"):
        desc = (_g("hf_description", "description_contains") or "").strip()
        if desc:
            selection["description_query"] = desc[:200]

    qs = (
        TimeEntry.objects.saved_only()
        .filter(user=user, workspace=ws)
        .select_related("client", "project", "project__client", "task", "task__project", "department")
        .order_by("-date", "-pk")
    )

    qs = _apply_history_date_filters(qs, selection["year"], selection["month"], selection["day"])

    otp = selection["overtime_param"]
    if otp == "1":
        qs = qs.filter(is_overtime=True)
    elif otp == "0":
        qs = qs.filter(is_overtime=False)

    if selection["client_id"] is not None:
        qs = qs.filter(client_id=selection["client_id"])
    if selection["project_id"] is not None:
        qs = qs.filter(project_id=selection["project_id"])
    if selection["task_id"] is not None:
        qs = qs.filter(task_id=selection["task_id"])
    if selection["entry_type"]:
        qs = qs.filter(entry_type=selection["entry_type"])
    if selection["description_query"]:
        qs = qs.filter(description__icontains=selection["description_query"])

    entries = list(qs[:_HISTORY_LIST_LIMIT])
    for e in entries:
        setattr(e, "history_hours_label", _time_entry_hours_label(e))

    meta = {
        "selection": selection,
        "table_colspan": _history_table_colspan(entry_form),
        "total_capped": len(entries) >= _HISTORY_LIST_LIMIT,
        "list_limit": _HISTORY_LIST_LIMIT,
    }
    return entries, meta


def _annotate_member_workspaces(workspaces: list[Workspace]) -> None:
    for w in workspaces:
        w.display_avatar_url = workspace_avatar_url(w)
        owner = w.owner
        name = (owner.get_full_name() or owner.first_name or "").strip()
        w.owner_display = f"{name + ' · ' if name else ''}{owner.email}"


def _member_workspaces_list(user: User) -> list[Workspace]:
    workspaces = list(member_workspaces_queryset(user))
    _annotate_member_workspaces(workspaces)
    return workspaces


def _user_context(request):
    user = request.user
    assert isinstance(user, User)
    return {
        "user_avatar_url": user_avatar_url(user),
    }


def _member_area_context(request):
    ctx = _user_context(request)
    ws = getattr(request, "active_member_workspace", None)
    if ws is not None:
        ctx["active_member_workspace"] = ws
    return ctx


def _entry_form_visibility(user: User, ws: Optional[Workspace]) -> dict[str, object]:
    """
    Campos do formulário de apontamento conforme TimeEntryTemplate do departamento
    atribuído pelo gestor neste workspace.
    """
    base: dict[str, object] = {
        "use_client": False,
        "use_project": False,
        "use_task": False,
        "use_type": False,
        "use_description": False,
        "template_name": None,
        "department_name": None,
        "configured": False,
    }
    if ws is None:
        return base
    ud = (
        UserDepartment.objects.filter(user=user, workspace=ws)
        .order_by("end_date", "-is_primary", "pk")
        .select_related("department", "department__template")
        .first()
    )
    if ud is None:
        return base
    base["department_name"] = ud.department.name
    tpl = ud.department.template
    if tpl is None:
        return base
    base.update(
        {
            "use_client": tpl.use_client,
            "use_project": tpl.use_project,
            "use_task": tpl.use_task,
            "use_type": tpl.use_type,
            "use_description": tpl.use_description,
            "template_name": tpl.name,
            "configured": True,
        }
    )
    return base


def _entry_access_querysets(user: User, ws: Workspace) -> dict[str, object]:
    """
    Clientes / projetos / tarefas que o membro pode usar nos apontamentos
    (UserClient / UserProject no workspace ativo).
    """
    client_ids = UserClient.objects.filter(user=user, workspace=ws).values_list(
        "client_id", flat=True
    )
    project_ids = UserProject.objects.filter(user=user, workspace=ws).values_list(
        "project_id", flat=True
    )
    clients = (
        Client.objects.filter(pk__in=client_ids, workspace=ws, is_active=True)
        .order_by("name")
    )
    projects = (
        Project.objects.filter(pk__in=project_ids, workspace=ws, is_active=True)
        .select_related("client")
        .order_by("client__name", "name")
    )
    tasks = (
        Task.objects.filter(
            project_id__in=project_ids,
            is_active=True,
        )
        .select_related("project", "project__client")
        .order_by("project__name", "name")
    )
    return {
        "entry_clients": clients,
        "entry_projects": projects,
        "entry_tasks": tasks,
    }


@platform_member_required
def user_workspaces(request):
    user = request.user
    assert isinstance(user, User)
    workspaces = _member_workspaces_list(user)

    if request.method == "POST":
        try:
            ws_id = int(request.POST.get("workspace_id", ""))
        except (TypeError, ValueError):
            ws_id = 0
        chosen = Workspace.objects.filter(pk=ws_id, memberships__user=user).first()
        if chosen is not None:
            set_member_workspace(request, chosen.pk)
            messages.success(
                request,
                f"Acessando o workspace «{chosen.workspace_name}».",
            )
            return redirect("user-home")
        messages.error(request, "Workspace inválido ou sem permissão.")

    active = resolve_member_workspace(request, user)
    return render(
        request,
        page_user + "workspaces.html",
        context={
            **_user_context(request),
            "workspaces": workspaces,
            "workspace_count": len(workspaces),
            "active_member_workspace": active,
        },
    )


@platform_member_required
@member_active_workspace_required
def user_home(request):
    ctx = _member_area_context(request)
    ws = ctx["active_member_workspace"]
    ctx["entry_form"] = _entry_form_visibility(request.user, ws)
    ctx.update(_entry_access_querysets(request.user, ws))
    history_entries, history_meta = _member_history_entries(
        request, request.user, ws, ctx["entry_form"]
    )
    ctx["history_entries"] = history_entries
    ctx["history_selection"] = history_meta["selection"]
    ctx["history_table_colspan"] = history_meta["table_colspan"]
    ctx["history_list_limited"] = history_meta["total_capped"]
    ctx["history_list_limit"] = history_meta["list_limit"]
    # Calendário na home é montado no cliente (mês conforme relógio local do navegador).
    today = date.today()
    ctx.update(_calendar_month_context(today.year, today.month))
    ctx.update(_history_filter_context(today))
    return render(request, page_user + "home.html", context=ctx)


@platform_member_required
@member_active_workspace_required
def user_dashboard(request):
    return render(
        request,
        page_user + "dashboard.html",
        context=_member_area_context(request),
    )


@platform_member_required
@member_active_workspace_required
def user_config(request):
    return render(
        request,
        page_user + "configuration.html",
        context=_member_area_context(request),
    )


@platform_member_required
@member_active_workspace_required
def user_account(request):
    ctx = _member_area_context(request)
    ws = ctx.get("active_member_workspace")
    user = request.user
    assert isinstance(user, User)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_avatar":
            handle_user_avatar_upload(request, user)
            return redirect("user-account")
        elif action == "update_birth_date":
            birth_form = UserBirthDateForm(request.POST, instance=user)
            if birth_form.is_valid():
                birth_form.save()
                messages.success(request, "Data de nascimento atualizada.")
                return redirect("user-account")
        else:
            birth_form = UserBirthDateForm(instance=user)
    else:
        birth_form = UserBirthDateForm(instance=user)

    employee_profile = None
    current_job = None
    compensation_history = CompensationHistory.objects.none()
    if ws is not None:
        employee_profile = EmployeeProfile.objects.filter(
            user=user,
            workspace=ws,
        ).first()
        if employee_profile is not None:
            current_job = JobHistory.objects.filter(
                employee_profile=employee_profile,
                end_date__isnull=True,
            ).order_by("-start_date", "-pk").first()
            compensation_history = CompensationHistory.objects.filter(
                employee_profile=employee_profile
            ).order_by("-start_date", "-pk")

    ctx.update(
        {
            "birth_form": birth_form,
            "employee_profile": employee_profile,
            "current_job": current_job,
            "compensation_history": compensation_history,
        }
    )

    return render(request, page_user + "account.html", context=ctx)
