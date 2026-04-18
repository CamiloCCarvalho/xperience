from datetime import date
from typing import cast

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from app.avatar import handle_user_avatar_upload, user_avatar_url, workspace_avatar_url
from app.decorators import admin_active_workspace_required, platform_admin_required
from app.forms import (
    ClientCreateForm,
    CompensationHistoryForm,
    DepartmentForm,
    EmployeeProfileForm,
    JobHistoryForm,
    MemberAddForm,
    ProjectCreateForm,
    TaskCreateForm,
    TimeEntryTemplateForm,
    UserBirthDateForm,
    UserDepartmentAssignForm,
    WorkspaceUserDatesForm,
    WorkScheduleForm,
    WorkspaceCreateForm,
)
from app.models import (
    Client,
    CompensationHistory,
    Department,
    EmployeeProfile,
    JobHistory,
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
    uds_by_user: dict[int, list[UserDepartment]] = {}
    for ud in (
        UserDepartment.objects.filter(workspace=ws)
        .select_related("department")
        .order_by("-is_primary", "department__name")
    ):
        uds_by_user.setdefault(ud.user_id, []).append(ud)
    rows = []
    for m in (
        Membership.objects.filter(workspace=ws)
        .select_related("user")
        .order_by("user__email")
    ):
        user_departments = uds_by_user.get(m.user_id, [])
        rows.append(
            {
                "user": m.user,
                "department_links": user_departments,
                "department": user_departments[0].department if user_departments else None,
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
    user_department_form = UserDepartmentAssignForm(workspace=ws)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_template":
            template_form = TimeEntryTemplateForm(request.POST, workspace=ws)
            if template_form.is_valid():
                template_form.save()
                messages.success(request, "Template criado.")
                return redirect("admin-home")
        elif action == "update_template":
            template = TimeEntryTemplate.objects.filter(
                pk=request.POST.get("template_id"),
                workspace=ws,
            ).first()
            if template is None:
                messages.error(request, "Template inválido.")
                return redirect("admin-home")
            template_form = TimeEntryTemplateForm(request.POST, workspace=ws, instance=template)
            if template_form.is_valid():
                template_form.save()
                messages.success(request, "Template atualizado.")
                return redirect("admin-home")
        elif action == "delete_template":
            deleted, _ = TimeEntryTemplate.objects.filter(
                pk=request.POST.get("template_id"),
                workspace=ws,
            ).delete()
            messages.success(request, "Template removido.") if deleted else messages.error(
                request, "Template não encontrado."
            )
            return redirect("admin-home")
        elif action == "create_schedule":
            schedule_form = WorkScheduleForm(request.POST, workspace=ws)
            if schedule_form.is_valid():
                schedule_form.save()
                messages.success(request, "Expediente criado.")
                return redirect("admin-home")
        elif action == "update_schedule":
            schedule = WorkSchedule.objects.filter(
                pk=request.POST.get("schedule_id"),
                workspace=ws,
            ).first()
            if schedule is None:
                messages.error(request, "Expediente inválido.")
                return redirect("admin-home")
            schedule_form = WorkScheduleForm(request.POST, workspace=ws, instance=schedule)
            if schedule_form.is_valid():
                schedule_form.save()
                messages.success(request, "Expediente atualizado.")
                return redirect("admin-home")
        elif action == "delete_schedule":
            deleted, _ = WorkSchedule.objects.filter(
                pk=request.POST.get("schedule_id"),
                workspace=ws,
            ).delete()
            messages.success(request, "Expediente removido.") if deleted else messages.error(
                request, "Expediente não encontrado."
            )
            return redirect("admin-home")
        elif action == "create_department":
            department_form = DepartmentForm(request.POST, workspace=ws)
            if department_form.is_valid():
                department_form.save()
                messages.success(request, "Departamento criado.")
                return redirect("admin-home")
        elif action == "update_department":
            department = Department.objects.filter(
                pk=request.POST.get("department_id"),
                workspace=ws,
            ).first()
            if department is None:
                messages.error(request, "Departamento inválido.")
                return redirect("admin-home")
            department_form = DepartmentForm(request.POST, workspace=ws, instance=department)
            if department_form.is_valid():
                department_form.save()
                messages.success(request, "Departamento atualizado.")
                return redirect("admin-home")
        elif action == "delete_department":
            deleted, _ = Department.objects.filter(
                pk=request.POST.get("department_id"),
                workspace=ws,
            ).delete()
            messages.success(request, "Departamento removido.") if deleted else messages.error(
                request, "Departamento não encontrado."
            )
            return redirect("admin-home")
        elif action == "assign_user_department":
            try:
                uid = int(request.POST.get("user_id", ""))
            except (TypeError, ValueError):
                messages.error(request, "Dados inválidos.")
            else:
                user_obj = User.objects.filter(pk=uid).first()
                if user_obj and Membership.objects.filter(user=user_obj, workspace=ws).exists():
                    user_department_form = UserDepartmentAssignForm(
                        request.POST,
                        workspace=ws,
                    )
                    if user_department_form.is_valid():
                        user_department = user_department_form.save(commit=False)
                        user_department.user = user_obj
                        user_department.workspace = ws
                        new_start_date = user_department.start_date or date.today()
                        active_links = UserDepartment.objects.filter(
                            user=user_obj,
                            workspace=ws,
                            end_date__isnull=True,
                        )
                        same_department_active = active_links.filter(
                            department=user_department.department
                        ).first()
                        if same_department_active is not None:
                            messages.info(
                                request,
                                "Este membro já está ativo neste departamento.",
                            )
                            return redirect("admin-home")

                        try:
                            with transaction.atomic():
                                # Ao trocar de departamento, encerramos o vínculo ativo anterior.
                                for current in active_links:
                                    current.end_date = new_start_date
                                    if user_department.is_primary:
                                        current.is_primary = False
                                    current.save(update_fields=["end_date", "is_primary"])

                                if user_department.is_primary:
                                    UserDepartment.objects.filter(
                                        user=user_obj,
                                        workspace=ws,
                                        is_primary=True,
                                    ).update(is_primary=False)

                                user_department.save()
                        except IntegrityError:
                            messages.error(
                                request,
                                "Não foi possível salvar o vínculo. Execute as migrations "
                                "pendentes (`python manage.py migrate`) para habilitar "
                                "múltiplos departamentos por usuário.",
                            )
                        else:
                            messages.success(request, "Departamento vinculado ao membro.")
                else:
                    messages.error(
                        request,
                        "Não foi possível atribuir: verifique usuário e departamento.",
                    )
            return redirect("admin-home")
        elif action == "delete_user_department":
            deleted, _ = UserDepartment.objects.filter(
                pk=request.POST.get("user_department_id"),
                workspace=ws,
            ).delete()
            messages.success(request, "Vínculo de departamento removido.") if deleted else messages.error(
                request, "Vínculo de departamento não encontrado."
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
            "user_department_form": user_department_form,
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


def _can_view_compensation(request_user: User, target_user: User, ws: Workspace) -> bool:
    """Salário: admin/gestor do workspace ou o próprio colaborador."""
    if request_user.pk == target_user.pk:
        return True
    if ws.owner_id == request_user.pk:
        return True
    return Membership.objects.filter(
        user=request_user,
        workspace=ws,
        role__in=("admin", "manager"),
    ).exists()


def _upcoming_birthdays(ws: Workspace, days_ahead: int = 60):
    today = date.today()
    users = User.objects.filter(
        memberships__workspace=ws,
        birth_date__isnull=False,
    ).distinct()
    rows: list[dict[str, object]] = []
    for u in users:
        assert u.birth_date is not None
        try:
            next_bday = u.birth_date.replace(year=today.year)
        except ValueError:
            # Ajuste para 29/02 em ano não bissexto.
            next_bday = date(today.year, 3, 1)
        if next_bday < today:
            try:
                next_bday = next_bday.replace(year=today.year + 1)
            except ValueError:
                next_bday = date(today.year + 1, 3, 1)
        delta = (next_bday - today).days
        if delta <= days_ahead:
            rows.append(
                {
                    "user": u,
                    "birth_date": u.birth_date,
                    "next_birthday": next_bday,
                    "days_until": delta,
                }
            )
    rows.sort(key=lambda item: cast(int, item["days_until"]))
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
    user_dates_form = WorkspaceUserDatesForm(workspace=ws)
    profile_form = EmployeeProfileForm(workspace=ws)
    job_history_form = JobHistoryForm(workspace=ws)
    compensation_form = CompensationHistoryForm(workspace=ws)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_workspace_budget":
            budget_raw = (request.POST.get("budget_total") or "").strip()
            ws.budget_total = budget_raw or None
            ws.updated_by = request.user
            ws.save(update_fields=["budget_total", "updated_by"])
            messages.success(request, "Budget do workspace atualizado.")
            return redirect("admin-config")
        if action == "update_user_dates":
            user_dates_form = WorkspaceUserDatesForm(request.POST, workspace=ws)
            if user_dates_form.is_valid():
                target_user = user_dates_form.cleaned_data["user"]
                target_user.birth_date = user_dates_form.cleaned_data["birth_date"]
                target_user.platform_join_date = user_dates_form.cleaned_data["platform_join_date"]
                target_user.save(update_fields=["birth_date", "platform_join_date"])
                messages.success(request, "Dados globais do colaborador atualizados.")
                return redirect("admin-config")
        elif action == "upsert_employee_profile":
            profile_form = EmployeeProfileForm(request.POST, workspace=ws)
            if profile_form.is_valid():
                candidate = profile_form.save(commit=False)
                existing = EmployeeProfile.objects.filter(
                    workspace=ws,
                    user=candidate.user,
                ).first()
                if existing is not None:
                    existing.employment_status = candidate.employment_status
                    existing.hire_date = candidate.hire_date
                    existing.termination_date = candidate.termination_date
                    existing.current_job_title = candidate.current_job_title
                    existing.save()
                    messages.success(request, "Vínculo empregatício atualizado.")
                else:
                    candidate.workspace = ws
                    candidate.save()
                    messages.success(request, "Vínculo empregatício criado.")
                return redirect("admin-config")
        elif action == "create_job_history":
            job_history_form = JobHistoryForm(request.POST, workspace=ws)
            if job_history_form.is_valid():
                job_history_form.save()
                messages.success(request, "Histórico de cargo cadastrado.")
                return redirect("admin-config")
        elif action == "create_compensation_history":
            compensation_form = CompensationHistoryForm(request.POST, workspace=ws)
            if compensation_form.is_valid():
                compensation_form.save()
                messages.success(request, "Histórico de remuneração cadastrado.")
                return redirect("admin-config")
        if action == "create_client":
            client_form = ClientCreateForm(request.POST)
            if client_form.is_valid():
                client_form.save(workspace=ws, created_by=request.user, updated_by=request.user)
                messages.success(request, "Cliente criado.")
                return redirect("admin-config")
        elif action == "update_client":
            client = Client.objects.filter(pk=request.POST.get("client_id"), workspace=ws).first()
            if client is None:
                messages.error(request, "Cliente inválido.")
                return redirect("admin-config")
            client_form = ClientCreateForm(request.POST, instance=client)
            if client_form.is_valid():
                client_form.save(workspace=ws, updated_by=request.user)
                messages.success(request, "Cliente atualizado.")
                return redirect("admin-config")
        elif action == "delete_client":
            deleted, _ = Client.objects.filter(pk=request.POST.get("client_id"), workspace=ws).delete()
            messages.success(request, "Cliente removido.") if deleted else messages.error(
                request, "Cliente não encontrado."
            )
            return redirect("admin-config")
        elif action == "create_project":
            project_form = ProjectCreateForm(request.POST, workspace=ws)
            if project_form.is_valid():
                project_form.save(workspace=ws, created_by=request.user, updated_by=request.user)
                messages.success(request, "Projeto criado.")
                return redirect("admin-config")
        elif action == "update_project":
            project = Project.objects.filter(pk=request.POST.get("project_id"), workspace=ws).first()
            if project is None:
                messages.error(request, "Projeto inválido.")
                return redirect("admin-config")
            project_form = ProjectCreateForm(request.POST, workspace=ws, instance=project)
            if project_form.is_valid():
                project_form.save(workspace=ws, updated_by=request.user)
                messages.success(request, "Projeto atualizado.")
                return redirect("admin-config")
        elif action == "delete_project":
            deleted, _ = Project.objects.filter(pk=request.POST.get("project_id"), workspace=ws).delete()
            messages.success(request, "Projeto removido.") if deleted else messages.error(
                request, "Projeto não encontrado."
            )
            return redirect("admin-config")
        elif action == "create_task":
            task_form = TaskCreateForm(request.POST, workspace=ws)
            if task_form.is_valid():
                task_form.save()
                messages.success(request, "Tarefa criada.")
                return redirect("admin-config")
        elif action == "update_task":
            task = Task.objects.filter(pk=request.POST.get("task_id"), project__workspace=ws).first()
            if task is None:
                messages.error(request, "Tarefa inválida.")
                return redirect("admin-config")
            task_form = TaskCreateForm(request.POST, workspace=ws, instance=task)
            if task_form.is_valid():
                task_form.save()
                messages.success(request, "Tarefa atualizada.")
                return redirect("admin-config")
        elif action == "delete_task":
            deleted, _ = Task.objects.filter(pk=request.POST.get("task_id"), project__workspace=ws).delete()
            messages.success(request, "Tarefa removida.") if deleted else messages.error(
                request, "Tarefa não encontrada."
            )
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
    employee_profiles = (
        EmployeeProfile.objects.filter(workspace=ws)
        .select_related("user")
        .order_by("user__email")
    )
    latest_job_by_profile = {
        item.employee_profile_id: item
        for item in JobHistory.objects.filter(
            employee_profile__workspace=ws,
            end_date__isnull=True,
        ).select_related("employee_profile")
    }
    compensation_history = (
        CompensationHistory.objects.filter(employee_profile__workspace=ws)
        .select_related("employee_profile", "employee_profile__user")
        .order_by("employee_profile__user__email", "-start_date")
    )
    compensation_history_visible = [
        ch
        for ch in compensation_history
        if _can_view_compensation(request.user, ch.employee_profile.user, ws)
    ]
    birthdays_preview = _upcoming_birthdays(ws)

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
            "employee_profiles": employee_profiles,
            "latest_job_by_profile": latest_job_by_profile,
            "compensation_history": compensation_history_visible,
            "user_dates_form": user_dates_form,
            "employee_profile_form": profile_form,
            "job_history_form": job_history_form,
            "compensation_history_form": compensation_form,
            "birthdays_preview": birthdays_preview,
        }
    )
    return render(request, page_admin + "configuration.html", context=ctx)


@platform_admin_required
@admin_active_workspace_required
def admin_account(request):
    user = request.user
    assert isinstance(user, User)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_avatar":
            handle_user_avatar_upload(request, user)
            return redirect("admin-account")
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
