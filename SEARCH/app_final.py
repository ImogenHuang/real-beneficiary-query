# -*- coding: utf-8 -*-
"""
Created on Mon Dec  1 14:23:17 2025

@author: user
"""



import streamlit as st
import pandas as pd
import sys
import os
import io
import contextlib
from datetime import datetime
from typing import Optional, Any, Dict, List, Union

# --- 設定路徑 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
scripts_path = os.path.join(current_dir, 'scripts')
data_file_name = 'concat_all.csv'
data_path = os.path.join(current_dir, 'data', data_file_name)

if scripts_path not in sys.path:
    sys.path.append(scripts_path)

# --- 嘗試 Import 您的背景程式 (放在 Global Scope 確保一次導入) ---
backend_script = None
try:
    # 這裡假設您的檔案叫做 "商工登記實質受益人查詢.py"
    import 商工登記實質受益人查詢 as imported_script
    backend_script = imported_script
except ImportError as e:
    # 這裡只會顯示錯誤，但不會讓整個 Streamlit 停止，讓使用者看到介面
    st.error(f"找不到背景程式，請確認 'scripts' 資料夾下有 '商工登記實質受益人查詢.py'。\n錯誤訊息: {e}")
except Exception as e:
    st.error(f"導入背景程式時發生未知錯誤: {e}")

# --- 側邊欄：讀取資料庫 (使用 Streamlit Cache 加速) ---
@st.cache_data
def load_company_data(file_path: str) -> pd.DataFrame:
    """載入並快取公司名單 CSV 資料"""
    st.header("資料庫狀態")
    
    if not os.path.exists(file_path):
        st.warning(f"找不到檔案：{file_path}")
        return pd.DataFrame()

    try:
        # 讀取 CSV (假設編碼為 utf-8-sig)
        df = pd.read_csv(file_path, encoding='utf-8-sig',dtype={'統編': str})
        
        # 確保統編是字串格式，避免開頭 0 被吃掉
        if '統編' in df.columns:
            #df['統編'] = df['統編'].astype(str)
            # 先轉成浮點數（處理可能的空值）
            df['統編'] = pd.to_numeric(df['統編'], errors='coerce')
            # 移除 NaN 列
            df = df.dropna(subset=['統編'])
            # 轉成整數再轉字串，這樣就沒有 .0 了
            df['統編'] = df['統編'].astype(int).astype(str).str.strip().str.zfill(8)
        
        st.success(f"已載入上市櫃名單：{len(df)} 筆")
        if not df.empty and '統編' in df.columns:
            st.info(f"範例統編：{df['統編'].head().tolist()}")
        return df
    except Exception as e:
        st.error(f"讀取 CSV 失敗: {e}")
        return pd.DataFrame()

# --- 介面設定 ---
st.set_page_config(page_title="實質受益人查詢系統", layout="wide")
st.title("🔍 商工登記實質受益人查詢系統")
st.markdown("---")

with st.sidebar:
    df_companies = load_company_data(data_path)

# --- 主畫面 ---
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. 輸入查詢資訊")
    input_tax_id = st.text_input("請輸入統一編號 (8碼)", max_chars=8)
    run_btn = st.button("開始查詢", type="primary")

with col2:
    st.subheader("2. 執行日誌與結果")
    log_area = st.empty() # 預留位置顯示 Log
    result_area = st.empty() # 預留位置顯示結果

