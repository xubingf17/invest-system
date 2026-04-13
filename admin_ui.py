import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from io import BytesIO
import time
# import graphviz


CURRENT_VERSION = "1.2.6"

# --- 頁面配置 ---
st.set_page_config(page_title="投資團隊管理系統", layout="wide")

st.markdown("""
    <style>
        /* 1. 側邊欄樣式 (維持你原本的設定) */
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

        /* 2. 核心：強制表格與指標全域置中 */
        
        /* 針對 st.dataframe 的容器與內容 */
        [data-testid="stDataFrame"] {
            display: flex;
            justify-content: center;
        }

        /* 關鍵：強制 Glide Data Grid 內部的文字節點對齊 */
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

        /* 針對傳統 st.table (如果有的話) */
        .stTable td, .stTable th {
            text-align: center !important;
        }

        /* 移除數字欄位預設的靠右對齊 */
        [data-testid="stTable"] td {
            text-align: center !important;
        }
    </style>
""", unsafe_allow_html=True)

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
        ["📋 合約總覽","📅 到期續約管理" , "💰 收益發放試算","💰 業務佣金", "👤 客戶資料管理", "🌳 團隊組織圖","➕ 新增資料", "⚙️ 基礎資料設定"],
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
    st.title("💰 收益發放試算 (次月起算制)")
    st.info("💡 規則：根據生效日(Day)落點發放。且生效當月不發放，須至『生效隔月』才開始。")

    # --- 1. 篩選與日期設定 ---
    with st.expander("📅 選擇發放日期 (日) 區間", expanded=True):
        col_d1, col_d2 = st.columns([2, 1])
        with col_d1:
            date_range = st.date_input(
                "選擇發放日期區間",
                value=(date.today().replace(day=1), date.today()),
                help="系統會找出『生效日(Day)』落在這個區區間內的合約"
            )
        
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_f, end_f = date_range
            start_day = start_f.day
            end_day = end_f.day
            # 取得本月 1 號，用於排除當月新件
            first_day_of_this_month = date.today().replace(day=1)
        else:
            st.warning("請在日曆中選擇開始與結束日期。")
            st.stop()

    # --- 2. 核心 SQL 查詢 ---
    # 邏輯：排除本月新件 (start_date < 本月1號)
    query = f"""
    SELECT 
        c.name as 客戶姓名,
        b.name as 業務員,
        boss.name as 所屬主管,
        ic.amount / 10000.0 as '金額(萬)',
        rp.plan_name,
        rp.annual_rate as '利率',
        ic.start_date as 生效日,
        ic.end_date as 結束日
    FROM invest_contracts ic
    JOIN customers c ON ic.customer_id = c.customer_id
    JOIN agents b ON c.agent_id = b.agent_id
    LEFT JOIN agents boss ON b.boss_id = boss.agent_id
    JOIN rate_plans rp ON ic.plan_id = rp.plan_id
    WHERE CAST(strftime('%d', ic.start_date) AS INTEGER) >= {start_day}
      AND CAST(strftime('%d', ic.start_date) AS INTEGER) <= {end_day}
      AND ic.start_date < '{first_day_of_this_month.isoformat()}'
      AND ic.end_date >= '{date.today().isoformat()}'
    """
    raw_df = pd.read_sql(query, conn)

    if not raw_df.empty:
        # ⚡️ 預處理與筆劃排序
        raw_df['方案(利率)'] = raw_df['plan_name'] + " (" + raw_df['利率'].astype(str) + "%)"
        raw_df = raw_df.sort_values(by=['業務員', '客戶姓名']).reset_index(drop=True)

        # --- 3. 連動篩選面板 ---
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            agent_opts = sorted(raw_df['業務員'].unique().tolist())
            sel_agents = st.multiselect("💼 篩選業務員", agent_opts, key="calc_agent_filter")
            plan_opts = sorted(raw_df['方案(利率)'].unique().tolist())
            sel_plans = st.multiselect("📈 篩選方案(利率)", plan_opts, key="calc_plan_filter")

        with f_col2:
            if sel_agents:
                cust_opts = sorted(raw_df[raw_df['業務員'].isin(sel_agents)]['客戶姓名'].unique().tolist())
            else:
                cust_opts = sorted(raw_df['客戶姓名'].unique().tolist())
            sel_custs = st.multiselect("👤 篩選客戶", cust_opts, key="calc_cust_filter")

        # 執行過濾
        df_filtered = raw_df.copy()
        if sel_agents:
            df_filtered = df_filtered[df_filtered['業務員'].isin(sel_agents)]
        if sel_custs:
            df_filtered = df_filtered[df_filtered['客戶姓名'].isin(sel_custs)]
        if sel_plans:
            df_filtered = df_filtered[df_filtered['方案(利率)'].isin(sel_plans)]

        if not df_filtered.empty:
            # --- 4. 計算發放金額 ---
            df_filtered['本月預計發放(萬)'] = (df_filtered['金額(萬)'] * (df_filtered['利率'] / 100.0))
            
            total_pay_wan = df_filtered['本月預計發放(萬)'].sum()
            display_total = f"NT$ {total_pay_wan / 10000:.2f} 億" if total_pay_wan >= 10000 else f"NT$ {total_pay_wan:,.2f} 萬"

            # --- 5. 顯示指標與表格 ---
            st.divider()
            st.subheader(f"📊 發放試算明細 ({start_day}號 ~ {end_day}號)")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("待發放筆數", f"{len(df_filtered)} 筆")
            m2.metric("總計應發金額", display_total)
            # m3.metric("折合台幣約", f"NT$ {int(total_pay_wan * 10000):,}")

            st.dataframe(
                df_filtered[['客戶姓名', '業務員', '所屬主管', '金額(萬)', '方案(利率)', '本月預計發放(萬)', '生效日']],
                use_container_width=True, hide_index=True, height=500
            )

            # --- 6. 底部統計表：業務與方案分布 ---
            st.divider()
            st.subheader("📊 業務員與合約分佈統計")

            try:
                # 1. 建立基礎交叉表：Index=業務員, Columns=方案(利率)
                pivot_df = df_filtered.pivot_table(
                    index='業務員', 
                    columns='方案(利率)', 
                    values='金額(萬)', 
                    aggfunc='sum',
                    fill_value=0
                )
                
                # 2. 取得利率對照表 (從篩選後的資料抓取 方案 -> 利率 數值)
                # 確保 map 的 key 與 pivot_df 的 columns 一致
                rate_map = df_filtered.drop_duplicates('方案(利率)').set_index('方案(利率)')['利率']

                # 3. 計算「收益」欄位
                # 邏輯：遍歷每一橫列(業務員)，將各方案本金乘以其對應利率後加總，再除以 12
                def calculate_member_income(row):
                    income_sum = 0
                    for plan_name in pivot_df.columns:
                        principal = row[plan_name]
                        plan_rate = rate_map.get(plan_name, 0)
                        income_sum += (principal * (plan_rate / 100.0))
                    return income_sum

                pivot_df['收益'] = pivot_df.apply(calculate_member_income, axis=1)

                # 4. 計算「方案合計」列 (最下方橫列)
                # 注意：收益欄位不參與方案本金的加總，所以我們只加總本金部分
                total_row = pivot_df.sum(axis=0)
                total_row.name = '方案合計(本金)'
                
                # 合併總結行
                pivot_final = pd.concat([pivot_df, total_row.to_frame().T])

                # 5. 顯示表格
                # 使用 precision=2 確保收益的小數點（萬）能看清楚
                st.dataframe(
                    pivot_final.style.format(precision=2, thousands=","), 
                    use_container_width=True, 
                    height=1000
                )
                
                st.info("💡 計算說明：『收益』欄位 = Σ(各方案本金 × 該方案利率 )。")

            except Exception as e:
                st.info(f"暫無足夠資料生成統計表，錯誤訊息：{e}")

            # 下載報表
            csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載發放清單 (CSV)", csv, f"payout_{date.today()}.csv", "text/csv", use_container_width=True)

    else:
        st.warning(f"🔔 區間內 ({start_day}號 ~ {end_day}號) 無符合之發條合約。")

