import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from io import BytesIO
import time
from datetime import date, datetime, timedelta
import calendar
# import graphviz


CURRENT_VERSION = "1.4.9"

# --- 頁面配置 ---
st.set_page_config(page_title="投資團隊管理系統", layout="wide")

st.markdown("""
    <style>
        /* 1. 側邊欄樣式 */
        section[data-testid="stSidebar"] { width: 300px !important; }
        section[data-testid="stSidebar"] .st-emotion-cache-17l2ba9, 
        section[data-testid="stSidebar"] p {
            font-size: 20px !important; 
            font-weight: 500 !important;
            line-height: 2.0 !important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
            margin-top: 20px !important;
            margin-bottom: 20px !important;
            padding: 10px !important;
        }
        section[data-testid="stSidebar"] h2 { font-size: 35px !important; }

        /* 2. 核心：強制置中與斑馬條紋 */
        
        /* 針對所有表格容器置中 */
        [data-testid="stDataFrame"] {
            display: flex;
            justify-content: center;
        }

        /* 🚀 斑馬條紋：針對 st.dataframe 與 st.data_editor 的底色 */
        /* 偶數行 (#F0F2F6 是 Streamlit 預設淺灰) */
        [data-testid="stDataFrame"] div[data-testid="stTable"] tr:nth-child(even),
        div[data-grid-container] tr:nth-child(even),
        .glideDataGridCanvas tr:nth-child(even) {
            background-color: #F0F2F6 !important;
        }

        /* 針對 st.data_editor 內部的渲染單元格 (Glide Data Grid) */
        /* 這可以確保在捲動或編輯時背景色依舊存在 */
        .st-emotion-cache-6v0v6f tr:nth-child(even) td {
            background-color: #F0F2F6 !important;
        }

        /* 關鍵：強制文字節點對齊與置中 */
        div[data-testid="stSelectionDataNode"] {
            display: flex !important;
            justify-content: center !important;
            text-align: center !important;
            width: 100% !important;
        }

        /* 針對 st.metric (數據指標) 置中 */
        [data-testid="stMetric"] > div {
            text-align: center !important;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        /* 針對傳統 st.table 置中與條紋 */
        .stTable td, .stTable th {
            text-align: center !important;
        }
        .stTable tr:nth-child(even) {
            background-color: #F0F2F6 !important;
        }

        /* 移除數字欄位預設的靠右對齊 */
        [data-testid="stTable"] td {
            text-align: center !important;
        }
            
        div[data-testid="stDataEditor"] tr:nth-child(even) {
            background-color: #D3D3D3 !important;
        }
    </style>
""", unsafe_allow_html=True)

def apply_zebra_style(df, format_cols=None):
    # 先做一份拷貝，不要改到原始數據
    display_df = df.copy()
    
    # 🎯 關鍵：手動找出所有數字欄位，把它們變成兩位小數的「字串」
    # 這樣 Streamlit 看到的就只是文字，不會自動補 0
    num_cols = display_df.select_dtypes(include=['number']).columns.tolist()
    for col in num_cols:
        display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}")

    # 斑馬線邏輯
    def zebra_logic(x):
        df_style = pd.DataFrame('', index=x.index, columns=x.columns)
        df_style.iloc[1::2, :] = 'background-color: #EEEAE7' # 深灰色
        return df_style

    styler = display_df.style.apply(zebra_logic, axis=None)
    return styler


# --- 資料庫連線 (使用 check_same_thread=False 確保 Streamlit 運行穩定) ---
def get_connection():
    return sqlite3.connect("data/investment.db", check_same_thread=False)

conn = get_connection()

# --- 強制檢查並補上缺失欄位 ---
def force_add_columns(conn):
    cursor = conn.cursor()
    
    # 1. 檢查並補齊 customers 的 note
    cursor.execute("PRAGMA table_info(customers)")
    cust_cols = [row[1] for row in cursor.fetchall()]
    if 'note' not in cust_cols:
        conn.execute("ALTER TABLE customers ADD COLUMN note TEXT;")
        conn.commit()

    # 2. 檢查並補齊 invest_contracts 的欄位
    cursor.execute("PRAGMA table_info(invest_contracts)")
    contract_cols = [row[1] for row in cursor.fetchall()]
    
    if 'note' not in contract_cols:
        conn.execute("ALTER TABLE invest_contracts ADD COLUMN note TEXT;")
        conn.commit()
    
    if 'is_renewed' not in contract_cols:
        conn.execute("ALTER TABLE invest_contracts ADD COLUMN is_renewed INTEGER DEFAULT 0;")
        conn.commit()
    
    cursor.execute("PRAGMA table_info(invest_contracts)")
    contract_cols = [row[1] for row in cursor.fetchall()]
    if 'contract_type' not in contract_cols:
        conn.execute("ALTER TABLE invest_contracts ADD COLUMN contract_type TEXT DEFAULT '續約';")
        conn.commit()

    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN sort_order INTEGER DEFAULT 999")
        conn.commit()
    except sqlite3.OperationalError:
        # 如果欄位已經存在，SQLite 會拋出錯誤，這裡抓到後不做事即可
        pass
    
    # try:
    #     conn.execute("UPDATE invest_contracts SET contract_type = '續約' WHERE contract_type = '新約'")
    #     conn.commit()
    #     st.toast("✅ 已成功將所有舊資料從『新約』校正為『續約』！", icon="🚀")
    # except Exception as e:
    #     st.error(f"校正失敗：{e}")

    # ⚡️ 關鍵修正：強制初始化所有 NULL 值為 0 (解決按了沒反應的問題)
    # 這行非常重要，它能把所有「隱形成空值」的舊資料全部校正回 0
    conn.execute("UPDATE invest_contracts SET is_renewed = 0 WHERE is_renewed IS NULL")
    conn.commit()
    
    # st.toast("資料庫結構檢查完成", icon="🔍")

# 執行強制檢查
force_add_columns(conn)