# --- 執行邏輯 ---
if run_btn:
    
    # 格式檢查
    if not input_tax_id or len(input_tax_id) != 8 or not input_tax_id.isdigit():
        st.error("請輸入有效的 **8 碼數字** 統一編號。")
        st.stop() # 停止執行後續邏輯
    
    # 統一格式處理
    input_tax_id = input_tax_id.strip().zfill(8)

    
    # 確保 DataFrame 格式一致
    if '統編' in df_companies.columns:
        
        df_companies['統編'] = df_companies['統編'].astype(str).str.strip().str.zfill(8)
        #st.write("處理後的統編欄位(前10筆):")
        #st.write(df_companies['統編'].head(10).tolist())
    else:
        st.error("❌ DataFrame 中沒有「統編」欄位!")
        st.stop()
    
    # 比對
    exempt_company = df_companies[df_companies['統編'] == input_tax_id]
    # 除錯:顯示比對結果
    st.write(f"比對結果筆數: {len(exempt_company)}")



    if not exempt_company.empty:
        # --- 情況 A: 在名單內 (免辨識) ---
        
        # *** 修正：使用 .iloc[0] 取得第一筆資料，避免 'i' undefined 的錯誤 ***
        if '公司名稱' in exempt_company.columns:
            # 使用 .iloc[0] 確保獲取唯一匹配項的第一列
            comp_name = exempt_company.iloc[0]['公司名稱'] 
        else:
            comp_name = "未知公司"
            
        st.success(f"✅ 統編 **{input_tax_id}** ({comp_name}) 位於上市櫃名單中。")
        st.info("💡 依規定：**免除辨識實質受益人**。")
        
        # 產生簡單的 CSV 下載
        res_df = pd.DataFrame([{"統編": input_tax_id, "公司名稱": comp_name, "狀態": "免辨識(上市櫃)"}])
        # 使用 st.download_button 顯示在結果區
        with result_area.container():
            st.dataframe(res_df)
            csv = res_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("下載查詢結果 (CSV)", csv, "exempt_result.csv", "text/csv")

    else:
        # --- 情況 B: 不在名單內 (執行背景程式) ---
        st.warning(f"統編 {input_tax_id} 不在免辨識名單中，啟動背景程式查詢...")
        
        if backend_script is None:
            # 如果一開始導入失敗，則不再執行後續邏輯
            st.error("無法執行背景程式，請先修復導入錯誤。")
            st.stop()

        # 捕捉 print 輸出的核心邏輯
        output_buffer = io.StringIO()
        result_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
        
        try:
            with st.spinner("背景程式運行中..."):
                # 使用 redirect_stdout 將 print 導向到 buffer
                with contextlib.redirect_stdout(output_buffer):
                    # *** 呼叫您的背景程式 ***
                    if hasattr(backend_script, 'run_query'):
                        result_data = backend_script.run_query(input_tax_id)
                    else:
                        print("錯誤：在背景程式中找不到 'run_query' 函數。")
                        
            # 顯示程式跑出來的 Log (Print 的內容)
            log_content = output_buffer.getvalue()
            log_area.code(log_content, language="text", line_numbers=True)

            # 處理結果並提供下載
            
            
            if result_data:
                
                if isinstance(result_data, list):
                        # 早退情境（免辨識/非核准設立等）：後端回傳 list
                        st.success("查詢完成（免辨識或早退情境）")
                        df_quick = pd.DataFrame(result_data)

                        with result_area.container():
                            st.dataframe(df_quick)
                            csv_quick = df_quick.to_csv(index=False).encode('utf-8-sig')
                            st.download_button("下載查詢結果 (CSV)", csv_quick,
                                               "quick_result.csv", "text/csv")

                        # 早退情境不需要再走 Excel 匯出等完整流程
                        st.stop()

                st.success("查詢完成！")
            
                # 取得各表格
                beneficial_owners = pd.DataFrame(result_data.get("beneficial_owners", []))
                company_info_df = result_data.get("company_info", pd.DataFrame())
                holding_process_df = result_data.get("holding_process", pd.DataFrame())
                warnings_df = result_data.get("warnings", pd.DataFrame())
                #result_data = backend_script.run_query(input_tax_id)
            
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    result_data["full_result"].to_excel(writer, sheet_name='完整查詢結果', index=False)
                    beneficial_owners.to_excel(writer, sheet_name='實質受益人', index=False)
                    company_info_df.to_excel(writer, sheet_name='公司基本資料', index=False)
                    holding_process_df.to_excel(writer, sheet_name='持股計算過程', index=False)
                    warnings_df.to_excel(writer, sheet_name='警示報告', index=False)
                output.seek(0)
            
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{input_tax_id}_beneficial_owners_{timestamp}.xlsx"
            
                with result_area.container():
                    st.dataframe(beneficial_owners)
                    st.download_button(
                        "下載完整查詢結果 (Excel)",
                        data=output,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )


            else:
                st.error("程式執行完畢，但沒有回傳資料，請檢查日誌。")

        except Exception as e:
            st.error(f"執行背景程式時發生錯誤: {e}")
            # 發生錯誤還是要把已經 print 的東西秀出來
            log_area.code(output_buffer.getvalue(), language="text", line_numbers=True)