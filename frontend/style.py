import streamlit as st


GLOBAL_CSS = """
<style>
/* ── Fonts & base ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Hide Streamlit chrome ────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* ── Page padding ─────────────────────────────────────────── */
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

/* ── Metric cards ─────────────────────────────────────────── */
.metric-card {
    background: #1a1d27;
    border: 1px solid #2d3148;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    text-align: center;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color: #6366f1; }

.metric-value {
    font-size: 2.2rem;
    font-weight: 700;
    color: #6366f1;
    line-height: 1.1;
    margin-bottom: 0.25rem;
}
.metric-label {
    font-size: 0.8rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 500;
}
.metric-sub {
    font-size: 0.75rem;
    color: #64748b;
    margin-top: 0.2rem;
}

/* ── Status badges ────────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.badge-completed  { background: #14532d; color: #22c55e; }
.badge-processing { background: #451a03; color: #f59e0b; }
.badge-pending    { background: #1e1b4b; color: #818cf8; }
.badge-queued     { background: #1e1b4b; color: #818cf8; }
.badge-failed     { background: #450a0a; color: #ef4444; }

/* ── Priority badges ──────────────────────────────────────── */
.priority-High   { color: #ef4444; font-weight: 600; }
.priority-Medium { color: #f59e0b; font-weight: 600; }
.priority-Low    { color: #22c55e; font-weight: 600; }

/* ── Meeting card (history list) ──────────────────────────── */
.meeting-card {
    background: #1a1d27;
    border: 1px solid #2d3148;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.2s, transform 0.1s;
}
.meeting-card:hover {
    border-color: #6366f1;
    transform: translateX(2px);
}
.meeting-card-title {
    font-size: 1rem;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 0.3rem;
}
.meeting-card-meta {
    font-size: 0.78rem;
    color: #64748b;
}

/* ── Page header ──────────────────────────────────────────── */
.page-header {
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #2d3148;
}
.page-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #e2e8f0;
    margin: 0;
}
.page-subtitle {
    font-size: 0.9rem;
    color: #64748b;
    margin-top: 0.3rem;
}

/* ── Action item cards ────────────────────────────────────── */
.action-card {
    background: #1a1d27;
    border-left: 3px solid #6366f1;
    border-radius: 0 8px 8px 0;
    padding: 0.75rem 1rem;
    margin-bottom: 0.6rem;
}
.action-card-task {
    font-size: 0.9rem;
    font-weight: 500;
    color: #e2e8f0;
    margin-bottom: 0.3rem;
}
.action-card-meta {
    font-size: 0.78rem;
    color: #64748b;
    display: flex;
    gap: 1rem;
}

/* ── Decision cards ───────────────────────────────────────── */
.decision-card {
    background: #1a1d27;
    border-left: 3px solid #22c55e;
    border-radius: 0 8px 8px 0;
    padding: 0.75rem 1rem;
    margin-bottom: 0.6rem;
}

/* ── Risk cards ───────────────────────────────────────────── */
.risk-card {
    background: #1a1d27;
    border-left: 3px solid #ef4444;
    border-radius: 0 8px 8px 0;
    padding: 0.75rem 1rem;
    margin-bottom: 0.6rem;
}

/* ── Transcript box ───────────────────────────────────────── */
.transcript-box {
    background: #0f1117;
    border: 1px solid #2d3148;
    border-radius: 8px;
    padding: 1.25rem;
    font-size: 0.88rem;
    line-height: 1.7;
    color: #cbd5e1;
    max-height: 500px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
}

/* ── Email box ────────────────────────────────────────────── */
.email-box {
    background: #0f1117;
    border: 1px solid #2d3148;
    border-radius: 8px;
    padding: 1.25rem;
    font-size: 0.88rem;
    line-height: 1.7;
    color: #cbd5e1;
    white-space: pre-wrap;
    font-family: monospace;
}

/* ── Q&A chat bubbles ─────────────────────────────────────── */
.qa-question {
    background: #1e1b4b;
    border-radius: 12px 12px 4px 12px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
    color: #c7d2fe;
    font-size: 0.9rem;
}
.qa-answer {
    background: #1a1d27;
    border-radius: 4px 12px 12px 12px;
    padding: 0.75rem 1rem;
    margin-bottom: 1rem;
    color: #e2e8f0;
    font-size: 0.9rem;
    border-left: 3px solid #6366f1;
    line-height: 1.6;
}

/* ── Progress bar ─────────────────────────────────────────── */
.stProgress > div > div > div { background-color: #6366f1; }

/* ── Buttons ──────────────────────────────────────────────── */
.stButton > button {
    border-radius: 8px;
    font-weight: 500;
    transition: opacity 0.2s;
}
.stButton > button:hover { opacity: 0.85; }

/* ── Tabs ─────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: #1a1d27;
    border-radius: 8px;
    padding: 4px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 6px;
    font-weight: 500;
    color: #94a3b8;
}
.stTabs [aria-selected="true"] {
    background: #6366f1 !important;
    color: white !important;
}

/* ── Sidebar ──────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #1a1d27;
    border-right: 1px solid #2d3148;
}
[data-testid="stSidebar"] .stMarkdown { color: #94a3b8; }

/* ── Inputs ───────────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea {
    background: #0f1117 !important;
    border-color: #2d3148 !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 1px #6366f1 !important;
}

/* ── Divider ──────────────────────────────────────────────── */
hr { border-color: #2d3148; }
</style>
"""


def inject_css():
    """Call this at the top of every page."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    inject_css()
    sub = f'<p class="page-subtitle">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="page-header">'
        f'<h1 class="page-title">{title}</h1>{sub}'
        f'</div>',
        unsafe_allow_html=True,
    )


def metric_card(value: str, label: str, sub: str = ""):
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="metric-card">'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-label">{label}</div>'
        f'{sub_html}'
        f'</div>'
    )


def status_badge(status: str) -> str:
    return f'<span class="badge badge-{status}">{status}</span>'


def priority_badge(priority: str) -> str:
    return f'<span class="priority-{priority}">{priority}</span>'
