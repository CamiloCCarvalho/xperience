from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.base_user import AbstractBaseUser
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
    if uploaded.size > MAX_USER_AVATAR_BYTES:
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


def user_avatar_url(user: AbstractBaseUser) -> str:
    if user.is_authenticated and getattr(user, "avatar", None) and user.avatar.name:
        return user.avatar.url
    return fake_workspaces.make_user_avatar()["user_avatar_url"]


def workspace_avatar_url(workspace) -> str:
    if workspace.workspace_avatar and workspace.workspace_avatar.name:
        return workspace.workspace_avatar.url
    return fake_workspaces.make_workspace()["workspace_avatar"]["url"]
