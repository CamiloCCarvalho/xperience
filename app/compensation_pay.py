"""
Cálculo centralizado de remuneração por apontamento (custo / valor a pagar).

Todas as fórmulas e a resolução da remuneração vigente pela data do apontamento
ficam aqui; ``app.financial`` apenas consome o resultado para ``FinancialEntry``.

Fórmulas (valor do apontamento = ``pay_amount``):

- **hourly**: ``pay_amount = horas_apontamento * hourly_rate`` (taxa vigente na data).

- **monthly + salário fixo** (``monthly_salary_is_fixed`` é True ou nulo em registros legados):
  ``valor_hora_efetivo = monthly_salary / horas_previstas_mes`` (expediente do
  departamento do apontamento na data do cálculo; congelado em snapshot).
  ``pay_amount = horas_apontamento * valor_hora_efetivo``.

- **monthly + salário não fixo** (``monthly_salary_is_fixed`` é False):
  ``valor_hora_base = monthly_salary / monthly_reference_hours``;
  ``pay_amount = horas_apontamento * valor_hora_base``.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TypedDict

from django.core.exceptions import ValidationError
from django.db import models

from app.models import CompensationHistory, EmployeeProfile, TimeEntry, User, WorkSchedule, Workspace

_DEFAULT_MONTHLY_HOURS = Decimal("160")
_DAY_KEY_BY_WEEKDAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def expected_working_hours_in_month(year: int, month: int, schedule: WorkSchedule | None) -> Decimal:
    """Total de horas previstas no mês (dias úteis da escala × horas/dia)."""
    if schedule is None or not getattr(schedule, "expected_hours_per_day", None):
        return _DEFAULT_MONTHLY_HOURS

    working_days = list(schedule.working_days or [])
    if not working_days:
        working_days = ["mon", "tue", "wed", "thu", "fri"]

    _, days_in_month = monthrange(year, month)
    worked_days = 0
    allowed = set(working_days)
    for day in range(1, days_in_month + 1):
        current = date(year, month, day)
        if _DAY_KEY_BY_WEEKDAY[current.weekday()] in allowed:
            worked_days += 1

    total = Decimal(worked_days) * Decimal(schedule.expected_hours_per_day)
    return total if total > 0 else _DEFAULT_MONTHLY_HOURS


def time_entry_hours_decimal(entry: TimeEntry) -> Decimal:
    """
    Horas efetivas do apontamento salvo: prioriza ``hours`` (modo duração);
    caso contrário usa ``duration_minutes`` (intervalo/cronômetro após ``clean``).
    """
    if entry.hours is not None:
        return Decimal(str(entry.hours))
    if entry.duration_minutes is not None:
        return Decimal(entry.duration_minutes) / Decimal("60")
    raise ValidationError("Apontamento salvo sem duração válida para cálculo de remuneração.")


def get_compensation_for_user_on_date(
    user: User, workspace: Workspace, on_date: date
) -> CompensationHistory:
    profile = EmployeeProfile.objects.filter(user=user, workspace=workspace).first()
    if profile is None:
        raise ValidationError("Colaborador sem vínculo empregatício no workspace para cálculo de remuneração.")

    compensation = (
        CompensationHistory.objects.filter(employee_profile=profile, start_date__lte=on_date)
        .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=on_date))
        .order_by("-start_date", "-pk")
        .first()
    )
    if compensation is None:
        raise ValidationError("Não existe remuneração vigente para este colaborador na data do apontamento.")
    return compensation


def get_compensation_for_entry(entry: TimeEntry) -> CompensationHistory:
    return get_compensation_for_user_on_date(entry.user, entry.workspace, entry.date)


class PayComputationResult(TypedDict):
    amount: Decimal
    effective_hourly_rate: Decimal
    expected_month_hours: Decimal | None
    compensation_history_id: int


def compute_time_entry_pay(entry: TimeEntry) -> PayComputationResult:
    """
    Calcula valor monetário do apontamento e taxa-hora efetiva, sem gravar no banco.
    Exige ``status == saved`` e dados de duração coerentes com ``full_clean``.
    """
    if entry.status != TimeEntry.Status.SAVED:
        raise ValidationError("Apenas apontamentos salvos têm valor de remuneração calculável.")

    compensation = get_compensation_for_entry(entry)
    hours = time_entry_hours_decimal(entry)
    schedule = getattr(entry.department, "schedule", None)

    if compensation.compensation_type == CompensationHistory.CompensationType.HOURLY:
        assert compensation.hourly_rate is not None
        rate = Decimal(str(compensation.hourly_rate))
        amount = quantize_money(rate * hours)
        return PayComputationResult(
            amount=amount,
            effective_hourly_rate=quantize_rate(rate),
            expected_month_hours=None,
            compensation_history_id=compensation.pk,
        )

    assert compensation.monthly_salary is not None
    salary = Decimal(str(compensation.monthly_salary))

    is_fixed = compensation.monthly_salary_is_fixed
    if is_fixed is None:
        is_fixed = True

    if is_fixed:
        expected = expected_working_hours_in_month(entry.date.year, entry.date.month, schedule)
        if expected <= 0:
            raise ValidationError("Horas previstas inválidas para cálculo do salário mensal fixo.")
        effective = salary / expected
        amount = quantize_money(effective * hours)
        exp_snap = expected.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return PayComputationResult(
            amount=amount,
            effective_hourly_rate=quantize_rate(effective),
            expected_month_hours=exp_snap,
            compensation_history_id=compensation.pk,
        )

    ref = compensation.monthly_reference_hours
    if ref is None or ref <= 0:
        raise ValidationError("Informe horas base mensais (maiores que zero) para remuneração mensal não fixa.")
    ref_dec = Decimal(str(ref))
    effective = salary / ref_dec
    amount = quantize_money(effective * hours)
    ref_snap = ref_dec.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return PayComputationResult(
        amount=amount,
        effective_hourly_rate=quantize_rate(effective),
        expected_month_hours=ref_snap,
        compensation_history_id=compensation.pk,
    )


def compute_and_assign_pay_snapshots(entry: TimeEntry) -> None:
    """Preenche (ou limpa) os campos de snapshot monetário no próprio ``entry``."""
    if entry.status != TimeEntry.Status.SAVED:
        entry.pay_amount_snapshot = None
        entry.effective_hourly_rate_snapshot = None
        entry.expected_month_hours_snapshot = None
        entry.compensation_history_snapshot_id = None
        return
    data = compute_time_entry_pay(entry)
    entry.pay_amount_snapshot = data["amount"]
    entry.effective_hourly_rate_snapshot = data["effective_hourly_rate"]
    entry.expected_month_hours_snapshot = data["expected_month_hours"]
    entry.compensation_history_snapshot_id = data["compensation_history_id"]


def day_pay_totals_for_calendar(
    user: User, workspace: Workspace, year: int, month: int
) -> dict[date, Decimal]:
    """Soma ``pay_amount_snapshot`` por dia (apenas salvos) — backend para o calendário."""
    last = monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last)
    totals: dict[date, Decimal] = {}
    for row in (
        TimeEntry.objects.saved_only()
        .filter(user=user, workspace=workspace, date__gte=start, date__lte=end)
        .values("date", "pay_amount_snapshot")
    ):
        d = row["date"]
        if not isinstance(d, date):
            continue
        snap = row.get("pay_amount_snapshot")
        if snap is None:
            continue
        piece = Decimal(str(snap))
        totals[d] = totals.get(d, Decimal("0")) + piece
    return totals
