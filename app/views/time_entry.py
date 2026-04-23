import json
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from app.decorators import member_active_workspace_required, platform_member_required
from app.forms import ManualTimeEntryForm, manual_time_entry_form_first_error
from app.models import Department, Membership, TimeEntry, User, Workspace
from app.time_entry_manual import (
    assert_manual_entry_editable,
    complete_saved_timer_template_fields,
    day_modal_entry_payload,
    get_member_time_entry,
    json_payload_to_manual_form_data,
    manual_time_entry_json,
)
from app.time_entry_prepared import (
    create_duration_entry_from_calendar_payload,
    duration_entry_created_payload,
)
from app.compensation_pay import day_pay_totals_for_calendar
from app.time_entry_timer import (
    _json_bool,
    assert_user_may_delete_time_entry,
    assert_user_may_edit_time_entry,
    discard_pending_timer_saved_entry,
    get_active_draft,
    get_member_primary_department,
    start_timer,
    stop_timer,
    time_entry_timer_payload,
)


def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


_VALID_SCHEDULE_WEEKDAY_KEYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
_DEFAULT_SCHEDULE_WORKING_DAYS = ["mon", "tue", "wed", "thu", "fri"]


def _schedule_weekday_visual_payload(schedule) -> dict[str, list[str]] | None:
    """
    Dias da semana com expediente, para o calendário do membro.
    Retorna None quando não há folga fixa por dia da semana (``has_fixed_days`` falso).
    """
    if not schedule.has_fixed_days:
        return None
    raw = list(schedule.working_days or [])
    normalized = [k for k in raw if k in _VALID_SCHEDULE_WEEKDAY_KEYS]
    if not normalized:
        normalized = list(_DEFAULT_SCHEDULE_WORKING_DAYS)
    return {"working_days": normalized}


def _workspace_member_user_ids(ws: Workspace) -> set[int]:
    ids = set(Membership.objects.filter(workspace=ws).values_list("user_id", flat=True))
    if ws.owner_id:
        ids.add(int(ws.owner_id))
    return ids


def _workspace_public_birthday_calendar_entries(ws: Workspace, viewer: User) -> list[dict[str, object]]:
    """
    Colegas do workspace com data de nascimento e visibilidade pública no calendário
    (exclui o usuário que está vendo a tela).
    """
    member_ids = _workspace_member_user_ids(ws)
    if not member_ids:
        return []
    rows: list[dict[str, object]] = []
    for u in (
        User.objects.filter(
            pk__in=member_ids,
            birth_date__isnull=False,
            birthday_public_in_workspace=True,
        )
        .exclude(pk=viewer.pk)
        .only("first_name", "last_name", "email", "birth_date")
        .iterator()
    ):
        bd = u.birth_date
        if bd is None:
            continue
        display = (u.get_full_name() or "").strip() or u.email
        rows.append({"month": int(bd.month), "day": int(bd.day), "display_name": display})
    return rows


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
    Contagem e soma de horas de apontamentos salvos por dia no mês (workspace ativo),
    para o calendário. Inclui meta diária (expediente do departamento principal do membro).
    Retorna apenas datas com pelo menos um registro em ``by_date``; o cliente trata ausência
    como zero. ``expected_hours_per_day`` é ``null`` quando não há expediente vinculado.
    ``schedule_weekday_visual`` é ``null`` ou ``{"working_days": ["mon", ...]}`` quando a
    folga segue dias fixos da semana; o cliente destaca os demais dias com ranhura discreta.
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
    by_count: defaultdict[date, int] = defaultdict(int)
    by_hours: defaultdict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in (
        TimeEntry.objects.saved_only()
        .filter(user=user, workspace=ws, date__gte=start, date__lte=end)
        .values("date", "hours", "duration_minutes")
    ):
        d = row["date"]
        if not isinstance(d, date):
            continue
        by_count[d] += 1
        piece = Decimal("0")
        if row["hours"] is not None:
            piece = Decimal(str(row["hours"]))
        elif row.get("duration_minutes"):
            piece = (Decimal(int(row["duration_minutes"])) / Decimal(60)).quantize(Decimal("0.01"))
        by_hours[d] += piece

    by_date: dict[str, int] = {}
    by_date_hours: dict[str, float] = {}
    for d, total in by_count.items():
        if total <= 0:
            continue
        key = d.isoformat()
        by_date[key] = int(total)
        by_date_hours[key] = float(by_hours[d].quantize(Decimal("0.01")))

    pay_totals = day_pay_totals_for_calendar(user, ws, year, month)
    by_date_pay: dict[str, float] = {}
    for d in by_count:
        if by_count[d] <= 0:
            continue
        tot_pay = pay_totals.get(d, Decimal("0"))
        by_date_pay[d.isoformat()] = float(tot_pay.quantize(Decimal("0.01")))

    expected_hours_per_day: int | None = None
    schedule_weekday_visual: dict[str, list[str]] | None = None
    dept = get_member_primary_department(user, ws)
    if dept is not None:
        dept = Department.objects.select_related("schedule").filter(pk=dept.pk).first()
        if dept and dept.schedule_id:
            sch = dept.schedule
            expected_hours_per_day = int(sch.expected_hours_per_day)
            schedule_weekday_visual = _schedule_weekday_visual_payload(sch)

    member_birthday: dict[str, int] | None = None
    birth = getattr(user, "birth_date", None)
    if birth is not None:
        member_birthday = {"month": int(birth.month), "day": int(birth.day)}

    workspace_public_birthdays = _workspace_public_birthday_calendar_entries(ws, user)

    return JsonResponse(
        {
            "by_date": by_date,
            "by_date_hours": by_date_hours,
            "by_date_pay": by_date_pay,
            "expected_hours_per_day": expected_hours_per_day,
            "schedule_weekday_visual": schedule_weekday_visual,
            "member_birthday": member_birthday,
            "workspace_public_birthdays": workspace_public_birthdays,
        }
    )


