import calendar
from datetime import date
from typing import Optional

from django.contrib import messages
from django.shortcuts import redirect, render

from app.avatar import user_avatar_url, workspace_avatar_url
from app.decorators import member_active_workspace_required, platform_member_required
from app.models import User, UserDepartment, Workspace
from app.workspace_session import (
    member_workspaces_queryset,
    resolve_member_workspace,
    set_member_workspace,
)

page_user = "xperience/pages/user/"

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
            #messages.success(
            #    request,
            #    f"Acessando o workspace «{chosen.workspace_name}».",
            #)
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
    ws = ctx.get("active_member_workspace")
    ctx["entry_form"] = _entry_form_visibility(request.user, ws)
    today = date.today()
    ctx.update(_calendar_month_context(today.year, today.month))
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
    return render(
        request,
        page_user + "account.html",
        context=_member_area_context(request),
    )
