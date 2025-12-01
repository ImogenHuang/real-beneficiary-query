# -*- coding: utf-8 -*-
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# 1. 設定必要的參數
def get_driver():
    options = Options()
    
    # 這是論壇文章中證實有效的必要參數
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # 2. 指定 Chromium 瀏覽器和驅動程式的絕對路徑
    options.binary_location = "/usr/bin/chromium"
    service = Service(executable_path="/usr/bin/chromedriver") 
    
    # 3. 啟動 Driver
    try:
        # 如果 /usr/bin/chromedriver 不存在，這裡會報錯
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        # 如果 /usr/bin/chromium 不存在，這裡會報錯
        st.error(f"無法啟動 ChromeDriver。這可能是因為 packages.txt 安裝失敗。錯誤訊息: {e}")
        st.stop()
        

# 測試執行
st.title("Selenium 最終測試")
if st.button("啟動爬蟲"):
    try:
        with st.spinner("正在啟動瀏覽器..."):
            driver = get_driver()
            driver.get("https://www.google.com")
            st.success(f"成功開啟網頁，標題為: {driver.title}")
            driver.quit()
    except Exception as e:
        # 如果 get_driver() 內部失敗，錯誤會在這邊被捕捉
        st.error(f"應用程式執行失敗: {e}")
