from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from app.models import CompensationHistory, EmployeeProfile, FinancialEntry, TimeEntry, User, Workspace

_DEFAULT_MONTHLY_HOURS = Decimal("160")
_DAY_KEY_BY_WEEKDAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _time_entry_hours(entry: TimeEntry) -> Decimal:
    if entry.hours is not None:
        return Decimal(str(entry.hours))
    if entry.duration_minutes is not None:
        return Decimal(entry.duration_minutes) / Decimal("60")
    raise ValidationError("Apontamento salvo sem duração válida para cálculo financeiro.")


def _monthly_expected_hours(entry: TimeEntry) -> Decimal:
    schedule = getattr(entry.department, "schedule", None)
    if schedule is None or not getattr(schedule, "expected_hours_per_day", None):
        return _DEFAULT_MONTHLY_HOURS

    working_days = list(schedule.working_days or [])
    if not working_days:
        working_days = ["mon", "tue", "wed", "thu", "fri"]

    year = entry.date.year
    month = entry.date.month
    _, days_in_month = monthrange(year, month)
    worked_days = 0
    allowed = set(working_days)
    for day in range(1, days_in_month + 1):
        current = date(year, month, day)
        if _DAY_KEY_BY_WEEKDAY[current.weekday()] in allowed:
            worked_days += 1

    total = Decimal(worked_days) * Decimal(schedule.expected_hours_per_day)
    return total if total > 0 else _DEFAULT_MONTHLY_HOURS


def get_time_entry_compensation(entry: TimeEntry) -> CompensationHistory:
    profile = EmployeeProfile.objects.filter(
        user=entry.user,
        workspace=entry.workspace,
    ).first()
    if profile is None:
        raise ValidationError("Colaborador sem vínculo empregatício no workspace para cálculo financeiro.")

    compensation = (
        CompensationHistory.objects.filter(
            employee_profile=profile,
            start_date__lte=entry.date,
        )
        .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=entry.date))
        .order_by("-start_date", "-pk")
        .first()
    )
    if compensation is None:
        raise ValidationError("Não existe remuneração vigente para este colaborador na data do apontamento.")
    return compensation


def get_time_entry_cost(entry: TimeEntry) -> Decimal:
    compensation = get_time_entry_compensation(entry)
    hours = _time_entry_hours(entry)
    if compensation.compensation_type == CompensationHistory.CompensationType.HOURLY:
        assert compensation.hourly_rate is not None
        return _quantize_money(Decimal(str(compensation.hourly_rate)) * hours)

    assert compensation.monthly_salary is not None
    expected_hours = _monthly_expected_hours(entry)
    if expected_hours <= 0:
        raise ValidationError("Horas esperadas inválidas para cálculo do custo mensal.")
    hourly_rate = Decimal(str(compensation.monthly_salary)) / expected_hours
    return _quantize_money(hourly_rate * hours)


def _time_entry_cost_description(entry: TimeEntry) -> str:
    parts = [f"Custo do apontamento de {entry.user.email}", f"em {entry.date.isoformat()}"]
    if entry.project_id:
        parts.append(f"projeto {entry.project.name}")
    elif entry.client_id:
        parts.append(f"cliente {entry.client.name}")
    return " - ".join(parts)


def sync_time_entry_financial_entry(entry: TimeEntry, *, actor: User | None) -> FinancialEntry:
    if entry.status != TimeEntry.Status.SAVED:
        raise ValidationError("Apenas apontamentos salvos podem gerar custo financeiro.")

    amount = get_time_entry_cost(entry)
    financial_actor = actor or entry.user
    auto_entry = FinancialEntry.objects.filter(
        time_entry=entry,
        entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST,
    ).first()
    if auto_entry is None:
        auto_entry = FinancialEntry(
            workspace=entry.workspace,
            entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST,
            created_by=financial_actor,
        )

    auto_entry.flow_type = FinancialEntry.FlowType.OUTFLOW
    auto_entry.occurred_on = entry.date
    auto_entry.amount = amount
    auto_entry.description = _time_entry_cost_description(entry)
    auto_entry.client = entry.client
    auto_entry.project = entry.project
    auto_entry.user = entry.user
    auto_entry.time_entry = entry
    auto_entry.source_time_entry_id = entry.pk
    auto_entry.updated_by = financial_actor
    auto_entry.save()
    return auto_entry


def reverse_time_entry_financial_entry(entry: TimeEntry, *, actor: User | None) -> FinancialEntry | None:
    auto_entry = FinancialEntry.objects.filter(
        time_entry=entry,
        entry_kind=FinancialEntry.EntryKind.TIME_ENTRY_COST,
    ).first()
    if auto_entry is None:
        return None

    existing_reversal = FinancialEntry.objects.filter(reversal_of=auto_entry).first()
    if existing_reversal is not None:
        return existing_reversal

    financial_actor = actor or entry.user
    reversal = FinancialEntry(
        workspace=entry.workspace,
        entry_kind=FinancialEntry.EntryKind.REVERSAL,
        flow_type=FinancialEntry.FlowType.INFLOW,
        occurred_on=entry.date,
        amount=auto_entry.amount,
        description=f"Estorno do apontamento de {entry.user.email} em {entry.date.isoformat()}",
        client=auto_entry.client,
        project=auto_entry.project,
        user=entry.user,
        time_entry=entry,
        source_time_entry_id=entry.pk,
        reversal_of=auto_entry,
        created_by=financial_actor,
        updated_by=financial_actor,
    )
    reversal.save()
    return reversal


def calculate_workspace_balance(workspace: Workspace) -> Decimal:
    inflows = workspace.financial_entries.filter(
        flow_type=FinancialEntry.FlowType.INFLOW
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    outflows = workspace.financial_entries.filter(
        flow_type=FinancialEntry.FlowType.OUTFLOW
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return _quantize_money(Decimal(str(inflows)) - Decimal(str(outflows)))
