from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Tuple

import pandas as pd


def _ensure_datetime(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column in df.columns:
        df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def calculate_days_without_sale(orders_df: pd.DataFrame, products_df: pd.DataFrame) -> pd.DataFrame:
    orders = orders_df.copy()
    orders = _ensure_datetime(orders, "created_at")
    orders = orders[orders["created_at"].notna()]
    orders["status"] = orders.get("status", "").astype(str).str.lower()
    orders = orders[orders["status"] != "cancelado"]

    last_sale = (
        orders.groupby("sku")["created_at"].max().reset_index().rename(columns={"created_at": "last_sale"})
    )
    products = products_df.copy()
    products = products.merge(last_sale, on="sku", how="left")
    products["days_without_sale"] = (
        pd.Timestamp.now() - products["last_sale"].fillna(pd.Timestamp.now())
    ).dt.days
    return products


def calculate_margin(orders_df: pd.DataFrame, products_df: pd.DataFrame) -> pd.DataFrame:
    orders = orders_df.copy()
    orders = _ensure_datetime(orders, "created_at")
    orders = orders[orders["created_at"].notna()]
    orders["status"] = orders.get("status", "").astype(str).str.lower()
    orders = orders[orders["status"] != "cancelado"]
    orders["qty"] = pd.to_numeric(orders.get("qty", 0), errors="coerce").fillna(0.0)
    orders["total"] = pd.to_numeric(orders.get("total", 0), errors="coerce").fillna(0.0)

    # Selecionar apenas colunas que existem em products_df
    product_cols = ["sku", "cost"]
    if "product_name" in products_df.columns:
        product_cols.insert(1, "product_name")
    
    products = products_df[product_cols].copy()
    merged = orders.merge(products, on="sku", how="left")
    merged["cost"] = pd.to_numeric(merged.get("cost", 0), errors="coerce").fillna(0.0)
    merged["cost_total"] = merged["qty"] * merged["cost"]
    merged["margin"] = merged["total"] - merged["cost_total"]

    # Preparar colunas para agrupamento
    group_cols = ["sku"]
    if "product_name" in merged.columns:
        group_cols.append("product_name")
        merged["product_name"] = merged["product_name"].fillna("Unknown")
    
    grouped = (
        merged.groupby(group_cols, dropna=False)
        .agg(qty_sold=("qty", "sum"), revenue=("total", "sum"), margin=("margin", "sum"))
        .reset_index()
    )
    return grouped


def classify_customer_recurrence(orders_df: pd.DataFrame) -> pd.DataFrame:
    orders = orders_df.copy()
    orders = _ensure_datetime(orders, "created_at")
    orders = orders[orders["created_at"].notna()]
    orders = orders.sort_values("created_at")

    first_purchase = orders.groupby("customer_id")["created_at"].transform("min")
    orders["customer_type"] = orders.apply(
        lambda row: "Novos Clientes" if row["created_at"] == first_purchase[row.name] else "Recorrentes",
        axis=1,
    )
    return orders


def _classify_abc(revenue_by_sku: pd.DataFrame) -> pd.DataFrame:
    revenue_by_sku = revenue_by_sku.sort_values("revenue", ascending=False)
    revenue_by_sku["cum_share"] = revenue_by_sku["revenue"].cumsum() / max(
        revenue_by_sku["revenue"].sum(), 1
    )
    revenue_by_sku["abc"] = revenue_by_sku["cum_share"].apply(
        lambda x: "A" if x <= 0.8 else ("B" if x <= 0.95 else "C")
    )
    return revenue_by_sku


def build_commander_kpis(
    orders_df: pd.DataFrame,
    products_df: pd.DataFrame,
    stock_df: pd.DataFrame,
) -> Dict[str, object]:
    orders = orders_df.copy()
    orders = _ensure_datetime(orders, "created_at")
    orders = orders[orders["created_at"].notna()]
    orders["status"] = orders.get("status", "").astype(str).str.lower()
    orders = orders[orders["status"] != "cancelado"]
    orders["total"] = pd.to_numeric(orders.get("total", 0), errors="coerce").fillna(0.0)
    orders["qty"] = pd.to_numeric(orders.get("qty", 0), errors="coerce").fillna(0.0)

    last_30 = orders[orders["created_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=30))]
    prev_30 = orders[(orders["created_at"] < pd.Timestamp.now() - pd.Timedelta(days=30)) &
                     (orders["created_at"] >= pd.Timestamp.now() - pd.Timedelta(days=60))]

    revenue_30 = last_30["total"].sum()
    revenue_prev = prev_30["total"].sum()
    delta = _safe_div(revenue_30 - revenue_prev, revenue_prev) * 100 if revenue_prev else 0

    ticket = _safe_div(revenue_30, max(last_30.shape[0], 1))

    margin_df = calculate_margin(last_30, products_df)
    gross_profit = margin_df["margin"].sum()

    # Pedidos travados - detalhamento
    locked_orders = orders[orders["status"].isin(["em aberto", "atrasado"])].copy()
    locked = locked_orders.shape[0]
    
    # Preparar dados dos pedidos travados para relatório
    if "order_id" in locked_orders.columns:
        locked_details = locked_orders[["order_id", "total", "status", "created_at"]].copy()
    elif "id" in locked_orders.columns:
        locked_details = locked_orders[["id", "total", "status", "created_at"]].copy()
        locked_details = locked_details.rename(columns={"id": "order_id"})
    else:
        # Criar IDs fictícios se não existirem
        locked_details = locked_orders[["total", "status", "created_at"]].copy()
        locked_details["order_id"] = [f"PED-{i+1}" for i in range(len(locked_details))]
        locked_details = locked_details[["order_id", "total", "status", "created_at"]]
    
    locked_details["total"] = pd.to_numeric(locked_details["total"], errors="coerce").fillna(0.0)
    locked_details = locked_details.sort_values("total", ascending=False)

    # Faturamento dos últimos 90 dias com comparação ao período anterior
    last_90 = orders[orders["created_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=90))]
    prev_90 = orders[(orders["created_at"] < pd.Timestamp.now() - pd.Timedelta(days=90)) &
                     (orders["created_at"] >= pd.Timestamp.now() - pd.Timedelta(days=180))]
    
    daily_current = last_90.groupby(last_90["created_at"].dt.date)["total"].sum().reset_index()
    daily_current = daily_current.rename(columns={"created_at": "date", "total": "revenue_current"})
    
    # Calcular faturamento do mesmo dia no período anterior (90 dias atrás)
    prev_90["date_offset"] = (prev_90["created_at"] + pd.Timedelta(days=90)).dt.date
    daily_prev = prev_90.groupby("date_offset")["total"].sum().reset_index()
    daily_prev = daily_prev.rename(columns={"date_offset": "date", "total": "revenue_prev"})
    
    # Merge dos dados atuais com anteriores
    daily = daily_current.merge(daily_prev, on="date", how="left")
    daily["revenue_prev"] = daily["revenue_prev"].fillna(0)

    stock = stock_df.copy()
    stock["saldo"] = pd.to_numeric(stock.get("saldo", 0), errors="coerce").fillna(0.0)
    stock["cost"] = pd.to_numeric(stock.get("cost", 0), errors="coerce").fillna(0.0)

    last_90_sales = orders[orders["created_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=90))]
    daily_sales = last_90_sales.groupby("sku")["qty"].sum() / 90.0
    daily_sales = daily_sales.reset_index().rename(columns={"qty": "daily_qty"})

    coverage = stock.merge(daily_sales, on="sku", how="left")
    coverage["daily_qty"] = coverage["daily_qty"].fillna(0.0)
    coverage["coverage_days"] = coverage.apply(
        lambda row: _safe_div(row["saldo"], row["daily_qty"]) if row["daily_qty"] > 0 else 999,
        axis=1,
    )

    last_30_rev = last_30.groupby("sku")["total"].sum().reset_index().rename(columns={"total": "revenue"})
    top = last_30_rev.copy()
    top["share"] = top["revenue"] / max(top["revenue"].sum(), 1)
    top = top[top["share"] > 0.05]
    top = top.merge(coverage[["sku", "coverage_days"]], on="sku", how="left")
    rupture = top[top["coverage_days"] < 5]

    days_without = calculate_days_without_sale(orders, products_df)
    stock_value = stock_df.copy()
    stock_value["saldo"] = pd.to_numeric(stock_value.get("saldo", 0), errors="coerce").fillna(0.0)
    stock_value["cost"] = pd.to_numeric(stock_value.get("cost", 0), errors="coerce").fillna(0.0)
    
    # Selecionar apenas colunas que existem em stock_value
    stock_cols = ["sku", "saldo"]
    if "cost" in stock_value.columns:
        stock_cols.append("cost")
    
    dead_stock = days_without.merge(stock_value[stock_cols], on="sku", how="left")
    dead_stock = dead_stock[dead_stock["days_without_sale"] > 90]
    
    # Calcular dead_value com segurança
    if "saldo" in dead_stock.columns and "cost" in dead_stock.columns:
        dead_stock["saldo"] = pd.to_numeric(dead_stock["saldo"], errors="coerce").fillna(0.0)
        dead_stock["cost"] = pd.to_numeric(dead_stock["cost"], errors="coerce").fillna(0.0)
        dead_value = (dead_stock["saldo"] * dead_stock["cost"]).sum()
    else:
        dead_value = 0.0

    # ========== RISCO DE RUPTURA DETALHADO (7 dias) ==========
    # Produtos com alta venda que vão acabar em 7 dias
    rupture_risk = coverage[
        (coverage["coverage_days"] < 7) & 
        (coverage["saldo"] > 0) &
        (coverage["daily_qty"] > 0)
    ].copy()
    
    # Adicionar product_name de forma segura
    if not rupture_risk.empty:
        if "product_name" in products_df.columns and "sku" in products_df.columns:
            product_names = products_df[["sku", "product_name"]].drop_duplicates()
            rupture_risk = rupture_risk.merge(product_names, on="sku", how="left")
            if "product_name" in rupture_risk.columns:
                rupture_risk["product_name"] = rupture_risk["product_name"].fillna(rupture_risk["sku"])
            else:
                rupture_risk["product_name"] = rupture_risk["sku"]
        else:
            rupture_risk["product_name"] = rupture_risk["sku"]
    else:
        rupture_risk["product_name"] = []
    
    # Calcular valor de venda que será perdido
    if "cost" in rupture_risk.columns:
        rupture_risk["daily_revenue"] = rupture_risk["daily_qty"] * rupture_risk["cost"] * 2.5  # Markup médio
    else:
        rupture_risk["daily_revenue"] = rupture_risk["daily_qty"] * 50  # Valor default
    rupture_risk["lost_revenue_7d"] = rupture_risk["daily_revenue"] * (7 - rupture_risk["coverage_days"]).clip(0)
    
    rupture_table = rupture_risk[["product_name", "saldo", "coverage_days"]].copy()
    rupture_table = rupture_table.sort_values("coverage_days", ascending=True).head(10)
    rupture_lost_value = rupture_risk["lost_revenue_7d"].sum()
    
    # ========== ESTOQUE MORTO DETALHADO (>90 dias) ==========
    # Verificar se dead_stock tem as colunas necessárias
    if "cost" in dead_stock.columns and "saldo" in dead_stock.columns:
        dead_stock["stock_value"] = dead_stock["saldo"] * dead_stock["cost"]
    else:
        dead_stock["stock_value"] = 0.0
    
    dead_stock_sorted = dead_stock.sort_values("stock_value", ascending=False)
    
    # Adicionar product_name ao dead_stock (verificar se existe)
    if not dead_stock_sorted.empty:
        if "product_name" in products_df.columns and "sku" in products_df.columns:
            product_names = products_df[["sku", "product_name"]].drop_duplicates()
            dead_stock_sorted = dead_stock_sorted.merge(product_names, on="sku", how="left")
            if "product_name" in dead_stock_sorted.columns:
                dead_stock_sorted["product_name"] = dead_stock_sorted["product_name"].fillna(dead_stock_sorted["sku"])
            else:
                dead_stock_sorted["product_name"] = dead_stock_sorted["sku"]
        else:
            dead_stock_sorted["product_name"] = dead_stock_sorted["sku"]
    else:
        dead_stock_sorted["product_name"] = []
    
    # Garantir que days_without_sale existe
    if "days_without_sale" not in dead_stock_sorted.columns:
        dead_stock_sorted["days_without_sale"] = 0
    
    # Top 5 vilões
    if not dead_stock_sorted.empty and "product_name" in dead_stock_sorted.columns:
        dead_top_villains = dead_stock_sorted[["product_name", "days_without_sale", "stock_value"]].head(5)
    else:
        dead_top_villains = pd.DataFrame(columns=["product_name", "days_without_sale", "stock_value"])
    
    # ========== FATURAMENTO 30 DIAS (para gráfico de área) ==========
    last_30_daily = last_30.groupby(last_30["created_at"].dt.date)["total"].sum().reset_index()
    last_30_daily = last_30_daily.rename(columns={"created_at": "date", "total": "revenue"})
    
    # Média do período anterior (para linha de referência)
    avg_prev_daily = revenue_prev / 30 if revenue_prev > 0 else 0

    return {
        "revenue_30": revenue_30,
        "delta": delta,
        "ticket": ticket,
        "gross_profit": gross_profit,
        "locked": locked,
        "locked_details": locked_details,
        "daily": daily,
        "daily_30": last_30_daily,
        "avg_prev_daily": avg_prev_daily,
        "rupture_count": rupture.shape[0],
        "rupture_table": rupture_table,
        "rupture_lost_value": rupture_lost_value,
        "dead_value": dead_value,
        "dead_top_villains": dead_top_villains,
    }


def build_inventory_intelligence(
    orders_df: pd.DataFrame,
    products_df: pd.DataFrame,
    stock_df: pd.DataFrame,
) -> Dict[str, object]:
    orders = orders_df.copy()
    orders = _ensure_datetime(orders, "created_at")
    orders = orders[orders["created_at"].notna()]
    orders["status"] = orders.get("status", "").astype(str).str.lower()
    orders = orders[orders["status"] != "cancelado"]
    orders["qty"] = pd.to_numeric(orders.get("qty", 0), errors="coerce").fillna(0.0)
    orders["total"] = pd.to_numeric(orders.get("total", 0), errors="coerce").fillna(0.0)

    stock = stock_df.copy()
    stock["saldo"] = pd.to_numeric(stock.get("saldo", 0), errors="coerce").fillna(0.0)
    stock["cost"] = pd.to_numeric(stock.get("cost", 0), errors="coerce").fillna(0.0)
    stock["stock_value"] = stock["saldo"] * stock["cost"]

    # ========== KPIs ==========
    total_stock_value = stock["stock_value"].sum()
    
    # Vendas diárias dos últimos 90 dias
    last_90 = orders[orders["created_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=90))]
    daily_sales = last_90.groupby("sku")["qty"].sum() / 90.0
    daily_sales = daily_sales.reset_index().rename(columns={"qty": "daily_qty"})

    merged = stock.merge(daily_sales, on="sku", how="left")
    merged["daily_qty"] = merged["daily_qty"].fillna(0.0)
    merged["coverage_days"] = merged.apply(
        lambda row: _safe_div(row["saldo"], row["daily_qty"]) if row["daily_qty"] > 0 else 999,
        axis=1,
    )
    merged["status"] = merged["coverage_days"].apply(
        lambda x: "COMPRAR 🚨" if x < 15 else "OK"
    )
    
    # Cobertura média ponderada (por valor)
    valid_coverage = merged[merged["coverage_days"] < 999].copy()
    if not valid_coverage.empty and valid_coverage["stock_value"].sum() > 0:
        avg_coverage = (valid_coverage["coverage_days"] * valid_coverage["stock_value"]).sum() / valid_coverage["stock_value"].sum()
    else:
        avg_coverage = 0.0
    
    # Itens em ruptura (saldo = 0)
    items_rupture = (merged["saldo"] == 0).sum()
    rupture_pct = _safe_div(items_rupture, merged.shape[0]) * 100

    # Recência - dias sem venda
    recency = calculate_days_without_sale(orders, products_df)
    
    # ABC Classification
    abc_base = orders.groupby("sku")["total"].sum().reset_index().rename(columns={"total": "revenue"})
    abc = _classify_abc(abc_base)
    
    # Merge para dados completos
    scatter = merged.merge(recency[["sku", "days_without_sale"]], on="sku", how="left")
    scatter = scatter.merge(abc[["sku", "abc"]], on="sku", how="left")
    scatter["days_without_sale"] = scatter["days_without_sale"].fillna(0)
    scatter["abc"] = scatter["abc"].fillna("C")
    
    # Remove product_name duplicado se existir
    if "product_name" in scatter.columns:
        scatter = scatter.drop(columns=["product_name"])
    
    # Adicionar product_name se existir em products_df
    if "product_name" in products_df.columns:
        scatter = scatter.merge(products_df[["sku", "product_name"]], on="sku", how="left")
        scatter["product_name"] = scatter["product_name"].fillna(scatter["sku"])
    else:
        scatter["product_name"] = scatter["sku"]
    
    # ========== ESTOQUE MORTO (> 90 dias sem venda) ==========
    dead_stock = scatter[scatter["days_without_sale"] > 90].copy()
    dead_stock_value = dead_stock["stock_value"].sum()
    dead_stock_table = dead_stock[["product_name", "days_without_sale", "cost", "stock_value"]].copy()
    dead_stock_table = dead_stock_table.sort_values("stock_value", ascending=False).head(15)
    
    # ========== RISCO DE RUPTURA (< 15 dias de cobertura, com estoque > 0) ==========
    rupture_risk = merged[
        (merged["coverage_days"] < 30) & 
        (merged["saldo"] > 0) &
        (merged["daily_qty"] > 0)
    ].copy()
    
    # Adicionar product_name (verificar se existe em products_df)
    if "product_name" not in rupture_risk.columns:
        if "product_name" in products_df.columns:
            rupture_risk = rupture_risk.merge(products_df[["sku", "product_name"]], on="sku", how="left")
            rupture_risk["product_name"] = rupture_risk["product_name"].fillna(rupture_risk["sku"])
        else:
            rupture_risk["product_name"] = rupture_risk["sku"]
    
    rupture_table = rupture_risk[["product_name", "saldo", "daily_qty", "coverage_days"]].copy()
    rupture_table = rupture_table.sort_values("coverage_days", ascending=True).head(15)
    
    # ========== ABC POR VALOR DE ESTOQUE ==========
    abc_stock = scatter.groupby("abc")["stock_value"].sum().reset_index()
    abc_stock = abc_stock.rename(columns={"stock_value": "value"})
    # Garantir que todas as categorias existam
    for cat in ["A", "B", "C"]:
        if cat not in abc_stock["abc"].values:
            abc_stock = pd.concat([abc_stock, pd.DataFrame({"abc": [cat], "value": [0]})], ignore_index=True)

    # ========== RELATÓRIO ABC PARA EXPORTAÇÃO ==========
    def _classify_strategic_status(row):
        """Classifica o status estratégico de cada produto"""
        abc = row.get("abc", "C")
        days_without = row.get("days_without_sale", 0)
        stock_val = row.get("stock_value", 0)
        saldo = row.get("saldo", 0)
        
        if saldo == 0:
            return "🚨 Ruptura"
        elif abc == "A" and days_without < 30:
            return "💎 Produto Herói"
        elif days_without > 90 and stock_val > 500:
            return "💀 Estoque Morto (Crítico)"
        elif days_without > 90:
            return "🐢 Estoque Lento"
        else:
            return "📦 Normal"
    
    # Criar DataFrame de exportação enriquecido
    export_df = scatter.copy()
    export_df["status_estrategico"] = export_df.apply(_classify_strategic_status, axis=1)
    
    # Selecionar e renomear colunas para exportação
    export_columns = {
        "sku": "SKU",
        "product_name": "Nome do Produto",
        "cost": "Preço Custo (R$)",
        "saldo": "Saldo em Estoque",
        "stock_value": "Valor Total Travado (R$)",
        "days_without_sale": "Dias sem Venda",
        "abc": "Classificação ABC",
        "status_estrategico": "Área / Status",
    }
    
    # Garantir que todas as colunas existam
    for col in export_columns.keys():
        if col not in export_df.columns:
            export_df[col] = 0 if col in ["cost", "saldo", "stock_value", "days_without_sale"] else "N/A"
    
    abc_export = export_df[list(export_columns.keys())].copy()
    abc_export = abc_export.rename(columns=export_columns)
    abc_export = abc_export.sort_values("Valor Total Travado (R$)", ascending=False)

    return {
        "total_stock_value": total_stock_value,
        "avg_coverage": avg_coverage,
        "items_rupture": items_rupture,
        "rupture_pct": rupture_pct,
        "dead_stock_value": dead_stock_value,
        "purchase_table": merged,
        "scatter": scatter,
        "rupture_table": rupture_table,
        "dead_stock_table": dead_stock_table,
        "abc_stock": abc_stock,
        "abc_export": abc_export,
    }


def build_sales_performance(
    orders_df: pd.DataFrame,
    products_df: pd.DataFrame,
) -> Dict[str, object]:
    orders = orders_df.copy()
    orders = _ensure_datetime(orders, "created_at")
    orders = orders[orders["created_at"].notna()]
    orders["status"] = orders.get("status", "").astype(str).str.lower()
    orders = orders[orders["status"] != "cancelado"]
    orders["total"] = pd.to_numeric(orders.get("total", 0), errors="coerce").fillna(0.0)
    orders["qty"] = pd.to_numeric(orders.get("qty", 0), errors="coerce").fillna(0.0)

    # ========== KPIs GERAIS ==========
    total_revenue = orders["total"].sum()
    total_orders = orders.shape[0]
    
    # Share por canal
    share = orders.groupby("channel")["total"].sum().reset_index().rename(columns={"total": "revenue"})
    share["pct"] = (share["revenue"] / max(share["revenue"].sum(), 1)) * 100
    
    # Melhor canal
    if not share.empty:
        best_channel_row = share.loc[share["revenue"].idxmax()]
        best_channel = best_channel_row["channel"]
        best_channel_pct = best_channel_row["pct"]
    else:
        best_channel = "N/A"
        best_channel_pct = 0.0

    # ========== RECORRÊNCIA ==========
    classified = classify_customer_recurrence(orders)
    
    # Contagem de pedidos por tipo de cliente
    recurrence_counts = classified.groupby("customer_type").size()
    total_recurrent = recurrence_counts.get("Recorrentes", 0)
    recurrence_rate = _safe_div(total_recurrent, total_orders) * 100
    
    # Cohort diário (Novos vs Recorrentes)
    daily_cohort = (
        classified.groupby([classified["created_at"].dt.date, "customer_type"])["total"]
        .sum()
        .reset_index()
        .rename(columns={"created_at": "date", "total": "revenue"})
    )

    # ========== EVOLUÇÃO POR CANAL (Linha temporal) ==========
    orders["date"] = orders["created_at"].dt.date
    channel_evolution = (
        orders.groupby(["date", "channel"])["total"]
        .sum()
        .reset_index()
        .rename(columns={"total": "revenue"})
    )

    # ========== MARGEM E LUCRO ==========
    margin = calculate_margin(orders, products_df)
    total_cost = (margin["revenue"] - margin["margin"]).sum()
    operational_profit = margin["margin"].sum()
    
    # Calcular margem % por produto
    margin["margin_pct"] = margin.apply(
        lambda row: _safe_div(row["margin"], row["revenue"]) * 100, axis=1
    )
    
    # Identificar canal principal de cada produto
    product_channel = (
        orders.groupby(["sku", "channel"])["total"]
        .sum()
        .reset_index()
    )
    product_channel = product_channel.loc[
        product_channel.groupby("sku")["total"].idxmax()
    ][["sku", "channel"]].rename(columns={"channel": "main_channel"})
    
    # Merge com dados de margem
    margin = margin.merge(product_channel, on="sku", how="left")
    margin["main_channel"] = margin["main_channel"].fillna("N/A")
    
    # Calcular preço médio e custo médio
    orders_with_cost = orders.merge(products_df[["sku", "cost"]], on="sku", how="left")
    orders_with_cost["cost"] = pd.to_numeric(orders_with_cost["cost"], errors="coerce").fillna(0.0)
    
    price_cost = orders_with_cost.groupby("sku").agg(
        avg_price=("total", lambda x: _safe_div(x.sum(), orders_with_cost.loc[x.index, "qty"].sum())),
        unit_cost=("cost", "first")
    ).reset_index()
    
    margin = margin.merge(price_cost, on="sku", how="left")
    margin = margin.sort_values("margin", ascending=False).head(15)

    return {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "best_channel": best_channel,
        "best_channel_pct": best_channel_pct,
        "recurrence_rate": recurrence_rate,
        "operational_profit": operational_profit,
        "share": share,
        "recurrence": daily_cohort,
        "channel_evolution": channel_evolution,
        "top_margin": margin,
    }


def generate_mock_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = datetime.now()
    products = []
    for i in range(12):
        products.append({
            "sku": f"SKU{i}",
            "product_name": f"Produto {i}",
            "cost": 20 + (i * 3),
        })

    orders = []
    for i in range(120):
        orders.append(
            {
                "order_id": f"PED-{1000 + i}",
                "created_at": base - timedelta(days=i % 45),
                "total": 800 + (i * 15),
                "status": "pago" if i % 10 else "em aberto",
                "channel": ["Mercado Livre", "Shopee", "Site Próprio"][i % 3],
                "sku": f"SKU{i % 12}",
                "product_name": f"Produto {i % 12}",
                "qty": 1 + (i % 4),
                "customer_id": f"CPF{i % 20}",
            }
        )

    stock = []
    for i in range(12):
        stock.append({
            "sku": f"SKU{i}",
            "product_name": f"Produto {i}",
            "saldo": 50 - i * 3,
            "cost": 20 + (i * 3),
        })

    return pd.DataFrame(orders), pd.DataFrame(stock), pd.DataFrame(products)
