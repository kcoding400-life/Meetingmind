"""
Full meeting view with five tabs:
  1. Summary     — executive summary, participants, follow-up email
  2. Transcript  — raw transcription with language tag
  3. Action Items — prioritised task list
  4. Analytics   — Plotly charts: priority breakdown, risk impact, timeline
  5. Q&A         — natural language questions against the transcript
"""

import json
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import api
import style

st.set_page_config(page_title="Meeting · MeetingMind", page_icon="📄", layout="wide")

if not st.session_state.get("token"):
    st.switch_page("app.py")

token = st.session_state["token"]
user = st.session_state.get("user", {})

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
    if st.button("← Back to History", use_container_width=True):
        st.switch_page("pages/3_History.py")
    st.markdown("---")
    if st.button("Sign Out", use_container_width=True):
        for k in ["token", "user"]:
            st.session_state.pop(k, None)
        st.switch_page("app.py")

#Resolve meeting ID
meeting_id = st.session_state.get("selected_meeting_id")

if not meeting_id:
    st.warning("No meeting selected. Redirecting to history…")
    st.switch_page("pages/3_History.py")

#Load meeting
with st.spinner("Loading meeting…"):
    meeting, err = api.get_meeting(token, meeting_id)

if err:
    st.error(f"Could not load meeting: {err}")
    if st.button("Back to History"):
        st.switch_page("pages/3_History.py")
    st.stop()

#Parse JSON fields
action_items = api.parse_json_field(meeting.get("action_items"))
decisions    = api.parse_json_field(meeting.get("decisions"))
risks        = api.parse_json_field(meeting.get("risks"))
participants = api.parse_json_field(meeting.get("participants"))

#Page header
status = meeting.get("status", "unknown")
duration_str = api.format_duration(meeting.get("duration_seconds"))
file_size_str = api.format_file_size(meeting.get("file_size_bytes"))
date_str = (meeting.get("created_at") or "")[:10]

