import streamlit as st
import json, os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import yfinance as yf
import ssl

# ══════════════════════════════════════════
# Mac OS SSL 인증서 우회
# ══════════════════════════════════════════
try: _create_unverified_https_context = ssl._create_unverified_context
except AttributeError: pass
else: ssl._create_default_https_context = _create_unverified_https_context

st.set_page_config(page_title="Wealth Manager Pro", page_icon="💎", layout="wide", initial_sidebar_state="expanded")

# ══════════════════════════════════════════
# 🔥 다크모드 테마 & 대시보드 전용 CSS 주입
# ══════════════════════════════════════════
st.markdown("""
<style>
    .stApp { background-color: #121418; color: #E2E8F0; }
    .top-header { display: flex; justify-content: space-between; align-items: flex-end; padding: 20px 0px; border-bottom: 1px solid #2D3748; margin-bottom: 30px; }
    .total-asset-title { font-size: 1.1rem; color: #A0AEC0; margin-bottom: 5px; }
    .total-asset-value { font-size: 3.5rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; margin:0; }
    .goal-container { width: 300px; text-align: right; }
    .goal-text { font-size: 0.9rem; color: #A0AEC0; margin-bottom: 8px; display: flex; justify-content: space-between;}
    .progress-bg { background-color: #2D3748; height: 10px; border-radius: 5px; width: 100%; overflow: hidden; }
    .progress-bar { background: linear-gradient(90deg, #4A90E2, #48BB78); height: 100%; border-radius: 5px; }
    .goal-percent { font-size: 2rem; font-weight: 700; color: #63B3ED; margin-top: 5px; }
    .asset-card { background-color: #1A202C; border-radius: 16px; padding: 24px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); height: 100%; border: 1px solid #2D3748; }
    .card-icon { font-size: 1.5rem; margin-bottom: 12px; }
    .card-title { font-size: 0.9rem; color: #A0AEC0; margin-bottom: 8px; }
    .card-value { font-size: 1.6rem; font-weight: 700; color: #FFFFFF; margin-bottom: 10px; }
    .card-percent { font-size: 0.9rem; color: #718096; }
</style>
""", unsafe_allow_html=True)

