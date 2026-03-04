import streamlit as st
import pandas as pd
import time
from database import (init_db, verify_login, import_from_excel,
                      get_all_students, get_unpaid_students,
                      mark_paid, mark_unpaid, get_all_institutes)
from whatsapp import send_text, send_attendance_alert

st.set_page_config(page_title="CoachingBot", page_icon="🎓", layout="wide")
init_db()

# ── LOGIN GATE ───────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.institute_name = ""
    st.session_state.is_admin = False

if not st.session_state.logged_in:
    st.title("🎓 CoachingBot — Login")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("🔐 Login", type="primary", use_container_width=True):
            if username == "admin" and password == "admin@2026":
                st.session_state.logged_in = True
                st.session_state.institute_name = "ALL"
                st.session_state.is_admin = True
                st.rerun()
            else:
                result = verify_login(username, password)
                if result:
                    st.session_state.logged_in = True
                    st.session_state.institute_name = result
                    st.session_state.is_admin = False
                    st.rerun()
                else:
                    st.error("❌ Wrong username or password")
    st.stop()

# ── SIDEBAR ──────────────────────────────────────────
institute = st.session_state.institute_name
is_admin  = st.session_state.is_admin

st.sidebar.title("🎓 CoachingBot")
if is_admin:
    st.sidebar.success("👑 Super Admin")
else:
    st.sidebar.success(f"🏫 {institute}")

if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.session_state.institute_name = ""
    st.session_state.is_admin = False
    st.rerun()

# ── ADMIN PANEL ──────────────────────────────────────
if is_admin:
    st.title("👑 Super Admin Panel")
    st.markdown("---")
    st.header("🏫 All Institutes")
    institutes = get_all_institutes()
    if institutes:
        st.dataframe(pd.DataFrame(institutes), use_container_width=True)
    else:
        st.warning("No institutes yet. Run setup_institute.py to add one.")
    st.markdown("---")
    st.header("👥 All Students")
    all_students = get_all_students()
    if all_students:
        search_admin = st.text_input("🔍 Search student by name or phone")
        df_admin = pd.DataFrame(all_students)
        if search_admin:
            df_admin = df_admin[
                df_admin["name"].str.contains(search_admin, case=False, na=False) |
                df_admin["phone"].str.contains(search_admin, na=False)
            ]
        st.dataframe(df_admin, use_container_width=True)
        st.info(f"Total: {len(all_students)} students across all institutes")
    else:
        st.warning("No students found.")
    st.stop()

# ── INSTITUTE DASHBOARD ──────────────────────────────
st.title(f"🎓 {institute} — Dashboard")
st.markdown("---")

students   = get_all_students(institute)
unpaid     = get_unpaid_students(institute)
paid_count = len(students) - len(unpaid)

col1, col2, col3 = st.columns(3)
col1.metric("👥 Total Students", len(students))
col2.metric("✅ Fees Paid",       paid_count)
col3.metric("⏳ Fees Pending",    len(unpaid))

# ── SECTION 1: UPLOAD EXCEL ──────────────────────────
st.markdown("---")
st.header("📁 Import Students from Excel")
st.caption("Columns needed: name, phone, batch, fee_amount, fee_due_date")

uploaded_file = st.file_uploader("Upload .xlsx file", type=["xlsx"])
if uploaded_file:
    with open("temp_upload.xlsx", "wb") as f:
        f.write(uploaded_file.read())
    if st.button("✅ Import Now", type="primary"):
        import_from_excel("temp_upload.xlsx", institute)
        st.success("✅ Students imported!")
        st.rerun()

# ── SECTION 2: STUDENT TABLE WITH SEARCH ─────────────
st.markdown("---")
st.header("👥 Student List")

search = st.text_input("🔍 Search by name, phone or batch")

if students:
    df = pd.DataFrame(students)

    # Apply search filter
    if search:
        df = df[
            df["name"].str.contains(search, case=False, na=False)  |
            df["phone"].str.contains(search, na=False)              |
            df["batch"].str.contains(search, case=False, na=False)
        ]

    if df.empty:
        st.warning(f"No students found for '{search}'")
    else:
        display_df = df.copy()
        display_df["fee_paid"] = display_df["fee_paid"].map(
            {True: "✅ Paid", False: "❌ Pending"}
        )
        display_df = display_df.rename(columns={
            "name": "Name", "phone": "Phone", "batch": "Batch",
            "fee_amount": "Fee (₹)", "fee_due_date": "Due Date",
            "fee_paid": "Status"
        })
        display_df = display_df.drop(columns=["institute"])
        st.dataframe(display_df, use_container_width=True)
        st.caption(f"Showing {len(df)} of {len(students)} students")
