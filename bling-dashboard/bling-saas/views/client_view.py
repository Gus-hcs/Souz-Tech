from __future__ import annotations

from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from services.analytics_service import (
    build_commander_kpis,
    build_inventory_intelligence,
    build_sales_performance,
    generate_mock_data,
)
from services.auth_service import logout
from services.bling_service import BlingAuthError, ensure_valid_token


def _apply_dark_layout(fig, title: str | None = None):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#E0E0E0"},
        margin=dict(l=20, r=20, t=40, b=20),
        title=title or "",
    )
    return fig


def _kpi_card(title: str, value: str, delta: str, delta_class: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-delta {delta_class}">{delta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_client(session, client) -> None:
    st.markdown(
        """
        <style>
            #MainMenu, footer, header {visibility: hidden;}
            div[data-testid="stAppViewContainer"] {background: #0E1117; color: #FAFAFA;}
            section.main {padding-top: 1rem;}
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
            .warning { color: #F59E0B; }
            .card {
                background: #1E1E1E;
                border-radius: 12px;
                padding: 20px;
                border: 1px solid #2A2A2A;
                box-shadow: 0 4px 10px rgba(0,0,0,0.4);
                margin-bottom: 20px;
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

    st.title("Centro de Comando")

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
    active_modules = []
    if client.access_commander:
        active_modules.append("🏠")
    if client.access_inventory:
        active_modules.append("📦")
    if client.access_performance:
        active_modules.append("💰")
    st.caption("Módulos: " + (" ".join(active_modules) if active_modules else "Nenhum módulo habilitado"))

    orders_df, stock_df, products_df = generate_mock_data()
    commander = build_commander_kpis(orders_df, products_df, stock_df)
    inventory = build_inventory_intelligence(orders_df, products_df, stock_df)
    sales_perf = build_sales_performance(orders_df, products_df)

    modules: list[tuple[str, str]] = []
    if client.access_commander:
        modules.append(("🏠 Visão do Comandante", "commander"))
    if client.access_inventory:
        modules.append(("📦 Inteligência de Estoque", "inventory"))
    if client.access_performance:
        modules.append(("💰 Performance de Vendas", "performance"))

    if not modules:
        st.warning("Sua conta está ativa, mas nenhum módulo foi habilitado. Contate o suporte.")
        return

    tabs = st.tabs([title for title, _ in modules])

    for tab, (_, key) in zip(tabs, modules):
        with tab:
            if key == "commander":
                delta_class = "positive" if commander["delta"] >= 0 else "negative"
                kpi_cols = st.columns(4)
                with kpi_cols[0]:
                    _kpi_card(
                        "Faturamento (30d)",
                        f"R$ {commander['revenue_30']:,.2f}",
                        f"{'↑' if commander['delta'] >= 0 else '↓'} {abs(commander['delta']):.1f}% vs período anterior",
                        delta_class,
                    )
                with kpi_cols[1]:
                    _kpi_card("Ticket Médio", f"R$ {commander['ticket']:,.2f}", "Consistência de vendas", "positive")
                with kpi_cols[2]:
                    _kpi_card(
                        "Lucro Bruto (Estimado)",
                        f"R$ {commander['gross_profit']:,.2f}",
                        "Margem sobre custos",
                        "positive",
                    )
                with kpi_cols[3]:
                    _kpi_card(
                        "Pedidos Travados",
                        f"{commander['locked']}",
                        "Atenção imediata",
                        "warning",
                    )

                # Gráfico de barras + linha (últimos 90 dias)
                daily = commander["daily"].copy()
                
                fig = go.Figure()
                
                # Adicionar barras (faturamento atual)
                fig.add_trace(go.Bar(
                    x=daily["date"],
                    y=daily["revenue_current"],
                    name="Faturamento Atual",
                    marker_color="#00CC96",
                    opacity=0.8,
                ))
                
                # Adicionar linha (faturamento do mesmo dia no mês anterior)
                fig.add_trace(go.Scatter(
                    x=daily["date"],
                    y=daily["revenue_prev"],
                    name="Mesmo Dia (90 dias atrás)",
                    mode="lines",
                    line=dict(color="#F59E0B", width=2, dash="dash"),
                    yaxis="y2",
                ))
                
                # Configurar layout com dois eixos Y
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    title=dict(text="Faturamento Diário (Últimos 90 dias)", font=dict(color="#E0E0E0", size=16)),
                    xaxis=dict(
                        title="Data",
                        gridcolor="#2A2A2A",
                        color="#E0E0E0",
                    ),
                    yaxis=dict(
                        title="Faturamento Atual (R$)",
                        gridcolor="#2A2A2A",
                        color="#E0E0E0",
                    ),
                    yaxis2=dict(
                        title="Comparação (R$)",
                        overlaying="y",
                        side="right",
                        color="#F59E0B",
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1,
                        font=dict(color="#E0E0E0"),
                    ),
                    hovermode="x unified",
                )
                
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.plotly_chart(fig, width='stretch', key='chart_daily_revenue')
                st.markdown('</div>', unsafe_allow_html=True)

                # Alertas e Relatório de Pedidos Travados
                col_alert1, col_alert2 = st.columns(2)
                
                with col_alert1:
                    if commander["rupture_count"] > 0:
                        st.error(f"🚨 {commander['rupture_count']} produtos principais acabam essa semana.")
                
                with col_alert2:
                    if commander["dead_value"] > 0:
                        st.warning(f"⚠️ R$ {commander['dead_value']:,.2f} parados no estoque.")
                
                # Botão e relatório de pedidos travados
                if commander["locked"] > 0:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown('<div class="section-title">⚠️ Pedidos Travados - Atenção Imediata</div>', unsafe_allow_html=True)
                    
                    with st.expander(f"📋 Ver Relatório Detalhado ({commander['locked']} pedidos)", expanded=False):
                        locked_details = commander["locked_details"].copy()
                        
                        # Formatar dados para exibição
                        locked_details["created_at"] = pd.to_datetime(locked_details["created_at"]).dt.strftime("%d/%m/%Y")
                        locked_details = locked_details.rename(columns={
                            "order_id": "Nº Pedido",
                            "total": "Valor (R$)",
                            "status": "Status",
                            "created_at": "Data",
                        })
                        
                        # Calcular total
                        total_travado = locked_details["Valor (R$)"].sum()
                        
                        st.dataframe(
                            locked_details,
                            width="stretch",
                            column_config={
                                "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                            },
                        )
                        
                        st.metric("💰 Valor Total Travado", f"R$ {total_travado:,.2f}")
                        
                        # Botão de download Excel
                        buffer = BytesIO()
                        with buffer:
                            locked_details.to_excel(buffer, index=False, sheet_name="Pedidos Travados", engine="openpyxl")
                            buffer.seek(0)
                            st.download_button(
                                label="📥 Baixar Relatório em Excel",
                                data=buffer,
                                file_name="pedidos_travados.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                    
                    st.markdown('</div>', unsafe_allow_html=True)

            elif key == "inventory":
                _kpi_card("% de Ruptura", f"{inventory['rupture_pct']:.1f}%", "SKUs ativos sem saldo", "warning")

                purchase = inventory["purchase_table"].copy()
                purchase = purchase[["sku", "product_name", "saldo", "daily_qty", "coverage_days", "status"]]
                purchase = purchase.rename(
                    columns={
                        "sku": "SKU",
                        "product_name": "Nome",
                        "saldo": "Estoque Atual",
                        "daily_qty": "Giro Diário",
                        "coverage_days": "Dias de Cobertura",
                        "status": "Status",
                    }
                )
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">Sugestão de Compra</div>', unsafe_allow_html=True)
                
                # Botão de download Excel
                buffer = BytesIO()
                with buffer:
                    purchase.to_excel(buffer, index=False, sheet_name="Lista de Reposição", engine="openpyxl")
                    buffer.seek(0)
                    st.download_button(
                        label="📥 Baixar Lista de Reposição em Excel",
                        data=buffer,
                        file_name="lista_reposicao.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

                    )
                
                st.dataframe(
                    purchase,
                    width="stretch",
                    column_config={
                        "Dias de Cobertura": st.column_config.NumberColumn(format="%.1f"),
                        "Giro Diário": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
                st.markdown('</div>', unsafe_allow_html=True)

                scatter = inventory["scatter"].copy()
                fig_scatter = px.scatter(
                    scatter,
                    x="days_without_sale",
                    y="stock_value",
                    color="abc",
                    hover_name="product_name",
                    color_discrete_map={"A": "#10B981", "B": "#F59E0B", "C": "#EF4444"},
                )
                fig_scatter = _apply_dark_layout(fig_scatter, "Curva ABC vs Estoque (Cemitério no quadrante superior direito)")
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.plotly_chart(fig_scatter, width='stretch', key='chart_abc_scatter')
                st.markdown('</div>', unsafe_allow_html=True)

            elif key == "performance":
                share = sales_perf["share"]
                fig_share = px.pie(share, values="revenue", names="channel", hole=0.5)
                fig_share = _apply_dark_layout(fig_share, "Share de Canais")
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.plotly_chart(fig_share, width='stretch', key='chart_channel_share')
                st.markdown('</div>', unsafe_allow_html=True)

                recurrence = sales_perf["recurrence"]
                fig_rec = px.bar(recurrence, x="date", y="revenue", color="customer_type", barmode="stack")
                fig_rec = _apply_dark_layout(fig_rec, "Cohort Diário: Novos vs Recorrentes")
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.plotly_chart(fig_rec, width='stretch', key='chart_recurrence')
                st.markdown('</div>', unsafe_allow_html=True)

                top_margin = sales_perf["top_margin"].copy()
                # Verificar se product_name existe, senão usar sku
                if "product_name" not in top_margin.columns:
                    if "sku" in top_margin.columns:
                        top_margin["product_name"] = top_margin["sku"]
                    else:
                        top_margin["product_name"] = "N/A"
                
                top_margin = top_margin[["product_name", "qty_sold", "revenue", "margin"]]
                top_margin = top_margin.rename(
                    columns={
                        "product_name": "Produto",
                        "qty_sold": "Qtd Vendida",
                        "revenue": "Faturamento",
                        "margin": "Lucro Real",
                    }
                )
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">Top Produtos por Margem</div>', unsafe_allow_html=True)
                st.dataframe(
                    top_margin,
                    width="stretch",
                    column_config={
                        "Faturamento": st.column_config.NumberColumn(format="R$ %.2f"),
                        "Lucro Real": st.column_config.NumberColumn(format="R$ %.2f"),
                    },
                )
            st.markdown('</div>', unsafe_allow_html=True)
