import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from io import BytesIO
import time
# import graphviz


CURRENT_VERSION = "1.1.3"

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
        ["📋 合約總覽","📅 到期續約管理" , "💰 收益發放試算","💰 業務佣金", "👤 客戶總覽", "🌳 團隊組織圖","➕ 新增資料", "⚙️ 基礎資料設定"],
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
    st.title("💰 收益發放試算 (組織聯動版)")
    st.info("💡 系統將根據『生效日』的日期（日）落點，找出本月需發放收益的合約。")

    # --- 1. 篩選與動態組織設定 ---
    with st.expander("🔍 試算條件與組織篩選", expanded=True):
        col_d1, col_d2 = st.columns([2, 1])
        with col_d1:
            # 預設為本月 1 號到今天
            date_range = st.date_input(
                "選擇發放日期區間",
                value=(date.today().replace(day=1), date.today()),
                help="系統會找出『生效日(Day)』落在這個區間內的合約"
            )
        
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_f, end_f = date_range
        else:
            st.warning("請在日曆中選擇開始與結束日期。")
            st.stop()

        # ⚡️ 動態主管偵測
        boss_query = """
            SELECT DISTINCT b.agent_id, b.name 
            FROM agents a
            JOIN agents b ON a.boss_id = b.agent_id
            ORDER BY b.name
        """
        boss_df = pd.read_sql(boss_query, conn)
        boss_list = ["全部主管"] + boss_df['name'].tolist()
        
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            sel_boss = st.selectbox("🎯 所屬主管組織", boss_list, help="此清單僅顯示旗下有隊員的人員")
        
        with col_s2:
            if sel_boss == "全部主管":
                agent_query = "SELECT name FROM agents ORDER BY name"
            else:
                agent_query = f"""
                    SELECT name FROM agents 
                    WHERE name = '{sel_boss}' 
                    OR boss_id = (SELECT agent_id FROM agents WHERE name = '{sel_boss}')
                    ORDER BY name
                """
            agent_df = pd.read_sql(agent_query, conn)
            sel_agents = st.multiselect(
                "💼 承辦業務員 (可多選)", 
                options=agent_df['name'].tolist(),
                placeholder="預設顯示該組織全員"
            )

    # --- 2. 構建核心試算 SQL (年利率 -> 利率) ---
    start_day = start_f.day
    end_day = end_f.day

    query = f"""
    SELECT 
        c.name as 客戶姓名,
        b.name as 業務員,
        boss.name as 所屬主管,
        ic.amount / 10000.0 as '金額(萬)',
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
      AND ic.start_date <= '{date.today().isoformat()}'
      AND ic.end_date >= '{date.today().isoformat()}'
    """

    raw_df = pd.read_sql(query, conn)

    if not raw_df.empty:
        # --- 3. 執行組織過濾 ---
        if sel_agents:
            raw_df = raw_df[raw_df['業務員'].isin(sel_agents)]
        elif sel_boss != "全部主管":
            raw_df = raw_df[(raw_df['所屬主管'] == sel_boss) | (raw_df['業務員'] == sel_boss)]

        # --- 4. 計算收益 (本金 * 利率 / 100) ---
        raw_df['本月預計發放(萬)'] = (raw_df['金額(萬)'] * (raw_df['利率'] / 100.0))
        
        # --- 5. 單位自動換算 (萬 vs 億) ---
        total_pay_wan = raw_df['本月預計發放(萬)'].sum()
        if total_pay_wan >= 10000:
            display_total = f"NT$ {total_pay_wan / 10000:.2f} 億"
        else:
            display_total = f"NT$ {total_pay_wan:,.2f} 萬"

        # --- 6. 顯示結果 ---
        st.divider()
        st.subheader(f"📊 發放試算結果 ({start_f.day}號 ~ {end_f.day}號)")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("待發放筆數", f"{len(raw_df)} 筆")
        m2.metric("總計應發金額", display_total)
        m3.metric("折合台幣約", f"NT$ {int(total_pay_wan * 10000):,}")

        # 表格顯示 (欄位名稱修改為「利率」)
        st.dataframe(
            raw_df[['客戶姓名', '業務員', '所屬主管', '金額(萬)', '利率', '本月預計發放(萬)', '生效日']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "金額(萬)": st.column_config.NumberColumn("金額(萬)", format="%d 萬"),
                "利率": st.column_config.NumberColumn("利率", format="%.1f %%"),
                "本月預計發放(萬)": st.column_config.NumberColumn("預計發放(萬)", format="%.2f 萬")
            }
        )

        # 下載報表
        csv = raw_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載發放清單 (CSV)",
            data=csv,
            file_name=f"payout_report_{date.today()}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.warning(f"🔔 區間內 ({start_day}號 ~ {end_day}號) 無任何需發放收益之有效合約。")

