from django.contrib import messages
from django.shortcuts import redirect, render

from app.avatar import user_avatar_url, workspace_avatar_url
from app.decorators import admin_active_workspace_required, platform_admin_required
from app.forms import (
    ClientCreateForm,
    DepartmentForm,
    MemberAddForm,
    ProjectCreateForm,
    TaskCreateForm,
    TimeEntryTemplateForm,
    WorkScheduleForm,
    WorkspaceCreateForm,
)
from app.models import (
    Client,
    Department,
    Membership,
    Project,
    Task,
    TimeEntryTemplate,
    User,
    UserClient,
    UserDepartment,
    UserProject,
    WorkSchedule,
    Workspace,
)
from app.workspace_session import (
    attach_admin_workspace_to_request,
    clear_admin_workspace,
    get_admin_workspace_id,
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
        action = (request.POST.get("action") or "").strip()

        if action == "delete_workspace":
            try:
                del_id = int(request.POST.get("workspace_id", ""))
            except (TypeError, ValueError):
                del_id = 0
            to_delete = Workspace.objects.filter(pk=del_id, owner=user).first()
            if to_delete is None:
                messages.error(
                    request,
                    "Não foi possível excluir: workspace inválido ou não pertence à sua conta.",
                )
            else:
                name = to_delete.workspace_name
                if get_admin_workspace_id(request) == to_delete.pk:
                    clear_admin_workspace(request)
                to_delete.delete()
                messages.success(
                    request,
                    f"Workspace «{name}» excluído. Membros, clientes, projetos e apontamentos "
                    "deste workspace foram removidos; contas de usuário em outros workspaces "
                    "permanecem intactas.",
                )
            return redirect("admin-workspaces")

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


def _user_in_workspace_admin_context(user: User, ws: Workspace) -> bool:
    if ws.owner_id == user.pk:
        return True
    return Membership.objects.filter(user=user, workspace=ws).exists()


def _admin_config_member_rows(ws: Workspace):
    uds = {
        ud.user_id: ud
        for ud in UserDepartment.objects.filter(workspace=ws).select_related("department")
    }
    seen: set[int] = set()
    users_ordered: list[User] = []
    for m in (
        Membership.objects.filter(workspace=ws)
        .select_related("user")
        .order_by("user__email")
    ):
        u = m.user
        if u.pk in seen:
            continue
        seen.add(u.pk)
        users_ordered.append(u)
    if ws.owner_id and ws.owner_id not in seen:
        owner = User.objects.filter(pk=ws.owner_id).first()
        if owner is not None:
            users_ordered.append(owner)
            seen.add(owner.pk)
    users_ordered.sort(key=lambda u: u.email.lower())

    rows = []
    for u in users_ordered:
        m = Membership.objects.filter(user=u, workspace=ws).first() # type: ignore
        ud = uds.get(u.pk)
        client_links = list(
            UserClient.objects.filter(user=u, workspace=ws).select_related("client").order_by("client__name")
        )
        project_links = list(
            UserProject.objects.filter(user=u, workspace=ws)
            .select_related("project", "project__client")
            .order_by("project__name")
        )
        rows.append(
            {
                "membership": m,
                "user": u,
                "department": ud.department if ud else None,
                "client_links": client_links,
                "project_links": project_links,
            }
        )
    return rows


@platform_admin_required
@admin_active_workspace_required
def admin_config(request):
    ws = getattr(request, "active_admin_workspace", None)
    ctx = _admin_context(request)
    if ws is None:
        return render(request, page_admin + "configuration.html", context=ctx)

    client_form = ClientCreateForm()
    project_form = ProjectCreateForm(workspace=ws)
    task_form = TaskCreateForm(workspace=ws)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_client":
            client_form = ClientCreateForm(request.POST)
            if client_form.is_valid():
                client_form.save(workspace=ws, created_by=request.user)
                messages.success(request, "Cliente criado.")
                return redirect("admin-config")
        elif action == "create_project":
            project_form = ProjectCreateForm(request.POST, workspace=ws)
            if project_form.is_valid():
                project_form.save(workspace=ws, created_by=request.user)
                messages.success(request, "Projeto criado.")
                return redirect("admin-config")
        elif action == "create_task":
            task_form = TaskCreateForm(request.POST, workspace=ws)
            if task_form.is_valid():
                task_form.save()
                messages.success(request, "Tarefa criada.")
                return redirect("admin-config")
        elif action == "link_user_client":
            try:
                uid = int(request.POST.get("user_id", ""))
                cid = int(request.POST.get("client_id", ""))
            except (TypeError, ValueError):
                messages.error(request, "Dados inválidos para vínculo com cliente.")
            else:
                user_obj = User.objects.filter(pk=uid).first()
                client_obj = Client.objects.filter(pk=cid, workspace=ws).first()
                if user_obj and client_obj and _user_in_workspace_admin_context(user_obj, ws):
                    UserClient.objects.get_or_create(
                        user=user_obj, client=client_obj, workspace=ws
                    )
                    messages.success(request, "Cliente vinculado ao membro.")
                else:
                    messages.error(request, "Não foi possível vincular o cliente.")
            return redirect("admin-config")
        elif action == "unlink_user_client":
            try:
                ucid = int(request.POST.get("uc_id", ""))
            except (TypeError, ValueError):
                messages.error(request, "Vínculo inválido.")
            else:
                deleted, _ = UserClient.objects.filter(pk=ucid, workspace=ws).delete()
                if deleted:
                    messages.success(request, "Vínculo com cliente removido.")
                else:
                    messages.error(request, "Vínculo não encontrado.")
            return redirect("admin-config")
        elif action == "link_user_project":
            try:
                uid = int(request.POST.get("user_id", ""))
                pid = int(request.POST.get("project_id", ""))
            except (TypeError, ValueError):
                messages.error(request, "Dados inválidos para vínculo com projeto.")
            else:
                user_obj = User.objects.filter(pk=uid).first()
                project_obj = Project.objects.filter(pk=pid, workspace=ws).first()
                if user_obj and project_obj and _user_in_workspace_admin_context(user_obj, ws):
                    UserProject.objects.get_or_create(
                        user=user_obj, project=project_obj, workspace=ws
                    )
                    messages.success(request, "Projeto vinculado ao membro.")
                else:
                    messages.error(request, "Não foi possível vincular o projeto.")
            return redirect("admin-config")
        elif action == "unlink_user_project":
            try:
                upid = int(request.POST.get("up_id", ""))
            except (TypeError, ValueError):
                messages.error(request, "Vínculo inválido.")
            else:
                deleted, _ = UserProject.objects.filter(pk=upid, workspace=ws).delete()
                if deleted:
                    messages.success(request, "Vínculo com projeto removido.")
                else:
                    messages.error(request, "Vínculo não encontrado.")
            return redirect("admin-config")

    clients = Client.objects.filter(workspace=ws).order_by("name")
    projects = Project.objects.filter(workspace=ws).select_related("client").order_by("name")
    tasks = (
        Task.objects.filter(project__workspace=ws)
        .select_related("project", "project__client")
        .order_by("project__name", "name")
    )
    active_clients = Client.objects.filter(workspace=ws, is_active=True).order_by("name")
    active_projects = (
        Project.objects.filter(workspace=ws, is_active=True)
        .select_related("client")
        .order_by("name")
    )
    member_rows = _admin_config_member_rows(ws)

    ctx.update(
        {
            "config_workspace": ws,
            "client_form": client_form,
            "project_form": project_form,
            "task_form": task_form,
            "clients": clients,
            "projects": projects,
            "tasks": tasks,
            "active_clients": active_clients,
            "active_projects": active_projects,
            "member_rows": member_rows,
            "member_count": len(member_rows),
            "client_count": clients.count(),
            "project_count": projects.count(),
            "task_count": tasks.count(),
        }
    )
    return render(request, page_admin + "configuration.html", context=ctx)


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
