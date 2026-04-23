from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest

from app.models import User
from utils.faker import fake_workspaces

MAX_USER_AVATAR_BYTES = 2 * 1024 * 1024
ALLOWED_USER_AVATAR_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)


def handle_user_avatar_upload(request: HttpRequest, user: User) -> None:
    """Valida e persiste ``User.avatar`` (campo já existente no modelo)."""
    uploaded = request.FILES.get("avatar")
    if not uploaded:
        messages.warning(request, "Selecione um arquivo de imagem.")
        return
    if int(getattr(uploaded, "size", 0) or 0) > MAX_USER_AVATAR_BYTES:
        messages.error(request, "A imagem deve ter no máximo 2 MB.")
        return
    raw_ct = getattr(uploaded, "content_type", None) or ""
    ctype = raw_ct.split(";")[0].strip().lower()
    if ctype not in ALLOWED_USER_AVATAR_TYPES:
        messages.error(request, "Formato não suportado. Use JPEG, PNG, WebP ou GIF.")
        return
    if user.avatar:
        user.avatar.delete(save=False)
    user.avatar = uploaded
    user.save()


def handle_workspace_avatar_upload(request: HttpRequest, workspace) -> None:
    """Valida e persiste ``Workspace.workspace_avatar`` (logo do workspace)."""
    uploaded = request.FILES.get("workspace_avatar")
    if not uploaded:
        messages.warning(request, "Selecione uma imagem para a logo do workspace.")
        return
    if int(getattr(uploaded, "size", 0) or 0) > MAX_USER_AVATAR_BYTES:
        messages.error(request, "A imagem deve ter no máximo 2 MB.")
        return
    raw_ct = getattr(uploaded, "content_type", None) or ""
    ctype = raw_ct.split(";")[0].strip().lower()
    if ctype not in ALLOWED_USER_AVATAR_TYPES:
        messages.error(request, "Formato não suportado. Use JPEG, PNG, WebP ou GIF.")
        return
    if workspace.workspace_avatar:
        workspace.workspace_avatar.delete(save=False)
    workspace.workspace_avatar = uploaded
    workspace.save(update_fields=["workspace_avatar", "updated_at"])


def remove_user_avatar(user: User) -> bool:
    if not user.avatar or not user.avatar.name:
        return False
    user.avatar.delete(save=False)
    user.avatar = None
    user.save(update_fields=["avatar"])
    return True


def remove_workspace_avatar(workspace) -> bool:
    if not workspace.workspace_avatar or not workspace.workspace_avatar.name:
        return False
    workspace.workspace_avatar.delete(save=False)
    workspace.workspace_avatar = None
    workspace.save(update_fields=["workspace_avatar", "updated_at"])
    return True


def user_avatar_url(user: User) -> str:
    if user.is_authenticated and getattr(user, "avatar", None) and user.avatar.name:
        return user.avatar.url
    return fake_workspaces.make_user_avatar()["user_avatar_url"]


def workspace_avatar_url(workspace) -> str:
    if workspace.workspace_avatar and workspace.workspace_avatar.name:
        return workspace.workspace_avatar.url
    return fake_workspaces.make_workspace()["workspace_avatar"]["url"]
