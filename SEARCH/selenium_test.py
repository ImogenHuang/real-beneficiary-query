# -*- coding: utf-8 -*-
"""
Created on Mon Dec  1 16:31:22 2025

@author: user
"""

import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import shutil # <<< 確保有匯入 shutil

def get_driver():
    # 1. 初始化 options
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # --- 關鍵修改：使用 shutil.which() 查找實際路徑 ---
    
    # 查找 Chromium 瀏覽器路徑
    chromium_path = shutil.which("chromium")
    
    # 查找 Chromedriver 驅動程式路徑 (會先找 'chromedriver')
    chromedriver_path = shutil.which("chromedriver") 
    
    # 備用查找：如果找不到 chromedriver，則試著找 chromium-driver
    if not chromedriver_path:
        chromedriver_path = shutil.which("chromium-driver")
    
    # 2. 檢查路徑是否成功找到
    if not chromium_path or not chromedriver_path:
        st.error("系統錯誤：無法在 PATH 中找到 Chromium 或 Chromedriver 執行檔。")
        st.stop()
    
    # 3. 指定路徑給 Selenium
    options.binary_location = chromium_path
    service = Service(executable_path=chromedriver_path) 
    
    # 4. 啟動 Driver
    try:
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        raise Exception(f"啟動 ChromeDriver 失敗，請檢查權限及版本是否匹配。Driver 路徑: {chromedriver_path}. 錯誤訊息: {e}")


# 測試執行
st.title("Selenium 測試 (shutil 查找版)")
if st.button("啟動爬蟲"):
    try:
        with st.spinner("正在啟動瀏覽器..."):
            driver = get_driver()
            driver.get("https://www.google.com")
            st.success(f"成功開啟網頁，標題為: {driver.title}")
            driver.quit()
    except Exception as e:
        st.error(f"執行錯誤: {e}")