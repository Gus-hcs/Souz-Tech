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

    return {
        "revenue_30": revenue_30,
        "delta": delta,
        "ticket": ticket,
        "gross_profit": gross_profit,
        "locked": locked,
        "locked_details": locked_details,
        "daily": daily,
        "rupture_count": rupture.shape[0],
        "dead_value": dead_value,
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

    recency = calculate_days_without_sale(orders, products_df)
    abc_base = orders.groupby("sku")["total"].sum().reset_index().rename(columns={"total": "revenue"})
    abc = _classify_abc(abc_base)

    scatter = merged.merge(recency[["sku", "days_without_sale"]], on="sku", how="left")
    scatter = scatter.merge(abc[["sku", "abc"]], on="sku", how="left")
    
    # Remove product_name from merged to avoid duplicate columns
    if "product_name" in scatter.columns:
        scatter = scatter.drop(columns=["product_name"])
    
    scatter = scatter.merge(products_df[["sku", "product_name"]], on="sku", how="left")

    rupture_pct = _safe_div((merged["saldo"] == 0).sum(), merged.shape[0]) * 100

    return {
        "purchase_table": merged,
        "scatter": scatter,
        "rupture_pct": rupture_pct,
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

    share = orders.groupby("channel")["total"].sum().reset_index().rename(columns={"total": "revenue"})

    classified = classify_customer_recurrence(orders)
    daily = (
        classified.groupby([classified["created_at"].dt.date, "customer_type"])["total"]
        .sum()
        .reset_index()
        .rename(columns={"created_at": "date", "total": "revenue"})
    )

    margin = calculate_margin(orders, products_df)
    margin = margin.sort_values("margin", ascending=False).head(10)

    return {
        "share": share,
        "recurrence": daily,
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
