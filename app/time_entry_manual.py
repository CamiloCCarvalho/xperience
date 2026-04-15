"""
Apontamentos manuais (duração / intervalo): lookup e serialização para API.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from app.models import TimeEntry, User, Workspace
from app.time_entry_prepared import get_member_template_flags


def get_member_time_entry(user: User, workspace: Workspace, pk: int) -> TimeEntry | None:
    """Apontamento do usuário no workspace ativo (qualquer status/modo)."""
    return (
        TimeEntry.objects.filter(pk=pk, user=user, workspace=workspace)
        .select_related("department", "workspace")
        .first()
    )


def assert_manual_entry_editable(entry: TimeEntry) -> None:
    """Rascunhos de cronômetro e registros timer não usam este fluxo de edição manual."""
    if entry.status == TimeEntry.Status.DRAFT:
        raise ValidationError("Rascunhos devem ser tratados pelo fluxo de cronômetro.")
    if entry.entry_mode == TimeEntry.EntryMode.TIMER:
        raise ValidationError("Apontamentos de cronômetro não podem ser editados por este formulário.")


def manual_time_entry_json(entry: TimeEntry) -> dict[str, Any]:
    return {
        "id": entry.pk,
        "workspace_id": entry.workspace_id,
        "department_id": entry.department_id,
        "date": entry.date.isoformat(),
        "status": entry.status,
        "entry_mode": entry.entry_mode,
        "hours": str(entry.hours) if entry.hours is not None else None,
        "start_time": entry.start_time.isoformat() if entry.start_time else None,
        "end_time": entry.end_time.isoformat() if entry.end_time else None,
        "duration_minutes": entry.duration_minutes,
        "client_id": entry.client_id,
        "project_id": entry.project_id,
        "task_id": entry.task_id,
        "entry_type": entry.entry_type or "",
        "description": entry.description or "",
    }


def json_payload_to_manual_form_data(body: dict[str, Any]) -> dict[str, Any]:
    """Converte corpo JSON da API (snake_case com *_id) para dados do ModelForm."""
    data: dict[str, Any] = {}
    if "entry_mode" in body:
        data["entry_mode"] = body["entry_mode"]
    if "date" in body:
        data["date"] = body["date"]
    if "hours" in body:
        data["hours"] = body["hours"]
    if "start_time" in body:
        data["start_time"] = body["start_time"] or None
    if "end_time" in body:
        data["end_time"] = body["end_time"] or None
    if "description" in body:
        data["description"] = body["description"]
    if "entry_type" in body:
        data["entry_type"] = body["entry_type"]
    for key, field in ("client_id", "client"), ("project_id", "project"), ("task_id", "task"):
        if key in body:
            v = body[key]
            data[field] = "" if v is None or v == "" else v
    return data


def _optional_int_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Identificador numérico inválido.") from exc


def complete_saved_timer_template_fields(
    user: User,
    workspace: Workspace,
    entry_id: int,
    data: dict[str, Any],
) -> TimeEntry:
    """
    Atualiza cliente/projeto/tarefa/descrição/tipo em apontamento **salvo** criado pelo cronômetro.
    Respeita validações do modelo e do template do departamento.
    """
    entry = get_member_time_entry(user, workspace, entry_id)
    if entry is None:
        raise ValidationError("Apontamento não encontrado.")
    if entry.entry_mode != TimeEntry.EntryMode.TIMER or entry.status != TimeEntry.Status.SAVED:
        raise ValidationError("Somente registros finalizados pelo cronômetro aceitam esta ação.")

    flags = get_member_template_flags(user, workspace)
    if not flags.get("configured"):
        raise ValidationError("Template de apontamento não configurado.")

    if "client_id" in data:
        entry.client_id = _optional_int_value(data.get("client_id"))
    if "project_id" in data:
        entry.project_id = _optional_int_value(data.get("project_id"))
    if "task_id" in data:
        entry.task_id = _optional_int_value(data.get("task_id"))
    if "description" in data:
        entry.description = (data.get("description") or "").strip()
    if "entry_type" in data:
        entry.entry_type = (data.get("entry_type") or "").strip()

    if flags["use_client"] and entry.client_id is None:
        raise ValidationError("Selecione um cliente.")
    if flags["use_project"] and entry.project_id is None:
        raise ValidationError("Selecione um projeto.")
    if flags["use_task"] and entry.task_id is None:
        raise ValidationError("Selecione uma tarefa.")
    if flags["use_type"]:
        et = entry.entry_type or ""
        if et not in (TimeEntry.EntryType.INTERNAL, TimeEntry.EntryType.EXTERNAL):
            raise ValidationError("Selecione o tipo de apontamento.")

    entry.save()
    return entry