# --- 側邊欄導航 (由 selectbox 改為 sidebar.radio) ---
with st.sidebar:
    st.title("📂 系統總覽")
    menu = st.sidebar.radio(
        "請選擇功能模組：",
        ["📋 合約總覽","📅 到期續約管理" , "💰 收益發放試算","💰 業務佣", "👤 客戶資料管理", "🌳 團隊組織圖","➕ 新增資料", "⚙️ 基礎資料設定", "⚙️ 業務排序設定"],
        index=0,
        label_visibility="collapsed"
    )
    st.divider()
    st.info(f"今天日期：{date.today()}")
    if st.button("檢查並更新系統版本"):
        with st.status("正在連線至 GitHub API...", expanded=True) as status:
            try:
                import requests
                import re
                
                # 1. 使用 GitHub API 獲取檔案內容
                # 格式：https://api.github.com/repos/{帳號}/{專案}/contents/{路徑}
                api_url = "https://api.github.com/repos/xubingf17/invest-system/contents/admin_ui.py"
                
                # 關鍵：加入這個 Header，API 會直接回傳檔案的純文字內容 (Raw string)
                headers = {"Accept": "application/vnd.github.v3.raw"}
                
                response = requests.get(api_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    remote_code = response.text
                    
                    # 2. 提取雲端版本號 (支援單引號與雙引號)
                    version_match = re.search(r'CURRENT_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', remote_code)
                    remote_version = version_match.group(1) if version_match else "0.0.0"
                    
                    # Debug 資訊 (可視化比對)
                    # st.write(f"📡 API 抓取版本: {remote_version}")
                    # st.write(f"💻 本機目前版本: {CURRENT_VERSION}")
                    
                    if remote_version > CURRENT_VERSION:
                        status.update(label=f"🚀 發現新版本 {remote_version}！準備升級...", state="running")
                        
                        # 3. 覆寫本地檔案
                        with open("admin_ui.py", "w", encoding="utf-8") as f:
                            f.write(remote_code)
                        
                        status.update(label=f"✅ 升級完成 (v{remote_version})！請重新啟動", state="complete", expanded=False)
                        st.balloons()
                        # 提示用戶重啟或自動重整
                        st.info("系統已更新，請關閉後重新開啟應用程式以套用變更。")
                    else:
                        status.update(label=f"✅ 您的系統已是最新狀態 (v{CURRENT_VERSION})", state="complete", expanded=False)
                
                elif response.status_code == 403:
                    st.error("❌ 觸發 GitHub API 頻率限制，請稍後再試。")
                else:
                    st.error(f"❌ 無法連線至 API (HTTP {response.status_code})")
                    
            except Exception as e:
                st.error(f"❌ 檢查更新時發生錯誤：{e}")

# --- 1. 客戶資料瀏覽 ---
if menu == "📊 客戶資料瀏覽":
    st.title("👥 所有客戶與投資合約")
    query = """
    SELECT c.name as 客戶姓名, ic.amount as 投資金額, rp.annual_rate as 利率, 
           ic.start_date as 生效日, ic.end_date as 結束日, ic.status as 狀態
    FROM invest_contracts ic
    JOIN customers c ON ic.customer_id = c.customer_id
    JOIN rate_plans rp ON ic.plan_id = rp.plan_id
    """
    df = pd.read_sql(query, conn)
    st.dataframe(df, use_container_width=True)

elif menu == "💰 收益發放試算":
    st.title("💰 收益發放試算")
    st.info("💡 規則：系統會自動比對合約『生效日(Day)』是否落在您的選定區間內。已排除『生效當月』新件。")

    # --- 0. 狀態初始化 (鎖定篩選條件) ---
    if 'p_start_date' not in st.session_state:
        st.session_state.p_start_date = date.today()
    if 'p_end_date' not in st.session_state:
        st.session_state.p_end_date = date.today() + timedelta(days=7)
    
    # 鎖定進階篩選器 Key 
    for k in ['p_agent_f', 'p_plan_f', 'p_cust_f']:
        if k not in st.session_state: st.session_state[k] = []

    # --- 1. 突破月份限制的日期選取介面 ---
    with st.expander("📅 設定對帳區間", expanded=True):
        col_start, col_end = st.columns(2)
        
        with col_start:
            st.write("**起始日期**")
            s_year = st.number_input("年", value=st.session_state.p_start_date.year, key="s_y")
            s_month = st.number_input("月", min_value=1, max_value=12, value=st.session_state.p_start_date.month, key="s_m")
            s_day = st.number_input("日", min_value=1, max_value=31, value=st.session_state.p_start_date.day, key="s_d")
            try:
                start_dt = date(s_year, s_month, s_day)
            except ValueError:
                # 自動校正無效日期（如 4/31 -> 4/30）
                import calendar
                last_day = calendar.monthrange(s_year, s_month)[1]
                start_dt = date(s_year, s_month, last_day)
                st.warning(f"⚠️ 起始日已調整為該月最後一天：{start_dt}")

        with col_end:
            st.write("**結束日期**")
            e_year = st.number_input("年", value=st.session_state.p_end_date.year, key="e_y")
            e_month = st.number_input("月", min_value=1, max_value=12, value=st.session_state.p_end_date.month, key="e_m")
            e_day = st.number_input("日", min_value=1, max_value=31, value=st.session_state.p_end_date.day, key="e_d")
            try:
                end_dt = date(e_year, e_month, e_day)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(e_year, e_month)[1]
                end_dt = date(e_year, e_month, last_day)
                st.warning(f"⚠️ 結束日已調整為該月最後一天：{end_dt}")

        st.session_state.p_start_date = start_dt
        st.session_state.p_end_date = end_dt

    # --- 2. 核心 SQL 查詢（解開日期鎖定缺陷） ---
    query = f"""
    SELECT 
        c.name as 客戶姓名, b.name as 業務員, boss.name as 所屬主管,
        ic.amount / 10000.0 as '金額', rp.plan_name, rp.annual_rate as '利率',
        ic.start_date as 生效日, ic.end_date as 結束日,
        b.sort_order as 業務權重
    FROM invest_contracts ic
    JOIN customers c ON ic.customer_id = c.customer_id
    JOIN agents b ON c.agent_id = b.agent_id
    LEFT JOIN agents boss ON b.boss_id = boss.agent_id
    JOIN rate_plans rp ON ic.plan_id = rp.plan_id
    WHERE ic.start_date <= '{end_dt.isoformat()}'   -- 🎯 只要在查詢結束日前生效的都要
      AND ic.end_date >= '{start_dt.isoformat()}'   -- 🎯 且合約還沒過期的都要
    ORDER BY b.sort_order ASC, ic.start_date ASC
    """
    raw_df = pd.read_sql(query, conn)

    # # --- 3. 區間掃描 (核心邏輯) ---
    # if not raw_df.empty:
    #     def is_payout_in_range(row, s_dt, e_dt):
    #         target_day = pd.to_datetime(row['生效日']).day
    #         curr = s_dt
    #         while curr <= e_dt:
    #             # 取得當前掃描月份的最後一天是幾號
    #             _, last_day_of_month = calendar.monthrange(curr.year, curr.month)
                
    #             # 判定邏輯：
    #             # 1. 日期完全吻合 (例如 5/31 對 31號)
    #             # 2. 或者：該月比較小，且今天是該月最後一天，而單子是 31 號 (例如 4/30 對 31號)
    #             if curr.day == target_day:
    #                 return True
    #             elif curr.day == last_day_of_month and target_day > last_day_of_month:
    #                 return True
                    
    #             curr += timedelta(days=1)
    #         return False

    #     mask = raw_df.apply(lambda r: is_payout_in_range(r, start_dt, end_dt), axis=1)
    #     raw_df = raw_df[mask].copy()

        # --- 3. 區間掃描 (核心邏輯：修正跨月不一致問題) ---
    # --- 3. 區間掃描 (核心邏輯：完美版) ---
    if not raw_df.empty:
        def is_payout_in_range_final(row, s_dt, e_dt):
            start_date_raw = pd.to_datetime(row['生效日']).date()
            target_day = int(start_date_raw.day)
            
            # 遍歷查詢區間內包含的所有「年-月」
            current_yr_mo = (s_dt.year, s_dt.month)
            end_yr_mo = (e_dt.year, e_dt.month)
            
            y, m = current_yr_mo
            while (y, m) <= end_yr_mo:
                # 🎯 核心防線：排除合約生效當月的發放 (新件當月不發利息)
                if y == start_date_raw.year and m == start_date_raw.month:
                    # 這是生效當月，跳過不計算
                    pass
                else:
                    # 取得該月實際有幾天並計算借位
                    _, last_day_of_month = calendar.monthrange(y, m)
                    actual_payout_day = min(target_day, last_day_of_month)
                    actual_payout_date = date(y, m, actual_payout_day)
                    
                    # 檢查算出來的發放日有沒有落在畫面選定的區間內
                    if s_dt <= actual_payout_date <= e_dt:
                        return True
                
                # 前進下個月
                if m == 12: y += 1; m = 1
                else: m += 1
                    
            return False

        # 套用終極過濾邏輯
        mask = raw_df.apply(lambda r: is_payout_in_range_final(r, start_dt, end_dt), axis=1)
        raw_df = raw_df[mask].copy()

    # --- 4. 進階篩選與狀態保留 (這就是你要的篩選功能) ---
    if not raw_df.empty:
        raw_df['方案(利率)'] = raw_df['plan_name'] + " (" + raw_df['利率'].astype(str) + "%)"
        raw_df['本月預計發放'] = round(raw_df['金額'] * (raw_df['利率'] / 100.0), 2)
        # raw_df = raw_df.sort_values(by=['業務員', '客戶姓名']).reset_index(drop=True)

        st.write("### 🔍 進階篩選")
        f_col1, f_col2 = st.columns(2)
        
        all_agents = raw_df['業務員'].unique().tolist()
        all_plans = raw_df['方案(利率)'].unique().tolist()
        
        # 💡 防止切換日期導致舊選項消失導致 Crash 的過濾邏輯
        st.session_state.p_agent_f = [x for x in st.session_state.p_agent_f if x in all_agents]
        st.session_state.p_plan_f = [x for x in st.session_state.p_plan_f if x in all_plans]

        with f_col1:
            st.multiselect("💼 篩選業務員", all_agents, key="p_agent_f")
            st.multiselect("📈 篩選方案(利率)", all_plans, key="p_plan_f")

        with f_col2:
            # 客戶選單連動
            valid_df = raw_df[raw_df['業務員'].isin(st.session_state.p_agent_f)] if st.session_state.p_agent_f else raw_df
            all_custs = sorted(valid_df['客戶姓名'].unique().tolist())
            st.session_state.p_cust_f = [x for x in st.session_state.p_cust_f if x in all_custs]
            st.multiselect("👤 篩選客戶", all_custs, key="p_cust_f")

        # --- 5. 執行最終過濾 ---
        df_filtered = raw_df.copy()
        if st.session_state.p_agent_f:
            df_filtered = df_filtered[df_filtered['業務員'].isin(st.session_state.p_agent_f)]
        if st.session_state.p_plan_f:
            df_filtered = df_filtered[df_filtered['方案(利率)'].isin(st.session_state.p_plan_f)]
        if st.session_state.p_cust_f:
            df_filtered = df_filtered[df_filtered['客戶姓名'].isin(st.session_state.p_cust_f)]

        # --- 6. 顯示結果指標與表格 ---
        if not df_filtered.empty:
            # 🎯 [修正 1] 確保顯示清單前，先按權重與日期排序
            # 假設 SQL 裡有抓 b.sort_order as 業務權重
            df_filtered = df_filtered.sort_values(by=['業務權重', '生效日'], ascending=[True, True]).reset_index(drop=True)

            total_pay = df_filtered['本月預計發放'].sum()
            st.divider()
            st.subheader(f"📊 預計發放清單 ({start_dt} ~ {end_dt})")
            
            m1, m2 = st.columns(2)
            m1.metric("待發放筆數", f"{len(df_filtered)} 筆")
            m2.metric("總計應發利息", f"NT$ {total_pay:,.2f} 萬")

            # 顯示清單
            st.dataframe(
                apply_zebra_style(df_filtered[['客戶姓名', '業務員', '金額', '方案(利率)', '本月預計發放', '生效日']], format_cols=['金額', '本月預計發放']),
                use_container_width=True, hide_index=True, height=400
            )

            # --- 7. 底部統計總表 ---
            st.divider()
            st.subheader("📊 合約類別總表")
            try:
                # 🎯 [修正 2] 取得正確的業務員排序清單 (根據原始 raw_df 的權重)
                ordered_names = raw_df.sort_values('業務權重')['業務員'].unique().tolist()

                pivot_df = df_filtered.pivot_table(
                    index='業務員', 
                    columns='方案(利率)', 
                    values='金額', 
                    aggfunc='sum', 
                    fill_value=0
                )

                # 🎯 [修正 3] 強制樞紐表按照權重重新索引，並過濾掉沒資料的人
                pivot_df = pivot_df.reindex(ordered_names).dropna(how='all')

                # 計算合計列
                pivot_df['合計'] = df_filtered.groupby('業務員')['本月預計發放'].sum()
                
                # 準備合計列 (🏁 總計)
                total_row = pivot_df.sum(axis=0)
                total_row.name = '🏁 總計'
                
                # 合併表格
                pivot_final = pd.concat([pivot_df, total_row.to_frame().T])
                
                # 轉回欄位
                pivot_final = pivot_final.reset_index().rename(columns={'index': '業務員'})

                # 🎨 顯示樞紐表
                st.dataframe(
                    apply_zebra_style(pivot_final), 
                    use_container_width=True, 
                    hide_index=True
                )
            except Exception as e:
                # 可以考慮印出 e 來除錯：st.write(e)
                st.info("暫無足夠資料生成統計表")

            csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載發放清單 (CSV)", csv, f"payout_{start_dt}_{end_dt}.csv", use_container_width=True)
        else:
            st.warning("⚠️ 目前篩選條件下無符合資料。")
    else:
        st.warning(f"🔔 此日期區間內無任何應發放收益之合約。")

elif menu == "📋 合約總覽":
    st.title("📋 合約總覽")
    
    # --- 1. 基礎資料與環境設定 ---
    all_agents_df = pd.read_sql("SELECT agent_id, name FROM agents ORDER BY name", conn)
    
    query = """
        SELECT 
            ic.contract_id as ID, 
            c.name as 客戶姓名, 
            a.name as 業務員, 
            a.agent_id,
            ic.contract_type as 類型,
            ic.amount / 10000.0 as '金額', 
            rp.plan_name as 方案名稱, 
            rp.annual_rate as '利率',
            ic.start_date as 開始日, 
            ic.end_date as 結束日, 
            ic.note as 備註
        FROM invest_contracts ic
        JOIN customers c ON ic.customer_id = c.customer_id
        JOIN agents a ON c.agent_id = a.agent_id
        JOIN rate_plans rp ON ic.plan_id = rp.plan_id
    """
    df_raw = pd.read_sql(query, conn)

    if not df_raw.empty:
        df_raw['方案(利率)'] = df_raw['方案名稱'] + " (" + df_raw['利率'].astype(str) + "%)"
        df_raw['開始日'] = pd.to_datetime(df_raw['開始日']).dt.date
        df_raw['結束日'] = pd.to_datetime(df_raw['結束日']).dt.date
        
        this_m = date.today().replace(day=1)
        def get_status_label(d):
            if d.replace(day=1) < this_m: return "🔴 已過期"
            elif d.replace(day=1) == this_m: return "🟡 本月到期"
            else: return "🟢 進行中"
        df_raw['狀態'] = df_raw['結束日'].apply(get_status_label)

    # --- 2. 進階篩選面板 ---
    with st.expander("🔍 進階篩選面板", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        show_expired = st.session_state.get("show_exp_key", False)

        with col_f1:
            df_for_stats = df_raw.copy() if not df_raw.empty else pd.DataFrame()
            if not show_expired and not df_for_stats.empty:
                df_for_stats = df_for_stats[df_for_stats['狀態'] != "🔴 已過期"]
            
            current_counts = df_for_stats.groupby('業務員').size().to_dict() if not df_for_stats.empty else {}
            agent_labels = {name: f"{name} ({current_counts.get(name, 0)})" for name in all_agents_df['name']}
            sel_agents = st.multiselect("💼 篩選業務員", options=all_agents_df['name'].tolist(), format_func=lambda x: agent_labels.get(x, x))
            
            linked_cust_list = sorted(df_raw[df_raw['業務員'].isin(sel_agents)]['客戶姓名'].unique().tolist()) if sel_agents else sorted(df_raw['客戶姓名'].unique().tolist()) if not df_raw.empty else []
            sel_customers = st.multiselect("👤 篩選客戶姓名", options=linked_cust_list)

        with col_f2:
            all_plan_rate_list = sorted(df_raw['方案(利率)'].unique().tolist()) if not df_raw.empty else []
            sel_plans_rates = st.multiselect("📈 篩選方案 (利率)", options=all_plan_rate_list)
            
            if not df_raw.empty:
                date_range = st.date_input("📅 篩選生效日範圍", value=(df_raw['開始日'].min(), df_raw['開始日'].max()))
            else:
                date_range = (date.today(), date.today())

        # 💡 新增：備註關鍵字搜尋框
        search_note = st.text_input("📝 搜尋備註內容", placeholder="請輸入關鍵字...")

        st.write("---")
        c_sub1, c_sub2, c_sub3 = st.columns(3)
        with c_sub1:
            status_opts = ["全部", "🟢 進行中", "🟡 本月到期"]
            if show_expired: status_opts.append("🔴 已過期")
            filter_status = st.selectbox("⏳ 合約狀態", status_opts)
        with c_sub2:
            filter_type = st.selectbox("📄 合約性質", ["全部", "新約", "續約"])
        with c_sub3:
            st.write("") 
            show_expired = st.checkbox("顯示已過期合約", value=False, key="show_exp_key")

    # --- 3. 執行過濾與顯示 ---
    if not df_raw.empty:
        df_display = df_raw.copy()
        if not show_expired: df_display = df_display[df_display['狀態'] != "🔴 已過期"]
        if sel_agents: df_display = df_display[df_display['業務員'].isin(sel_agents)]
        if sel_customers: df_display = df_display[df_display['客戶姓名'].isin(sel_customers)]
        if sel_plans_rates: df_display = df_display[df_display['方案(利率)'].isin(sel_plans_rates)]
        if isinstance(date_range, tuple) and len(date_range) == 2:
            df_display = df_display[(df_display['開始日'] >= date_range[0]) & (df_display['開始日'] <= date_range[1])]
        if filter_type != "全部": df_display = df_display[df_display['類型'] == filter_type]
        if filter_status != "全部": df_display = df_display[df_display['狀態'] == filter_status]
        
        # 💡 執行備註關鍵字過濾
        if search_note:
            df_display = df_display[df_display['備註'].str.contains(search_note, case=False, na=False, regex=False)]

        total_wan = df_display['金額'].sum()
        display_total = f"{total_wan/10000:.4f} 億" if total_wan >= 10000 else f"{total_wan:,.0f} 萬"
        st.divider()
        m1, m2 = st.columns(2)
        m1.metric("符合條件筆數", f"{len(df_display)} 筆")
        m2.metric("篩選總金額 (NT$)", display_total)

        event = st.dataframe(
            df_display.drop(columns=['agent_id', '方案(利率)', '方案名稱']), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width=60, format="%d"),
                "利率": st.column_config.NumberColumn("利率", format="%.1f%%")
            },
            on_select="rerun",
            selection_mode="single-row",
            key="overview_table_final"
        )

        auto_selected_id = "請選擇..."
        try:
            selected_rows = event.selection.get("rows", [])
            if selected_rows:
                auto_selected_id = df_display.iloc[selected_rows[0]]['ID']
        except:
            pass

        # --- 4. 🛠️ 快速維護區 ---
        st.divider()
        st.subheader("🛠️ 合約快速維護區")
        op_col1, op_col2 = st.columns(2)

        id_list = df_display['ID'].tolist()
        current_idx = id_list.index(auto_selected_id) + 1 if auto_selected_id in id_list else 0

        with op_col1:
            st.markdown("##### 📝 修正合約資料")
            edit_id = st.selectbox("1. 選擇要修正的 ID", ["請選擇..."] + id_list, index=current_idx, key=f"edit_ui_{auto_selected_id}")
            
            if edit_id != "請選擇...":
                detail_query = """
                    SELECT ic.*, rp.plan_name, rp.annual_rate, rp.period_months, 
                           a.name as agent_name, c.name as customer_name
                    FROM invest_contracts ic
                    JOIN rate_plans rp ON ic.plan_id = rp.plan_id
                    JOIN customers c ON ic.customer_id = c.customer_id
                    JOIN agents a ON c.agent_id = a.agent_id
                    WHERE ic.contract_id = ?
                """
                det_df = pd.read_sql(detail_query, conn, params=(edit_id,))
                if not det_df.empty:
                    info = det_df.iloc[0]
                    st.info(f"📍 編輯：ID {edit_id} | 👤 客戶：{info['customer_name']}")

                    c1, c2 = st.columns(2)
                    with c1:
                        new_c_name = st.text_input("修正姓名", value=info['customer_name'])
                    with c2:
                        a_names = all_agents_df['name'].tolist()
                        new_a_name = st.selectbox("變更業務", a_names, index=a_names.index(info['agent_name']))
                        new_a_id = int(all_agents_df[all_agents_df['name'] == new_a_name]['agent_id'].values[0])

                    plans_df = pd.read_sql("SELECT plan_id, plan_name, annual_rate, period_months FROM rate_plans", conn)
                    plans_df['display'] = plans_df['plan_name'] + " (" + plans_df['annual_rate'].astype(str) + "%)"
                    p_opts = plans_df['display'].tolist()
                    curr_p = f"{info['plan_name']} ({info['annual_rate']}%)"
                    new_p_label = st.selectbox("變更方案", p_opts, index=p_opts.index(curr_p) if curr_p in p_opts else 0)
                    
                    p_info = plans_df[plans_df['display'] == new_p_label].iloc[0]
                    new_p_id, new_p_m = int(p_info['plan_id']), int(p_info['period_months'])

                    new_s_dt = st.date_input("開始日", value=pd.to_datetime(info['start_date']).date())
                    new_e_dt = new_s_dt + relativedelta(months=new_p_m)
                    st.caption(f"📅 自動計算結束日：**{new_e_dt}**")

                    amt_c, type_c = st.columns(2)
                    with amt_c:
                        new_amt = st.number_input("金額", value=float(info['amount']/10000))
                    with type_c:
                        new_type = st.radio("性質", ["新約", "續約"], index=0 if info['contract_type'] == "新約" else 1, horizontal=True)
                    
                    new_n = st.text_input("備註", value=str(info['note']) if info['note'] else "")
                    
                    if st.button("💾 儲存修正", use_container_width=True, type="primary"):
                        conn.execute("UPDATE invest_contracts SET plan_id=?, amount=?, start_date=?, end_date=?, note=?, contract_type=? WHERE contract_id=?", 
                                     (new_p_id, new_amt*10000, new_s_dt.isoformat(), new_e_dt.isoformat(), new_n, new_type, edit_id))
                        conn.execute("UPDATE customers SET name=?, agent_id=? WHERE customer_id=?", 
                                     (new_c_name, new_a_id, int(info['customer_id'])))
                        conn.commit(); st.success("修正成功！"); time.sleep(1); st.rerun()

        with op_col2:
            st.markdown("##### ❌ 刪除合約紀錄")
            del_id = st.selectbox("1. 選擇要刪除的 ID", ["請選擇..."] + id_list, index=current_idx, key=f"del_ui_{auto_selected_id}")
            
            if del_id != "請選擇...":
                row = df_display[df_display['ID'] == del_id].iloc[0]
                st.error(f"⚠️ 警告：即將刪除合約 ID {del_id}")
                st.write(f"客戶：{row['客戶姓名']} | 金額：{row['金額']} 萬")
                st.write("---")
                is_confirmed = st.checkbox(f"我已確認要永久刪除此筆資料", key=f"confirm_del_{del_id}")
                
                if is_confirmed:
                    if st.button(f"🔥 確定刪除 ID:{del_id}", type="primary", use_container_width=True):
                        conn.execute("DELETE FROM invest_contracts WHERE contract_id=?", (del_id,))
                        conn.commit()
                        st.success(f"🗑️ 已移除資料"); time.sleep(1); st.rerun()
    else:
        st.info("⚠️ 目前資料庫中無任何合約。")
        
