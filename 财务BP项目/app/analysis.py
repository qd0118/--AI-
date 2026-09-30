"""Auditable finance calculations; no LLM participates in arithmetic."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DB = Path(__file__).resolve().parents[1] / "data" / "finance_bp.sqlite"


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    if not sql.lstrip().lower().startswith(("select", "with")):
        raise ValueError("Only read-only queries are permitted")
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def pnl() -> pd.DataFrame:
    return query("SELECT * FROM vw_monthly_pnl ORDER BY month")


def product_view(month: int) -> pd.DataFrame:
    return query("""
        WITH b AS (SELECT product, channel, SUM(units) units_b, SUM(revenue) revenue_b, SUM(cogs) cogs_b
                   FROM budget_2025 WHERE month=? GROUP BY product, channel),
             a AS (SELECT product, channel, SUM(units) units_a, SUM(revenue) revenue_a, SUM(cogs) cogs_a
                   FROM actual_2025 WHERE month=? GROUP BY product, channel)
        SELECT a.product, a.channel, b.units_b, a.units_a, b.revenue_b, a.revenue_a,
               b.cogs_b, a.cogs_a, a.revenue_a-a.cogs_a AS gross_profit_a
        FROM a JOIN b USING(product,channel) ORDER BY a.product,a.channel
    """, (month, month))


def expense_view(month: int) -> pd.DataFrame:
    df = query("SELECT department,account,budget,actual,reason FROM expense_2025 WHERE month=? ORDER BY account", (month,))
    df["variance"] = df.actual - df.budget
    df["variance_pct"] = df.variance / df.budget
    return df


def revenue_bridge(month: int) -> dict[str, float]:
    """Exact volume/mix/price decomposition at product×channel×region grain.

    Mix is sequential: actual units at budget price minus actual total units
    at the budget overall average price. Price is applied last.
    """
    b = query("SELECT product,channel,region,units,price,revenue,cogs,unit_cost FROM budget_2025 WHERE month=?", (month,))
    a = query("SELECT product,channel,region,units,price,revenue,cogs,unit_cost FROM actual_2025 WHERE month=?", (month,))
    x = b.merge(a, on=["product", "channel", "region"], suffixes=("_b", "_a"), validate="one_to_one")
    q0, q1 = x.units_b.sum(), x.units_a.sum()
    p0 = x.revenue_b.sum() / q0
    c0 = x.cogs_b.sum() / q0
    rev = {
        "预算收入": float(x.revenue_b.sum()), "销量影响": float((q1-q0)*p0),
        "结构影响": float((x.units_a*x.price_b).sum()-q1*p0),
        "价格影响": float((x.units_a*(x.price_a-x.price_b)).sum()),
        "实际收入": float(x.revenue_a.sum()),
    }
    cost = {
        "预算成本": float(x.cogs_b.sum()), "销量影响": float((q1-q0)*c0),
        "结构影响": float((x.units_a*x.unit_cost_b).sum()-q1*c0),
        "单位成本影响": float((x.units_a*(x.unit_cost_a-x.unit_cost_b)).sum()),
        "实际成本": float(x.cogs_a.sum()),
    }
    assert abs(sum(v for k,v in rev.items() if k in ["销量影响","结构影响","价格影响"]) -
               (rev["实际收入"] - rev["预算收入"])) < .02
    assert abs(cost["销量影响"]+cost["结构影响"]+cost["单位成本影响"] -
               (cost["实际成本"]-cost["预算成本"])) < .02
    return {"收入": rev, "成本": cost,
            "毛利差异": float((rev["实际收入"]-rev["预算收入"]) - (cost["实际成本"]-cost["预算成本"]))}


@dataclass(frozen=True)
class Scenario:
    month: int
    volume_pct: float = 0.0
    price_pct: float = 0.0
    cost_pct: float = 0.0
    marketing_shift_pct: float = 0.0  # share of monthly marketing spend, online -> offline if positive
    collection_delay_pct: float = 0.0  # extra fraction of collections deferred to next month


def scenario(s: Scenario) -> dict:
    """One-month incremental decision case, compared with that month's actual.

    Spend reallocation is budget neutral. Response ratios are synthetic scenario
    assumptions, not company-observed ROI. Cash is a simplified operational proxy.
    """
    if s.month not in range(1, 13):
        raise ValueError("Month must be 1–12")
    if not (-.5 <= s.volume_pct <= .5 and -.3 <= s.price_pct <= .3 and
            -.3 <= s.cost_pct <= .3 and -.5 <= s.marketing_shift_pct <= .5 and
            0 <= s.collection_delay_pct <= .4):
        raise ValueError("Assumption outside allowed range")
    base = pnl().set_index("month").loc[s.month]
    marketing = expense_view(s.month).set_index("account").loc["市场推广", "actual"]
    moved = float(marketing*s.marketing_shift_pct)
    # Illustrative response: moving ¥1 from online to offline yields +¥0.60
    # of revenue, moving it in reverse yields +¥0.15; margin varies by channel.
    response_revenue = .60*moved if moved >= 0 else .15*(-moved)
    response_cogs = response_revenue * (.65 if moved >= 0 else .53)
    revenue = float(base.actual_revenue*(1+s.volume_pct)*(1+s.price_pct) + response_revenue)
    cost = float(base.actual_cogs*(1+s.volume_pct)*(1+s.cost_pct) + response_cogs)
    expenses = float(base.actual_opex)  # transfer between marketing channels, no extra spend
    profit = revenue-cost-expenses
    base_profit = float(base.actual_contribution_after_expenses)
    # Cash proxy, not an audited cash flow statement: incremental collections
    # less incremental purchase payments (70% of cost this month) and opex.
    incremental_revenue = revenue-float(base.actual_revenue)
    incremental_cost = cost-float(base.actual_cogs)
    incremental_cash = (.80*incremental_revenue - .70*incremental_cost
                        - s.collection_delay_pct*revenue)
    return {
        "month": s.month, "baseline_revenue": float(base.actual_revenue),
        "scenario_revenue": revenue, "baseline_gross_profit": float(base.actual_gross_profit),
        "scenario_gross_profit": revenue-cost, "baseline_operating_proxy": base_profit,
        "scenario_operating_proxy": profit, "incremental_operating_proxy": profit-base_profit,
        "baseline_collections": float(base.collections),
        "incremental_cash_proxy": incremental_cash,
        "scenario_closing_ar_proxy": float(base.closing_ar)+.20*incremental_revenue+s.collection_delay_pct*revenue,
        "marketing_reallocated": moved,
        "assumptions": "All scenario drivers and spend-response coefficients are illustrative; cash proxy is incremental collections minus 70% of incremental cost cash payments, not audited operating cash flow.",
    }
