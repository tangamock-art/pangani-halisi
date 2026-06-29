import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import io
import zipfile  # Kwa ajili ya kuunganisha ripoti kwenye ZIP
import plotly.express as px  # Maktaba kwa ajili ya Bar Graph zenye rangi na mvuto
from datetime import datetime

DB_NECTA = "mpj_necta_academic.db"

st.set_page_config(page_title="MPJ NECTA ACADEMIC SYSTEM v3.0", page_icon="🔑", layout="wide")

# 1. DATABASE SETUP & GRADING SYSTEM TABLES
def init_necta_db():
    with sqlite3.connect(DB_NECTA, timeout=30) as conn:
        c = conn.cursor()

# JEDWALI LA KALENDA YA SHULE NA KITAALUMA
        c.execute('''CREATE TABLE IF NOT EXISTS school_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT,
    event_name TEXT,
    event_type TEXT,
    description TEXT
)''')
        c.execute('''CREATE TABLE IF NOT EXISTS students (\n            reg_no TEXT PRIMARY KEY, full_name TEXT, class TEXT, gender TEXT, stream_or_comb TEXT, parent_phone TEXT)''')
        
        try:
            c.execute("SELECT stream_or_comb FROM students LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE students ADD COLUMN stream_or_comb TEXT")
            
        # Uhakiki wa Column ya namba ya simu ya mzazi
        try:
            c.execute("SELECT parent_phone FROM students LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE students ADD COLUMN parent_phone TEXT")
            
        c.execute('''CREATE TABLE IF NOT EXISTS subjects (\n            subject_code TEXT PRIMARY KEY, subject_name TEXT, is_grading INTEGER DEFAULT 1)''')
        
        try:
            c.execute("SELECT is_grading FROM subjects LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE subjects ADD COLUMN is_grading INTEGER DEFAULT 1")

        c.execute('''CREATE TABLE IF NOT EXISTS exam_scores (\n            id TEXT PRIMARY KEY, reg_no TEXT, class TEXT, exam_name TEXT, \n            subject_code TEXT, score INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS grading_system (\n            level TEXT, grade TEXT, min_score INTEGER, max_score INTEGER, points INTEGER, PRIMARY KEY (level, grade))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS users (\n            username TEXT PRIMARY KEY, password TEXT, full_name TEXT, role TEXT)''')
        
        c.execute("INSERT OR IGNORE INTO users VALUES ('admin', 'admin123', 'Administrator', 'Admin')")
        c.execute("INSERT OR IGNORE INTO users VALUES ('superadmin', 'super123', 'Super Administrator', 'Super Admin')")
        
        # Mfumo wa Settings za Ripoti pamoja na Expiry Date ya Mfumo

        c.execute('''CREATE TABLE IF NOT EXISTS report_settings (\n            id INTEGER PRIMARY KEY, waziri_header TEXT, tamisemi_header TEXT, wilaya_header TEXT, \n            shule_name TEXT, simu_mawasiliano TEXT, slp_box TEXT, default_tabia TEXT, tarehe_kufungua TEXT, maagizo_mengine TEXT, tarehe_kufunga TEXT, system_expiry TEXT)''')
        
        c.execute('''INSERT OR IGNORE INTO report_settings (id, waziri_header, tamisemi_header, wilaya_header, shule_name, simu_mawasiliano, slp_box, default_tabia, tarehe_kufungua, maagizo_mengine, tarehe_kufunga, system_expiry) \n                     VALUES (1, 'OFISI YA WAZIRI MKUU', 'TAWALA ZA MIKOA NA SERIKALI ZA MITAA', 'HALMASHAURI YA WILAYA YA PANGANI', 'PANGANI HALISI SECONDARY SCHOOL', '0715975553 / 0655402558', 'S.L.P 84, Pangani', 'NZURI', '06/07/2026', '', '05/06/2026', '2027-12-31')''')
        
        # Uhakiki wa Column Mpya ya Tarehe ya Kufunga na Expiry
        try:
            c.execute("SELECT tarehe_kufunga FROM report_settings LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE report_settings ADD COLUMN tarehe_kufunga TEXT")
            c.execute("UPDATE report_settings SET tarehe_kufunga = '05/06/2026' WHERE id=1")
            
        try:
            c.execute("SELECT system_expiry FROM report_settings LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE report_settings ADD COLUMN system_expiry TEXT")
            c.execute("UPDATE report_settings SET system_expiry = '2027-12-31' WHERE id=1")
            
        try:
            c.execute("SELECT maagizo_mengine FROM report_settings LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE report_settings ADD COLUMN maagizo_mengine TEXT")

        # Default O-Level Grades
        o_grades = [('O-LEVEL', 'A', 75, 100, 1), ('O-LEVEL', 'B', 65, 74, 2),
                    ('O-LEVEL', 'C', 45, 64, 3), ('O-LEVEL', 'D', 30, 44, 4), ('O-LEVEL', 'F', 0, 29, 5)]
        for lvl, grd, mn, mx, pt in o_grades:
            c.execute("INSERT OR IGNORE INTO grading_system VALUES (?,?,?,?,?)", (lvl, grd, mn, mx, pt))
            
        # Default A-Level Grades
        a_grades = [('A-LEVEL', 'A', 80, 100, 1), ('A-LEVEL', 'B', 70, 79, 2),
                    ('A-LEVEL', 'C', 60, 69, 3), ('A-LEVEL', 'D', 50, 59, 4),
                    ('A-LEVEL', 'E', 40, 49, 5), ('A-LEVEL', 'S', 35, 39, 6), ('A-LEVEL', 'F', 0, 34, 7)]
        for lvl, grd, mn, mx, pt in a_grades:
            c.execute("INSERT OR IGNORE INTO grading_system VALUES (?,?,?,?,?)", (lvl, grd, mn, mx, pt))

        default_subs = [("CIV", "Civics", 1), ("HIST", "History", 1), ("GEOG", "Geography", 1), 
                        ("KISW", "Kiswahili", 1), ("ENGL", "English", 1), ("MATH", "Mathematics", 1)]
        for code, name, grd_stat in default_subs:
            c.execute("INSERT OR IGNORE INTO subjects (subject_code, subject_name, is_grading) VALUES (?, ?, ?)", (code, name, grd_stat))
        conn.commit()

init_necta_db()

def get_level_by_class(class_name):
    if class_name in ["Form 5", "Form 6"]:
        return "A-LEVEL"
    return "O-LEVEL"

def get_dynamic_grade_and_point(score, class_name):
    level = get_level_by_class(class_name)
    if pd.isna(score) or score is None or score < 0:
        return None, None
    
    with sqlite3.connect(DB_NECTA) as conn:
        c = conn.cursor()
        c.execute("SELECT grade, points FROM grading_system WHERE level=? AND ? BETWEEN min_score AND max_score", (level, int(score)))
        res = c.fetchone()
        if res:
            return res[0], res[1]
    return ('F', 7 if level == "A-LEVEL" else 5)

def get_swahili_remarks(grade):
    remarks_map = {
        'A': 'Bora Sana',
        'B': 'Vizuri Sana',
        'C': 'Vizuri',
        'D': 'Inaridhisha',
        'E': 'Inaridhisha Kidogo',
        'S': 'Ameshinda Kidogo',
        'F': 'Hairidhishi'
    }
    return remarks_map.get(grade, '-')

def calculate_necta_division(points_list, class_name):
    level = get_level_by_class(class_name)
    valid_points = [p for p in points_list if p is not None and p > 0]
    
    if level == "O-LEVEL":
        if len(valid_points) < 7:
            return "INC", "-"
        valid_points.sort()
        best_points = sum(valid_points[:7])
        
        if best_points >= 7 and best_points <= 17: return "I", best_points
        elif best_points >= 18 and best_points <= 21: return "II", best_points
        elif best_points >= 22 and best_points <= 25: return "III", best_points
        elif best_points >= 26 and best_points <= 34: return "IV", best_points
        else: return "0", best_points
    else:
        if len(valid_points) < 3:
            return "INC", "-"
        valid_points.sort()
        best_points = sum(valid_points[:3])
        
        if best_points >= 3 and best_points <= 9: return "I", best_points
        elif best_points >= 10 and best_points <= 12: return "II", best_points
        elif best_points >= 13 and best_points <= 17: return "III", best_points
        elif best_points >= 18 and best_points <= 19: return "IV", best_points
        else: return "0", best_points

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.session_state['user_role'] = ""
    st.session_state['full_name'] = ""
    st.session_state['student_reg'] = ""

# Uhakiki wa usajili wa mfumo (Countdown & Expiry)
def check_system_status():
    with sqlite3.connect(DB_NECTA) as conn:
        res = pd.read_sql_query("SELECT system_expiry FROM report_settings WHERE id=1", conn)
        if not res.empty and res.iloc[0]['system_expiry']:
            expiry_str = res.iloc[0]['system_expiry']
            try:
                expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                today = datetime.now().date()
                days_left = (expiry_date - today).days
                return days_left, expiry_date
            except:
                return 30, datetime.now().date()
    return 30, datetime.now().date()

days_remaining, end_date = check_system_status()


# =====================================================================
# LOGIN SCREEN & EXPIRY BLOCK LOGIC (IMELINDWA KWA MA-USER NA ADMIN)
# =====================================================================
if not st.session_state['logged_in']:
    st.markdown("<h2 style='text-align: center; color: #1e3a8a;'> MPJ INTEGRATED ACADEMIC SYSTEM</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Ingiza nenosiri lako na jina la mtumiaji kuingia kwenye mfumo au Chagua Portal ya Wanafunzi</p>", unsafe_allow_html=True)
    
    # Tukio la kuonyesha onyo kama mfumo umeisha kabla ya ku-log in
    if days_remaining <= 0:
        st.error(f"❌ Mfumo umefikia kikomo cha matumizi yake ({end_date}). Ni Super Admin tu anayeruhusiwa kuingia kufanya marekebisho piga 0655402558.")
        
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            login_role = st.selectbox("Aina ya Mtumiaji (Role)", ["Staff (Admin/Teacher)", "Student / Parent Portal"])
            user_input = st.text_input("Username (Acha wazi kama wewe ni Mwanafunzi/Mzazi)").strip()
            pass_input = st.text_input("Password / Namba ya Usajili ya Mwanafunzi", type="password")
            submit_login = st.form_submit_button("Ingia Mfumoni 🚀", use_container_width=True)
            
            if submit_login:
                if login_role == "Student / Parent Portal":
                    # Mwanafunzi ana-login kwa kutumia Namba ya Usajili (Reg No) kama Password tu
                    if not pass_input.strip():
                        st.error("❌ Tafadhali ingiza Namba ya Usajili ya mwanafunzi kwenye sehemu ya Password!")
                    else:
                        with sqlite3.connect(DB_NECTA) as conn:
                            c = conn.cursor()
                            c.execute("SELECT reg_no, full_name FROM students WHERE reg_no=?", (pass_input.strip(),))
                            res_stud = c.fetchone()
                            if res_stud:
                                st.session_state['logged_in'] = True
                                st.session_state['username'] = res_stud[0]
                                st.session_state['full_name'] = res_stud[1]
                                st.session_state['user_role'] = 'Student/Parent'
                                st.session_state['student_reg'] = res_stud[0]
                                st.success(f"🔑 Karibu {res_stud[1]} kwenye Portal ya Matokeo.")
                                st.rerun()
                            else:
                                st.error("❌ Namba ya mwanafunzi haijapatikana kwenye mfumo! Hakiki vizuri.")
                else:
                    # Mfumo wa kawaida wa Login ya Staff
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        c.execute("SELECT username, full_name, role FROM users WHERE username=? AND password=?", (user_input, pass_input))
                        res = c.fetchone()
                        if res:
                            fetched_role = res[2]
                            
                            # Kagua kama mfumo umeisha muda wake
                            if days_remaining <= 0:
                                if fetched_role == 'Super Admin':
                                    st.session_state['logged_in'] = True
                                    st.session_state['username'] = res[0]
                                    st.session_state['full_name'] = res[1]
                                    st.session_state['user_role'] = fetched_role
                                    st.success("🔑 Karibu Super Admin. Mfumo umeisha muda, tafadhali nenda kwenye 'Super Admin Control Panel' kusasisha tarehe.")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Mfumo umefungwa kwa sababu muda wake wa matumizi umeisha ({end_date}). Wasiliana na Super Admin kurefusha muda.")
                            else:
                                st.session_state['logged_in'] = True
                                st.session_state['username'] = res[0]
                                st.session_state['full_name'] = res[1]
                                st.session_state['user_role'] = fetched_role
                                st.rerun()
                        else:
                            st.error("❌ Username au Password sio sahihi!")
    st.stop()

# BLOCK YA USALAMA: Kama mtumiaji alikuwa ndani na mfumo ukaisha muda ukiwa hewani
if days_remaining <= 0 and st.session_state['user_role'] not in ['Super Admin', 'Student/Parent']:
    st.error(f"❌ Kikomo cha matumizi kimefikiwa ({end_date}). Mfumo umefungwa kwa sasa.")
    if st.sidebar.button("🚪 Log Out", use_container_width=True):
        st.session_state['logged_in'] = False
        st.rerun()
    st.stop()

# SIDEBAR NAV
st.sidebar.markdown(f"<h3 style='color:#1e3a8a; text-align:center;'> MPJ MIFUMO MASHULENI</h3>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='text-align:center; font-weight:bold;'>👤 {st.session_state['full_name']} ({st.session_state['user_role']})</p>", unsafe_allow_html=True)

# Muonekano wa Countdown ya siku kwenye Sidebar kwa kila mtu
if st.session_state['user_role'] != 'Student/Parent':
    if days_remaining <= 14:
        st.sidebar.error(f"⚠️ Mfumo utafungwa baada ya siku: {days_remaining}")
    else:
        st.sidebar.info(f"⏳ Siku zilizobaki kutumia mfumo: {days_remaining}")

st.sidebar.markdown("---")

ALL_CLASSES = ["Form 1", "Form 2", "Form 3", "Form 4", "Form 5", "Form 6"]

EXAMS_LIST = [
    "Test 1", "Test 2", "Test 3", 
    "Test 4", "Test 5", "Test 6",
    "Mid-Term 1", "Mid-Term 2", 
    "Terminal Exam 1", "Terminal Exam 2", 
    "Annual Exam / Pre-National", "National Exam Simulation"
]

if st.session_state['user_role'] == 'Super Admin':
    menu = [
        "📊 Dashboard & Status",
        "🔑 Super Admin Control Panel",
        "👥 Daftari la Wanafunzi",
        "📝 Jaza Alama (Marks Entry)",
        "🖨️ ISAL, CAL and sitting plan",
        "📜 Mkeka wa Matokeo",
        "📄 Ripoti za Wanafunzi (Report Cards)",
        "📈 Continuous Assessment (CA) Tracker",
        "📚 Sajili Masomo Yako",
        "⚙️ Grading Config",
        "🎓 Promote Wanafunzi",
        "⚙️ Ripoti Settings",
        "📅 Ratiba ya Zamu za Walimu",
        "📅 Kalenda ya Shule",
        "🔐 Manage Teachers Credentials"
        
    ]
elif st.session_state['user_role'] == 'Admin':
    menu = [
        "📊 Dashboard & Status",
        "👥 Daftari la Wanafunzi",
        "📝 Jaza Alama (Marks Entry)",
        "🖨️ ISAL, CAL and sitting plan",
        "📜 Mkeka wa Matokeo",
        "📄 Ripoti za Wanafunzi (Report Cards)",
        "📈 Continuous Assessment (CA) Tracker",
        "📚 Sajili Masomo Yako",
        "⚙️ Grading Config",
        "🎓 Promote Wanafunzi",
        "⚙️ Ripoti Settings",
        "📅 Ratiba ya Zamu za Walimu",
        "📅 Kalenda ya Shule",
        "🔐 Manage Teachers Credentials"
       
    ]
elif st.session_state['user_role'] == 'Teacher':
    menu = [
        "📊 Dashboard & Status",
        "📝 Jaza Alama (Marks Entry)",
        "📜 Mkeka wa Matokeo",
        "📄 Ripoti za Wanafunzi (Report Cards)",
        "📈 Continuous Assessment (CA) Tracker",
        "📅 Ratiba ya Zamu za Walimu",
        "📅 Kalenda ya Shule"

        
    ]
else:
    # Menu pekee ya Mwanafunzi au Mzazi
    menu = ["👨‍👩‍👦 Angalia Matokeo Yako"]

choice = st.sidebar.radio("CHAGUA KITENDO:", menu)

# Kitufe cha Log Out na Mawasiliano ya IT Chini Yake
if st.sidebar.button("🚪 Log Out", use_container_width=True):
    st.session_state['logged_in'] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("<div style='text-align: center; color: #6b7280; font-size: 13px;'>🛠️ IT Support / Developer:</div>", unsafe_allow_html=True)
st.sidebar.markdown("<div style='text-align: center; color: #1e3a8a; font-weight: bold; font-size: 15px;'>📞 0655402558</div>", unsafe_allow_html=True)