elif menu == "⚙️ 基礎資料設定":
    st.title("⚙️ 系統參數與管理")

    st.subheader("👤 業務員人事調整")
    with st.expander("🛠️ 執行業務姓名、升遷或主管調動", expanded=True):
        # 抓取所有業務員資訊
        agent_query = """
            SELECT a.agent_id, a.name as 業務姓名, r.rank_name as 目前職級, r.rank_id, 
                   b.name as 目前主管, a.boss_id
            FROM agents a
            JOIN ranks r ON a.rank_id = r.rank_id
            LEFT JOIN agents b ON a.boss_id = b.agent_id
        """
        all_agents_df = pd.read_sql(agent_query, conn)
        all_ranks_df = pd.read_sql("SELECT rank_id, rank_name FROM ranks", conn)

        if not all_agents_df.empty:
            # A. 選擇要修改的對象
            agent_list = all_agents_df.apply(lambda r: f"{r['業務姓名']} (級別: {r['目前職級']} | 主管: {r['目前主管'] if r['目前主管'] else '無'})", axis=1).tolist()
            selected_agent_str = st.selectbox("1. 選擇要調整的業務員", agent_list)
            t_idx = agent_list.index(selected_agent_str)
            t_id = int(all_agents_df.iloc[t_idx]['agent_id'])
            old_name = all_agents_df.iloc[t_idx]['業務姓名']

            st.divider()
            
            # B. 編輯各項資料
            col_name, col_rank, col_boss = st.columns(3)
            
            with col_name:
                # 新增：修改姓名欄位
                new_name = st.text_input("📝 修改業務姓名", value=old_name)
            
            with col_rank:
                curr_rank = all_agents_df.iloc[t_idx]['目前職級']
                rank_opts = all_ranks_df['rank_name'].tolist()
                new_rank = st.selectbox("🎖️ 變更新職級", rank_opts, index=rank_opts.index(curr_rank))
                new_rank_id = int(all_ranks_df[all_ranks_df['rank_name'] == new_rank]['rank_id'].values[0])
            
            with col_boss:
                potential_boss = all_agents_df[all_agents_df['agent_id'] != t_id]
                boss_opts = ["None (無主管)"] + potential_boss['業務姓名'].tolist()
                curr_boss = all_agents_df.iloc[t_idx]['目前主管']
                def_idx = boss_opts.index(curr_boss) if curr_boss in boss_opts else 0
                new_boss_name = st.selectbox("🌳 變更直屬主管", boss_opts, index=def_idx)
                new_boss_id = None if new_boss_name == "None (無主管)" else int(potential_boss[potential_boss['業務姓名'] == new_boss_name]['agent_id'].values[0])

            if st.button("💾 儲存所有變更", use_container_width=True, type="primary"):
                if not new_name.strip():
                    st.error("姓名不能為空！")
                else:
                    try:
                        cursor = conn.cursor()
                        # 執行更新：同時更新姓名、職級、主管 ID
                        cursor.execute("""
                            UPDATE agents 
                            SET name = ?, rank_id = ?, boss_id = ? 
                            WHERE agent_id = ?
                        """, (new_name.strip(), new_rank_id, new_boss_id, t_id))
                        
                        conn.commit()
                        st.success(f"✅ 更新成功！已將資料同步至系統。")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"變更失敗：{e}")
        else:
            st.info("目前尚無業務員資料。")

    st.divider()

    # --- 2. 職級分潤管理 (編輯+刪除) ---
    st.subheader("🎖️ 業務職級與分潤定義")
    rank_df = pd.read_sql("SELECT rank_id, rank_name as 職級, commission_rate as 分潤比例 FROM ranks", conn)
    
    col_r1, col_r2 = st.columns([1, 1.2])
    with col_r1:
        st.write("📌 **目前職級定義**")
        if not rank_df.empty:
            st.table(rank_df[['職級', '分潤比例']].style.format({"分潤比例": "{:.1%}"}))
        else:
            st.info("尚未建立職級。")

    with col_r2:
        st.write("📝 **修改職級名稱或比例**")
        if not rank_df.empty:
            # 排序確保筆劃順序
            rank_list = sorted(rank_df['職級'].tolist())
            target_rank = st.selectbox("選擇操作職級", rank_list, key="rank_op_sel")
            curr_r = rank_df[rank_df['職級'] == target_rank].iloc[0]
            
            # 💡 關鍵：在 key 裡面加入 target_rank，切換時會強制刷新內容
            with st.expander(f"修改 {target_rank} 的名稱或比例"):
                new_r_name = st.text_input("修正職級名稱", value=curr_r['職級'], key=f"name_{target_rank}")
                new_r_comm = st.number_input("修正分潤比例 (%)", value=float(curr_r['分潤比例']*100), step=0.1, key=f"comm_{target_rank}")
                
                if st.button("💾 儲存修改", use_container_width=True, key=f"btn_{target_rank}"):
                    conn.execute("UPDATE ranks SET rank_name = ?, commission_rate = ? WHERE rank_id = ?", 
                                 (new_r_name, new_r_comm/100.0, int(curr_r['rank_id'])))
                    conn.commit()
                    st.success("更新成功")
                    time.sleep(2)
                    st.rerun()

            if st.button(f"❌ 刪除職級：{target_rank}", type="secondary", use_container_width=True):
                check_agent = pd.read_sql(f"SELECT COUNT(*) as count FROM agents WHERE rank_id = {curr_r['rank_id']}", conn)
                if check_agent['count'][0] > 0:
                    st.error(f"無法刪除！目前仍有 {check_agent['count'][0]} 位業務員屬於此職級。")
                else:
                    conn.execute("DELETE FROM ranks WHERE rank_id = ?", (int(curr_r['rank_id']),))
                    conn.commit()
                    st.warning(f"已刪除職級：{target_rank}")
                    time.sleep(2)
                    st.rerun()

    st.divider()

    # --- 3. 利率方案管理 (編輯+刪除) ---
    st.subheader("📈 利率方案設定")
    plan_df = pd.read_sql("SELECT plan_id, plan_name as 方案, annual_rate as 年利率, period_months as 週期 FROM rate_plans", conn)
    
    col_p1, col_p2 = st.columns([1, 1.2])
    with col_p1:
        st.write("📌 **目前利率方案**")
        if not plan_df.empty:
            st.dataframe(apply_zebra_style(plan_df[['方案', '年利率', '週期']]), hide_index=True)
        else:
            st.info("尚未建立方案。")

    with col_p2:
        st.write("📝 **修改或刪除方案**")
        if not plan_df.empty:
            # 排序確保筆劃順序
            plan_list = sorted(plan_df['方案'].tolist())
            target_p = st.selectbox("選擇操作方案", plan_list, key="plan_op_selectbox")
            p_info = plan_df[plan_df['方案'] == target_p].iloc[0]
            
            # 💡 關鍵：在 key 裡面加入 target_p，切換選單時輸入框內容會跟著變
            with st.expander(f"修改 {target_p} 參數"):
                new_p_name = st.text_input("修正方案名稱", value=p_info['方案'], key=f"p_name_{target_p}")
                new_p_rate = st.number_input("修正年利率 (%)", value=float(p_info['年利率']), key=f"p_rate_{target_p}")
                new_p_period = st.number_input("修正週期 (月)", value=int(p_info['週期']), key=f"p_period_{target_p}")
                
                if st.button("💾 儲存方案修改", use_container_width=True, key=f"save_btn_{target_p}"):
                    conn.execute("UPDATE rate_plans SET plan_name = ?, annual_rate = ?, period_months = ? WHERE plan_id = ?", 
                                 (new_p_name, new_p_rate, new_p_period, int(p_info['plan_id'])))
                    conn.commit()
                    st.success("方案更新成功")
                    time.sleep(2)
                    st.rerun()

            if st.button(f"❌ 刪除方案：{target_p}", type="secondary", use_container_width=True, key=f"del_btn_{target_p}"):
                check_contract = pd.read_sql(f"SELECT COUNT(*) as count FROM invest_contracts WHERE plan_id = {p_info['plan_id']}", conn)
                if check_contract['count'][0] > 0:
                    st.error(f"無法刪除！目前仍有 {check_contract['count'][0]} 筆合約使用此方案。")
                else:
                    conn.execute("DELETE FROM rate_plans WHERE plan_id = ?", (int(p_info['plan_id']),))
                    conn.commit()
                    st.warning(f"已刪除方案：{target_p}")
                    time.sleep(2)
                    st.rerun()
    st.divider()
    # --- 危險操作區 ---
    st.subheader("⚠️ 危險操作區")
    with st.expander("💣 重設系統資料 (慎用)"):
        st.warning("此操作將永久刪除『所有』投資合約紀錄，但會保留您的客戶、業務員與方案設定。")
        
        confirm_text = st.text_input("請在下方輸入『CONFIRM』以確認刪除所有合約：")
        
        if st.button("🔥 確定清空所有合約資料", type="primary", use_container_width=True):
            if confirm_text == "CONFIRM":
                try:
                    cursor = conn.cursor()
                    
                    # 1. 刪除所有合約資料
                    cursor.execute("DELETE FROM invest_contracts")
                    
                    # 2. 智慧重設計數器：先檢查 sqlite_sequence 是否存在
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
                    if cursor.fetchone():
                        # 如果表存在，才執行歸零
                        cursor.execute("DELETE FROM sqlite_sequence WHERE name='invest_contracts'")
                    
                    conn.commit()
                    st.success("✅ 所有合約資料已清空，計數器已重置！")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 刪除失敗：{e}")
            else:
                st.error("請正確輸入『CONFIRM』字樣。")

