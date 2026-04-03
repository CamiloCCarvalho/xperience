from django.contrib import messages
from django.shortcuts import redirect, render

from app.avatar import user_avatar_url, workspace_avatar_url
from app.decorators import admin_active_workspace_required, platform_admin_required
from app.forms import (
    DepartmentForm,
    MemberAddForm,
    TimeEntryTemplateForm,
    WorkScheduleForm,
    WorkspaceCreateForm,
)
from app.models import (
    Department,
    Membership,
    TimeEntryTemplate,
    User,
    UserDepartment,
    WorkSchedule,
    Workspace,
)
from app.workspace_session import (
    attach_admin_workspace_to_request,
    set_admin_workspace,
)

page_admin = "xperience/pages/admin/"


def _admin_context(request):
    user = request.user
    assert isinstance(user, User)
    attach_admin_workspace_to_request(request, user)
    return {
        "user_avatar_url": user_avatar_url(user),
        "active_admin_workspace": request.active_admin_workspace,
    }


@platform_admin_required
def admin_workspaces(request):
    user = request.user
    assert isinstance(user, User)
    workspaces = list(Workspace.objects.filter(owner=user))
    for w in workspaces:
        w.display_avatar_url = workspace_avatar_url(w)

    if request.method == "POST":
        try:
            ws_id = int(request.POST.get("workspace_id", ""))
        except (TypeError, ValueError):
            ws_id = 0
        chosen = Workspace.objects.filter(pk=ws_id, owner=user).first()
        if chosen is not None:
            set_admin_workspace(request, chosen.pk)
            messages.success(
                request,
                f"Workspace ativo na gestão: «{chosen.workspace_name}».",
            )
            return redirect("admin-home")
        messages.error(request, "Workspace inválido ou não pertence à sua conta.")

    ctx = _admin_context(request)
    ctx["workspaces"] = workspaces
    ctx["workspace_count"] = len(workspaces)
    return render(request, page_admin + "workspaces.html", context=ctx)


def _admin_home_member_rows(ws: Workspace):
    uds = {
        ud.user_id: ud
        for ud in UserDepartment.objects.filter(workspace=ws).select_related("department")
    }
    rows = []
    for m in (
        Membership.objects.filter(workspace=ws)
        .select_related("user")
        .order_by("user__email")
    ):
        ud = uds.get(m.user_id)
        rows.append(
            {
                "user": m.user,
                "department": ud.department if ud else None,
            }
        )
    return rows


@platform_admin_required
@admin_active_workspace_required
def admin_home(request):
    ws = getattr(request, "active_admin_workspace", None)
    ctx = _admin_context(request)
    if ws is None:
        return render(request, page_admin + "home.html", context=ctx)

    template_form = TimeEntryTemplateForm(workspace=ws)
    schedule_form = WorkScheduleForm(workspace=ws)
    department_form = DepartmentForm(workspace=ws)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_template":
            template_form = TimeEntryTemplateForm(request.POST, workspace=ws)
            if template_form.is_valid():
                template_form.save()
                messages.success(request, "Template criado.")
                return redirect("admin-home")
        elif action == "create_schedule":
            schedule_form = WorkScheduleForm(request.POST, workspace=ws)
            if schedule_form.is_valid():
                schedule_form.save()
                messages.success(request, "Expediente criado.")
                return redirect("admin-home")
        elif action == "create_department":
            department_form = DepartmentForm(request.POST, workspace=ws)
            if department_form.is_valid():
                department_form.save()
                messages.success(request, "Departamento criado.")
                return redirect("admin-home")
        elif action == "assign_user_department":
            try:
                uid = int(request.POST.get("user_id", ""))
                did = int(request.POST.get("department_id", ""))
            except (TypeError, ValueError):
                messages.error(request, "Dados inválidos.")
            else:
                user_obj = User.objects.filter(pk=uid).first()
                dept = Department.objects.filter(pk=did, workspace=ws).first()
                if (
                    user_obj
                    and dept
                    and Membership.objects.filter(user=user_obj, workspace=ws).exists()
                ):
                    UserDepartment.objects.update_or_create(
                        user=user_obj,
                        workspace=ws,
                        defaults={"department": dept},
                    )
                    messages.success(request, "Departamento do membro atualizado.")
                else:
                    messages.error(
                        request,
                        "Não foi possível atribuir: verifique usuário e departamento.",
                    )
            return redirect("admin-home")

    departments = list(
        Department.objects.filter(workspace=ws)
        .select_related("schedule", "template")
        .order_by("name")
    )
    ctx.update(
        {
            "time_templates": TimeEntryTemplate.objects.filter(workspace=ws).order_by("name"),
            "work_schedules": WorkSchedule.objects.filter(workspace=ws).order_by("name"),
            "departments": departments,
            "member_rows": _admin_home_member_rows(ws),
            "template_form": template_form,
            "schedule_form": schedule_form,
            "department_form": department_form,
        }
    )
    return render(request, page_admin + "home.html", context=ctx)


@platform_admin_required
@admin_active_workspace_required
def admin_dashboard(request):
    return render(
        request,
        page_admin + "dashboard.html",
        context=_admin_context(request),
    )


@platform_admin_required
@admin_active_workspace_required
def admin_config(request):
    return render(
        request,
        page_admin + "configuration.html",
        context=_admin_context(request),
    )


@platform_admin_required
@admin_active_workspace_required
def admin_account(request):
    return render(
        request,
        page_admin + "account.html",
        context=_admin_context(request),
    )


@platform_admin_required
def admin_workspaces_create(request):
    if request.method == "POST":
        form = WorkspaceCreateForm(request.POST)
        if form.is_valid():
            ws = form.save(commit=False)
            ws.owner = request.user
            ws.save()
            messages.success(request, "Workspace criado com sucesso.")
            return redirect("admin-workspaces")
    else:
        form = WorkspaceCreateForm()
    return render(
        request,
        page_admin + "workspaces_create.html",
        context={
            **_admin_context(request),
            "form": form,
        },
    )


@platform_admin_required
def admin_members_add(request):
    owner = request.user
    assert isinstance(owner, User)
    if request.method == "POST":
        form = MemberAddForm(request.POST, owner=owner)
        if form.is_valid():
            form.save()
            messages.success(request, "Membro vinculado ao workspace com sucesso.")
            return redirect("admin-members-add")
    else:
        form = MemberAddForm(owner=owner)
    return render(
        request,
        page_admin + "members_add.html",
        context={
            **_admin_context(request),
            "form": form,
        },
    )
