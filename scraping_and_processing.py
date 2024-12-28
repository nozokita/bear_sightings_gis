# scraping_and_processing.py

import os
import requests
import json
import re
import pdfplumber
import pandas as pd
import yaml
import numpy as np

# ====== Selenium + ChromeDriverの設定 ====== #
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scrape_pdfs():
    """
    静岡県・山梨県・神奈川県のPDFを取得してローカルに保存。
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # ヘッドレスモード
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    driver = webdriver.Chrome(options=options)

    # === 山梨県 ===
    yamanashi_url = "https://www.pref.yamanashi.jp/shizen/kuma2.html"
    driver.get(yamanashi_url)
    try:
        wait = WebDriverWait(driver, 10)
        link = wait.until(
            EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "令和6年度（2024年度）ツキノワグマ出没・目撃情報"))
        )
        pdf_url = link.get_attribute("href")
        pdf_path = "kuma_r6_yamanashi.pdf"
        r = requests.get(pdf_url)
        with open(pdf_path, 'wb') as f:
            f.write(r.content)
        print("[山梨県] PDF保存:", pdf_path)
    except Exception as e:
        print("山梨県のPDF取得エラー:", e)

    # === 静岡県 ===
    shizuoka_url = "https://www.pref.shizuoka.jp/kurashikankyo/shizenkankyo/wild/1017680.html"
    driver.get(shizuoka_url)
    try:
        wait = WebDriverWait(driver, 10)
        link = wait.until(
            EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "【NEW】クマ出没マップ"))
        )
        pdf_url = link.get_attribute("href")
        pdf_path = "kuma_r6_shizuoka.pdf"
        r = requests.get(pdf_url)
        with open(pdf_path, 'wb') as f:
            f.write(r.content)
        print("[静岡県] PDF保存:", pdf_path)
    except Exception as e:
        print("静岡県のPDF取得エラー:", e)

    # === 神奈川県 ===
    kanagawa_url = "https://www.pref.kanagawa.jp/docs/t4i/cnt/f3813/"
    driver.get(kanagawa_url)
    try:
        wait = WebDriverWait(driver, 10)
        link = wait.until(
            EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "ツキノワグマの目撃等情報を更新しました"))
        )
        pdf_url = link.get_attribute("href")
        pdf_path = "kuma_r6_kanagawa.pdf"
        r = requests.get(pdf_url)
        with open(pdf_path, 'wb') as f:
            f.write(r.content)
        print("[神奈川県] PDF保存:", pdf_path)
    except Exception as e:
        print("神奈川県のPDF取得エラー:", e)

    driver.quit()

def parse_kanagawa_pdf():
    """
    神奈川県PDF(kuma_r6_kanagawa.pdf)を解析し、bear_sightings_kanagawa.json を生成
    """
    pdf_path = "kuma_r6_kanagawa.pdf"
    json_path = "bear_sightings_kanagawa.json"

    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_lines = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_lines.extend(text.split('\n'))

        column_titles = ["月日", "時間", "頭数", "状況", "場所等", "区分", "目撃・痕跡", "その他"]
        date_pattern = re.compile(r'(1[0-2]|[1-9])月(\d{1,2})日')

        sightings = []
        for line in all_lines:
            # タイトル・不要行除外
            if (not line.strip() or
                '《目撃・痕跡・その他》' in line or
                all(title in line for title in column_titles)):
                continue

            m = date_pattern.search(line)
            if not m:
                continue

            date_str = m.group(0)
            after_date_part = line[m.end():].strip()
            parts = after_date_part.split()

            if len(parts) >= 5:
                time = parts[0]
                number_of_bears = parts[1]
                status = parts[2]
                area_type = parts[-2]
                observation_type = parts[-1]

                # 場所情報
                location_parts = parts[3:-2]
                location = " ".join(location_parts) if location_parts else ""

                sightings.append({
                    "date": date_str,
                    "time": time,
                    "number_of_bears": number_of_bears,
                    "status": status,
                    "location": location,
                    "area_type": area_type,
                    "observation_type": observation_type
                })

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sightings, f, ensure_ascii=False, indent=2)
        print("[神奈川] JSON保存:", json_path)

    except Exception as e:
        print("[神奈川] PDF解析エラー:", e)

def parse_yamanashi_pdf():
    """
    山梨県PDF(kuma_r6_yamanashi.pdf)を解析し、bear_sightings_yamanashi.json を生成
    """
    pdf_path = "kuma_r6_yamanashi.pdf"
    json_path = "bear_sightings_yamanashi.json"

    try:
        sightings = []
        with pdfplumber.open(pdf_path) as pdf:
            all_lines = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_lines.extend(text.split('\n'))

        date_pattern = re.compile(r'(\d{4}/\d{1,2}/\d{1,2})')
        city_pattern = re.compile(r'(.+?[市町村])(.*)')
        location_pattern = re.compile(r'([^晴雨曇]{2,}?)((?:晴|雨|曇|霧|雪|地内).*)')

        for line in all_lines:
            if not line.strip() or '《目撃・痕跡・その他》' in line:
                continue

            m = date_pattern.search(line)
            if not m:
                continue

            date_str = m.group(1)
            after_date_part = line[m.end():].strip()

            # "頃" の直後に空白がない場合は補完
            after_date_part = re.sub(r'頃(?!\s)', '頃 ', after_date_part)
            parts = after_date_part.split()

            if len(parts) < 3:
                continue

            time = parts[0]

            # 市町村＋地名
            remaining_text = ' '.join(parts[1:])
            city_match = city_pattern.match(remaining_text)
            if city_match:
                city = city_match.group(1)
                location_full = city_match.group(2).strip()
                
                loc_match = location_pattern.match(location_full)
                if loc_match:
                    location = loc_match.group(1).strip()
                else:
                    # 天候情報等が見つからない場合は最初の単語を場所とする例
                    location = location_full.split()[0] if location_full.split() else location_full
            else:
                # フォーマット外の場合 (暫定処理)
                city = parts[1]
                location = parts[2]

            # 熊の頭数 (例として、後半パーツに数字があれば最後を利用)
            remaining = parts[3:]
            nums = [re.sub(r'\D', '', x) for x in remaining if re.search(r'\d+', x)]
            bear_count = nums[-1] if nums else "不明"

            sightings.append({
                "date": date_str,
                "time": time,
                "city": city,
                "location": location,
                "bear_count": bear_count
            })

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sightings, f, ensure_ascii=False, indent=2)
        print("[山梨] JSON保存:", json_path)

    except Exception as e:
        print("[山梨] PDF解析エラー:", e)

def parse_shizuoka_pdf():
    """
    静岡県PDF(kuma_r6_shizuoka.pdf)を解析し、bear_sightings_shizuoka.json を生成。
    この例ではサンプルとして座標抽出領域を crop() している形になっていますが、
    実際のPDFレイアウトに応じて修正してください。
    """
    pdf_path = "kuma_r6_shizuoka.pdf"
    json_path = "bear_sightings_shizuoka.json"

    def extract_text_from_regions(pdf_path, regions):
        extracted_texts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for region in regions:
                    crop = page.crop(region)
                    text = crop.extract_text()
                    if text:
                        extracted_texts.append(text)
        return extracted_texts

    def parse_bear_sightings(texts):
        sightings = []
        for text in texts:
            lines = text.split('\n')
            for line in lines:
                match = re.match(r'^(\d+(?:-\d+)?)\s+(\d+月\d+日)\s+(\S+)\s+(.+)$', line.strip())
                if match:
                    sightings.append({
                        "number": match.group(1),
                        "date": match.group(2),
                        "municipality": match.group(3),
                        "location": match.group(4).strip()
                    })
        return sightings

    try:
        # PDF 内の特定座標範囲を切り出す例 (実際はPDFに合わせて調整)
        regions = [
            (30, 40, 120, 540),   # 仮の領域1
            (125, 100, 200, 470)  # 仮の領域2
        ]
        texts = extract_text_from_regions(pdf_path, regions)
        sightings = parse_bear_sightings(texts)

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sightings, f, ensure_ascii=False, indent=2)
        print("[静岡] JSON保存:", json_path)

    except Exception as e:
        print("[静岡] PDF解析エラー:", e)

# ========== 日付文字列の変換 ==========
def convert_date(date_str: str) -> pd.Timestamp:
    if not date_str:
        return pd.NaT
    # 例: "2024/6/4"
    if '/' in date_str:
        return pd.to_datetime(date_str, errors='coerce')
    # 例: "6月19日" （年が書かれていないので2024を仮定）
    if '月' in date_str and '日' in date_str:
        current_year = 2024
        date_str_mod = f"{current_year}年{date_str}"
        date_str_mod = date_str_mod.replace('年', '/').replace('月', '/').replace('日', '')
        return pd.to_datetime(date_str_mod, errors='coerce')
    return pd.NaT

def parse_kanagawa_location(loc_str: str):
    if not loc_str:
        return pd.NA, pd.NA
    boundary_words = ["市", "町", "村"]
    idx = None
    boundary_char = None
    for bw in boundary_words:
        i = loc_str.find(bw)
        if i != -1:
            if idx is None or i < idx:
                idx = i
                boundary_char = bw
    if idx is not None:
        city_str = loc_str[: idx + len(boundary_char)]
        loc_str_remain = loc_str[idx + len(boundary_char) :].strip()
        return city_str, loc_str_remain
    else:
        return pd.NA, loc_str

def combine_json_data():
    """
    3つのJSONファイルを読み込み、共通DataFrame化 → CSV出力
    """
    # --- 神奈川 ---
    try:
        with open('bear_sightings_kanagawa.json', 'r', encoding='utf-8') as f:
            kanagawa_data = json.load(f)
    except:
        kanagawa_data = []
    # --- 静岡 ---
    try:
        with open('bear_sightings_shizuoka.json', 'r', encoding='utf-8') as f:
            shizuoka_data = json.load(f)
    except:
        shizuoka_data = []
    # --- 山梨 ---
    try:
        with open('bear_sightings_yamanashi.json', 'r', encoding='utf-8') as f:
            yamanashi_data = json.load(f)
    except:
        yamanashi_data = []

    normalized_data = []

    # ==== 神奈川データ ====
    for rec in kanagawa_data:
        raw_location = rec.get('location')
        city_kanagawa, loc_kanagawa = parse_kanagawa_location(raw_location)
        normalized_data.append({
            'prefecture': '神奈川県',
            'date': rec.get('date'),
            'city': city_kanagawa,
            'location': loc_kanagawa
        })

    # ==== 静岡データ ====
    for rec in shizuoka_data:
        normalized_data.append({
            'prefecture': '静岡県',
            'date': rec.get('date'),
            'city': rec.get('municipality'),
            'location': rec.get('location')
        })

    # ==== 山梨データ ====
    for rec in yamanashi_data:
        normalized_data.append({
            'prefecture': '山梨県',
            'date': rec.get('date'),
            'city': rec.get('city'),
            'location': rec.get('location')
        })

    df = pd.DataFrame(normalized_data, columns=['prefecture', 'date', 'city', 'location'])
    df['date'] = df['date'].apply(convert_date)
    df.sort_values('date', inplace=True)
    df.reset_index(drop=True, inplace=True)

    output_csv = 'bear_sightings_combined.csv'
    df.to_csv(output_csv, index=False, encoding='utf-8')
    print("== combine_json_data ==")
    print(df.head())
    print(df.tail())
    print("CSV出力:", output_csv)

# ------ 郡名マッピング (例) ------ #
CITY_GUN_MAP = {
    # (都道府県, 市町村名) : "郡名＋市町村名"

    # --- 神奈川県 ---
    ("神奈川県", "葉山町"): "三浦郡葉山町",
    ("神奈川県", "二宮町"): "中郡二宮町",
    ("神奈川県", "大磯町"): "中郡大磯町",
    ("神奈川県", "愛川町"): "愛甲郡愛川町",
    ("神奈川県", "清川村"): "愛甲郡清川村",
    ("神奈川県", "中井町"): "足柄上郡中井町",
    ("神奈川県", "大井町"): "足柄上郡大井町",
    ("神奈川県", "山北町"): "足柄上郡山北町",
    ("神奈川県", "松田町"): "足柄上郡松田町",
    ("神奈川県", "開成町"): "足柄上郡開成町",
    ("神奈川県", "湯河原町"): "足柄下郡湯河原町",
    ("神奈川県", "真鶴町"): "足柄下郡真鶴町",
    ("神奈川県", "箱根町"): "足柄下郡箱根町",
    ("神奈川県", "寒川町"): "高座郡寒川町",

    # --- 山梨県 ---
    ("山梨県", "昭和町"): "中巨摩郡昭和町",
    ("山梨県", "丹波山村"): "北都留郡丹波山村",
    ("山梨県", "小菅村"): "北都留郡小菅村",
    ("山梨県", "南部町"): "南巨摩郡南部町",
    ("山梨県", "富士川町"): "南巨摩郡富士川町",
    ("山梨県", "早川町"): "南巨摩郡早川町",
    ("山梨県", "身延町"): "南巨摩郡身延町",
    ("山梨県", "富士河口湖町"): "南都留郡富士河口湖町",
    ("山梨県", "山中湖村"): "南都留郡山中湖村",
    ("山梨県", "忍野村"): "南都留郡忍野村",
    ("山梨県", "西桂町"): "南都留郡西桂町",
    ("山梨県", "道志村"): "南都留郡道志村",
    ("山梨県", "鳴沢村"): "南都留郡鳴沢村",
    ("山梨県", "市川三郷町"): "西八代郡市川三郷町",

    # --- 静岡県 ---
    ("静岡県", "森町"): "周智郡森町",
    ("静岡県", "吉田町"): "榛原郡吉田町",
    ("静岡県", "川根本町"): "榛原郡川根本町",
    ("静岡県", "函南町"): "田方郡函南町",
    ("静岡県", "南伊豆町"): "賀茂郡南伊豆町",
    ("静岡県", "東伊豆町"): "賀茂郡東伊豆町",
    ("静岡県", "松崎町"): "賀茂郡松崎町",
    ("静岡県", "河津町"): "賀茂郡河津町",
    ("静岡県", "西伊豆町"): "賀茂郡西伊豆町",
    ("静岡県", "小山町"): "駿東郡小山町",
    ("静岡県", "清水町"): "駿東郡清水町",
    ("静岡県", "長泉町"): "駿東郡長泉町",
}

def fix_city_name(pref: str, city: str) -> str:
    if pd.isna(city):
        return ""
    return CITY_GUN_MAP.get((pref, city), city)

def clean_address(city: str, location: str) -> tuple[str, str]:
    """
    city, location の文字列をクレンジングして新しい (city, location) を返す。
    
    例:
    - 「緑区」を city に合体
    - 「・」が入っていれば手前だけ採用
    - 括弧内の文字列を除去
    - 不要な文字列を除去
    """
    # NaN→空文字
    city = '' if pd.isna(city) else str(city)
    location = '' if pd.isna(location) else str(location)

    # 市名の重複を削除 (あれば)
    if city and location.startswith(city):
        location = location[len(city):].strip()

    # 「緑区」が location にあれば city に合体
    if "緑区" in location and "緑区" not in city:
        city += "緑区"
        location = location.replace("緑区", "")

    # 「・」で分割 → 先頭だけ
    if "・" in location:
        location = location.split("・")[0]

    # 正規表現で括弧内を削除（全角＆半角）
    location = re.sub(r'（.*?）', '', location)  # 全角括弧
    location = re.sub(r'\(.*?\)', '', location)  # 半角括弧

    # 不要単語を置換
    remove_words = ["付近", "峠", "地区", "地内", "山地", "徳間", "鯨野", "釜の口", "諏訪内", "大道", "佐野区"]
    for word in remove_words:
        location = location.replace(word, '')

    return city.strip(), location.strip()

def load_geo_cache(yaml_path='areas_with_coords.yml') -> dict:
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def lookup_coords(pref: str, city: str, area: str, geo_dict: dict) -> dict:
    """
    geo_dict[pref][city][area] を検索、なければ "以下に掲載がない場合" → それでもなければNone
    """
    try:
        return geo_dict[pref][city][area]
    except KeyError:
        try:
            return geo_dict[pref][city]["以下に掲載がない場合"]
        except KeyError:
            return {"longitude": None, "latitude": None}

def add_coords_from_cache(df: pd.DataFrame, geo_dict: dict) -> pd.DataFrame:
    longitudes = []
    latitudes = []
    for _, row in df.iterrows():
        pref = row['prefecture']
        city_raw = row['city']
        loc_raw = row['location']
        city_cleaned, loc_cleaned = clean_address(city_raw, loc_raw)
        city_fixed = fix_city_name(pref, city_cleaned)
        coords = lookup_coords(pref, city_fixed, loc_cleaned, geo_dict)
        longitudes.append(coords['longitude'])
        latitudes.append(coords['latitude'])
    df['longitude'] = longitudes
    df['latitude'] = latitudes
    return df

def main():
    # 1) PDFをダウンロード
    scrape_pdfs()

    # 2) 各県のPDF解析
    parse_kanagawa_pdf()
    parse_yamanashi_pdf()
    parse_shizuoka_pdf()

    # 3) JSONを統合 → CSV(bear_sightings_combined.csv)
    combine_json_data()

    # 4) CSVに座標付与 → bear_sightings_with_coords.csv
    df = pd.read_csv('bear_sightings_combined.csv', encoding='utf-8')
    try:
        geo_cache = load_geo_cache('areas_with_coords.yml')  # 事前に用意した YAML
        df = add_coords_from_cache(df, geo_cache)
    except Exception as e:
        print("YAMLロード or 座標付与エラー:", e)
        # 座標付与に失敗しても続行する例
        df['longitude'] = np.nan
        df['latitude'] = np.nan

    out_csv = 'bear_sightings_with_coords.csv'
    df.to_csv(out_csv, index=False, encoding='utf-8')
    print("最終CSV保存:", out_csv)

if __name__ == "__main__":
    main()