elif menu == "👤 客戶資料管理":
    st.title("👤 客戶資料管理")

    # --- 1. 撈取基礎資料 (使用 LEFT JOIN 確保資料完整) ---
    cust_query = """
    SELECT 
        c.customer_id as ID, 
        c.name as 客戶姓名, 
        IFNULL(a.name, '⚠️ 未分配') as 業務姓名
    FROM customers c
    LEFT JOIN agents a ON c.agent_id = a.agent_id
    ORDER BY c.customer_id DESC
    """
    df_all_cust = pd.read_sql(cust_query, conn)

    if df_all_cust.empty:
        st.info("目前資料庫中尚無客戶資料。")
    else:
        # --- 2. 頂部篩選面板 (影響下方的表格顯示) ---
        st.subheader("🔍 篩選客戶名單")
        agent_opts = ["全部"] + sorted(df_all_cust['業務姓名'].unique().tolist())
        sel_agent = st.selectbox("請選擇業務員進行過濾：", agent_opts, key="filter_agent_top")

        # 執行過濾邏輯
        df_display = df_all_cust.copy()
        if sel_agent != "全部":
            df_display = df_display[df_display['業務姓名'] == sel_agent]

        # --- 3. 顯示客戶清單 (優化欄位寬度) ---
        st.write(f"📅 目前顯示：**{sel_agent}** 的客戶 (共 {len(df_display)} 筆)")
        st.dataframe(
            apply_zebra_style(df_display), 
            use_container_width=False,
            hide_index=True,
            height=600,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width=60, format="%d"),
                "客戶姓名": st.column_config.TextColumn("客戶姓名", width="large"),
                "業務姓名": st.column_config.TextColumn("所屬業務", width="large")
            }
        )

        # --- 4. 刪除客戶功能 (業務員連動版) ---
        st.divider()
        st.subheader("🗑️ 刪除客戶資料")
        st.caption("流程：先選業務員 ➔ 再選該業務下的客戶 ➔ 系統檢查後刪除")

        col_del1, col_del2 = st.columns(2)
        
        with col_del1:
            # 這裡列出所有在資料庫中有客戶的業務員
            del_agent_list = sorted(df_all_cust['業務姓名'].unique().tolist())
            sel_del_agent = st.selectbox(
                "1. 選擇該客戶的所屬業務", 
                ["請選擇業務..."] + del_agent_list,
                key="del_agent_step_1"
            )
        
        with col_del2:
            target_id = None
            target_name_only = ""
            if sel_del_agent != "請選擇業務...":
                # 只撈出該業務名下的客戶
                sub_list = df_all_cust[df_all_cust['業務姓名'] == sel_del_agent]
                
                if not sub_list.empty:
                    cust_opts = [f"{r['客戶姓名']} (ID: {r['ID']})" for _, r in sub_list.iterrows()]
                    selected_cust = st.selectbox("2. 選擇欲刪除的客戶", ["請選擇客戶..."] + cust_opts)
                    
                    if "請選擇" not in selected_cust:
                        target_id = int(selected_cust.split("(ID: ")[1].split(")")[0])
                        target_name_only = selected_cust.split(" (ID:")[0]
                else:
                    st.warning("⚠️ 該業務目前名下無客戶。")
            else:
                st.selectbox("2. 選擇欲刪除的客戶", ["請先完成第一步"], disabled=True)

        # 執行刪除
        if target_id:
            st.error(f"即將刪除：**{target_name_only}** (業務：{sel_del_agent})")
            if st.button("🔥 確認永久刪除此客戶", use_container_width=True):
                try:
                    # 安全檢查：若有合約則不給刪
                    check_cnt = pd.read_sql(
                        "SELECT COUNT(*) as n FROM invest_contracts WHERE customer_id = ?", 
                        conn, params=(target_id,)
                    ).iloc[0]['n']

                    if check_cnt > 0:
                        st.error(f"❌ 無法刪除：此客戶名下尚有 {check_cnt} 筆合約紀錄，請先移除合約。")
                    else:
                        conn.execute("DELETE FROM customers WHERE customer_id = ?", (target_id,))
                        conn.commit()
                        st.success(f"✅ 已成功移除客戶：{target_name_only}")
                        time.sleep(1.5)
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ 刪除失敗：{e}")

# --- 4. 資料總覽 ---
elif menu == "📋 資料總覽":
    st.title("👥 資料總覽與狀態追蹤")
    query = """
    SELECT ic.contract_id as ID, c.name as 客戶, ic.amount as 金額, 
        rp.plan_name as 方案, ic.start_date as 開始日, ic.end_date as 結束日
    FROM invest_contracts ic
    JOIN customers c ON ic.customer_id = c.customer_id
    JOIN rate_plans rp ON ic.plan_id = rp.plan_id
    """
    df = pd.read_sql(query, conn)

    if not df.empty:
        # --- 單位換算：將金額轉為「萬」 ---
        df['金額'] = (df['金額'] / 10000).astype(str) + " 萬"
        
        df['結束日'] = pd.to_datetime(df['結束日']).dt.date
        today = date.today()
        df['合約狀態'] = df['結束日'].apply(lambda x: "🔴 已過期" if x < today else "🟢 進行中")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("目前尚無合約資料")

