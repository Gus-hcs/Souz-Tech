from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from services.analytics_service import (
    build_finance_kpis,
    build_inventory_kpis,
    build_sales_kpis,
    generate_mock_data,
)
from services.auth_service import logout
from services.bling_service import BlingAuthError, ensure_valid_token


def render_sales_view() -> None:
    st.markdown(
        """
        <style>
        .metric-card {
            background-color: #1E1E1E;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            margin-bottom: 15px;
        }
        .metric-title {
            color: #A0A0A0;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 5px;
        }
        .metric-value {
            color: #FFFFFF;
            font-size: 28px;
            font-weight: bold;
        }
        .metric-delta {
            font-size: 14px;
            font-weight: bold;
        }
        .positive { color: #00CC96; }
        .negative { color: #EF553B; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    receita_total = 1960560.20
    mom_delta = 0.12
    yoy_delta = 0.34
    ticket_medio = 215.90
    conversao = 0.084

    kpi_cols = st.columns(3)
    with kpi_cols[0]:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Receita Total</div>
                <div class="metric-value">R$ {receita_total:,.2f}</div>
                <div class="metric-delta positive">↑ {mom_delta*100:.1f}% MoM • ↑ {yoy_delta*100:.1f}% YoY</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with kpi_cols[1]:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Ticket Médio</div>
                <div class="metric-value">R$ {ticket_medio:,.2f}</div>
                <div class="metric-delta positive">↑ Consistência mensal</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with kpi_cols[2]:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Taxa de Conversão</div>
                <div class="metric-value">{conversao*100:.1f}%</div>
                <div class="metric-delta positive">↑ Leads qualificados</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    row2 = st.columns([1, 2])
    with row2[0]:
        fig_gauge = go.Figure(
            go.Indicator(
                mode="gauge+number+delta",
                value=75000,
                delta={"reference": 100000, "increasing": {"color": "#00CC96"}},
                gauge={"axis": {"range": [0, 100000]}, "bar": {"color": "#2563EB"}},
                title={"text": "Vendas vs Meta"},
            )
        )
        fig_gauge.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#E0E0E0"},
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with row2[1]:
        ticket_df = px.data.tips()
        ticket_df = ticket_df.groupby("day")["total_bill"].mean().reset_index()
        ticket_df = ticket_df.rename(columns={"day": "canal", "total_bill": "ticket"})
        ticket_df["canal"] = ["Mercado Livre", "Shopee", "Site Próprio", "Outros"][: len(ticket_df)]
        fig_ticket = px.bar(ticket_df, x="canal", y="ticket", template="plotly_dark")
        fig_ticket.update_layout(
            title="Ticket Médio por Canal",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#E0E0E0"},
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.plotly_chart(fig_ticket, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    row3 = st.columns([1, 1])
    with row3[0]:
        funnel_df = px.data.tips()
        funnel_df = funnel_df.head(4)
        funnel_df["stage"] = [
            "Orçamentos Criados",
            "Em Negociação",
            "Aguardando Pagamento",
            "Pedido Faturado",
        ]
        funnel_df["value"] = [1200, 860, 540, 420]
        fig_funnel = px.funnel(funnel_df, x="value", y="stage", template="plotly_dark")
        fig_funnel.update_layout(
            title="Funil de Vendas",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#E0E0E0"},
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.plotly_chart(fig_funnel, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with row3[1]:
        map_df = px.data.gapminder().query("year == 2007")
        map_df = map_df[map_df["continent"] == "Americas"].head(10)
        map_df = map_df.assign(
            state=["SP", "RJ", "MG", "PR", "RS", "SC", "BA", "GO", "PE", "CE"],
            lat=[-23.5, -22.9, -19.9, -25.4, -30.0, -27.6, -12.9, -16.6, -8.0, -3.7],
            lon=[-46.6, -43.2, -43.9, -49.3, -51.2, -48.5, -38.5, -49.3, -34.9, -38.5],
            sales=[120, 95, 80, 70, 65, 60, 55, 50, 45, 40],
        )
        fig_map = px.scatter_geo(
            map_df,
            lat="lat",
            lon="lon",
            size="sales",
            hover_name="state",
            scope="south america",
            template="plotly_dark",
        )
        fig_map.update_layout(
            title="Vendas por Estado",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#E0E0E0"},
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.plotly_chart(fig_map, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.markdown("**Top 10 Produtos (Pareto)**")
    top_products = {
        "Produto": [f"Produto {i}" for i in range(1, 11)],
        "Receita Gerada": [98000, 86000, 74000, 62000, 54000, 48000, 42000, 36000, 32000, 28000],
    }
    top_df = px.data.tips().head(10)
    top_df = top_df.assign(**top_products)
    st.dataframe(
        top_df[["Produto", "Receita Gerada"]],
        width="stretch",
        column_config={
            "Receita Gerada": st.column_config.ProgressColumn(
                "Receita Gerada",
                min_value=0,
                max_value=max(top_products["Receita Gerada"]),
                format="R$ %d",
            )
        },
    )
    st.markdown('</div>', unsafe_allow_html=True)


def render_client(session, client) -> None:
    st.markdown(
        """
        <style>
            #MainMenu, footer, header {visibility: hidden;}
            div[data-testid="stAppViewContainer"] {background: #0f1115; color: #E0E0E0;}
            section.main {padding-top: 1rem;}
            .card {
                background: #1E1E1E;
                border-radius: 12px;
                padding: 20px;
                border: 1px solid #2A2A2A;
                box-shadow: 0 4px 10px rgba(0,0,0,0.4);
                margin-bottom: 20px;
            }
            .kpi-title {
                font-size: 0.85rem;
                color: #A0A0A0;
                margin-bottom: 6px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .kpi-value {
                font-size: 1.8rem;
                font-weight: 700;
                color: #E0E0E0;
            }
            .kpi-delta {
                font-size: 0.85rem;
                color: #10B981;
                margin-top: 6px;
            }
            .section-title {
                font-size: 1.1rem;
                font-weight: 600;
                color: #E0E0E0;
                margin-bottom: 12px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Dashboard do Cliente")

    if st.button("Sair"):
        logout()
        st.rerun()

    token_error = st.session_state.pop("token_error", None)
    if token_error:
        st.error(token_error)

    try:
        ensure_valid_token(client, session)
    except BlingAuthError:
        st.error("Token Bling expirado. Contate o suporte para reautenticar.")

    st.write(f"Loja: **{client.company_name}**")

    orders_df, stock_df, ar_df, ap_df = generate_mock_data()
    sales_kpis = build_sales_kpis(orders_df)
    inventory_kpis = build_inventory_kpis(stock_df, orders_df)
    finance_kpis = build_finance_kpis(ar_df, ap_df)

    tabs = []
    tab_keys = []
    if client.plan_sales:
        tabs.append("Vendas")
        tab_keys.append("sales")
    if client.plan_inventory:
        tabs.append("Estoque")
        tab_keys.append("inventory")
    if client.plan_financial:
        tabs.append("Financeiro")
        tab_keys.append("financial")

    if not tabs:
        st.info("Este módulo não está incluso no seu plano. Contate o suporte para upgrade.")
        return

    tab_objs = st.tabs(tabs)
    for index, key in enumerate(tab_keys):
        with tab_objs[index]:
            if key == "sales":
                render_sales_view()
            elif key == "inventory":
                st.subheader("Supply Chain")
                if inventory_kpis.get("empty"):
                    st.info("Dados insuficientes para calcular este indicador.")
                    continue
                st.markdown(
                    f"""
                    <div class="card">
                        <div class="kpi-title">Valor em Estoque (Custo)</div>
                        <div class="kpi-value">R$ {inventory_kpis['stock_value']:,.2f}</div>
                        <div class="kpi-delta">Capital imobilizado</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                grid = st.columns(2)
                with grid[0]:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown('<div class="section-title">Risco de Ruptura</div>', unsafe_allow_html=True)
                    st.dataframe(inventory_kpis["rupture"], width="stretch")
                    st.markdown('</div>', unsafe_allow_html=True)
                with grid[1]:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown('<div class="section-title">Estoque Morto</div>', unsafe_allow_html=True)
                    st.dataframe(inventory_kpis["dead_stock"], width="stretch")
                    st.markdown('</div>', unsafe_allow_html=True)
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">Curva ABC</div>', unsafe_allow_html=True)
                st.dataframe(inventory_kpis["abc"], width="stretch")
                st.markdown('</div>', unsafe_allow_html=True)
            elif key == "financial":
                st.subheader("Financeiro")
                if finance_kpis.get("empty"):
                    st.info("Dados insuficientes para calcular este indicador.")
                    continue
                st.markdown(
                    f"""
                    <div class="card">
                        <div class="kpi-title">Inadimplência</div>
                        <div class="kpi-value">{finance_kpis['inadimplencia']:.1f}%</div>
                        <div class="kpi-delta">Últimos vencimentos</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                projected = finance_kpis["projected"]
                if not projected.empty:
                    fig_cash = px.bar(
                        projected,
                        x="due_date",
                        y="amount",
                        color="type",
                        template="plotly_dark",
                        barmode="group",
                    )
                    fig_cash.update_layout(
                        title="Fluxo de Caixa Projetado",
                        margin=dict(l=0, r=0, t=40, b=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#E0E0E0",
                    )
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.plotly_chart(fig_cash, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