style.inject_css()
st.markdown(
    f"""
    <div class="page-header">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;">
            <div>
                <h1 class="page-title">{meeting['title']}</h1>
                <div class="page-subtitle">
                    {style.status_badge(status)}
                    <span style="margin-left:0.75rem;">📅 {date_str}</span>
                    <span style="margin-left:0.75rem;">⏱ {duration_str}</span>
                    <span style="margin-left:0.75rem;">💾 {file_size_str}</span>
                    {"<span style='margin-left:0.75rem;'>🌐 " + (meeting.get('language') or '').upper() + "</span>" if meeting.get('language') else ""}
                </div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

#Not processed yet
if status != "completed":
    if status == "failed":
        st.error(
            f"❌ Processing failed: {meeting.get('error_message', 'Unknown error')}"
        )
    else:
        st.info(
            f"⏳ This meeting is currently **{status}**. "
            "AI analysis will appear here once processing completes.",
            icon="🔄",
        )
        if st.button("🔄 Refresh", use_container_width=False):
            st.rerun()
    st.stop()

#Five tabs
tab_summary, tab_transcript, tab_actions, tab_analytics, tab_qa = st.tabs([
    "📋 Summary",
    "📝 Transcript",
    "✅ Action Items",
    "📊 Analytics",
    "💬 Q&A",
])

# TAB 1 — SUMMARY
with tab_summary:
    if not meeting.get("summary"):
        st.info("No summary available — AI processing may not have run.")
        st.stop()

    # Executive summary
    st.markdown("#### Executive Summary")
    st.markdown(
        f'<div style="background:#1a1d27;border-left:3px solid #6366f1;'
        f'border-radius:0 8px 8px 0;padding:1.25rem;line-height:1.7;color:#cbd5e1;">'
        f'{meeting["summary"]}'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Participants + decisions in two columns
    col_part, col_dec = st.columns([1, 1])

    with col_part:
        st.markdown("#### 👥 Participants")
        if participants:
            for p in participants:
                st.markdown(
                    f'<div style="background:#1a1d27;border-radius:6px;padding:0.4rem 0.75rem;'
                    f'margin-bottom:0.4rem;color:#cbd5e1;font-size:0.88rem;">👤 {p}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div style="color:#64748b;font-size:0.85rem;">No participants detected</div>', unsafe_allow_html=True)

    with col_dec:
        st.markdown("#### ✅ Key Decisions")
        if decisions:
            for d in decisions:
                st.markdown(
                    f'<div class="decision-card">'
                    f'<div style="font-weight:500;color:#e2e8f0;margin-bottom:0.3rem;">{d.get("decision","")}</div>'
                    f'<div style="font-size:0.78rem;color:#64748b;">'
                    f'<span>🧠 {d.get("rationale","")}</span> &nbsp;·&nbsp; '
                    f'<span>👤 {d.get("made_by","")}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div style="color:#64748b;font-size:0.85rem;">No decisions recorded</div>', unsafe_allow_html=True)

    # Follow-up email
    if meeting.get("follow_up_email"):
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📧 Follow-Up Email")

        col_email, col_copy = st.columns([6, 1])
        with col_email:
            st.markdown(
                f'<div class="email-box">{meeting["follow_up_email"]}</div>',
                unsafe_allow_html=True,
            )
        with col_copy:
            st.download_button(
                "⬇ Save",
                data=meeting["follow_up_email"],
                file_name=f"followup_{meeting['id'][:8]}.txt",
                mime="text/plain",
                use_container_width=True,
            )

# TAB 2 — TRANSCRIPT
with tab_transcript:
    if not meeting.get("transcript"):
        st.info("No transcript available.")
    else:
        transcript = meeting["transcript"]
        word_count = len(transcript.split())
        char_count = len(transcript)

        # Stats bar
        st.markdown(
            f'<div style="display:flex;gap:2rem;margin-bottom:1rem;font-size:0.82rem;color:#64748b;">'
            f'<span>📝 {word_count:,} words</span>'
            f'<span>🔤 {char_count:,} characters</span>'
            f'<span>🌐 {(meeting.get("language") or "unknown").upper()}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="transcript-box">{transcript}</div>',
            unsafe_allow_html=True,
        )

        st.download_button(
            "⬇ Download Transcript",
            data=transcript,
            file_name=f"transcript_{meeting['id'][:8]}.txt",
            mime="text/plain",
        )

# TAB 3 — ACTION ITEMS
with tab_actions:
    if not action_items:
        st.info("No action items found in this meeting.")
    else:
        # Filter + sort controls
        col_f1, col_f2 = st.columns([2, 2])
        with col_f1:
            owner_filter = st.text_input("Filter by owner", placeholder="Alice…", key="ai_owner")
        with col_f2:
            priority_filter = st.selectbox(
                "Filter by priority",
                ["All", "High", "Medium", "Low"],
                key="ai_priority",
            )

        filtered_actions = action_items
        if owner_filter:
            filtered_actions = [
                a for a in filtered_actions
                if owner_filter.lower() in a.get("owner", "").lower()
            ]
        if priority_filter != "All":
            filtered_actions = [
                a for a in filtered_actions
                if a.get("priority") == priority_filter
            ]

        st.markdown(
            f'<div style="color:#64748b;font-size:0.82rem;margin-bottom:1rem;">'
            f'Showing {len(filtered_actions)} of {len(action_items)} action items</div>',
            unsafe_allow_html=True,
        )

        for i, item in enumerate(filtered_actions, 1):
            priority = item.get("priority", "Medium")
            p_badge = style.priority_badge(priority)
            st.markdown(
                f'<div class="action-card">'
                f'<div class="action-card-task">{i}. {item.get("task","")}</div>'
                f'<div class="action-card-meta">'
                f'<span>👤 {item.get("owner","Unassigned")}</span>'
                f'<span>📅 {item.get("deadline","Not specified")}</span>'
                f'<span>⚡ {p_badge}</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        # Export as CSV-style text
        csv_lines = ["Task,Owner,Deadline,Priority"]
        for item in action_items:
            csv_lines.append(
                f'"{item.get("task","")}","{item.get("owner","")}","{item.get("deadline","")}","{item.get("priority","")}"'
            )
        st.download_button(
            "⬇ Export Action Items (CSV)",
            data="\n".join(csv_lines),
            file_name=f"actions_{meeting['id'][:8]}.csv",
            mime="text/csv",
        )

        # Risks section
        if risks:
            st.markdown("---")
            st.markdown("#### ⚠️ Risks & Blockers")
            for risk in risks:
                impact = risk.get("impact", "Medium")
                impact_colors = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}
                impact_color = impact_colors.get(impact, "#94a3b8")
                st.markdown(
                    f'<div class="risk-card">'
                    f'<div style="font-weight:500;color:#e2e8f0;margin-bottom:0.3rem;">{risk.get("risk","")}</div>'
                    f'<div style="font-size:0.78rem;color:#64748b;">'
                    f'<span style="color:{impact_color};font-weight:600;">● {impact} Impact</span>'
                    f' &nbsp;·&nbsp; 🛡 {risk.get("mitigation","")}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

# TAB 4 — ANALYTICS
with tab_analytics:
    if not action_items and not risks and not decisions:
        st.info("No analytics data available yet.")
    else:
        row1_col1, row1_col2 = st.columns(2)

        #Chart 1: Action items by priority
        with row1_col1:
            st.markdown("##### Action Items by Priority")
            if action_items:
                from collections import Counter
                priority_counts = Counter(a.get("priority", "Medium") for a in action_items)
                labels = ["High", "Medium", "Low"]
                values = [priority_counts.get(l, 0) for l in labels]
                colors = ["#ef4444", "#f59e0b", "#22c55e"]

                fig_p = go.Figure(data=[go.Bar(
                    x=labels, y=values,
                    marker_color=colors,
                    marker_line_width=0,
                    text=values, textposition="auto",
                )])
                fig_p.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#94a3b8",
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=240,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor="#2d3148", tickformat="d"),
                    showlegend=False,
                )
                st.plotly_chart(fig_p, use_container_width=True)
            else:
                st.markdown('<div style="color:#64748b;font-size:0.85rem;padding:2rem;text-align:center;">No action items</div>', unsafe_allow_html=True)

        #Chart 2: Risk impact distribution
        with row1_col2:
            st.markdown("##### Risk Impact Distribution")
            if risks:
                from collections import Counter
                risk_counts = Counter(r.get("impact", "Medium") for r in risks)
                labels = [k for k in risk_counts]
                values = [risk_counts[k] for k in labels]
                risk_colors = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}
                colors = [risk_colors.get(l, "#94a3b8") for l in labels]

                fig_r = go.Figure(data=[go.Pie(
                    labels=labels, values=values,
                    hole=0.5,
                    marker_colors=colors,
                    textinfo="label+value",
                    textfont_size=12,
                )])
                fig_r.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#94a3b8",
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=240,
                    showlegend=False,
                )
                st.plotly_chart(fig_r, use_container_width=True)
            else:
                st.markdown('<div style="color:#64748b;font-size:0.85rem;padding:2rem;text-align:center;">No risks identified</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        #Chart 3: Owners workload
        if action_items:
            st.markdown("##### Action Items by Owner")
            from collections import Counter
            owner_counts = Counter(
                a.get("owner", "Unassigned") for a in action_items
                if a.get("owner") and a.get("owner") != "Unassigned"
            )
            if owner_counts:
                owners = list(owner_counts.keys())
                counts = list(owner_counts.values())

                fig_o = go.Figure(data=[go.Bar(
                    x=owners, y=counts,
                    marker_color="#6366f1",
                    marker_line_width=0,
                    text=counts, textposition="auto",
                )])
                fig_o.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#94a3b8",
                    margin=dict(t=10, b=30, l=10, r=10),
                    height=220,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor="#2d3148", tickformat="d"),
                    showlegend=False,
                )
                st.plotly_chart(fig_o, use_container_width=True)

        #Summary stats
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(style.metric_card(str(len(action_items)), "Action Items"), unsafe_allow_html=True)
        with m2:
            st.markdown(style.metric_card(str(len(decisions)), "Decisions"), unsafe_allow_html=True)
        with m3:
            st.markdown(style.metric_card(str(len(risks)), "Risks"), unsafe_allow_html=True)
        with m4:
            st.markdown(style.metric_card(str(len(participants)), "Participants"), unsafe_allow_html=True)

# TAB 5 — Q&A

with tab_qa:
    if not meeting.get("transcript"):
        st.info("💬 Q&A requires a transcript. This meeting has not been transcribed yet.")
        st.stop()

    st.markdown(
        """
        <div style="background:#1e1b4b;border:1px solid #3730a3;border-radius:8px;
                    padding:0.75rem 1rem;margin-bottom:1.5rem;font-size:0.82rem;color:#a5b4fc;">
            💡 Ask anything about this meeting. Answers are grounded in the transcript —
            no hallucination. Rate limited to 10 questions per minute.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Suggested questions
    suggestions = [
        "What were the main action items?",
        "Who is responsible for the most tasks?",
        "What decisions were made?",
        "What risks were raised?",
        "What is the overall sentiment of this meeting?",
    ]

    st.markdown("**Suggested questions:**")
    sug_cols = st.columns(len(suggestions))
    for i, (col, sug) in enumerate(zip(sug_cols, suggestions)):
        with col:
            if st.button(sug, key=f"sug_{i}", use_container_width=True):
                st.session_state["qa_prefill"] = sug

    st.markdown("<br>", unsafe_allow_html=True)

    # Q&A history stored in session
    if "qa_history" not in st.session_state:
        st.session_state["qa_history"] = []
    if f"qa_history_{meeting_id}" not in st.session_state:
        st.session_state[f"qa_history_{meeting_id}"] = []

    # Display conversation history for this meeting
    history = st.session_state[f"qa_history_{meeting_id}"]
    for qa in history:
        st.markdown(
            f'<div class="qa-question">❓ {qa["question"]}</div>'
            f'<div class="qa-answer">🤖 {qa["answer"]}</div>',
            unsafe_allow_html=True,
        )

    # Input area
    prefill = st.session_state.pop("qa_prefill", "")
    with st.form("qa_form", clear_on_submit=True):
        question = st.text_input(
            "Your question",
            value=prefill,
            placeholder="What were the key decisions made in this meeting?",
            label_visibility="collapsed",
        )
        col_ask, col_clear = st.columns([3, 1])
        with col_ask:
            ask_submitted = st.form_submit_button(
                "Ask →", type="primary", use_container_width=True
            )
        with col_clear:
            clear_submitted = st.form_submit_button("Clear", use_container_width=True)

    if clear_submitted:
        st.session_state[f"qa_history_{meeting_id}"] = []
        st.rerun()

    if ask_submitted and question.strip():
        with st.spinner("Thinking…"):
            result, err = api.ask_question(token, meeting_id, question.strip())

        if err:
            st.error(f"❌ {err}")
        else:
            answer = result.get("answer", "No answer returned.")
            st.session_state[f"qa_history_{meeting_id}"].append({
                "question": question.strip(),
                "answer": answer,
            })
            st.rerun()
