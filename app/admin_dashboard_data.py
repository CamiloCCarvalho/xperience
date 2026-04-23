"""
Agregação de dados reais para o dashboard do gestor (workspace ativo).

Métricas consolidadas usam apenas ``TimeEntry`` salvos e lançamentos ``FinancialEntry``.
Saldo e caixa seguem entradas/saídas reais; orçamento de cliente/projeto vem dos campos
``budget`` / ``estimated_hours`` nos models, sem misturar com saldo de caixa.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from app.compensation_pay import quantize_money, time_entry_hours_decimal
from app.financial import calculate_workspace_balance
from app.models import Department, FinancialEntry, Membership, Project, TimeEntry, User, Workspace

_VALID_PERIOD_KEYS = frozenset({"7d", "30d", "month_current", "month_prev"})


def _d(v: Decimal | None) -> Decimal:
    if v is None:
        return Decimal("0.00")
    return quantize_money(Decimal(str(v)))


def _fmt_br(d: Decimal) -> str:
    q = _d(d)
    s = f"{q:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _user_label(u: User) -> str:
    fn = (u.first_name or "").strip()
    ln = (u.last_name or "").strip()
    if fn or ln:
        return (fn + " " + ln).strip()
    return u.email


def resolve_period_bounds(period_key: str, *, today: date) -> tuple[date, date, str]:
    key = period_key if period_key in _VALID_PERIOD_KEYS else "month_current"
    if key == "7d":
        end = today
        start = today - timedelta(days=6)
        label = f"Últimos 7 dias ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"
    elif key == "30d":
        end = today
        start = today - timedelta(days=29)
        label = f"Últimos 30 dias ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"
    elif key == "month_prev":
        y, m = today.year, today.month
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
        start = date(y, m, 1)
        if m == 12:
            end = date(y, 12, 31)
        else:
            end = date(y, m + 1, 1) - timedelta(days=1)
        label = f"Mês anterior ({start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')})"
    else:
        start = date(today.year, today.month, 1)
        if today.month == 12:
            end = date(today.year, 12, 31)
        else:
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)
        label = f"Mês atual ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"

    return start, end, label


def _balance_through_day(workspace: Workspace, day: date) -> Decimal:
    """Saldo acumulado até o fim do dia ``day`` (entradas − saídas, occurred_on ≤ day)."""
    inf = (
        FinancialEntry.objects.filter(
            workspace=workspace,
            flow_type=FinancialEntry.FlowType.INFLOW,
            occurred_on__lte=day,
        ).aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
    )
    out = (
        FinancialEntry.objects.filter(
            workspace=workspace,
            flow_type=FinancialEntry.FlowType.OUTFLOW,
            occurred_on__lte=day,
        ).aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
    )
    return _d(inf) - _d(out)


def _entry_kind_label(kind: str) -> str:
    mapping = {
        FinancialEntry.EntryKind.MANUAL: "Manual",
        FinancialEntry.EntryKind.TIME_ENTRY_COST: "Custo de apontamento",
        FinancialEntry.EntryKind.REVERSAL: "Estorno",
    }
    return mapping.get(kind, kind)


def build_admin_dashboard(workspace: Workspace, period_key: str) -> dict[str, Any]:
    today = timezone.localdate()
    start, end, period_label = resolve_period_bounds(period_key, today=today)
    period_key_resolved = period_key if period_key in _VALID_PERIOD_KEYS else "month_current"

    fin_exists = FinancialEntry.objects.filter(workspace=workspace).exists()
    current_balance = calculate_workspace_balance(workspace)

    inflow_qs = FinancialEntry.objects.filter(
        workspace=workspace,
        flow_type=FinancialEntry.FlowType.INFLOW,
        occurred_on__gte=start,
        occurred_on__lte=end,
    )
    outflow_qs = FinancialEntry.objects.filter(
        workspace=workspace,
        flow_type=FinancialEntry.FlowType.OUTFLOW,
        occurred_on__gte=start,
        occurred_on__lte=end,
    )
    inflow_total = _d(inflow_qs.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"])
    outflow_total = _d(outflow_qs.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"])
    net_total = _d(inflow_total - outflow_total)

    period_has_financial_movement = inflow_total > 0 or outflow_total > 0
    show_finance_kpis = fin_exists or period_has_financial_movement

    opening_balance = _balance_through_day(workspace, start - timedelta(days=1))

    daily_in: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    daily_out: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in inflow_qs.values("occurred_on").annotate(t=Sum("amount")):
        daily_in[row["occurred_on"]] = _d(row["t"])
    for row in outflow_qs.values("occurred_on").annotate(t=Sum("amount")):
        daily_out[row["occurred_on"]] = _d(row["t"])

    daily_series: list[dict[str, Any]] = []
    balance_series: list[dict[str, Any]] = []
    run_bal = opening_balance
    d = start
    while d <= end:
        di = daily_in.get(d, Decimal("0"))
        do = daily_out.get(d, Decimal("0"))
        di_f = float(di)
        do_f = float(do)
        total_mov_f = di_f + do_f
        if total_mov_f > 0:
            # Cada dia: verde + laranja preenchem 100% da área na proporção entrada/(entrada+saída).
            pct_in = int(round((di_f / total_mov_f) * 100))
            pct_in = max(0, min(100, pct_in))
            pct_out = 100 - pct_in
        else:
            pct_in = 0
            pct_out = 0
        daily_series.append(
            {
                "day": d.isoformat(),
                "day_label": d.strftime("%d/%m"),
                "inflow": di_f,
                "outflow": do_f,
                "pct_in": pct_in,
                "pct_out": pct_out,
            }
        )
        run_bal = _d(run_bal + di - do)
        balance_series.append({"day": d.isoformat(), "day_label": d.strftime("%d/%m"), "balance": float(run_bal)})
        d += timedelta(days=1)

    show_finance_trends = period_has_financial_movement and len(daily_series) > 0

    outflow_kind_agg: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in (
        outflow_qs.values("entry_kind")
        .annotate(t=Coalesce(Sum("amount"), Decimal("0")))
        .order_by()
    ):
        outflow_kind_agg[row["entry_kind"]] = _d(row["t"])
    outflow_by_kind: list[dict[str, Any]] = []
    kind_max = max(outflow_kind_agg.values(), default=Decimal("0"))
    for kind, amt in sorted(outflow_kind_agg.items(), key=lambda x: -x[1]):
        outflow_by_kind.append(
            {
                "kind": kind,
                "label": _entry_kind_label(kind),
                "amount": float(amt),
                "amount_fmt": _fmt_br(amt),
                "pct_width": int((amt / kind_max * 100)) if kind_max > 0 else 0,
            }
        )

    te_qs = (
        TimeEntry.objects.saved_only()
        .filter(workspace=workspace, date__gte=start, date__lte=end)
        .select_related("user", "department", "client", "project")
    )

    total_hours = Decimal("0")
    team_cost_total = Decimal("0")
    dept_cost: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    dept_hours: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    emp_cost: dict[int, tuple[User, Decimal]] = {}
    emp_hours: dict[int, tuple[User, Decimal]] = {}

    client_cost: dict[int, tuple[str, Decimal]] = {}
    project_cost: dict[int, tuple[str, str, Decimal]] = {}

    for entry in te_qs:
        try:
            h = time_entry_hours_decimal(entry)
        except Exception:
            continue
        total_hours += h
        dept_name = entry.department.name if entry.department_id else "—"
        dept_hours[dept_name] += h

        cost = _d(entry.pay_amount_snapshot) if entry.pay_amount_snapshot is not None else Decimal("0")
        team_cost_total += cost
        dept_cost[dept_name] += cost

        uid = entry.user_id
        if uid not in emp_cost:
            emp_cost[uid] = (entry.user, Decimal("0"))
        emp_cost[uid] = (entry.user, emp_cost[uid][1] + cost)
        if uid not in emp_hours:
            emp_hours[uid] = (entry.user, Decimal("0"))
        emp_hours[uid] = (entry.user, emp_hours[uid][1] + h)

        if entry.client_id and entry.client:
            cid = entry.client_id
            if cid not in client_cost:
                client_cost[cid] = (entry.client.name, Decimal("0"))
            client_cost[cid] = (entry.client.name, client_cost[cid][1] + cost)

        if entry.project_id and entry.project:
            pid = entry.project_id
            if pid not in project_cost:
                project_cost[pid] = (entry.project.name, entry.project.client.name, Decimal("0"))
            project_cost[pid] = (
                entry.project.name,
                entry.project.client.name,
                project_cost[pid][2] + cost,
            )

    total_hours_f = float(total_hours.quantize(Decimal("0.01")))
    team_cost_total = _d(team_cost_total)

    dept_list = Department.objects.filter(workspace=workspace).exists()
    member_count = Membership.objects.filter(workspace=workspace).values_list("user_id", flat=True).distinct().count()
    has_members_or_depts = dept_list or member_count > 0
    show_operation = has_members_or_depts and (total_hours > 0 or team_cost_total > 0)

    def _breakdown_cost(rows: list[tuple[str, Decimal]], *, top: int = 8) -> list[dict[str, Any]]:
        rows = [(a, _d(b)) for a, b in rows if b > 0]
        rows.sort(key=lambda x: -x[1])
        mx = rows[0][1] if rows else Decimal("0")
        out = []
        for name, amt in rows[:top]:
            out.append(
                {
                    "name": name,
                    "amount": float(amt),
                    "amount_fmt": _fmt_br(amt),
                    "pct_width": int(amt / mx * 100) if mx > 0 else 0,
                }
            )
        return out

    department_cost_breakdown = _breakdown_cost(list(dept_cost.items()))
    department_hours_breakdown = _breakdown_cost([(k, v) for k, v in dept_hours.items()])

    emp_cost_rows = [(_user_label(u), v) for _uid, (u, v) in emp_cost.items()]
    employee_cost_breakdown = _breakdown_cost(emp_cost_rows)
    emp_h_rows = [(_user_label(u), v) for _uid, (u, v) in emp_hours.items()]
    employee_hours_breakdown = _breakdown_cost(emp_h_rows)

    n_clients = workspace.clients.count()
    n_projects = Project.objects.filter(workspace=workspace).count()
    has_clients = n_clients > 0
    has_projects = n_projects > 0

    client_cost_breakdown = _breakdown_cost([(n, a) for _cid, (n, a) in client_cost.items()])
    project_cost_breakdown = _breakdown_cost([(f"{pn} ({cn})", a) for _pid, (pn, cn, a) in project_cost.items()])

    client_inflow: dict[int, tuple[str, Decimal]] = {}
    for fe in inflow_qs.filter(client__isnull=False).select_related("client"):
        cid = fe.client_id
        if cid and fe.client:
            if cid not in client_inflow:
                client_inflow[cid] = (fe.client.name, Decimal("0"))
            client_inflow[cid] = (fe.client.name, client_inflow[cid][1] + _d(fe.amount))
    client_inflow_breakdown = _breakdown_cost([(n, a) for _cid, (n, a) in client_inflow.items()])

    show_client_section = has_clients and (len(client_cost_breakdown) > 0 or len(client_inflow_breakdown) > 0)
    show_project_cost_section = has_projects and len(project_cost_breakdown) > 0

    # Budget vs actual (project.budget); gasto = soma snapshots de apontamentos salvos (all-time)
    project_budget_rows: list[dict[str, Any]] = []
    risky_projects: list[dict[str, Any]] = []
    projects_hours_compare: list[dict[str, Any]] = []

    for proj in Project.objects.filter(workspace=workspace).select_related("client"):
        budget = proj.budget
        if budget is not None and budget > 0:
            spent_all = _d(
                TimeEntry.objects.saved_only()
                .filter(workspace=workspace, project=proj, pay_amount_snapshot__isnull=False)
                .aggregate(t=Coalesce(Sum("pay_amount_snapshot"), Decimal("0")))["t"]
            )
            ratio_pct = _d((spent_all / budget) * Decimal("100")) if budget > 0 else Decimal("0")
            pct = float(ratio_pct)
            project_budget_rows.append(
                {
                    "id": proj.pk,
                    "name": proj.name,
                    "client_name": proj.client.name,
                    "budget": float(budget),
                    "budget_fmt": _fmt_br(budget),
                    "spent": float(spent_all),
                    "spent_fmt": _fmt_br(spent_all),
                    "pct": round(pct, 1),
                    "pct_width": min(100, int(pct)),
                    "over_budget": spent_all > budget,
                }
            )
            if ratio_pct >= Decimal("90") or spent_all > budget:
                risky_projects.append(
                    {
                        "name": proj.name,
                        "client_name": proj.client.name,
                        "pct": round(pct, 1),
                        "over_budget": spent_all > budget,
                    }
                )

        eh = proj.estimated_hours
        if eh is not None and eh > 0:
            hrs_real = Decimal("0")
            for e in TimeEntry.objects.saved_only().filter(workspace=workspace, project=proj):
                try:
                    hrs_real += time_entry_hours_decimal(e)
                except Exception:
                    pass
            projects_hours_compare.append(
                {
                    "name": proj.name,
                    "client_name": proj.client.name,
                    "estimated": float(eh),
                    "realized": float(hrs_real.quantize(Decimal("0.01"))),
                    "pct_hours": float(_d((hrs_real / eh) * Decimal("100"))) if eh > 0 else 0.0,
                }
            )

    show_budget_block = len(project_budget_rows) > 0
    show_hours_estimate_block = len(projects_hours_compare) > 0

    # Maiores saídas do período (top 8)
    top_outflows = list(
        outflow_qs.select_related("user", "client", "project").order_by("-amount", "-pk")[:8]
    )
    attention_rows: list[dict[str, Any]] = []
    for fe in top_outflows:
        attention_rows.append(
            {
                "kind": "outflow",
                "label": "Saída",
                "title": (fe.description or "")[:80],
                "detail": fe.occurred_on.strftime("%d/%m/%Y"),
                "amount_fmt": _fmt_br(fe.amount),
            }
        )
    for row in sorted(dept_cost.items(), key=lambda x: -x[1])[:5]:
        if row[1] > 0:
            attention_rows.append(
                {
                    "kind": "dept_cost",
                    "label": "Custo · departamento",
                    "title": row[0],
                    "detail": period_label,
                    "amount_fmt": _fmt_br(row[1]),
                }
            )
    for _uid, (u, amt) in sorted(emp_cost.items(), key=lambda x: -x[1][1])[:5]:
        if amt > 0:
            attention_rows.append(
                {
                    "kind": "emp_cost",
                    "label": "Custo · colaborador",
                    "title": _user_label(u),
                    "detail": period_label,
                    "amount_fmt": _fmt_br(amt),
                }
            )
    for r in risky_projects[:8]:
        attention_rows.append(
            {
                "kind": "risk_project",
                "label": "Projeto · budget",
                "title": r["name"],
                "detail": f"{r['client_name']} — {r['pct']}% consumido"
                + (" — estourado" if r["over_budget"] else ""),
                "amount_fmt": "",
            }
        )

    show_where_money = (
        len(outflow_by_kind) > 0
        or len(department_cost_breakdown) > 0
        or len(employee_cost_breakdown) > 0
        or len(department_hours_breakdown) > 0
        or len(employee_hours_breakdown) > 0
    )
    show_commercial = show_client_section or show_project_cost_section or show_budget_block or show_hours_estimate_block
    show_attention = len(attention_rows) > 0

    balances = [b["balance"] for b in balance_series]
    if balances:
        bal_min = min(balances)
        bal_max = max(balances)
        if bal_min == bal_max:
            bal_min -= 1.0
            bal_max += 1.0
    else:
        bal_min, bal_max = 0.0, 1.0

    outflow_pie_style = ""
    balance_svg_points = ""
    if len(balance_series) <= 1:
        balance_svg_points = "0,50 100,50"
    else:
        nbal = len(balance_series)
        pts: list[str] = []
        for i, b in enumerate(balance_series):
            x = (i / (nbal - 1)) * 100.0 if nbal > 1 else 50.0
            span = bal_max - bal_min
            t = (b["balance"] - bal_min) / span if span else 0.5
            t = max(0.0, min(1.0, t))
            y = 100.0 - t * 100.0
            pts.append(f"{x:.2f},{y:.2f}")
        balance_svg_points = " ".join(pts)

    if outflow_by_kind:
        total_k = sum(k["amount"] for k in outflow_by_kind)
        if total_k > 0:
            colors = ["#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#ef4444", "#06b6d4", "#eab308"]
            angle = 0.0
            parts: list[str] = []
            for i, k in enumerate(outflow_by_kind):
                frac = k["amount"] / total_k
                end = angle + frac * 360.0
                parts.append(f"{colors[i % len(colors)]} {angle:.3f}deg {end:.3f}deg")
                angle = end
            outflow_pie_style = "conic-gradient(" + ", ".join(parts) + ")"

    has_any_content = (
        show_finance_kpis
        or show_finance_trends
        or show_operation
        or show_where_money
        or show_commercial
        or show_attention
    )

    period_options = [
        {"key": "7d", "label": "7 dias", "active": period_key_resolved == "7d"},
        {"key": "30d", "label": "30 dias", "active": period_key_resolved == "30d"},
        {"key": "month_current", "label": "Mês atual", "active": period_key_resolved == "month_current"},
        {"key": "month_prev", "label": "Mês anterior", "active": period_key_resolved == "month_prev"},
    ]

    return {
        "period_key": period_key_resolved,
        "period_label": period_label,
        "period_start": start,
        "period_end": end,
        "period_options": period_options,
        "current_balance": current_balance,
        "current_balance_fmt": _fmt_br(current_balance),
        "inflow_total": inflow_total,
        "inflow_total_fmt": _fmt_br(inflow_total),
        "outflow_total": outflow_total,
        "outflow_total_fmt": _fmt_br(outflow_total),
        "net_total": net_total,
        "net_total_fmt": _fmt_br(net_total),
        "total_logged_hours": total_hours_f,
        "total_logged_hours_fmt": f"{total_hours_f:.2f}".replace(".", ","),
        "team_cost_total": team_cost_total,
        "team_cost_total_fmt": _fmt_br(team_cost_total),
        "daily_series": daily_series,
        "balance_series": balance_series,
        "outflow_by_kind": outflow_by_kind,
        "department_cost_breakdown": department_cost_breakdown,
        "employee_cost_breakdown": employee_cost_breakdown,
        "department_hours_breakdown": department_hours_breakdown,
        "employee_hours_breakdown": employee_hours_breakdown,
        "client_cost_breakdown": client_cost_breakdown,
        "client_inflow_breakdown": client_inflow_breakdown,
        "project_cost_breakdown": project_cost_breakdown,
        "project_budget_rows": project_budget_rows,
        "risky_projects": risky_projects,
        "projects_hours_compare": projects_hours_compare,
        "attention_rows": attention_rows,
        "show_finance_kpis": show_finance_kpis,
        "show_finance_trends": show_finance_trends,
        "show_operation": show_operation,
        "show_where_money": show_where_money,
        "show_client_section": show_client_section,
        "show_project_cost_section": show_project_cost_section,
        "show_budget_block": show_budget_block,
        "show_hours_estimate_block": show_hours_estimate_block,
        "show_commercial": show_commercial,
        "show_attention": show_attention,
        "has_any_content": has_any_content,
        "has_clients": has_clients,
        "has_projects": has_projects,
        "balance_chart_min": bal_min,
        "balance_chart_max": bal_max,
        "outflow_pie_style": outflow_pie_style,
        "balance_svg_points": balance_svg_points,
    }
