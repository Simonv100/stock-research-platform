import streamlit as st


def apply_workspace_style() -> None:
    st.markdown(
        """
        <style>
        .stMainBlockContainer { max-width: 1600px; padding-top: 3.5rem; padding-bottom: 3rem; }
        [data-testid="stSidebar"] { border-right: 1px solid rgba(128,148,174,.18); }
        [data-testid="stSidebar"] h2 { font-size: 1.05rem; }
        h1 { font-size: 2rem !important; letter-spacing: -.045em; font-weight: 750 !important; }
        h2, h3 { letter-spacing: -.025em; }
        [data-testid="stMetric"] {
            border: 1px solid rgba(128,148,174,.2); border-radius: 14px;
            padding: 1rem 1.1rem; background: rgba(100,140,195,.055);
        }
        [data-testid="stMetricValue"] { font-size: 1.55rem; letter-spacing: -.025em; }
        [data-testid="stMetricLabel"] { opacity: .78; }
        [data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {
            border: 1px solid rgba(128,148,174,.15); border-radius: 12px;
            overflow: hidden;
        }
        [role="tablist"] { gap: .35rem; border-bottom-color: rgba(128,148,174,.2); }
        [role="tab"] { padding: .65rem 1rem; border-radius: 9px 9px 0 0; }
        [role="tab"][aria-selected="true"] {
            background: rgba(59,130,246,.12); color: #60a5fa;
            border-bottom-color: #60a5fa;
        }
        [data-testid="stBaseButton-primary"] {
            background: #2563eb; color: white; border-color: #2563eb; border-radius: 9px;
        }
        [data-testid="stBaseButton-primary"]:hover { background: #1d4ed8; color: white; }
        [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px;
        }
        .workspace-brand {
            display: flex; align-items: center; gap: .7rem; margin: .2rem 0 1.25rem;
        }
        .workspace-mark {
            width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
            color: #fff; font-weight: 750; background: linear-gradient(135deg, #2563eb, #0d9488);
        }
        .workspace-brand strong { font-size: 1.08rem; letter-spacing: -.025em; }
        .workspace-brand small { display: block; opacity: .65; font-size: .72rem; }
        .workspace-kicker {
            color: #60a5fa; font-size: .72rem; font-weight: 700;
            letter-spacing: .15em; margin-bottom: .4rem;
        }
        @media (max-width: 900px) {
            .stMainBlockContainer { padding: 3.5rem 1rem 2rem; }
            [data-testid="stHorizontalBlock"]:has([data-testid="stChatMessage"]),
            [data-testid="stHorizontalBlock"]:has([data-testid="stForm"]) { flex-wrap: wrap; }
            [data-testid="stHorizontalBlock"]:has([data-testid="stForm"]) > [data-testid="stColumn"] {
                width: 100% !important; flex: 1 1 100% !important; min-width: 0;
            }
            [data-testid="stMetric"] { padding: .7rem; }
            [data-testid="stMetricValue"] { font-size: 1.2rem; }
        }
        @media (max-width: 640px) {
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] > [data-testid="stMetric"]) {
                flex-wrap: wrap; gap: .65rem;
            }
            [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] > [data-testid="stMetric"]) {
                width: calc(50% - .65rem) !important;
                flex: 1 1 calc(50% - .65rem) !important; min-width: 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_brand() -> None:
    st.markdown(
        '<div class="workspace-brand"><div class="workspace-mark">G</div>'
        '<div><strong>Global Research</strong><small>Your local investment workspace</small></div></div>',
        unsafe_allow_html=True,
    )
