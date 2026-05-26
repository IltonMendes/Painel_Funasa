# app.py
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from dash import Dash, dcc, html, Input, Output, dash_table

# =========================================================
# CONFIG BANCO
# =========================================================
DB_HOST     = "bigdata.dataiesb.com"
DB_PORT     = 5432
DB_NAME     = "iesb"
DB_USER     = "data_iesb"
DB_PASSWORD = "iesb"

SCHEMA = "public"
TABLE  = "sus_aih"

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

# =========================================================
# PALETA FUNASA
# =========================================================
THEME = {
    "bg_page"      : "#EDF3FB",
    "sidebar_top"  : "#0D3B66",
    "sidebar_bot"  : "#082848",
    "card_bg"      : "#FFFFFF",
    "blue"         : "#005A9C",
    "blue_light"   : "#3A7FC1",
    "green"        : "#0B8F6A",
    "green_light"  : "#1FA67A",
    "yellow"       : "#F2C94C",
    "red"          : "#C0392B",
    "text"         : "#1F2937",
    "muted"        : "#6B7280",
    "border"       : "#DCE3EA",
    "shadow"       : "0 4px 20px rgba(13,59,102,0.10)",
}

COLOR_SEQ = [
    "#005A9C", "#0B8F6A", "#F2C94C",
    "#5FA8D3", "#7BC8A4", "#F39C12",
    "#8E44AD", "#2C3E50"
]

MACROGRUPOS = {
    "qtd_01": "01 – Promoção e Prevenção",
    "qtd_02": "02 – Finalidade Diagnóstica",
    "qtd_03": "03 – Procedimentos Clínicos",
    "qtd_04": "04 – Procedimentos Cirúrgicos",
    "qtd_05": "05 – Transplantes",
    "qtd_06": "06 – Medicamentos",
    "qtd_07": "07 – Órteses e Próteses",
    "qtd_08": "08 – Ações Complementares",
}
MACROGRUPOS_VL = {k.replace("qtd_", "vl_"): v for k, v in MACROGRUPOS.items() if k != "qtd_01"}

# =========================================================
# HELPERS
# =========================================================
def fmt_num(n):
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except Exception:
        return "—"

def fmt_brl(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "—"

def empty_fig(msg="Sem dados para os filtros selecionados"):
    fig = go.Figure()
    fig.add_annotation(
        text=msg, x=0.5, y=0.5,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=14, color=THEME["muted"], family="Segoe UI")
    )
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=10, r=10, t=40, b=10)
    )
    return fig

def apply_theme(fig, title, height=330):
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=14, color=THEME["text"], family="Segoe UI"),
            x=0.01, pad=dict(b=8)
        ),
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="Segoe UI, Arial", color=THEME["text"], size=12),
        margin=dict(l=16, r=12, t=54, b=16),
        height=height,
        legend=dict(
            orientation="h", yanchor="bottom",
            y=1.02, xanchor="left", x=0,
            font=dict(size=11)
        ),
        hoverlabel=dict(
            bgcolor="white",
            bordercolor=THEME["border"],
            font=dict(family="Segoe UI", size=12, color=THEME["text"])
        ),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEF2F7", zeroline=False, tickfont=dict(size=11))
    fig.update_yaxes(showgrid=True, gridcolor="#EEF2F7", zeroline=False, tickfont=dict(size=11))
    return fig

