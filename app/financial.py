from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from app.models import FinancialEntry, TimeEntry, User, Workspace


def _quantize_money(value: Decimal) -> Decimal:
    from app.compensation_pay import quantize_money

    return quantize_money(value)


def get_time_entry_compensation(entry: TimeEntry):
    """Compatível com código legado: delega à camada única de remuneração."""
    from app.compensation_pay import get_compensation_for_entry

    return get_compensation_for_entry(entry)


def get_time_entry_cost(entry: TimeEntry) -> Decimal:
    """Custo do apontamento = snapshot monetário (definido em ``TimeEntry.save``)."""
    if entry.status != TimeEntry.Status.SAVED:
        raise ValidationError("Apenas apontamentos salvos têm custo calculável.")
    if entry.pay_amount_snapshot is None:
        raise ValidationError("Apontamento sem valor monetário consolidado (snapshot).")
    return Decimal(str(entry.pay_amount_snapshot))


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
