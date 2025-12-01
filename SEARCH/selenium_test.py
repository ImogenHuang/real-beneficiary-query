# -*- coding: utf-8 -*-
"""
Created on Mon Dec  1 16:31:22 2025

@author: user
"""

import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os # <<< 確保匯入 os 模組

# Streamlit Cloud (Debian) 環境下，Chromium 檔案的標準絕對路徑
CHROMIUM_PATH = "/usr/bin/chromium"
CHROMEDRIVER_PATH = "/usr/bin/chromedriver"

def get_driver():
    # 1. 初始化 options
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # --- 關鍵修改：強制使用絕對路徑並檢查檔案存在性 ---
    
    # 檢查檔案是否確實存在，如果 packages.txt 失敗，這裡會報錯
    if not os.path.exists(CHROMIUM_PATH) or not os.path.exists(CHROMEDRIVER_PATH):
        st.error("致命錯誤：Chromium/Chromedriver 執行檔不存在。")
        st.warning("這表示 packages.txt 中的依賴安裝失敗。請確認 packages.txt 內容並重新部署。")
        st.write(f"預期 Chromium 路徑: {CHROMIUM_PATH}")
        st.write(f"預期 Chromedriver 路徑: {CHROMEDRIVER_PATH}")
        st.stop()
    
    # 2. 指定路徑給 Selenium
    options.binary_location = CHROMIUM_PATH
    service = Service(executable_path=CHROMEDRIVER_PATH) 
    
    # 3. 啟動 Driver
    try:
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        raise Exception(f"啟動 ChromeDriver 失敗。錯誤訊息: {e}")


# 測試執行
st.title("Selenium 測試 (絕對路徑版)")
# 測試執行
if st.button("啟動爬蟲"):
    try:
        with st.spinner("正在啟動瀏覽器..."):
            driver = get_driver()
            driver.get("https://www.google.com")
            st.success(f"成功開啟網頁，標題為: {driver.title}")
            driver.quit()
    except Exception as e:
        st.error(f"執行錯誤: {e}")

