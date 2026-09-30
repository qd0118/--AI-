"""Run with: streamlit run app/dashboard.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st

from app.analysis import Scenario, expense_view, pnl, product_view, revenue_bridge, scenario
from app.agent import draft_report

st.set_page_config(page_title="财务BP经营分析", page_icon="📊", layout="wide")
st.title("预算编制与经营分析决策平台")
st.caption("格拉斯哥大学会计与金融专业背景下的项目实践｜公开年报校准；2025年月度经营、预算、订单及应收为模拟数据")

month = st.sidebar.selectbox("分析月份（2025年）", list(range(1,13)), index=8, format_func=lambda m: f"{m}月")
st.sidebar.header("情景假设")
volume = st.sidebar.slider("销量变化", -30, 30, 0) / 100
price = st.sidebar.slider("成交价变化", -20, 20, 0) / 100
cost = st.sidebar.slider("单位成本变化", -20, 20, 0) / 100
marketing = st.sidebar.slider("推广预算转至线下（负值为转至线上）", -30, 30, 0) / 100
delay = st.sidebar.slider("额外延迟回款比例", 0, 30, 0) / 100
case = Scenario(month, volume, price, cost, marketing, delay)
money = lambda x: f"¥{x/1e6:,.1f} 百万"
row = pnl().set_index("month").loc[month]
scenario_result = scenario(case)

c1,c2,c3,c4 = st.columns(4)
c1.metric("实际收入", money(row.actual_revenue), money(row.actual_revenue-row.budget_revenue))
c2.metric("实际毛利", money(row.actual_gross_profit), money(row.actual_gross_profit-row.budget_gross_profit))
c3.metric("实际费用", money(row.actual_opex), money(row.actual_opex-row.budget_opex), delta_color="inverse")
c4.metric("期末应收（模拟）", money(row.closing_ar))

tab1,tab2,tab3 = st.tabs(["预实分析", "情景决策", "Agent报告"])
with tab1:
    st.subheader("收入与成本桥接")
    bridge = revenue_bridge(month)
    a,b = st.columns(2)
    a.dataframe({k: [round(v/1e6,2)] for k,v in bridge["收入"].items()}, width="stretch")
    b.dataframe({k: [round(v/1e6,2)] for k,v in bridge["成本"].items()}, width="stretch")
    st.caption("桥接单位：百万元；销量→结构→价格／单位成本按固定顺序计算，分项之和等于总差异。")
    st.subheader("产品与渠道")
    view = product_view(month)
    st.dataframe(view, width="stretch")
    st.subheader("部门费用")
    st.dataframe(expense_view(month), width="stretch")
    st.line_chart(pnl().set_index("month")[["budget_revenue","actual_revenue"]])
with tab2:
    st.subheader("在相同月度基线下比较资源配置")
    st.caption("金额单位：百万元。仅为可调整假设的模拟情景；现金为增量代理指标，并非审计现金流量表。")
    d1,d2,d3 = st.columns(3)
    d1.metric("收入变化", money(scenario_result["scenario_revenue"]-scenario_result["baseline_revenue"]))
    d2.metric("经营贡献变化", money(scenario_result["incremental_operating_proxy"]))
    d3.metric("增量现金代理", money(scenario_result["incremental_cash_proxy"]))
    st.json({k: v for k,v in scenario_result.items() if k not in ["assumptions"]})
    st.info(scenario_result["assumptions"])
with tab3:
    llm = st.toggle("启用LLM撰写（需自行设置 OPENAI_API_KEY）", value=False)
    if st.button("运行异常归因与报告Agent"):
        output = draft_report(month, case, use_llm=llm)
        st.caption(output["mode"])
        st.text(output["report"])
        with st.expander("可核对的数据证据"):
            st.json(output["evidence"])
