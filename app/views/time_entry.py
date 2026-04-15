import json
from calendar import monthrange
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from app.decorators import member_active_workspace_required, platform_member_required
from app.forms import ManualTimeEntryForm, manual_time_entry_form_first_error
from app.models import TimeEntry, User
from app.time_entry_manual import (
    assert_manual_entry_editable,
    complete_saved_timer_template_fields,
    get_member_time_entry,
    json_payload_to_manual_form_data,
    manual_time_entry_json,
)
from app.time_entry_prepared import (
    create_duration_entry_from_calendar_payload,
    duration_entry_created_payload,
)
from app.time_entry_timer import (
    assert_user_may_delete_time_entry,
    assert_user_may_edit_time_entry,
    get_active_draft,
    get_member_primary_department,
    start_timer,
    stop_timer,
    time_entry_timer_payload,
)


def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _format_validation_error(exc: ValidationError) -> str:
    if getattr(exc, "error_dict", None):
        for _field, msgs in exc.error_dict.items():
            if isinstance(msgs, list) and msgs:
                return str(msgs[0])
            return str(msgs)
    if exc.messages:
        return str(exc.messages[0])
    return str(exc)


@platform_member_required
@member_active_workspace_required
@require_GET
def time_entry_month_counts(request):
    """
    Contagem de apontamentos salvos por dia no mês (workspace ativo), para o calendário.
    Retorna apenas datas com pelo menos um registro; o cliente trata ausência como zero.
    """
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    try:
        year = int(request.GET.get("year") or 0)
        month = int(request.GET.get("month") or 0)
    except (TypeError, ValueError):
        return _json_error("Parâmetros year e month inválidos.", status=400)
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        return _json_error("year ou month fora do intervalo válido.", status=400)
    last = monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last)
    rows = (
        TimeEntry.objects.saved_only()
        .filter(user=user, workspace=ws, date__gte=start, date__lte=end)
        .values("date")
        .annotate(total=Count("pk"))
    )
    by_date: dict[str, int] = {}
    for row in rows:
        d = row["date"]
        key = d.isoformat() if isinstance(d, date) else str(d)
        by_date[key] = int(row["total"])
    return JsonResponse({"by_date": by_date})


def _parse_json_body(request) -> dict:
    ctype = request.META.get("CONTENT_TYPE", "")
    if "application/json" not in ctype:
        return {}
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode())
    except json.JSONDecodeError:
        return {}


@platform_member_required
@member_active_workspace_required
@require_GET
def timer_active_draft(request):
    """Retorna o rascunho ativo do usuário no workspace da sessão (se houver)."""
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    draft = get_active_draft(user, ws)
    if draft is None:
        return JsonResponse({"active": False, "entry": None})
    return JsonResponse({"active": True, "entry": time_entry_timer_payload(draft)})


@platform_member_required
@member_active_workspace_required
@require_POST
def timer_start(request):
    """Inicia cronômetro: cria ``TimeEntry`` em ``draft`` (JSON opcional vazio)."""
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    try:
        entry = start_timer(user, ws)
    except ValidationError as exc:
        msg = exc.messages[0] if exc.messages else str(exc)
        return _json_error(msg, status=400)
    return JsonResponse(
        {"entry": time_entry_timer_payload(entry)},
        status=201,
    )


@platform_member_required
@member_active_workspace_required
@require_POST
def timer_stop(request):
    """
    Finaliza o cronômetro do rascunho ativo (ou do ``entry_id`` informado no JSON).
    Corpo JSON opcional: ``entry_id``, ``stopped_at`` (ISO-8601; default: agora).
    """
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    data = _parse_json_body(request)
    raw_id = data.get("entry_id")
    entry_id: int | None
    if raw_id is None or raw_id == "":
        entry_id = None
    else:
        try:
            entry_id = int(raw_id)
        except (TypeError, ValueError):
            return _json_error("entry_id inválido.", status=400)

    stopped_at = None
    raw_stop = data.get("stopped_at")
    if raw_stop:
        parsed = parse_datetime(str(raw_stop))
        if parsed is None:
            return _json_error("stopped_at inválido (use ISO-8601).", status=400)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        stopped_at = parsed

    try:
        entry = stop_timer(user, ws, entry_id=entry_id, stopped_at=stopped_at)
    except ValidationError as exc:
        msg = exc.messages[0] if exc.messages else str(exc)
        return _json_error(msg, status=400)

    return JsonResponse({"entry": time_entry_timer_payload(entry)}, status=200)


@platform_member_required
@member_active_workspace_required
@require_POST
def prepared_entry_submit(request):
    """
    Salva apontamento em modo duração na data informada (JSON), após o fluxo de preparar no cliente.
    """
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    data = _parse_json_body(request)
    if not data:
        return _json_error("Envie um corpo JSON com date, hours e os campos do template.", status=400)
    try:
        entry = create_duration_entry_from_calendar_payload(user, ws, data)
    except ValidationError as exc:
        return _json_error(_format_validation_error(exc), status=400)
    except PermissionDenied as exc:
        return _json_error(str(exc), status=403)
    return JsonResponse(
        {"ok": True, "entry": duration_entry_created_payload(entry)},
        status=201,
    )