@platform_member_required
@member_active_workspace_required
@require_GET
def time_entry_day_detail(request):
    """
    Detalhe de um dia para o modal do calendário (fora do modo pré-apontamento):
    apontamentos salvos com permissões de editar/excluir e eventos (ex.: aniversário).
    """
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    raw = (request.GET.get("date") or "").strip()
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return _json_error("Informe date no formato YYYY-MM-DD.", status=400)
    if d.year < 2000 or d.year > 2100:
        return _json_error("Data fora do intervalo válido.", status=400)

    qs = (
        TimeEntry.objects.saved_only()
        .filter(user=user, workspace=ws, date=d)
        .select_related("client", "project", "task")
        .order_by("id")
    )
    entries = [day_modal_entry_payload(user, e) for e in qs]

    events: list[dict[str, str]] = []
    birth = getattr(user, "birth_date", None)
    if birth is not None and int(birth.month) == d.month and int(birth.day) == d.day:
        display = (user.get_full_name() or "").strip() or user.email
        events.append(
            {
                "type": "birthday",
                "title": "Aniversário",
                "detail": f"Aniversário de {display} nesta data.",
            }
        )

    member_ids = _workspace_member_user_ids(ws)
    if member_ids:
        for u in (
            User.objects.filter(
                pk__in=member_ids,
                birth_date__isnull=False,
                birthday_public_in_workspace=True,
            )
            .exclude(pk=user.pk)
            .only("first_name", "last_name", "email", "birth_date")
            .iterator()
        ):
            bd = u.birth_date
            if bd is None:
                continue
            if int(bd.month) != d.month or int(bd.day) != d.day:
                continue
            display = (u.get_full_name() or "").strip() or u.email
            events.append(
                {
                    "type": "birthday",
                    "title": "Aniversário",
                    "detail": f"Aniversário de {display} nesta data.",
                }
            )

    return JsonResponse({"date": d.isoformat(), "entries": entries, "events": events})


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
    data = _parse_json_body(request)
    try:
        entry = start_timer(user, ws, is_overtime=_json_bool(data.get("is_overtime")))
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
def timer_discard_pending(request):
    """Descarta apontamento salvo ao parar o cronômetro, antes de concluir o template."""
    user = request.user
    assert isinstance(user, User)
    ws = request.active_member_workspace
    data = _parse_json_body(request)
    try:
        entry_id = int(data.get("entry_id") or 0)
    except (TypeError, ValueError):
        return _json_error("entry_id inválido.", status=400)
    if entry_id <= 0:
        return _json_error("Informe entry_id.", status=400)
    try:
        discard_pending_timer_saved_entry(user, ws, entry_id)
    except ValidationError as exc:
        msg = exc.messages[0] if exc.messages else str(exc)
        return _json_error(msg, status=400)
    except PermissionDenied as exc:
        return _json_error(str(exc), status=403)
    return JsonResponse({"ok": True}, status=200)


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
