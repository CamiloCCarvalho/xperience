"""
Domínio do cronômetro de apontamento (start/stop, rascunho, permissões por departamento).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from app.models import Department, TimeEntry, User, UserDepartment, Workspace


def _json_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    return str(value).lower() in ("1", "true", "yes", "on")


def _active_user_departments_qs(user: User, workspace: Workspace):
    return (
        UserDepartment.objects.filter(
            user=user,
            workspace=workspace,
            end_date__isnull=True,
        )
        .select_related("department")
        .order_by("-is_primary", "pk")
    )


def get_member_primary_department(user: User, workspace: Workspace) -> Department | None:
    """Departamento ativo do membro no workspace (preferência por principal)."""
    ud = _active_user_departments_qs(user, workspace).first()
    return ud.department if ud else None


def get_active_draft(user: User, workspace: Workspace) -> TimeEntry | None:
    """Único rascunho permitido por (usuário, workspace), se existir."""
    return (
        TimeEntry.objects.filter(
            user=user,
            workspace=workspace,
            status=TimeEntry.Status.DRAFT,
        )
        .select_related("department", "workspace")
        .first()
    )


def assert_user_may_edit_time_entry(user: User, entry: TimeEntry) -> None:
    """Respeita ``Department.can_edit_time_entries`` do membro no workspace."""
    if entry.user_id != user.pk:
        raise PermissionDenied("Você não pode editar este apontamento.")
    dept = get_member_primary_department(user, entry.workspace)
    if dept is None or not dept.can_edit_time_entries:
        raise PermissionDenied("Edição de apontamentos não permitida para o seu departamento.")


def assert_user_may_delete_time_entry(user: User, entry: TimeEntry) -> None:
    """Respeita ``Department.can_delete_time_entries`` do membro no workspace."""
    if entry.user_id != user.pk:
        raise PermissionDenied("Você não pode excluir este apontamento.")
    dept = get_member_primary_department(user, entry.workspace)
    if dept is None or not dept.can_delete_time_entries:
        raise PermissionDenied("Exclusão de apontamentos não permitida para o seu departamento.")


def time_entry_timer_payload(entry: TimeEntry) -> dict[str, Any]:
    """Serialização mínima para API JSON."""
    return {
        "id": entry.pk,
        "workspace_id": entry.workspace_id,
        "department_id": entry.department_id,
        "date": entry.date.isoformat(),
        "status": entry.status,
        "entry_mode": entry.entry_mode,
        "timer_started_at": entry.timer_started_at.isoformat() if entry.timer_started_at else None,
        "start_time": entry.start_time.isoformat() if entry.start_time else None,
        "end_time": entry.end_time.isoformat() if entry.end_time else None,
        "duration_minutes": entry.duration_minutes,
        "hours": str(entry.hours) if entry.hours is not None else None,
        "is_overtime": entry.is_overtime,
        "timer_pending_template_completion": entry.timer_pending_template_completion,
    }


def start_timer(
    user: User,
    workspace: Workspace,
    *,
    started_at: dt.datetime | None = None,
    is_overtime: bool = False,
) -> TimeEntry:
    """
    Cria ``TimeEntry`` em rascunho (modo cronômetro).
    Falha se já existir qualquer rascunho neste workspace (inclui corrida → IntegrityError).
    """
    if TimeEntry.objects.filter(
        user=user,
        workspace=workspace,
        status=TimeEntry.Status.DRAFT,
    ).exists():
        raise ValidationError(
            "Já existe um rascunho ativo neste workspace. Finalize-o antes de iniciar outro cronômetro."
        )

    department = get_member_primary_department(user, workspace)
    if department is None:
        raise ValidationError("Não há departamento atribuído a você neste workspace.")
    if department.workspace_id != workspace.pk:
        raise ValidationError("Departamento inválido para este workspace.")

    started_at = started_at or timezone.now()
    local = timezone.localtime(started_at)
    start_t = dt.time(
        hour=local.hour,
        minute=local.minute,
        second=local.second,
        microsecond=0,
    )

    entry = TimeEntry(
        user=user,
        workspace=workspace,
        department=department,
        date=local.date(),
        status=TimeEntry.Status.DRAFT,
        entry_mode=TimeEntry.EntryMode.TIMER,
        timer_started_at=started_at,
        start_time=start_t,
        is_overtime=is_overtime,
    )
    try:
        with transaction.atomic():
            entry.save()
    except IntegrityError as exc:
        raise ValidationError(
            "Já existe um rascunho ativo neste workspace. Finalize-o antes de iniciar outro cronômetro."
        ) from exc
    return entry


def stop_timer(
    user: User,
    workspace: Workspace,
    *,
    entry_id: int | None = None,
    stopped_at: dt.datetime | None = None,
) -> TimeEntry:
    """
    Finaliza o rascunho de cronômetro: preenche ``end_time``, ``duration_minutes`` (via ``clean``)
    e grava como ``saved``. Não atravessa meia-noite no fuso configurado.
    """
    stopped_at = stopped_at or timezone.now()

    with transaction.atomic():
        qs = TimeEntry.objects.select_for_update().filter(
            user=user,
            workspace=workspace,
            status=TimeEntry.Status.DRAFT,
        )
        if entry_id is not None:
            entry = qs.filter(pk=entry_id).first()
        else:
            entry = qs.first()

        if entry is None:
            raise ValidationError("Nenhum rascunho ativo para finalizar.")

        if entry.entry_mode != TimeEntry.EntryMode.TIMER:
            raise ValidationError("O rascunho ativo não é um cronômetro.")

        if not entry.timer_started_at:
            raise ValidationError("Registro de cronômetro sem hora de início.")

        start_local = timezone.localtime(entry.timer_started_at)
        stop_local = timezone.localtime(stopped_at)

        if start_local.date() != stop_local.date():
            raise ValidationError("O cronômetro não pode atravessar meia-noite.")

        start_t = dt.time(
            hour=start_local.hour,
            minute=start_local.minute,
            second=start_local.second,
            microsecond=0,
        )
        end_t = dt.time(
            hour=stop_local.hour,
            minute=stop_local.minute,
            second=stop_local.second,
            microsecond=0,
        )

        if end_t <= start_t:
            raise ValidationError(
                "O horário de fim deve ser maior que o de início no mesmo dia "
                "(o cronômetro não pode atravessar meia-noite)."
            )

        entry.start_time = start_t
        entry.end_time = end_t
        entry.date = start_local.date()
        entry.status = TimeEntry.Status.SAVED
        entry.hours = None
        entry.timer_pending_template_completion = True
        entry.save()

    return entry


def discard_pending_timer_saved_entry(user: User, workspace: Workspace, entry_id: int) -> None:
    """
    Remove apontamento salvo pelo fluxo parar-cronômetro enquanto ainda aguarda
    conclusão dos campos do template (``timer_pending_template_completion``).
    """
    with transaction.atomic():
        entry = (
            TimeEntry.objects.filter(pk=entry_id, user=user, workspace=workspace)
            .select_for_update()
            .first()
        )
        if entry is None:
            raise ValidationError("Apontamento não encontrado.")
        if entry.entry_mode != TimeEntry.EntryMode.TIMER or entry.status != TimeEntry.Status.SAVED:
            raise ValidationError("Somente registros do cronômetro neste estado podem ser descartados.")
        if not entry.timer_pending_template_completion:
            raise ValidationError("Este apontamento já foi concluído ou não pode ser descartado por aqui.")
        assert_user_may_delete_time_entry(user, entry)
        entry.delete()