# =========================================================
# WHERE CLAUSE
# =========================================================
def build_where(anos_selecionados, uf, regiao, meses):
    params = {}

    if not anos_selecionados:
        anos_selecionados = []

    where = """
        WHERE trim(ano_aih) ~ '^\\d{4}$'
          AND trim(mes_aih) ~ '^\\d{1,2}$'
          AND trim(mes_aih)::int BETWEEN 1 AND 12
    """

    # Anos (multi dropdown)
    if anos_selecionados:
        ano_keys = []
        for i, a in enumerate(sorted(set(anos_selecionados))):
            k = f"a{i}"
            ano_keys.append(f":{k}")
            params[k] = int(a)
        where += f" AND trim(ano_aih)::int IN ({', '.join(ano_keys)})"

    # UF
    if uf and uf != "TODAS":
        where += " AND COALESCE(NULLIF(trim(uf_sigla),''),'NA') = :uf"
        params["uf"] = uf

    # Região
    if regiao and regiao != "TODAS":
        where += " AND COALESCE(NULLIF(trim(regiao_nome),''),'NA') = :regiao"
        params["regiao"] = regiao

    # Meses
    if meses:
        mes_keys = []
        for i, m in enumerate(sorted(set(meses))):
            k = f"m{i}"
            mes_keys.append(f":{k}")
            params[k] = int(m)
        where += f" AND trim(mes_aih)::int IN ({', '.join(mes_keys)})"

    return where, params

# =========================================================
# QUERIES
# =========================================================
def get_filters():
    with engine.connect() as conn:
        meta = conn.execute(text(f"""
            SELECT MIN(trim(ano_aih)::int) AS ano_min,
                   MAX(trim(ano_aih)::int) AS ano_max
            FROM {SCHEMA}.{TABLE}
            WHERE trim(ano_aih) ~ '^\\d{{4}}$'
        """)).mappings().first()

        anos = [
            r[0] for r in conn.execute(text(f"""
                SELECT DISTINCT trim(ano_aih)::int AS ano
                FROM {SCHEMA}.{TABLE}
                WHERE trim(ano_aih) ~ '^\\d{{4}}$'
                ORDER BY 1
            """)).fetchall()
        ]

        ufs = [r[0] for r in conn.execute(text(f"""
            SELECT DISTINCT COALESCE(NULLIF(trim(uf_sigla),''),'NA')
            FROM {SCHEMA}.{TABLE} ORDER BY 1
        """)).fetchall()]

        regs = [r[0] for r in conn.execute(text(f"""
            SELECT DISTINCT COALESCE(NULLIF(trim(regiao_nome),''),'NA')
            FROM {SCHEMA}.{TABLE} ORDER BY 1
        """)).fetchall()]

    ano_min = int(meta["ano_min"]) if meta and meta["ano_min"] else 2018
    ano_max = int(meta["ano_max"]) if meta and meta["ano_max"] else 2026
    return ano_min, ano_max, anos or [], ufs or ["NA"], regs or ["NA"]


def q_kpi(where, params):
    return pd.read_sql(text(f"""
        SELECT
            SUM(COALESCE(qtd_total,0))                              AS qtd_total,
            SUM(COALESCE(vl_total,0))                               AS vl_total,
            COUNT(DISTINCT codigo_municipio_dv)                     AS municipios,
            COUNT(DISTINCT COALESCE(NULLIF(trim(uf_sigla),''),'NA')) AS ufs
        FROM {SCHEMA}.{TABLE} {where}
    """), engine, params=params)


def q_temporal(where, params):
    return pd.read_sql(text(f"""
        SELECT
            make_date(trim(ano_aih)::int, trim(mes_aih)::int, 1) AS competencia,
            SUM(COALESCE(qtd_total,0)) AS qtd_total,
            SUM(COALESCE(vl_total,0))  AS vl_total
        FROM {SCHEMA}.{TABLE} {where}
        GROUP BY 1 ORDER BY 1
    """), engine, params=params)


def q_regiao(where, params):
    return pd.read_sql(text(f"""
        SELECT
            COALESCE(NULLIF(trim(regiao_nome),''),'NA') AS regiao,
            SUM(COALESCE(qtd_total,0)) AS qtd_total,
            SUM(COALESCE(vl_total,0))  AS vl_total
        FROM {SCHEMA}.{TABLE} {where}
        GROUP BY 1 ORDER BY 2 DESC
    """), engine, params=params)


def q_uf(where, params):
    return pd.read_sql(text(f"""
        SELECT
            COALESCE(NULLIF(trim(uf_sigla),''),'NA') AS uf,
            SUM(COALESCE(qtd_total,0)) AS qtd_total,
            SUM(COALESCE(vl_total,0))  AS vl_total
        FROM {SCHEMA}.{TABLE} {where}
        GROUP BY 1 ORDER BY 2 DESC
    """), engine, params=params)