else:
    st.warning("No students yet. Upload Excel above.")

# ── SECTION 3: FEE REMINDERS ─────────────────────────
st.markdown("---")
st.header("📢 Send Fee Reminders")

col1, col2 = st.columns([2, 1])
with col1:
    if st.button("🔔 Send Reminder to ALL Unpaid Students", type="primary"):
        if not unpaid:
            st.success("🎉 All fees collected!")
        else:
            bar = st.progress(0, text="Sending...")
            for i, s in enumerate(unpaid):
                message = (
                    f"📚 Fee Reminder\n\n"
                    f"Hi {s['name']}, your fee of ₹{s['fee_amount']} "
                    f"for *{s['batch']}* batch is due on {s['fee_due_date']}.\n\n"
                    f"Contact {s['institute']} to avoid late charges. 🙏"
                )
                send_text(s["phone"], message)
                time.sleep(1)
                bar.progress((i + 1) / len(unpaid),
                             text=f"Sent to {s['name']}...")
            st.success(f"✅ Reminders sent to {len(unpaid)} students!")
with col2:
    st.metric("Will receive reminder", len(unpaid))

# ── SECTION 4: MARK FEE PAID / UNPAID ───────────────
st.markdown("---")
st.header("💰 Fee Status Management")

if students:
    # Search inside this section too
    fee_search = st.text_input("🔍 Search student", key="fee_search")

    filtered = students
    if fee_search:
        filtered = [
            s for s in students
            if fee_search.lower() in s["name"].lower()
            or fee_search in s["phone"]
        ]

    if not filtered:
        st.warning(f"No student found for '{fee_search}'")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Mark as ✅ Paid")
            unpaid_filtered = [s for s in filtered if not s["fee_paid"]]
            if unpaid_filtered:
                paid_opts     = {f"{s['name']} — {s['phone']}": s["phone"]
                                 for s in unpaid_filtered}
                paid_selected = st.selectbox("Select unpaid student",
                                             list(paid_opts.keys()),
                                             key="paid_select")
                if st.button("✅ Mark as Paid", type="primary"):
                    mark_paid(paid_opts[paid_selected])
                    st.success(f"✅ {paid_selected.split('—')[0].strip()} marked as paid!")
                    st.rerun()
            else:
                st.success("🎉 All filtered students have paid!")

        with col2:
            st.subheader("Undo ↩️ Mark as Unpaid")
            paid_filtered = [s for s in filtered if s["fee_paid"]]
            if paid_filtered:
                unpaid_opts     = {f"{s['name']} — {s['phone']}": s["phone"]
                                   for s in paid_filtered}
                unpaid_selected = st.selectbox("Select paid student",
                                               list(unpaid_opts.keys()),
                                               key="unpaid_select")
                if st.button("↩️ Mark as Unpaid"):
                    mark_unpaid(unpaid_opts[unpaid_selected])
                    st.warning(f"↩️ {unpaid_selected.split('—')[0].strip()} marked as unpaid!")
                    st.rerun()
            else:
                st.info("No paid students to undo.")

# ── SECTION 5: ATTENDANCE ALERT ──────────────────────
st.markdown("---")
st.header("📋 Attendance Alert")

if students:
    att_search = st.text_input("🔍 Search absent student", key="att_search")
    att_list   = students
    if att_search:
        att_list = [
            s for s in students
            if att_search.lower() in s["name"].lower()
            or att_search in s["phone"]
        ]

    if att_list:
        att_opts = {f"{s['name']} — {s['phone']}": s for s in att_list}
        att_sel  = st.selectbox("Select absent student", list(att_opts.keys()))
        if st.button("🔴 Send Absence Alert to Parent"):
            s = att_opts[att_sel]
            send_attendance_alert(s["name"], s["phone"], s["institute"])
            st.success(f"✅ Absence alert sent for {s['name']}!")
    else:
        st.warning(f"No student found for '{att_search}'")

# ── SECTION 6: CUSTOM BROADCAST ──────────────────────
st.markdown("---")
st.header("📣 Custom Broadcast")

msg    = st.text_area("Message",
                      placeholder="Holiday notice, exam date, result update...")
target = st.radio("Send to", ["All Students", "Unpaid Only"], horizontal=True)

if st.button("📤 Send Broadcast"):
    if not msg.strip():
        st.error("Please type a message!")
    else:
        targets = students if target == "All Students" else unpaid
        bar     = st.progress(0, text="Broadcasting...")
        for i, s in enumerate(targets):
            send_text(s["phone"], msg)
            time.sleep(1)
            bar.progress((i + 1) / len(targets),
                         text=f"Sent to {s['name']}...")
        st.success(f"✅ Broadcast sent to {len(targets)} students!")