# ----------------- MODULI MPYA: PORTAL YA MWANAFUNZI / MZAZI -----------------
if choice == "👨‍👩‍👦 Angalia Matokeo Yako":
    s_reg = st.session_state['student_reg']
    
    with sqlite3.connect(DB_NECTA) as conn:
        c = conn.cursor()
        c.execute("SELECT reg_no, full_name, class, gender, stream_or_comb FROM students WHERE reg_no=?", (s_reg,))
        row_st = c.fetchone()
        
        df_subs_active = pd.read_sql_query("SELECT subject_code, subject_name, is_grading FROM subjects", conn)
        cfg_res = pd.read_sql_query("SELECT * FROM report_settings WHERE id=1", conn)
        cfg = cfg_res.iloc[0] if not cfg_res.empty else {}
        
    if not row_st:
        st.error("Taarifa zako hazikupatikana kwa sasa.")
    else:
        f_class = row_st[2]
        s_sex = row_st[3]
        s_stream = row_st[4] if row_st[4] else "A"
        safe_student_name = str(row_st[1]).upper()
        
        # Sehemu kuu moja tu ya taarifa na uchaguzi
        st.markdown(f"### Karibu kwenye Portal ya Matokeo: **{safe_student_name}**")
        st.info(f"Namba ya Usajili: {s_reg} | Darasa: {f_class} | Mkondo/Kombinisho: {s_stream}")
        st.markdown("---")
        
        # Radio button moja tu ya uhakika yenye key mpya kabisa ya kipekee
        aina_ya_muonekano = st.radio(
            "Chagua Namna ya Kuangalia Matokeo:",
            ["📊 Matokeo ya Mtihani Mmoja", "📄 Ripoti Kamili ya Muhula (Mitihani 3)"],
            key="unique_portal_view_option"
        )
        st.markdown("---")
        
        if aina_ya_muonekano == "📊 Matokeo ya Mtihani Mmoja":
            # ---------------- MUONEKANO WA MTIHANI MMOJA TU ----------------
            selected_single_exam = st.selectbox("Chagua Mtihani Unakaotaka Kuangalia:", EXAMS_LIST, key="single_exam_select_opt")
            
            with sqlite3.connect(DB_NECTA) as conn:
                df_all_class_studs = pd.read_sql_query("SELECT reg_no, stream_or_comb FROM students WHERE class=?", conn, params=(f_class,))
                df_all_scores = pd.read_sql_query("SELECT reg_no, subject_code, score FROM exam_scores WHERE class=? AND exam_name=?", conn, params=(f_class, selected_single_exam))
            
            stud_totals_single = {}
            for idx, r_bulk in df_all_class_studs.iterrows():
                r_no = r_bulk['reg_no']
                st_sc = df_all_scores[df_all_scores['reg_no'] == r_no]
                valid_scores = st_sc['score'].dropna().tolist()
                stud_totals_single[r_no] = sum(valid_scores) if valid_scores else 0
                
            rank_df_single = pd.DataFrame(list(stud_totals_single.items()), columns=['reg_no', 'total_score'])
            rank_df_single = pd.merge(rank_df_single, df_all_class_studs, on='reg_no')
            rank_df_single['class_rank'] = rank_df_single['total_score'].rank(ascending=False, method='min')
            rank_df_single['stream_rank'] = rank_df_single.groupby('stream_or_comb')['total_score'].rank(ascending=False, method='min')
            
            current_student_rank = rank_df_single[rank_df_single['reg_no'] == s_reg].iloc[0]
            pos_class = int(current_student_rank['class_rank'])
            pos_stream = int(current_student_rank['stream_rank'])
            tot_class = len(rank_df_single)
            tot_stream = len(rank_df_single[rank_df_single['stream_or_comb'] == s_stream])
            
            st.markdown(f"##### 📊 Jedwali la Alama - {selected_single_exam}")
            
            rows_single = []
            st_sc_current = df_all_scores[df_all_scores['reg_no'] == s_reg]
            
            for r_na, sub_row in df_subs_active.iterrows():
                code = sub_row['subject_code']
                name = sub_row['subject_name']
                
                match_score = st_sc_current[st_sc_current['subject_code'] == code]
                score_val = match_score.iloc[0]['score'] if not match_score.empty and not pd.isna(match_score.iloc[0]['score']) else None
                
                score_str = str(int(score_val)) if score_val is not None else "-"
                grd, pt = get_dynamic_grade_and_point(score_val if score_val is not None else -1, f_class)
                if score_val == -1 or score_val is None: grd = "-"
                
                rem = get_swahili_remarks(grd)
                rows_single.append({
                    "Na": r_na + 1,
                    "Somo": name,
                    "Alama (%)": score_str,
                    "Gredi": grd,
                    "Maoni": rem
                })
                
            st.dataframe(pd.DataFrame(rows_single), use_container_width=True, hide_index=True)
            
            col_rk1, col_rk2 = st.columns(2)
            with col_rk1:
                st.metric(label="Nafasi Darasani (Class Rank)", value=f"{pos_class} kati ya {tot_class}")
            with col_rk2:
                st.metric(label="Nafasi Kwenye Mkondo (Stream Rank)", value=f"{pos_stream} kati ya {tot_stream}")
                
        else:
            # ---------------- MUONEKANO WA RIPOTI NZIMA (MITIHANI 3) ----------------
            st.markdown("##### 📄 Sanidi Mitihani Itakayounda Ripoti Kamili")
            col_ex1, col_ex2, col_ex3 = st.columns(3)
            with col_ex1: ex_jaribio = st.selectbox("1. Jaribio (100%):", EXAMS_LIST, key="exam_j_select_opt")
            with col_ex2: ex_midterm = st.selectbox("2. 1/2 Muhula (100%):", EXAMS_LIST, key="exam_m_select_opt")
            with col_ex3: ex_final = st.selectbox("3. Mtihani wa Mwisho (100%):", EXAMS_LIST, key="exam_f_select_opt")
            
            tengeneza_ripoti = st.button("📄 Tengeneza na Angalia Ripoti", type="primary", key="btn_gen_report_opt")
            
            if tengeneza_ripoti:
                with sqlite3.connect(DB_NECTA) as conn:
                    df_all_class_studs = pd.read_sql_query("SELECT reg_no, full_name, stream_or_comb FROM students WHERE class=?", conn, params=(f_class,))
                    df_all_scores = pd.read_sql_query("SELECT reg_no, exam_name, subject_code, score FROM exam_scores WHERE class=?", conn, params=(f_class,))
                    
                stud_totals_bulk = {}
                for idx, r_bulk in df_all_class_studs.iterrows():
                    r_no = r_bulk['reg_no']
                    st_sc = df_all_scores[df_all_scores['reg_no'] == r_no]
                    total_marks, sub_count = 0, 0
                    for code in df_subs_active['subject_code'].tolist():
                        sc_sub = st_sc[st_sc['subject_code'] == code]
                        sc_j = sc_sub[sc_sub['exam_name'] == ex_jaribio]
                        sc_m = sc_sub[sc_sub['exam_name'] == ex_midterm]
                        sc_f = sc_sub[sc_sub['exam_name'] == ex_final]
                        
                        v_j = sc_j.iloc[0]['score'] if not sc_j.empty and not pd.isna(sc_j.iloc[0]['score']) else None
                        v_m = sc_m.iloc[0]['score'] if not sc_m.empty and not pd.isna(sc_m.iloc[0]['score']) else None
                        v_f = sc_f.iloc[0]['score'] if not sc_f.empty and not pd.isna(sc_f.iloc[0]['score']) else None
                        
                        valid_vals = [v for v in [v_j, v_m, v_f] if v is not None]
                        if valid_vals:
                            total_marks += (sum(valid_vals) / len(valid_vals))
                            sub_count += 1
                    stud_totals_bulk[r_no] = total_marks if sub_count > 0 else 0
                    
                rank_df_bulk = pd.DataFrame(list(stud_totals_bulk.items()), columns=['reg_no', 'total_score'])
                rank_df_bulk = pd.merge(rank_df_bulk, df_all_class_studs, on='reg_no')
                rank_df_bulk['class_rank'] = rank_df_bulk['total_score'].rank(ascending=False, method='min')
                rank_df_bulk['stream_rank'] = rank_df_bulk.groupby('stream_or_comb')['total_score'].rank(ascending=False, method='min')
                
                current_student_rank = rank_df_bulk[rank_df_bulk['reg_no'] == s_reg].iloc[0]
                pos_class = int(current_student_rank['class_rank'])
                pos_stream = int(current_student_rank['stream_rank'])
                tot_class = len(rank_df_bulk)
                tot_stream = len(rank_df_bulk[rank_df_bulk['stream_or_comb'] == s_stream])
                
                report_table_rows_html = ""
                student_total_marks, grading_subjects_count = 0, 0
                points_for_div = []
                
                st_sc = df_all_scores[df_all_scores['reg_no'] == s_reg]
                
                for r_na, sub_row in df_subs_active.iterrows():
                    code = sub_row['subject_code']
                    name = sub_row['subject_name']
                    is_grd_status = sub_row['is_grading']
                    
                    sc_sub = st_sc[st_sc['subject_code'] == code]
                    sc_j = sc_sub[sc_sub['exam_name'] == ex_jaribio]
                    sc_m = sc_sub[sc_sub['exam_name'] == ex_midterm]
                    sc_f = sc_sub[sc_sub['exam_name'] == ex_final]
                    
                    v_j = sc_j.iloc[0]['score'] if not sc_j.empty and not pd.isna(sc_j.iloc[0]['score']) else None
                    v_m = sc_m.iloc[0]['score'] if not sc_m.empty and not pd.isna(sc_m.iloc[0]['score']) else None
                    v_f = sc_f.iloc[0]['score'] if not sc_f.empty and not pd.isna(sc_f.iloc[0]['score']) else None
                    
                    vals = [v for v in [v_j, v_m, v_f] if v is not None]
                    v_avg = sum(vals)/len(vals) if vals else 0
                    
                    v_j_str = str(int(v_j)) if v_j is not None else "-"
                    v_m_str = str(int(v_m)) if v_m is not None else "-"
                    v_f_str = str(int(v_f)) if v_f is not None else "-"
                    v_avg_str = f"{v_avg:.1f}" if vals else "-"
                    
                    grd, pt = get_dynamic_grade_and_point(v_avg if vals else -1, f_class)
                    if not vals: grd, pt = "-", None
                    
                    if pt is not None and is_grd_status == 1:
                        points_for_div.append(pt)
                        student_total_marks += v_avg
                        grading_subjects_count += 1
                        
                    rem = get_swahili_remarks(grd)
                    sgn_str = grd if grd != "-" else ""
                    
                    report_table_rows_html += f"<tr><td>{r_na+1}</td><td style='font-weight:600;'>{name}</td><td style='text-align:center;'>{v_j_str}</td><td style='text-align:center;'>{v_m_str}</td><td style='text-align:center;'>{v_f_str}</td><td style='text-align:center; font-weight:bold; color:#1e3a8a;'>{v_avg_str}</td><td style='text-align:center; font-weight:bold;'>{grd}</td><td style='text-align:center;'>{sgn_str}</td><td style='font-size:10px; color:#4b5563;'>{rem}</td></tr>"
                    
                final_gpa = (student_total_marks / grading_subjects_count) if grading_subjects_count > 0 else 0
                final_class_grade, _ = get_dynamic_grade_and_point(final_gpa if grading_subjects_count > 0 else -1, f_class)
                if grading_subjects_count == 0: final_class_grade = "-"
                
                final_div, final_aggt = calculate_necta_division(points_for_div, f_class)
                
                mwl_maoni, mkuu_maoni, status_faulu = "", "", ""
                if final_div in ["I", "II", "III"]:
                    mwl_maoni = "Amefanya vizuri sana. Aendelee kudumisha juhudi hizi."
                    mkuu_maoni = "Ufaulu wake ni mzuri sana. Hongera kwa juhudi hizi!"
                    status_faulu = "AMEFAULU"
                elif final_div == "IV":
                    mwl_maoni = "Ufaulu wake ni wa kuridhisha lakini ana uwezo wa vizuri zaidi."
                    mkuu_maoni = "Nafasi ya kurekebisha ipo, akaze buti zaidi."
                    status_faulu = "AMEFAULU"
                else:
                    mwl_maoni = "Ufaulu wake hauridhishi kabisa. Anahitaji kuongeza juhudi maradufu."
                    mkuu_maoni = "Ufaulu wake si mzuri, asome sana na wenzie wenye uwezo."
                    status_faulu = "AKAZE BUTI"
                    
                h_waziri = str(cfg.get('waziri_header','')).upper()
                h_tamisemi = str(cfg.get('tamisemi_header','')).upper()
                h_wilaya = str(cfg.get('wilaya_header','')).upper()
                h_shule = str(cfg.get('shule_name','')).upper()
                h_phone = str(cfg.get('simu_mawasiliano',''))
                h_box = str(cfg.get('slp_box',''))
                h_kufungua = str(cfg.get('tarehe_kufungua',''))
                h_kufunga = str(cfg.get('tarehe_kufunga','')) if cfg.get('tarehe_kufunga','') else "-"
                h_tabia_val = str(cfg.get('default_tabia','')).upper()
                h_maagizo_mengine = str(cfg.get('maagizo_mengine','')) if cfg.get('maagizo_mengine','') else ""
                
                report_print_html = f"""
                <html>
                <head>
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; color: #1f2937; background-color: #f3f4f6; line-height: 1.4; }}
                    .report-wrapper {{ max-width: 900px; margin: 0 auto; background-color: #fff; border: 3px double #1e3a8a; padding: 30px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-radius: 8px; }}
                    .no-print-btn {{ background-color: #2563eb; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: background 0.2s; }}
                    .no-print-btn:hover {{ background-color: #1d4ed8; }}
                    .header-title {{ text-align: center; font-weight: 700; font-size: 14px; margin: 0; padding: 1px; letter-spacing: 0.5px; color: #374151; }}
                    .school-name {{ text-align: center; font-weight: 800; font-size: 22px; color: #1e3a8a; margin: 5px 0; letter-spacing: 1px; }}
                    .school-contact {{ text-align: center; font-size: 11px; font-weight: 600; color: #6b7280; margin-bottom: 10px; }}
                    .report-title {{ text-align: center; font-size: 15px; font-weight: 700; margin: 15px 0; text-transform: uppercase; color: #1e3a8a; border-bottom: 2px solid #1e3a8a; display: inline-block; width: 100%; padding-bottom: 5px; }}
                    
                    .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; background: #f8fafc; padding: 15px; border-radius: 6px; border: 1px solid #e2e8f0; }}
                    .info-item {{ font-size: 13px; }}
                    .highlight-text {{ font-weight: bold; color: #0f172a; }}
                    
                    .main-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }}
                    .main-table th {{ background-color: #1e3a8a; color: white; font-weight: 600; text-transform: uppercase; font-size: 11px; padding: 8px; border: 1px solid #1e3a8a; }}
                    .main-table td {{ border: 1px solid #e2e8f0; padding: 7px 8px; text-align: left; }}
                    .main-table tr:nth-child(even) {{ background-color: #f8fafc; }}
                    
                    .summary-card {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 15px; border-radius: 6px; margin-top: 15px; font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
                    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 8px; }}
                    .badge-white {{ background: white; color: #1e3a8a; padding: 2px 6px; border-radius: 4px; font-weight: bold; }}
                    
                    .comments-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }}
                    .comments-table td {{ border: 1px solid #e2e8f0; padding: 10px; vertical-align: top; }}
                    .section-lbl {{ font-weight: bold; background-color: #f1f5f9; width: 25%; color: #334155; }}
                    .sig-space {{ margin-top: 20px; font-style: italic; color: #64748b; font-size: 11px; text-align: right; }}
                    
                    .footer-notes {{ border-left: 4px solid #1e3a8a; background: #f8fafc; padding: 10px 15px; margin-top: 15px; font-size: 11px; border-radius: 0 6px 6px 0; border-top: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }}
                    
                    @media print {{
                        body {{ background-color: #fff; padding: 0; }}
                        .report-wrapper {{ border: none; box-shadow: none; padding: 0; max-width: 100%; }}
                        .no-print-btn {{ display: none !important; }}
                    }}
                </style>
                </head>
                <body>
                    <div style="text-align: center;">
                        <button class="no-print-btn" onclick="window.print()">📥 Pakua Ripoti ya Mwanafunzi (PDF) / Print</button>
                    </div>
                    
                    <div class="report-wrapper">
                        <div class="header-title">{h_waziri}</div>
                        <div class="header-title">{h_tamisemi}</div>
                        <div class="header-title">{h_wilaya}</div>
                        <div class="school-name">{h_shule}</div>
                        <div class="school-contact">SLP: {h_box} | SIMU MAWASILIANO: {h_phone}</div>
                        
                        <div class="report-title">RIPOTI YA MAENDELEO YA TAALUMA NA TABIA - {str(f_class).upper()}</div>
                        
                        <div class="info-grid">
                            <div class="info-item"> JINA: <span class="highlight-text">{safe_student_name}</span></div>
                            <div class="info-item"> NAMBA YA USAJILI: <span class="highlight-text">{s_reg}</span></div>
                            <div class="info-item"> JINSIA: <span class="highlight-text">{s_sex}</span></div>
                            <div class="info-item"> MKONDO / COMB: <span class="highlight-text">{str(s_stream).upper()}</span></div>
                        </div>
                        
                        <table class="main-table">
                            <thead>
                                <tr>
                                    <th style="width: 5%;">NA</th>
                                    <th style="width: 35%;">SOMO</th>
                                    <th style="text-align:center; width: 10%;">JARIBIO</th>
                                    <th style="text-align:center; width: 10%;">1/2 MUHULA</th>
                                    <th style="text-align:center; width: 10%;">MTIHANI</th>
                                    <th style="text-align:center; width: 10%;">WASTANI</th>
                                    <th style="text-align:center; width: 8%;">GREDI</th>
                                    <th style="text-align:center; width: 5%;">SGN</th>
                                    <th style="width: 17%;">MAONI MAFUPI</th>
                                </tr>
                            </thead>
                            <tbody>
                                {report_table_rows_html}
                            </tbody>
                        </table>
                        
                        <div class="summary-card">
                            <strong>A: TATHMINI YA JUMLA YA TAALUMA</strong><br>
                            Jumla ya Alama: <strong>{student_total_marks:.1f}</strong> &nbsp;|&nbsp; Wastani: <strong>{final_gpa:.1f}</strong> &nbsp;|&nbsp; Daraja la Wastani: <strong>{final_class_grade}</strong>
                            <div class="summary-grid">
                                <div>Nafasi Darasani: <span class="badge-white">{pos_class} / {tot_class}</span></div>
                                <div>Nafasi Mkondo: <span class="badge-white">{pos_stream} / {tot_stream}</span></div>
                                <div>Uamuzi: <span class="badge-white">DIV {final_div} ({final_aggt} PTS)</span></div>
                            </div>
                            <div style="margin-top: 8px; font-weight: bold; text-align: center; letter-spacing: 1px;">
                                HALI YA UFAULU: <span style="background: white; color: #1e3a8a; padding: 2px 10px; border-radius: 4px;">{status_faulu}</span>
                            </div>
                        </div>
                        
                        <table class="comments-table">
                            <tr>
                                <td class="section-lbl">1. TABIA NA MWENENDO</td>
                                <td>Mwanafunzi huyu ana tabia: <strong>{h_tabia_val}</strong>.</td>
                            </tr>
                            <tr>
                                <td class="section-lbl">2. MAONI YA MWALIMU WA DARASA</td>
                                <td>
                                    {mwl_maoni}
                                    <div class="sig-space">Sahihi ya Mwalimu wa Darasa: .......................................</div>
                                </td>
                            </tr>
                            <tr>
                                <td class="section-lbl">3. MAONI YA MKUU WA SHULE</td>
                                <td>
                                    {mkuu_maoni}
                                    <div class="sig-space">Sahihi na Muhuri wa Mkuu wa Shule: .......................................</div>
                                </td>
                            </tr>
                        </table>
                        
                        <div class="footer-notes">
                            <strong style="color: #1e3a8a;">⚠️ TAARIFA NA MAAGIZO YA SHULE:</strong><br>
                            1. Shule imefungwa rasmi leo tarehe: <strong>{h_kufunga}</strong>.<br>
                            2. Shule itafunguliwa rasmi tarehe: <strong>{h_kufungua}</strong>.<br>
                            {f'3. Maagizo ya ziada: {h_maagizo_mengine}' if h_maagizo_mengine else ''}
                        </div>
                    </div>
                </body>
                </html>
                """
                st.components.v1.html(report_print_html, height=850, scrolling=True)



