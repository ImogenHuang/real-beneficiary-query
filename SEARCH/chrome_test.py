# -*- coding: utf-8 -*-
"""
Created on Mon Dec  1 16:44:57 2025

@author: user
"""

import os
import streamlit as st

st.write("### 環境診斷")
st.write("Chromium 位置:", os.path.exists("/usr/bin/chromium"))
st.write("ChromeDriver 位置:", os.path.exists("/usr/bin/chromedriver"))

# 列出可用的驅動程式
if os.path.exists("/usr/bin/"):
    files = os.listdir("/usr/bin/")
    chrome_files = [f for f in files if 'chrom' in f.lower()]
    st.write("找到的 Chrome 相關檔案:", chrome_files)