def q_anual(where, params):
    return pd.read_sql(text(f"""
        SELECT
            trim(ano_aih)::int                           AS ano,
            COALESCE(NULLIF(trim(regiao_nome),''),'NA') AS regiao,
            SUM(COALESCE(qtd_total,0))                   AS qtd_total,
            SUM(COALESCE(vl_total,0))                    AS vl_total
        FROM {SCHEMA}.{TABLE} {where}
        GROUP BY 1,2 ORDER BY 1,2
    """), engine, params=params)


def q_proc(where, params):
    return pd.read_sql(text(f"""
        SELECT
            SUM(COALESCE(qtd_01,0)) AS qtd_01,
            SUM(COALESCE(qtd_02,0)) AS qtd_02,
            SUM(COALESCE(qtd_03,0)) AS qtd_03,
            SUM(COALESCE(qtd_04,0)) AS qtd_04,
            SUM(COALESCE(qtd_05,0)) AS qtd_05,
            SUM(COALESCE(qtd_06,0)) AS qtd_06,
            SUM(COALESCE(qtd_07,0)) AS qtd_07,
            SUM(COALESCE(qtd_08,0)) AS qtd_08,
            SUM(COALESCE(vl_02,0))  AS vl_02,
            SUM(COALESCE(vl_03,0))  AS vl_03,
            SUM(COALESCE(vl_04,0))  AS vl_04,
            SUM(COALESCE(vl_05,0))  AS vl_05,
            SUM(COALESCE(vl_06,0))  AS vl_06,
            SUM(COALESCE(vl_07,0))  AS vl_07,
            SUM(COALESCE(vl_08,0))  AS vl_08
        FROM {SCHEMA}.{TABLE} {where}
    """), engine, params=params)


def q_mapa(where, params):
    return pd.read_sql(text(f"""
        SELECT
            COALESCE(NULLIF(trim(nome_municipio),''),'Sem nome') AS municipio,
            COALESCE(NULLIF(trim(uf_sigla),''),'NA')             AS uf,
            AVG(latitude)::float                                  AS lat,
            AVG(longitude)::float                                 AS lon,
            SUM(COALESCE(qtd_total,0))                           AS qtd_total,
            SUM(COALESCE(vl_total,0))                            AS vl_total
        FROM {SCHEMA}.{TABLE} {where}
          AND latitude  IS NOT NULL
          AND longitude IS NOT NULL
        GROUP BY 1,2
    """), engine, params=params)


def q_top(where, params, col="qtd_total"):
    return pd.read_sql(text(f"""
        SELECT
            COALESCE(NULLIF(trim(nome_municipio),''),'Sem nome') AS municipio,
            COALESCE(NULLIF(trim(uf_sigla),''),'NA')             AS uf,
            SUM(COALESCE({col},0))                               AS valor
        FROM {SCHEMA}.{TABLE} {where}
        GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15
    """), engine, params=params)

# =========================================================
# DADOS INICIAIS
# =========================================================
ANO_MIN, ANO_MAX, ANOS_LISTA, UFS, REGS = get_filters()

ANO_OPT = [{"label": str(a), "value": a} for a in ANOS_LISTA]
UF_OPT  = [{"label": "TODAS", "value": "TODAS"}] + [{"label": u, "value": u} for u in UFS]
REG_OPT = [{"label": "TODAS", "value": "TODAS"}] + [{"label": r, "value": r} for r in REGS]
MES_OPT = [
    {"label": "Janeiro",   "value": 1},
    {"label": "Fevereiro", "value": 2},
    {"label": "Março",     "value": 3},
    {"label": "Abril",     "value": 4},
    {"label": "Maio",      "value": 5},
    {"label": "Junho",     "value": 6},
    {"label": "Julho",     "value": 7},
    {"label": "Agosto",    "value": 8},
    {"label": "Setembro",  "value": 9},
    {"label": "Outubro",   "value": 10},
    {"label": "Novembro",  "value": 11},
    {"label": "Dezembro",  "value": 12},
]
IND_OPT = [
    {"label": "📦  Quantidade de AIH",    "value": "qtd_total"},
    {"label": "💲  Valor aprovado (R$)",  "value": "vl_total"},
]