# ----------------- MODULI YA DASHBOARD (KIDIGITALI NA KISASA ZAIDI) -----------------
elif choice == "📊 Dashboard & Status":
    with sqlite3.connect(DB_NECTA) as conn:
        res_shule = pd.read_sql_query("SELECT shule_name FROM report_settings WHERE id=1", conn)
        jina_la_shule = res_shule.iloc[0]['shule_name'] if not res_shule.empty else "MPJ INTEGRATED SCHOOL"
        
        # Data za haraka kwa ajili ya Kadi za Takwimu (KPI Cards)
        tot_studs_all = pd.read_sql_query("SELECT COUNT(*) as count FROM students", conn).iloc[0]['count']
        tot_subs_all = pd.read_sql_query("SELECT COUNT(*) as count FROM subjects", conn).iloc[0]['count']
        tot_users_all = pd.read_sql_query("SELECT COUNT(*) as count FROM users", conn).iloc[0]['count']
        
    st.markdown(f"<h1 style='color:#1e3a8a; text-align: center; margin-bottom: 0px;'> {jina_la_shule.upper()}</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='color:#4b5563; text-align: center; margin-top: 5px;'>📊 Live Data Entry & Academic Dashboard</h3>", unsafe_allow_html=True)
    st.markdown("---")
    
    # MUONEKANO MPYA WA KISASA: Kadi za Takwimu Kuu (KPIs Layout)
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.markdown(f"<div style='background: linear-gradient(135deg, #1e3a8a, #3b82f6); padding: 20px; border-radius: 10px; color: white; text-align: center;'><h3>👥 Wanafunzi</h3><h2>{tot_studs_all}</h2><p>Waliosajiliwa</p></div>", unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"<div style='background: linear-gradient(135deg, #10b981, #059669); padding: 20px; border-radius: 10px; color: white; text-align: center;'><h3>📚 Masomo</h3><h2>{tot_subs_all}</h2><p>Yaliyosajiliwa</p></div>", unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"<div style='background: linear-gradient(135deg, #f59e0b, #d97706); padding: 20px; border-radius: 10px; color: white; text-align: center;'><h3>👤 Watumiaji</h3><h2>{tot_users_all}</h2><p>Walimu</p></div>", unsafe_allow_html=True)
    with kpi4:
        bg_expiry = "linear-gradient(135deg, #ef4444, #dc2626)" if days_remaining <= 14 else "linear-gradient(135deg, #6366f1, #4f46e5)"
        st.markdown(f"<div style='background: {bg_expiry}; padding: 20px; border-radius: 10px; color: white; text-align: center;'><h3>⏳Zimebaki siku</h3><h2>{days_remaining}</h2><p>Mwisho: {end_date}</p></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    # KIPENGELE KIPYA: Tabs za usajili wa wanafunzi kwa kila darasa kwenye Dashboard
    st.markdown("### 📁 Hali ya Usajili wa Wanafunzi kwa Kila Darasa")
    dash_tabs = st.tabs([f"📁 {cls}" for cls in ALL_CLASSES])
    
    for i, cls_name in enumerate(ALL_CLASSES):
        with dash_tabs[i]:
            with sqlite3.connect(DB_NECTA) as conn:
                df_cls_studs = pd.read_sql_query("SELECT reg_no as 'CNO', full_name as 'JINA KAMILI', gender as 'JINSIA', stream_or_comb as 'MKONDO/COMB', parent_phone as 'SIMU YA MZAZI' FROM students WHERE class=?", conn, params=(cls_name,))
            
            total_in_class = len(df_cls_studs)
            
            col_t1, col_t2, col_t3 = st.columns([1, 1, 2])
            with col_t1:
                st.metric(label=f"Jumla ya Wanafunzi ({cls_name})", value=total_in_class)
            with col_t2:
                me_count = len(df_cls_studs[df_cls_studs['JINSIA'] == 'M'])
                ke_count = len(df_cls_studs[df_cls_studs['JINSIA'] == 'F'])
                st.write(f"👦 **Wanaume (M):** {me_count}")
                st.write(f"👧 **Wanawake (F):** {ke_count}")
                
            if total_in_class > 0:
                with st.expander(f"👁️ Fungua kuona Orodha ya Wanafunzi wote wa {cls_name}"):
                    st.dataframe(df_cls_studs, use_container_width=True, hide_index=True)
            else:
                st.info(f"ℹ️ Hakuna wanafunzi waliosajiliwa kwenye darasa la {cls_name} kwa savyo.")
                
    st.markdown("---")
    st.markdown("### 📝 Uhakiki wa Ujazaji wa Alama za Mitihani")
    col_d1, col_d2 = st.columns(2)
    with col_d1: dash_class = st.selectbox("Chagua Kidato cha Kuhakiki Status:", ALL_CLASSES)
    with col_d2: dash_exam = st.selectbox("Chagua Aina ya Mtihani:", EXAMS_LIST)
        
    with sqlite3.connect(DB_NECTA) as conn:
        total_studs = pd.read_sql_query("SELECT COUNT(*) as count FROM students WHERE class=?", conn, params=(dash_class,)).iloc[0]['count']
        df_active_subs = pd.read_sql_query("SELECT * FROM subjects", conn)
        df_entered_scores = pd.read_sql_query("SELECT subject_code, COUNT(DISTINCT reg_no) as entered FROM exam_scores WHERE class=? AND exam_name=? AND score IS NOT NULL GROUP BY subject_code", conn, params=(dash_class, dash_exam))
        
    st.markdown(f"#### Status ya Ujazaji Alama: **{dash_class} - {dash_exam}** (Jumla ya Wanafunzi Waliopo: `{total_studs}`)")
    
    if total_studs == 0:
        st.warning(f"⚠️ Hakuna wanafunzi waliosajiliwa kwenye {dash_class} bado.")
    elif df_active_subs.empty:
        st.warning("⚠️ Hakuna masomo yaliyosajiliwa kwenye mfumo.")
    else:
        for _, sub_row in df_active_subs.iterrows():
            code = sub_row['subject_code']
            name = sub_row['subject_name']
            match = df_entered_scores[df_entered_scores['subject_code'] == code]
            entered_count = match.iloc[0]['entered'] if not match.empty else 0
            entered_count = min(entered_count, total_studs)
            percentage = (entered_count / total_studs) if total_studs > 0 else 0
            
            col_s1, col_s2 = st.columns([1, 3])
            with col_s1: st.write(f"**{name} ({code})**")
            with col_s2:
                if percentage == 1.0:
                    st.progress(percentage)
                    st.caption(f"✅ Imekamilika ({entered_count}/{total_studs})")
                elif percentage > 0:
                    st.progress(percentage)
                    st.caption(f"⏳ Inajazwa sasa ({entered_count}/{total_studs})")
                else:
                    st.progress(0.0)
                    st.caption(f"❌ Bado Haijaguswa (0/{total_studs})")

# ----------------- MODULI MPYA: SUPER ADMIN CONTROL PANEL -----------------
elif choice == "🔑 Super Admin Control Panel" and st.session_state['user_role'] == 'Super Admin':
    st.subheader("🔑 Super Admin Dashboard Control")
    st.write("Dhibiti tarehe ya mwisho ya matumizi ya mfumo na dhibiti Ma-admin pamoja na Walimu wote.")
    
    tab_sa1, tab_sa2 = st.tabs(["⏳ Mfumo Expiry Settings", "👥 Usimamizi Mkuu wa Watumiaji"])
    
    with tab_sa1:
        st.markdown("#### Weka tarehe ya mwisho ya mfumo kufanya kazi")
        with sqlite3.connect(DB_NECTA) as conn:
            res_exp = pd.read_sql_query("SELECT system_expiry FROM report_settings WHERE id=1", conn)
            current_expiry_val = res_exp.iloc[0]['system_expiry'] if not res_exp.empty else "2027-12-31"
            
        try:
            current_date_obj = datetime.strptime(current_expiry_val, "%Y-%m-%d").date()
        except:
            current_date_obj = datetime.now().date()
            
        new_expiry_date = st.date_input("Chagua Tarehe ya Mwisho (Expiry Date):", value=current_date_obj)
        
        if st.button("💾 Sasisha Tarehe ya Mwisho", use_container_width=True):
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                c.execute("UPDATE report_settings SET system_expiry=? WHERE id=1", (str(new_expiry_date),))
                conn.commit()
            st.success(f"✅ Tarehe ya mwisho ya matumizi imesasishwa kuwa: {new_expiry_date}")
            st.rerun()
            
    with tab_sa2:
        st.markdown("#### Orodha Kuu ya Watumiaji wa Mfumo")
        with sqlite3.connect(DB_NECTA) as conn:
            df_sa_users = pd.read_sql_query("SELECT username as 'USERNAME', full_name as 'JINA KAMILI', role as 'ROLE', password as 'PASSWORD' FROM users", conn)
        st.dataframe(df_sa_users, use_container_width=True, hide_index=True)

# ----------------- MODULI: WANAFUNZI -----------------
elif choice == "👥 Daftari la Wanafunzi" and st.session_state['user_role'] in ['Admin', 'Super Admin']:
    st.subheader("👥 Usajili wa Wanafunzi (Manual, Bulk & Modification)")
    tab1, tab2, tab3 = st.tabs(["✍️ Sajili Mmoja mmoja", "📤 Bulk Registration (Excel/CSV)", "✏️ Hariri / Futa Mwanafunzi"])
    
    with tab1:
        with st.form("stud_form"):
            r_no = st.text_input("Namba ya Usajili / CNO *")
            f_name = st.text_input("Jina Kamili la Mwanafunzi *")
            s_class = st.selectbox("Darasa/Kidato", ALL_CLASSES)
            is_advance = get_level_by_class(s_class) == "A-LEVEL"
            label_text = "Tahasusi / Combination (Mfano: PCM, HGL)" if is_advance else "Mkondo / Stream (Mfano: A, B, Gold)"
            s_stream_or_comb = st.text_input(label_text).strip().upper()
            s_gen = st.radio("Jinsia", ["M", "F"], horizontal=True)
            s_phone = st.text_input("Namba ya Simu ya Mzazi")
            btn_stud = st.form_submit_button("Hifadhi Mwanafunzi")
            
        if btn_stud and r_no and f_name:
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO students (reg_no, full_name, class, gender, stream_or_comb, parent_phone) VALUES (?,?,?,?,?,?)", 
                          (r_no.strip(), f_name.strip(), s_class, s_gen, s_stream_or_comb, s_phone.strip()))
                conn.commit()
            st.success(f"✔️ Mwanafunzi {f_name} amesajiliwa kikamilifu!")
            st.rerun()
            
    with tab2:
        stud_template = pd.DataFrame(columns=["reg_no", "full_name", "class", "gender", "stream_or_comb", "parent_phone"])
        stud_template.loc[0] = ["S0101/0001", "JUMA HAMISI", "Form 1", "M", "A", "0655402558"]
        stud_csv = stud_template.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Pakua Template ya Wanafunzi", data=stud_csv, file_name="Template_Wanafunzi.csv", mime="text/csv")
        
        uploaded_stud_file = st.file_uploader("Upload Faili Lililojazwa", type=["csv", "xlsx"])
        if uploaded_stud_file:
            try:
                df_up = pd.read_csv(uploaded_stud_file) if uploaded_stud_file.name.endswith('.csv') else pd.read_excel(uploaded_stud_file)
                if st.button("🚀 Kamilisha Kupandisha Wanafunzi"):
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        for _, r in df_up.iterrows():
                            phone_val = str(r['parent_phone']) if 'parent_phone' in r and not pd.isna(r['parent_phone']) else ""
                            c.execute("INSERT OR REPLACE INTO students (reg_no, full_name, class, gender, stream_or_comb, parent_phone) VALUES (?,?,?,?,?,?)", 
                                      (str(r['reg_no']), str(r['full_name']), str(r['class']), str(r['gender']), str(r['stream_or_comb']).upper(), phone_val))
                        conn.commit()
                    st.success("✔️ Wanafunzi wote wamepandishwa kwa mafanikio!")
                    st.rerun()
            except Exception as e: st.error(f"Hitilafu kwenye faili: {e}")

    with tab3:
        with sqlite3.connect(DB_NECTA) as conn:
            all_studs_list = pd.read_sql_query("SELECT reg_no, full_name, class FROM students", conn)
        if not all_studs_list.empty:
            all_studs_list['display_name'] = all_studs_list['reg_no'] + " - " + all_studs_list['full_name'] + " (" + all_studs_list['class'] + ")"
            selected_stud_disp = st.selectbox("Chagua Mwanafunzi wa Kuedit/Kufuta:", all_studs_list['display_name'].tolist())
            selected_reg_no = all_studs_list[all_studs_list['display_name'] == selected_stud_disp].iloc[0]['reg_no']
            
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                c.execute("SELECT reg_no, full_name, class, gender, stream_or_comb, parent_phone FROM students WHERE reg_no = ?", (selected_reg_no,))
                stud_data = c.fetchone()
                
            if stud_data:
                with st.form("edit_stud_form"):
                    edit_name = st.text_input("Jina Kamili la Mwanafunzi", value=stud_data[1])
                    edit_class = st.selectbox("Darasa/Kidato", ALL_CLASSES, index=ALL_CLASSES.index(stud_data[2]) if stud_data[2] in ALL_CLASSES else 0)
                    lbl_txt = "Tahasusi / Combination" if get_level_by_class(edit_class) == "A-LEVEL" else "Mkondo / Stream"
                    edit_stream = st.text_input(lbl_txt, value=stud_data[4] if stud_data[4] else "").strip().upper()
                    edit_gender = st.radio("Jinsia", ["M", "F"], index=0 if stud_data[3] == "M" else 1, horizontal=True)
                    edit_phone = st.text_input("Namba ya Simu ya Mzazi", value=stud_data[5] if stud_data[5] else "")
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1: save_changes = st.form_submit_button("💾 Hifadhi Marekebisho")
                    with col_btn2: delete_stud = st.form_submit_button("❌ Futa Mwanafunzi Kabisa")
                    
                if save_changes:
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE students SET full_name=?, class=?, gender=?, stream_or_comb=?, parent_phone=? WHERE reg_no=?", 
                                  (edit_name.strip(), edit_class, edit_gender, edit_stream, edit_phone.strip(), selected_reg_no))
                        conn.commit()
                    st.success("✔️ Taarifa zimesasishwa vizuri!")
                    st.rerun()
                    
                if delete_stud:
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM students WHERE reg_no=?", (selected_reg_no,))
                        c.execute("DELETE FROM exam_scores WHERE reg_no=?", (selected_reg_no,))
                        conn.commit()
                    st.success("🗑️ Mwanafunzi amefutwa!")
                    st.rerun()

    with sqlite3.connect(DB_NECTA) as conn:
        df_all_studs = pd.read_sql_query("SELECT reg_no as 'CNO', full_name as 'JINA KAMILI', class as 'KIDATO', stream_or_comb as 'MKONDO/COMB', gender as 'JINSIA', parent_phone as 'SIMU YA MZAZI' FROM students", conn)
    st.dataframe(df_all_studs, use_container_width=True, hide_index=True)

# ----------------- MODULI: DATA ENTRY -----------------
elif choice == "📝 Jaza Alama (Marks Entry)":
    st.subheader("📝 Kuingiza Alama za Mitihani")
    f_class = st.selectbox("Chagua Darasa la Kujaza:", ALL_CLASSES)
    f_exam = st.selectbox("Chagua Mtihani:", EXAMS_LIST)
    
    with sqlite3.connect(DB_NECTA) as conn:
        df_students = pd.read_sql_query("SELECT reg_no, full_name, stream_or_comb, gender FROM students WHERE class = ?", conn, params=(f_class,))
        df_subjects = pd.read_sql_query("SELECT subject_code FROM subjects", conn)
        df_existing = pd.read_sql_query("SELECT reg_no, subject_code, score FROM exam_scores WHERE class = ? AND exam_name = ?", conn, params=(f_class, f_exam))
    
    if df_students.empty or df_subjects.empty:
        st.warning("Hakikisha kuna wanafunzi na masomo kwenye darasa hili.")
    else:
        sub_list = df_subjects['subject_code'].tolist()
        matrix_df = df_students.copy()
        is_adv = get_level_by_class(f_class) == "A-LEVEL"
        col_lbl = "COMB" if is_adv else "MKONDO"
        matrix_df = matrix_df.rename(columns={"stream_or_comb": col_lbl})
        
        for sub in sub_list:
            if not df_existing.empty:
                sub_scores = df_existing[df_existing['subject_code'] == sub].set_index('reg_no')['score']
                matrix_df[sub] = matrix_df['reg_no'].map(sub_scores)
                matrix_df[sub] = matrix_df[sub].astype('Int64')
            else: 
                matrix_df[sub] = pd.NA
                matrix_df[sub] = matrix_df[sub].astype('Int64')

        edited_df = st.data_editor(matrix_df, use_container_width=True, hide_index=True, disabled=["reg_no", "full_name", col_lbl, "gender"])
        
        if st.button("💾 Hifadhi Alama Zote Ulizobadilisha", use_container_width=True):
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                for _, row in edited_df.iterrows():
                    r_no = row['reg_no']
                    for sub in sub_list:
                        val = row[sub]
                        if pd.isna(val) or val is None:
                            val_to_save = None
                        else:
                            val_to_save = int(val)
                            if val_to_save < 0 or val_to_save > 100:
                                continue
                                
                        s_id = f"{r_no}_{f_class}_{f_exam}_{sub}"
                        c.execute("INSERT OR REPLACE INTO exam_scores (id, reg_no, class, exam_name, subject_code, score) VALUES (?,?,?,?,?,?)", 
                                  (s_id, r_no, f_class, f_exam, sub, val_to_save))
                conn.commit()
            st.success("🎉 Alama zote zimehifadhiwa kwa mafanikio!")
            st.rerun()

