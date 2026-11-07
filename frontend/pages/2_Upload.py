"""
Meeting upload page with live progress polling.
"""

import time
import streamlit as st
import api
import style

st.set_page_config(page_title="Upload · MeetingMind", page_icon="⬆️", layout="centered")

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

style.page_header("Upload Meeting", "Transcribe and analyse your recording with AI")

#Supported formats notice
st.markdown(
    """
    <div style="background:#1a1d27;border:1px solid #2d3148;border-radius:8px;
                padding:0.75rem 1rem;margin-bottom:1.5rem;font-size:0.82rem;color:#64748b;">
        🎵 Supported formats: MP3, MP4, M4A, WAV, WEBM, OGG, FLAC, OPUS &nbsp;·&nbsp;
        Max size: 100 MB
    </div>
    """,
    unsafe_allow_html=True,
)

#Upload form
# Only show the form when not currently processing
if not st.session_state.get("active_job_id"):
    with st.form("upload_form", clear_on_submit=False):
        title = st.text_input(
            "Meeting Title *",
            placeholder="Q3 Planning Session",
            max_chars=500,
        )
        description = st.text_area(
            "Description (optional)",
            placeholder="Brief context about this meeting…",
            max_chars=1000,
            height=80,
        )
        uploaded_file = st.file_uploader(
            "Audio / Video File *",
            type=["mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac", "opus", "mpeg", "mpga"],
            help="Your file is uploaded to secure cloud storage and never shared.",
        )

        col_submit, col_space = st.columns([1, 2])
        with col_submit:
            submitted = st.form_submit_button(
                "⬆️ Upload & Analyse", type="primary", use_container_width=True
            )

    if submitted:
        # Validate
        if not title.strip():
            st.error("Please enter a meeting title.")
            st.stop()
        if not uploaded_file:
            st.error("Please select an audio file.")
            st.stop()

        file_bytes = uploaded_file.read()
        content_type = uploaded_file.type or "audio/mpeg"

        with st.spinner("Uploading file…"):
            result, err = api.upload_meeting(
                token=token,
                title=title.strip(),
                description=description.strip(),
                file_bytes=file_bytes,
                filename=uploaded_file.name,
                content_type=content_type,
            )

        if err:
            st.error(f"❌ Upload failed: {err}")
            st.stop()

        # Store job info and trigger polling
        st.session_state["active_job_id"] = result["job_id"]
        st.session_state["active_meeting_id"] = result["meeting_id"]
        st.session_state["active_meeting_title"] = title.strip()
        st.rerun()

#Live progress polling
if st.session_state.get("active_job_id"):
    job_id = st.session_state["active_job_id"]
    meeting_id = st.session_state["active_meeting_id"]
    meeting_title = st.session_state.get("active_meeting_title", "Meeting")

    st.markdown(
        f"""
        <div style="text-align:center;padding:1rem 0 0.5rem;">
            <div style="font-size:1.1rem;font-weight:600;color:#e2e8f0;">
                Processing: {meeting_title}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    step_placeholder = st.empty()
    action_placeholder = st.empty()

    # Poll until terminal state
    terminal_states = {"completed", "failed"}
    max_polls = 240   # 240 × 2.5s = 10 minutes max
    poll_count = 0
    final_status = None

    while poll_count < max_polls:
        job_data, err = api.get_job_status(token, job_id)

        if err:
            status_placeholder.error(f"Could not poll job status: {err}")
            time.sleep(5)
            poll_count += 1
            continue

        status = job_data.get("status", "queued")
        progress = job_data.get("progress", 0)
        current_step = job_data.get("current_step", "…")
        error_message = job_data.get("error_message")

        # Update UI
        progress_placeholder.progress(progress / 100)

        cache_indicator = "⚡ cached" if job_data.get("source") == "cache" else "🔄 live"
        status_placeholder.markdown(
            f"""
            <div style="display:flex;justify-content:space-between;
                        align-items:center;margin:0.5rem 0;">
                <span>{style.status_badge(status)}</span>
                <span style="font-size:0.72rem;color:#475569;">{cache_indicator}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        step_placeholder.markdown(
            f'<div style="color:#94a3b8;font-size:0.85rem;text-align:center;'
            f'padding:0.5rem 0;">{current_step} — {progress}%</div>',
            unsafe_allow_html=True,
        )

        if status in terminal_states:
            final_status = status
            break

        time.sleep(2.5)
        poll_count += 1

    #Terminal state handling
    if final_status == "completed":
        progress_placeholder.progress(1.0)
        st.success("✅ Meeting processed successfully!")
        st.balloons()

        col1, col2 = action_placeholder.columns(2)
        with col1:
            if st.button("📄 View Meeting Details", type="primary", use_container_width=True):
                st.session_state["selected_meeting_id"] = meeting_id
                # Clear job state
                for k in ["active_job_id", "active_meeting_id", "active_meeting_title"]:
                    st.session_state.pop(k, None)
                st.switch_page("pages/4_Meeting_Detail.py")
        with col2:
            if st.button("⬆️ Upload Another", use_container_width=True):
                for k in ["active_job_id", "active_meeting_id", "active_meeting_title"]:
                    st.session_state.pop(k, None)
                st.rerun()

    elif final_status == "failed":
        st.error(
            f"❌ Processing failed: "
            f"{job_data.get('error_message', 'Unknown error')}"
        )
        if st.button("Try Again", use_container_width=True):
            for k in ["active_job_id", "active_meeting_id", "active_meeting_title"]:
                st.session_state.pop(k, None)
            st.rerun()

    elif poll_count >= max_polls:
        st.warning("⏰ Processing is taking longer than expected. Check Meeting History for updates.")
        if st.button("View History", use_container_width=True):
            for k in ["active_job_id", "active_meeting_id", "active_meeting_title"]:
                st.session_state.pop(k, None)
            st.switch_page("pages/3_History.py")
