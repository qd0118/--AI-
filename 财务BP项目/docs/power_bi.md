# Power BI 导入与页面搭建

本项目提供 Power BI 看板所需的 CSV、页面设计和 DAX 指标。在 Power BI Desktop 中选择“获取数据 → 文本/CSV”，导入 `exports/monthly_pnl.csv`、`product_channel.csv`、`department_expenses.csv` 和 `variance_bridge.csv`；按下方步骤完成后保存为 `.pbix`，即可作为可直接演示的看板文件。所有金额为人民币元，年月均为 **2025 年模拟数据**。

## 建议页面

1. 月度经营总览：按 `month` 筛选；卡片显示收入、毛利、费用及期末应收；折线显示预算与实际收入。
2. 业务下钻：从 `product_channel` 按产品、渠道看预算与实际收入、成本、毛利。
3. 费用与归因：`department_expenses` 的部门、科目矩阵及超预算 5% 标记；`variance_bridge` 做收入和成本的分项瀑布图。桥接的“预算收入/实际收入”等是端点，瀑布图只把中间变化项作为增量。

## 示例 DAX（在相应导入表中新建度量值）

```dax
实际收入 = SUM(monthly_pnl[actual_revenue])
预算收入 = SUM(monthly_pnl[budget_revenue])
收入差异 = [实际收入] - [预算收入]
收入差异率 = DIVIDE([收入差异], [预算收入])
实际毛利 = SUM(monthly_pnl[actual_gross_profit])
毛利率 = DIVIDE([实际毛利], [实际收入])
费用差异 = SUM(monthly_pnl[actual_opex]) - SUM(monthly_pnl[budget_opex])
实际经营贡献 = SUM(monthly_pnl[actual_contribution_after_expenses])
```

在多个事实表之间同步筛选月份时，建立单列 `DimMonth`（值 1–12），分别与四个事实表的 month 建立单向一对多关系；产品和渠道只存在于 `product_channel`，无需把它们强连到汇总月表。可用 `exports/sample_evidence_2025_09.json` 核对 9 月的差异。

## 数据边界

安克创新 2024 年度公开报告仅用于三类产品年度收入/成本的数值校准及费用量级参照。所有模拟明细、2025 年预算和实际、应收收款、异常原因均由本案例生成。不能把看板结果称为公司的真实经营表现。
