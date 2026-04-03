from functools import wraps
from typing import Callable, TypeVar

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect

from app.models import User
from app.workspace_session import (
    admin_owned_workspaces,
    attach_admin_workspace_to_request,
    resolve_member_workspace,
)

F = TypeVar("F", bound=Callable[..., HttpResponse])


def platform_admin_required(view_func: F) -> F:
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not isinstance(request.user, User):
            return HttpResponseForbidden()
        if request.user.platform_role != User.PlatformRole.ADMIN:
            return redirect("user-workspaces")
        return view_func(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def admin_active_workspace_required(view_func: F) -> F:
    """Com 2+ workspaces próprios, exige um selecionado na sessão antes do Spaceon."""

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = request.user
        if not isinstance(user, User):
            return HttpResponseForbidden()
        attach_admin_workspace_to_request(request, user)
        n = admin_owned_workspaces(user).count()
        if n >= 2 and request.active_admin_workspace is None:
            messages.warning(
                request,
                "Selecione um workspace na lista para continuar.",
            )
            return redirect("admin-workspaces")
        return view_func(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def member_active_workspace_required(view_func: F) -> F:
    """Exige membro com workspace ativo na sessão e vínculo via Membership."""

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = request.user
        if not isinstance(user, User):
            return HttpResponseForbidden()
        ws = resolve_member_workspace(request, user)
        if ws is None:
            messages.warning(
                request,
                "Selecione um workspace para continuar.",
            )
            return redirect("user-workspaces")
        request.active_member_workspace = ws
        return view_func(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def platform_member_required(view_func: F) -> F:
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not isinstance(request.user, User):
            return HttpResponseForbidden()
        if request.user.platform_role == User.PlatformRole.ADMIN:
            return redirect("admin-workspaces")
        return view_func(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]