# --- 新增資料 (核心功能) ---
elif menu == "➕ 新增資料":
    st.title("➕ 系統資料錄入")

    # --- 第一部分：建立投資合約 ---
    st.markdown("### 1. 建立投資合約")
    add_mode = st.radio("選擇合約錄入方式", ["單筆手動填寫", "批量 CSV 上傳"], horizontal=True)

    if add_mode == "單筆手動填寫":
        st.info("💡 預設使用選單選擇舊客戶。若要建立新客戶，請勾選『手動輸入新客戶』。")
        
        # 1. 抓取基礎資料
        agent_df = pd.read_sql("SELECT agent_id, name FROM agents ORDER BY name", conn)
        plan_df = pd.read_sql("""
            SELECT 
                plan_id, 
                plan_name || ' (' || annual_rate || '%)' as 展示名稱,
                period_months 
            FROM rate_plans
        """, conn)

        # --- ⚡️ 第一層：選擇業務 (這決定了後面的客戶名單) ---
        sel_agent_name = st.selectbox(
            "💼 承辦業務員", 
            agent_df['name'] if not agent_df.empty else ["⚠️ 請先新增業務員"],
            key="agent_select_main"
        )

        # --- ⚡️ 第二層：客戶選擇邏輯 (選單與手動輸入切換) ---
        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            # 切換開關
            is_new_cust = st.checkbox("手動輸入新客戶", value=False)
        
        with col_c2:
            if is_new_cust:
                target_cust_name = st.text_input("👤 請輸入新客戶姓名", placeholder="例如：王大明")
            else:
                # 連動顯示該業務名下的舊客戶
                if not agent_df.empty and sel_agent_name != "⚠️ 請先新增業務員":
                    t_agent_id = int(agent_df[agent_df['name'] == sel_agent_name]['agent_id'].values[0])
                    cust_df = pd.read_sql("SELECT name FROM customers WHERE agent_id = ? ORDER BY name", conn, params=(t_agent_id,))
                    target_cust_name = st.selectbox("👤 選擇現有客戶", cust_df['name'] if not cust_df.empty else ["⚠️ 該業務名下尚無客戶"])
                else:
                    target_cust_name = st.selectbox("👤 選擇現有客戶", ["請先選擇業務員"])
        
        if 'default_amt' not in st.session_state:
            st.session_state.default_amt = None

        # --- ⚡️ 第三層：合約細節表單 ---
        with st.form("single_contract_combined", clear_on_submit=True):
            col_amt, col_plan = st.columns(2)
            with col_amt:
                amt_wan = st.number_input(
                    "💰 投資金額", 
                    min_value=0.0, 
                    value=st.session_state.default_amt, 
                    step=10.0,
                    placeholder="請輸入金額...",
                    key="amt_wan_input"
                )
            with col_plan:
                sel_plan_display = st.selectbox("📈 選擇方案 (利率)", plan_df['展示名稱'] if not plan_df.empty else ["⚠️ 請先設定方案"])

            col_date, col_type = st.columns(2)
            with col_date:
                start_dt = st.date_input("📅 生效日期", date.today())
            with col_type:
                contract_type_val = st.radio("📄 合約性質", ["新約", "續約"], index=1, horizontal=True)
            
            note_val = st.text_input("🗒️ 合約備註 (選填)")
            
            submit_btn = st.form_submit_button("🚀 確認送出合約", use_container_width=True, type="primary")

            if submit_btn:
                # 基礎驗證
                if not sel_agent_name or sel_agent_name == "⚠️ 請先新增業務員":
                    st.error("❌ 請先選擇業務員。")
                elif not target_cust_name or "⚠️" in target_cust_name or target_cust_name == "請先選擇業務員":
                    st.error("❌ 請選擇或輸入正確的客戶姓名。")
                elif amt_wan is None or amt_wan <= 0:
                    st.error("❌ 請輸入有效的投資金額！")
                else:
                    try:
                        cursor = conn.cursor()
                        final_agent_id = int(agent_df[agent_df['name'] == sel_agent_name]['agent_id'].values[0])
                        cust_name_clean = target_cust_name.strip()

                        # 🔍 檢查並處理客戶 (不論手動還是選單，都過一次檢查最保險)
                        cursor.execute("SELECT customer_id FROM customers WHERE name = ? AND agent_id = ?", 
                                     (cust_name_clean, final_agent_id))
                        res = cursor.fetchone()
                        
                        if res:
                            final_cust_id = res[0]
                        else:
                            # 如果沒找到，自動建立 (這解決了手動輸入的問題)
                            cursor.execute("INSERT INTO customers (name, agent_id) VALUES (?, ?)", 
                                         (cust_name_clean, final_agent_id))
                            final_cust_id = cursor.lastrowid

                        # 解析方案與日期
                        p_row = plan_df[plan_df['展示名稱'] == sel_plan_display]
                        p_id = int(p_row['plan_id'].values[0])
                        months = int(p_row['period_months'].values[0])
                        real_amount = amt_wan * 10000
                        end_dt = start_dt + relativedelta(months=months)
                        
                        # 寫入合約
                        cursor.execute("""
                            INSERT INTO invest_contracts (
                                customer_id, plan_id, amount, start_date, end_date, 
                                status, note, contract_type, is_renewed
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """, (
                            final_cust_id, p_id, real_amount, start_dt.isoformat(), 
                            end_dt.isoformat(), "Active", note_val, contract_type_val
                        ))
                        
                        conn.commit()
                        st.session_state.default_amt = None
                        st.balloons()
                        st.success(f"🎉 成功！已為【{cust_name_clean}】建立合約。")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 系統錯誤：{e}")
    else:
        st.write("### 🚀 批量匯入投資合約")
        
        # --- 1. 下載範本 ---
        st.markdown("#### 📥 第一步：下載範本")
        today = date.today()
        roc_year = today.year - 1911
        
        template_df = pd.DataFrame({
            "客戶姓名": ["王小明", "李大華"],
            "歸屬業務姓名": ["張經理", "李襄理"],
            "年利率(%)": [6.0, 8.5],
            "週期(月)": [12, 24],
            "金額": [100.0, 50.0],
            "生效年": [roc_year, roc_year],
            "生效月": [today.month, today.month],
            "生效日": [today.day, today.day],
            "合約性質": ["續約", "新約"],
            "備註": ["續約件", "新件"]
        })
        
        csv_data = template_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載批量匯入範本 (CSV)", csv_data, "合約匯入範本_v1.5.csv", "text/csv")

        st.divider()

        # --- 2. 上傳與預檢 ---
        uploaded_file = st.file_uploader("選擇填寫好的 CSV 檔案", type="csv")
        
        # ⚡️ 初始化 session_state 用來存儲錯誤
        if 'batch_errors' not in st.session_state:
            st.session_state.batch_errors = []

        if uploaded_file:
            # 💡 當有新檔案上傳時，自動清空之前的錯誤紀錄
            if "last_file_name" not in st.session_state or st.session_state.last_file_name != uploaded_file.name:
                st.session_state.batch_errors = []
                st.session_state.last_file_name = uploaded_file.name

            df_upload = None
            for enc in ['utf-8-sig', 'utf-8', 'cp950']:
                try:
                    uploaded_file.seek(0)
                    df_upload = pd.read_csv(uploaded_file, encoding=enc)
                    break
                except: continue
            
            if df_upload is not None:
                df_upload['歸屬業務姓名'] = df_upload['歸屬業務姓名'].astype(str).str.strip()
                df_upload['客戶姓名'] = df_upload['客戶姓名'].astype(str).str.strip()

                # A. 業務員預檢
                db_agents_df = pd.read_sql("SELECT agent_id, name FROM agents", conn)
                db_agents_dict = dict(zip(db_agents_df['name'], db_agents_df['agent_id']))
                csv_agents = set(df_upload['歸屬業務姓名'].unique())
                missing_agents = [a for a in csv_agents if a not in db_agents_dict]
                
                if missing_agents:
                    st.error(f"⚠️ 找不到業務員：{', '.join(missing_agents)}")
                    st.stop() 
                
                st.success("✅ 業務員預檢通過！")
                st.dataframe(df_upload, use_container_width=True, hide_index=True)
                
                # --- 執行按鈕 ---
                if st.button("🔥 確定執行智慧匯入", type="primary", use_container_width=True):
                    current_errors = [] 
                    cursor = conn.cursor()
                    success_count = 0
                    
                    for index, row in df_upload.iterrows():
                        row_idx = index + 2 
                        cust_name = str(row['客戶姓名']).strip()
                        agent_name = str(row['歸屬業務姓名']).strip()
                        
                        # 1. 取得業務 ID (已預檢必存在)
                        target_agent_id = db_agents_dict[agent_name]

                        # 2. 處理合約性質
                        c_type = str(row.get('合約性質', '續約')).strip()
                        if not c_type or c_type == 'nan': c_type = "續約"
                        if c_type not in ["新約", "續約"]: c_type = "續約"

                        # 3. 方案自動對照
                        try:
                            target_rate = float(row['年利率(%)'])
                            target_period = int(row['週期(月)'])
                            plan_res = pd.read_sql("SELECT plan_id FROM rate_plans WHERE annual_rate = ? AND period_months = ?", conn, params=(target_rate, target_period))
                            if plan_res.empty:
                                current_errors.append(f"❌ 行號 {row_idx}：找不到利率 {target_rate}% / 週期 {target_period}月 的方案")
                                continue
                            p_id = int(plan_res['plan_id'][0])
                        except Exception:
                            current_errors.append(f"❌ 行號 {row_idx}：利率或週期格式錯誤")
                            continue

                        # 4. 日期與金額檢查
                        try:
                            y, m, d = int(row['生效年'])+1911, int(row['生效月']), int(row['生效日'])
                            s_dt = date(y, m, d)
                            e_dt = s_dt + relativedelta(months=target_period)
                            real_amt = float(row['金額']) * 10000
                        except Exception:
                            current_errors.append(f"❌ 行號 {row_idx}：日期日期或金額格式錯誤")
                            continue

                        # 5. ⚡️ 客戶處理 (防撞名邏輯：姓名 + 業務ID)
                        # 檢查該業務名下是否已有同名客戶
                        check_cust = pd.read_sql(
                            "SELECT customer_id FROM customers WHERE name = ? AND agent_id = ?", 
                            conn, params=(cust_name, target_agent_id)
                        )
                        
                        if check_cust.empty:
                            # 建立該業務員名下的新客戶
                            cursor.execute("INSERT INTO customers (name, agent_id) VALUES (?, ?)", (cust_name, target_agent_id))
                            conn.commit()
                            cust_id = cursor.lastrowid
                        else:
                            cust_id = int(check_cust['customer_id'][0])

                        # 6. 寫入合約
                        cursor.execute("""
                            INSERT INTO invest_contracts (customer_id, plan_id, amount, start_date, end_date, status, note, contract_type, is_renewed)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """, (cust_id, p_id, real_amt, s_dt.isoformat(), e_dt.isoformat(), "Active", str(row.get('備註', '')), c_type))
                        success_count += 1
                    
                    conn.commit()
                    
                    # 💡 將錯誤存入 session_state 供 Rerun 後顯示
                    st.session_state.batch_errors = current_errors
                    
                    if not current_errors:
                        st.balloons()
                        st.success(f"🎉 批量匯入成功！共完成 {success_count} 筆。")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning(f"⚠️ 匯入完成，但發現 {len(current_errors)} 處錯誤 (已跳過該行)。")

        # --- 3. 顯示錯誤清單 ---
        if st.session_state.batch_errors:
            st.divider()
            st.error("🚨 匯入異常報告 (請修正 CSV 後重新上傳)：")
            # 使用 container 讓錯誤訊息排版整齊
            with st.container():
                for err in st.session_state.batch_errors:
                    st.write(err)
            if st.button("🗑️ 清除錯誤訊息"):
                st.session_state.batch_errors = []
                st.rerun()

    st.divider()

    # --- 第二部分：建立基礎對象 ---
    st.markdown("### 2. 建立基礎對象")
    tab_customer, tab_agent ,  tab_plan, tab_rank= st.tabs([
        "👤 新增客戶", "💼 新增業務員", "📈 新增利率方案", "🎖️ 新增職級"
    ])

    # 1. 新增職級
    with tab_rank:
        with st.form("form_rank"):
            st.write("#### 定義職級與佣金比")
            r_name = st.text_input("職級名稱 (如：經理、襄理)")
            r_comm = st.number_input("佣金比例 (%，例如 1% 則填 1.0)", min_value=0.0, max_value=100.0, step=0.1)
            if st.form_submit_button("確認建立職級"):
                if r_name:
                    conn.execute("INSERT INTO ranks (rank_name, commission_rate) VALUES (?, ?)", (r_name, r_comm/100))
                    conn.commit()
                    st.success(f"✅ 職級 {r_name} 已成功建立！")
                    st.rerun()
                else:
                    st.error("請輸入職級名稱")

    # 2. 新增業務員
    with tab_agent:
        with st.form("form_agent"):
            st.write("#### 新增業務員")
            a_name = st.text_input("業務姓名")
            rank_query = pd.read_sql("SELECT rank_id, rank_name FROM ranks", conn)
            sel_rank = st.selectbox("分配職級", rank_query['rank_name'] if not rank_query.empty else ["請先新增職級"])
            
            all_agents = pd.read_sql("SELECT agent_id, name FROM agents", conn)
            sel_boss = st.selectbox("直屬主管", ["None (最高主管)"] + all_agents['name'].tolist())
            
            if st.form_submit_button("確認建立業務"):
                if not rank_query.empty and a_name:
                    r_id = int(rank_query[rank_query['rank_name'] == sel_rank]['rank_id'].values[0])
                    b_id = None
                    if sel_boss != "None (最高主管)":
                        b_id = int(all_agents[all_agents['name'] == sel_boss]['agent_id'].values[0])
                    
                    conn.execute("INSERT INTO agents (name, rank_id, boss_id) VALUES (?, ?, ?)", (a_name, r_id, b_id))
                    conn.commit()
                    st.success(f"✅ 業務員 {a_name} 已成功建立！")
                    st.rerun()
                else:
                    st.error("請填寫姓名並確保已有職級資料")

    # 3. 新增客戶
    with tab_customer:
        with st.form("form_customer"):
            st.write("#### 新增客戶")
            c_name = st.text_input("客戶姓名")
            agent_query = pd.read_sql("SELECT agent_id, name FROM agents", conn)
            sel_agent = st.selectbox("歸屬業務", agent_query['name'] if not agent_query.empty else ["請先新增業務員"])
            bank = st.text_input("銀行資訊")
            c_note = st.text_area("備註") 
            
            if st.form_submit_button("確認建立客戶"):
                if not agent_query.empty and c_name:
                    ag_id = int(agent_query[agent_query['name'] == sel_agent]['agent_id'].values[0])
                    conn.execute(
                        "INSERT INTO customers (name, agent_id, bank_info, note) VALUES (?, ?, ?, ?)", 
                        (c_name, ag_id, bank, c_note)
                    )
                    conn.commit()
                    st.success(f"✅ 客戶 {c_name} 已成功建立！")
                    st.rerun()

    # 4. 新增利率方案
    with tab_plan:
        with st.form("form_rate_plan"):
            st.write("#### 設定投資方案參數")
            p_name = st.text_input("方案名稱 (如：半年期穩健方案、一年期高利方案)")
            p_rate = st.number_input("年利率 (%)", min_value=0.0, max_value=100.0, value=6.0, step=0.1)
            p_period = st.number_input("合約週期 (月)", min_value=1, max_value=120, value=12)
            
            if st.form_submit_button("確認建立方案"):
                if p_name:
                    try:
                        conn.execute(
                            "INSERT INTO rate_plans (plan_name, annual_rate, period_months) VALUES (?, ?, ?)", 
                            (p_name, p_rate, p_period)
                        )
                        conn.commit()
                        st.success(f"✅ 方案 {p_name} 已成功建立！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"建立失敗：{e}")
                else:
                    st.error("請輸入方案名稱")

elif menu == "📅 到期續約管理":
    st.title("📅 到期續約管理")
    
    # --- 0. 初始化狀態與記憶金鑰 ---
    if 'renew_sync_key' not in st.session_state:
        st.session_state.renew_sync_key = 0
    if 'renew_checked_ids' not in st.session_state:
        st.session_state.renew_checked_ids = set()

    # --- 1. 時間區間選擇器 ---
    with st.expander("📅 篩選合約到期日期區間", expanded=True):
        col_date1, col_date2 = st.columns([2, 1])
        with col_date1:
            today = date.today()
            default_end = (today + relativedelta(months=1)).replace(day=1) - relativedelta(days=1)
            renew_range = st.date_input("選擇到期日區間", value=(today, default_end))
    
    if isinstance(renew_range, tuple) and len(renew_range) == 2:
        r_start, r_end = renew_range

        # --- 2. 核心 SQL 查詢 ---
        query = """
        SELECT ic.contract_id, c.name as 客戶姓名, a.name as 業務姓名,
               ic.amount / 10000.0 as '金額', rp.plan_name, rp.annual_rate,
               ic.end_date as 原結束日, ic.is_renewed
        FROM invest_contracts ic
        JOIN customers c ON ic.customer_id = c.customer_id
        JOIN agents a ON c.agent_id = a.agent_id
        JOIN rate_plans rp ON ic.plan_id = rp.plan_id
        WHERE ic.end_date >= ? AND ic.end_date <= ?
        ORDER BY CAST(a.sort_order AS INTEGER) ASC, ic.end_date ASC
        """

        all_df = pd.read_sql(query, conn, params=(r_start.isoformat(), r_end.isoformat()))

        if not all_df.empty:
            all_df['方案(利率)'] = all_df['plan_name'] + " (" + all_df['annual_rate'].astype(str) + "%)"
            # all_df = all_df.sort_values(by=['業務姓名', '客戶姓名']).reset_index(drop=True)
            
            # --- 3. 進階篩選面板 ---
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                sel_agents = st.multiselect("💼 篩選業務員", sorted(all_df['業務姓名'].unique().tolist()))
                sel_plans = st.multiselect("📈 篩選方案", sorted(all_df['方案(利率)'].unique().tolist()))
            with f_col2:
                cust_pool = all_df[all_df['業務姓名'].isin(sel_agents)] if sel_agents else all_df
                sel_custs = st.multiselect("🔍 篩選客戶", sorted(cust_pool['客戶姓名'].unique().tolist()))

            # 執行篩選
            df_filtered = all_df.copy()
            if sel_agents: df_filtered = df_filtered[df_filtered['業務姓名'].isin(sel_agents)]
            if sel_custs: df_filtered = df_filtered[df_filtered['客戶姓名'].isin(sel_custs)]
            if sel_plans: df_filtered = df_filtered[df_filtered['方案(利率)'].isin(sel_plans)]

            # 區分待處理與已完成
            pending_df = df_filtered[df_filtered['is_renewed'].fillna(0).astype(int) == 0].copy()
            done_df = df_filtered[df_filtered['is_renewed'] == 1].copy()

            # --- 🚀 4. 頂部數字看板 ---
            st.divider()
            m_col1, m_col2, m_col3 = st.columns(3)
            
            # 計算目前畫面上看得到且已勾選的 ID
            current_viewing_ids = set(pending_df['contract_id'].tolist())
            viewing_selected_count = len(current_viewing_ids.intersection(st.session_state.renew_checked_ids))
            total_checked = len(st.session_state.renew_checked_ids)

            with m_col1:
                st.metric("📋 篩選後待處理件數", f"{len(pending_df)} 筆")
            with m_col2:
                st.metric("💰 篩選後總金額", f"{pending_df['金額'].sum():,.2f}")
            with m_col3:
                # st.metric("✅ 勾選狀態", f"目前畫面 {viewing_selected_count} / 總勾選 {total_checked}")
                st.metric("✅ 勾選狀態", f"總勾選 {total_checked}")

            # --- 5. 待處理續約編輯器 ---
            if not pending_df.empty:
                def get_wed(d_str):
                    d = pd.to_datetime(d_str).date()
                    days_until_wed = (2 - d.weekday() + 7) % 7
                    return d + relativedelta(days=days_until_wed)
                pending_df['下週三生效'] = pending_df['原結束日'].apply(get_wed)
                
                # ✅ 智慧全選功能
                is_all_selected = current_viewing_ids.issubset(st.session_state.renew_checked_ids) if current_viewing_ids else False
                
                def on_all_check_change():
                    if st.session_state.all_sel_trigger:
                        st.session_state.renew_checked_ids.update(current_viewing_ids)
                    else:
                        st.session_state.renew_checked_ids.difference_update(current_viewing_ids)

                st.checkbox("全選目前篩選結果", value=is_all_selected, key="all_sel_trigger", on_change=on_all_check_change)

                # 從背景 Set 恢復勾選狀態
                pending_df['確認續約'] = pending_df['contract_id'].apply(lambda x: x in st.session_state.renew_checked_ids)

                # ✅ 核心同步函式 (解決手動取消沒反應的問題)
                def sync_editor_to_state():
                    ed_key = f"renew_ed_{st.session_state.renew_sync_key}"
                    if ed_key in st.session_state:
                        edited_rows = st.session_state[ed_key]["edited_rows"]
                        for row_idx, changes in edited_rows.items():
                            cid = int(pending_df.iloc[int(row_idx)]['contract_id'])
                            if "確認續約" in changes:
                                if changes["確認續約"]: st.session_state.renew_checked_ids.add(cid)
                                else: st.session_state.renew_checked_ids.discard(cid)

                st.data_editor(
                    # 這裡絕對維持原始 df，不套用樣式
                    pending_df[['確認續約', '客戶姓名', '業務姓名', '金額', '方案(利率)', '原結束日', '下週三生效']], 
                    hide_index=True, 
                    use_container_width=True, 
                    key=f"renew_ed_{st.session_state.renew_sync_key}",
                    on_change=sync_editor_to_state,
                    height=500,
                    # 💡 透過配置讓欄位「看起來」有被設計過
                    column_config={
                        "確認續約": st.column_config.CheckboxColumn("確認續約", help="點擊方框執行續約"),
                        "金額": st.column_config.NumberColumn("金額 (萬)", format="%.2f"),
                        "下週三生效": st.column_config.DateColumn("預計生效日期")
                    }
                )

                # 執行按鈕區
                col_btn1, col_btn2 = st.columns([4, 1])
                with col_btn1:
                    if st.button("🚀 執行批次續約 (針對所有勾選項目)", type="primary", use_container_width=True):
                        if st.session_state.renew_checked_ids:
                            try:
                                cursor = conn.cursor()
                                for oid in list(st.session_state.renew_checked_ids):
                                    cursor.execute("SELECT customer_id, plan_id, amount, end_date FROM invest_contracts WHERE contract_id = ?", (oid,))
                                    c_id, p_id, amt, old_end = cursor.fetchone()
                                    cursor.execute("SELECT period_months FROM rate_plans WHERE plan_id = ?", (p_id,))
                                    p_months = cursor.fetchone()[0]
                                    ns = get_wed(old_end)
                                    ne = ns + relativedelta(months=p_months)
                                    
                                    cursor.execute("""
                                        INSERT INTO invest_contracts (customer_id, plan_id, amount, start_date, end_date, status, is_renewed, note, contract_type)
                                        VALUES (?, ?, ?, ?, ?, 'Active', 0, ?, '續約')
                                    """, (c_id, p_id, amt, ns.isoformat(), ne.isoformat(), f"由 ID:{oid} 續約轉入"))
                                    cursor.execute("UPDATE invest_contracts SET is_renewed = 1, status = 'Closed' WHERE contract_id = ?", (oid,))
                                
                                conn.commit()
                                st.session_state.renew_checked_ids.clear()
                                st.session_state.renew_sync_key += 1
                                st.success("✅ 已完成批次續約！")
                                time.sleep(1); st.rerun()
                            except Exception as e:
                                conn.rollback(); st.error(f"❌ 續約失敗：{e}")
                with col_btn2:
                    if st.button("🗑️ 清空勾選"):
                        st.session_state.renew_checked_ids.clear(); st.rerun()
            else:
                st.success("🎉 選定條件下，無待處理合約。")

            st.divider()

            # --- 🚀 6. 已處理完成清單 (補回此處) ---
            st.subheader(f"✅ 已處理完成清單 ({len(done_df)} 筆)")
            if not done_df.empty:
                done_df = done_df.sort_values(by='原結束日', ascending=False)
                st.dataframe(apply_zebra_style(done_df[['客戶姓名', '業務姓名', '金額', '方案(利率)', '原結束日']]), use_container_width=True, hide_index=True)
            else:
                st.info("💡 目前區間內尚無已處理完成的續約。")

        else:
            st.info(f"📅 在 {r_start} 到 {r_end} 之間沒有到期合約。")

elif menu == "💰 業務佣":
    st.title("💰 C")

    # --- 0. 預載組織快取 ---
    agent_query = """
    SELECT a.agent_id, a.name, a.boss_id, r.commission_rate as rate, r.rank_name as rank,
            a.sort_order
    FROM agents a JOIN ranks r ON a.rank_id = r.rank_id
    """
    agent_map = pd.read_sql(agent_query, conn).set_index('agent_id').to_dict('index')

    if 'comm_date_range' not in st.session_state:
        st.session_state.comm_date_range = (date.today().replace(day=1), date.today())
    if 'extra_rules' not in st.session_state:
        st.session_state.extra_rules = []

    # --- 1. 動態獎勵規則管理區 ---
    with st.expander("🎁 額外活動獎勵管理", expanded=False):
        all_plans_info = pd.read_sql("SELECT plan_name, annual_rate, period_months FROM rate_plans", conn)
        all_plans_info['display'] = all_plans_info['plan_name'] + " (" + all_plans_info['annual_rate'].astype(str) + "%)"
        
        r_col1, r_col2, r_col3 = st.columns([2, 1, 1])
        with r_col1:
            sel_rule_plan = st.selectbox("選擇利率方案", all_plans_info['display'].tolist())
        with r_col2:
            sel_rule_time = st.number_input("第幾次領取時獎勵", min_value=0, value=0, step=1)
        with r_col3:
            sel_rule_bonus = st.number_input("加給 % 數", min_value=0.0, value=2.0, format="%.2f")
            
        if st.button("➕ 新增獎勵規則", use_container_width=True):
            st.session_state.extra_rules.append({
                "id": time.time(), "plan": sel_rule_plan, 
                "time": sel_rule_time, "bonus_rate": sel_rule_bonus / 100
            })
            st.rerun()
        
        if st.session_state.extra_rules:
            st.divider()
            for idx, rule in enumerate(st.session_state.extra_rules):
                rc1, rc2 = st.columns([4, 1])
                with rc1: st.write(f"📍 {rule['plan']} - 第 {rule['time']} 次：+{rule['bonus_rate']*100:.2f}%")
                with rc2:
                    if st.button("❌", key=f"del_{rule['id']}"):
                        st.session_state.extra_rules.pop(idx); st.rerun()

    # --- 2. 選擇日期範圍 ---
    date_range = st.date_input("請選擇對帳日期區間", key="comm_date_range")
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_f, end_f = date_range
        query = """
        SELECT ic.contract_id, c.name as 客戶姓名, a.name as 業務姓名, a.agent_id, a.boss_id, 
               r.rank_name as 職級, r.commission_rate as 個人比例, ic.amount / 10000.0 as '金額', 
               rp.plan_name, rp.annual_rate as '利率', ic.start_date as 生效日, 
               rp.period_months as 總期數, ic.contract_type,
               a.sort_order as 業務權重
        FROM invest_contracts ic 
        JOIN customers c ON ic.customer_id = c.customer_id 
        JOIN agents a ON c.agent_id = a.agent_id 
        JOIN ranks r ON a.rank_id = r.rank_id 
        JOIN rate_plans rp ON ic.plan_id = rp.plan_id 
        WHERE ic.start_date <= ?
        ORDER BY a.sort_order ASC
        """
        df_raw = pd.read_sql(query, conn, params=(end_f.isoformat(),))

        if not df_raw.empty:
            df_raw['方案名稱(%)'] = df_raw['plan_name'] + " (" + df_raw['利率'].astype(str) + "%)"
            payouts = {aid: {'個人':0.0, '加給':0.0, '獎勵':0.0, '業績':{}} for aid in agent_map}
            volume_box = {aid: {'級差池': {}, '子代池': {}, '孫代池': {}} for aid in agent_map}
            summary_payout_details = []
            contract_flow_logs = [] 

            for _, row in df_raw.iterrows():
                amt, aid, plan = row['金額'], row['agent_id'], row['方案名稱(%)']
                
                # ✅ 判定性質 (新/續)
                raw_type = row['contract_type'] if pd.notna(row['contract_type']) else "續約"
                suffix = "新" if "新" in raw_type else "續"
                detailed_plan_key = f"{plan}-{suffix}"
                
                start_dt = pd.to_datetime(row['生效日']).date()
                diff_months = (end_f.year - start_dt.year) * 12 + (end_f.month - start_dt.month)
                is_in_date_range = (start_f <= start_dt <= end_f)
                
                target_aid = aid
                if row['職級'] in ['高專', '累件中', '外圍'] and pd.notna(row['boss_id']):
                    target_aid = row['boss_id']
                
                # 過期或未開始則跳過
                if diff_months < 0 or diff_months >= row['總期數']: continue

                # this_log = {"客戶": row['客戶姓名'], "業務": row['業務姓名'], "金額": amt, "生效日": row['生效日'], "分配明細": []}
                this_log = {"客戶": row['客戶姓名'], "業務": agent_map[target_aid]['name'], "金額": amt, "生效日": row['生效日'], "分配明細": []}

                # ✅ (A) 獎勵計算
                for rule in st.session_state.extra_rules:
                    if plan == rule['plan'] and diff_months == rule['time'] and is_in_date_range:
                        rew_amt = round(amt * rule['bonus_rate'], 2)
                        # payouts[aid]['獎勵'] += rew_amt
                        # payouts[target_aid]['獎勵'] += rew_amt
                        # this_log["分配明細"].append(f"🎁獎勵({row['業務姓名']}):+{rew_amt}")
                        payouts[target_aid]['獎勵'] += rew_amt 
                        this_log["分配明細"].append(f"🎁獎勵({agent_map[target_aid]['name']}):+{rew_amt}")

                # ✅ (B) 核心分潤與業績歸帳 (僅計算選定區間內的新業績)
                if is_in_date_range:
                    # target_aid = aid
                    base_agent = agent_map.get(target_aid)
                    if not base_agent: continue
                    
                    # 業績歸帳到對應的 [方案-新/續]
                    payouts[target_aid]['業績'][detailed_plan_key] = payouts[target_aid]['業績'].get(detailed_plan_key, 0) + amt
                    
                    base_rate = base_agent['rate']
                    self_comm = round(amt * base_rate, 2)
                    payouts[target_aid]['個人'] += self_comm
                    this_log["分配明細"].append(f"個人({base_agent['name']}):+{self_comm}")

                    # 🚀 爬升引擎 (級差與平階)
                    last_rate = base_rate
                    child_group_id = target_aid 
                    curr_id = base_agent['boss_id']
                    peer_count = 0

                    while curr_id in agent_map:
                        boss = agent_map[curr_id]
                        if boss['rate'] > last_rate:
                            volume_box[curr_id]['級差池'][child_group_id] = volume_box[curr_id]['級差池'].get(child_group_id, 0) + amt
                            s_rate = round(boss['rate'] - last_rate, 4)
                            this_log["分配明細"].append(f"級差({boss['name']}):+{round(amt*s_rate, 2)}")
                            child_group_id = curr_id 
                            last_rate = boss['rate']
                        elif boss['rate'] == last_rate and boss['rank'] != '主任':
                            peer_count += 1
                            if peer_count == 1:
                                volume_box[curr_id]['子代池'][target_aid] = volume_box[curr_id]['子代池'].get(target_aid, 0) + amt
                                this_log["分配明細"].append(f"子代({boss['name']}):+0.2%")
                            elif peer_count == 2:
                                volume_box[curr_id]['孫代池'][target_aid] = volume_box[curr_id]['孫代池'].get(target_aid, 0) + amt
                                this_log["分配明細"].append(f"孫代({boss['name']}):+0.1%")
                        curr_id = boss['boss_id']
                
                if this_log["分配明細"]:
                    this_log["分配明細"] = " | ".join(this_log["分配明細"])
                    contract_flow_logs.append(this_log)

            # --- 第二階段：結算加給 ---
            for m_id, v_data in volume_box.items():
                m_info = agent_map[m_id]
                for sub_id, total_amt in v_data['級差池'].items():
                    s_rate = round(m_info['rate'] - agent_map[sub_id]['rate'], 4)
                    if s_rate > 0:
                        gain = round(total_amt * s_rate, 2)
                        payouts[m_id]['加給'] += gain
                        summary_payout_details.append({'受款人': m_info['name'], '項目': f"【{agent_map[sub_id]['name']}組】級差", '總業績': total_amt, '計算式': f"{s_rate*100:.1f}%", '金額': gain, '支出人': '-'})
                
                for gen_name, pool_key, g_rate in [('子代', '子代池', 0.002), ('孫代', '孫代池', 0.001)]:
                    for sub_id, group_amt in v_data[pool_key].items():
                        if group_amt > 0:
                            g_gain = round(group_amt * g_rate, 2)
                            payer_id, t_id = None, m_info['boss_id']
                            while t_id in agent_map:
                                if agent_map[t_id]['rate'] > m_info['rate']:
                                    payer_id = t_id; break
                                t_id = agent_map[t_id]['boss_id']
                            if payer_id:
                                payouts[m_id]['加給'] += g_gain
                                payouts[payer_id]['加給'] -= g_gain
                                summary_payout_details.append({'受款人': m_info['name'], '項目': f"{gen_name}補償({agent_map[sub_id]['name']}單)", '總業績': round(group_amt, 2), '計算式': f"{g_rate*100:.2f}%", '金額': g_gain, '支出人': agent_map[payer_id]['name']})

            # --- 3. 欄位排序與生成 (利率由小到大) ---
            raw_keys = set([k for d in payouts.values() for k in d['業績'].keys()])
            base_plans = set([k.rsplit('-', 1)[0] for k in raw_keys])
            
            def get_rate_val(p_str):
                import re
                match = re.search(r"\((.*?)%\)", p_str)
                return float(match.group(1)) if match else 0.0

            sorted_base_plans = sorted(list(base_plans), key=get_rate_val)
            all_detailed_cols = []
            for bp in sorted_base_plans:
                all_detailed_cols.append(f"{bp}-新")
                all_detailed_cols.append(f"{bp}-續")

            # --- 4. 生成 Matrix C 表格數據 ---
            summary_data = []

            sorted_aids = sorted(
                payouts.keys(), 
                key=lambda x: agent_map.get(x, {}).get('sort_order', 999)
            )

            # for aid, data in payouts.items():
            for aid in sorted_aids:
                data = payouts[aid]
                if any(v > 0 for v in data['業績'].values()) or data['加給'] != 0 or data['獎勵'] != 0:
                    r_data = {'姓名': agent_map[aid]['name']}
                    r_data['_sort'] = agent_map[aid].get('sort_order', 999)
                    for p_col in all_detailed_cols:
                        r_data[p_col] = data['業績'].get(p_col, 0)

                    r_data['總業績'] = sum(data['業績'].values())
                    r_data['個人Ｃ'] = data['個人']
                    r_data['差%加給'] = data['加給']
                    r_data['活動獎勵'] = data['獎勵']
                    r_data['應領總計'] = data['個人'] + data['加給'] + data['獎勵']
                    summary_data.append(r_data)
            
            # --- 5. 呈現表格 ---
            if summary_data:
                df_final = pd.DataFrame(summary_data).fillna(0)
                total_row = {'姓名': '⭐ 合計 (Total)'}
                for col in df_final.columns:
                    if col != '姓名': total_row[col] = df_final[col].sum()
                
                df_with_total = pd.concat([pd.DataFrame([total_row]), df_final], ignore_index=True)
                display_cols = ['姓名'] + all_detailed_cols + ['總業績', '個人Ｃ', '差%加給', '活動獎勵', '應領總計']
                df_with_total = df_with_total[display_cols]

                st.write("### 🧩 Matrix C")
                st.dataframe(apply_zebra_style(df_with_total), use_container_width=True, hide_index=True)
                
                st.divider()
                st.write("### 🔍 明細")
                if summary_payout_details:
                    # st.dataframe(apply_zebra_style(pd.DataFrame(summary_payout_details)), use_container_width=True, hide_index=True)
                    det_df = pd.DataFrame(summary_payout_details)
                    if not det_df.empty:
                        # 1. 建立對照表，增加 .get() 的預設值 999 避免 NaN
                        name_to_order = {v['name']: v.get('sort_order', 999) for v in agent_map.values()}
                        
                        # 2. 映射排序權重，使用 .fillna(999) 防止有人的姓名不在 agent_map 中導致報錯
                        det_df['_sort'] = det_df['受款人'].map(name_to_order).fillna(999)
                        
                        # 3. 排序並過濾輔助欄位
                        # 建議也把 '受款人' 放在前面排序，這樣同一人的明細會聚在一起
                        det_df = det_df.sort_values(by=['_sort', '受款人']).drop(columns=['_sort'])
                        
                        st.dataframe(
                            apply_zebra_style(det_df), 
                            use_container_width=True, 
                            hide_index=True
                        )
                
                st.write("### 📄 明細紀錄")
                if contract_flow_logs:
                    st.dataframe(apply_zebra_style(pd.DataFrame(contract_flow_logs)), use_container_width=True, hide_index=True)
            else:
                st.warning("🌙 此區間無數據。")

elif menu == "🌳 團隊組織圖":
    st.title("🌳 團隊組織架構圖")
    
    # 1. 執行 SQL 抓取關係
    query = """
        SELECT a.name as employee, b.name as boss, r.rank_name as rank
        FROM agents a
        LEFT JOIN agents b ON a.boss_id = b.agent_id
        JOIN ranks r ON a.rank_id = r.rank_id
    """
    hierarchy_df = pd.read_sql(query, conn)

    if not hierarchy_df.empty:
        # 🎨 職級配色定義
        rank_colors = {
            "協理": "#0000FF", "經理": "#FF0000", "資副": "#FF8C00", 
            "副理": "#9400D3", "主任": "#008000", "高專": "#FFFF00", 
            "累件中": "#00FFFF", "外圍": "#FF00FF"
        }

        # 5. 職級對照表
        st.write("---")
        st.markdown("##### 🎨 職級配色參考")
        cols = st.columns(len(rank_colors))
        for i, (name, color) in enumerate(rank_colors.items()):
            t_color = "black" if name in ["高專", "累件中", "外圍"] else "white"
            cols[i].markdown(f'<div style="background-color:{color}; padding:10px; border-radius:8px; text-align:center; color:{t_color}; font-size:14px; font-weight:bold;">{name}</div>', unsafe_allow_html=True)

        st.write("")
        st.write("")
        st.write("")
        st.write("")
        st.write("")
        st.write("")

        # 2. 構建樹狀結構
        nodes = {row['employee']: {'rank': row['rank'], 'children': []} for _, row in hierarchy_df.iterrows()}
        roots = []
        for _, row in hierarchy_df.iterrows():
            if row['boss'] and row['boss'] in nodes:
                nodes[row['boss']]['children'].append(row['employee'])
            else:
                roots.append(row['employee'])

        def generate_horizontal_html(node_name):
            rk = nodes[node_name]['rank']
            bg_color = rank_colors.get(rk, "#000")
            txt_color = "black" if rk in ["高專", "累件中", "外圍"] else "white"
            has_children = len(nodes[node_name]['children']) > 0
            html = f'<li>'
            html += f'''<div class="node-card" style="background-color: {bg_color}; color: {txt_color};"><div class="name">{node_name}</div><div class="rank">{rk}</div></div>'''
            if has_children:
                html += '<ul>' + "".join([generate_horizontal_html(c) for c in nodes[node_name]['children']]) + '</ul>'
            html += '</li>'
            return html

        tree_content = "".join([generate_horizontal_html(root) for root in roots])

        # 🎯 3. 控制面板
        col1, col2 = st.columns([3, 1])
        with col1:
            main_zoom = st.slider("🔍 主網頁預覽縮放", 0.05, 1.0, 0.25, 0.05)
        with col2:
            st.write("") 
            import base64
            # 🚀 全螢幕版本 HTML：重點在於 @media print 的修正
            full_html = f"""
            <html>
            <head>
                <meta charset='utf-8'>
                <style>
                    body {{ margin:0; font-family:"Microsoft JhengHei", Arial; background:#fdfdfd; }}
                    #vp {{ width:100vw; height:100vh; overflow: auto; display: block; }}
                    #sf {{ 
                        display: inline-block;
                        padding: 60px; 
                        transform-origin: 0 0; 
                        transform: scale(0.7); 
                        white-space: nowrap; 
                        transition: transform 0.1s ease;
                    }}
                    .tree-hor ul {{ padding-left: 60px; position: relative; list-style-type: none; margin: 0; }}
                    .tree-hor li {{ position: relative; padding: 10px 0 10px 60px; display: flex; align-items: center; }}
                    .tree-hor li::after {{
                        content: ''; position: absolute; top: 0; left: 0;
                        border-left: 3px solid #444; height: 100%; width: 0;
                    }}
                    .tree-hor li:first-child::after {{ height: 50%; top: 50%; }}
                    .tree-hor li:last-child::after {{ height: 50%; }}
                    .tree-hor li:only-child::after {{ display: none; }}
                    .tree-hor li::before {{
                        content: ''; position: absolute; top: 50%; left: 0;
                        border-top: 3px solid #444; width: 60px; height: 0;
                    }}
                    .tree-hor > ul > li::before, .tree-hor > ul > li::after {{ display: none; }}
                    .tree-hor > ul > li {{ padding-left: 0; }}
                    .node-card {{ border: 3px solid #fff; padding: 12px 25px; min-width: 160px; text-align: center; border-radius: 10px; box-shadow: 4px 4px 10px rgba(0,0,0,0.15); z-index: 10; position: relative; }}
                    .node-card .name {{ font-size: 28px; font-weight: bold; }}
                    .node-card .rank {{ font-size: 16px; border-top: 1px solid rgba(255,255,255,0.3); margin-top: 5px; }}
                    .controls {{ position:fixed; top:20px; left:20px; z-index:9999; display:flex; gap:10px; background:white; padding:10px; border-radius:10px; box-shadow:0 4px 15px rgba(0,0,0,0.1); }}
                    .btn {{ padding:8px 15px; border:none; border-radius:5px; cursor:pointer; font-weight:bold; background:#f0f2f6; }}

                    /* 🎯 關鍵列印優化：確保印出完整表格而非只有視窗內的部分 */
                    @media print {{
                        .controls {{ display:none; }}
                        body, #vp {{ overflow: visible !important; height: auto !important; width: auto !important; }}
                        #sf {{ transform: scale(0.6) !important; position: relative !important; padding: 0 !important; top: 0 !important; left: 0 !important; }}
                    }}
                </style>
            </head>
            <body>
                <div class="controls">
                    <button class="btn" onclick="z(0.1)">➕ 放大</button>
                    <button class="btn" onclick="z(-0.1)">➖ 縮小</button>
                    <button class="btn" onclick="window.print()" style="background:#FF4B4B; color:white;">🖨️ 列印完整 PDF</button>
                </div>
                <div id='vp'><div id='sf'><div class='tree-hor'><ul>{tree_content}</ul></div></div></div>
                <script>
                    let s=0.7; const f=document.getElementById('sf');
                    function z(d){{ s=Math.min(Math.max(0.1,s+d),3); f.style.transform=`scale(${{s}})`; }}
                </script>
            </body>
            </html>
            """
            b64 = base64.b64encode(full_html.encode('utf-8')).decode('utf-8')
            st.markdown(f'<a href="data:text/html;base64,{b64}" target="_blank" style="text-decoration:none;"><div style="background:#81D4FA;color:white;padding:10px;border-radius:8px;text-align:center;font-weight:bold;cursor:pointer;">全螢幕瀏覽</div></a>', unsafe_allow_html=True)

        # 4. 主頁面預覽
        preview_html = f"""
        <html><head><style>
            body {{ margin: 0; background: #fdfdfd; }}
            #vp {{ width: 100%; height: 800px; overflow: auto; }}
            #sf {{ display: inline-block; transform-origin: 0 0; transform: scale({main_zoom}) !important; white-space: nowrap; padding: 50px; }}
            .tree-hor ul {{ padding-left: 60px; position: relative; list-style-type: none; margin: 0; }}
            .tree-hor li {{ position: relative; padding: 10px 0 10px 60px; display: flex; align-items: center; }}
            .tree-hor li::after {{ content: ''; position: absolute; top: 0; left: 0; border-left: 3px solid #444; height: 100%; }}
            .tree-hor li:first-child::after {{ height: 50%; top: 50%; }}
            .tree-hor li:last-child::after {{ height: 50%; }}
            .tree-hor li:only-child::after {{ display: none; }}
            .tree-hor li::before {{ content: ''; position: absolute; top: 50%; left: 0; border-top: 3px solid #444; width: 60px; }}
            .tree-hor > ul > li::before, .tree-hor > ul > li::after {{ display: none; }}
            .tree-hor > ul > li {{ padding-left: 0; }}
            .node-card {{ border: 3px solid #fff; padding: 12px 25px; min-width: 160px; text-align: center; border-radius: 10px; box-shadow: 4px 4px 10px rgba(0,0,0,0.1); }}
            .node-card .name {{ font-size: 28px; font-weight: bold; }}
            .node-card .rank {{ font-size: 16px; border-top: 1px solid rgba(255,255,255,0.3); margin-top: 5px; }}
        </style></head>
        <body><div id="vp"><div id="sf"><div class="tree-hor"><ul>{tree_content}</ul></div></div></div></body></html>
        """
        st.components.v1.html(preview_html, height=800)

        st.write("")
        st.write("")
        st.write("")
        st.write("")
        st.write("")

        # 6. 文字版隸屬清單
       # 6. 文字版隸屬清單
        with st.expander("📋 查看文字版隸屬清單"):
            # 🎯 步驟 1：建立一個「主管 -> 直屬屬員」的快速對照表
            boss_to_direct_children = {}
            for _, row in hierarchy_df.iterrows():
                if row['boss']:
                    if row['boss'] not in boss_to_direct_children:
                        boss_to_direct_children[row['boss']] = []
                    boss_to_direct_children[row['boss']].append(row['employee'])

            # 🎯 步驟 2：定義一個遞迴函式，用來數出某個人「下面所有的子孫代」
            def count_all_descendants(name):
                # 拿他的直屬屬員
                direct_children = boss_to_direct_children.get(name, [])
                total = len(direct_children) # 先加上直屬人數
                
                # 再去數他屬員下面的所有人（無限往下延伸）
                for child in direct_children:
                    total += count_all_descendants(child)
                return total

            # 🎯 步驟 3：複製一份 DataFrame 來做畫面顯示，並計算人數
            display_df = hierarchy_df.copy()
            
            # 算出每個人手下的直屬人數（僅供參考對照）
            direct_counts = display_df['employee'].map(lambda x: len(boss_to_direct_children.get(x, [])))
            
            # 算出每個人手下的「傘下總人數」（直屬 + 所有的下線）
            total_team_counts = display_df['employee'].map(count_all_descendants)
            
            # 🎯 步驟 4：把人數塞進表格欄位
            display_df['直屬人數'] = direct_counts
            display_df['團隊總人數'] = total_team_counts

            # 🎯 步驟 5：排序（讓團隊大的人排在上面，找人更好找）
            display_df = display_df.sort_values(by='團隊總人數', ascending=False)

            # 更改名稱並填補空值顯示
            display_df = display_df.rename(columns={
                'employee': '業務姓名',
                'boss': '直屬主管',
                'rank': '職級'
            }).fillna("-(最高階主管)-")

            # 🎨 呈現優化後的表格
            st.table(display_df[['業務姓名', '職級', '直屬主管', '直屬人數', '團隊總人數']])
    else:
        st.warning("目前尚無資料。")

elif menu == "⚙️ 業務排序設定":
    st.title("⚙️ 業務人員自定義排序")
    st.info("💡 說明：在「排序權重」欄位輸入數字（數字越小，排名越靠前）。修改後請點擊左下角按鈕儲存。")

    # 抓取目前的業務清單
    query = "SELECT agent_id, name, rank_id, sort_order FROM agents ORDER BY sort_order ASC, agent_id ASC"
    df_agents = pd.read_sql(query, conn)
    
    # 建立一個編輯器
    edited_df = st.data_editor(
        df_agents,
        column_config={
            "agent_id": None, # 隱藏 ID
            "name": st.column_config.Column("業務姓名", disabled=True),
            "rank_id": st.column_config.Column("職級ID", disabled=True),
            "sort_order": st.column_config.NumberColumn("排序權重", help="數字越小排越前面", min_value=0, step=1)
        },
        hide_index=True,
        use_container_width=True
    )

    if st.button("💾 儲存排序設定"):
        try:
            cursor = conn.cursor()
            for index, row in edited_df.iterrows():
                cursor.execute("UPDATE agents SET sort_order = ? WHERE agent_id = ?", (row['sort_order'], row['agent_id']))
            conn.commit()
            st.success("✅ 排序設定已成功同步至資料庫！")
            st.rerun()
        except Exception as e:
            st.error(f"❌ 儲存失敗：{e}")

st.markdown("---")
st.caption(f"© 2026 Bing Xu. All Rights Reserved. | 投資管理系統 v{CURRENT_VERSION}")
st.caption("本軟體僅供授權用戶使用，嚴禁任何形式之未經授權重製、散佈或商業用途。")