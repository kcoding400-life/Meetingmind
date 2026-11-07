"""
Meeting history — searchable and filterable list of all meetings.
"""

import streamlit as st
import api
import style

st.set_page_config(page_title="History · MeetingMind", page_icon="📋", layout="wide")

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
    if st.button("Sign Out", use_container_width=True):
        for k in ["token", "user"]:
            st.session_state.pop(k, None)
        st.switch_page("app.py")

style.page_header("Meeting History", "Browse and manage all your recorded meetings")

#Load data
with st.spinner("Loading meetings…"):
    data, err = api.list_meetings(token, limit=200)

if err:
    st.error(f"Could not load meetings: {err}")
    st.stop()

meetings = data.get("meetings", [])
total = data.get("total", 0)

if not meetings:
    st.markdown(
        """
        <div style="text-align:center;padding:4rem;color:#64748b;">
            <div style="font-size:3rem;margin-bottom:1rem;">📋</div>
            <div style="font-size:1rem;font-weight:600;color:#94a3b8;">No meetings yet</div>
            <div style="font-size:0.85rem;margin-top:0.5rem;">
                Upload your first recording to see it here
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("⬆️ Upload Meeting", type="primary"):
        st.switch_page("pages/2_Upload.py")
    st.stop()

#Filters
col_search, col_status, col_sort = st.columns([3, 1.5, 1.5])

with col_search:
    search_query = st.text_input(
        "Search", placeholder="🔍 Search by title…", label_visibility="collapsed"
    )
with col_status:
    status_filter = st.selectbox(
        "Status",
        ["All", "completed", "processing", "pending", "failed"],
        label_visibility="collapsed",
    )
with col_sort:
    sort_order = st.selectbox(
        "Sort",
        ["Newest first", "Oldest first"],
        label_visibility="collapsed",
    )

#Filter+sort
filtered = meetings

if search_query:
    q = search_query.lower()
    filtered = [m for m in filtered if q in m["title"].lower()]

if status_filter != "All":
    filtered = [m for m in filtered if m["status"] == status_filter]

if sort_order == "Oldest first":
    filtered = list(reversed(filtered))

#Summary bar
st.markdown(
    f'<div style="color:#64748b;font-size:0.82rem;margin:0.75rem 0 1.25rem;">'
    f'Showing {len(filtered)} of {total} meetings'
    f'</div>',
    unsafe_allow_html=True,
)

#Meeting rows
if not filtered:
    st.info("No meetings match your filters.")
else:
    # Column headers
    hcol1, hcol2, hcol3, hcol4, hcol5 = st.columns([4, 1.5, 1.5, 1.5, 1.5])
    with hcol1:
        st.markdown('<div style="font-size:0.75rem;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Title</div>', unsafe_allow_html=True)
    with hcol2:
        st.markdown('<div style="font-size:0.75rem;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Status</div>', unsafe_allow_html=True)
    with hcol3:
        st.markdown('<div style="font-size:0.75rem;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Duration</div>', unsafe_allow_html=True)
    with hcol4:
        st.markdown('<div style="font-size:0.75rem;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Date</div>', unsafe_allow_html=True)
    with hcol5:
        st.markdown('<div style="font-size:0.75rem;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">Actions</div>', unsafe_allow_html=True)

    st.markdown('<div style="border-bottom:1px solid #2d3148;margin:0.5rem 0 0.75rem;"></div>', unsafe_allow_html=True)

    for m in filtered:
        c1, c2, c3, c4, c5 = st.columns([4, 1.5, 1.5, 1.5, 1.5])

        with c1:
            fn = m.get("file_name", "")
            st.markdown(
                f'<div style="font-weight:500;color:#e2e8f0;">{m["title"]}</div>'
                f'<div style="font-size:0.75rem;color:#475569;">{fn}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(style.status_badge(m["status"]), unsafe_allow_html=True)
        with c3:
            st.markdown(
                f'<div style="color:#94a3b8;font-size:0.85rem;">{api.format_duration(m.get("duration_seconds"))}</div>',
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f'<div style="color:#94a3b8;font-size:0.85rem;">{m["created_at"][:10]}</div>',
                unsafe_allow_html=True,
            )
        with c5:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("View", key=f"view_{m['id']}", use_container_width=True):
                    st.session_state["selected_meeting_id"] = m["id"]
                    st.switch_page("pages/4_Meeting_Detail.py")
            with btn_col2:
                if st.button("🗑", key=f"del_{m['id']}", use_container_width=True, help="Delete meeting"):
                    st.session_state[f"confirm_delete_{m['id']}"] = True

        # Confirm delete
        if st.session_state.get(f"confirm_delete_{m['id']}"):
            st.warning(f"Delete **{m['title']}**? This cannot be undone.")
            d1, d2, _ = st.columns([1, 1, 4])
            with d1:
                if st.button("Yes, delete", key=f"yes_{m['id']}", type="primary"):
                    _, del_err = api.delete_meeting(token, m["id"])
                    if del_err:
                        st.error(f"Delete failed: {del_err}")
                    else:
                        st.success("Meeting deleted.")
                        st.session_state.pop(f"confirm_delete_{m['id']}", None)
                        st.rerun()
            with d2:
                if st.button("Cancel", key=f"cancel_{m['id']}"):
                    st.session_state.pop(f"confirm_delete_{m['id']}", None)
                    st.rerun()

        st.markdown('<div style="border-bottom:1px solid #1a1d27;margin:0.3rem 0;"></div>', unsafe_allow_html=True)