# "1억 6,000만원" 형식으로 보여주는 함수
def format_krw(amount):
    if amount == 0: return "0원"
    is_negative = amount < 0
    amount = abs(amount)
    
    eok = int(amount // 100000000)
    man = int((amount % 100000000) // 10000)
    won = int(amount % 10000)
    
    res = ""
    if eok > 0: res += f"{eok:,}억 "
    if man > 0: res += f"{man:,}만"
    if eok == 0 and man == 0 and won > 0: res += f"{won:,}"
    
    res = res.strip() + "원"
    return f"-{res}" if is_negative else res

# ══════════════════════════════════════════
# 주식 리스트 및 종목명 매핑
# ══════════════════════════════════════════
@st.cache_data(ttl=86400)
def get_stock_universe():
    try:
        import FinanceDataReader as fdr
        d, n = {}, []
        for _, r in fdr.StockListing('KRX').iterrows():
            t = r['Code'] + (".KS" if r['Market'] == 'KOSPI' else ".KQ")
            name = f"🇰🇷 {r['Name']} ({t})"
            d[name] = t; n.append(name)
        for _, r in fdr.StockListing('S&P500').iterrows():
            name = f"🇺🇸 {r['Name']} ({r['Symbol']})"
            d[name] = r['Symbol']; n.append(name)
        return d, n
    except:
        b = {"🇰🇷 삼성전자 (005930.KS)": "005930.KS", "🇺🇸 Apple (AAPL)": "AAPL"}
        return b, list(b.keys())

stock_map, stock_list_display = get_stock_universe()
ticker_to_name = {ticker: name.split(' (')[0][3:].strip() for name, ticker in stock_map.items()}

# ══════════════════════════════════════════
# 데이터 관리
# ══════════════════════════════════════════
def load_users():
    # 서버 꼬임 방지를 위해 파일 대신 코드에 아이디/비번을 직접 고정합니다.
    return {
        "admin": "1234",
        "user1": "1234",    # user1 추가
        "user2": "5678"     # user2 추가 (원하는대로 계속 줄을 늘려서 추가 가능합니다)
    }
def login():
    users = load_users()
    if "user" not in st.session_state: st.session_state.user = None
    if st.session_state.user: return st.session_state.user
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.title("🔐 Wealth Manager")
        with st.form("login_form"):
            u = st.text_input("아이디")
            p = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인", use_container_width=True):
                if u in users and users[u] == p: st.session_state.user = u; st.rerun()
                else: st.error("오류")
    st.stop()

user = login()

def load_data(user):
    os.makedirs("data/users", exist_ok=True)
    path = f"data/users/{user}.json"
    default_monthly = [{"월": f"{i}월", "수입": 0, "저축": 0, "추가 수입": 0, "메모(설,상여 등)": ""} for i in range(1, 13)]
    default_expenses = {"경조사": [], "생활비": [], "소비항목": [], "여행": [], "보험_세금": [], "자동차": [], "가구_기타": []}
    
    if not os.path.exists(path):
        d = {"real_estate": [], "cash": [], "stocks": [], "settings": {"goal":1000000000}, "spreadsheet": {"monthly": default_monthly, "expenses": default_expenses}}
        with open(path, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
        return d
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
        if "settings" not in d: d["settings"] = {"goal":1000000000}
        if "spreadsheet" not in d: d["spreadsheet"] = {"monthly": default_monthly, "expenses": default_expenses}
        return d

def save_data(user, data):
    with open(f"data/users/{user}.json", "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data(user)

# ══════════════════════════════════════════
# 자산 계산
# ══════════════════════════════════════════
@st.cache_data(ttl=300)
def get_exchange_rates():
    try: return {"USD_KRW": round(float(yf.Ticker("USDKRW=X").history(period="1d")["Close"].iloc[-1]),1)}
    except: return {"USD_KRW": 1350.0}

@st.cache_data(ttl=300)
def get_stock_price(ticker):
    try: return float(yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1])
    except: return 0.0

rates = get_exchange_rates()
def get_fx(ticker): return 1 if str(ticker).upper().endswith((".KS", ".KQ")) else rates["USD_KRW"]

def calc_asset_details():
    re = sum(r.get("current_price", 0) for r in data["real_estate"])
    ca = sum(c.get("amount", 0) for c in data["cash"])
    stk = sum(get_stock_price(s.get("ticker", "")) * float(s.get("quantity", 0)) * get_fx(s.get("ticker", "")) for s in data["stocks"])
    return {"total": re + ca + stk, "re": re, "ca": ca, "stk": stk}

assets = calc_asset_details()

# ══════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════
with st.sidebar:
    st.markdown(f"### 👤 {user}님")
    if st.button("🚪 로그아웃", use_container_width=True): st.session_state.user = None; st.rerun()
    st.divider()
    menu = st.radio("메뉴", ["📊 대시보드", "🗓️ 월간 현금흐름 (시트)", "🏢 부동산", "💵 현금", "📈 주식", "🔥 FIRE 시뮬레이터", "⚙️ 설정"], label_visibility="collapsed")
    st.divider()
    st.metric("USD/KRW 환율", f"{rates['USD_KRW']:,}원")

# ══════════════════════════════════════════
# 1. 대시보드
# ══════════════════════════════════════════
if menu == "📊 대시보드":
    goal = data['settings'].get('goal', 1000000000)
    goal_pct = (assets['total'] / goal * 100) if goal > 0 else 0
    
    st.markdown(f"""
    <div class="top-header">
        <div>
            <div class="total-asset-title">총 자산</div>
            <div class="total-asset-value">{format_krw(assets['total'])}</div>
        </div>
        <div class="goal-container">
            <div class="goal-text"><span>목표 달성률</span><span>{format_krw(goal)} 목표</span></div>
            <div class="progress-bg">
                <div class="progress-bar" style="width: {min(goal_pct, 100)}%;"></div>
            </div>
            <div class="goal-percent">{goal_pct:.1f}%</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    pct_ca = (assets['ca'] / assets['total'] * 100) if assets['total'] else 0
    pct_stk = (assets['stk'] / assets['total'] * 100) if assets['total'] else 0
    pct_re = (assets['re'] / assets['total'] * 100) if assets['total'] else 0

    c1, c2, c3 = st.columns(3)
    cards = [(c1, "💰", "현금/예적금", assets['ca'], pct_ca), (c2, "📈", "주식/ETF", assets['stk'], pct_stk), (c3, "🏠", "부동산", assets['re'], pct_re)]
    
    for col, icon, title, val, pct in cards:
        with col:
            st.markdown(f"""
            <div class="asset-card">
                <div class="card-icon">{icon}</div>
                <div class="card-title">{title}</div>
                <div class="card-value">{format_krw(val)}</div>
                <div class="card-percent">{pct:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)
            
    st.write("") # 화면 충돌 방지용 여백

    if assets['total'] > 0:
        df_assets = pd.DataFrame({"자산군": ["부동산", "현금", "주식"], "금액": [assets['re'], assets['ca'], assets['stk']]})
        df_assets = df_assets[df_assets["금액"] > 0]
        fig = go.Figure(data=[go.Pie(labels=df_assets['자산군'], values=df_assets['금액'], hole=0.65, textinfo='label+percent', textfont=dict(size=16, color="white"), hoverinfo='label+value', marker=dict(colors=['#FAC858', '#5470C6', '#91CC75'], line=dict(color='#121418', width=2)))])
        fig.update_layout(title_text="자산 포트폴리오 비중", title_font_size=18, title_font_color="#A0AEC0", showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5, font=dict(color="#A0AEC0")), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=40, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════
# 2. 🗓️ 월간 현금흐름
# ══════════════════════════════════════════
elif menu == "🗓️ 월간 현금흐름 (시트)":
    current_year = datetime.now().year
    st.title(f"🗓️ {current_year}년 저축 및 지출 계획표")
    
    with st.expander("📸 토스/은행 캡쳐 이미지로 자동 입력하기 (AI Vision)", expanded=False):
        st.info("💡 토스나 은행 앱의 지출 내역 캡쳐본을 올리면, AI가 숫자를 판독하여 아래 표에 자동 분류해 줍니다.")
        uploaded_file = st.file_uploader("이미지 파일 업로드 (JPG, PNG)", type=["png", "jpg", "jpeg"])
        if uploaded_file is not None:
            col1, col2 = st.columns([1, 2])
            with col1: st.image(uploaded_file, caption="업로드된 캡쳐본", use_column_width=True)
            with col2:
                st.success("판독 대기중! (현재는 시뮬레이션 UI입니다)")
                st.warning("🚧 실제 작동을 위해서는 OpenAI API Key (GPT-4o Vision) 연동 코드가 필요합니다.")

    st.info("💡 셀에 금액을 입력하고 엔터를 치면 천단위 콤마(,)가 자동으로 적용되며 저장됩니다.")

    df_monthly = pd.DataFrame(data["spreadsheet"]["monthly"])
    df_monthly["수입+추가"] = df_monthly["수입"] + df_monthly["추가 수입"]
    df_monthly["저축률(%)"] = (df_monthly["저축"] / df_monthly["수입+추가"] * 100).fillna(0).round(1)
    
    m_config = {
        "수입": st.column_config.NumberColumn(step=10000),
        "저축": st.column_config.NumberColumn(step=10000),
        "추가 수입": st.column_config.NumberColumn(step=10000),
        "저축률(%)": st.column_config.NumberColumn(format="%.1f %%")
    }

    edited_monthly = st.data_editor(df_monthly[["월", "수입", "저축", "저축률(%)", "추가 수입", "메모(설,상여 등)"]], use_container_width=True, disabled=["월", "저축률(%)"], hide_index=True, column_config=m_config)
    
    new_monthly = [{"월": r["월"], "수입": int(r["수입"]) if pd.notna(r["수입"]) else 0, "저축": int(r["저축"]) if pd.notna(r["저축"]) else 0, "추가 수입": int(r["추가 수입"]) if pd.notna(r["추가 수입"]) else 0, "메모(설,상여 등)": str(r["메모(설,상여 등)"]) if pd.notna(r["메모(설,상여 등)"]) else ""} for _, r in edited_monthly.iterrows()]
    
    # 🔥 에러 방지: st.toast 삭제하고 st.rerun()만 안전하게 호출
    if data["spreadsheet"]["monthly"] != new_monthly: 
        data["spreadsheet"]["monthly"] = new_monthly
        save_data(user, data)
        st.rerun()

    t_inc, t_sav, t_add = edited_monthly["수입"].sum(), edited_monthly["저축"].sum(), edited_monthly["추가 수입"].sum()
    st.markdown(f"**🔹 합계 ➔ 수입:** {t_inc:,.0f}원 | **저축:** {t_sav:,.0f}원 | **추가수입:** {t_add:,.0f}원 | **평균 저축률:** {(t_sav / (t_inc + t_add) * 100) if (t_inc + t_add) > 0 else 0:.1f}%")

    st.divider()
    st.subheader(f"🛒 {current_year}년 카테고리별 지출 항목")
    cat_keys = ["경조사", "생활비", "소비항목", "여행", "보험_세금", "자동차", "가구_기타"]
    edited_expenses = {}
    exp_col_config = {"금액": st.column_config.NumberColumn(step=1000)}

    cols1 = st.columns(4)
    for i in range(4):
        with cols1[i]:
            st.markdown(f"**{cat_keys[i]}**")
            df_exp = pd.DataFrame(data["spreadsheet"]["expenses"][cat_keys[i]]) if data["spreadsheet"]["expenses"][cat_keys[i]] else pd.DataFrame(columns=["항목", "금액"])
            edited_expenses[cat_keys[i]] = st.data_editor(df_exp, num_rows="dynamic", use_container_width=True, hide_index=True, key=f"e_{cat_keys[i]}", column_config=exp_col_config)
            
    cols2 = st.columns(4)
    for i in range(4, 7):
        with cols2[i-4]:
            st.markdown(f"**{cat_keys[i]}**")
            df_exp = pd.DataFrame(data["spreadsheet"]["expenses"][cat_keys[i]]) if data["spreadsheet"]["expenses"][cat_keys[i]] else pd.DataFrame(columns=["항목", "금액"])
            edited_expenses[cat_keys[i]] = st.data_editor(df_exp, num_rows="dynamic", use_container_width=True, hide_index=True, key=f"e_{cat_keys[i]}", column_config=exp_col_config)

    any_c = False
    for key in cat_keys:
        nl = [{"항목": str(r["항목"]).strip(), "금액": int(r["금액"]) if pd.notna(r["금액"]) else 0} for _, r in edited_expenses[key].iterrows() if pd.notna(r["항목"]) and str(r["항목"]).strip() != ""]
        if data["spreadsheet"]["expenses"][key] != nl: 
            data["spreadsheet"]["expenses"][key] = nl
            any_c = True
            
    # 🔥 에러 방지용 안전 저장
    if any_c: 
        save_data(user, data)
        st.rerun()

    # 🔥 에러 방지: Streamlit 네이티브 마크다운 색상 문법 적용 (:red[...])
    grand_total_expense = sum([df["금액"].sum() for df in edited_expenses.values() if not df.empty])
    st.markdown(f"### 🔴 총 지출 예상액 합계: :red[{grand_total_expense:,.0f} 원]")

# ══════════════════════════════════════════
# 3~5. 부동산, 현금, 주식
# ══════════════════════════════════════════
elif menu == "🏢 부동산":
    st.title("🏢 부동산 관리")
    st.info("💡 시세를 입력하고 엔터를 치면 천단위 콤마(,)가 자동으로 찍힙니다.")
    
    df = pd.DataFrame(data["real_estate"])
    if not df.empty: df.columns = ["자산명", "현재 시세 (원)"]
    else: df = pd.DataFrame(columns=["자산명", "현재 시세 (원)"])
    
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="re", column_config={"현재 시세 (원)": st.column_config.NumberColumn(step=10000)})
    
    new_data = [{"name": str(r["자산명"]).strip(), "current_price": int(r["현재 시세 (원)"]) if pd.notna(r["현재 시세 (원)"]) else 0} for _, r in edited_df.iterrows() if pd.notna(r["자산명"]) and str(r["자산명"]).strip() != ""]
    if data["real_estate"] != new_data: 
        data["real_estate"] = new_data
        save_data(user, data)
        st.rerun()

elif menu == "💵 현금":
    st.title("💵 현금 및 계좌 관리")
    st.info("💡 금액을 입력하고 엔터를 치면 천단위 콤마(,)가 자동으로 찍힙니다.")
    
    df = pd.DataFrame(data["cash"])
    if not df.empty: df.columns = ["계좌명", "금액 (원)"]
    else: df = pd.DataFrame(columns=["계좌명", "금액 (원)"])
    
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="ca", column_config={"금액 (원)": st.column_config.NumberColumn(step=100000)})
    
    new_data = [{"name": str(r["계좌명"]).strip(), "amount": int(r["금액 (원)"]) if pd.notna(r["금액 (원)"]) else 0} for _, r in edited_df.iterrows() if pd.notna(r["계좌명"]) and str(r["계좌명"]).strip() != ""]
    if data["cash"] != new_data: 
        data["cash"] = new_data
        save_data(user, data)
        st.rerun()

elif menu == "📈 주식":
    st.title("📈 주식 포트폴리오")
    tab1, tab2 = st.tabs(["📋 내 포트폴리오", "🔍 종목 추가"])
    with tab1:
        s_list = []
        for s in data["stocks"]:
            t, q, a = s.get("ticker",""), float(s.get("quantity",0)), float(s.get("avg_price",0))
            p, fx = get_stock_price(t), get_fx(t)
            s_list.append({"종목명": ticker_to_name.get(t, t), "티커": t, "수량": q, "평균단가": a, "현재가": p, "수익률(%)": ((p-a)/a*100) if a>0 else 0, "평가액": q*p*fx})
            
        df = pd.DataFrame(s_list) if s_list else pd.DataFrame(columns=["종목명", "티커", "수량", "평균단가", "현재가", "수익률(%)", "평가액"])
        edf = st.data_editor(
            df, num_rows="dynamic", use_container_width=True, disabled=["종목명", "티커", "현재가", "수익률(%)", "평가액"], 
            column_config={"평균단가": st.column_config.NumberColumn(format="%.2f"), "수익률(%)": st.column_config.NumberColumn(format="%.2f %%"), "평가액": st.column_config.NumberColumn(step=1000)}
        )
        new_stocks = [{"ticker": str(r["티커"]), "quantity": float(r["수량"]) if pd.notna(r["수량"]) else 0, "avg_price": float(r["평균단가"]) if pd.notna(r["평균단가"]) else 0} for _, r in edf.iterrows() if pd.notna(r["티커"])]
        if data["stocks"] != new_stocks: 
            data["stocks"] = new_stocks
            save_data(user, data)
            st.rerun()

    with tab2:
        m = st.radio("방식", ["검색", "직접입력"])
        with st.form("stk"):
            t = stock_map.get(st.selectbox("검색", ["선택"] + stock_list_display), "") if m == "검색" else st.text_input("티커")
            c1, c2 = st.columns(2)
            q, a = c1.number_input("수량", 1.0, step=1.0), c2.number_input("평균단가", 0.0, step=1000.0)
            if st.form_submit_button("포트폴리오에 추가"):
                if t and t!="선택": 
                    data["stocks"].append({"ticker":t, "quantity":float(q), "avg_price":float(a)})
                    save_data(user, data)
                    st.rerun()

# ══════════════════════════════════════════
# 6. FIRE 시뮬레이터
# ══════════════════════════════════════════
elif menu == "🔥 FIRE 시뮬레이터":
    st.title("🔥 조기 은퇴(FIRE) 시뮬레이터")
    
    df_monthly = pd.DataFrame(data["spreadsheet"]["monthly"])
    active_months = df_monthly[df_monthly["저축"] > 0]
    avg_monthly_savings = active_months["저축"].mean() if not active_months.empty else 0
    
    st.metric("📊 현재 평균 월 저축액 (시트 연동)", format_krw(avg_monthly_savings))

    goal = st.number_input("🎯 목표 은퇴 자산 (원)", value=data["settings"]["goal"], step=10000000)
    if goal != data["settings"]["goal"]: 
        data["settings"]["goal"] = goal
        save_data(user, data)
        st.rerun()

    if avg_monthly_savings <= 0:
        st.error("⚠️ 시트 메뉴에서 월 저축액을 먼저 입력해주세요!")
    else:
        sim, months, history = assets['total'], 0, [assets['total']]
        while sim < goal and months < 600:
            sim += avg_monthly_savings; months += 1
            if months % 12 == 0 or sim >= goal: history.append(sim)

        st.success(f"💡 현재 속도라면 목표 달성까지 **{months // 12}년 {months % 12}개월** 남았습니다.")
        fig = px.area(pd.DataFrame({"연차": range(len(history)), "예상 자산": history}), x="연차", y="예상 자산", markers=True)
        fig.add_hline(y=goal, line_dash="dash", line_color="green", annotation_text="목표 자산")
        st.plotly_chart(fig, use_container_width=True)

elif menu == "⚙️ 설정":
    st.title("⚙️ 설정")
    if st.button("데이터 초기화 (주의!)", type="primary"):
        os.remove(f"data/users/{user}.json")
        st.rerun()
