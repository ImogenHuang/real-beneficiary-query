# -*- coding: utf-8 -*-
"""
Created on Thu Nov 27 11:28:11 2025

@author: user
"""

import requests
import pandas as pd
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import os
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# ========== 全域設定 ==========
COMPANY_SEARCH_URL = "https://opendata.vip/data/company?keyword={keyword}"
GCIS_DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"
REQ_TIMEOUT = 15
SLEEP_BETWEEN_CALLS = 0.4
HEADERS = {
    "User-Agent": "TW-Compliance-Recursive-Agent/1.0",
    "Accept": "application/json, text/xml;q=0.9"
}
DEFAULT_STOCK_PAR_VALUE = 10.0

# 快取字典
_cache_company_no: Dict[str, Optional[str]] = {}
_cache_directors_by_no: Dict[str, List[Dict]] = {}
_cache_company_info: Dict[str, Optional[Dict]] = {}

# 載入上市櫃公司名單
try:
    #df_listed = pd.read_csv("D:/.spyder-py3備份/SEARCH/data/concat_all.csv")
    # 取得目前程式檔案所在目錄
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 往上一層找 data 資料夾
    data_dir = os.path.join(os.path.dirname(current_dir), 'data')
    concat_file = os.path.join(data_dir, 'concat_all.csv')
    df_listed = pd.read_csv(concat_file, encoding='utf-8-sig')
    LISTED_BAN_SET = set(df_listed['統編'].astype(str).str.strip())
    LISTED_NAME_SET = set(df_listed['公司名稱'].astype(str).str.strip())
    print(f"[INFO] 已載入 {len(LISTED_BAN_SET)} 家上市櫃公司資料")
except Exception as e:
    print(f"[WARNING] 無法載入上市櫃公司名單: {e}")
    LISTED_BAN_SET = set()
    LISTED_NAME_SET = set()


# ========== 工具函數 ==========
def _to_float(val: Optional[str]) -> Optional[float]:
    """將字串數字（可能含逗點、中文單位）轉成 float"""
    if not val:
        return None
    try:
        clean = re.sub(r"[^\d\.\-]", "", str(val))
        return float(clean) if clean else None
    except Exception:
        return None