# ----------------- MODULI YA MKEKA WA MATOKEO -----------------
elif choice == "📜 Mkeka wa Matokeo":
    f_class = st.selectbox("Darasa la Uhakiki:", ALL_CLASSES, key="mkeka_class_select")
    f_exam = st.selectbox("Mtihani wa Uhakiki:", EXAMS_LIST, key="mkeka_exam_select")
    
    dynamic_header = f"{f_class.upper()} {f_exam.upper()} EXAMINATION RESULTS"
    
    with sqlite3.connect(DB_NECTA) as conn:
        df_base_students = pd.read_sql_query("SELECT reg_no, full_name, stream_or_comb, gender FROM students WHERE class = ?", conn, params=(f_class,))
        df_scores_raw = pd.read_sql_query("SELECT reg_no, subject_code, score FROM exam_scores WHERE class = ? AND exam_name = ?", conn, params=(f_class, f_exam))
        df_subs_active = pd.read_sql_query("SELECT subject_code, subject_name, is_grading FROM subjects", conn)
    
    if df_base_students.empty or df_scores_raw.empty:
        st.warning(f"⚠️ Bado hakuna alama zilizohifadhiwa kwa ajili ya {f_class} kwenye mtihani wa {f_exam}.")
    else:
        pivot_scores = df_scores_raw.pivot_table(index='reg_no', columns='subject_code', values='score', aggfunc='first').reset_index()
        pivot_df = pd.merge(df_base_students, pivot_scores, on='reg_no', how='inner')
        
        sub_codes = df_subs_active['subject_code'].tolist()
        existing_subs = [c for c in sub_codes if c in pivot_df.columns]
        
        if not existing_subs:
            st.warning("⚠️ Masomo yaliyojaziwa alama hayapo kwenye orodha kuu ya masomo.")
        else:
            grading_map = dict(zip(df_subs_active['subject_code'], df_subs_active['is_grading']))
            
            necta_rows = []
            summary_counts = {
                'F': {'I':0, 'II':0, 'III':0, 'IV':0, '0':0, 'INC':0, 'TOTAL':0}, 
                'M': {'I':0, 'II':0, 'III':0, 'IV':0, '0':0, 'INC':0, 'TOTAL':0}
            }
            subject_stats = {sub: {'A':0, 'B':0, 'C':0, 'D':0, 'E':0, 'S':0, 'F':0, 'REG':0, 'SAT':0} for sub in existing_subs}
            total_gpa_points, total_gpa_subjects_count = 0, 0
            
            for idx, row in pivot_df.iterrows():
                points_list = []
                detail_strings = []
                for sub in existing_subs:
                    score = row[sub]
                    subject_stats[sub]['REG'] += 1
                    
                    if pd.isna(score) or score is None:
                        continue 
                    
                    grd, pt = get_dynamic_grade_and_point(score, f_class)
                    
                    if grd is not None:
                        subject_stats[sub]['SAT'] += 1
                        subject_stats[sub][grd] += 1
                        
                        if grading_map.get(sub, 1) == 1:
                            points_list.append(pt)
                            total_gpa_points += pt
                            total_gpa_subjects_count += 1
                            detail_strings.append(f"{sub}-'{grd}'")
                        else:
                            detail_strings.append(f"{sub}-'{grd}'*")
                
                div, points = calculate_necta_division(points_list, f_class)
                gender = row['gender'] if row['gender'] in ['F', 'M'] else 'M'
                summary_counts[gender][div] += 1
                summary_counts[gender]['TOTAL'] += 1
                
                necta_rows.append({
                    "CNO": row['reg_no'], "STUDENT NAME": row['full_name'], "SEX": row['gender'], "COMB/STR": row['stream_or_comb'] if row['stream_or_comb'] else "-",
                    "AGGT": points, "DIV": div, "DETAILED SUBJECTS": "  ".join(detail_strings) if detail_strings else "NO EXAMS ATTENDED"
                })
                
            summary_data = [
                {"SEX": "F", "I": summary_counts['F']['I'], "II": summary_counts['F']['II'], "III": summary_counts['F']['III'], "IV": summary_counts['F']['IV'], "0": summary_counts['F']['0'], "INC": summary_counts['F']['INC'], "TOTAL": summary_counts['F']['TOTAL']},
                {"SEX": "M", "I": summary_counts['M']['I'], "II": summary_counts['M']['II'], "III": summary_counts['M']['III'], "IV": summary_counts['M']['IV'], "0": summary_counts['M']['0'], "INC": summary_counts['M']['INC'], "TOTAL": summary_counts['M']['TOTAL']},
                {"SEX": "T", "I": summary_counts['F']['I'] + summary_counts['M']['I'], "II": summary_counts['F']['II'] + summary_counts['M']['II'], "III": summary_counts['F']['III'] + summary_counts['M']['III'], "IV": summary_counts['F']['IV'] + summary_counts['M']['IV'], "0": summary_counts['F']['0'] + summary_counts['M']['0'], "INC": summary_counts['F']['INC'] + summary_counts['M']['INC'], "TOTAL": summary_counts['F']['TOTAL'] + summary_counts['M']['TOTAL']}
            ]
            
            st.markdown("### DIVISION PERFORMANCE SUMMARY")
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
            
            st.markdown("### EXAMINATION RESULTS SHEET")
            final_necta_df = pd.DataFrame(necta_rows)
            st.dataframe(final_necta_df, use_container_width=True, hide_index=True)
            
            def rank_key(row):
                div_map = {"I": 1, "II": 2, "III": 3, "IV": 4, "0": 5, "INC": 6}
                d_val = div_map.get(row['DIV'], 7)
                try: p_val = int(row['AGGT'])
                except: p_val = 999
                return (d_val, p_val, row['STUDENT NAME'])

            sorted_necta_rows = sorted(necta_rows, key=rank_key)
            top_ten = sorted_necta_rows[:10]
            last_ten = sorted_necta_rows[-10:] if len(sorted_necta_rows) >= 10 else sorted_necta_rows
            
            total_students = summary_counts['F']['TOTAL'] + summary_counts['M']['TOTAL']
            total_passed = (summary_data[2]['I'] + summary_data[2]['II'] + summary_data[2]['III'] + summary_data[2]['IV'])
            centre_gpa = total_gpa_points / total_gpa_subjects_count if total_gpa_subjects_count > 0 else 0
            
            def get_gpa_grade_label(gpa):
                if gpa <= 1.5: return "GRADE A (EXCELLENT)"
                elif gpa <= 2.5: return "GRADE B (VERY GOOD)"
                elif gpa <= 3.5: return "GRADE C (GOOD)"
                elif gpa <= 4.5: return "GRADE D (SATISFACTORY)"
                else: return "GRADE F (UNSATISFACTORY)"

            subject_rows = []
            for code in existing_subs:
                sub_title_row = df_subs_active[df_subs_active['subject_code'] == code]
                sub_name = sub_title_row['subject_name'].values[0] if not sub_title_row.empty else code
                stats = subject_stats[code]
                lvl_weight = 7 if get_level_by_class(f_class) == "A-LEVEL" else 5
                wigo = (1*stats['A']) + (2*stats['B']) + (3*stats['C']) + (4*stats['D']) + (5*stats['E']) + (6*stats['S']) + (lvl_weight*stats['F'])
                sub_gpa = wigo / stats['SAT'] if stats['SAT'] > 0 else 0
                pass_count = stats['A'] + stats['B'] + stats['C'] + stats['D'] + stats['E'] + stats['S']
                
                comp = get_gpa_grade_label(sub_gpa)
                g_type = "Grading" if grading_map.get(code, 1) == 1 else "Non-Grading"
                subject_rows.append({
                    "CODE": code, "SUBJECT NAME": sub_name, "TYPE": g_type, "REG": stats['REG'], "SAT": stats['SAT'],
                    "ABS": stats['REG'] - stats['SAT'], "PASS": pass_count, "GPA": round(sub_gpa, 2) if g_type == "Grading" else "-", "COMPETENCY LEVEL": comp if g_type == "Grading" else "NON-GRADING"
                })
                
            lbl_str_comb = "COMB/STR" if get_level_by_class(f_class) == "A-LEVEL" else "MKONDO"
            
            html_rows = ""
            for r in necta_rows:
                html_rows += f"<tr><td>{r['CNO']}</td><td>{r['STUDENT NAME']}</td><td style='text-align:center;'>{r['SEX']}</td><td style='text-align:center;'>{r['COMB/STR']}</td><td style='text-align:center;'>{r['AGGT']}</td><td style='text-align:center;'><strong>{r['DIV']}</strong></td><td>{r['DETAILED SUBJECTS']}</td></tr>"
                
            subject_html_rows = ""
            for row in subject_rows:
                subject_html_rows += f"<tr><td style='text-align:center;'>{row['CODE']}</td><td>{row['SUBJECT NAME']}</td><td style='text-align:center;'>{row['REG']}</td><td style='text-align:center;'>{row['SAT']}</td><td style='text-align:center;'>{row['ABS']}</td><td style='text-align:center;'>{row['PASS']}</td><td style='text-align:center;'>{row['GPA']}</td><td>{row['COMPETENCY LEVEL']}</td></tr>"

            border_summary_html = ""
            for sd in summary_data:
                border_summary_html += f"<tr><td style='text-align:center;font-weight:bold;'>{sd['SEX']}</td><td style='text-align:center;'>{sd['I']}</td><td style='text-align:center;'>{sd['II']}</td><td style='text-align:center;'>{sd['III']}</td><td style='text-align:center;'>{sd['IV']}</td><td style='text-align:center;'>{sd['0']}</td><td style='text-align:center;'>{sd['INC']}</td><td style='text-align:center;font-weight:bold;'>{sd['TOTAL']}</td></tr>"

            top_ten_html = ""
            for i, r in enumerate(top_ten, 1):
                top_ten_html += f"<tr><td style='text-align:center;'>{i}</td><td>{r['CNO']}</td><td>{r['STUDENT NAME']}</td><td style='text-align:center;'>{r['SEX']}</td><td style='text-align:center;'>{r['COMB/STR']}</td><td style='text-align:center;'>{r['AGGT']}</td><td style='text-align:center;'><strong>{r['DIV']}</strong></td></tr>"

            last_ten_html = ""
            for i, r in enumerate(last_ten, 1):
                last_ten_html += f"<tr><td style='text-align:center;'>{i}</td><td>{r['CNO']}</td><td>{r['STUDENT NAME']}</td><td style='text-align:center;'>{r['SEX']}</td><td style='text-align:center;'>{r['COMB/STR']}</td><td style='text-align:center;'>{r['AGGT']}</td><td style='text-align:center;'><strong>{r['DIV']}</strong></td></tr>"

            print_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Arial', sans-serif; padding: 10px; color: #333; }}
                    h2, h3, h4 {{ text-align: center; color: #1e3a8a; text-transform: uppercase; margin-top: 5px; margin-bottom: 5px; }}
                    table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 11px; }}
                    th, td {{ border: 1px solid #777; padding: 5px; text-align: left; }}
                    th {{ background-color: #f2f2f2; font-weight: bold; }}
                    .metric-container {{ display: flex; justify-content: space-between; margin-bottom: 20px; }}
                    .metric-box {{ flex: 1; border: 2px solid #1e3a8a; padding: 8px; margin: 0 5px; text-align: center; background-color: #f8fafc; border-radius: 4px; }}
                    .metric-val {{ font-size: 15px; font-weight: bold; color: #1e3a8a; margin-top: 4px; }}
                    .rank-tables-container {{ display: flex; justify-content: space-between; gap: 15px; margin-top: 15px; }}
                    .rank-box {{ flex: 1; }}
                </style>
            </head>
            <body>
                <h2>{dynamic_header}</h2>
                
                <h3>DIVISION PERFORMANCE SUMMARY</h3>
                <table><thead><tr><th>SEX</th><th>I</th><th>II</th><th>III</th><th>IV</th><th>0</th><th>INC</th><th>TOTAL</th></tr></thead><tbody>{border_summary_html}</tbody></table>
                
                <h3>EXAMINATION CENTRE SUMMARY RESULTS</h3>
                <div class="metric-container">
                    <div class="metric-box"><div>TOTAL PASSED CANDIDATES</div><div class="metric-val">{total_passed} / {total_students}</div></div>
                    <div class="metric-box"><div>EXAMINATION CENTRE GPA</div><div class="metric-val">{centre_gpa:.2f}</div></div>
                </div>

                <h3>EXAMINATION RESULTS SHEET</h3>
                <table><thead><tr><th>CNO</th><th>STUDENT NAME</th><th>SEX</th><th>{lbl_str_comb}</th><th>AGGT</th><th>DIV</th><th>DETAILED SUBJECTS</th></tr></thead><tbody>{html_rows}</tbody></table>
                
                <h3>EXAMINATION CENTRE SUBJECT PERFORMANCE</h3>
                <table><thead><tr><th>CODE</th><th>SUBJECT NAME</th><th>REG</th><th>SAT</th><th>ABS</th><th>PASS</th><th>GPA</th><th>COMPETENCY LEVEL</th></tr></thead><tbody>{subject_html_rows}</tbody></table>
                
                <div class="rank-tables-container">
                    <div class="rank-box">
                        <h3>🏆 TOP TEN STUDENTS</h3>
                        <table>
                            <thead><tr><th>RANK</th><th>CNO</th><th>STUDENT NAME</th><th>SEX</th><th>{lbl_str_comb}</th><th>AGGT</th><th>DIV</th></tr></thead>
                            <tbody>{top_ten_html}</tbody>
                        </table>
                    </div>
                    <div class="rank-box">
                        <h3>⚠️ LAST TEN STUDENTS</h3>
                        <table>
                            <thead><tr><th>POS</th><th>CNO</th><th>STUDENT NAME</th><th>SEX</th><th>{lbl_str_comb}</th><th>AGGT</th><th>DIV</th></tr></thead>
                            <tbody>{last_ten_html}</tbody>
                        </table>
                    </div>
                </div>
                <script>window.onload = function() {{ window.print(); }}</script>
            </body>
            </html>
            """
            if st.button("🖨️ Print Results & Summary Sheet", use_container_width=True, key="btn_print_mkeka"):
                st.components.v1.html(print_content, height=600, scrolling=True)

# ----------------- MODULI MPYA: RIPOTI ZA WANAFUNZI (STAFF PORTAL) -----------------
elif choice == "📄 Ripoti za Wanafunzi (Report Cards)" and st.session_state['user_role'] in ['Super Admin', 'Admin', 'Teacher']:
    st.subheader("📄 Ripoti za Wanafunzi (Report Cards)")
    st.write("Tengeneza na pakua ripoti za wanafunzi moja moja, au darasa zima kwa pamoja (Bulk Print / ZIP).")
    
    # 1. Chagua Darasa na Mitihani
    f_class = st.selectbox("Chagua Darasa:", ALL_CLASSES, key="staff_rep_class")
    
    st.markdown("##### Sanidi Mitihani Itakayounda Ripoti")
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    with col_ex1: ex_jaribio = st.selectbox("1. Jaribio (100%):", EXAMS_LIST, index=0, key="st_ex_j")
    with col_ex2: ex_midterm = st.selectbox("2. 1/2 Muhula (100%):", EXAMS_LIST, index=6, key="st_ex_m")
    with col_ex3: ex_final = st.selectbox("3. Mtihani wa Mwisho (100%):", EXAMS_LIST, index=8, key="st_ex_f")
    
    st.markdown("---")
    aina_ya_print = st.radio("Chagua Namna ya Kuprint:", ["👤 Mwanafunzi Mmoja Mmoja", "📚 Darasa Zima (Bulk Print / ZIP)"], horizontal=True)
    
    with sqlite3.connect(DB_NECTA) as conn:
        df_all_class_studs = pd.read_sql_query("SELECT reg_no, full_name, class, gender, stream_or_comb FROM students WHERE class=?", conn, params=(f_class,))
        df_all_scores = pd.read_sql_query("SELECT reg_no, exam_name, subject_code, score FROM exam_scores WHERE class=?", conn, params=(f_class,))
        df_subs_active = pd.read_sql_query("SELECT subject_code, subject_name, is_grading FROM subjects", conn)
        cfg_res = pd.read_sql_query("SELECT * FROM report_settings WHERE id=1", conn)
        cfg = cfg_res.iloc[0] if not cfg_res.empty else {}

    if df_all_class_studs.empty:
        st.warning(f"⚠️ Hakuna wanafunzi waliosajiliwa kwenye darasa la {f_class}.")
    else:
        # Piga hesabu ya Ranks za darasa zima (Kama kwenye Student Portal)
        stud_totals_bulk = {}
        for idx, r_bulk in df_all_class_studs.iterrows():
            r_no = r_bulk['reg_no']
            st_sc = df_all_scores[df_all_scores['reg_no'] == r_no]
            total_marks, sub_count = 0, 0
            for code in df_subs_active['subject_code'].tolist():
                sc_sub = st_sc[st_sc['subject_code'] == code]
                sc_j = sc_sub[sc_sub['exam_name'] == ex_jaribio]
                sc_m = sc_sub[sc_sub['exam_name'] == ex_midterm]
                sc_f = sc_sub[sc_sub['exam_name'] == ex_final]
                
                v_j = sc_j.iloc[0]['score'] if not sc_j.empty and not pd.isna(sc_j.iloc[0]['score']) else None
                v_m = sc_m.iloc[0]['score'] if not sc_m.empty and not pd.isna(sc_m.iloc[0]['score']) else None
                v_f = sc_f.iloc[0]['score'] if not sc_f.empty and not pd.isna(sc_f.iloc[0]['score']) else None
                
                valid_vals = [v for v in [v_j, v_m, v_f] if v is not None]
                if valid_vals:
                    total_marks += (sum(valid_vals) / len(valid_vals))
                    sub_count += 1
            stud_totals_bulk[r_no] = total_marks if sub_count > 0 else 0
            
        rank_df_bulk = pd.DataFrame(list(stud_totals_bulk.items()), columns=['reg_no', 'total_score'])
        rank_df_bulk = pd.merge(rank_df_bulk, df_all_class_studs, on='reg_no')
        rank_df_bulk['class_rank'] = rank_df_bulk['total_score'].rank(ascending=False, method='min')
        rank_df_bulk['stream_rank'] = rank_df_bulk.groupby('stream_or_comb')['total_score'].rank(ascending=False, method='min')
        
        tot_class = len(rank_df_bulk)

        # Helper function ya kutengeneza HTML ya mwanafunzi mmoja
        def generate_student_html(r_no, s_name, s_sex, s_stream):
            current_student_rank = rank_df_bulk[rank_df_bulk['reg_no'] == r_no].iloc[0]
            pos_class = int(current_student_rank['class_rank'])
            pos_stream = int(current_student_rank['stream_rank'])
            tot_stream = len(rank_df_bulk[rank_df_bulk['stream_or_comb'] == s_stream])
            
            student_total_marks, grading_subjects_count = 0, 0
            points_for_div = []
            report_table_rows_html = ""
            
            st_sc = df_all_scores[df_all_scores['reg_no'] == r_no]
            
            for r_na, sub_row in df_subs_active.iterrows():
                code = sub_row['subject_code']
                name = sub_row['subject_name']
                is_grd_status = sub_row['is_grading']
                
                sc_sub = st_sc[st_sc['subject_code'] == code]
                sc_j = sc_sub[sc_sub['exam_name'] == ex_jaribio]
                sc_m = sc_sub[sc_sub['exam_name'] == ex_midterm]
                sc_f = sc_sub[sc_sub['exam_name'] == ex_final]
                
                v_j = sc_j.iloc[0]['score'] if not sc_j.empty and not pd.isna(sc_j.iloc[0]['score']) else None
                v_m = sc_m.iloc[0]['score'] if not sc_m.empty and not pd.isna(sc_m.iloc[0]['score']) else None
                v_f = sc_f.iloc[0]['score'] if not sc_f.empty and not pd.isna(sc_f.iloc[0]['score']) else None
                
                vals = [v for v in [v_j, v_m, v_f] if v is not None]
                v_avg = sum(vals)/len(vals) if vals else 0
                
                v_j_str = str(int(v_j)) if v_j is not None else "-"
                v_m_str = str(int(v_m)) if v_m is not None else "-"
                v_f_str = str(int(v_f)) if v_f is not None else "-"
                v_avg_str = f"{v_avg:.1f}" if vals else "-"
                
                grd, pt = get_dynamic_grade_and_point(v_avg if vals else -1, f_class)
                if not vals: grd, pt = "-", None
                
                if pt is not None and is_grd_status == 1:
                    points_for_div.append(pt)
                    student_total_marks += v_avg
                    grading_subjects_count += 1
                    
                rem = get_swahili_remarks(grd)
                sgn_str = grd if grd != "-" else ""
                
                report_table_rows_html += f"<tr><td>{r_na+1}</td><td style='font-weight:600;'>{name}</td><td style='text-align:center;'>{v_j_str}</td><td style='text-align:center;'>{v_m_str}</td><td style='text-align:center;'>{v_f_str}</td><td style='text-align:center; font-weight:bold; color:#1e3a8a;'>{v_avg_str}</td><td style='text-align:center; font-weight:bold;'>{grd}</td><td style='text-align:center;'>{sgn_str}</td><td style='font-size:10px; color:#4b5563;'>{rem}</td></tr>"
                
            final_gpa = (student_total_marks / grading_subjects_count) if grading_subjects_count > 0 else 0
            final_class_grade, _ = get_dynamic_grade_and_point(final_gpa if grading_subjects_count > 0 else -1, f_class)
            if grading_subjects_count == 0: final_class_grade = "-"
            
            final_div, final_aggt = calculate_necta_division(points_for_div, f_class)
            
            mwl_maoni, mkuu_maoni, status_faulu = "", "", ""
            if final_div in ["I", "II", "III"]:
                mwl_maoni = "Amefanya vizuri sana. Aendelee kudumisha juhudi hizi."
                mkuu_maoni = "Ufaulu wake ni mzuri sana. Hongera kwa juhudi hizi!"
                status_faulu = "AMEFAULU"
            elif final_div == "IV":
                mwl_maoni = "Ufaulu wake ni wa kuridhisha lakini ana uwezo wa vizuri zaidi."
                mkuu_maoni = "Nafasi ya kurekebisha ipo, akaze buti zaidi."
                status_faulu = "AMEFAULU"
            else:
                mwl_maoni = "Ufaulu wake hauridhishi kabisa. Anahitaji kuongeza juhudi maradufu."
                mkuu_maoni = "Ufaulu wake si mzuri, asome sana na wenzie wenye uwezo."
                status_faulu = "AKAZE BUTI"
                
            h_waziri = str(cfg.get('waziri_header','')).upper()
            h_tamisemi = str(cfg.get('tamisemi_header','')).upper()
            h_wilaya = str(cfg.get('wilaya_header','')).upper()
            h_shule = str(cfg.get('shule_name','')).upper()
            h_phone = str(cfg.get('simu_mawasiliano',''))
            h_box = str(cfg.get('slp_box',''))
            h_kufungua = str(cfg.get('tarehe_kufungua',''))
            h_kufunga = str(cfg.get('tarehe_kufunga','')) if cfg.get('tarehe_kufunga','') else "-"
            h_tabia_val = str(cfg.get('default_tabia','')).upper()
            h_maagizo_mengine = str(cfg.get('maagizo_mengine','')) if cfg.get('maagizo_mengine','') else ""
            
            student_html = f"""
            <div class="report-page">
                <div class="header-title">{h_waziri}</div>
                <div class="header-title">{h_tamisemi}</div>
                <div class="header-title">{h_wilaya}</div>
                <div class="school-name">{h_shule}</div>
                <div class="school-contact">SLP: {h_box} | SIMU MAWASILIANO: {h_phone}</div>
                <div class="report-title">RIPOTI YA MAENDELEO YA TAALUMA NA TABIA - {str(f_class).upper()}</div>
                <div class="info-grid">
                    <div class="info-item"> JINA: <span class="highlight-text">{str(s_name).upper()}</span></div>
                    <div class="info-item"> NAMBA YA USAJILI: <span class="highlight-text">{r_no}</span></div>
                    <div class="info-item"> JINSIA: <span class="highlight-text">{s_sex}</span></div>
                    <div class="info-item"> MKONDO / COMB: <span class="highlight-text">{str(s_stream).upper()}</span></div>
                </div>
                <table class="main-table">
                    <thead><tr><th style="width: 5%;">NA</th><th style="width: 35%;">SOMO</th><th style="text-align:center; width: 10%;">JARIBIO</th><th style="text-align:center; width: 10%;">1/2 MUHULA</th><th style="text-align:center; width: 10%;">MTIHANI</th><th style="text-align:center; width: 10%;">WASTANI</th><th style="text-align:center; width: 8%;">GREDI</th><th style="text-align:center; width: 5%;">SGN</th><th style="width: 17%;">MAONI MAFUPI</th></tr></thead>
                    <tbody>{report_table_rows_html}</tbody>
                </table>
                <div class="summary-card">
                    <strong>A: TATHMINI YA JUMLA YA TAALUMA</strong><br>
                    Jumla ya Alama: <strong>{student_total_marks:.1f}</strong> &nbsp;|&nbsp; Wastani: <strong>{final_gpa:.1f}</strong> &nbsp;|&nbsp; Daraja la Wastani: <strong>{final_class_grade}</strong>
                    <div class="summary-grid">
                        <div>Nafasi Darasani: <span class="badge-white">{pos_class} / {tot_class}</span></div>
                        <div>Nafasi Mkondo: <span class="badge-white">{pos_stream} / {tot_stream}</span></div>
                        <div>Uamuzi: <span class="badge-white">DIV {final_div} ({final_aggt} PTS)</span></div>
                    </div>
                    <div style="margin-top: 8px; font-weight: bold; text-align: center; letter-spacing: 1px;">
                        HALI YA UFAULU: <span style="background: white; color: #1e3a8a; padding: 2px 10px; border-radius: 4px;">{status_faulu}</span>
                    </div>
                </div>
                <table class="comments-table">
                    <tr><td class="section-lbl">1. TABIA NA MWENENDO</td><td>Mwanafunzi huyu ana tabia: <strong>{h_tabia_val}</strong>.</td></tr>
                    <tr><td class="section-lbl">2. MAONI YA MWALIMU WA DARASA</td><td>{mwl_maoni}<div class="sig-space">Sahihi ya Mwalimu wa Darasa: .......................................</div></td></tr>
                    <tr><td class="section-lbl">3. MAONI YA MKUU WA SHULE</td><td>{mkuu_maoni}<div class="sig-space">Sahihi na Muhuri wa Mkuu wa Shule: .......................................</div></td></tr>
                </table>
                <div class="footer-notes">
                    <strong style="color: #1e3a8a;">⚠️ TAARIFA NA MAAGIZO YA SHULE:</strong><br>
                    1. Shule imefungwa rasmi leo tarehe: <strong>{h_kufunga}</strong>.<br>
                    2. Shule itafunguliwa rasmi tarehe: <strong>{h_kufungua}</strong>.<br>
                    {f'3. Maagizo ya ziada: {h_maagizo_mengine}' if h_maagizo_mengine else ''}
                </div>
            </div>
            """
            return student_html

        # CSS Master ya Ripoti zote
        master_css = """
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; background-color: #f3f4f6; line-height: 1.4; margin: 0; padding: 20px;}
            .no-print-btn { background-color: #2563eb; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: background 0.2s; display: block; margin-left: auto; margin-right: auto; }
            .no-print-btn:hover { background-color: #1d4ed8; }
            .report-page { background-color: #fff; border: 3px double #1e3a8a; padding: 30px; margin-bottom: 30px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-radius: 8px; page-break-after: always; max-width: 900px; margin-left: auto; margin-right: auto;}
            .report-page:last-child { page-break-after: auto; }
            .header-title { text-align: center; font-weight: 700; font-size: 14px; margin: 0; padding: 1px; letter-spacing: 0.5px; color: #374151; }
            .school-name { text-align: center; font-weight: 800; font-size: 22px; color: #1e3a8a; margin: 5px 0; letter-spacing: 1px; }
            .school-contact { text-align: center; font-size: 11px; font-weight: 600; color: #6b7280; margin-bottom: 10px; }
            .report-title { text-align: center; font-size: 15px; font-weight: 700; margin: 15px 0; text-transform: uppercase; color: #1e3a8a; border-bottom: 2px solid #1e3a8a; display: inline-block; width: 100%; padding-bottom: 5px; }
            .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; background: #f8fafc; padding: 15px; border-radius: 6px; border: 1px solid #e2e8f0; }
            .info-item { font-size: 13px; }
            .highlight-text { font-weight: bold; color: #0f172a; }
            .main-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }
            .main-table th { background-color: #1e3a8a; color: white; font-weight: 600; text-transform: uppercase; font-size: 11px; padding: 8px; border: 1px solid #1e3a8a; }
            .main-table td { border: 1px solid #e2e8f0; padding: 7px 8px; text-align: left; }
            .main-table tr:nth-child(even) { background-color: #f8fafc; }
            .summary-card { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 15px; border-radius: 6px; margin-top: 15px; font-size: 13px; }
            .summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 8px; }
            .badge-white { background: white; color: #1e3a8a; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
            .comments-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }
            .comments-table td { border: 1px solid #e2e8f0; padding: 10px; vertical-align: top; }
            .section-lbl { font-weight: bold; background-color: #f1f5f9; width: 25%; color: #334155; }
            .sig-space { margin-top: 20px; font-style: italic; color: #64748b; font-size: 11px; text-align: right; }
            .footer-notes { border-left: 4px solid #1e3a8a; background: #f8fafc; padding: 10px 15px; margin-top: 15px; font-size: 11px; border-radius: 0 6px 6px 0; border-top: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }
            @media print {
                body { background-color: #fff; padding: 0; }
                .report-page { border: none; box-shadow: none; padding: 0; max-width: 100%; margin-bottom: 0; }
                .no-print-btn { display: none !important; }
            }
        </style>
        """

        if aina_ya_print == "👤 Mwanafunzi Mmoja Mmoja":
            df_all_class_studs['display_label'] = df_all_class_studs['reg_no'] + " - " + df_all_class_studs['full_name']
            selected_st_label = st.selectbox("Tafuta na Chagua Mwanafunzi:", df_all_class_studs['display_label'].tolist())
            
            if st.button("📄 Tengeneza Ripoti", type="primary"):
                sel_row = df_all_class_studs[df_all_class_studs['display_label'] == selected_st_label].iloc[0]
                html_body = generate_student_html(sel_row['reg_no'], sel_row['full_name'], sel_row['gender'], sel_row['stream_or_comb'])
                
                full_html = f"<html><head>{master_css}</head><body><button class='no-print-btn' onclick='window.print()'>📥 Print Ripoti (PDF)</button>{html_body}</body></html>"
                st.components.v1.html(full_html, height=850, scrolling=True)
                
        else:
            st.info(f"Kipengele hiki kitatengeneza ripoti za wanafunzi wote {tot_class} wa {f_class}. Unaweza kuprint zote kwa mkupuo (zitatengana page) au kudownload ZIP.")
            col_b1, col_b2 = st.columns(2)
            
            if col_b1.button("🖨️ Tengeneza Continuous HTML (Print Zote)"):
                all_html_bodies = ""
                for idx, st_row in df_all_class_studs.iterrows():
                    all_html_bodies += generate_student_html(st_row['reg_no'], st_row['full_name'], st_row['gender'], st_row['stream_or_comb'])
                
                full_bulk_html = f"<html><head>{master_css}</head><body><button class='no-print-btn' onclick='window.print()'>🖨️ Print Ripoti Zote (Darasa Zima)</button>{all_html_bodies}</body></html>"
                st.components.v1.html(full_bulk_html, height=850, scrolling=True)
                
            if col_b2.button("📦 Tengeneza ZIP ya HTML Zote"):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for idx, st_row in df_all_class_studs.iterrows():
                        single_body = generate_student_html(st_row['reg_no'], st_row['full_name'], st_row['gender'], st_row['stream_or_comb'])
                        single_full_html = f"<html><head>{master_css}</head><body><button class='no-print-btn' onclick='window.print()'>📥 Print Ripoti</button>{single_body}</body></html>"
                        safe_name = str(st_row['full_name']).replace(" ", "_").replace("/", "-")
                        file_name = f"Ripoti_{safe_name}_{st_row['reg_no'].replace('/','-')}.html"
                        zf.writestr(file_name, single_full_html)
                
                st.download_button(
                    label="📥 Pakua ZIP ya Ripoti Zote",
                    data=zip_buffer.getvalue(),
                    file_name=f"Ripoti_Zote_{f_class.replace(' ','_')}.zip",
                    mime="application/zip",
                    type="primary"
                )


# ----------------- MODULI: CA TRACKER -----------------
elif choice == "📈 Continuous Assessment (CA) Tracker":
    st.markdown("<h2 style='color:#1e3a8a;'>📈 Continuous Assessment & Progress Tracker</h2>", unsafe_allow_html=True)
    tab_ca1, tab_ca2 = st.tabs(["👤 CA ya Mwanafunzi (Searchable)", "📚 CA ya Somo (Searchable)"])
    
    with tab_ca1:
        st.subheader("Ufuatiliaji wa Progress ya Mwanafunzi Mmoja mmoja")
        with sqlite3.connect(DB_NECTA) as conn:
            df_all_s = pd.read_sql_query("SELECT reg_no, full_name, class FROM students", conn)
        
        if df_all_s.empty:
            st.warning("Hakuna wanafunzi waliosajiliwa kwenye mfumo bado.")
        else:
            df_all_s['search_label'] = df_all_s['reg_no'] + " - " + df_all_s['full_name'] + " (" + df_all_s['class'] + ")"
            selected_student_ca = st.selectbox("Tafuta/Chagua Mwanafunzi Uhakiki Progress yake:", df_all_s['search_label'].tolist())
            
            s_reg = df_all_s[df_all_s['search_label'] == selected_student_ca].iloc[0]['reg_no']
            
            with sqlite3.connect(DB_NECTA) as conn:
                df_stud_scores = pd.read_sql_query("SELECT exam_name, subject_code, score FROM exam_scores WHERE reg_no=? AND score IS NOT NULL", conn, params=(s_reg,))
                
            if df_stud_scores.empty:
                st.info("Mwanafunzi huyu bado hajazimwa alama za mtihani wowote.")
            else:
                ca_pivot = df_stud_scores.pivot_table(index='exam_name', columns='subject_code', values='score', aggfunc='mean').reindex(EXAMS_LIST).dropna(how='all')
                
                # Kutengeneza Bar Graph ya Plotly kwa Mwanafunzi
                df_plot = ca_pivot.reset_index().melt(id_vars='exam_name', var_name='SOMO', value_name='ALAMA')
                df_plot = df_plot.dropna(subset=['ALAMA'])
                
                fig_stud = px.bar(df_plot, x='exam_name', y='ALAMA', color='SOMO', barmode='group',
                                  title=f"Mchanganuo wa Alama kwa Mitihani - {selected_student_ca}",
                                  labels={'exam_name': 'Mtihani', 'ALAMA': 'Alama (Marks)'},
                                  color_discrete_sequence=px.colors.qualitative.Bold)
                fig_stud.update_layout(xaxis_title="Mitihani", yaxis_title="Alama", legend_title="Masomo")
                st.plotly_chart(fig_stud, use_container_width=True)
                
                st.dataframe(ca_pivot.style.highlight_max(axis=0, color='#dcfce7'), use_container_width=True)

    with tab_ca2:
        st.subheader("Ufuatiliaji wa Progress ya Somo/Darasa zima")
        with sqlite3.connect(DB_NECTA) as conn:
            df_all_sub_list = pd.read_sql_query("SELECT subject_code, subject_name FROM subjects", conn)
            
        if df_all_sub_list.empty:
            st.warning("Hakuna masomo yaliyosajiliwa bado.")
        else:
            df_all_sub_list['search_sub_label'] = df_all_sub_list['subject_code'] + " - " + df_all_sub_list['subject_name']
            col_ca_sub1, col_ca_sub2 = st.columns(2)
            with col_ca_sub1: selected_sub_ca = st.selectbox("Tafuta/Chagua Somo (Searchable):", df_all_sub_list['search_sub_label'].tolist())
            with col_ca_sub2: selected_class_ca = st.selectbox("Chagua Kidato:", ALL_CLASSES, key="ca_class_sub")
                
            sub_code_selected = df_all_sub_list[df_all_sub_list['search_sub_label'] == selected_sub_ca].iloc[0]['subject_code']
            
            with sqlite3.connect(DB_NECTA) as conn:
                df_class_sub_scores = pd.read_sql_query("SELECT exam_name, score FROM exam_scores WHERE subject_code=? AND class=? AND score IS NOT NULL", conn, params=(sub_code_selected, selected_class_ca))
                
            if df_class_sub_scores.empty:
                st.info(f"Somo la {sub_code_selected} bado halina alama zozote.")
            else:
                sub_progress = df_class_sub_scores.groupby('exam_name')['score'].mean().reindex(EXAMS_LIST).dropna()
                
                # Kutengeneza Bar Graph ya Plotly kwa Somo Zima
                df_sub_plot = sub_progress.reset_index()
                fig_sub = px.bar(df_sub_plot, x='exam_name', y='score', color='exam_name',
                                 title=f"Wastani wa Darasa: {selected_class_ca} - Somo: {selected_sub_ca}",
                                 labels={'exam_name': 'Mtihani', 'score': 'Wastani wa Alama (Class Average)'},
                                 color_discrete_sequence=px.colors.qualitative.Set2)
                fig_sub.update_layout(showlegend=False, xaxis_title="Mitihani", yaxis_title="Wastani")
                st.plotly_chart(fig_sub, use_container_width=True)

# ----------------- MODULI: MASOMO -----------------
elif choice == "📚 Sajili Masomo Yako" and st.session_state['user_role'] in ['Admin', 'Super Admin']:
    st.subheader("📚 Sajili Masomo Mapya au Hariri Masomo Yaliyopo")
    tab_s1, tab_s2 = st.tabs(["✍️ Sajili Somo Jipya", "✏️ Hariri / Futa Somo"])
    
    with tab_s1:
        with st.form("subject_form"):
            s_code = st.text_input("Kifupi cha Somo / Code * (Mfano: KISW, BIOS)").strip().upper()
            s_name = st.text_input("Jina Kamili la Somo * (Mfano: Kiswahili, Biology)")
            s_grad = st.checkbox("Je, Somo hili linahesabiwa kwenye pointi za NECTA (Grading Subject)?", value=True)
            btn_sub = st.form_submit_button("Sajili Somo")
            
        if btn_sub and s_code and s_name:
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                g_val = 1 if s_grad else 0
                c.execute("INSERT OR REPLACE INTO subjects (subject_code, subject_name, is_grading) VALUES (?,?,?)", (s_code, s_name.strip(), g_val))
                conn.commit()
            st.success(f"✔️ Somo {s_name} limesajiliwa vyema!")
            st.rerun()
            
    with tab_s2:
        with sqlite3.connect(DB_NECTA) as conn:
            all_subs_list = pd.read_sql_query("SELECT subject_code, subject_name FROM subjects", conn)
        if not all_subs_list.empty:
            all_subs_list['display_name'] = all_subs_list['subject_code'] + " - " + all_subs_list['subject_name']
            selected_sub_disp = st.selectbox("Chagua Somo la Kuedit/Kufuta:", all_subs_list['display_name'].tolist())
            selected_sub_code = all_subs_list[all_subs_list['display_name'] == selected_sub_disp].iloc[0]['subject_code']
            
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                c.execute("SELECT subject_code, subject_name, is_grading FROM subjects WHERE subject_code = ?", (selected_sub_code,))
                sub_data = c.fetchone()
                
            if sub_data:
                with st.form("edit_sub_form"):
                    e_sub_name = st.text_input("Jina la Somo", value=sub_data[1])
                    e_sub_grad = st.checkbox("Grading Subject?", value=True if sub_data[2] == 1 else False)
                    col_sbtn1, col_sbtn2 = st.columns(2)
                    with col_sbtn1: save_sub_changes = st.form_submit_button("💾 Hifadhi Marekebisho")
                    with col_sbtn2: delete_sub = st.form_submit_button("❌ Futa Somo")
                    
                if save_sub_changes:
                    g_val = 1 if e_sub_grad else 0
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE subjects SET subject_name=?, is_grading=? WHERE subject_code=?", (e_sub_name.strip(), g_val, selected_sub_code))
                        conn.commit()
                    st.success(f"✔️ Taarifa za somo {selected_sub_code} zimesasishwa!")
                    st.rerun()
                    
                if delete_sub:
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM subjects WHERE subject_code=?", (selected_sub_code,))
                        c.execute("DELETE FROM exam_scores WHERE subject_code=?", (selected_sub_code,))
                        conn.commit()
                    st.success("🗑️ Somo pamoja na alama zake zote zimefutwa kikamilifu!")
                    st.rerun()
                    
        st.markdown("---")
        with sqlite3.connect(DB_NECTA) as conn:
            df_subs_view = pd.read_sql_query("SELECT subject_code as 'CODE', subject_name as 'NAME', CASE WHEN is_grading=1 THEN '✅ Grading Subject' ELSE '❌ Non-Grading' END as 'AINA YA SOMO' FROM subjects", conn)
        st.dataframe(df_subs_view, use_container_width=True, hide_index=True)

# ----------------- MODULI YA CREDENTIALS (MABADILIKO MUHIMU: MA-ADMIN ASIONE SUPER ADMIN) -----------------
elif choice == "🔐 Manage Teachers Credentials" and st.session_state['user_role'] in ['Admin', 'Super Admin']:
    st.subheader("🔐 Usimamizi wa Akaunti za Walimu")
    tab_u1, tab_u2 = st.tabs(["✍️ Sajili Mwalimu Mpya", "✏️ Hariri / Futa Akaunti"])
    
    with tab_u1:
        with st.form("teacher_form"):
            t_user = st.text_input("Username ya Mwalimu *").strip().lower()
            t_pass = st.text_input("Password ya Kuanzia *")
            t_name = st.text_input("Jina Kamili la Mwalimu *")
            if st.session_state['user_role'] == 'Super Admin':
                t_role = st.selectbox("Role ya Mtumiaji", ["Teacher", "Admin", "Super Admin"])
            else:
                t_role = st.selectbox("Role ya Mtumiaji", ["Teacher", "Admin"])
                
            btn_user = st.form_submit_button("Hifadhi Akaunti")
            
        if btn_user and t_user and t_pass:
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO users (username, password, full_name, role) VALUES (?,?,?,?)", 
                          (t_user, t_pass, t_name, t_role))
                conn.commit()
            st.success(f"✔️ Mtumiaji {t_name} amesajiliwa kikamilifu!")
            st.rerun()
            
    with tab_u2:
        with sqlite3.connect(DB_NECTA) as conn:
            if st.session_state['user_role'] == 'Admin':
                all_users_list = pd.read_sql_query("SELECT username, full_name, role FROM users WHERE role != 'Super Admin' AND username != 'superadmin'", conn)
            else:
                all_users_list = pd.read_sql_query("SELECT username, full_name, role FROM users", conn)
                
        if not all_users_list.empty:
            all_users_list['display_name'] = all_users_list['username'] + " - " + all_users_list['full_name'] + " (" + all_users_list['role'] + ")"
            selected_user_disp = st.selectbox("Chagua Mtumiaji wa Kuedit/Kufuta:", all_users_list['display_name'].tolist())
            selected_username = all_users_list[all_users_list['display_name'] == selected_user_disp].iloc[0]['username']
            
            with sqlite3.connect(DB_NECTA) as conn:
                c = conn.cursor()
                c.execute("SELECT username, password, full_name, role FROM users WHERE username = ?", (selected_username,))
                u_data = c.fetchone()
                
            if u_data:
                with st.form("edit_user_form"):
                    edit_u_name = st.text_input("Jina Kamili", value=u_data[2])
                    edit_u_pass = st.text_input("Password", value=u_data[1])
                    
                    if st.session_state['user_role'] == 'Super Admin':
                        roles_options = ["Teacher", "Admin", "Super Admin"]
                        current_idx = roles_options.index(u_data[3]) if u_data[3] in roles_options else 0
                        edit_u_role = st.selectbox("Role", roles_options, index=current_idx)
                    else:
                        roles_options = ["Teacher", "Admin"]
                        current_idx = roles_options.index(u_data[3]) if u_data[3] in roles_options else 0
                        edit_u_role = st.selectbox("Role", roles_options, index=current_idx)
                        
                    col_ubtn1, col_ubtn2 = st.columns(2)
                    with col_ubtn1: save_u_changes = st.form_submit_button("💾 Hifadhi Marekebisho")
                    with col_ubtn2: delete_user = st.form_submit_button("❌ Futa Akaunti")
                    
                if save_u_changes:
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE users SET full_name=?, password=?, role=? WHERE username=?", 
                                  (edit_u_name.strip(), edit_u_pass, edit_u_role, selected_username))
                        conn.commit()
                    st.success("✔️ Akaunti imesasishwa kwa mafanikio!")
                    st.rerun()
                    
                if delete_user:
                    if selected_username in ["admin", "superadmin"]:
                        st.error("❌ Akaunti kuu hii haiwezi kufutwa kwa usalama vya mfumo!")
                    else:
                        with sqlite3.connect(DB_NECTA) as conn:
                            c = conn.cursor()
                            c.execute("DELETE FROM users WHERE username=?", (selected_username,))
                        conn.commit()
                        st.success("🗑️ Akaunti imefutwa kikamilifu!")
                        st.rerun()
        else:
            st.info("Hakuna akaunti zinazoweza kuhaririwa kwa sasa.")

    with sqlite3.connect(DB_NECTA) as conn:
        if st.session_state['user_role'] == 'Admin':
            df_u = pd.read_sql_query("SELECT username as 'USERNAME', full_name as 'JINA', password as 'PASSWORD', role as 'ROLE' FROM users WHERE role != 'Super Admin' AND username != 'superadmin'", conn)
        else:
            df_u = pd.read_sql_query("SELECT username as 'USERNAME', full_name as 'JINA', password as 'PASSWORD', role as 'ROLE' FROM users", conn)
            
    st.dataframe(df_u, use_container_width=True, hide_index=True)

# ----------------- MODULI YA GRADING CONFIG -----------------
elif choice == "⚙️ Grading Config" and st.session_state['user_role'] in ['Admin', 'Super Admin']:
    st.subheader("⚙️ Weka Vigezo vya Gradi (O-Level & A-Level)")
    sel_level = st.selectbox("Chagua Ngazi ya Shule:", ["O-LEVEL", "A-LEVEL"])
    
    with sqlite3.connect(DB_NECTA) as conn:
        df_curr_grades = pd.read_sql_query("SELECT grade, min_score, max_score, points FROM grading_system WHERE level=?", conn, params=(sel_level,))
    
    edited_grades = st.data_editor(df_curr_grades, use_container_width=True, hide_index=True, disabled=["grade"])
    
    if st.button("💾 Hifadhi Vigezo vya Gradi Ulizobadilisha", use_container_width=True):
        with sqlite3.connect(DB_NECTA) as conn:
            c = conn.cursor()
            for _, r in edited_grades.iterrows():
                c.execute("UPDATE grading_system SET min_score=?, max_score=?, points=? WHERE level=? AND grade=?", 
                          (int(r['min_score']), int(r['max_score']), int(r['points']), sel_level, r['grade']))
            conn.commit()
        st.success("✔️ Vigezo vipya vya makadirio ya maksi vimehifadhiwa kikamilifu!")
        st.rerun()

# ----------------- MODULI YA SETTINGS & RESET MFUMO -----------------
elif choice == "⚙️ Ripoti Settings" and st.session_state['user_role'] in ['Admin', 'Super Admin']:
    st.subheader("⚙️ Ripoti Settings & Database Utilities")
    
    # Tumeongeza tab ya tatu kwa ajili ya ku-reset mfumo
    tab_st1, tab_st2, tab_st3 = st.tabs(["📜 Kichwa cha Ripoti (Headers & Setup)", "💾 Database Backup & Restore", "🗑️ Reset Data za Mfumo"])
    
    with tab_st1:
        with sqlite3.connect(DB_NECTA) as conn:
            df_sett = pd.read_sql_query("SELECT * FROM report_settings WHERE id=1", conn)
            
        if not df_sett.empty:
            current_settings = df_sett.iloc[0]
            with st.form("settings_form"):
                in_waziri = st.text_input("Kichwa cha Juu Kabisa (Mstari wa 1)", value=current_settings['waziri_header'])
                in_tamisemi = st.text_input("Kichwa cha Pili (Mstari wa 2)", value=current_settings['tamisemi_header'])
                in_wilaya = st.text_input("Ofisi ya Wilaya / Mkoa (Mstari wa 3)", value=current_settings['wilaya_header'])
                in_shule = st.text_input("Jina Rasmi la Shule (Mstari wa 4)", value=current_settings['shule_name'])
                in_phone = st.text_input("Simu / Mawasiliano ya Shule", value=current_settings['simu_mawasiliano'])
                in_box = st.text_input("S.L.P / P.O. BOX ya Shule", value=current_settings['slp_box'])
                in_tabia = st.text_input("Default Tabia ya Wanafunzi kwenye ripoti", value=current_settings['default_tabia'])
                in_kufunga = st.text_input("Tarehe ya Shule Kufunga (Mfano: 05/06/2026)", value=current_settings.get('tarehe_kufunga', '05/06/2026'))
                in_kufungua = st.text_input("Tarehe ya Shule Kufunguliwa (Mfano: 06/07/2026)", value=current_settings['tarehe_kufungua'])
                in_maagizo = st.text_area("Maagizo ya ziada ya shule yatakayotokea chini kwenye ripoti zote", value=current_settings.get('maagizo_mengine', ''))
                
                save_settings_btn = st.form_submit_button("💾 Hifadhi Config Zote za Shule", use_container_width=True)
                
            if save_settings_btn:
                with sqlite3.connect(DB_NECTA) as conn:
                    c = conn.cursor()
                    c.execute('''UPDATE report_settings SET 
                        waziri_header=?, tamisemi_header=?, wilaya_header=?, shule_name=?, 
                        simu_mawasiliano=?, slp_box=?, default_tabia=?, tarehe_kufungua=?, maagizo_mengine=?, tarehe_kufunga=?
                        WHERE id=1''', (in_waziri.strip(), in_tamisemi.strip(), in_wilaya.strip(), in_shule.strip(), 
                                      in_phone.strip(), in_box.strip(), in_tabia.strip().upper(), in_kufungua.strip(), in_maagizo.strip(), in_kufunga.strip()))
                    conn.commit()
                st.success("✔️ Settings za kichwa cha ripoti zimesasishwa vizuri!")
                st.rerun()

    with tab_st2:
        col_bk1, col_bk2 = st.columns(2)
        with col_bk1:
            st.markdown("#### 📥 Pakua Backup ya Mfumo (Download Database)")
            st.write("Bonyeza kitufe hapa chini ili kupakua data zako zote kwa usalama.")
            try:
                with open(DB_NECTA, "rb") as f:
                    db_bytes = f.read()
                st.download_button(
                    label="📥 Pakua Database (.db File)",
                    data=db_bytes,
                    file_name="mpj_necta_academic_backup.db",
                    mime="application/octet-stream",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Imeshindwa kusoma database kwa backup: {e}")
                
        with col_bk2:
            st.markdown("#### 📤 Rejesha Mfumo (Upload Backup)")
            uploaded_backup = st.file_uploader("Chagua faili la backup (.db) ulilolipakua hapo awali:", type=["db"])
            if uploaded_backup is not None:
                if st.button("🔄 Anza Kurejesha Data (Restore Backup)", use_container_width=True):
                    try:
                        with open(DB_NECTA, "wb") as f:
                            f.write(uploaded_backup.getbuffer())
                        st.success("✅ Mfumo umerejeshwa vizuri kutoka kwenye backup! Mfumo unajirefresh sasa...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hitilafu wakati wa kurejesha backup: {e}")

    # -------- KIPENGELE KIPYA CHA KURESET DATA --------
    with tab_st3:
        st.markdown("#### ⚠️ Sehemu ya Hatari (Danger Zone)")
        st.warning("Tahadhari: Kufuta data hapa ni kwa kudumu na hakiwezi kutenguliwa. Tafadhali hakikisha umepakua 'Backup' kwenye tab iliyotangulia kabla ya kufanya hivi.")
        
        reset_option = st.radio(
            "Chagua kipi unataka kusafisha kwenye mfumo:",
            [
                "1. Futa Alama Zote za Mitihani (Wanafunzi na Masomo vitabaki)",
                "2. Futa Wanafunzi Wote (Alama zao pia zitafutwa moja kwa moja)",
                "3. Futa Masomo Yote (Alama zake pia zitafutwa moja kwa moja)",
                "4. Futa Vyote (Wanafunzi, Masomo, na Alama) - Mfumo Uwe Mpya kabisa"
            ]
        )
        
        st.markdown("---")
        hakikisha_reset = st.checkbox("Ndio, nina uhakika na ninakubali kufuta data hizi kabisa.", key="chk_reset_confirm")
        
        if st.button("🗑️ Futa Data Uliyochagua", type="primary", use_container_width=True):
            if not hakikisha_reset:
                st.error("❌ Tafadhali weka tiki kwenye kiboksi cha 'Ndio, nina uhakika' kwanza ndipo ufute.")
            else:
                with sqlite3.connect(DB_NECTA) as conn:
                    c = conn.cursor()
                    
                    if reset_option.startswith("1"):
                        c.execute("DELETE FROM exam_scores")
                        st.success("✅ Usafishaji Umekamilika: Alama zote za mitihani zimefutwa.")
                        
                    elif reset_option.startswith("2"):
                        c.execute("DELETE FROM exam_scores") # Lazima uanze na alama ili kuepusha 'orphaned data'
                        c.execute("DELETE FROM students")
                        st.success("✅ Usafishaji Umekamilika: Wanafunzi wote pamoja na alama zao wamefutwa.")
                        
                    elif reset_option.startswith("3"):
                        c.execute("DELETE FROM exam_scores")
                        c.execute("DELETE FROM subjects")
                        st.success("✅ Usafishaji Umekamilika: Masomo yote pamoja na alama zake yamefutwa.")
                        
                    elif reset_option.startswith("4"):
                        c.execute("DELETE FROM exam_scores")
                        c.execute("DELETE FROM students")
                        c.execute("DELETE FROM subjects")
                        st.success("✅ Usafishaji Umekamilika: Mfumo umesafishwa kabisa (Wanafunzi, Masomo, na Alama vimefutwa).")
                        
                    conn.commit()
                
                # Kuondoa tiki ya uhakika baada ya kufuta
                st.rerun()



# ------------------------------------- MODULI YA KUHITIMISHA WANAFUNZI (ALUMNI/GRADUATION) --------------------------------------


# -------------------------------------------------MODULI YA KU-PROMOTE WANAFUNZI ------------------------------------------------

elif choice == "🎓 Promote Wanafunzi" and st.session_state['user_role'] in ['Super Admin', 'Admin']:
    st.subheader("🎓 Promotion ya Wanafunzi")
    
    with sqlite3.connect(DB_NECTA) as conn:
        all_classes = pd.read_sql_query("SELECT DISTINCT class FROM students ORDER BY class", conn)['class'].tolist()
        
    col1, col2 = st.columns(2)
    with col1:
        f_class_from = st.selectbox("Chagua Darasa la KUTOKA:", all_classes)
    with col2:
        f_class_to = st.selectbox("Chagua Darasa la KWENDA:", all_classes)
        
    # Leta wanafunzi wa darasa hilo
    with sqlite3.connect(DB_NECTA) as conn:
        df_studs = pd.read_sql_query("SELECT reg_no, full_name FROM students WHERE class=?", conn, params=(f_class_from,))

    if not df_studs.empty:
        st.write(f"Chagua wanafunzi wa kupandishwa kutoka **{f_class_from}** kwenda **{f_class_to}**:")
        
        # Tunaongeza column ya 'select' yenye checkbox (Boolean)
        df_studs['select'] = True 
        
        # Tunatumia data_editor kuruhusu Admin kuchagua wanafunzi
        edited_df = st.data_editor(
            df_studs,
            column_config={
                "select": st.column_config.CheckboxColumn("Chagua", default=True),
                "reg_no": "Namba ya Usajili",
                "full_name": "Jina la Mwanafunzi"
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Chuja wale waliochaguliwa pekee
        selected_students = edited_df[edited_df['select'] == True]
        count = len(selected_students)
        
        if count > 0:
            if st.button(f"🚀 Pandisha Wanafunzi {count} waliochaguliwa", type="primary"):
                if f_class_from == f_class_to:
                    st.error("❌ Huwezi kupandisha darasa kwenda lilelile!")
                else:
                    # Tunabadilisha darasa kwa wale waliochaguliwa tu
                    reg_nos = tuple(selected_students['reg_no'].tolist())
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        # Query ya kubadilisha darasa kwa listi ya reg_nos
                        query = f"UPDATE students SET class=? WHERE reg_no IN {reg_nos if len(reg_nos) > 1 else f'(\"{reg_nos[0]}\")'}"
                        c.execute(query, (f_class_to,))
                        conn.commit()
                        
                    st.success(f"✅ Mafanikio! Wanafunzi {count} wamehamishiwa {f_class_to}.")
                    st.rerun()
        else:
            st.warning("⚠️ Hakuna mwanafunzi aliyeteuliwa kwa ajili ya promotion.")
    else:
        st.warning("⚠️ Hakuna wanafunzi kwenye darasa la kuanzia.")


    st.markdown("---")
    st.subheader("🎓 Graduation: Futa Wanafunzi Waliomaliza Shule")
    st.warning("Tahadhari: Kitendo hiki kitawafuta wanafunzi wa madarasa uliyochagua kwenye orodha ya wanafunzi wanaosoma (Active Students).")
    
    with sqlite3.connect(DB_NECTA) as conn:
        all_classes_grad = pd.read_sql_query("SELECT DISTINCT class FROM students ORDER BY class", conn)['class'].tolist()
        
    # Multiselect inaruhusu kuchagua Form 4 na Form 6 kwa pamoja
    selected_classes_grad = st.multiselect("Chagua madarasa yote yanayohitimu:", all_classes_grad)
    
    if selected_classes_grad:
        with sqlite3.connect(DB_NECTA) as conn:
            # Tunabadilisha listi ya madarasa kuwa format inayokubalika na SQL
            classes_tuple = tuple(selected_classes_grad)
            query_placeholder = ','.join(['?'] * len(classes_tuple))
            
            df_grad = pd.read_sql_query(f"SELECT * FROM students WHERE class IN ({query_placeholder})", conn, params=classes_tuple)
            
        st.write(f"Wanafunzi {len(df_grad)} wamepatikana kwenye madarasa uliyochagua:")
        st.dataframe(df_grad[['reg_no', 'full_name', 'class']], use_container_width=True)
        
        if st.checkbox("Nathibitisha kufuta wanafunzi hawa wote kwa pamoja."):
            if st.button("🗑️ Futa Wanafunzi Waliomaliza", type="primary"):
                with sqlite3.connect(DB_NECTA) as conn:
                    c = conn.cursor()
                    # Futa wanafunzi hao
                    c.execute(f"DELETE FROM students WHERE class IN ({query_placeholder})", classes_tuple)
                    conn.commit()
                st.success(f"✅ Mafanikio! Wanafunzi wote wa {', '.join(selected_classes_grad)} wamehitimu na kuondolewa.")
                st.rerun()
    else:
        st.info("Tafadhali chagua angalau darasa moja (mfano: Form 4, Form 6) ili kuanza.")

# =====================================================================
# CODE ZA CHINI KABISA: KUZUIA MFUMO KURUDI LOGIN PAGE UKIREFRESH
# =====================================================================
if st.session_state.get('logged_in', False):
    if 'current_choice' not in st.session_state:
        st.session_state['current_choice'] = choice
else:
    if not st.session_state['logged_in'] and choice != "📊 Dashboard & Status":
        st.session_state['logged_in'] = False
        st.rerun()

if st.runtime.exists():
    pass



                                         #=======================================================================#
                                         # MODULI MPYA: FOMU YA KUPRINT ORODHA NA ALAMA (ISAL) / MAHUDHURIO (CAL)#
                                         #=======================================================================#

if choice == "🖨️ ISAL, CAL and sitting plan":
    st.markdown("<h3 style='color: #1e3a8a;'>🖨️ Tengeneza Fomu za Karatasi (Alama & Mahudhurio)</h3>", unsafe_allow_html=True)
    st.write("Sanidi darasa na mkondo ili kutoa fomu rasmi ya karatasi kwa ajili ya matumizi ya darasani.")
    
    # Kuchukua taarifa za shule kutoka kwenye report_settings
    with sqlite3.connect(DB_NECTA) as conn:
        cfg_res = pd.read_sql_query("SELECT * FROM report_settings WHERE id=1", conn)
        cfg = cfg_res.iloc[0] if not cfg_res.empty else {}
        
    h_waziri = str(cfg.get('waziri_header', 'OFISI YA WAZIRI MKUU')).upper()
    h_tamisemi = str(cfg.get('tamisemi_header', 'TAWALA ZA MIKOA NA SERIKALI ZA MITAA')).upper()
    h_wilaya = str(cfg.get('wilaya_header', 'HALMASHAURI YA WILAYA YA PANGANI')).upper()
    h_shule = str(cfg.get('shule_name', 'PANGANI HALISI SECONDARY SCHOOL')).upper()

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        selected_class = st.selectbox("Chagua Darasa:", ALL_CLASSES, key="score_sheet_class")
    with col_f2:
        with sqlite3.connect(DB_NECTA) as conn:
            df_streams = pd.read_sql_query("SELECT DISTINCT stream_or_comb FROM students WHERE class=?", conn, params=(selected_class,))
        streams_list = df_streams['stream_or_comb'].dropna().tolist()
        if not streams_list:
            streams_list = ["A", "B", "C"]
        selected_stream = st.selectbox("Chagua Mkondo/Kombinisho:", streams_list, key="score_sheet_stream")
        
    vyeo_vya_mitihani = st.text_input("Jina la Mtihani / Shughuli:", "FOMU YA KUINGIZA ALAMA NA SAINI (ISAL)")
    
    # KIPENGELE KIPYA: Kuchagua Somo kwa ajili ya Score Sheet
    # Unaweza kutumia orodha ya masomo kutoka kwenye mfumo wako (kama ipo kwenye variables zako)
    ORODHA_MASOMO = ["CIVICS", "HISTORY", "GEOGRAPHY", "KISWAHILI", "ENGLISH", "PHYSICS", "CHEMISTRY", "BIOLOGY", "BASIC MATHEMATICS"]
    selected_subject = st.selectbox("Chagua Somo (Kwa ajili ya Fomu ya Alama):", ORODHA_MASOMO, key="score_sheet_subject")

    # Orodha ya masomo fupi fupi kwa ajili ya fomu ya mahudhurio ya pamoja
    MASOMO_YOTE = ["CIV", "HIST", "GEO", "KISW", "ENGL", "PHY", "CHEM", "BIO", "B/MATH"]

    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        btn_score = st.button("📊 Fomu ya Alama (Score Sheet)", type="primary", use_container_width=True)
    with col_btn2:
        btn_attendance = st.button("📝 Fomu ya Mahudhurio ya Masomo", type="secondary", use_container_width=True)
    with col_btn3:
        btn_sitting = st.button("🪑 Sitting Plan (S-Shape)", type="secondary", use_container_width=True)

    #################################### 1. KIKUNDI CHA FOMU YA ALAMA (SASA INA SOMO NA MWAKA WA AUTOMATIC)######################################
    if btn_score:
        with sqlite3.connect(DB_NECTA) as conn:
            df_studs = pd.read_sql_query(
                "SELECT reg_no, full_name, gender FROM students WHERE class=? AND stream_or_comb=? ORDER BY full_name ASC", 
                conn, params=(selected_class, selected_stream)
            )
            
        if df_studs.empty:
            st.warning(f"⚠️ Hakuna wanafunzi waliopatikana kwenye darasa la {selected_class} Mkondo {selected_stream}.")
        else:
            table_rows_html = ""
            for idx, row in df_studs.iterrows():
                table_rows_html += f"""
                <tr>
                    <td style='text-align: center;'>{idx + 1}</td>
                    <td style='text-align: center;'>{row['reg_no']}</td>
                    <td>{str(row['full_name']).upper()}</td>
                    <td style='text-align: center;'>{row['gender']}</td>
                    <td style='width: 15%;'></td>
                    <td style='width: 20%;'></td>
                </tr>
                """
                
            form_print_html = f"""
            <html><head><style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 10px; color: #000; background-color: #fff; line-height: 1.3; }}
                .print-wrapper {{ max-width: 850px; margin: 0 auto; border: 1px solid #000; padding: 20px; background-color: #fff; }}
                .no-print-btn {{ background-color: #1e3a8a; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; margin-bottom: 20px; display: block; margin-left: auto; margin-right: auto; }}
                .no-print-btn:hover {{ background-color: #1d4ed8; }}
                .header-title {{ text-align: center; font-weight: bold; font-size: 13px; margin: 0; }}
                .school-name {{ text-align: center; font-weight: bold; font-size: 18px; color: #000; margin: 4px 0; text-transform: uppercase; }}
                .form-title {{ text-align: center; font-size: 14px; font-weight: bold; margin: 10px 0; text-transform: uppercase; text-decoration: underline; }}
                
                .meta-table {{ width: 100%; margin-bottom: 15px; font-size: 13px; font-weight: bold; }}
                .main-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }}
                .main-table th {{ background-color: #f2f2f2; color: #000; font-weight: bold; text-transform: uppercase; font-size: 11px; padding: 6px; border: 1px solid #000; }}
                .main-table td {{ border: 1px solid #000; padding: 6px; text-align: left; height: 24px; }}
                
                .footer-section {{ width: 100%; margin-top: 40px; font-size: 13px; page-break-inside: avoid; }}
                .footer-table {{ width: 100%; border-collapse: collapse; }}
                .footer-table td {{ border: none; padding: 10px; vertical-align: top; }}
                .stamp-box {{ border: 1px dashed #000; width: 140px; height: 100px; text-align: center; vertical-align: middle; font-size: 11px; color: #555; font-style: italic; }}
                
                @media print {{
                    body {{ padding: 0; }}
                    .print-wrapper {{ border: none; padding: 0; max-width: 100%; }}
                    .no-print-btn {{ display: none !important; }}
                    @page {{ margin: 1.5cm; }}
                }}
            </style></head><body>
                <button class="no-print-btn" onclick="window.print()">📥 Print Fomu ya Alama / Hifadhi kama PDF</button>
                <div class="print-wrapper">
                    <div class="header-title">{h_waziri}</div>
                    <div class="header-title">{h_tamisemi}</div>
                    <div class="header-title">{h_wilaya}</div>
                    <div class="school-name">{h_shule}</div>
                    <div class="form-title">{vyeo_vya_mitihani}</div>
                    
                    <table class="meta-table">
                        <tr>
                            <td>DARASA: <span style='font-weight:normal;'>{selected_class.upper()}</span></td>
                            <td style='text-align: right;'>MKONDO / COMB: <span style='font-weight:normal;'>{selected_stream.upper()}</span></td>
                        </tr>
                        <tr>
                            <td>SOMO: <span style='font-weight:bold; color:#1e3a8a;'>{selected_subject.upper()}</span></td>
                            <td style='text-align: right;'>MWAKA: <span style='font-weight:normal;'>{datetime.now().year}</span></td>
                        </tr>
                    </table>
                    
                    <table class="main-table">
                        <thead>
                            <tr>
                                <th style="width: 5%;">Na.</th>
                                <th style="width: 15%;">Namba ya Usajili</th>
                                <th style="width: 35%;">Jina Kamili la Mwanafunzi</th>
                                <th style="width: 8%;">Jinsia</th>
                                <th style="width: 17%;">SCORE</th>
                                <th style="width: 20%;">SAINI YA MWANAFUNZI</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows_html}
                        </tbody>
                    </table>
                    
                    <div class="footer-section">
                        <table class="footer-table">
                            <tr>
                                <td style="width: 40%;">
                                    <strong>MSIMAMIZI WA MKONDO:</strong><br><br>
                                    Jina: ........................................................<br><br>
                                    Sahihi: ....................................................<br><br>
                                    Tarehe: ......./......./20......
                                </td>
                                <td style="width: 20%; text-align: center;">
                                    <div class="stamp-box"><br><br>MUHURI WA<br>SHULE</div>
                                </td>
                                <td style="width: 40%; text-align: right;">
                                    <strong>MKUU WA SHULE:</strong><br><br>
                                    Jina: ........................................................<br><br>
                                    Sahihi: ....................................................<br><br>
                                    Tarehe: ......./......./20......
                                </td>
                            </tr>
                        </table>
                    </div>
                </div>
            </body></html>"""
            st.components.v1.html(form_print_html, height=900, scrolling=True)

    ####################################### 2. KIKUNDI CHA FOMU YA MAHUDHURIO (MWAKA WA AUTOMATIC)###########################################
    if btn_attendance:
        with sqlite3.connect(DB_NECTA) as conn:
            df_studs = pd.read_sql_query(
                "SELECT reg_no, full_name, gender FROM students WHERE class=? AND stream_or_comb=? ORDER BY full_name ASC", 
                conn, params=(selected_class, selected_stream)
            )
            
        if df_studs.empty:
            st.warning(f"⚠️ Hakuna wanafunzi waliopatikana kwenye darasa la {selected_class} Mkondo {selected_stream}.")
        else:
            subject_headers_html = "".join([f"<th style='width: 6%; font-size: 9px; text-align: center;'>{sub}</th>" for sub in MASOMO_YOTE])
            
            table_rows_html = ""
            for idx, row in df_studs.iterrows():
                subject_cells_html = "".join(["<td style='text-align: center;'></td>" for _ in MASOMO_YOTE])
                table_rows_html += f"<tr><td style='text-align: center;'>{idx + 1}</td><td>{str(row['full_name']).upper()}</td><td style='text-align: center;'>{row['gender']}</td>{subject_cells_html}<td></td></tr>"
                
            form_attendance_html = f"""
            <html><head><style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 10px; color: #000; background-color: #fff; }}
                .print-wrapper {{ max-width: 950px; margin: 0 auto; border: 1px solid #000; padding: 20px; }}
                .no-print-btn {{ background-color: #16a34a; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; display: block; margin: 10px auto; }}
                .header-title {{ text-align: center; font-weight: bold; font-size: 12px; margin: 0; }}
                .school-name {{ text-align: center; font-weight: bold; font-size: 16px; margin: 4px 0; text-transform: uppercase; }}
                .form-title {{ text-align: center; font-size: 13px; font-weight: bold; margin: 10px 0; text-transform: uppercase; text-decoration: underline; }}
                .meta-table {{ width: 100%; margin-bottom: 10px; font-size: 12px; font-weight: bold; }}
                .main-table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
                .main-table th {{ background-color: #f2f2f2; border: 1px solid #000; padding: 5px; text-transform: uppercase; text-align: center; }}
                .main-table td {{ border: 1px solid #000; padding: 5px; height: 25px; }}
                .footer-section {{ width: 100%; margin-top: 30px; font-size: 12px; page-break-inside: avoid; }}
                .footer-table {{ width: 100%; border-collapse: collapse; }}
                .stamp-box {{ border: 1px dashed #000; width: 120px; height: 80px; text-align: center; vertical-align: middle; font-size: 10px; font-style: italic; }}
                @media print {{ .no-print-btn {{ display: none !important; }} .print-wrapper {{ border: none; padding: 0; max-width: 100%; }} @page {{ margin: 1cm; size: A4 portrait; }} }}
            </style></head><body>
                <button class="no-print-btn" onclick="window.print()">📥 Print Fomu ya Mahudhurio / Hifadhi kama PDF</button>
                <div class="print-wrapper">
                    <div class="header-title">{h_waziri}</div>
                    <div class="header-title">{h_tamisemi}</div>
                    <div class="header-title">{h_wilaya}</div>
                    <div class="school-name">{h_shule}</div>
                    <div class="form-title">FOMU RASMI YA MAHUDHURIO NA SAINI YA WANAFUNZI (CAL)</div>
                    
                    <table class="meta-table">
                        <tr>
                            <td>DARASA: <span style='font-weight:normal;'>{selected_class.upper()}</span></td>
                            <td style='text-align: right;'>MKONDO / COMB: <span style='font-weight:normal;'>{selected_stream.upper()}</span></td>
                        </tr>
                        <tr>
                            <td>WIKI / MUHULA: .........................</td>
                            <td style='text-align: right;'>MWAKA: <span style='font-weight:normal;'>{datetime.now().year}</span></td>
                        </tr>
                    </table>
                    
                    <table class="main-table">
                        <thead>
                            <tr>
                                <th style="width: 4%;" rowspan="2">Na.</th>
                                <th style="width: 32%; text-align: left;" rowspan="2">Jina Kamili la Mwanafunzi</th>
                                <th style="width: 5%;" rowspan="2">Jinsia</th>
                                <th colspan="{len(MASOMO_YOTE)}">WEKA TICK (✓) KWA KILA SOMO ALILOHUDHURIA</th>
                                <th style="width: 18%;" rowspan="2">SAINI YA MWANAFUNZI</th>
                            </tr>
                            <tr>{subject_headers_html}</tr>
                        </thead>
                        <tbody>{table_rows_html}</tbody>
                    </table>
                    
                    <div class="footer-section">
                        <table class="footer-table">
                            <tr>
                                <td style="width: 40%;"><strong>MKUU WA SKULI / MKUU WA TAALUMA:</strong><br><br>Jina: ........................................................<br><br>Sahihi: ....................................................</td>
                                <td style="width: 20%; text-align: center;"><div class="stamp-box"><br>MUHURI WA<br>SHULE</div></td>
                                <td style="width: 40%; text-align: right;"><strong>MSIMAMIZI WA MKONDO (CLASS TEACHER):</strong><br><br>Jina: ........................................................<br><br>Sahihi: ....................................................</td>
                            </tr>
                        </table>
                    </div>
                </div>
            </body></html>"""
            st.components.v1.html(form_attendance_html, height=900, scrolling=True)

    # =====================================================================
    # 3. KIKUNDI CHA SITTING PLAN: VERTICAL COLUMN-BASED S-SHAPE (PORTRAIT + FLUID DOOR)
    # =====================================================================
    if "show_sitting_plan" not in st.session_state:
        st.session_state.show_sitting_plan = False

    if btn_sitting:
        st.session_state.show_sitting_plan = True

    if st.session_state.show_sitting_plan:
        with sqlite3.connect(DB_NECTA) as conn:
            df_studs = pd.read_sql_query(
                "SELECT reg_no, full_name, gender FROM students WHERE class=? AND stream_or_comb=? ORDER BY reg_no ASC", 
                conn, params=(selected_class, selected_stream)
            )
            
        if df_studs.empty:
            st.warning(f"⚠️ Hakuna wanafunzi waliopatikana kwenye darasa la {selected_class} Mkondo {selected_stream}.")
            st.session_state.show_sitting_plan = False
        else:
            total_students = len(df_studs)
            st.info(f"📋 Jumla ya Wanafunzi Waliopo: {total_students}")
            
            st.markdown("#### 🛠️ Sanidi Mpangilio wa Chumba (Safu kwa Safu - Portrait)")
            
            col_set1, col_set2 = st.columns(2)
            with col_set1:
                num_cols = st.number_input("Idadi ya Safu Wima (Columns) Darasani:", min_value=1, max_value=10, value=4, step=1, key="sit_num_cols_stable")
                start_side = st.selectbox("Namba Ndogo Ianzie Column ya Upande Gani?", ["Kushoto", "Kulia"], key="sit_start_side_stable")
            with col_set2:
                num_rows = st.number_input("Idadi ya Viti/Meza kwa kila Column (Rows kwenda Nyuma):", min_value=1, max_value=50, value=6, step=1, key="sit_num_rows_stable")
                door_side = st.selectbox("Mlango wa Darasa Upo Upande Gani kwa Mbele?", ["Kushoto", "Kulia"], key="sit_door_side_stable")
            
            capacity = num_cols * num_rows
            if capacity < total_students:
                st.error(f"❌ Nafasi haitoshi! Chumba kina uwezo wa viti {capacity} tu, lakini wanafunzi ni {total_students}. Ongeza viti kwa kila Column au ongeza idadi ya Columns.")
            else:
                # 1. KUTENGENEZA MATRIX TUPU YA CHUMBA
                seating_matrix = [[None for _ in range(num_cols)] for _ in range(num_rows)]
                students_list = df_studs.to_dict('records')
                
                # 2. ALGORITHM YA S-SHAPE KWA KUTUMIA COLUMNS
                ordered_coordinates = []
                cols_order = list(range(num_cols)) if start_side == "Kushoto" else list(range(num_cols - 1, -1, -1))
                
                s_counter = 0
                for c in cols_order:
                    if s_counter % 2 == 0:
                        rows_order = list(range(num_rows))
                    else:
                        rows_order = list(range(num_rows - 1, -1, -1))
                    
                    for r in rows_order:
                        ordered_coordinates.append((r, c))
                    s_counter += 1
                
                for idx, stud in enumerate(students_list):
                    if idx < len(ordered_coordinates):
                        r, c = ordered_coordinates[idx]
                        seating_matrix[r][c] = stud
                
                # 3. KUTENGENEZA RAMANI YA HTML (DESKS GRID)
                grid_items_html = ""
                for r in range(num_rows):
                    for c in range(num_cols):
                        stud = seating_matrix[r][c]
                        if stud:
                            names = stud['full_name'].split()
                            short_name = f"{names[0]} {names[-1]}" if len(names) > 1 else names[0]
                            
                            grid_items_html += f"""
                            <div class="desk-space">
                                <div class="desk-top">
                                    <div class="exam-no">{stud['reg_no']}</div>
                                    <div class="student-name">{short_name}</div>
                                    <div class="student-gender">({stud['gender']})</div>
                                </div>
                                <div class="chair"></div>
                            </div>
                            """
                        else:
                            grid_items_html += """
                            <div class="desk-space empty-space">
                                <div class="desk-top" style="background: #fafafa; border: 1px dashed #ccc; box-shadow: none;">
                                    <div style="color:#aaa; font-style:italic; margin-top:12px; font-size:10px;">WAZI</div>
                                </div>
                            </div>
                            """
                
                # Udhibiti thabiti wa Mlango kwa kutumia Flexbox Order na Alignment
                door_flex_direction = "row" if door_side == "Kushoto" else "row-reverse"
                
                # HTML na CSS iliyorekebishwa
                sitting_print_html = f"""
                <html>
                <head>
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 10px; color: #000; background-color: #fff; }}
                    .print-wrapper {{ max-width: 790px; margin: 0 auto; border: 1px solid #000; padding: 20px; background: #fff; position: relative; }}
                    .no-print-btn {{ background-color: #8b5cf6; color: white; padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; display: block; margin: 10px auto; font-size: 14px; }}
                    
                    .header-title {{ text-align: center; font-weight: bold; font-size: 11px; margin: 0; }}
                    .school-name {{ text-align: center; font-weight: bold; font-size: 15px; margin: 4px 0; text-transform: uppercase; }}
                    .form-title {{ text-align: center; font-size: 12px; font-weight: bold; margin: 10px 0; text-transform: uppercase; text-decoration: underline; }}
                    
                    .meta-table {{ width: 100%; margin-bottom: 15px; font-size: 12px; font-weight: bold; border-collapse: collapse; }}
                    
                    /* MFUMO MPYA WA FLEXBOX KUSHUGHULIKIA MLANGO */
                    .front-wall-area {{ 
                        width: 100%; 
                        margin-bottom: 25px; 
                        display: flex; 
                        flex-direction: column;
                    }}
                    .directions-bar {{ 
                        background-color: #e5e7eb; 
                        border: 1px solid #9ca3af; 
                        padding: 6px; 
                        text-align: center; 
                        font-size: 10px; 
                        font-weight: bold; 
                        text-transform: uppercase; 
                        letter-spacing: 1px; 
                    }}
                    
                    .door-container-row {{
                        display: flex;
                        flex-direction: {door_flex_direction};
                        width: 100%;
                        margin-top: 2px;
                    }}
                    
                    .classroom-door {{
                        width: 100px;
                        background-color: #b45309; 
                        color: #fff;
                        font-size: 9px;
                        font-weight: bold;
                        text-align: center;
                        padding: 5px 0;
                        border: 2px solid #374151;
                        text-transform: uppercase;
                        box-sizing: border-box;
                    }}
                    
                    .room-grid {{ 
                        display: grid; 
                        grid-template-columns: repeat({num_cols}, 1fr); 
                        gap: 20px 15px; 
                        margin-top: 15px;
                    }}
                    
                    .desk-space {{ display: flex; flex-direction: column; align-items: center; justify-content: center; }}
                    
                    .desk-top {{
                        width: 100%; max-width: 140px; height: 60px; border: 2px solid #374151; border-radius: 4px;
                        background-color: #fef08a; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                        text-align: center; padding: 3px; box-sizing: border-box; position: relative;
                    }}
                    
                    .exam-no {{ font-size: 9px; font-weight: bold; color: #1e3a8a; background: #fff; border: 1px solid #374151; border-radius: 2px; padding: 1px 2px; display: inline-block; margin-bottom: 1px; }}
                    .student-name {{ font-size: 10px; font-weight: bold; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #000; }}
                    .student-gender {{ font-size: 8px; color: #4b5563; font-weight: 500; }}
                    
                    .chair {{ width: 45px; height: 15px; border: 2px solid #374151; border-top: none; background-color: #d1d5db; border-radius: 0 0 4px 4px; margin-top: 2px; }}
                    .empty-space {{ opacity: 0.4; }}
                    
                    @media print {{
                        .no-print-btn {{ display: none !important; }}
                        .print-wrapper {{ border: none; padding: 0; max-width: 100%; }}
                        body {{ background: #fff; }}
                        .desk-top {{ background-color: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                        .classroom-door {{ background-color: #b45309 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                        @page {{ margin: 1cm; size: A4 portrait; }}
                    }}
                </style>
                </head>
                <body>
                    <button class="no-print-btn" onclick="window.print()">📥 Print Sitting Plan Map (Portrait) / PDF</button>
                    
                    <div class="print-wrapper">
                        <div class="header-title">{h_waziri}</div>
                        <div class="header-title">{h_tamisemi}</div>
                        <div class="header-title">{h_wilaya}</div>
                        <div class="school-name">{h_shule}</div>
                        <div class="form-title">RAMANI YA MPANGILIO WA KUKAA KATIKA MITIHANI (FLEXIBLE S-SHAPE)</div>
                        
                        <table class="meta-table">
                            <tr>
                                <td>DARASA: <span style='font-weight:normal;'>{selected_class.upper()}</span></td>
                                <td style='text-align: center;'>MKONDO / COMB: <span style='font-weight:normal;'>{selected_stream.upper()}</span></td>
                                <td style='text-align: right;'>MWAKA: <span style='font-weight:normal;'>{datetime.now().year}</span></td>
                            </tr>
                        </table>
                        
                        <div class="front-wall-area">
                            <div class="directions-bar">⬇️ UKUTA WA MBELE / BLACKBOARD / MEZA YA MSIMAMIZI ⬇️</div>
                            <div class="door-container-row">
                                <div class="classroom-door">🚪 Mlango</div>
                            </div>
                        </div>
                        
                        <div class="room-grid">
                            {grid_items_html}
                        </div>
                        
                        <div style="margin-top: 35px; font-size: 11px; font-style: italic; color: #374151; text-align: center; border-top: 1px dashed #ccc; padding-top: 10px;">
                            * Mfumo wa Mtiririko: Wanafunzi wamepangwa kwa usahihi kwa namba za usajili safu kwa safu kuanzia upande wa <strong>{start_side}</strong> katika muundo wa karatasi ya Wima (Portrait). Mlango mkuu upo mbele upande wa <strong>{door_side}</strong>.
                        </div>
                    </div>
                </body>
                </html>
                """
                st.components.v1.html(sitting_print_html, height=1100, scrolling=True)




# =====================================================================
# MODULI YA RATIBA YA ZAMU ZA WALIMU (WITH CUSTOM REMARKS & PDF GENERATOR)
# =====================================================================
elif choice == "📅 Ratiba ya Zamu za Walimu":
    st.title("📅 Zamu za Walimu (Auto-Duty Roster)")
    st.markdown("---")
    
    # 1. SEHEMU YA KUTENGENEZA RATIBA (Admin & Super Admin Tu)
    if st.session_state.get('user_role') in ['Admin', 'Super Admin']:
        st.subheader("🎲 Tengeneza Ratiba ya Zamu")
        
        with st.form("auto_roster_form_custom"):
            col1, col2 = st.columns(2)
            with col1:
                s_date = st.date_input("Tarehe ya Kuanza Ratiba (Jumatatu):")
                wiki_ngapi = st.number_input("Unataka kutengeneza zamu za Wiki ngapi?", min_value=1, max_value=54, value=4)
                idadi_kwa_wiki = st.slider("Idadi ya walimu kwa kila wiki (Zamu moja):", min_value=1, max_value=4, value=2)
            with col2:
                walimu_input = st.text_area(
                    "Ingiza Orodha ya Walimu Wote (Tenganisha kwa mkato):", 
                    value="Mwl. Juma, Mwl. Anna, Mwl. Kipanya, Mwl. Maria, Mwl. John, Mwl. Amina"
                )
                # SEHEMU YA KUANDIKA MAJUKUMU WEWE MWENYEWE
                majukumu_binafsi = st.text_area(
                    "Andika Majukumu ya Walimu wa Zamu:", 
                    value="Kusimamia mapokezi, usafi wa mazingira, nidhamu na nishati shuleni."
                )
            
            generate_btn = st.form_submit_button("Generate Roster 🚀", use_container_width=True)
            
            if generate_btn:
                lista_ya_walimu = [w.strip() for w in walimu_input.split(",") if w.strip()]
                
                if len(lista_ya_walimu) < idadi_kwa_wiki:
                    st.error("❌ Idadi ya walimu walioingizwa ni ndogo sana kulinganisha na idadi ya walimu kwa wiki!")
                else:
                    import random
                    from datetime import timedelta
                    
                    random.shuffle(lista_ya_walimu)
                    current_start = s_date
                    walimu_index = 0
                    
                    with sqlite3.connect(DB_NECTA) as conn:
                        c = conn.cursor()
                        
                        for w_idx in range(wiki_ngapi):
                            current_end = current_start + timedelta(days=4) # Jumatatu hadi Ijumaa
                            
                            wiki_teachers = []
                            for _ in range(idadi_kwa_wiki):
                                wiki_teachers.append(lista_ya_walimu[walimu_index % len(lista_ya_walimu)])
                                walimu_index += 1
                                
                            walimu_wa_zamu_str = ", ".join(wiki_teachers)
                            
                            c.execute(
                                "INSERT INTO teacher_duty (start_date, end_date, teacher_names, remarks) VALUES (?, ?, ?, ?)",
                                (str(current_start), str(current_end), walimu_wa_zamu_str, majukumu_binafsi.strip())
                            )
                            current_start = current_start + timedelta(days=7)
                            
                        conn.commit()
                    
                    if 'log_action' in globals():
                        log_action("GENERATE_ROSTER", f"Amezalisha ratiba ya wiki {wiki_ngapi} kiotomatiki.")
                        
                    st.success(f"✅ Ratiba imetengenezwa kwa mafanikio na majukumu uliyoyaandika yamehifadhiwa!")
                    st.rerun()

    # =====================================================================
    # 2. SEHEMU YA KUONESHA RATIBA NA KU-DOWNLOAD PDF (Inaonekana na Users Wote)
    # =====================================================================
    st.markdown("---")
    st.subheader("📋 Ratiba ya Zamu Iliyopo Mfumoni 📋")
    
    with sqlite3.connect(DB_NECTA) as conn:
        df_duty = pd.read_sql_query(
            "SELECT id AS 'ID', start_date AS 'Kuanza (Jumatatu)', end_date AS 'Kuisha (Ijumaa)', teacher_names AS 'Walimu wa Zamu', remarks AS 'Majukumu ya Wiki' FROM teacher_duty ORDER BY start_date ASC", 
            conn
        )
        
    if df_duty.empty:
        st.info("📭 Hakuna ratiba iliyotengenezwa bado. Bofya 'Generate Roster' hapo juu.")
    else:
        # Onyesha jedwali kwanza kwenye screen ya Streamlit ili uhakikishe data zipo
        st.dataframe(df_duty, use_container_width=True, hide_index=True)
        
        # --- Kazi ya kutengeneza PDF inafanyika hapa chini ili kuzuia kurasa kuwa blank ---
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        
        # 1. Kazi ya ku-convert DataFrame kwenda PDF bytes (Inaitwa pale tu mtu akibonyeza download)
        def create_duty_pdf(data_frame):
            pdf_buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                pdf_buffer, 
                pagesize=landscape(letter), 
                rightMargin=30, 
                leftMargin=30, 
                topMargin=30, 
                bottomMargin=30
            )
            story = []
            
            styles = getSampleStyleSheet()
            
            school_title_style = ParagraphStyle(
                'SchoolTitleStyle',
                parent=styles['Heading1'],
                fontSize=24,
                leading=28,
                textColor=colors.HexColor('#1e3a8a'),
                alignment=1,
                fontName='Helvetica-Bold',
                spaceAfter=5
            )
            
            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading2'],
                fontSize=14,
                leading=18,
                textColor=colors.HexColor('#475569'),
                alignment=1,
                fontName='Helvetica-Bold',
                spaceAfter=20
            )
            
            cell_style = ParagraphStyle('CellText', parent=styles['Normal'], fontSize=10, leading=14)
            header_style = ParagraphStyle('HeaderText', parent=styles['Normal'], fontSize=11, leading=14, textColor=colors.white, fontName='Helvetica-Bold')

            # --- Kusoma jina la shule kutoka database ---
            with sqlite3.connect(DB_NECTA) as conn_db:
                school_res = conn_db.execute("SELECT shule_name FROM report_settings WHERE id=1").fetchone()
                jina_la_shule = school_res[0] if school_res else "MPJ SECONDARY SCHOOL"

            # --- Kusoma Mwaka wa Sasa Kiotomatiki ---
            mwaka_wa_sasa = datetime.now().year

            # --- Weka Vichwa vya Habari kwenye PDF (Pamoja na Mwaka) ---
            story.append(Paragraph(jina_la_shule.upper(), school_title_style))
            story.append(Paragraph(f"RATIBA YA ZAMU ZA WALIMU - MWAKA {mwaka_wa_sasa} (TEACHER DUTY ROSTER)", title_style))
            story.append(Spacer(1, 30))
            
            # Tengeneza table data upya kutoka kwenye data_frame iliyopitishwa (Sio ile ya nje)
            table_data = [[
                Paragraph("S/N", header_style), 
                Paragraph("Kuanza (Jumatatu)", header_style), 
                Paragraph("Kuisha (Ijumaa)", header_style), 
                Paragraph("Walimu wa Zamu", header_style), 
                Paragraph("Majukumu / Maelezo", header_style)
            ]]
            
            for idx, row in data_frame.iterrows():
                table_data.append([
                    Paragraph(str(idx + 1), cell_style),
                    Paragraph(str(row['Kuanza (Jumatatu)']), cell_style),
                    Paragraph(str(row['Kuisha (Ijumaa)']), cell_style),
                    Paragraph(str(row['Walimu wa Zamu']), cell_style),
                    Paragraph(str(row['Majukumu ya Wiki']), cell_style)
                ])
                
            duty_table = Table(table_data, colWidths=[40, 110, 110, 180, 280])
            duty_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ]))


            
            story.append(duty_table)
            doc.build(story)
            pdf_buffer.seek(0)
            return pdf_buffer.getvalue()

        # 2. Kitufe sasa kinachukua data moja kwa moja kutoka kwenye function iliyosheheni data halisi
        st.download_button(
            label="🖨️ Pakua Ratiba Hii kama PDF (Beautiful Report)",
            data=create_duty_pdf(df_duty),
            file_name=f"ratiba_ya_zamu_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        
        # 3. KUFUTA RATIBA (Admin Tu)
        if st.session_state.get('user_role') in ['Admin', 'Super Admin']:
            st.markdown("---")
            if st.button("Futa Ratiba Zote na Uanze Upya 🗑️", type="primary", use_container_width=True):
                with sqlite3.connect(DB_NECTA) as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM teacher_duty")
                    conn.commit()
                if 'log_action' in globals():
                    log_action("CLEAR_DUTY_ROSTER", "Amefuta ratiba zote za zamu.")
                st.success("✅ Ratiba zote zimefutwa kikamilifu!")

# =====================================================================
# MODULI YA KALENDA YA SHULE NA KITAALUMA (MODERN CALENDAR & PDF PRINT)
# =====================================================================
elif choice == "📅 Kalenda ya Shule":
    st.markdown("<h2 style='color: #1e3a8a;'>📅 Kalenda ya Shule na Kitaaluma (Academic Calendar)</h2>", unsafe_allow_html=True)
    st.markdown("---")
    
    # 1. SEHEMU YA ADMIN KUSAJILI MATUKIO (Admin & Super Admin Tu)
    if st.session_state.get('user_role') in ['Admin', 'Super Admin']:
        with st.expander("➕ Sajili Tukio Jipya kwenye Kalenda", expanded=False):
            with st.form("calendar_form_modern", clear_on_submit=True):
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    e_date = st.date_input("Tarehe ya Tukio:")
                    e_name = st.text_input("Jina la Tukio:", placeholder="Mfano: Mitihani ya Terminal, Kikao cha Wazazi")
                with col_c2:
                    e_type = st.selectbox("Aina ya Tukio:", ["Mitihani (Exams)", "Likizo (Holidays)", "Vikao (Meetings)", "Michezo & Utamaduni", "Sikukuu", "Matukio Mengine"])
                    e_desc = st.text_area("Maelezo ya Ziada (Hiari):", placeholder="Andika maelezo mafupi kuhusu tukio hili...")
                    
                submit_event = st.form_submit_button("Hifadhi Tukio Kwenye Kalenda 🚀", use_container_width=True)
                if submit_event:
                    if not e_name.strip():
                        st.error("❌ Tafadhali jaza Jina la Tukio!")
                    else:
                        with sqlite3.connect(DB_NECTA) as conn:
                            c = conn.cursor()
                            c.execute("INSERT INTO school_calendar (event_date, event_name, event_type, description) VALUES (?, ?, ?, ?)",
                                      (str(e_date), e_name.strip(), e_type, e_desc.strip()))
                            conn.commit()
                        
                        if 'log_action' in globals():
                            log_action("ADD_CALENDAR_EVENT", f"Amesajili tukio: {e_name} tarehe {e_date}")
                            
                        st.success("✅ Tukio limehifadhiwa kwenye kalenda kikamilifu!")
                        st.rerun()

    # 2. KUSOMA DATA KUTOKA DATABASE
    with sqlite3.connect(DB_NECTA) as conn:
        df_cal = pd.read_sql_query(
            "SELECT id AS 'ID', event_date AS 'Tarehe', event_name AS 'Tukio / Shughuli', event_type AS 'Aina ya Tukio', description AS 'Maelezo ya Ziada' FROM school_calendar ORDER BY event_date ASC", 
            conn
        )
        
    if df_cal.empty:
        st.info("📭 Kalenda haina matukio yaliyosajiliwa kwa sasa. Tumia fomu ya juu kuongeza.")
    else:
        # Muonekano wa Kisasa wa Kadi (Dashboard Cards) kwa kila aina ya tukio ndani ya Streamlit
        st.subheader("📊 Muhtasari wa Matukio Yajayo")
        counts = df_cal['Aina ya Tukio'].value_counts()
        
        c_cols = st.columns(len(counts) if len(counts) > 0 else 1)
        for i, (t_type, count) in enumerate(counts.items()):
            with c_cols[i % len(c_cols)]:
                st.markdown(f"""
                <div style='background-color: #f1f5f9; padding: 15px; border-radius: 8px; border-left: 5px solid #1e3a8a; text-align: center;'>
                    <span style='color: #475569; font-size: 14px; font-weight: bold;'>{t_type}</span><br>
                    <span style='font-size: 24px; font-weight: bold; color: #1e3a8a;'>{count}</span>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df_cal, use_container_width=True, hide_index=True)
        
        # --- UTENGENEZAJI WA PDF YA KISASA (Modern Layout) ---
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        
        def create_modern_calendar_pdf(data_frame):
            pdf_buffer = io.BytesIO()
            # topMargin = 30 ili kuanza juu kabisa kwenye kurasa za mbele
            doc = SimpleDocTemplate(
                pdf_buffer, 
                pagesize=landscape(letter), 
                rightMargin=30, 
                leftMargin=30, 
                topMargin=30, 
                bottomMargin=40
            )
            story = []
            styles = getSampleStyleSheet()
            
            # Kichwa cha Kisasa cha Shule (Ukurasa wa Kwanza Tu)
            def weka_header_ukurasa_wa_kwanza_tu(canvas, doc):
                canvas.saveState()
                with sqlite3.connect(DB_NECTA) as conn_db:
                    school_res = conn_db.execute("SELECT shule_name FROM report_settings WHERE id=1").fetchone()
                    jina_la_shule = school_res[0] if school_res else "PANGANI HALISI SECONDARY SCHOOL"
                
                mwaka_wa_sasa = datetime.now().year
                
                # Jina la Shule (Bold & Professional)
                canvas.setFont('Helvetica-Bold', 24)
                canvas.setFillColor(colors.HexColor('#1e3a8a')) # Royal Blue
                canvas.drawCentredString(landscape(letter)[0] / 2.0, landscape(letter)[1] - 40, jina_la_shule.upper())
                
                # Jina la Ripoti ya Kisasa
                canvas.setFont('Helvetica-Bold', 13)
                canvas.setFillColor(colors.HexColor('#475569')) # Slate Grey
                canvas.drawCentredString(landscape(letter)[0] / 2.0, landscape(letter)[1] - 58, f"KALENDA RASMI YA SHULE NA RATIBA YA KITAALUMA • MWAKA {mwaka_wa_sasa}")
                
                # Mstari mwembamba wa kisasa (Slate look)
                canvas.setStrokeColor(colors.HexColor('#cbd5e1'))
                canvas.setLineWidth(1)
                canvas.line(30, landscape(letter)[1] - 70, landscape(letter)[0] - 30, landscape(letter)[1] - 70)
                canvas.restoreState()

            # Mitindo ya maandishi ya jedwali (Fonts & Typography)
            cell_style = ParagraphStyle('CellText', parent=styles['Normal'], fontSize=10, leading=14, fontName='Helvetica')
            header_style = ParagraphStyle('HeaderText', parent=styles['Normal'], fontSize=11, leading=14, textColor=colors.white, fontName='Helvetica-Bold')
            
            # Row Header ya Jedwali kwenye PDF
            table_data = [[
                Paragraph("S/N", header_style), 
                Paragraph("Tarehe ya Tukio", header_style), 
                Paragraph("Tukio / Shughuli ya Kitaaluma", header_style), 
                Paragraph("Aina ya Shughuli", header_style), 
                Paragraph("Maelezo Kamili na Maagizo", header_style)
            ]]
            
            for idx, row in data_frame.iterrows():
                # Kubadili tarehe kuwa muonekano mzuri wa kusomeka (Mfano: 2026-06-25 kuwa 25/06/2026)
                try:
                    tarehe_safi = datetime.strptime(str(row['Tarehe']), "%Y-%m-%d").strftime("%d/%m/%Y")
                except:
                    tarehe_safi = str(row['Tarehe'])

                table_data.append([
                    Paragraph(str(idx + 1), cell_style),
                    Paragraph(tarehe_safi, cell_style),
                    Paragraph(str(row['Tukio / Shughuli']), cell_style),
                    Paragraph(str(row['Aina ya Tukio']), cell_style),
                    Paragraph(str(row['Maelezo ya Ziada']) if row['Maelezo ya Ziada'] else "-", cell_style)
                ])
                
            # repeatRows=1 inahakikisha vichwa vya jedwali pekee vinajirudie kila kurasa
            cal_table = Table(table_data, colWidths=[35, 105, 200, 120, 260], repeatRows=1)
            
            # Mitindo ya jedwali la kisasa (No heavy black lines, sleek backgrounds)
            cal_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')), # Header ya Bluu ya Kiofisi
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white]), # Pishana Kijivu Laini na Nyeupe
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')), # Mstari laini sana wa kijivu
            ]))
            
            # Spacer inasukuma jedwali chini kwenye ukurasa wa kwanza tu ili lisigongane na jina la shule
            story.append(Spacer(1, 50))
            story.append(cal_table)
            
            # Kichwa kikuu cha shule kitatokea ukurasa wa kwanza tu (onLaterPages=None), row header ya jedwali itajirudia yenyewe
            doc.build(story, onFirstPage=weka_header_ukurasa_wa_kwanza_tu, onLaterPages=None)
            pdf_buffer.seek(0)
            return pdf_buffer.getvalue()
            
        st.markdown("---")
        st.download_button(
            label="🖨️ Print / Pakua Kalenda ya Shule (Modern PDF Report)",
            data=create_modern_calendar_pdf(df_cal),
            file_name=f"Kalenda_ya_Shule_{datetime.now().year}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        
      # =====================================================================
        # 3. SEHEMU YA USIMAMIZI: KUHARIRI NA KUFUTA MATUKIO (Admin Tu)
        # =====================================================================
        if st.session_state.get('user_role') in ['Admin', 'Super Admin']:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("🛠️ Usimamizi, Uhariri na Ufutaji wa Matukio"):
                
                # Tunatengeneza Tab mbili tofauti kwa ajili ya Uhariri na Ufutaji
                tab_edit, tab_delete = st.tabs(["✏️ Hariri Tukio (Edit)", "🗑️ Futa Tukio (Delete)"])
                
                # --- TAB 1: KUHARIRI TUKIO ---
                with tab_edit:
                    st.markdown("##### Kurekebisha Taarifa za Tukio")
                    edit_id = st.number_input("Ingiza ID ya Tukio unalotaka kuhariri:", min_value=1, step=1, key="edit_ev_id")
                    
                    # Kitufe cha kupakua data zilizopo ili mtumiaji azione kabla ya kuzi-update
                    if st.button("Tafuta Tukio 🔍", key="fetch_event_btn"):
                        with sqlite3.connect(DB_NECTA) as conn:
                            ev_data = conn.execute(
                                "SELECT event_date, event_name, event_type, description FROM school_calendar WHERE id=?", 
                                (edit_id,)
                            ).fetchone()
                        
                        if ev_data:
                            st.session_state[f"ev_date_{edit_id}"] = datetime.strptime(ev_data[0], "%Y-%m-%d").date()
                            st.session_state[f"ev_name_{edit_id}"] = ev_data[1]
                            st.session_state[f"ev_type_{edit_id}"] = ev_data[2]
                            st.session_state[f"ev_desc_{edit_id}"] = ev_data[3]
                            st.success(f"✅ Data za Tukio ID {edit_id} zimepatikana! Rekebisha hapo chini:")
                        else:
                            st.error("❌ Hakuna tukio lenye ID hiyo!")
                    
                    # Fomu ya kufanya mabadiliko (Inatokea ikiwa data zilishatafutwa)
                    if f"ev_name_{edit_id}" in st.session_state:
                        with st.form(f"form_edit_{edit_id}"):
                            col_e1, col_e2 = st.columns(2)
                            with col_e1:
                                new_date = st.date_input("Tarehe Mpya:", value=st.session_state[f"ev_date_{edit_id}"])
                                new_name = st.text_input("Jina Jipya la Tukio:", value=st.session_state[f"ev_name_{edit_id}"])
                            with col_e2:
                                # Kupata index ya aina ya tukio iliyokuwepo
                                types_list = ["Mitihani (Exams)", "Likizo (Holidays)", "Vikao (Meetings)", "Michezo & Utamaduni", "Sikukuu", "Matukio Mengine"]
                                try:
                                    old_type_idx = types_list.index(st.session_state[f"ev_type_{edit_id}"])
                                except:
                                    old_type_idx = 0
                                    
                                new_type = st.selectbox("Aina Mpya ya Tukio:", types_list, index=old_type_idx)
                                new_desc = st.text_area("Maelezo Mipya ya Ziada:", value=st.session_state[f"ev_desc_{edit_id}"])
                                
                            update_btn = st.form_submit_button("Hifadhi Mabadiliko 💾", use_container_width=True)
                            if update_btn:
                                if not new_name.strip():
                                    st.error("❌ Jina la tukio haliwezi kuwa tupu!")
                                else:
                                    with sqlite3.connect(DB_NECTA) as conn:
                                        c = conn.cursor()
                                        c.execute(
                                            "UPDATE school_calendar SET event_date=?, event_name=?, event_type=?, description=? WHERE id=?",
                                            (str(new_date), new_name.strip(), new_type, new_desc.strip(), edit_id)
                                        )
                                        conn.commit()
                                    
                                    if 'log_action' in globals():
                                        log_action("EDIT_CALENDAR_EVENT", f"Amehariri tukio ID {edit_id}: {new_name}")
                                        
                                    st.success("🎉 Mabadiliko yamehifadhiwa kikamilifu!")
                                    
                                    # Kusafisha session state
                                    del st.session_state[f"ev_name_{edit_id}"]
                                    st.rerun()
                
                # --- TAB 2: KUFUTA MATUKIO (Kama ilivyokuwa mwanzo) ---
                with tab_delete:
                    col_del1, col_del2 = st.columns([2, 1])
                    with col_del1:
                        event_id_to_delete = st.number_input("Ingiza ID ya Tukio unalotaka kufuta:", min_value=1, step=1, key="del_modern_ev_id")
                        if st.button("Futa Tukio Hili 🗑️", type="primary"):
                            with sqlite3.connect(DB_NECTA) as conn:
                                c = conn.cursor()
                                c.execute("DELETE FROM school_calendar WHERE id=?", (event_id_to_delete,))
                                conn.commit()
                            if 'log_action' in globals():
                                log_action("DELETE_CALENDAR_EVENT", f"Amefuta tukio lenye ID {event_id_to_delete}")
                            st.success(f"✅ Tukio lenye ID {event_id_to_delete} limefutwa!")
                            st.rerun()
                    with col_del2:
                        st.write("")
                        st.write("")
                        if st.button("Futa Kalenda Nzima ⚠️", type="secondary", use_container_width=True):
                            with sqlite3.connect(DB_NECTA) as conn:
                                c = conn.cursor()
                                c.execute("DELETE FROM school_calendar")
                                conn.commit()
                            if 'log_action' in globals():
                                log_action("CLEAR_SCHOOL_CALENDAR", "Amefuta kalenda nzima ya shule")
                            st.success("✅ Kalenda yote imefutwa kikamilifu!")
                            st.rerun()




