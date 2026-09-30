"""Two bounded agents: anomaly triage and evidence-grounded report drafting."""
from __future__ import annotations

import json
import os
import urllib.request

from .analysis import expense_view, pnl, revenue_bridge, scenario, Scenario


def evidence(month: int, threshold: float = .05) -> dict:
    row = pnl().set_index("month").loc[month]
    bridge = revenue_bridge(month)
    expenses = expense_view(month)
    significant = expenses.loc[expenses.variance_pct.abs() >= threshold]
    cases = [{"account": x.account, "variance_rmb": round(float(x.variance), 2),
              "variance_pct": round(float(x.variance_pct), 4), "simulated_cause": x.reason}
             for x in significant.itertuples(index=False)]
    return {
        "month": month,
        "metric_source": f"vw_monthly_pnl WHERE month={month}; expense_2025; budget_2025; actual_2025",
        "budget_revenue": round(float(row.budget_revenue), 2),
        "actual_revenue": round(float(row.actual_revenue), 2),
        "budget_gross_profit": round(float(row.budget_gross_profit), 2),
        "actual_gross_profit": round(float(row.actual_gross_profit), 2),
        "budget_opex": round(float(row.budget_opex), 2),
        "actual_opex": round(float(row.actual_opex), 2),
        "revenue_bridge": bridge["收入"], "cost_bridge": bridge["成本"],
        "gross_profit_variance": bridge["毛利差异"],
        "expense_alerts": cases, "closing_ar": round(float(row.closing_ar), 2),
        "disclosure": "2025 monthly budgets, transactions, receivables and causes are synthetic; no actual company managerial decisions are represented.",
    }


def deterministic_draft(ev: dict, decision: dict | None = None) -> str:
    m = ev["month"]
    rb = ev["revenue_bridge"]
    lines = [f"{m}月模拟经营分析初稿（单位：百万元；基于模拟明细）",
             f"收入：预算 {ev['budget_revenue']/1e6:,.1f}，实际 {ev['actual_revenue']/1e6:,.1f}。",
             f"收入差异：销量 {rb['销量影响']/1e6:+,.1f}，结构 {rb['结构影响']/1e6:+,.1f}，价格 {rb['价格影响']/1e6:+,.1f}。",
             f"毛利差异 {ev['gross_profit_variance']/1e6:+,.1f}；费用实际与预算差异 {(ev['actual_opex']-ev['budget_opex'])/1e6:+,.1f}。"]
    for x in ev["expense_alerts"]:
        lines.append(f"费用关注：{x['account']}差异 {x['variance_rmb']/1e6:+,.1f} 百万元（{x['variance_pct']:+.1%}）；记录原因：{x['simulated_cause']}。")
    if decision:
        lines.append(f"情景测算：相对基线经营贡献变化 {decision['incremental_operating_proxy']/1e6:+,.1f} 百万元；增量现金代理变化 {decision['incremental_cash_proxy']/1e6:+,.1f} 百万元。")
    lines += ["后续动作：核对异常费用的业务计划及归属期间；根据情景结果由负责人判断是否调整投入。",
              f"计算依据：{ev['metric_source']}。所有月度数据均为模拟，建议需人工审核。"]
    return "\n".join(lines)


def draft_report(month: int, decision: Scenario | None = None, use_llm: bool = False) -> dict:
    """Run the two agents. LLM calls are opt-in and restricted to writing only."""
    ev = evidence(month)
    calculated = scenario(decision) if decision else None
    fallback = deterministic_draft(ev, calculated)
    if not use_llm:
        return {"mode": "规则化报告（未调用LLM）", "evidence": ev, "scenario": calculated, "report": fallback}
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"mode": "未设置OPENAI_API_KEY；规则化报告", "evidence": ev, "scenario": calculated, "report": fallback}
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "你是财务BP报告写作助手。只能依据给定JSON解释数据，不得创造数字、真实企业行为或已落实建议。必须标明所有月度数据为模拟、来源表名、待人工复核。用简洁中文分成结论、差异归因、情景建议。"},
            {"role": "user", "content": json.dumps({"evidence": ev, "scenario": calculated}, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request("https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        report = result["choices"][0]["message"]["content"]
        if not isinstance(report, str) or "模拟" not in report:
            raise ValueError("LLM report omitted data provenance")
        return {"mode": "LLM报告初稿，待人工复核", "evidence": ev, "scenario": calculated, "report": report}
    except Exception as exc:
        return {"mode": f"LLM调用失败；规则化报告 ({type(exc).__name__})", "evidence": ev,
                "scenario": calculated, "report": fallback}
