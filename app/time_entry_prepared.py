"""
Criação de apontamento (modo duração) a partir do fluxo pré-apontamento + data no calendário.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError

from app.models import TimeEntry, User, UserDepartment, Workspace
from app.time_entry_timer import _json_bool, get_member_primary_department


def get_member_template_flags(user: User, workspace: Workspace) -> dict[str, Any]:
    base: dict[str, Any] = {
        "configured": False,
        "use_client": False,
        "use_project": False,
        "use_task": False,
        "use_type": False,
        "use_description": False,
    }
    ud = (
        UserDepartment.objects.filter(user=user, workspace=workspace)
        .order_by("end_date", "-is_primary", "pk")
        .select_related("department", "department__template")
        .first()
    )
    if ud is None:
        return base
    tpl = ud.department.template
    if tpl is None:
        return base
    base.update(
        {
            "configured": True,
            "use_client": tpl.use_client,
            "use_project": tpl.use_project,
            "use_task": tpl.use_task,
            "use_type": tpl.use_type,
            "use_description": tpl.use_description,
        }
    )
    return base


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Identificador numérico inválido.") from exc


def create_duration_entry_from_calendar_payload(
    user: User,
    workspace: Workspace,
    payload: dict[str, Any],
) -> TimeEntry:
    """
    Espera chaves: ``date`` (YYYY-MM-DD), ``hours``, opcionais ``client_id``, ``project_id``,
    ``task_id``, ``description``, ``entry_type``, ``workspace_id`` (deve coincidir).
    """
    flags = get_member_template_flags(user, workspace)
    if not flags["configured"]:
        raise ValidationError("Template de apontamento não configurado para o seu departamento.")

    ws_raw = payload.get("workspace_id")
    if ws_raw is None or int(ws_raw) != workspace.pk:
        raise ValidationError("Workspace inválido.")

    date_raw = payload.get("date")
    if not date_raw or not isinstance(date_raw, str):
        raise ValidationError("Informe a data (YYYY-MM-DD).")
    try:
        entry_date = date.fromisoformat(date_raw)
    except ValueError as exc:
        raise ValidationError("Data inválida.") from exc

    hours_raw = payload.get("hours")
    try:
        hours_dec = Decimal(str(hours_raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Horas inválidas.") from exc
    if hours_dec <= 0:
        raise ValidationError("Informe um valor de horas maior que zero.")

    client_id = _optional_int(payload.get("client_id"))
    project_id = _optional_int(payload.get("project_id"))
    task_id = _optional_int(payload.get("task_id"))
    description = (payload.get("description") or "").strip() if payload.get("description") is not None else ""
    entry_type = (payload.get("entry_type") or "").strip()

    if flags["use_client"] and client_id is None:
        raise ValidationError("Selecione um cliente.")
    if flags["use_project"] and project_id is None:
        raise ValidationError("Selecione um projeto.")
    if flags["use_task"] and task_id is None:
        raise ValidationError("Selecione uma tarefa.")
    if flags["use_type"] and entry_type not in (
        TimeEntry.EntryType.INTERNAL,
        TimeEntry.EntryType.EXTERNAL,
    ):
        raise ValidationError("Selecione o tipo de apontamento.")

    department = get_member_primary_department(user, workspace)
    if department is None:
        raise ValidationError("Não há departamento atribuído a você neste workspace.")
    if department.workspace_id != workspace.pk:
        raise ValidationError("Departamento inválido.")

    entry = TimeEntry(
        user=user,
        workspace=workspace,
        department=department,
        date=entry_date,
        status=TimeEntry.Status.SAVED,
        entry_mode=TimeEntry.EntryMode.DURATION,
        hours=hours_dec,
        client_id=client_id,
        project_id=project_id,
        task_id=task_id,
        description=description,
        entry_type=entry_type,
        is_overtime=_json_bool(payload.get("is_overtime")),
    )
    entry.save()
    return entry


def duration_entry_created_payload(entry: TimeEntry) -> dict[str, Any]:
    return {
        "id": entry.pk,
        "date": entry.date.isoformat(),
        "hours": str(entry.hours) if entry.hours is not None else None,
        "duration_minutes": entry.duration_minutes,
        "is_overtime": entry.is_overtime,
    }