elif menu == "📋 合約總覽":
    st.title("📋 投資合約總覽")
    
    # --- 1. 基礎資料與環境設定 ---
    all_agents_df = pd.read_sql("SELECT agent_id, name FROM agents ORDER BY name", conn)
    
    query = """
        SELECT 
            ic.contract_id as ID, 
            c.name as 客戶姓名, 
            a.name as 業務員, 
            a.agent_id,
            ic.contract_type as 類型,
            ic.amount / 10000.0 as '金額(萬)', 
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
        
        # 💡 先讀取 Checkbox 的狀態（透過 session_state 以防順序移動導致抓不到值）
        show_expired = st.session_state.get("show_exp_key", False)

        with col_f1:
            # A. 業務員篩選 (會計算目前筆數)
            df_for_stats = df_raw.copy() if not df_raw.empty else pd.DataFrame()
            if not show_expired and not df_for_stats.empty:
                df_for_stats = df_for_stats[df_for_stats['狀態'] != "🔴 已過期"]
            
            current_counts = df_for_stats.groupby('業務員').size().to_dict() if not df_for_stats.empty else {}
            agent_labels = {name: f"{name} ({current_counts.get(name, 0)})" for name in all_agents_df['name']}
            sel_agents = st.multiselect("💼 篩選業務員", options=all_agents_df['name'].tolist(), format_func=lambda x: agent_labels.get(x, x))
            
            # B. 客戶篩選 (連動)
            linked_cust_list = sorted(df_raw[df_raw['業務員'].isin(sel_agents)]['客戶姓名'].unique().tolist()) if sel_agents else sorted(df_raw['客戶姓名'].unique().tolist()) if not df_raw.empty else []
            sel_customers = st.multiselect("👤 篩選客戶姓名", options=linked_cust_list)

        with col_f2:
            # C. 方案篩選
            all_plan_rate_list = sorted(df_raw['方案(利率)'].unique().tolist()) if not df_raw.empty else []
            sel_plans_rates = st.multiselect("📈 篩選方案 (利率)", options=all_plan_rate_list)
            
            # D. 日期範圍
            if not df_raw.empty:
                date_range = st.date_input("📅 篩選生效日範圍", value=(df_raw['開始日'].min(), df_raw['開始日'].max()))
            else:
                date_range = (date.today(), date.today())

        # 💡 將狀態篩選與過期開關移至最下方
        st.write("---")
        c_sub1, c_sub2, c_sub3 = st.columns(3)
        with c_sub1:
            status_opts = ["全部", "🟢 進行中", "🟡 本月到期"]
            if show_expired: status_opts.append("🔴 已過期")
            filter_status = st.selectbox("⏳ 合約狀態", status_opts)
        with c_sub2:
            filter_type = st.selectbox("📄 合約性質", ["全部", "新約", "續約"])
        with c_sub3:
            st.write("") # 對齊用
            # 💡 這裡是你要移動的 Checkbox
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

        # 業績總結
        total_wan = df_display['金額(萬)'].sum()
        display_total = f"{total_wan/10000:.2f} 億" if total_wan >= 10000 else f"{total_wan:,.0f} 萬"
        st.divider()
        m1, m2 = st.columns(2)
        m1.metric("符合條件筆數", f"{len(df_display)} 筆")
        m2.metric("篩選總金額 (NT$)", display_total)

        # 顯示表格並捕捉選取事件
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
                        new_amt = st.number_input("金額(萬)", value=float(info['amount']/10000))
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
                st.write(f"客戶：{row['客戶姓名']} | 金額：{row['金額(萬)']} 萬")
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
            st.dataframe(plan_df[['方案', '年利率', '週期']], hide_index=True)
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
            df_display, 
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

        # --- ⚡️ 第三層：合約細節表單 ---
        with st.form("single_contract_combined"):
            col_amt, col_plan = st.columns(2)
            with col_amt:
                amt_wan = st.number_input("💰 投資金額 (萬)", min_value=0.0, value=100.0, step=10.0)
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
            "金額(萬)": [100.0, 50.0],
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
                            real_amt = float(row['金額(萬)']) * 10000
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
    
    # 💡 初始化強制刷新金鑰
    if 'renew_sync_key' not in st.session_state:
        st.session_state.renew_sync_key = 0

    # --- 1. 時間區間選擇器 ---
    with st.expander("📅 篩選合約到期日期區間", expanded=True):
        col_date1, col_date2 = st.columns([2, 1])
        with col_date1:
            today = date.today()
            default_end = (today + relativedelta(months=1)).replace(day=1) - relativedelta(days=1)
            renew_range = st.date_input("選擇到期日區間", value=(today, default_end))
    
    if isinstance(renew_range, tuple) and len(renew_range) == 2:
        r_start, r_end = renew_range

        # 2. 核心 SQL 查詢
        query = """
        SELECT 
            ic.contract_id, 
            c.name as 客戶姓名, 
            a.name as 業務姓名,
            ic.amount / 10000.0 as '金額(萬)', 
            rp.plan_name, 
            rp.annual_rate,
            rp.plan_id,
            ic.end_date as 原結束日,
            ic.is_renewed,
            ic.note
        FROM invest_contracts ic
        JOIN customers c ON ic.customer_id = c.customer_id
        JOIN agents a ON c.agent_id = a.agent_id
        JOIN rate_plans rp ON ic.plan_id = rp.plan_id
        WHERE ic.end_date >= ? AND ic.end_date <= ?
        """
        all_df = pd.read_sql(query, conn, params=(r_start.isoformat(), r_end.isoformat()))

        if not all_df.empty:
            # ⚡️ 關鍵修正：建立「唯一方案標籤」，解決同名不同利率的問題
            # 格式： 半年期 (6.0%)
            all_df['方案(利率)'] = all_df['plan_name'] + " (" + all_df['annual_rate'].astype(str) + "%)"
            
            # ⚡️ 強制按姓名筆劃排序
            all_df = all_df.sort_values(by=['業務姓名', '客戶姓名']).reset_index(drop=True)
            
            # --- 3. 進階連動篩選面板 ---
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                # 業務清單排序
                agent_opts = sorted(all_df['業務姓名'].unique().tolist())
                sel_agents = st.multiselect("💼 篩選業務員", agent_opts, key="renew_agent_filter")
                
                # ⚡️ 方案清單：現在會列出所有「名稱+利率」的組合，不會再遺漏
                plan_rate_opts = sorted(all_df['方案(利率)'].unique().tolist())
                sel_plans = st.multiselect("📈 篩選方案(利率)", plan_rate_opts, key="renew_plan_filter")

            with f_col2:
                # 客戶連動：只顯示選中業務員的客戶 (並排序)
                if sel_agents:
                    cust_opts = sorted(all_df[all_df['業務姓名'].isin(sel_agents)]['客戶姓名'].unique().tolist())
                else:
                    cust_opts = sorted(all_df['客戶姓名'].unique().tolist())
                
                sel_custs = st.multiselect("🔍 篩選客戶", cust_opts, key="renew_cust_filter")

            # 執行篩選過濾
            df_filtered = all_df.copy()
            if sel_agents:
                df_filtered = df_filtered[df_filtered['業務姓名'].isin(sel_agents)]
            if sel_custs:
                df_filtered = df_filtered[df_filtered['客戶姓名'].isin(sel_custs)]
            if sel_plans:
                df_filtered = df_filtered[df_filtered['方案(利率)'].isin(sel_plans)]

            # --- 4. 區塊一：待處理續約 ---
            # 只抓 is_renewed 為 0 (未處理) 的
            pending_df = df_filtered[df_filtered['is_renewed'].fillna(0).astype(int) == 0].copy()
            
            st.subheader(f"⚠️ 待處理續約名單 ({len(pending_df)} 筆)")
            
            if not pending_df.empty:
                def get_wed(d_str):
                    d = pd.to_datetime(d_str).date()
                    days_until_wed = (2 - d.weekday() + 7) % 7
                    return d + relativedelta(days=days_until_wed)
                
                pending_df['下週三生效'] = pending_df['原結束日'].apply(get_wed)
                
                select_all = st.checkbox("全選畫面上所有待處理合約", value=False, key="select_all_btn")
                pending_df['確認續約'] = select_all
                
                # 使用動態 Key 強制刷新編輯器
                dynamic_key = f"renew_editor_{st.session_state.renew_sync_key}"
                
                ed_p = st.data_editor(
                    pending_df[['確認續約', '客戶姓名', '業務姓名', '金額(萬)', '方案(利率)', '原結束日', '下週三生效']], 
                    hide_index=True, use_container_width=True, key=dynamic_key,
                    height=800
                )

                if st.button("🚀 執行批次續約並歸檔", type="primary", use_container_width=True):
                    # 💡 1. 取得編輯器中被勾選的行
                    # 我們直接將 ed_p 跟 pending_df 的 contract_id 合併，確保抓到的是正確的 ID
                    selected_rows = ed_p[ed_p['確認續約'] == True]
                    
                    if not selected_rows.empty:
                        try:
                            cursor = conn.cursor()
                            msg_placeholder = st.empty()
                            
                            # 💡 2. 這裡改用 selected_rows 的資料，因為 ed_p 可能不包含 contract_id
                            # 我們要從原本的 pending_df 找回對應的 ID
                            # 為了保險，我們直接從 pending_df 篩選出跟 ed_p 勾選內容一致的資料
                            # 最穩的方法是：直接利用 pending_df 的索引來對應 ed_p
                            
                            processed_count = 0
                            for idx in selected_rows.index:
                                # 從原始 pending_df 抓取真正的資料庫 ID
                                real_row = pending_df.loc[idx]
                                oid = int(real_row['contract_id'])
                                
                                # 3. 抓取原約資訊 (與你原本邏輯相同)
                                cursor.execute("SELECT customer_id, plan_id, amount FROM invest_contracts WHERE contract_id = ?", (oid,))
                                info = cursor.fetchone()
                                
                                if info:
                                    c_id, p_id, amt = info
                                    cursor.execute("SELECT period_months FROM rate_plans WHERE plan_id = ?", (p_id,))
                                    p_months = int(cursor.fetchone()[0])
                                    
                                    # 計算日期
                                    ns = real_row['下週三生效']
                                    ne = ns + relativedelta(months=p_months)
                                    
                                    # 4. 執行資料庫變更
                                    # A. 建立新約
                                    cursor.execute("""
                                        INSERT INTO invest_contracts (
                                            customer_id, plan_id, amount, start_date, end_date, 
                                            status, is_renewed, note, contract_type
                                        ) VALUES (?, ?, ?, ?, ?, 'Active', 0, ?, '續約')
                                    """, (c_id, p_id, amt, ns.isoformat(), ne.isoformat(), f"由 ID:{oid} 續約轉入"))
                                    
                                    # B. 更新舊約 (關鍵：強制轉型 oid 確保 SQL 匹配)
                                    cursor.execute("""
                                        UPDATE invest_contracts 
                                        SET is_renewed = 1, status = 'Closed' 
                                        WHERE contract_id = ?
                                    """, (oid,))
                                    
                                    processed_count += 1
                            
                            # 💡 5. 執行存檔
                            conn.commit()
                            
                            # 💡 6. 更新 Session State 強制 UI 刷新
                            st.session_state.renew_sync_key += 1
                            
                            msg_placeholder.success(f"✅ 成功處理 {processed_count} 筆續約！資料已存入。5 秒後自動刷新...")
                            time.sleep(5)
                            msg_placeholder.empty()
                            st.rerun()

                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ 續約失敗：{e}")
                    else:
                        st.warning("⚠️ 請先勾選要續約的項目。")
            else:
                st.success("🎉 選定條件下所有合約皆已處理完成。")

            st.divider()

            # --- 5. 區塊二：已處理完成清單 ---
            done_df = df_filtered[df_filtered['is_renewed'] == 1].copy()
            st.subheader(f"✅ 已處理完成清單 ({len(done_df)} 筆)")
            if not done_df.empty:
                done_df = done_df.sort_values(by='原結束日', ascending=False)
                st.dataframe(done_df[['客戶姓名', '業務姓名', '金額(萬)', '方案(利率)', '原結束日']], use_container_width=True, hide_index=True)

        else:
            st.info(f"📅 在 {r_start} 到 {r_end} 之間沒有到期合約。")

elif menu == "💰 業務佣金":
    st.title("💰 業務佣金對帳 ")
    st.info("💡 規則提醒：獎勵期數計算為『放款日次月』算第 1 次。系統將以『結束日期』作為期數計算基準。")

    # --- 0. 動態獎勵條件管理區 ---
    with st.expander("🎁 額外活動獎勵管理", expanded=True):
        if 'extra_rules' not in st.session_state:
            st.session_state.extra_rules = []
            
        all_plans_info = pd.read_sql("SELECT plan_name, annual_rate, period_months FROM rate_plans", conn)
        all_plans_info['display'] = all_plans_info['plan_name'] + " (" + all_plans_info['annual_rate'].astype(str) + "%)"
        
        r_col1, r_col2, r_col3 = st.columns([2, 1, 1])
        with r_col1:
            sel_rule_plan = st.selectbox("選擇利率方案", all_plans_info['display'].tolist())
        with r_col2:
            sel_rule_time = st.number_input("第幾次領取時獎勵 (次月=1)", min_value=1, value=6, step=1)
        with r_col3:
            sel_rule_bonus = st.number_input("加給 % 數", min_value=0.0, value=2.0, format="%.2f")
            
        if st.button("➕ 新增獎勵規則", use_container_width=True):
            max_p = all_plans_info[all_plans_info['display'] == sel_rule_plan]['period_months'].values[0]
            if sel_rule_time >= max_p:
                st.error(f"❌ 獎勵期數 ({sel_rule_time}) 不得大於等於合約總期數 ({max_p})")
            else:
                new_rule = {"id": time.time(), "plan": sel_rule_plan, "time": sel_rule_time, "bonus_rate": sel_rule_bonus / 100}
                st.session_state.extra_rules.append(new_rule)
                st.rerun() 
        
        if st.session_state.extra_rules:
            st.write("---")
            for idx, rule in enumerate(st.session_state.extra_rules):
                rc1, rc2 = st.columns([4, 1])
                with rc1: st.write(f"📍 {rule['plan']} - 第 {rule['time']} 次：加給 {rule['bonus_rate']*100:.2f}%")
                with rc2:
                    if st.button(f"❌", key=f"del_{rule['id']}"):
                        st.session_state.extra_rules.pop(idx)
                        st.rerun()
            if st.button("🗑️ 全部清空規則"):
                st.session_state.extra_rules = []
                st.rerun()

    # 1. 選擇日期範圍
    col_date1, col_date2 = st.columns([2, 1])
    with col_date1:
        date_range = st.date_input("請選擇對帳日期區間", value=(date.today().replace(day=1), date.today()))
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_f, end_f = date_range

        # 2. SQL 查詢
        query = """
        SELECT 
            c.name as 客戶姓名, a.name as 業務姓名, r.rank_name as 職級, r.commission_rate as 個人比例,
            ic.amount / 10000.0 as '金額', rp.plan_name, rp.annual_rate as '利率', 
            ic.start_date as 生效日, rp.period_months as 總期數,
            b.name as 直屬主管, rb.rank_name as 主管職級, rb.commission_rate as 主管比例,
            bb.name as 上級主管, rbb.rank_name as 上級職級, rbb.commission_rate as 上級比例
        FROM invest_contracts ic
        JOIN customers c ON ic.customer_id = c.customer_id
        JOIN agents a ON c.agent_id = a.agent_id
        JOIN ranks r ON a.rank_id = r.rank_id
        JOIN rate_plans rp ON ic.plan_id = rp.plan_id
        LEFT JOIN agents b ON a.boss_id = b.agent_id
        LEFT JOIN ranks rb ON b.rank_id = rb.rank_id
        LEFT JOIN agents bb ON b.boss_id = bb.agent_id
        LEFT JOIN ranks rbb ON bb.rank_id = rbb.rank_id
        WHERE ic.start_date <= ?
        """
        df_all = pd.read_sql(query, conn, params=(end_f.isoformat(),))

        if not df_all.empty:
            df_all['方案名稱(%)'] = df_all['plan_name'] + " (" + df_all['利率'].astype(str) + "%)"

            # --- 3. 核心計算邏輯 (進位與隔離) ---
            def calculate_detail_logic(row):
                start_dt = pd.to_datetime(row['生效日']).date()
                diff_months = (end_f.year - start_dt.year) * 12 + (end_f.month - start_dt.month)
                is_new = (row['生效日'] >= start_f.isoformat() and row['生效日'] <= end_f.isoformat())
                
                if diff_months < 0 or diff_months >= row['總期數']:
                    return pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

                amt = row['金額']
                extra_bonus = 0.0
                for rule in st.session_state.get('extra_rules', []):
                    if row['方案名稱(%)'] == rule['plan'] and diff_months == rule['time']:
                        extra_bonus = round(amt * rule['bonus_rate'], 2)

                self_base = round(amt * row['個人比例'], 2) if is_new else 0.0
                boss_over = 0.0
                grand_over = 0.0
                if is_new:
                    p_s, p_b, p_bb = row['個人比例'], (row['主管比例'] or 0), (row['上級比例'] or 0)
                    if pd.notna(row['直屬主管']):
                        if p_b > p_s: boss_over = round(amt * (p_b - p_s), 2)
                        elif p_b == p_s and row['主管職級'] != '主任': boss_over = round(amt * 0.002, 2)
                    
                    if pd.notna(row['上級主管']):
                        if p_bb > p_b:
                            val = amt * (p_bb - max(p_b, p_s))
                            if p_b == p_s and row['主管職級'] != '主任': val -= amt * 0.002
                            grand_over = round(val, 2)
                        elif p_bb == p_s and row['上級職級'] != '主任': grand_over = round(amt * 0.001, 2)

                return pd.Series([round(self_base + extra_bonus, 2), boss_over, grand_over, (amt if (is_new or extra_bonus > 0) else 0.0), extra_bonus, self_base])

            df_all[['個人小計', '主管加給', '上級加給', '計算業績', '活動獎勵', '職級分潤']] = df_all.apply(calculate_detail_logic, axis=1)
            df_final = df_all[(df_all['個人小計'] + df_all['主管加給'] + df_all['上級加給'] + df_all['計算業績']) > 0].copy()

            if not df_final.empty:
                # --- 4. 數據歸併 ---
                summary_data = []
                for _, r in df_final.iterrows():
                    payee = r['直屬主管'] if r['職級'] == '高專' and pd.notna(r['直屬主管']) else r['業務姓名']
                    if r['計算業績'] > 0:
                        summary_data.append({'姓名': payee, '方案': r['方案名稱(%)'], '類別': '業績', '金額': r['計算業績']})
                    if r['職級分潤'] > 0:
                        summary_data.append({'姓名': payee, '方案': r['方案名稱(%)'], '類別': '個人佣金', '金額': r['職級分潤']})
                    if r['主管加給'] > 0:
                        summary_data.append({'姓名': r['直屬主管'], '方案': r['方案名稱(%)'], '類別': '差%加給', '金額': r['主管加給']})
                    if r['上級加給'] > 0:
                        summary_data.append({'姓名': r['上級主管'], '方案': r['方案名稱(%)'], '類別': '差%加給', '金額': r['上級加給']})
                    if r['活動獎勵'] > 0:
                        summary_data.append({'姓名': payee, '方案': r['方案名稱(%)'], '類別': '獎勵', '金額': r['活動獎勵']})

                df_sum = pd.DataFrame(summary_data)

                # --- 5. 製作統計矩陣 ---
                plans_query = "SELECT plan_name, annual_rate FROM rate_plans ORDER BY annual_rate ASC"
                ordered_plans = [f"{rp['plan_name']} ({rp['annual_rate']}%)" for _, rp in pd.read_sql(plans_query, conn).iterrows()]

                all_names = df_sum['姓名'].unique()
                pivot_perf = df_sum[df_sum['類別'] == '業績'].pivot_table(index='姓名', columns='方案', values='金額', aggfunc='sum', fill_value=0)
                pivot_perf = pivot_perf.reindex(index=all_names, columns=ordered_plans, fill_value=0)

                comm_type_pivot = df_sum[df_sum['類別'] != '業績'].pivot_table(index='姓名', columns='類別', values='金額', aggfunc='sum', fill_value=0)
                for col in ['個人佣金', '差%加給', '獎勵']:
                    if col not in comm_type_pivot.columns: comm_type_pivot[col] = 0.0

                pivot_perf['個人業績佣金'] = comm_type_pivot['個人佣金'].reindex(pivot_perf.index, fill_value=0)
                pivot_perf['差%'] = comm_type_pivot['差%加給'].reindex(pivot_perf.index, fill_value=0)
                pivot_perf['獎勵'] = comm_type_pivot['獎勵'].reindex(pivot_perf.index, fill_value=0)
                pivot_perf['應領佣金'] = (pivot_perf['個人業績佣金'] + pivot_perf['差%'] + pivot_perf['獎勵']).round(2)
                
                pivot_perf = pivot_perf.sort_values(by='應領佣金', ascending=False)

                # --- 6. 顯示圖表 (無色版本) ---
                st.write("### 🧩 佣金統計矩陣 (細項拆解)")
                format_dict = {plan: "{:.0f}" for plan in ordered_plans}
                for extra in ['個人業績佣金', '差%', '獎勵', '應領佣金']:
                    format_dict[extra] = "{:.2f}"
                
                st.dataframe(
                    pivot_perf.style.format(format_dict), 
                    use_container_width=True, 
                    height=500
                )

                st.divider()
                st.write("### 📄 本月對帳明細 (計算基準)")
                st.dataframe(
                    df_final[['客戶姓名', '業務姓名', '生效日', '方案名稱(%)', '計算業績', '職級分潤', '活動獎勵', '主管加給', '上級加給', '個人小計']],
                    use_container_width=True, hide_index=True,
                    column_config={"職級分潤": "本件分潤", "活動獎勵": "獎勵", "個人小計": "小計"}
                )
            else:
                st.warning("🌙 此區間無應領佣金或業績資料。")

# --- 🌳 團隊組織圖 模組 ---
elif menu == "🌳 團隊組織圖":
    st.title("🌳 團隊組織架構圖")
    st.info("💡 提示：此圖表根據業務員設定之「直屬主管」自動生成。若要調整隸屬關係，請至「基礎資料設定」。")

    # 1. 執行 SQL 抓取關係 (包含業務姓名、主管姓名、職級)
    query = """
        SELECT 
            a.name as employee, 
            b.name as boss, 
            r.rank_name as rank
        FROM agents a
        LEFT JOIN agents b ON a.boss_id = b.agent_id
        JOIN ranks r ON a.rank_id = r.rank_id
    """
    hierarchy_df = pd.read_sql(query, conn)

    if not hierarchy_df.empty:
        
        # 2. 構建 Graphviz 語法字串 (使用高相容性語法)
        # TB 代表 Top to Bottom (由上而下)
        dot_code = """
        digraph {
            graph [rankdir=TB, nodesep=0.5, ranksep=0.8];
            node [
                shape=box, 
                style="filled,rounded", 
                color="#1f77b4", 
                fillcolor="#1f77b4", 
                fontcolor=white, 
                fontname="Arial",
                width=1.5,
                height=0.6
            ];
            edge [color="#777777", penwidth=1.5];
        """

        for _, row in hierarchy_df.iterrows():
            # 節點顯示：姓名 \n (職級)
            node_label = f"{row['employee']}\\n({row['rank']})"
            dot_code += f'    "{row["employee"]}" [label="{node_label}"];\n'
            
            # 如果有主管，建立連線 (主管 -> 部屬)
            if row['boss']:
                dot_code += f'    "{row["boss"]}" -> "{row["employee"]}";\n'

        dot_code += "}"

        # 3. 渲染圖表
        try:
            st.graphviz_chart(dot_code)
        except Exception as e:
            st.error(f"圖表渲染失敗，請確保已安裝 graphviz 套件。錯誤：{e}")
        
        # 4. 附上清單方便核對
        with st.expander("📋 查看文字版隸屬清單"):
            display_h = hierarchy_df.copy()
            display_h.columns = ['業務姓名', '直屬主管', '職級']
            st.table(display_h.fillna("-(最高階)-"))
            
    else:
        st.warning("目前資料庫中尚無業務員資料，請先至「新增資料」建立。")

st.markdown("---")
st.caption(f"© 2026 Bing Xu. All Rights Reserved. | 投資管理系統 v{CURRENT_VERSION}")
st.caption("本軟體僅供授權用戶使用，嚴禁任何形式之未經授權重製、散佈或商業用途。")