"""
MeetingMind entry point — Login and Registration page.
"""
import streamlit as st
import api
import style


# Page config 
st.set_page_config(
    page_title="MeetingMind",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

style.inject_css()

# Already logged in 

if st.session_state.get("token"):
    st.switch_page("pages/1_Dashboard.py")

# Branding

st.markdown(
    """
    <div style="text-align:center; padding: 2rem 0 1.5rem;">
        <div style="font-size: 3rem; margin-bottom: 0.5rem;">🎙️</div>
        <h1 style="font-size:2rem; font-weight:700; color:#e2e8f0; margin:0;">
            MeetingMind
        </h1>
        <p style="color:#64748b; margin-top:0.4rem; font-size:0.95rem;">
            AI-powered meeting intelligence
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Login / Register tabs

tab_login, tab_register = st.tabs(["Sign In", "Create Account"])

#Login
with tab_login:
    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("login_form"):
        email = st.text_input("Email", placeholder="you@company.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

    if submitted:
        if not email or not password:
            st.error("Please enter your email and password.")
        else:
            with st.spinner("Signing in…"):
                data, err = api.login(email, password)

            if err:
                st.error(f"❌ {err}")
            else:
                st.session_state["token"] = data["access_token"]

                # Fetch user profile
                user, err2 = api.get_me(data["access_token"])
                if user:
                    st.session_state["user"] = user
                    st.success(f"Welcome back, {user['full_name'].split()[0]}!")
                    st.switch_page("pages/1_Dashboard.py")
                else:
                    st.error(f"Login succeeded but could not load profile: {err2}")

#Register
with tab_register:
    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("register_form"):
        reg_name = st.text_input("Full Name", placeholder="Alex Johnson")
        reg_email = st.text_input("Email", placeholder="alex@company.com", key="reg_email")
        reg_pass = st.text_input(
            "Password",
            type="password",
            placeholder="Min 8 chars, one uppercase, one digit",
            key="reg_pass",
        )
        reg_submitted = st.form_submit_button(
            "Create Account", use_container_width=True, type="primary"
        )

    if reg_submitted:
        if not reg_name or not reg_email or not reg_pass:
            st.error("All fields are required.")
        else:
            with st.spinner("Creating account…"):
                data, err = api.register(reg_email, reg_name, reg_pass)

            if err:
                st.error(f"❌ {err}")
            else:
                st.success("✅ Account created! Please sign in.")


# Footer
st.markdown(
    """
    <div style="text-align:center; margin-top:3rem; color:#374151; font-size:0.75rem;">
        MeetingMind · AI Meeting Intelligence
    </div>
    """,
    unsafe_allow_html=True,
)
