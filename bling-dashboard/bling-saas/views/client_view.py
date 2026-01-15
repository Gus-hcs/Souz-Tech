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
                # ========== LINHA 1: KPIs (4 Big Numbers) ==========
                delta_class = "positive" if commander["delta"] >= 0 else "negative"
                delta_arrow = "▲" if commander["delta"] >= 0 else "▼"
                
                kpi_cols = st.columns(4)
                with kpi_cols[0]:
                    _kpi_card(
                        "💵 Faturamento (30d)",
                        f"R$ {commander['revenue_30']:,.2f}",
                        f"{delta_arrow} {abs(commander['delta']):.1f}% vs mês anterior",
                        delta_class,
                    )
                with kpi_cols[1]:
                    _kpi_card(
                        "📈 Lucro Bruto",
                        f"R$ {commander['gross_profit']:,.2f}",
                        "Receita - Custo dos Produtos",
                        "positive" if commander['gross_profit'] > 0 else "negative",
                    )
                with kpi_cols[2]:
                    _kpi_card(
                        "🎯 Ticket Médio",
                        f"R$ {commander['ticket']:,.2f}",
                        "Valor médio por pedido",
                        "positive",
                    )
                with kpi_cols[3]:
                    locked_class = "warning" if commander['locked'] > 0 else "positive"
                    _kpi_card(
                        "⏳ Pedidos Pendentes",
                        f"{commander['locked']}",
                        "Em aberto ou atrasados",
                        locked_class,
                    )

                # ========== LINHA 2: Gráfico de Tendência (100% width) ==========
                st.markdown('<div class="card">', unsafe_allow_html=True)
                
                daily_30 = commander["daily_30"].copy()
                avg_prev = commander["avg_prev_daily"]
                
                fig_trend = go.Figure()
                
                # Área preenchida do faturamento
                fig_trend.add_trace(go.Scatter(
                    x=daily_30["date"],
                    y=daily_30["revenue"],
                    name="Faturamento",
                    mode="lines",
                    fill="tozeroy",
                    fillcolor="rgba(0, 204, 150, 0.2)",
                    line=dict(color="#00CC96", width=2.5),
                    hovertemplate="<b>%{x}</b><br>R$ %{y:,.2f}<extra></extra>",
                ))
                
                # Linha de referência (média do mês anterior)
                if avg_prev > 0:
                    fig_trend.add_hline(
                        y=avg_prev,
                        line_dash="dash",
                        line_color="#6B7280",
                        line_width=1.5,
                        annotation_text=f"Média Anterior: R$ {avg_prev:,.0f}",
                        annotation_position="top right",
                        annotation_font=dict(color="#9CA3AF", size=10),
                    )
                
                fig_trend.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=30, l=10, r=10, b=10),
                    title=dict(
                        text="📊 Evolução do Faturamento (Últimos 30 dias)",
                        font=dict(color="#E0E0E0", size=14),
                    ),
                    xaxis=dict(
                        title="",
                        gridcolor="#2A2A2A",
                        color="#A0A0A0",
                        showgrid=False,
                    ),
                    yaxis=dict(
                        title="",
                        gridcolor="#2A2A2A",
                        color="#A0A0A0",
                    ),
                    showlegend=False,
                    hovermode="x unified",
                    height=300,
                )
                
                st.plotly_chart(fig_trend, use_container_width=True, key='chart_revenue_trend')
                st.markdown('</div>', unsafe_allow_html=True)

                # ========== LINHA 3: Pedidos Pendentes (Tabela completa) ==========
                if commander["locked"] > 0:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown('<div class="section-title">⏳ Pedidos Pendentes - Ação Necessária</div>', unsafe_allow_html=True)
                    
                    with st.expander(f"📋 Ver Detalhes ({commander['locked']} pedidos)", expanded=True):
                        locked_details = commander["locked_details"].copy()
                        locked_details["created_at"] = pd.to_datetime(locked_details["created_at"]).dt.strftime("%d/%m/%Y")
                        locked_details = locked_details.rename(columns={
                            "order_id": "Nº Pedido",
                            "total": "Valor (R$)",
                            "status": "Status",
                            "created_at": "Data",
                        })
                        
                        total_travado = locked_details["Valor (R$)"].sum()
                        
                        col_metric, col_table = st.columns([1, 3])
                        with col_metric:
                            st.metric("💰 Valor Total", f"R$ {total_travado:,.2f}")
                        
                        with col_table:
                            st.dataframe(
                                locked_details,
                                use_container_width=True,
                                column_config={
                                    "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                                },
                                hide_index=True,
                                height=300,
                            )
                        
                        buffer = BytesIO()
                        locked_details.to_excel(buffer, index=False, sheet_name="Pedidos Travados", engine="openpyxl")
                        buffer.seek(0)
                        st.download_button(
                            label="📥 Baixar Relatório Excel",
                            data=buffer.getvalue(),
                            file_name="pedidos_travados.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    
                    st.markdown('</div>', unsafe_allow_html=True)

            elif key == "inventory":
                # ========== LINHA 1: KPIs (4 Cards) ==========
                kpi_cols = st.columns(4)
                with kpi_cols[0]:
                    _kpi_card(
                        "💰 Valor em Estoque",
                        f"R$ {inventory['total_stock_value']:,.2f}",
                        "Capital imobilizado (custo)",
                        "positive",
                    )
                with kpi_cols[1]:
                    _kpi_card(
                        "📅 Cobertura Média",
                        f"{inventory['avg_coverage']:.0f} dias",
                        "Média ponderada por valor",
                        "positive" if inventory['avg_coverage'] > 30 else "warning",
                    )
                with kpi_cols[2]:
                    _kpi_card(
                        "🚨 Itens em Ruptura",
                        f"{inventory['items_rupture']}",
                        f"{inventory['rupture_pct']:.1f}% do catálogo",
                        "negative" if inventory['items_rupture'] > 0 else "positive",
                    )
                with kpi_cols[3]:
                    _kpi_card(
                        "💀 Dinheiro Parado",
                        f"R$ {inventory['dead_stock_value']:,.2f}",
                        "Sem venda há +90 dias",
                        "negative" if inventory['dead_stock_value'] > 1000 else "warning",
                    )

                # ========== LINHA 2: Matriz Estratégica (70% | 30%) ==========
                col_scatter, col_abc = st.columns([7, 3])
                
                with col_scatter:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    scatter = inventory["scatter"].copy()
                    
                    fig_scatter = px.scatter(
                        scatter,
                        x="days_without_sale",
                        y="stock_value",
                        color="abc",
                        size="saldo",
                        size_max=40,
                        hover_name="product_name",
                        hover_data={
                            "days_without_sale": True,
                            "stock_value": ":.2f",
                            "saldo": True,
                            "abc": True,
                        },
                        color_discrete_map={"A": "#10B981", "B": "#F59E0B", "C": "#EF4444"},
                        labels={
                            "days_without_sale": "Dias sem Venda",
                            "stock_value": "Valor em Estoque (R$)",
                            "abc": "Curva ABC",
                            "saldo": "Saldo Físico",
                        },
                    )
                    
                    # Adicionar quadrantes visuais com anotações
                    fig_scatter.add_annotation(
                        x=0.95, y=0.95, xref="paper", yref="paper",
                        text="💀 Cemitério",
                        showarrow=False,
                        font=dict(size=12, color="#EF4444"),
                        bgcolor="rgba(239,68,60,0.15)",
                        borderpad=4,
                    )
                    fig_scatter.add_annotation(
                        x=0.05, y=0.95, xref="paper", yref="paper",
                        text="⭐ Heróis",
                        showarrow=False,
                        font=dict(size=12, color="#10B981"),
                        bgcolor="rgba(16,185,129,0.15)",
                        borderpad=4,
                    )
                    
                    fig_scatter.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(t=40, l=10, r=10, b=10),
                        title=dict(
                            text="🎯 Matriz de Saúde do Estoque",
                            font=dict(color="#E0E0E0", size=14),
                        ),
                        xaxis=dict(
                            title="Dias sem Venda (Recência)",
                            gridcolor="#2A2A2A",
                            color="#A0A0A0",
                        ),
                        yaxis=dict(
                            title="Valor em Estoque (R$)",
                            gridcolor="#2A2A2A",
                            color="#A0A0A0",
                        ),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1,
                            font=dict(color="#E0E0E0", size=10),
                            title="",
                        ),
                        height=380,
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True, key='chart_inventory_scatter')
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col_abc:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    abc_stock = inventory["abc_stock"]
                    total_abc = abc_stock["value"].sum()
                    
                    fig_abc = go.Figure(data=[go.Pie(
                        labels=abc_stock["abc"],
                        values=abc_stock["value"],
                        hole=0.6,
                        marker=dict(colors=["#10B981", "#F59E0B", "#EF4444"]),
                        textinfo="label+percent",
                        textposition="outside",
                        textfont=dict(color="#E0E0E0", size=11),
                        hovertemplate="<b>Curva %{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
                        sort=False,
                    )])
                    
                    fig_abc.add_annotation(
                        text=f"<b>R$ {total_abc:,.0f}</b><br><span style='font-size:10px;color:#A0A0A0'>Total</span>",
                        x=0.5, y=0.5,
                        font=dict(size=14, color="#FFFFFF"),
                        showarrow=False,
                    )
                    
                    fig_abc.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(t=40, l=10, r=10, b=10),
                        title=dict(
                            text="📊 Distribuição ABC (Valor)",
                            font=dict(color="#E0E0E0", size=14),
                        ),
                        showlegend=False,
                        height=380,
                    )
                    st.plotly_chart(fig_abc, use_container_width=True, key='chart_abc_donut')
                    st.markdown('</div>', unsafe_allow_html=True)

                # ========== BOTÃO DE EXPORTAÇÃO ABC ==========
                st.markdown('<div class="card">', unsafe_allow_html=True)
                col_export_info, col_export_btn = st.columns([3, 1])
                
                with col_export_info:
                    st.markdown(
                        """
                        <div style="padding: 10px 0;">
                            <div style="font-size: 14px; font-weight: bold; color: #E0E0E0;">📊 Relatório de Inteligência ABC</div>
                            <div style="font-size: 12px; color: #9CA3AF;">Exporta todos os produtos com classificação ABC, status estratégico e métricas de estoque.</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                
                with col_export_btn:
                    abc_export = inventory.get("abc_export", pd.DataFrame())
                    if not abc_export.empty:
                        buffer_abc = BytesIO()
                        with pd.ExcelWriter(buffer_abc, engine="openpyxl") as writer:
                            abc_export.to_excel(writer, index=False, sheet_name="Inteligência ABC")
                        buffer_abc.seek(0)
                        
                        st.download_button(
                            label="📥 Baixar Relatório ABC (.xlsx)",
                            data=buffer_abc.getvalue(),
                            file_name="relatorio_inteligencia_abc.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )
                    else:
                        st.warning("Dados não disponíveis para exportação.")
                
                st.markdown('</div>', unsafe_allow_html=True)

                # ========== LINHA 3: Tabelas de Ação (50% | 50%) ==========
                col_rupture, col_dead = st.columns(2)
                
                with col_rupture:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown('<div class="section-title">🚨 Risco de Ruptura</div>', unsafe_allow_html=True)
                    
                    rupture_table = inventory["rupture_table"].copy()
                    if not rupture_table.empty:
                        # Normalizar coverage_days para ProgressColumn (0-30 dias)
                        rupture_table["coverage_norm"] = rupture_table["coverage_days"].clip(0, 30) / 30
                        
                        display_rupture = rupture_table[["product_name", "saldo", "daily_qty", "coverage_norm"]].copy()
                        display_rupture = display_rupture.rename(columns={
                            "product_name": "Produto",
                            "saldo": "Saldo",
                            "daily_qty": "Venda/Dia",
                            "coverage_norm": "Dias Restantes",
                        })
                        
                        st.dataframe(
                            display_rupture,
                            use_container_width=True,
                            column_config={
                                "Produto": st.column_config.TextColumn(width="medium"),
                                "Saldo": st.column_config.NumberColumn(format="%d", width="small"),
                                "Venda/Dia": st.column_config.NumberColumn(format="%.1f", width="small"),
                                "Dias Restantes": st.column_config.ProgressColumn(
                                    label="Dias Restantes",
                                    format="%.0f",
                                    min_value=0,
                                    max_value=1,
                                    width="medium",
                                ),
                            },
                            hide_index=True,
                            height=350,
                        )
                    else:
                        st.success("✅ Nenhum produto com risco de ruptura!")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col_dead:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown('<div class="section-title">🐢 Estoque Morto (Promoção Urgente)</div>', unsafe_allow_html=True)
                    
                    dead_table = inventory["dead_stock_table"].copy()
                    if not dead_table.empty:
                        display_dead = dead_table.rename(columns={
                            "product_name": "Produto",
                            "days_without_sale": "Dias Parado",
                            "cost": "Custo Unit.",
                            "stock_value": "Total Travado",
                        })
                        
                        st.dataframe(
                            display_dead,
                            use_container_width=True,
                            column_config={
                                "Produto": st.column_config.TextColumn(width="medium"),
                                "Dias Parado": st.column_config.NumberColumn(format="%d dias", width="small"),
                                "Custo Unit.": st.column_config.NumberColumn(format="R$ %.2f", width="small"),
                                "Total Travado": st.column_config.NumberColumn(format="R$ %.2f", width="small"),
                            },
                            hide_index=True,
                            height=350,
                        )
                    else:
                        st.success("✅ Nenhum produto parado há mais de 90 dias!")
                    
                    st.markdown('</div>', unsafe_allow_html=True)

                # ========== DOWNLOAD EXCEL COMPLETO ==========
                st.markdown('<div class="card">', unsafe_allow_html=True)
                col_download1, col_download2, col_spacer = st.columns([1, 1, 2])
                
                with col_download1:
                    purchase = inventory["purchase_table"].copy()
                    if "product_name" not in purchase.columns:
                        purchase = purchase.merge(
                            inventory["scatter"][["sku", "product_name"]].drop_duplicates(),
                            on="sku", how="left"
                        )
                    purchase_export = purchase[["sku", "product_name", "saldo", "daily_qty", "coverage_days", "status"]].copy()
                    purchase_export = purchase_export.rename(columns={
                        "sku": "SKU",
                        "product_name": "Produto",
                        "saldo": "Estoque Atual",
                        "daily_qty": "Giro Diário",
                        "coverage_days": "Dias de Cobertura",
                        "status": "Status",
                    })
                    
                    buffer = BytesIO()
                    purchase_export.to_excel(buffer, index=False, sheet_name="Reposição", engine="openpyxl")
                    buffer.seek(0)
                    st.download_button(
                        label="📥 Baixar Lista de Reposição",
                        data=buffer.getvalue(),
                        file_name="lista_reposicao.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                
                with col_download2:
                    dead_export = inventory["dead_stock_table"].copy()
                    if not dead_export.empty:
                        dead_export = dead_export.rename(columns={
                            "product_name": "Produto",
                            "days_without_sale": "Dias Parado",
                            "cost": "Custo Unit.",
                            "stock_value": "Total Travado R$",
                        })
                        buffer2 = BytesIO()
                        dead_export.to_excel(buffer2, index=False, sheet_name="Estoque Morto", engine="openpyxl")
                        buffer2.seek(0)
                        st.download_button(
                            label="📥 Baixar Estoque Morto",
                            data=buffer2.getvalue(),
                            file_name="estoque_morto.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                
                st.markdown('</div>', unsafe_allow_html=True)

            elif key == "performance":
                # ========== LINHA 1: KPIs (4 Cards) ==========
                kpi_cols = st.columns(4)
                with kpi_cols[0]:
                    _kpi_card(
                        "💵 Vendas Totais",
                        f"R$ {sales_perf['total_revenue']:,.2f}",
                        f"{sales_perf['total_orders']} pedidos no período",
                        "positive",
                    )
                with kpi_cols[1]:
                    _kpi_card(
                        "🏆 Melhor Canal",
                        sales_perf["best_channel"],
                        f"{sales_perf['best_channel_pct']:.1f}% das vendas",
                        "positive",
                    )
                with kpi_cols[2]:
                    _kpi_card(
                        "🔄 Taxa de Recorrência",
                        f"{sales_perf['recurrence_rate']:.1f}%",
                        "Clientes que voltaram a comprar",
                        "positive" if sales_perf['recurrence_rate'] > 30 else "warning",
                    )
                with kpi_cols[3]:
                    _kpi_card(
                        "📊 Lucro Operacional",
                        f"R$ {sales_perf['operational_profit']:,.2f}",
                        "Receita - Custo dos Produtos",
                        "positive" if sales_perf['operational_profit'] > 0 else "negative",
                    )

                # ========== LINHA 2: Inteligência de Canais ==========
                col_donut, col_evolution = st.columns([4, 6])
                
                with col_donut:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    share = sales_perf["share"]
                    total_val = share["revenue"].sum()
                    
                    fig_donut = go.Figure(data=[go.Pie(
                        labels=share["channel"],
                        values=share["revenue"],
                        hole=0.6,
                        marker=dict(colors=["#00CC96", "#F59E0B", "#636EFA", "#EF553B", "#AB63FA"]),
                        textinfo="label+percent",
                        textposition="outside",
                        textfont=dict(color="#E0E0E0", size=11),
                        hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
                    )])
                    
                    fig_donut.add_annotation(
                        text=f"<b>R$ {total_val:,.0f}</b><br><span style='font-size:11px;color:#A0A0A0'>Total</span>",
                        x=0.5, y=0.5,
                        font=dict(size=18, color="#FFFFFF"),
                        showarrow=False,
                    )
                    
                    fig_donut.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(t=30, l=10, r=10, b=10),
                        showlegend=False,
                        title=dict(text="Share de Canais", font=dict(color="#E0E0E0", size=14), x=0.5),
                        height=320,
                    )
                    st.plotly_chart(fig_donut, use_container_width=True, key='chart_channel_share')
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col_evolution:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    channel_ev = sales_perf["channel_evolution"]
                    
                    fig_line = px.line(
                        channel_ev,
                        x="date",
                        y="revenue",
                        color="channel",
                        markers=True,
                        color_discrete_sequence=["#00CC96", "#F59E0B", "#636EFA", "#EF553B", "#AB63FA"],
                    )
                    
                    fig_line.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(t=30, l=10, r=10, b=10),
                        title=dict(text="Evolução de Vendas por Canal", font=dict(color="#E0E0E0", size=14)),
                        xaxis=dict(title="", gridcolor="#2A2A2A", color="#A0A0A0"),
                        yaxis=dict(title="Faturamento (R$)", gridcolor="#2A2A2A", color="#A0A0A0"),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1,
                            font=dict(color="#E0E0E0", size=10),
                        ),
                        hovermode="x unified",
                        height=320,
                    )
                    
                    fig_line.update_traces(line=dict(width=2))
                    st.plotly_chart(fig_line, use_container_width=True, key='chart_channel_evolution')
                    st.markdown('</div>', unsafe_allow_html=True)

                # ========== LINHA 3: Cohort (Novos vs Recorrentes) ==========
                col_cohort, col_insight = st.columns([6, 4])
                
                with col_cohort:
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    recurrence = sales_perf["recurrence"]
                    
                    fig_cohort = px.bar(
                        recurrence,
                        x="date",
                        y="revenue",
                        color="customer_type",
                        barmode="stack",
                        color_discrete_map={
                            "Novos Clientes": "#60A5FA",      # Azul claro
                            "Recorrentes": "#3730A3",         # Azul escuro/roxo
                        },
                    )
                    
                    fig_cohort.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(t=30, l=10, r=10, b=10),
                        title=dict(text="Cohort Diário: Novos vs Recorrentes", font=dict(color="#E0E0E0", size=14)),
                        xaxis=dict(title="", gridcolor="#2A2A2A", color="#A0A0A0"),
                        yaxis=dict(title="Faturamento (R$)", gridcolor="#2A2A2A", color="#A0A0A0"),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1,
                            font=dict(color="#E0E0E0", size=10),
                        ),
                        bargap=0.15,
                        height=320,
                    )
                    st.plotly_chart(fig_cohort, use_container_width=True, key='chart_recurrence')
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col_insight:
                    st.markdown(
                        f"""
                        <div class="card" style="height: 320px; display: flex; flex-direction: column; justify-content: center;">
                            <div style="text-align: center;">
                                <div style="font-size: 48px; margin-bottom: 10px;">🔄</div>
                                <div style="font-size: 36px; font-weight: bold; color: #00CC96;">
                                    {sales_perf['recurrence_rate']:.1f}%
                                </div>
                                <div style="font-size: 14px; color: #A0A0A0; margin-top: 8px;">
                                    Taxa de Recompra
                                </div>
                                <hr style="border-color: #333; margin: 20px 0;">
                                <div style="font-size: 13px; color: #E0E0E0; text-align: left; padding: 0 10px;">
                                    <strong>📈 Insight:</strong><br>
                                    {'Excelente! Clientes estão voltando a comprar. Mantenha a qualidade e fidelização.' if sales_perf['recurrence_rate'] > 40 else 'Oportunidade de melhoria! Considere programas de fidelidade e remarketing.' if sales_perf['recurrence_rate'] > 20 else 'Atenção! Baixa retenção. Analise a experiência do cliente e pós-venda.'}
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # ========== LINHA 4: Tabela de Produtos por Margem (Full Width) ==========
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="section-title">🏷️ Top Produtos por Lucratividade</div>', unsafe_allow_html=True)
                
                top_margin = sales_perf["top_margin"].copy()
                
                # Garantir colunas necessárias
                if "product_name" not in top_margin.columns:
                    top_margin["product_name"] = top_margin.get("sku", "N/A")
                if "main_channel" not in top_margin.columns:
                    top_margin["main_channel"] = "N/A"
                if "avg_price" not in top_margin.columns:
                    top_margin["avg_price"] = top_margin["revenue"] / top_margin["qty_sold"].replace(0, 1)
                if "unit_cost" not in top_margin.columns:
                    top_margin["unit_cost"] = 0.0
                if "margin_pct" not in top_margin.columns:
                    top_margin["margin_pct"] = (top_margin["margin"] / top_margin["revenue"].replace(0, 1)) * 100
                
                # Normalizar margin_pct para 0-1 (para ProgressColumn)
                top_margin["margin_pct_norm"] = top_margin["margin_pct"].clip(0, 100) / 100
                
                display_df = top_margin[["product_name", "main_channel", "avg_price", "unit_cost", "margin", "margin_pct_norm"]].copy()
                display_df = display_df.rename(columns={
                    "product_name": "Produto",
                    "main_channel": "Canal Principal",
                    "avg_price": "Preço Venda",
                    "unit_cost": "Custo Unit.",
                    "margin": "Margem R$",
                    "margin_pct_norm": "Margem %",
                })
                
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    column_config={
                        "Produto": st.column_config.TextColumn(width="medium"),
                        "Canal Principal": st.column_config.TextColumn(width="small"),
                        "Preço Venda": st.column_config.NumberColumn(format="R$ %.2f", width="small"),
                        "Custo Unit.": st.column_config.NumberColumn(format="R$ %.2f", width="small"),
                        "Margem R$": st.column_config.NumberColumn(format="R$ %.2f", width="small"),
                        "Margem %": st.column_config.ProgressColumn(
                            label="Margem %",
                            format="%.0f%%",
                            min_value=0,
                            max_value=1,
                            width="medium",
                        ),
                    },
                    hide_index=True,
                    height=400,
                )
                st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
