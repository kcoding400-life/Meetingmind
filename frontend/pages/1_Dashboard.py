"""
Main dashboard — aggregate metrics + recent meeting list.
"""

import streamlit as st
import plotly.graph_objects as go
from collections import Counter
import api
import style

st.set_page_config(page_title="Dashboard · MeetingMind", page_icon="🎙️", layout="wide")

#Auth guard
if not st.session_state.get("token"):
    st.switch_page("app.py")

token = st.session_state["token"]
user  = st.session_state.get("user", {})

#Sidebar
with st.sidebar:
    st.markdown(
        f'<div style="padding:1rem 0 1.5rem;">'
        f'<div style="font-size:1.4rem;font-weight:700;color:#e2e8f0;">🎙️ MeetingMind</div>'
        f'<div style="font-size:0.8rem;color:#64748b;margin-top:0.25rem;">{user.get("email","")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_Dashboard.py", label="📊 Dashboard")
    st.page_link("pages/2_Upload.py",    label="⬆️  Upload Meeting")
    st.page_link("pages/3_History.py",   label="📋 Meeting History")
    st.markdown("---")
    if st.button("Sign Out", use_container_width=True):
        for k in ["token", "user"]:
            st.session_state.pop(k, None)
        st.switch_page("app.py")

#Page header
style.page_header(
    f"Good day, {user.get('full_name', 'there').split()[0]} 👋",
    "Here's your meeting intelligence overview",
)

#Load data (single API call)
with st.spinner("Loading…"):
    data, err = api.list_meetings(token, limit=200)

if err:
    st.error(f"Could not load meetings: {err}")
    st.stop()

meetings  = data.get("meetings", [])
total     = data.get("total", 0)

completed  = [m for m in meetings if m["status"] == "completed"]
processing = [m for m in meetings if m["status"] in ("processing", "pending", "queued")]
failed     = [m for m in meetings if m["status"] == "failed"]

total_seconds = sum((m.get("duration_seconds") or 0) for m in completed)
total_hours   = total_seconds / 3600

#Metric cards
st.markdown("<br>", unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        style.metric_card(str(total), "Total Meetings", f"{len(completed)} completed"),
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        style.metric_card(f"{total_hours:.1f}h", "Hours Processed",
                          f"{len(completed)} recordings"),
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        style.metric_card(str(len(processing)), "In Progress",
                          "being transcribed" if processing else "queue empty"),
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        style.metric_card(str(len(failed)), "Failed",
                          "need attention" if failed else "all good ✓"),
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

#Charts
if meetings:
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Meeting Status")
        fig_pie = go.Figure(data=[go.Pie(
            labels=["Completed", "In Progress", "Failed"],
            values=[len(completed), len(processing), len(failed)],
            hole=0.55,
            marker_colors=["#22c55e", "#f59e0b", "#ef4444"],
            textinfo="label+percent",
            textfont_size=12,
        )])
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#94a3b8", showlegend=False,
            margin=dict(t=10, b=10, l=10, r=10), height=250,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_right:
        st.markdown("#### Meetings Over Time")
        date_counts = Counter()
        for m in meetings:
            try:
                date_counts[m["created_at"][:10]] += 1
            except Exception:
                pass

        sorted_dates = sorted(date_counts.items())[-14:]
        if sorted_dates:
            dates, counts = zip(*sorted_dates)
            fig_bar = go.Figure(data=[go.Bar(
                x=list(dates), y=list(counts),
                marker_color="#6366f1", marker_line_width=0,
            )])
            fig_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#94a3b8",
                margin=dict(t=10, b=30, l=10, r=10), height=250,
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="#2d3148", tickformat="d"),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

#Recent meetings
st.markdown("#### Recent Meetings")

if not meetings:
    st.markdown(
        '<div style="text-align:center;padding:3rem;color:#64748b;">'
        '<div style="font-size:2.5rem;margin-bottom:1rem;">🎙️</div>'
        '<div style="font-size:1rem;font-weight:600;color:#94a3b8;">No meetings yet</div>'
        '<div style="font-size:0.85rem;margin-top:0.5rem;">Upload your first recording to get started</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if st.button("⬆️ Upload your first meeting", type="primary"):
        st.switch_page("pages/2_Upload.py")
else:
    for m in meetings[:10]:
        badge    = style.status_badge(m["status"])
        duration = api.format_duration(m.get("duration_seconds"))
        date_str = m["created_at"][:10]

        col_a, col_b = st.columns([6, 1])
        with col_a:
            st.markdown(
                f'<div class="meeting-card">'
                f'<div class="meeting-card-title">{m["title"]}</div>'
                f'<div class="meeting-card-meta">{badge} &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp; {duration}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with col_b:
            st.markdown("<div style='margin-top:0.6rem;'>", unsafe_allow_html=True)
            if st.button("View", key=f"dash_{m['id']}", use_container_width=True):
                st.session_state["selected_meeting_id"] = m["id"]
                st.switch_page("pages/4_Meeting_Detail.py")
            st.markdown("</div>", unsafe_allow_html=True)

    if total > 10:
        if st.button("View all meetings →", use_container_width=True):
            st.switch_page("pages/3_History.py")

if processing:
    st.info(
        f"⏳ {len(processing)} meeting(s) are currently processing. "
        "Refresh to see updated status.",
        icon="🔄",
    )