# ========== Selenium 爬蟲類別 ==========
class FindbizSeleniumScraper:
    """使用 Selenium 爬取商工登記資料"""
    
    def __init__(self, headless: bool = True, driver_path: Optional[str] = None):
        self.base_url = "https://findbiz.nat.gov.tw/fts/query/QueryBar/queryInit.do"
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--lang=zh-TW')
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        #service = Service(driver_path) if driver_path else Service()
        options.binary_location="/user/bin/chromium"
        service = Service("/user/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)

    def get_company_data(self, ban_no: str, company_name: Optional[str] = None) -> Optional[Dict]:
        """查詢公司資料並解析詳細頁"""
        try:
            self.driver.get(self.base_url)
            self.wait.until(EC.presence_of_element_located((By.ID, "qryCond")))
            
            search_input = self.driver.find_element(By.ID, "qryCond")
            search_input.clear()
            search_input.send_keys(ban_no)
            
            search_button = self.wait.until(EC.element_to_be_clickable((By.ID, "qryBtn")))
            search_button.click()
            
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "panel-heading")))
            
            if company_name:
                links = self.driver.find_elements(By.CSS_SELECTOR, "a.hover")
                target = None
                for link in links:
                    if link.text.strip() == company_name.strip():
                        target = link
                        break
                if not target and links:
                    target = links[0]
                if not target:
                    return None
                target.click()
            else:
                link = self.driver.find_element(By.CSS_SELECTOR, "a.hover")
                link.click()
            
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "table-striped")))
            page_source = self.driver.page_source
            return self._parse_page(page_source, ban_no)
            
        except Exception as e:
            print(f"[ERROR] 查詢失敗 ({ban_no}): {e}")
            return None
        finally:
            time.sleep(0.3)

    def _parse_page(self, html: str, ban_no: str) -> Optional[Dict]:
        """解析詳細頁 HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        data = {
            '統一編號': ban_no,
            '公司名稱': None,
            '登記現況': None,
            '代表人': None,
            '公司所在地': None,
            '資本總額': None,
            '實收資本額': None,
            '每股金額': None,
            '已發行股份總數': None,
            '所營事業資料':[],
            
        }
        
        table = soup.find('table', class_='table-striped') or soup.find('table', class_='table')
        if not table:
            return None
        def parse_business_items(text: str):
            pattern = r"([A-Z]\d{6})\s*([^\dA-Z]+)"
            matches = re.findall(pattern, text)
            return [{"業別代碼": c, "業別名稱": n.strip()} for c, n in matches]
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            key = cells[0].get_text(strip=True)
            value = ' '.join(cells[1].get_text(strip=True).split())
            
            if key == '統一編號':
                data['統一編號'] = value.split()[0].split('訂閱')[0]
            elif key == '公司名稱':
                value = value.split('Google搜尋')[0].split('國際貿易署')[0]
                data['公司名稱'] = value.strip()
            elif key == '登記現況':
                data['登記現況'] = value.split('「')[0].strip()
            elif key == '代表人姓名':
                data['代表人'] = value
            elif key == '公司所在地':
                clean_value = re.sub(r"電子地圖同地址公司家數[:：]?\s*\d+", "", value).strip()
                data['公司所在地'] = clean_value    
            elif key == '資本總額(元)':
                data['資本總額'] = value
            elif key == '實收資本額(元)':
                data['實收資本額'] = value
            elif key == '每股金額(元)':
                data['每股金額'] = value
            elif key == '已發行股份總數(股)':
                data['已發行股份總數'] = value
            elif key == '所營事業資料':
                data['所營事業資料'] = parse_business_items(value)   
        print(data)
        return data

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ========== 核心查詢函數 ==========
def get_business_no_by_name(company_name_or_no: str) -> Optional[str]:
    """依公司名稱或統編查詢統一編號"""
    input_key = company_name_or_no.strip()
    if not input_key:
        return None
    
    # 檢查是否為統編（純數字且長度 7-8 位）
    if input_key.isdigit() and 7 <= len(input_key) <= 8:
        business_no = input_key.zfill(8)
        print(f"[INFO] 輸入為統編: {business_no}")
        _cache_company_no[input_key] = business_no
        return business_no
    
    # 檢查快取
    if input_key in _cache_company_no:
        return _cache_company_no[input_key]
    
    # 以公司名稱查詢
    url = COMPANY_SEARCH_URL.format(keyword=requests.utils.quote(input_key))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
        if resp.status_code != 200:
            _cache_company_no[input_key] = None
            return None
        
        data = resp.json()
        if not data or "output" not in data or not data["output"]:
            _cache_company_no[input_key] = None
            return None
        
        df = pd.DataFrame(data["output"])
        exact = df[df["Company_Name"].str.strip() == input_key]
        target_row = exact.iloc[0] if len(exact) > 0 else df.iloc[0]
        
        raw_no = str(target_row["Business_Accounting_NO"]).strip()
        business_no = raw_no.zfill(8) if raw_no.isdigit() else None
        
        _cache_company_no[input_key] = business_no
        time.sleep(SLEEP_BETWEEN_CALLS)
        return business_no
        
    except Exception as e:
        print(f"[WARNING] 查詢失敗: {e}")
        _cache_company_no[input_key] = None
        return None
    



# --- 金融機構判斷（常見代碼） ---
financial_codes = {
    "H301011",  # 證券商
    "H304011",  # 證券投資顧問業
    "H305011",  # 證券經紀商  
    "H401011",  # 期貨商
    "H403011",  # 投信投顧
    "H105011",  # 信託業
 
}
GOV_KEYWORDS = ["公所", "部", "局", "院", "委員會", "國營", "行政院"]

# --- 消極非金融機構（例如：一般投資業） ---
passive_non_financial_codes = {
    "H201010",  # 一般投資業（你的例子）
    "H202010",  # 創業投資業
}
def classify_company_by_business_items(business_items):
    # --- 1. 政府機關 ---
    for item in business_items:
        name = item.get("業別名稱", "")
        if any(k in name for k in GOV_KEYWORDS):
            return "政府機關"

    # --- 2. 金融機構 ---
    for item in business_items:
        code = item.get("業別代碼", "")
        if code in financial_codes:
            return "金融機構"

    # --- 3. 消極非金融機構 ---
    for item in business_items:
        code = item.get("業別代碼", "")
        if code in passive_non_financial_codes:
            return "消極非金融機構"

    # --- 4. 都不是 → 積極非金融機構 ---
    return "積極非金融機構"




def fetch_company_info_findbiz(
    business_no: str,
    company_name: Optional[str] = None,
    scraper: Optional[FindbizSeleniumScraper] = None,
    use_cache: bool = True
) -> Optional[Dict]:
    """以 FindBiz 抓公司資訊並回傳統一結構"""
    global _cache_company_info
    
    if use_cache and business_no in _cache_company_info:
        return _cache_company_info[business_no]
    
    owns_scraper = False
    if scraper is None:
        scraper = FindbizSeleniumScraper(headless=True)
        owns_scraper = True
    
    try:
        raw = scraper.get_company_data(business_no, company_name)
        if not raw:
            result = None
        else:
            capital_total = _to_float(raw.get('資本總額'))
            paid_in = _to_float(raw.get('實收資本額'))
            par_val = _to_float(raw.get('每股金額')) or DEFAULT_STOCK_PAR_VALUE
            issued_cnt = _to_float(raw.get('已發行股份總數'))
            
            if issued_cnt is None and paid_in and par_val and par_val > 0:
                issued_cnt = paid_in / par_val
            items = raw.get("所營事業資料")
            if not isinstance(items, list):
                items = []
            result = {
                #"統一編號": raw.get('統一編號') or business_no,
                "統一編號": business_no,
                "公司名稱": raw.get('公司名稱'),
                "登記現況": raw.get('登記現況'),
                "代表人": raw.get('代表人'),
                "公司所在地": raw.get('公司所在地'),
                "資本總額": capital_total,
                "實收資本額": paid_in,
                "每股金額": par_val,
                "已發行股數": issued_cnt,
                "所營事業資料": raw.get("所營事業資料"),
                "CRS分類":classify_company_by_business_items(items)
                
            }
        
        if use_cache:
            _cache_company_info[business_no] = result
        return result
        
    finally:
        if owns_scraper:
            scraper.close()
        time.sleep(SLEEP_BETWEEN_CALLS)


def fetch_directors_by_business_no(business_no: str) -> List[Dict]:
    """查詢董監事資料（含股數與出資額）"""
    if business_no in _cache_directors_by_no:
        return _cache_directors_by_no[business_no]
    
    records: List[Dict] = []
    business_no_formats = [business_no, business_no.lstrip('0')]
    
    # 先試 JSON
    for bn_format in business_no_formats:
        params_json = {"$format": "json", "$filter": f"Business_Accounting_NO eq {bn_format}"}
        try:
            rj = requests.get(GCIS_DIRECTOR_API, params=params_json, headers=HEADERS, timeout=REQ_TIMEOUT)
            if rj and rj.status_code == 200:
                payload = rj.json()
                if isinstance(payload, list) and len(payload) > 0:
                    for row in payload:
                        share_raw = str(row.get("Person_Shareholding", "")).strip()
                        invest_raw = str(row.get("Person_Investment_Amount", "")).strip()
                        
                        records.append({
                            "職稱": str(row.get("Person_Position_Name", "")).strip(),
                            "姓名": str(row.get("Person_Name", "")).strip(),
                            "所代表法人": str(row.get("Juristic_Person_Name", "")).strip(),
                            "所持有股數": _to_float(share_raw),
                            "出資額": _to_float(invest_raw),
                            "統一編號": str(row.get("Business_Accounting_NO", "")).strip()
                        })
                if records:
                    break
        except Exception:
            pass
    
    time.sleep(SLEEP_BETWEEN_CALLS)
    _cache_directors_by_no[business_no] = records
    return records


def is_listed_company(business_no: str, company_name: str) -> bool:
    """判斷是否為上市櫃公司"""

    
    #return result
    return (business_no in LISTED_BAN_SET) or (company_name in LISTED_NAME_SET)


def find_chairman_or_representative(company_name: str) -> Optional[str]:
    """查詢董事長或代表人姓名"""
    bn = get_business_no_by_name(company_name)
    if not bn:
        return None
    
    directors = fetch_directors_by_business_no(bn)
    
    # 優先找董事長
    for row in directors:
        title = (row.get("職稱") or "").strip()
        if "董事長" in title:
            name = (row.get("姓名") or "").strip()
            return name if name else None
    
    # 次選代表人
    for row in directors:
        title = (row.get("職稱") or "").strip()
        if "代表人" in title:
            name = (row.get("姓名") or "").strip()
            return name if name else None
    
    return None


def is_natural_person(name: str) -> bool:
    """判斷是否為自然人"""
    if not name or pd.isna(name):
        return False
    name = str(name).strip()
    exclude_keywords = ["有限公司", "股份有限公司", "公司", "缺額"]
    return not any(kw in name for kw in exclude_keywords)


# ========== 遞迴查詢主函數 ==========
def crawl_director_chain(seed_company_name: str, max_depth: int = 5) -> pd.DataFrame:
    """遞迴查詢董監事鏈"""
    visited_names = set()
    stack = [(seed_company_name.strip(), 0)]
    rows = []
    
    while stack:
        company_name, depth = stack.pop()
        
        if depth > max_depth:
            continue
        if not company_name or company_name in visited_names:
            continue
        
        visited_names.add(company_name)
        
        business_no = get_business_no_by_name(company_name)
        print(f"[Level {depth}] 查詢: {company_name} -> 統編: {business_no}")
        
        if not business_no:
            rows.append({
                "level": depth,
                "from_company": company_name,
                "from_business_no": None,
                "職稱": "",
                "姓名": "",
                "所代表法人": "",
                "to_business_no": None,
                "所持有股數": None,
                "出資額": None,
                "是法人代表": False,
                "占比": None,
                "計算基準": None,
                "備註": "非台灣公司或查無統編"
            })
            continue
        
        company_info = fetch_company_info_findbiz(business_no)
        if not company_info:
            rows.append({
                "level": depth,
                "from_company": company_name,
                "from_business_no": business_no,
                "職稱": "",
                "姓名": "",
                "所代表法人": "",
                "to_business_no": None,
                "所持有股數": None,
                "出資額": None,
                "是法人代表": False,
                "占比": None,
                "計算基準": None,
                "備註": "查無公司資料"
            })
            continue
        
        total_shares = company_info.get("已發行股數")
        total_capital = company_info.get("資本總額")
        par_value = company_info.get("每股金額", DEFAULT_STOCK_PAR_VALUE)
        
        # 決定計算模式
        mode = None
        denominator = None
        if total_shares and total_shares > 0:
            mode = "shares"
            denominator = total_shares
        elif total_capital and total_capital > 0:
            mode = "capital"
            denominator = total_capital
        
        directors = fetch_directors_by_business_no(business_no)
        if not directors:
            rows.append({
                "level": depth,
                "from_company": company_name,
                "from_business_no": business_no,
                "職稱": "",
                "姓名": "",
                "所代表法人": "",
                "to_business_no": None,
                "所持有股數": None,
                "出資額": None,
                "是法人代表": False,
                "占比": None,
                "計算基準": mode,
                "備註": "查無董監事資料"
            })
            continue
        
        # 整併法人持股（避免重複計算）
        juristic_holdings_shares: Dict[str, float] = {}
        juristic_holdings_amount: Dict[str, float] = {}
        
        for d in directors:
            repco = (d.get("所代表法人") or "").strip()
            shares_num = d.get("所持有股數")
            invest_num = d.get("出資額")
            
            if not repco:
                continue
            
            if mode == "shares" and shares_num:
                juristic_holdings_shares[repco] = max(juristic_holdings_shares.get(repco, 0.0), shares_num)
            elif mode == "capital":
                amt = invest_num if invest_num else (shares_num * par_value if shares_num and par_value else None)
                if amt:
                    juristic_holdings_amount[repco] = max(juristic_holdings_amount.get(repco, 0.0), amt)
        
        # 處理每位董監事
        for d in directors:
            title = d.get("職稱", "")
            person = d.get("姓名", "")
            repco = (d.get("所代表法人") or "").strip()
            shares_num = d.get("所持有股數")
            invest_num = d.get("出資額")
            is_juristic_rep = bool(repco)
            
            # 計算占比
            ratio = None
            if mode == "shares" and denominator:
                numerator = juristic_holdings_shares.get(repco) if is_juristic_rep else shares_num
                if numerator:
                    ratio = numerator / denominator
            elif mode == "capital" and denominator:
                if is_juristic_rep:
                    numerator = juristic_holdings_amount.get(repco)
                else:
                    numerator = invest_num if invest_num else (shares_num  if shares_num and par_value else None)
                if numerator:
                    ratio = numerator / denominator
            
            to_business_no = None
            remark = ""
            should_recurse = False
            
            if repco:
                to_business_no = get_business_no_by_name(repco)
                
                # 檢查是否為上市櫃公司且持股>50%
                if to_business_no and is_listed_company(to_business_no, repco):
                    if ratio and ratio > 0.5:
                        remark = "上市櫃公司持股>50%，免辨識"
                    else:
                        remark = "上市櫃公司"
                        should_recurse = False
                else:
                    should_recurse = True
            
            rows.append({
                "level": depth,
                "from_company": company_name,
                "from_business_no": business_no,
                "職稱": title,
                "姓名": person,
                "所代表法人": repco,
                "to_business_no": to_business_no,
                "所持有股數": shares_num,
                "出資額": invest_num,
                "是法人代表": is_juristic_rep,
                "占比": ratio,
                "計算基準": mode,
                "備註": remark
            })
            
            # 決定是否遞迴
            if should_recurse and repco and to_business_no:
                stack.append((repco, depth + 1))
        
        time.sleep(SLEEP_BETWEEN_CALLS)
    
    df = pd.DataFrame(rows)
    df = df.sort_values(by=["level", "from_company", "職稱", "姓名"], kind="stable").reset_index(drop=True)
    return df


# ========== 持股分析函數 ==========
def build_ownership_paths(df: pd.DataFrame) -> List[Dict]:
    """建立完整持股路徑"""
    paths = []
    df_sorted = df.sort_values(by=["level", "from_company"]).reset_index(drop=True)
    
    for idx, row in df_sorted.iterrows():
        name = row["姓名"]
        ratio = row["占比"]
        current_level = row["level"]
        repco = row["所代表法人"]
        
        # 只處理自然人葉節點
        if not is_natural_person(name):
            continue
        if pd.isna(ratio):
            continue
        if repco:  # 有代表法人表示不是葉節點
            continue
        
        # 往上回溯
        path_ratios = [ratio]
        path_companies = [row["from_company"]]
        current_company = row["from_company"]
        
        for level in range(current_level - 1, -1, -1):
            prev_rows = df_sorted[
                (df_sorted["level"] == level) &
                (df_sorted["所代表法人"].str.strip() == current_company)
            ]
            if not prev_rows.empty:
                prev_row = prev_rows.iloc[0]
                prev_ratio = prev_row["占比"]
                if not pd.isna(prev_ratio):
                    path_ratios.append(prev_ratio)
                    path_companies.append(prev_row["from_company"])
                    current_company = prev_row["from_company"]
                else:
                    break
            else:
                break
        
        path_ratios.reverse()
        path_companies.reverse()
        paths.append({
            "name": name,
            "ratios": path_ratios,
            "path": path_companies
        })
    
    return paths


def calc_final_natural_person_shares(df: pd.DataFrame, threshold: float = 0.25) -> Dict[str, float]:
    """計算最終自然人持股占比"""
    paths = build_ownership_paths(df)
    person_shares: Dict[str, float] = {}
    holding_process_log = []  # 新增紀錄清單
    print("\n=== 持股計算過程 ===")
    for path_info in paths:
        name = path_info["name"]
        ratios = path_info["ratios"]
        companies = path_info["path"]
        
        final_ratio = 1.0
        for ratio in ratios:
            final_ratio *= ratio
        
        person_shares[name] = person_shares.get(name, 0) + final_ratio
        
        path_str = " → ".join(companies)
        calc_str = " × ".join([f"{r:.2%}" for r in ratios])
        
        log_text = f"{name}: {path_str}\n  計算: {calc_str} = {final_ratio:.2%}"
        print(log_text)
      
        holding_process_log.append(log_text)  # 加入紀錄
    result = {k: v for k, v in person_shares.items() if v > threshold}
    return result, holding_process_log 


def find_senior_management(df: pd.DataFrame) -> List[Dict]:
    """找出高階管理人"""
    senior_titles = ["董事長", "總經理", "監察人"]
    level0 = df[df["level"] == 0]
    senior = []
    
    for _, row in level0.iterrows():
        title = str(row["職稱"])
        if any(t in title for t in senior_titles):
            senior.append({
                "姓名": row["姓名"],
                "職稱": title
            })
    
    return senior



def fallback_final_beneficial_owner(df: pd.DataFrame, threshold: float = 0.25) -> List[Dict]:
    level0 = df[df["level"] == 0]
    corp_rows = level0[level0["是法人代表"] & level0["所代表法人"].astype(str).str.strip().ne("")]
    corp_names = [c for c in corp_rows["所代表法人"].dropna().unique() if str(c).strip()]
    results = []

    # 先檢查是否有上市櫃公司持股>50%，有的話直接免辨識
    for corp in corp_names:
        rep_rows = corp_rows[corp_rows["所代表法人"] == corp]
        if rep_rows.empty:
            continue
        ratio = rep_rows.iloc[0]["占比"]
        bn = get_business_no_by_name(corp)
        if bn and is_listed_company(bn, corp) and ratio and ratio > 0.5:
            # 只要有一間上市櫃公司持股>50%，直接免辨識
            return [{
                "類型": "上市櫃公司持股>50%免辨識",
                "法人": corp,
                "統編": bn,
                "占比": ratio
            }]

    # 沒有上市櫃公司持股>50%，才 fallback 到法人代表人
    for corp in corp_names:
        rep_rows = corp_rows[corp_rows["所代表法人"] == corp]
        if rep_rows.empty:
            continue
        ratio = rep_rows.iloc[0]["占比"]
        bn = get_business_no_by_name(corp)
        if pd.notna(ratio) and ratio > threshold:
            chairman = find_chairman_or_representative(corp)
            results.append({
                "類型": "法人持股>25%",
                "法人": corp,
                "代表人": chairman or "查無代表人",
                "占比": ratio,
                "統編": bn
            })
    if results:
        return results

    # 最後才 fallback 到高階管理人
    senior = find_senior_management(df)
    if senior:
        for s in senior:
            results.append({
                "類型": "高階管理人",
                "姓名": s["姓名"],
                "職稱": s["職稱"]
            })
    return results



def check_total_ratio(df):
    total_ratio = df["占比"].dropna().sum()
    if total_ratio < 0.75:  # 例如低於75%就警示
        return f"⚠️ 董監事持股加總僅 {total_ratio:.2%}，可能有未揭露股東"
    return None

# =============================================================================
# def main():
#     print("="*60)
#     print("實質受益人辨識系統")
#     print("="*60)
#     
#     seed = input("\n請輸入公司名稱或統編：").strip()
#     if not seed:
#         print("輸入不可為空")
#         return
#     
#     # Step 1: 查詢統編
#     print("\n[Step 1] 查詢統編...")
#     business_no = get_business_no_by_name(seed)
#     if not business_no:
#         print("❌ 查無統編，無法繼續")
#         return
#     print(f"✓ 統編: {business_no}")
#     
#     # Step 2: 查詢公司基本資料與登記現況
#     print("\n[Step 2] 查詢公司基本資料...")
#     company_info = fetch_company_info_findbiz(business_no)
#     if not company_info:
#         print("❌ 查無公司基本資料")
#         return
#     
#     company_name = company_info.get("公司名稱", seed)
#     status = company_info.get("登記現況", "").strip()
#     
#     print(f"✓ 公司名稱: {company_name}")
#     print(f"✓ 登記現況: {status}")
#     
#     if status != "核准設立":
#         print(f"⚠️  公司登記現況非「核准設立」，請營業員進行查核")
#         return
#     
#     # Step 3: 判斷是否為上市櫃公司
#     print("\n[Step 3] 判斷是否為上市櫃公司...")
#     if is_listed_company(business_no, company_name):
#         print("✓ 此公司為上市櫃公司，免辨識")
#         return
#     print("✓ 非上市櫃公司，需進行實質受益人辨識")
#     
#     # Step 4: 遞迴查詢董監事
#     print("\n[Step 4] 開始遞迴查詢董監事...")
#     result_df = crawl_director_chain(company_name, max_depth=5)
#     
#     if result_df.empty:
#         print("❌ 無法取得董監事資料")
#         return
#     
#     print(f"✓ 共查詢到 {len(result_df)} 筆董監事記錄")
#     
#     # 顯示查詢結果摘要
#     print("\n=== 查詢結果摘要 ===")
#     for level in sorted(result_df["level"].unique()):
#         level_data = result_df[result_df["level"] == level]
#         companies = level_data["from_company"].unique()
#         print(f"第 {level} 層: {len(companies)} 家公司, {len(level_data)} 筆記錄")
#     
#     # Step 5: 計算自然人持股
#     print("\n[Step 5] 計算自然人持股占比...")
#     final_shares,holding_process_log = calc_final_natural_person_shares(result_df, threshold=0.25)
#     
#     print("\n" + "="*60)
#     print("=== 實質受益人辨識結果 ===")
#     print("="*60)
#     
#     if final_shares:
#         print("\n✓ 持股 ≥ 25% 的自然人:")
#         for name, ratio in sorted(final_shares.items(), key=lambda x: x[1], reverse=True):
#             print(f"  • {name}: {ratio:.2%}")
#     else:
#         print("\n⚠️  無自然人持股達 25%")
#         
#         # Step 6: Fallback 規則
#         print("\n[Step 6] 執行 Fallback 規則...")
#         fallback_results = fallback_final_beneficial_owner(result_df, threshold=0.25)
#         
#         if fallback_results:
#             
#             # 新增判斷：如果是上市櫃公司持股>50%免辨識
#             if fallback_results[0].get("類型") == "上市櫃公司持股>50%免辨識":
#                 corp = fallback_results[0].get("法人")
#                 bn = fallback_results[0].get("統編")
#                 ratio = fallback_results[0].get("占比", 0)
#                 print(f"\n✓ 由於「{corp}」（統編：{bn}）為上市櫃公司，且持股比例達 {ratio:.2%}，依規定免辨識實質受益人。")
#             else:
#                 print("\n以下人員可視為實質受益人，但需與客戶確認，並進行文件徵提")
#                 for item in fallback_results:
#                     if item.get("類型") == "法人持股>25%":
#                         corp = item.get("法人")
#                         rep = item.get("代表人")
#                         ratio = item.get("占比", 0)
#                         bn = item.get("統編")
#                         print(f"\n  法人: {corp}")
#                         print(f"  統編: {bn or '查無'}")
#                         print(f"  持股: {ratio:.2%}")
#                         print(f"  代表人: {rep}")
#                         
#                     elif item.get("類型") == "高階管理人":
#                         name = item.get("姓名")
#                         title = item.get("職稱")
#                         print(f"\n  {title}: {name}")
#         else:
#             print("\n⚠️  無法辨識實質受益人，建議:")
#             print("  1. 請客戶提供聲明書")
#             print("  2. 由營業員進一步查核")
#     
#     # 新增持股揭露比例檢查
#     ratio_warning = check_total_ratio(result_df)
#     warnings = []
#     if ratio_warning:
#         
#         warnings.append(ratio_warning)
#         warnings.append("持股揭露比例不足，請與客戶徵提對應的文件")
#     
#         print("\n=== 警示訊息 ===")
#         print(ratio_warning)
#         print("持股揭露比例不足，請與客戶徵提對應的文件")
# 
#     
#     
#     # 匯出結果
#     print("\n" + "="*60)
#     output_file = f"實質受益人查詢結果_{business_no}.xlsx"
#     try:
#         with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
#             # 原本的完整董監事資料
#             result_df.to_excel(writer, sheet_name='完整查詢結果', index=False)
#     
#             # 原本的最終結果摘要
#             if final_shares:
#                 summary_df = pd.DataFrame([
#                     {"姓名": name, "持股占比": f"{ratio:.2%}", "類型": "自然人"}
#                     for name, ratio in final_shares.items()
#                 ])
#             else:
#                 fallback_results = fallback_final_beneficial_owner(result_df, threshold=0.25)
#                 summary_data = []
#                 for item in fallback_results:
#                     if item.get("類型") == "法人持股>25%":
#                         summary_data.append({
#                             "姓名": item.get("代表人"),
#                             "持股占比": f"{item.get('占比', 0):.2%}",
#                             "類型": f"法人代表 ({item.get('法人')})"
#                         })
#                     elif item.get("類型") == "高階管理人":
#                         summary_data.append({
#                             "姓名": item.get("姓名"),
#                             "持股占比": "-",
#                             "類型": item.get("職稱")
#                         })
#                 summary_df = pd.DataFrame(summary_data) if summary_data else pd.DataFrame()
#     
#             if not summary_df.empty:
#                 summary_df.to_excel(writer, sheet_name='實質受益人', index=False)
#     
#             # ✅ 新增：公司基本資料
#             company_df = pd.DataFrame(list(company_info.items()), columns=['欄位', '內容'])
#             company_df.to_excel(writer, sheet_name='公司基本資料', index=False)
#     
#             # ✅ 新增：持股計算過程（從 calc_final_natural_person_shares 回傳的 holding_process_log）
#             holding_df = pd.DataFrame({'持股計算過程': holding_process_log})
#             holding_df.to_excel(writer, sheet_name='持股計算過程', index=False)
#     
#             # ✅ 新增：警示報告（從 check_total_ratio 或其他檢查收集的 warnings）
#             if warnings:
#                 warning_df = pd.DataFrame({'警示': warnings})
#                 warning_df.to_excel(writer, sheet_name='警示報告', index=False)
#     
#         print(f"✓ 結果已匯出至: {output_file}")
#     except Exception as e:
#         print(f"⚠️ 匯出失敗: {e}")
#     
#     print("="*60)
#     print("查詢完成")
#     print("="*60)
# 
# 
# 
# if __name__ == "__main__":
#     main()
# =============================================================================

def run_query(tax_id: str):
    """
    根據統編查詢實質受益人，回傳結構化資料給 Streamlit
    """
    print("="*60)
    print(f"開始查詢統編：{tax_id}")
    print("="*60)

    # Step 1: 查詢公司基本資料
    company_info = fetch_company_info_findbiz(tax_id)
    if not company_info:
        print("❌ 查無公司基本資料")
        return []

    company_name = company_info.get("公司名稱", "")
    status = company_info.get("登記現況", "").strip()
    print(f"✓ 公司名稱: {company_name}")
    print(f"✓ 登記現況: {status}")

    if status != "核准設立":
        print("⚠️ 公司登記現況非「核准設立」，請營業員進行查核")
        #return [{"統編": tax_id, "公司名稱": company_name, "狀態": "非核准設立"}]
        
        # 建公司基本資料表
        company_info_df = pd.DataFrame(list(company_info.items()), columns=['欄位', '內容'])
        
        # 早退概要
        bo_summary = [{
            "類型": "非核准設立",
            "統編": tax_id,
            "公司名稱": company_name
        }]
        return {
           "full_result": pd.DataFrame(),
           "beneficial_owners": bo_summary,
           "company_info": company_info_df,
           "holding_process": pd.DataFrame({'持股計算過程': []}),
           "warnings": pd.DataFrame({'警示': ["登記現況非核准設立，請進一步查核"]})
        }


    # Step 2: 判斷是否上市櫃
    if is_listed_company(tax_id, company_name):
        print("✓ 此公司為上市櫃公司，免辨識")
        #return [{"統編": tax_id, "公司名稱": company_name, "狀態": "免辨識(上市櫃)"}]
        
        company_info_df = pd.DataFrame(list(company_info.items()), columns=['欄位', '內容'])
        bo_summary = [{
            "類型": "免辨識(上市櫃)",
            "統編": tax_id,
            "公司名稱": company_name
        }]
        warnings_df = pd.DataFrame({'警示': ["依規定：免除辨識實質受益人"]})
        
        return {
            "full_result": pd.DataFrame(),          # 免辨識不走遞迴結果
            "beneficial_owners": bo_summary,
            "company_info": company_info_df,
            "holding_process": pd.DataFrame({'持股計算過程': []}),
            "warnings": warnings_df
        }

    # Step 3: 遞迴查詢董監事
    result_df = crawl_director_chain(company_name, max_depth=5)
    if result_df.empty:
        print("❌ 無法取得董監事資料")
        return [{"統編": tax_id, "公司名稱": company_name, "狀態": "查無董監事"}]

    # Step 4: 計算自然人持股
    final_shares, holding_process_log = calc_final_natural_person_shares(result_df, threshold=0.25)

    # Step 5: 整理結果
    output = []
    if final_shares:
        for name, ratio in sorted(final_shares.items(), key=lambda x: x[1], reverse=True):
            output.append({"姓名": name, "持股占比": f"{ratio:.2%}", "類型": "自然人"})
    else:
        fallback_results = fallback_final_beneficial_owner(result_df, threshold=0.25)
        for item in fallback_results:
            output.append(item)
    
    # 主要結果
    beneficial_owners = output  # list of dict
    
    # 公司基本資料
    company_info_df = pd.DataFrame(list(company_info.items()), columns=['欄位', '內容'])
    # 持股計算過程
    holding_process_df = pd.DataFrame({'持股計算過程': holding_process_log})
    # 警示報告
    warnings = []
    ratio_warning = check_total_ratio(result_df)
    if ratio_warning:
        warnings.append(ratio_warning)
        warnings.append("持股揭露比例不足，請與客戶徵提對應的文件")
    warnings_df = pd.DataFrame({'警示': warnings}) if warnings else pd.DataFrame()
    print("查詢完成")
    return {
        "full_result": result_df,
        "beneficial_owners": beneficial_owners,
        "company_info": company_info_df,
        "holding_process": holding_process_df,
        "warnings": warnings_df
    }




def main():
    # CLI 測試用
    seed = input("請輸入公司名稱或統編：").strip()
    if seed:
        run_query(seed)
    else:
        print("輸入不可為空")

if __name__ == "__main__":

   main()