def _save_manual_time_entry_from_form(user: User, workspace, form: ManualTimeEntryForm) -> TimeEntry:
    department = get_member_primary_department(user, workspace)
    if department is None:
        raise ValidationError("Não há departamento atribuído a você neste workspace.")
    if department.workspace_id != workspace.pk:
        raise ValidationError("Departamento inválido.")
    entry = form.save(commit=False)
    entry.user = user
    entry.workspace = workspace
    entry.department = department
    entry.status = TimeEntry.Status.SAVED
    entry.timer_started_at = None
    if entry.entry_mode == TimeEntry.EntryMode.DURATION:
        entry.start_time = None
        entry.end_time = None
    elif entry.entry_mode == TimeEntry.EntryMode.TIME_RANGE:
        entry.hours = None
    entry.save()
    return entry


def _update_manual_time_entry_from_form(entry: TimeEntry, form: ManualTimeEntryForm) -> TimeEntry:
    obj = form.save(commit=False)
    obj.status = TimeEntry.Status.SAVED
    obj.timer_started_at = None
    if obj.entry_mode == TimeEntry.EntryMode.DURATION:
        obj.start_time = None
        obj.end_time = None
    elif obj.entry_mode == TimeEntry.EntryMode.TIME_RANGE:
        obj.hours = None
    obj.save()
    return obj


@platform_member_required
@member_active_workspace_required
@require_POST
def manual_time_entry_create(request):
    """Cria apontamento manual (``duration`` ou ``time_range``), JSON."""
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    body = _parse_json_body(request)
    if not body:
        return _json_error("Envie JSON com entry_mode, date e campos do modo escolhido.", status=400)
    data = json_payload_to_manual_form_data(body)
    if not data.get("entry_mode") or not data.get("date"):
        return _json_error("Informe entry_mode e date.", status=400)
    form = ManualTimeEntryForm(data=data, user=user, workspace=ws)
    if not form.is_valid():
        return _json_error(manual_time_entry_form_first_error(form), status=400)
    try:
        entry = _save_manual_time_entry_from_form(user, ws, form)
    except ValidationError as exc:
        return _json_error(_format_validation_error(exc), status=400)
    except PermissionDenied as exc:
        return _json_error(str(exc), status=403)
    return JsonResponse({"ok": True, "entry": manual_time_entry_json(entry)}, status=201)


@platform_member_required
@member_active_workspace_required
@require_POST
def manual_time_entry_update(request, pk: int):
    """Atualiza apontamento manual salvo (não rascunho, não modo timer)."""
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    entry = get_member_time_entry(user, ws, pk)
    if entry is None:
        return JsonResponse({"error": "Apontamento não encontrado."}, status=404)
    try:
        assert_manual_entry_editable(entry)
    except ValidationError as exc:
        return _json_error(_format_validation_error(exc), status=400)
    try:
        assert_user_may_edit_time_entry(user, entry)
    except PermissionDenied as exc:
        return _json_error(str(exc), status=403)
    body = _parse_json_body(request)
    if not body:
        return _json_error("Envie JSON com os campos a atualizar.", status=400)
    data = json_payload_to_manual_form_data(body)
    if not data.get("entry_mode") or not data.get("date"):
        return _json_error("Informe entry_mode e date.", status=400)
    form = ManualTimeEntryForm(data=data, user=user, workspace=ws, instance=entry)
    if not form.is_valid():
        return _json_error(manual_time_entry_form_first_error(form), status=400)
    try:
        updated = _update_manual_time_entry_from_form(entry, form)
    except ValidationError as exc:
        return _json_error(_format_validation_error(exc), status=400)
    except PermissionDenied as exc:
        return _json_error(str(exc), status=403)
    return JsonResponse({"ok": True, "entry": manual_time_entry_json(updated)}, status=200)


@platform_member_required
@member_active_workspace_required
@require_POST
def manual_time_entry_delete(request, pk: int):
    """Exclui apontamento do usuário no workspace ativo (respeita ``can_delete_time_entries``)."""
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    entry = get_member_time_entry(user, ws, pk)
    if entry is None:
        return JsonResponse({"error": "Apontamento não encontrado."}, status=404)
    try:
        assert_user_may_delete_time_entry(user, entry)
    except PermissionDenied as exc:
        return _json_error(str(exc), status=403)
    entry.delete()
    return JsonResponse({"ok": True}, status=200)


@platform_member_required
@member_active_workspace_required
@require_POST
def timer_saved_complete_fields(request):
    """
    Completa cliente/projeto/tarefa/descrição/tipo em apontamento salvo originado do cronômetro (JSON).
    """
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    data = _parse_json_body(request)
    if not data:
        return _json_error("Envie JSON com entry_id e os campos do template.", status=400)
    try:
        entry_id = int(data.get("entry_id") or 0)
    except (TypeError, ValueError):
        return _json_error("entry_id inválido.", status=400)
    if entry_id <= 0:
        return _json_error("Informe entry_id.", status=400)
    entry = get_member_time_entry(user, ws, entry_id)
    if entry is None:
        return JsonResponse({"error": "Apontamento não encontrado."}, status=404)
    try:
        assert_user_may_edit_time_entry(user, entry)
    except PermissionDenied as exc:
        return _json_error(str(exc), status=403)
    try:
        updated = complete_saved_timer_template_fields(user, ws, entry_id, data)
    except ValidationError as exc:
        return _json_error(_format_validation_error(exc), status=400)
    return JsonResponse({"ok": True, "entry": manual_time_entry_json(updated)}, status=200)