elif menu == "📋 合約總覽":
    st.title("📋 投資合約總覽")
    
    # --- 1. 基礎資料抓取 ---
    all_agents_df = pd.read_sql("SELECT name FROM agents ORDER BY name", conn)
    
    query = """
        SELECT 
            ic.contract_id as ID, 
            c.name as 客戶姓名, 
            a.name as 業務員, 
            ic.contract_type as 類型,
            ic.amount / 10000.0 as '金額(萬)', 
            rp.plan_name as 方案, 
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

    # --- 2. 預處理狀態 (為了讓選單能過濾過期筆數) ---
    if not df_raw.empty:
        df_raw['結束日'] = pd.to_datetime(df_raw['結束日']).dt.date
        this_m = date.today().replace(day=1)
        def get_status_label(d):
            if d.replace(day=1) < this_m: return "🔴 已過期"
            elif d.replace(day=1) == this_m: return "🟡 本月到期"
            else: return "🟢 進行中"
        df_raw['狀態'] = df_raw['結束日'].apply(get_status_label)

    # --- 3. 篩選面板 (放置開關) ---
    with st.expander("🔍 進階篩選面板 (50/50 比例)", expanded=True):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            # 1. 準備統計資料 (邏輯前置，不影響 UI 順序)
            df_for_stats = df_raw.copy() if not df_raw.empty else pd.DataFrame()
            
            # --- ⚡️ 關鍵：使用暫存預留空間，先定義勾選框的狀態 ---
            # 雖然 checkbox 在下方，但我們在邏輯上先獲取它的值
            # 註：在同一個 fragment 或 rerun 中，Streamlit 會自動抓取最新的組件值
            
            # 2. 獲取勾選框狀態 (我們把它移到 multiselect 下面)
            # 這裡先預設一個變數來承接，稍後在下方才正式畫出 UI
            
            # --- 3. 計算聯動後的筆數 ---
            # 我們先假設用戶可能已經勾選了 (Streamlit 會從 Session State 抓取)
            # 如果是第一次執行，預設為 False
            is_show_expired = st.session_state.get("show_exp_key", False)
            
            if not is_show_expired and not df_for_stats.empty:
                df_for_stats = df_for_stats[df_for_stats['狀態'] != "🔴 已過期"]
            
            current_counts = df_for_stats.groupby('業務員').size().to_dict() if not df_for_stats.empty else {}
            
            agent_name_to_label = {name: f"{name} ({current_counts.get(name, 0)})" for name in all_agents_df['name']}

            # --- 4. 正式畫出 UI ---
            sel_agents = st.multiselect(
                "💼 篩選承辦業務 (可複選)", 
                options=all_agents_df['name'].tolist(), 
                format_func=lambda x: agent_name_to_label.get(x, x),
                placeholder="預設顯示全部業務",
                key="agent_select_key"
            )

            # 💡 把勾選框移到這裡 (下面)
            show_expired = st.checkbox(
                "顯示已過期合約", 
                value=False, 
                key="show_exp_key", # 這裡的 key 必須與上方 session_state 一致
                help="未勾選時，姓名旁的筆數僅計算『進行中』與『本月到期』"
            )
            
        with col_f2:
            cust_list = ["全部"] + sorted(df_for_stats['客戶姓名'].unique().tolist()) if not df_for_stats.empty else ["全部"]
            filter_cust = st.selectbox("👤 指定客戶姓名", cust_list)
            
            c_sub1, c_sub2 = st.columns(2)
            with c_sub1:
                status_options = ["全部", "🟢 進行中", "🟡 本月到期"]
                if show_expired: status_options.append("🔴 已過期")
                filter_status = st.selectbox("⏳ 狀態", status_options)
            with c_sub2:
                filter_type = st.selectbox("📄 性質", ["全部", "新約", "續約"])

    # --- 4. 執行最終過濾與顯示 ---
    if not df_raw.empty:
        df_display = df_for_stats.copy() # 從統計後的基礎資料(已處理過期開關)開始過濾
        
        if sel_agents:
            df_display = df_display[df_display['業務員'].isin(sel_agents)]
        if filter_cust != "全部":
            df_display = df_display[df_display['客戶姓名'] == filter_cust]
        if filter_type != "全部":
            df_display = df_display[df_display['類型'] == filter_type]
        if filter_status != "全部":
            df_display = df_display[df_display['狀態'] == filter_status]

        # 業績與筆數指標
        total_wan = df_display['金額(萬)'].sum()
        display_total = f"{total_wan/10000:.2f} 億" if total_wan >= 10000 else f"{total_wan:,.0f} 萬"
        
        st.divider()
        m1, m2 = st.columns(2)
        m1.metric("當前篩選結果", f"{len(df_display)} 筆")
        m2.metric("顯示範圍總業績", f"NT$ {display_total}")
        
        # 顯示表格
        st.dataframe(
            df_display[['ID', '客戶姓名', '業務員', '類型', '金額(萬)', '方案', '利率', '開始日', '結束日', '狀態', '備註']], 
            use_container_width=True, 
            hide_index=True
        )

        # --- 5. 🛠️ 快速維護區 ---
        st.divider()
        st.subheader("🛠️ 合約快速維護區")
        op_col1, op_col2 = st.columns(2)

        with op_col1:
            st.markdown("##### 📝 修正合約資料")
            edit_id = st.selectbox("1. 選擇要修正的 ID", ["請選擇..."] + df_display['ID'].tolist(), key="edit_box")
            if edit_id != "請選擇...":
                row = df_display[df_display['ID'] == edit_id].iloc[0]
                st.info(f"📍 核對：{row['客戶姓名']} | {row['業務員']}")
                new_amt = st.number_input("2. 修正金額(萬)", value=float(row['金額(萬)']), step=1.0)
                new_type = st.radio("3. 修正性質", ["新約", "續約"], index=0 if row['類型'] == "新約" else 1, horizontal=True)
                new_note = st.text_input("4. 修正備註", value=str(row['備註']) if row['備註'] and row['備註'] != 'None' else "")
                if st.button("💾 儲存修正內容", use_container_width=True, type="primary"):
                    conn.execute("UPDATE invest_contracts SET amount=?, note=?, contract_type=? WHERE contract_id=?", 
                                 (new_amt * 10000, new_note, new_type, edit_id))
                    conn.commit()
                    st.success("更新成功！"); time.sleep(1); st.rerun()

        with op_col2:
            st.markdown("##### ❌ 刪除合約")
            del_id = st.selectbox("1. 選擇要刪除的 ID", ["請選擇..."] + df_display['ID'].tolist(), key="del_box")
            if del_id != "請選擇...":
                row = df_display[df_display['ID'] == del_id].iloc[0]
                st.error(f"⚠️ 警告：即將刪除 {row['客戶姓名']} 的 {row['金額(萬)']} 萬合約")
                confirm_del = st.checkbox(f"我確認要永久刪除 ID {del_id}")
                if st.button(f"🔥 執行刪除 ID {del_id}", use_container_width=True, disabled=not confirm_del):
                    conn.execute("DELETE FROM invest_contracts WHERE contract_id=?", (del_id,))
                    conn.commit()
                    st.toast(f"🗑️ 合約 {del_id} 已移除"); time.sleep(1); st.rerun()
    else:
        st.info("目前系統中無任何有效合約。")

        
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
            target_rank = st.selectbox("選擇操作職級", rank_df['職級'].tolist(), key="rank_op_sel")
            curr_r = rank_df[rank_df['職級'] == target_rank].iloc[0]
            
            with st.expander("修改名稱或比例"):
                new_r_name = st.text_input("修正職級名稱", value=curr_r['職級'], key="rank_name_input")
                new_r_comm = st.number_input("修正分潤比例 (%)", value=float(curr_r['分潤比例']*100), step=0.1)
                if st.button("💾 儲存修改", use_container_width=True):
                    conn.execute("UPDATE ranks SET rank_name = ?, commission_rate = ? WHERE rank_id = ?", 
                                 (new_r_name, new_r_comm/100.0, int(curr_r['rank_id'])))
                    conn.commit(); st.success("更新成功"); time.sleep(0.5); st.rerun()

            if st.button(f"❌ 刪除職級：{target_rank}", type="secondary", use_container_width=True):
                check_agent = pd.read_sql(f"SELECT COUNT(*) as count FROM agents WHERE rank_id = {curr_r['rank_id']}", conn)
                if check_agent['count'][0] > 0:
                    st.error(f"無法刪除！目前仍有 {check_agent['count'][0]} 位業務員屬於此職級。請先將他們調職。")
                else:
                    conn.execute("DELETE FROM ranks WHERE rank_id = ?", (int(curr_r['rank_id']),))
                    conn.commit(); st.warning(f"已刪除職級：{target_rank}"); time.sleep(0.5); st.rerun()

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
            target_p = st.selectbox("選擇操作方案", plan_df['方案'].tolist(), key="plan_op_selectbox")
            p_info = plan_df[plan_df['方案'] == target_p].iloc[0]
            
            with st.expander("修改方案參數"):
                new_p_name = st.text_input("修正方案名稱", value=p_info['方案'], key="edit_plan_name_input")
                new_p_rate = st.number_input("修正年利率 (%)", value=float(p_info['年利率']), key="edit_plan_rate_number")
                new_p_period = st.number_input("修正週期 (月)", value=int(p_info['週期']), key="edit_plan_period_number")
                
                if st.button("💾 儲存方案修改", use_container_width=True, key="save_plan_btn"):
                    conn.execute("UPDATE rate_plans SET plan_name = ?, annual_rate = ?, period_months = ? WHERE plan_id = ?", 
                                 (new_p_name, new_p_rate, new_p_period, int(p_info['plan_id'])))
                    conn.commit()
                    st.success("方案更新成功")
                    time.sleep(0.5)
                    st.rerun()

            if st.button(f"❌ 刪除方案：{target_p}", type="secondary", use_container_width=True, key="del_plan_btn"):
                check_contract = pd.read_sql(f"SELECT COUNT(*) as count FROM invest_contracts WHERE plan_id = {p_info['plan_id']}", conn)
                if check_contract['count'][0] > 0:
                    st.error(f"無法刪除！目前仍有 {check_contract['count'][0]} 筆合約使用此方案。")
                else:
                    conn.execute("DELETE FROM rate_plans WHERE plan_id = ?", (int(p_info['plan_id']),))
                    conn.commit()
                    st.warning(f"已刪除方案：{target_p}")
                    time.sleep(0.5)
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

elif menu == "👤 客戶總覽":
    st.title("👤 客戶資料管理")
    
    # 這裡關聯業務員 (agents)
    query = """
    SELECT 
        c.customer_id as ID, 
        c.name as 客戶姓名, 
        a.name as 歸屬業務, 
        c.bank_info as 銀行資訊,
        c.note as 備註
    FROM customers c
    LEFT JOIN agents a ON c.agent_id = a.agent_id
    """
    df_cust = pd.read_sql(query, conn)
    
    if not df_cust.empty:
        # 使用 st.data_editor 甚至可以直接在介面上改備註（如果之後需要的話）
        st.dataframe(df_cust, use_container_width=True, hide_index=True)
        
        st.write(f"目前共有 {len(df_cust)} 位客戶")
    else:
        st.info("目前尚無客戶資料，請至「新增資料」建立。")

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
        with st.form("single_contract"):
            st.info("💡 請填寫下方欄位以建立單筆合約 (金額單位：萬)")
            
            # 1. 抓取基礎資料 (客戶、方案)
            cust_df = pd.read_sql("SELECT customer_id, name FROM customers ORDER BY name", conn)
            # 方案顯示：名稱 + 利率 (年利率 -> 利率)
            plan_df = pd.read_sql("""
                SELECT 
                    plan_id, 
                    plan_name || ' (' || annual_rate || '%)' as 展示名稱,
                    period_months 
                FROM rate_plans
            """, conn)
            
            # 第一橫列：客戶與金額
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                sel_cust = st.selectbox("👤 選擇客戶", cust_df['name'] if not cust_df.empty else ["⚠️ 請先新增客戶"])
            with col_a2:
                amt_wan = st.number_input("💰 投資金額 (萬)", min_value=0.0, value=100.0, step=10.0)
            
            # 第二橫列：方案與生效日
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                sel_plan_display = st.selectbox("📈 選擇方案 (利率)", plan_df['展示名稱'] if not plan_df.empty else ["⚠️ 請先設定方案"])
            with col_b2:
                start_dt = st.date_input("📅 生效日期", date.today())
            
            # 第三橫列：合約性質 (新約/續約)
            st.write("---")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                # ⚡️ 預設值設為「續約」 (index=1)
                contract_type_val = st.radio("📄 合約性質", ["新約", "續約"], index=1, horizontal=True, help="這將影響後續業績統計與佣金計算")
            
            # 備註欄位
            note_val = st.text_area("🗒️ 合約備註 (選填)", placeholder="例如：由舊合約轉入、特別優惠等...", height=100)
            
            # 提交按鈕
            submit_btn = st.form_submit_button("✅ 確認送出單筆合約", use_container_width=True, type="primary")

            if submit_btn:
                if cust_df.empty or plan_df.empty:
                    st.error("❌ 缺少客戶或方案基礎資料，無法建立合約。")
                elif not sel_cust or sel_cust == "⚠️ 請先新增客戶":
                    st.error("❌ 請選擇正確的客戶。")
                else:
                    try:
                        # A. 取得正確的 ID
                        c_id = int(cust_df[cust_df['name'] == sel_cust]['customer_id'].values[0])
                        
                        # B. 解析方案資訊
                        p_row = plan_df[plan_df['展示名稱'] == sel_plan_display]
                        p_id = int(p_row['plan_id'].values[0])
                        months = int(p_row['period_months'].values[0])
                        
                        # C. 計算金額與結束日
                        real_amount = amt_wan * 10000
                        end_dt = start_dt + relativedelta(months=months)
                        
                        # D. 寫入資料庫
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO invest_contracts (
                                customer_id, plan_id, amount, start_date, end_date, 
                                status, note, contract_type, is_renewed
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """, (
                            c_id, p_id, real_amount, start_dt.isoformat(), 
                            end_dt.isoformat(), "Active", note_val, contract_type_val
                        ))
                        
                        conn.commit()
                        st.balloons()
                        st.success(f"🎉 已成功建立【{sel_cust}】的 {amt_wan} 萬合約 ({contract_type_val})")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 儲存失敗，錯誤訊息：{e}")

    else:
        st.write("### 🚀 批量匯入投資合約")
        
        # --- 1. 下載範本 ---
        st.markdown("#### 📥 第一步：下載範本")
        
        today = date.today()
        roc_year = today.year - 1911
        
        # 建立範本 (包含合約性質)
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
        st.download_button("📥 下載全自動對照範本 (CSV)", csv_data, "合約匯入範本_v1.4.csv", "text/csv")

        st.divider()

        # --- 2. 上傳與預檢 ---
        uploaded_file = st.file_uploader("選擇填寫好的 CSV 檔案", type="csv")
        
        if uploaded_file:
            df_upload = None
            for enc in ['utf-8-sig', 'utf-8', 'cp950']:
                try:
                    uploaded_file.seek(0)
                    df_upload = pd.read_csv(uploaded_file, encoding=enc)
                    break
                except: continue
            
            if df_upload is not None:
                # 清理文字
                df_upload['歸屬業務姓名'] = df_upload['歸屬業務姓名'].astype(str).str.strip()
                df_upload['客戶姓名'] = df_upload['客戶姓名'].astype(str).str.strip()

                # 業務員預檢
                db_agents_df = pd.read_sql("SELECT name FROM agents", conn)
                db_agents = set(db_agents_df['name'].unique())
                missing_agents = [a for a in df_upload['歸屬業務姓名'].unique() if a not in db_agents]
                
                if missing_agents:
                    st.error(f"⚠️ 找不到業務員：{', '.join(missing_agents)}")
                else:
                    st.success("✅ 業務員預檢通過！")
                    st.dataframe(df_upload, use_container_width=True, hide_index=True)
                    
                    if st.button("🔥 確定執行智慧匯入", type="primary", use_container_width=True):
                        try:
                            cursor = conn.cursor()
                            success_count = 0
                            error_list = []
                            
                            for _, row in df_upload.iterrows():
                                cust_name = str(row['客戶姓名']).strip()
                                agent_name = str(row['歸屬業務姓名']).strip()
                                
                                # A. 處理合約性質 (預設為續約)
                                c_type = str(row.get('合約性質', '續約')).strip()
                                if not c_type or c_type == 'nan': c_type = "續約"
                                if c_type not in ["新約", "續約"]: c_type = "續約"

                                # B. 方案自動對照 (參數化查詢防止 nan 報錯)
                                try:
                                    target_rate = float(row['年利率(%)'])
                                    target_period = int(row['週期(月)'])
                                    plan_res = pd.read_sql("SELECT plan_id FROM rate_plans WHERE annual_rate = ? AND period_months = ?", conn, params=(target_rate, target_period))
                                    
                                    if plan_res.empty:
                                        error_list.append(f"客戶『{cust_name}』：找不到對應方案 ({target_rate}% / {target_period}月)")
                                        continue
                                    p_id = int(plan_res['plan_id'][0])
                                except:
                                    error_list.append(f"客戶『{cust_name}』：利率或週期格式錯誤")
                                    continue

                                # C. 客戶處理
                                check_cust = pd.read_sql(f"SELECT customer_id FROM customers WHERE name = '{cust_name}'", conn)
                                if check_cust.empty:
                                    ag_res = pd.read_sql(f"SELECT agent_id FROM agents WHERE name = '{agent_name}'", conn)
                                    ag_id = int(ag_res['agent_id'][0])
                                    cursor.execute("INSERT INTO customers (name, agent_id) VALUES (?, ?)", (cust_name, ag_id))
                                    conn.commit()
                                    cust_id = cursor.lastrowid
                                else:
                                    cust_id = int(check_cust['customer_id'][0])

                                # D. 日期與金額處理
                                try:
                                    y, m, d = int(row['生效年'])+1911, int(row['生效月']), int(row['生效日'])
                                    s_dt = date(y, m, d)
                                    e_dt = s_dt + relativedelta(months=target_period)
                                    real_amt = float(row['金額(萬)']) * 10000
                                except:
                                    error_list.append(f"客戶『{cust_name}』：日期或金額格式有誤")
                                    continue

                                # E. 建立合約
                                cursor.execute("""
                                    INSERT INTO invest_contracts (
                                        customer_id, plan_id, amount, start_date, end_date, 
                                        status, note, contract_type, is_renewed
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                                """, (cust_id, p_id, real_amt, s_dt.isoformat(), e_dt.isoformat(), "Active", str(row.get('備註', '')), c_type))
                                success_count += 1
                            
                            conn.commit()
                            if error_list:
                                for err in error_list: st.warning(err)
                            
                            st.balloons()
                            st.success(f"🎉 批量匯入完成！成功：{success_count} 筆")
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 執行出錯：{e}")

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
            c_note = st.text_area("備註 (例如：客戶偏好、特殊要求等)") 
            
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
    
    # 1. 取得日期範圍 (本月第一天到最後一天)
    today = date.today()
    this_m_s = today.replace(day=1)
    this_m_e = (this_m_s + relativedelta(months=1)) - relativedelta(days=1)

    # 2. 從資料庫抓取最新資料
    query = """
    SELECT 
        ic.contract_id, 
        c.name as 客戶姓名, 
        a.name as 業務姓名,
        ic.amount / 10000.0 as '金額(萬)', 
        rp.plan_name as 方案名稱, 
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
    all_df = pd.read_sql(query, conn, params=(this_m_s.isoformat(), this_m_e.isoformat()))

    if not all_df.empty:
        # --- ⚡️ 新增：頂部篩選器 (讓你更好找已處理的筆數) ---
        with st.expander("🔍 續約清單篩選", expanded=True):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                agent_opts = ["全部"] + sorted(all_df['業務姓名'].unique().tolist())
                sel_agent = st.selectbox("篩選業務", agent_opts, key="renew_agent_filter")
            with f_col2:
                cust_opts = ["全部"] + sorted(all_df['客戶姓名'].unique().tolist())
                sel_cust = st.selectbox("篩選客戶", cust_opts, key="renew_cust_filter")

        # 執行過濾
        filtered_df = all_df.copy()
        if sel_agent != "全部":
            filtered_df = filtered_df[filtered_df['業務姓名'] == sel_agent]
        if sel_cust != "全部":
            filtered_df = filtered_df[filtered_df['客戶姓名'] == sel_cust]

        # --- 區塊一：待處理續約 ---
        st.subheader("⚠️ 待處理續約 (尚未標記)")
        pending_df = filtered_df[filtered_df['is_renewed'] == 0].copy()
        
        if not pending_df.empty:
            def get_wed(d_str):
                d = pd.to_datetime(d_str).date()
                days = 2 - d.weekday()
                if days <= 0: days += 7
                return d + relativedelta(days=days)
            
            pending_df['下週三生效'] = pending_df['原結束日'].apply(get_wed)
            pending_df['確認續約'] = False
            
            ed_p = st.data_editor(
                pending_df[['確認續約', '客戶姓名', '業務姓名', '金額(萬)', '方案名稱', '原結束日', '下週三生效']], 
                hide_index=True, use_container_width=True, key="p_editor"
            )
            
            if st.button("🚀 執行批次續約", type="primary", use_container_width=True):
                to_r = ed_p[ed_p['確認續約'] == True].index
                if not to_r.empty:
                    cursor = conn.cursor()
                    for idx in to_r:
                        row = pending_df.loc[idx]
                        oid = row['contract_id']
                        info = pd.read_sql(f"SELECT * FROM invest_contracts WHERE contract_id={oid}", conn).iloc[0]
                        pid = int(info['plan_id'])
                        m = int(pd.read_sql(f"SELECT period_months FROM rate_plans WHERE plan_id={pid}", conn)['period_months'][0])
                        ns = row['下週三生效']; ne = ns + relativedelta(months=m)
                        
                        cursor.execute("INSERT INTO invest_contracts (customer_id, plan_id, amount, start_date, end_date, status, is_renewed, note) VALUES (?,?,?,?,?,?,0,?)",
                                       (int(info['customer_id']), pid, float(info['amount']), ns.isoformat(), ne.isoformat(), "Active", info['note']))
                        cursor.execute("UPDATE invest_contracts SET is_renewed = 1 WHERE contract_id = ?", (oid,))
                    conn.commit()
                    st.toast("續約成功！", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.success("🎉 此篩選條件下無待處理合約")

        st.divider()

        # --- 區塊二：已處理清單 ---
        st.subheader("✅ 已處理續約 (本月結案)")
        # 這裡從過濾後的 filtered_df 抓取 is_renewed = 1 的
        done_df = filtered_df[filtered_df['is_renewed'] == 1].copy()
        if not done_df.empty:
            st.dataframe(
                done_df[['客戶姓名', '業務姓名', '金額(萬)', '方案名稱', '原結束日']],
                use_container_width=True, hide_index=True
            )
        else:
            st.caption("目前無已處理資料 (請檢查篩選條件)")

        st.divider()
        
        # with st.expander("🛠️ 數據庫原始狀態監控 (Debug Only)", expanded=False):
        #     st.write("這張表顯示資料庫內『所有』合約的續約標記，方便確認更新是否成功：")
        #     debug_df = pd.read_sql("""
        #         SELECT 
        #             ic.contract_id as ID, 
        #             c.name as 客戶, 
        #             ic.end_date as 結束日,
        #             ic.is_renewed as 續約狀態
        #         FROM invest_contracts ic
        #         JOIN customers c ON ic.customer_id = c.customer_id
        #         ORDER BY ic.contract_id DESC
        #     """, conn)
            
        #     # 使用彩色標註，方便一眼看穿
        #     def highlight_renewed(val):
        #         color = 'background-color: #2ecc71' if val == 1 else 'background-color: #e74c3c' if val == 0 else 'background-color: #f1c40f'
        #         return f'color: white; {color}'
            
        #     st.dataframe(debug_df.style.applymap(highlight_renewed, subset=['續約狀態']), use_container_width=True)
        #     st.caption("🟢 1 = 已續約 | 🔴 0 = 未續約 | 🟡 None/NULL = 異常空值")

        # --- 區塊三：手動標記狀態 ---
        st.subheader("🛠️ 手動標記狀態")
        
        # 這裡改用 all_df 確保不受上方篩選器的「業務/客戶」限制，方便全域搜尋
        # 且強制過濾出 is_renewed 為 0 (或 NULL) 的資料
        raw_pending = all_df[all_df['is_renewed'].fillna(0).astype(int) == 0]
        
        if not raw_pending.empty:
            # 在選單字串中直接加入 ID，這是最保險的作法，避免同名同金額抓錯筆
            t_options = raw_pending.apply(
                lambda r: f"ID:{int(r['contract_id'])} | {r['客戶姓名']} ({r['金額(萬)']}萬, 結束:{r['原結束日']})", 
                axis=1
            ).tolist()
            
            sel_t = st.selectbox(
                "若已手動新增續約，請在此標記舊合約為『已續約』：", 
                ["請選擇..."] + t_options, 
                key="fix_select_manual"
            )
            
            if st.button("🔧 執行標記並存檔", use_container_width=True):
                if sel_t != "請選擇...":
                    try:
                        # 1. 從選單字串中直接解析出 ID (最準確)
                        # 字串格式為 "ID:123 | ..." -> 取出 123
                        target_id = int(sel_t.split('|')[0].replace('ID:', '').strip())
                        
                        # 2. 執行更新
                        cursor = conn.cursor()
                        cursor.execute("UPDATE invest_contracts SET is_renewed = 1 WHERE contract_id = ?", (target_id,))
                        
                        # 3. 強制提交事務 (Commit)
                        conn.commit()
                        
                        # 4. 成功提示並重整
                        st.toast(f"✅ 合約 ID:{target_id} 狀態已成功變更！", icon="🎉")
                        time.sleep(0.5)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ 標記失敗，錯誤訊息：{e}")
        else:
            st.info("目前無待處理的到期合約。")