# =========================================================
# ESTILOS
# =========================================================
CARD = {
    "backgroundColor": THEME["card_bg"],
    "border"         : f"1px solid {THEME['border']}",
    "borderRadius"   : "16px",
    "boxShadow"      : THEME["shadow"],
    "padding"        : "16px",
}

DD_STYLE = {
    "color"     : THEME["text"],
    "fontSize"  : "13px",
    "marginBottom": "14px",
}

LBL_STYLE = {
    "fontSize"    : "12px",
    "fontWeight"  : "600",
    "marginBottom": "5px",
    "opacity"     : 0.85,
    "display"     : "block",
    "letterSpacing": "0.3px",
}

# =========================================================
# APP
# =========================================================
app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server
app.title = "Painel Funasa | AIH"

app.layout = html.Div(
    style={
        "background"  : f"linear-gradient(145deg, {THEME['bg_page']} 0%, #F0F7FF 100%)",
        "minHeight"   : "100vh",
        "fontFamily"  : "Segoe UI, Arial, sans-serif",
    },
    children=[

        # ===================================================
        # SIDEBAR
        # ===================================================
        html.Div(
            style={
                "position"     : "fixed",
                "top": 0, "left": 0, "bottom": 0,
                "width"        : "268px",
                "display"      : "flex",
                "flexDirection": "column",
                "background"   : f"linear-gradient(180deg, {THEME['sidebar_top']} 0%, {THEME['sidebar_bot']} 100%)",
                "color"        : "white",
                "overflowY"    : "auto",
                "zIndex"       : 1000,
                "boxShadow"    : "4px 0 20px rgba(0,0,0,0.18)",
            },
            children=[

                # Cabeçalho sidebar
                html.Div(
                    style={
                        "padding"     : "24px 18px 14px",
                        "borderBottom": "1px solid rgba(255,255,255,0.13)",
                    },
                    children=[
                        html.Div("🏥", style={"fontSize": "34px", "marginBottom": "6px"}),
                        html.Div("FUNASA", style={
                            "fontWeight"   : "800",
                            "fontSize"     : "22px",
                            "letterSpacing": "2px",
                            "color"        : THEME["yellow"],
                        }),
                        html.Div("Painel de Internações AIH", style={
                            "fontSize": "12px", "opacity": 0.7, "marginTop": "3px"
                        }),
                    ]
                ),

                # Filtros
                html.Div(
                    style={"padding": "16px 18px", "flex": 1},
                    children=[

                        html.Div("FILTROS", style={
                            "fontSize"     : "10px",
                            "letterSpacing": "1.8px",
                            "opacity"      : 0.45,
                            "marginBottom" : "14px",
                        }),

                        # Indicador
                        html.Label("📊  Indicador", style=LBL_STYLE),
                        dcc.Dropdown(
                            id="filtro-indicador",
                            options=IND_OPT,
                            value="qtd_total",
                            clearable=False,
                            style=DD_STYLE,
                        ),

                        # Ano (multi-select)
                        html.Label("📆  Anos", style=LBL_STYLE),
                        dcc.Dropdown(
                            id="filtro-anos",
                            options=ANO_OPT,
                            value=ANOS_LISTA,
                            multi=True,
                            placeholder="Selecione os anos...",
                            style=DD_STYLE,
                        ),

                        # Mês (multi-select)
                        html.Label("📅  Meses", style=LBL_STYLE),
                        dcc.Dropdown(
                            id="filtro-meses",
                            options=MES_OPT,
                            value=list(range(1, 13)),
                            multi=True,
                            placeholder="Selecione os meses...",
                            style=DD_STYLE,
                        ),

                        # Região
                        html.Label("🗺  Região", style=LBL_STYLE),
                        dcc.Dropdown(
                            id="filtro-regiao",
                            options=REG_OPT,
                            value="TODAS",
                            clearable=False,
                            style=DD_STYLE,
                        ),

                        # UF
                        html.Label("📍  Estado (UF)", style=LBL_STYLE),
                        dcc.Dropdown(
                            id="filtro-uf",
                            options=UF_OPT,
                            value="TODAS",
                            clearable=False,
                            style=DD_STYLE,
                        ),

                        # Dica
                        html.Div(
                            "💡 Selecione uma UF ou período menor para respostas mais rápidas.",
                            style={
                                "marginTop"   : "8px",
                                "background"  : "rgba(255,255,255,0.09)",
                                "border"      : "1px solid rgba(255,255,255,0.15)",
                                "padding"     : "10px 12px",
                                "borderRadius": "10px",
                                "fontSize"    : "11px",
                                "lineHeight"  : "1.55",
                                "opacity"     : 0.8,
                            }
                        ),
                    ]
                ),

                # Rodapé sidebar
                html.Div(
                    style={
                        "padding"   : "12px 18px",
                        "borderTop" : "1px solid rgba(255,255,255,0.10)",
                        "fontSize"  : "10px",
                        "opacity"   : 0.45,
                        "textAlign" : "center",
                    },
                    children=["Dados: SUS / DATASUS", html.Br(), "IESB — Análise de Dados"]
                ),
            ]
        ),

        # ===================================================
        # CONTEÚDO PRINCIPAL
        # ===================================================
        html.Div(
            style={"marginLeft": "268px", "padding": "22px"},
            children=[

                # Cabeçalho
                html.Div(
                    style={
                        **CARD,
                        "marginBottom": "18px",
                        "borderLeft"  : f"6px solid {THEME['green']}",
                        "display"     : "flex",
                        "justifyContent": "space-between",
                        "alignItems"    : "center",
                    },
                    children=[
                        html.Div([
                            html.H2(
                                "Internações Hospitalares — SUS / AIH",
                                style={"margin": "0", "color": THEME["text"], "fontSize": "19px"}
                            ),
                            html.P(
                                "Monitoramento estratégico de produção hospitalar por território e competência.",
                                style={"margin": "4px 0 0", "color": THEME["muted"], "fontSize": "13px"}
                            ),
                        ]),
                        html.Div(
                            id="label-periodo",
                            style={
                                "background"  : THEME["blue"],
                                "color"       : "white",
                                "padding"     : "6px 16px",
                                "borderRadius": "20px",
                                "fontSize"    : "13px",
                                "fontWeight"  : "600",
                                "whiteSpace"  : "nowrap",
                            }
                        ),
                    ]
                ),

                # KPIs
                html.Div(
                    style={
                        "display"            : "grid",
                        "gridTemplateColumns": "repeat(4, 1fr)",
                        "gap"                : "14px",
                        "marginBottom"       : "18px",
                    },
                    children=[
                        html.Div(style={**CARD, "borderTop": f"4px solid {THEME['blue']}"}, children=[
                            html.Div("🏥", style={"fontSize": "24px", "marginBottom": "4px"}),
                            html.Div("Total de internações", style={"color": THEME["muted"], "fontSize": "12px"}),
                            html.H2(id="kpi-qtd", style={"color": THEME["blue"], "margin": "6px 0 0", "fontSize": "24px"}),
                        ]),
                        html.Div(style={**CARD, "borderTop": f"4px solid {THEME['green']}"}, children=[
                            html.Div("💰", style={"fontSize": "24px", "marginBottom": "4px"}),
                            html.Div("Valor total aprovado", style={"color": THEME["muted"], "fontSize": "12px"}),
                            html.H2(id="kpi-vl", style={"color": THEME["green"], "margin": "6px 0 0", "fontSize": "20px"}),
                        ]),
                        html.Div(style={**CARD, "borderTop": f"4px solid {THEME['yellow']}"}, children=[
                            html.Div("📈", style={"fontSize": "24px", "marginBottom": "4px"}),
                            html.Div("Ticket médio por AIH", style={"color": THEME["muted"], "fontSize": "12px"}),
                            html.H2(id="kpi-ticket", style={"color": THEME["text"], "margin": "6px 0 0", "fontSize": "20px"}),
                        ]),
                        html.Div(style={**CARD, "borderTop": f"4px solid {THEME['blue_light']}"}, children=[
                            html.Div("📍", style={"fontSize": "24px", "marginBottom": "4px"}),
                            html.Div("Municípios / UFs", style={"color": THEME["muted"], "fontSize": "12px"}),
                            html.H2(id="kpi-mun", style={"color": THEME["text"], "margin": "6px 0 0", "fontSize": "24px"}),
                        ]),
                    ]
                ),

                # Loading
                dcc.Loading(type="circle", color=THEME["blue"], children=[

                    # Linha 1 — temporal + donut
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "1.7fr 1fr", "gap": "14px", "marginBottom": "14px"},
                        children=[
                            html.Div(style=CARD, children=[dcc.Graph(id="fig-temporal", config={"displayModeBar": False})]),
                            html.Div(style=CARD, children=[dcc.Graph(id="fig-regiao",   config={"displayModeBar": False})]),
                        ]
                    ),

                    # Linha 2 — área anual + barras UF
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px", "marginBottom": "14px"},
                        children=[
                            html.Div(style=CARD, children=[dcc.Graph(id="fig-anual", config={"displayModeBar": False})]),
                            html.Div(style=CARD, children=[dcc.Graph(id="fig-uf",    config={"displayModeBar": False})]),
                        ]
                    ),

                    # Linha 3 — sunburst + mapa
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "1fr 1.4fr", "gap": "14px", "marginBottom": "14px"},
                        children=[
                            html.Div(style=CARD, children=[dcc.Graph(id="fig-proc", config={"displayModeBar": False})]),
                            html.Div(style=CARD, children=[dcc.Graph(id="fig-mapa", config={"displayModeBar": False})]),
                        ]
                    ),

                    # Linha 4 — tabela
                    html.Div(
                        style=CARD,
                        children=[
                            html.H4("🏆  Top 15 Municípios", style={"marginTop": "0", "color": THEME["text"], "fontSize": "15px"}),
                            dash_table.DataTable(
                                id="tbl-top",
                                columns=[
                                    {"name": "#",          "id": "rank"},
                                    {"name": "Município",  "id": "municipio"},
                                    {"name": "UF",         "id": "uf"},
                                    {"name": "Valor",      "id": "valor_fmt"},
                                ],
                                data=[],
                                sort_action="native",
                                style_table={"overflowX": "auto"},
                                style_header={
                                    "backgroundColor": THEME["blue"],
                                    "color"          : "white",
                                    "fontWeight"     : "700",
                                    "border"         : "none",
                                    "fontSize"       : "13px",
                                    "padding"        : "10px 12px",
                                },
                                style_cell={
                                    "padding"    : "9px 12px",
                                    "fontSize"   : "13px",
                                    "textAlign"  : "left",
                                    "border"     : f"1px solid {THEME['border']}",
                                    "fontFamily" : "Segoe UI, Arial",
                                },
                                style_data={"backgroundColor": "white", "color": THEME["text"]},
                                style_data_conditional=[
                                    {"if": {"row_index": "odd"},      "backgroundColor": "#F5F9FF"},
                                    {"if": {"column_id": "rank"},     "fontWeight": "700", "color": THEME["blue"]},
                                    {"if": {"column_id": "valor_fmt"},"fontWeight": "600"},
                                ],
                                page_size=15,
                            )
                        ]
                    ),
                ]),

                # Rodapé principal
                html.Div(
                    "Painel desenvolvido com Plotly Dash  ·  Dados: DATASUS/SUS AIH  ·  IESB 2024",
                    style={
                        "textAlign"    : "center",
                        "marginTop"    : "18px",
                        "paddingBottom": "12px",
                        "color"        : THEME["muted"],
                        "fontSize"     : "11px",
                    }
                ),
            ]
        ),
    ]
)

