"""Workspace ativo na sessão: membros (vários gestores) e gestores (vários próprios workspaces)."""

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect

from app.models import User, Workspace

SESSION_MEMBER_WORKSPACE_KEY = "member_active_workspace_id"
SESSION_ADMIN_WORKSPACE_KEY = "admin_active_workspace_id"


def clear_member_workspace(request: HttpRequest) -> None:
    request.session.pop(SESSION_MEMBER_WORKSPACE_KEY, None)


def set_member_workspace(request: HttpRequest, workspace_id: int) -> None:
    request.session[SESSION_MEMBER_WORKSPACE_KEY] = int(workspace_id)
    request.session.modified = True


def get_member_workspace_id(request: HttpRequest) -> int | None:
    raw = request.session.get(SESSION_MEMBER_WORKSPACE_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def member_workspaces_queryset(user: User):
    return (
        Workspace.objects.filter(memberships__user=user)
        .distinct()
        .select_related("owner")
        .order_by("workspace_name", "pk")
    )


def resolve_member_workspace(request: HttpRequest, user: User) -> Workspace | None:
    ws_id = get_member_workspace_id(request)
    if ws_id is None:
        return None
    return member_workspaces_queryset(user).filter(pk=ws_id).first()


def member_redirect_after_login(request: HttpRequest, user: User):
    """
    Membro sem workspace → tela vazia.
    Um workspace → define sessão e vai direto ao app.
    Vários → obriga escolher na lista (sessão antiga inválida é limpa).
    """
    workspaces = list(member_workspaces_queryset(user))
    n = len(workspaces)
    if n == 0:
        clear_member_workspace(request)
        return redirect("user-workspaces")
    if n == 1:
        set_member_workspace(request, workspaces[0].pk)
        return redirect("user-home")
    clear_member_workspace(request)
    messages.info(
        request,
        "Você tem acesso a mais de um workspace. Escolha qual deseja acessar agora.",
    )
    return redirect("user-workspaces")


# --- Gestor (dono dos workspaces) -------------------------------------------


def clear_admin_workspace(request: HttpRequest) -> None:
    request.session.pop(SESSION_ADMIN_WORKSPACE_KEY, None)


def set_admin_workspace(request: HttpRequest, workspace_id: int) -> None:
    request.session[SESSION_ADMIN_WORKSPACE_KEY] = int(workspace_id)
    request.session.modified = True


def get_admin_workspace_id(request: HttpRequest) -> int | None:
    raw = request.session.get(SESSION_ADMIN_WORKSPACE_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def admin_owned_workspaces(user: User):
    return Workspace.objects.filter(owner=user).order_by("workspace_name", "pk")


def resolve_admin_workspace(request: HttpRequest, user: User) -> Workspace | None:
    ws_id = get_admin_workspace_id(request)
    if ws_id is None:
        return None
    return admin_owned_workspaces(user).filter(pk=ws_id).first()


def attach_admin_workspace_to_request(request: HttpRequest, user: User) -> None:
    """
    Define request.active_admin_workspace para templates.
    Um único workspace: fixa na sessão automaticamente.
    Vários: só preenche se a sessão apontar para um dos seus.
    """
    owned = list(admin_owned_workspaces(user))
    n = len(owned)
    if n == 0:
        request.active_admin_workspace = None
        return
    if n == 1:
        set_admin_workspace(request, owned[0].pk)
        request.active_admin_workspace = owned[0]
        return
    ws = resolve_admin_workspace(request, user)
    request.active_admin_workspace = ws