elif menu == "💰 業務佣金":
    st.title("💰 業務佣金對帳 (個人新件)")
    st.info("系統將根據合約的『生效日』是否落在選擇區間內，計算業務員應得之佣金。")
    
    # 1. 選擇日期範圍
    col_date1, col_date2 = st.columns([2, 1])
    with col_date1:
        date_range = st.date_input(
            "請選擇對帳日期區間",
            value=(date.today().replace(day=1), date.today()),
            help="起始日與結束日皆會包含在計算內"
        )
    
    # 確保使用者選了兩個日期（開始與結束）
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_f, end_f = date_range
        st.caption(f"📅 目前統計區間：{start_f} 至 {end_f}")

        # 2. SQL 查詢：抓取區間內生效的合約
        query = """
        SELECT 
            c.name as 客戶姓名,
            a.name as 業務姓名,
            r.rank_name as 職級,
            r.commission_rate as 分潤比例,
            ic.amount / 10000.0 as '金額(萬)',
            ic.start_date as 生效日
        FROM invest_contracts ic
        JOIN customers c ON ic.customer_id = c.customer_id
        JOIN agents a ON c.agent_id = a.agent_id
        JOIN ranks r ON a.rank_id = r.rank_id
        WHERE ic.start_date >= ? AND ic.start_date <= ?
        """
        df = pd.read_sql(query, conn, params=(start_f.isoformat(), end_f.isoformat()))

        if not df.empty:
            # --- ⚡️ 新增：篩選 UI 區 ---
            with st.expander("🔍 佣金清單篩選", expanded=True):
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    agent_opts = ["全部"] + sorted(df['業務姓名'].unique().tolist())
                    sel_agent = st.selectbox("篩選業務", agent_opts)
                with f_col2:
                    cust_opts = ["全部"] + sorted(df['客戶姓名'].unique().tolist())
                    sel_cust = st.selectbox("篩選客戶", cust_opts)

            # 執行過濾邏輯
            if sel_agent != "全部":
                df = df[df['業務姓名'] == sel_agent]
            if sel_cust != "全部":
                df = df[df['客戶姓名'] == sel_cust]

            if not df.empty:
                # 3. 計算佣金並四捨五入至兩位
                df['應領佣金(萬)'] = (df['金額(萬)'] * df['分潤比例']).round(2)

                # 4. 介面樣式：強制表格內容置中
                st.markdown("""
                    <style>
                        [data-testid="stDataFrame"] td { text-align: center !important; }
                        [data-testid="stDataFrame"] th { text-align: center !important; }
                        .stTable td, .stTable th { text-align: center !important; }
                    </style>
                """, unsafe_allow_html=True)
                
                st.write("### 📄 區間內佣金明細")
                
                # 格式化顯示用 DataFrame
                display_df = df.copy()
                display_df['分潤比例'] = display_df['分潤比例'].apply(lambda x: f"{x*100:.1f}%")
                
                st.dataframe(
                    display_df[['客戶姓名', '業務姓名', '職級', '金額(萬)', '分潤比例', '應領佣金(萬)', '生效日']],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "金額(萬)": st.column_config.NumberColumn("金額(萬)", format="%.2f 萬"),
                        "應領佣金(萬)": st.column_config.NumberColumn("應領佣金(萬)", format="%.2f 萬"),
                        "生效日": st.column_config.DateColumn("生效日")
                    }
                )

                st.divider()

                # 5. 匯總：業務員領款總表
                st.write("### 📊 業務員領款總表")
                summary_df = df.groupby('業務姓名')['應領佣金(萬)'].sum().reset_index()
                summary_df.columns = ['業務姓名', '總計佣金(萬)']
                
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.table(summary_df.style.format({"總計佣金(萬)": "{:.2f} 萬"}).set_properties(**{'text-align': 'center'}))
                
                with c2:
                    total_all = summary_df['總計佣金(萬)'].sum()
                    st.metric("區間發放總額", f"{total_all:.2f} 萬")
                    st.metric("折合台幣約", f"NT$ {int(total_all * 10000):,}")

                # 6. 下載報表
                csv = summary_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    "📥 下載佣金結算單 (CSV)", 
                    csv, 
                    f"commission_{start_f}_to_{end_f}.csv", 
                    "text/csv",
                    use_container_width=True
                )
            else:
                st.warning("篩選條件下無資料。")

        else:
            st.warning(f"🌙 在 {start_f} 到 {end_f} 之間沒有任何新合約生效。")
    else:
        st.info("請在上方日期欄位選擇『開始日期』與『結束日期』。")

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