# =========================================================
# CALLBACK
# =========================================================
@app.callback(
    Output("label-periodo", "children"),
    Output("kpi-qtd",       "children"),
    Output("kpi-vl",        "children"),
    Output("kpi-ticket",    "children"),
    Output("kpi-mun",       "children"),
    Output("fig-temporal",  "figure"),
    Output("fig-regiao",    "figure"),
    Output("fig-anual",     "figure"),
    Output("fig-uf",        "figure"),
    Output("fig-proc",      "figure"),
    Output("fig-mapa",      "figure"),
    Output("tbl-top",       "data"),
    Input("filtro-anos",      "value"),
    Input("filtro-meses",     "value"),
    Input("filtro-regiao",    "value"),
    Input("filtro-uf",        "value"),
    Input("filtro-indicador", "value"),
)
def atualizar(anos, meses, regiao, uf, indicador):
    if not anos:
        anos = ANOS_LISTA
    if not meses:
        meses = list(range(1, 13))

    where, params = build_where(anos, uf, regiao, meses)
    y     = indicador
    y_lbl = "Quantidade" if y == "qtd_total" else "Valor (R$)"

    # Label período
    anos_str   = ", ".join(str(a) for a in sorted(anos))
    label_p    = f"📅 {anos_str}"

    # KPIs
    kpi    = q_kpi(where, params)
    qtd_t  = float(kpi["qtd_total"].fillna(0).iloc[0])
    vl_t   = float(kpi["vl_total"].fillna(0).iloc[0])
    muns   = int(kpi["municipios"].fillna(0).iloc[0])
    ufs_n  = int(kpi["ufs"].fillna(0).iloc[0])
    ticket = (vl_t / qtd_t) if qtd_t > 0 else 0.0

    # Temporal
    df_t = q_temporal(where, params)
    if df_t.empty:
        fig_t = empty_fig()
    else:
        fig_t = go.Figure()
        fig_t.add_trace(go.Scatter(
            x=df_t["competencia"], y=df_t[y],
            mode="lines+markers", name=y_lbl,
            line=dict(color=THEME["blue"], width=3, shape="spline"),
            marker=dict(size=6, color=THEME["green"], line=dict(width=1, color="white")),
            fill="tozeroy",
            fillcolor="rgba(0,90,156,0.07)",
            hovertemplate="<b>%{x|%b/%Y}</b><br>" + y_lbl + ": %{y:,.0f}<extra></extra>",
        ))
        apply_theme(fig_t, f"Evolução Temporal — {y_lbl}", height=300)
        fig_t.update_layout(hovermode="x unified")

    # Região (donut)
    df_r = q_regiao(where, params)
    if df_r.empty or df_r[y].sum() == 0:
        fig_r = empty_fig()
    else:
        fig_r = px.pie(
            df_r, names="regiao", values=y, hole=0.58,
            color_discrete_sequence=COLOR_SEQ
        )
        fig_r.update_traces(
            textposition="outside", textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>" + y_lbl + ": %{value:,.0f}<extra></extra>"
        )
        apply_theme(fig_r, f"Distribuição por Região — {y_lbl}", height=300)
        fig_r.update_layout(showlegend=False)

    # Área anual por região
    df_a = q_anual(where, params)
    if df_a.empty:
        fig_a = empty_fig()
    else:
        fig_a = px.area(
            df_a, x="ano", y=y, color="regiao",
            color_discrete_sequence=COLOR_SEQ, markers=True,
        )
        fig_a.update_traces(
            hovertemplate="<b>%{x}</b> | %{fullData.name}<br>" + y_lbl + ": %{y:,.0f}<extra></extra>"
        )
        apply_theme(fig_a, f"Tendência Anual por Região — {y_lbl}", height=310)
        fig_a.update_xaxes(title="Ano", dtick=1)
        fig_a.update_yaxes(title=y_lbl)

    # UF (barras horizontais)
    df_u = q_uf(where, params).head(12)
    if df_u.empty:
        fig_u = empty_fig()
    else:
        df_u_s = df_u.sort_values(y, ascending=True)
        fig_u  = px.bar(
            df_u_s, x=y, y="uf", orientation="h",
            color=y,
            color_continuous_scale=[[0.0, "#A8D5C2"], [0.5, THEME["green"]], [1.0, THEME["blue"]]],
            text=df_u_s[y].apply(lambda v: fmt_num(v) if y == "qtd_total" else fmt_brl(v))
        )
        fig_u.update_traces(
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>" + y_lbl + ": %{x:,.0f}<extra></extra>"
        )
        apply_theme(fig_u, f"Top UFs — {y_lbl}", height=310)
        fig_u.update_layout(coloraxis_showscale=False)
        fig_u.update_xaxes(title=y_lbl)
        fig_u.update_yaxes(title="")

    # Macrogrupos (sunburst)
    df_praw = q_proc(where, params)
    pmap    = MACROGRUPOS if y == "qtd_total" else MACROGRUPOS_VL
    vals    = [
        {
            "grupo": nome.split("–")[1].strip(),
            "valor": float(df_praw[col].fillna(0).iloc[0])
        }
        for col, nome in pmap.items()
    ]
    df_p = pd.DataFrame(vals)
    if df_p.empty or df_p["valor"].sum() == 0:
        fig_p = empty_fig()
    else:
        df_p = df_p[df_p["valor"] > 0]
        df_p["raiz"] = "AIH"
        fig_p = px.sunburst(
            df_p, path=["raiz", "grupo"], values="valor",
            color="valor",
            color_continuous_scale=[[0.0, THEME["yellow"]], [0.5, THEME["green"]], [1.0, THEME["blue"]]],
            hover_data={"valor": ":,.0f"}
        )
        apply_theme(fig_p, f"Composição por Macrogrupo — {y_lbl}", height=340)

    # Mapa (scatter_map tile)
    df_m = q_mapa(where, params)
    if df_m.empty:
        fig_m = empty_fig("Sem coordenadas disponíveis para o recorte")
    else:
        fig_m = px.scatter_map(
            df_m,
            lat="lat", lon="lon",
            size=(df_m[y].clip(lower=0) + 1),
            color=y,
            hover_name="municipio",
            hover_data={"uf": True, "lat": False, "lon": False, y: ":,.0f"},
            color_continuous_scale=[[0.0, "#A8D5C2"], [0.5, THEME["green"]], [1.0, THEME["blue"]]],
            size_max=40,
            zoom=3.5,
            center={"lat": -14.2, "lon": -51.9},
            map_style="carto-positron",
            opacity=0.8,
        )
        apply_theme(fig_m, f"Distribuição Geográfica — {y_lbl}", height=400)
        fig_m.update_layout(
            margin=dict(l=0, r=0, t=54, b=0),
            coloraxis_colorbar=dict(title=y_lbl, thickness=12, len=0.5)
        )

    # Tabela top municípios
    col_sql = "qtd_total" if y == "qtd_total" else "vl_total"
    df_top  = q_top(where, params, col=col_sql)
    df_top["rank"]      = range(1, len(df_top) + 1)
    df_top["valor_fmt"] = df_top["valor"].fillna(0).apply(
        fmt_num if y == "qtd_total" else fmt_brl
    )
    tbl = df_top[["rank", "municipio", "uf", "valor_fmt"]].to_dict("records")

    return (
        label_p,
        fmt_num(qtd_t),
        fmt_brl(vl_t),
        fmt_brl(ticket),
        f"{fmt_num(muns)} / {ufs_n} UFs",
        fig_t, fig_r, fig_a, fig_u, fig_p, fig_m, tbl
    )

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        print("✅  Conexão com PostgreSQL OK.")
    app.run(debug=False, host="0.0.0.0", port=8050)