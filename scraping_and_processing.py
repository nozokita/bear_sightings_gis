# scraping_and_processing.py

"""
熊目撃情報を自動でスクレイピング、PDF解析、データ整形し、
最終的に住所→座標を付与したCSVを出力するメイン処理コード。
"""

import os
import requests
import json
import re
import pdfplumber
import pandas as pd
import yaml
import numpy as np

# ====== Selenium + ChromeDriverを使ったスクレイピング関連 ====== #
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scrape_pdfs():
    """
    静岡県・山梨県・神奈川県の各公式サイトにアクセスし、
    クマ出没情報が書かれたPDFをダウンロードしてローカルに保存する処理。

    1. WebDriver（ChromeDriver）を起動（ヘッドレスモード）
    2. 各県のサイトにアクセス
    3. PDFリンクを見つける(PARTIAL_LINK_TEXTなどで検索)
    4. リンク先のPDFファイルを取得し、"kuma_r6_◯◯.pdf"という名前で保存
    5. エラー時はログ出力
    6. 最後にブラウザを閉じる
    """

    # Chromeのオプション設定（ヘッドレス：画面表示しないモード）
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    # WebDriverのインスタンス生成
    driver = webdriver.Chrome(options=options)

    # ========== 山梨県のPDF ========== #
    # 県公式サイトを開く
    yamanashi_url = "https://www.pref.yamanashi.jp/shizen/kuma2.html"
    driver.get(yamanashi_url)
    try:
        # ページが完全に読み込まれるまで最大10秒待機
        wait = WebDriverWait(driver, 10)
        # テキストの一部に「令和6年度（2024年度）ツキノワグマ出没・目撃情報」という文字列を含むリンクを探す
        link = wait.until(
            EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "令和6年度（2024年度）ツキノワグマ出没・目撃情報"))
        )
        # リンクのhref属性（実際のPDFファイルのURL）を取得
        pdf_url = link.get_attribute("href")
        # ダウンロード先ファイル名を指定
        pdf_path = "kuma_r6_yamanashi.pdf"

        # requestsでPDFをGETリクエストし、バイナリとして保存する
        r = requests.get(pdf_url)
        with open(pdf_path, 'wb') as f:
            f.write(r.content)

        print("[山梨県] PDF保存:", pdf_path)

    except Exception as e:
        print("山梨県のPDF取得エラー:", e)

    # ========== 静岡県のPDF ========== #
    shizuoka_url = "https://www.pref.shizuoka.jp/kurashikankyo/shizenkankyo/wild/1017680.html"
    driver.get(shizuoka_url)
    try:
        wait = WebDriverWait(driver, 10)
        # 「【NEW】クマ出没マップ」という文字を含むリンクを検索
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

    # ========== 神奈川県のPDF ========== #
    kanagawa_url = "https://www.pref.kanagawa.jp/docs/t4i/cnt/f3813/"
    driver.get(kanagawa_url)
    try:
        wait = WebDriverWait(driver, 10)
        # 「ツキノワグマの目撃等情報を更新しました」という文字を含むリンクを検索
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

    # 最後にドライバを終了させる
    driver.quit()


def parse_kanagawa_pdf():
    """
    神奈川県のPDF (kuma_r6_kanagawa.pdf) を解析し、
    「日付」「時間」「頭数」「状況」「場所等」などの情報を抽出して
    JSONファイル (bear_sightings_kanagawa.json) として保存する。

    ※ pdfplumberでPDFからテキスト抽出
    ※ 正規表現を使って「○月○日」形式の日付などを拾う
    ※ データの形式は適宜調整
    """
    pdf_path = "kuma_r6_kanagawa.pdf"
    json_path = "bear_sightings_kanagawa.json"

    try:
        # pdfplumberでPDFを開く
        with pdfplumber.open(pdf_path) as pdf:
            all_lines = []
            # 各ページを順番に処理
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # 改行ごとに分割してリストにためる
                    all_lines.extend(text.split('\n'))

        # PDFの表に含まれていそうなカラムタイトル（神奈川の想定）
        column_titles = ["月日", "時間", "頭数", "状況", "場所等", "区分", "目撃・痕跡", "その他"]
        # 「○月○日」を検出するための正規表現 (1〜9月 or 10〜12月)
        date_pattern = re.compile(r'(1[0-2]|[1-9])月(\d{1,2})日')

        sightings = []
        # テキスト行を順番に見て、必要情報を抽出
        for line in all_lines:
            # 不要な行やカラムタイトル行を除外する
            if (not line.strip() or
                '《目撃・痕跡・その他》' in line or
                # column_titles内の全ての単語を含む場合、タイトル行とみなす
                all(title in line for title in column_titles)):
                continue

            # 「○月○日」のパターンを探す
            m = date_pattern.search(line)
            if not m:
                continue

            # date_strには例えば「6月19日」のような文字列が入る
            date_str = m.group(0)

            # 日付の文字列の末尾までで一旦切り、その後の部分を解析する
            after_date_part = line[m.end():].strip()
            # スペース区切りで分割
            parts = after_date_part.split()

            # 最低限、分割結果が5要素以上あるかチェック
            if len(parts) >= 5:
                time = parts[0]               # 例: 14:00
                number_of_bears = parts[1]    # 例: 1頭
                status = parts[2]            # 例: 徘徊
                area_type = parts[-2]        # 例: ○○区分
                observation_type = parts[-1] # 例: 目撃 or 痕跡など

                # 場所については3番目〜(末尾-2)までを結合
                location_parts = parts[3:-2]
                location = " ".join(location_parts) if location_parts else ""

                # 辞書としてまとめる
                sightings.append({
                    "date": date_str,
                    "time": time,
                    "number_of_bears": number_of_bears,
                    "status": status,
                    "location": location,
                    "area_type": area_type,
                    "observation_type": observation_type
                })

        # JSONファイルに書き出す
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sightings, f, ensure_ascii=False, indent=2)

        print("[神奈川] JSON保存:", json_path)

    except Exception as e:
        print("[神奈川] PDF解析エラー:", e)


def parse_yamanashi_pdf():
    """
    山梨県のPDF (kuma_r6_yamanashi.pdf) を解析し、
    「日付（2024/6/4 など）」「時間」「市町村」「場所」「熊の頭数」を抽出して
    JSONファイル (bear_sightings_yamanashi.json) として保存する。

    PDF内の日付は「2024/7/12」のような文字列が含まれていると想定。
    """
    pdf_path = "kuma_r6_yamanashi.pdf"
    json_path = "bear_sightings_yamanashi.json"

    try:
        sightings = []

        # pdfplumberを用いて、PDF全ページからテキストを取得
        with pdfplumber.open(pdf_path) as pdf:
            all_lines = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_lines.extend(text.split('\n'))

        # 日付パターン: 年4桁/1-2桁/月1-2桁/日の形式 (例: 2024/6/20)
        date_pattern = re.compile(r'(\d{4}/\d{1,2}/\d{1,2})')

        # 市町村を抽出するための例示的な正規表現
        city_pattern = re.compile(r'(.+?[市町村])(.*)')
        # 天候情報等を取り除く例示的なパターン
        location_pattern = re.compile(r'([^晴雨曇]{2,}?)((?:晴|雨|曇|霧|雪|地内).*)')

        for line in all_lines:
            # 空行や不要行はスキップ
            if not line.strip() or '《目撃・痕跡・その他》' in line:
                continue

            # 行に日付パターンがあるか確認
            m = date_pattern.search(line)
            if not m:
                continue

            # 例: "2024/6/4"
            date_str = m.group(1)

            # 日付の後ろの部分を抽出
            after_date_part = line[m.end():].strip()

            # "頃"の後ろにスペースが無い場合、ある程度整形する（例: "14:00頃近く" → "14:00頃 近く"）
            after_date_part = re.sub(r'頃(?!\s)', '頃 ', after_date_part)

            # スペース区切り
            parts = after_date_part.split()
            if len(parts) < 3:
                continue

            # parts[0]に時間が入る想定 (例: "14:00頃")
            time = parts[0]

            # 残りの文字列は市町村＋地名を含むと想定
            remaining_text = ' '.join(parts[1:])
            city_match = city_pattern.match(remaining_text)

            if city_match:
                # 例: city="甲府市", location_full="○○地区..."
                city = city_match.group(1)
                location_full = city_match.group(2).strip()

                # さらに location_full から天候などの文字を分割
                loc_match = location_pattern.match(location_full)
                if loc_match:
                    location = loc_match.group(1).strip()
                else:
                    # 該当がなければ先頭単語だけを場所とする暫定ロジック
                    location = location_full.split()[0] if location_full.split() else location_full
            else:
                # city_patternに合致しない場合の暫定処理
                city = parts[1]
                location = parts[2]

            # 熊の頭数を探す。parts[3:] の中に数字があれば最後のものを利用する想定
            remaining = parts[3:]
            nums = [re.sub(r'\D', '', x) for x in remaining if re.search(r'\d+', x)]
            bear_count = nums[-1] if nums else "不明"

            # 取得情報をリストに格納
            sightings.append({
                "date": date_str,
                "time": time,
                "city": city,
                "location": location,
                "bear_count": bear_count
            })

        # JSON出力
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sightings, f, ensure_ascii=False, indent=2)

        print("[山梨] JSON保存:", json_path)

    except Exception as e:
        print("[山梨] PDF解析エラー:", e)


def parse_shizuoka_pdf():
    """
    静岡県のPDF (kuma_r6_shizuoka.pdf) を解析し、
    目撃情報を JSONファイル (bear_sightings_shizuoka.json) として保存する。

    ここではPDFから必要なエリアを crop()（切り出し）してテキストを抽出する例を示しているが、
    実際のPDFレイアウトに合わせて変更が必要。
    """
    pdf_path = "kuma_r6_shizuoka.pdf"
    json_path = "bear_sightings_shizuoka.json"

    def extract_text_from_regions(pdf_path, regions):
        """
        pdfplumberの crop() を用いて、指定した領域だけを抽出してテキスト化する関数。
        regions は (x0, top, x1, bottom) のタプルを要素としたリスト。
        """
        extracted_texts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for region in regions:
                    # 領域を切り出し
                    crop = page.crop(region)
                    text = crop.extract_text()
                    if text:
                        extracted_texts.append(text)
        return extracted_texts

    def parse_bear_sightings(texts):
        """
        切り出したテキスト群から、日付や地点を正規表現などで解析し、
        熊目撃情報をリストで返す。
        """
        sightings = []
        for text in texts:
            lines = text.split('\n')
            for line in lines:
                # 例： "1  6月19日  静岡市  ○○地区" のような行を想定
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
        # 解析したいページ領域の例 (左上x, 上からの距離, 右下x, 下からの距離)
        # 実際のPDFレイアウトによって数値調整が必要
        regions = [
            (30, 40, 120, 540),   # 仮の領域1
            (125, 100, 200, 470)  # 仮の領域2
        ]
        texts = extract_text_from_regions(pdf_path, regions)
        sightings = parse_bear_sightings(texts)

        # JSON出力
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sightings, f, ensure_ascii=False, indent=2)

        print("[静岡] JSON保存:", json_path)

    except Exception as e:
        print("[静岡] PDF解析エラー:", e)


# ========== 日付文字列の変換用 関数 ========== #
def convert_date(date_str: str) -> pd.Timestamp:
    """
    文字列で与えられる日付を pd.Timestamp に変換する。
    例: "2024/6/4" → 2024-06-04 (Timestamp)
        "6月19日" → (2024年と仮定して) 2024-06-19
    変換できない場合は pd.NaT（Not a Time）を返す。
    """
    if not date_str:
        return pd.NaT

    # '/'が含まれる -> 2024/6/4 のような形式
    if '/' in date_str:
        return pd.to_datetime(date_str, errors='coerce')

    # '○月○日'が含まれる -> 年が書かれていないので仮に2024年とする
    if '月' in date_str and '日' in date_str:
        current_year = 2024
        # "6月19日" -> "2024年6月19日" -> "2024/6/19"
        date_str_mod = f"{current_year}年{date_str}"
        date_str_mod = date_str_mod.replace('年', '/').replace('月', '/').replace('日', '')
        return pd.to_datetime(date_str_mod, errors='coerce')

    # どれにも該当しなければ NaT
    return pd.NaT


def parse_kanagawa_location(loc_str: str):
    """
    神奈川データの「location」文字列から市区町村名と残りの住所を分割するための例。
    「市」「町」「村」のいずれかが出てくる位置を探し、
    そこまでを市区町村、それ以降を残りの場所とする単純ロジック。
    """
    if not loc_str:
        return pd.NA, pd.NA

    boundary_words = ["市", "町", "村"]
    idx = None
    boundary_char = None

    for bw in boundary_words:
        i = loc_str.find(bw)
        if i != -1:
            # 最初に見つかった位置を優先
            if idx is None or i < idx:
                idx = i
                boundary_char = bw

    if idx is not None:
        # loc_str[: idx + len(boundary_char)] -> ex) "横浜市"
        city_str = loc_str[: idx + len(boundary_char)]
        # 残り部分 -> ex) "緑区...XXX"
        loc_str_remain = loc_str[idx + len(boundary_char) :].strip()
        return city_str, loc_str_remain
    else:
        # "市"などの文字が見つからない場合は全てlocationに入れる
        return pd.NA, loc_str


def combine_json_data():
    """
    3県（神奈川・静岡・山梨）のJSONファイルを読み込み、
    共通フォーマットのDataFrameに整形して
    bear_sightings_combined.csv を出力する。

    1. JSONロード（ファイルが無い場合は空リスト）
    2. 各県ごとに必要項目をピックアップ
    3. date カラムを convert_date() でTimestamp化
    4. ソートしてCSVに保存
    """
    # --- 神奈川 JSONロード --- #
    try:
        with open('bear_sightings_kanagawa.json', 'r', encoding='utf-8') as f:
            kanagawa_data = json.load(f)
    except:
        kanagawa_data = []

    # --- 静岡 JSONロード --- #
    try:
        with open('bear_sightings_shizuoka.json', 'r', encoding='utf-8') as f:
            shizuoka_data = json.load(f)
    except:
        shizuoka_data = []

    # --- 山梨 JSONロード --- #
    try:
        with open('bear_sightings_yamanashi.json', 'r', encoding='utf-8') as f:
            yamanashi_data = json.load(f)
    except:
        yamanashi_data = []

    normalized_data = []

    # ==== 神奈川データを整形 ====
    for rec in kanagawa_data:
        raw_location = rec.get('location')
        # 神奈川特有の「市町村名・残りの住所」の分割関数を適用
        city_kanagawa, loc_kanagawa = parse_kanagawa_location(raw_location)

        normalized_data.append({
            'prefecture': '神奈川県',    # 固定
            'date': rec.get('date'),    # "6月19日"など
            'city': city_kanagawa,
            'location': loc_kanagawa
        })

    # ==== 静岡データを整形 ====
    for rec in shizuoka_data:
        normalized_data.append({
            'prefecture': '静岡県',
            'date': rec.get('date'),             # "6月19日"など
            'city': rec.get('municipality'),     # PDFの取り方に準拠
            'location': rec.get('location')
        })

    # ==== 山梨データを整形 ====
    for rec in yamanashi_data:
        normalized_data.append({
            'prefecture': '山梨県',
            'date': rec.get('date'),             # "2024/6/19"など
            'city': rec.get('city'),
            'location': rec.get('location')
        })

    # DataFrame化
    df = pd.DataFrame(normalized_data, columns=['prefecture', 'date', 'city', 'location'])

    # 日付をTimestampに変換
    df['date'] = df['date'].apply(convert_date)

    # 日付順にソート
    df.sort_values('date', inplace=True)
    df.reset_index(drop=True, inplace=True)

    # CSV書き出し
    output_csv = 'bear_sightings_combined.csv'
    df.to_csv(output_csv, index=False, encoding='utf-8')
    print("== combine_json_data ==")
    print(df.head())
    print(df.tail())
    print("CSV出力:", output_csv)


# ------ 郡名マッピング (例) ------
# 例：("神奈川県", "葉山町") → "三浦郡葉山町"
#  町名が郡に属している場合などに、正式名称に置き換えるマッピング
CITY_GUN_MAP = {
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
    """
    市町村名が郡に属している場合など、
    CITY_GUN_MAPで定義されていれば置き換える。
    """
    if pd.isna(city):
        return ""
    return CITY_GUN_MAP.get((pref, city), city)


def clean_address(city: str, location: str) -> tuple[str, str]:
    """
    city と location をクレンジングして、より正確な市町村名＋場所に分割し直す。
    主な処理:
      - city が location を重複して持っていれば削除
      - 「緑区」が location に含まれていれば city に付加
      - 「・」があれば手前だけ取得
      - 括弧内（全角＆半角）を除去
      - 不要単語（付近、峠、地区、地内...など）を除去
    """
    # NaNなら空文字に置き換え
    city = '' if pd.isna(city) else str(city)
    location = '' if pd.isna(location) else str(location)

    # city名が重複してlocationに含まれる場合、重複部分を削除
    if city and location.startswith(city):
        location = location[len(city):].strip()

    # locationに「緑区」があり、かつcityに「緑区」が無い場合はcityに付加
    if "緑区" in location and "緑区" not in city:
        city += "緑区"
        location = location.replace("緑区", "")

    # 「・」で分割して先頭だけ使用
    if "・" in location:
        location = location.split("・")[0]

    # 全角・半角括弧内の文字列を削除
    location = re.sub(r'（.*?）', '', location)  # 全角括弧
    location = re.sub(r'\(.*?\)', '', location)  # 半角括弧

    # 特定の単語を削除
    remove_words = ["付近", "峠", "地区", "地内", "山地", "徳間", "鯨野", "釜の口", "諏訪内", "大道", "佐野区"]
    for word in remove_words:
        location = location.replace(word, '')

    return city.strip(), location.strip()


def load_geo_cache(yaml_path='areas_with_coords.yml') -> dict:
    """
    areas_with_coords.yml をロードして辞書型にする関数。
    例: geo_dict["静岡県"]["静岡市"]["葵区"] = { "longitude": ..., "latitude": ... }
    """
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def lookup_coords(pref: str, city: str, area: str, geo_dict: dict) -> dict:
    """
    YAML で定義している geo_dict から、都道府県(pref)、市町村(city)、エリア(area)をキーにして
    {"longitude": float, "latitude": float} を返す。

    - 完全一致で見つからなければ "以下に掲載がない場合" を探す
    - それでもなければ None を返す
    """
    try:
        return geo_dict[pref][city][area]
    except KeyError:
        try:
            return geo_dict[pref][city]["以下に掲載がない場合"]
        except KeyError:
            return {"longitude": None, "latitude": None}


def add_coords_from_cache(df: pd.DataFrame, geo_dict: dict) -> pd.DataFrame:
    """
    DataFrameの各行に対して、
      1) city, locationのクレンジング
      2) fix_city_nameで郡名を補完
      3) lookup_coordsで座標を取得
    し、longitude, latitude の2列を追加する。
    """
    longitudes = []
    latitudes = []

    for _, row in df.iterrows():
        pref = row['prefecture']
        city_raw = row['city']
        loc_raw = row['location']

        # 1) 住所のクレンジング
        city_cleaned, loc_cleaned = clean_address(city_raw, loc_raw)

        # 2) 郡名がある場合の補正
        city_fixed = fix_city_name(pref, city_cleaned)

        # 3) YAML辞書から座標を引く
        coords = lookup_coords(pref, city_fixed, loc_cleaned, geo_dict)
        longitudes.append(coords['longitude'])
        latitudes.append(coords['latitude'])

    df['longitude'] = longitudes
    df['latitude'] = latitudes
    return df


def main():
    """
    メイン処理:
      1) PDFを3県ぶんスクレイピングして取得
      2) 取得したPDFから各県ごとのJSONを作成
      3) JSONを統合して CSV (bear_sightings_combined.csv) を生成
      4) CSVに対して YAML (areas_with_coords.yml) を使い座標付与 → 最終CSV (bear_sightings_with_coords.csv)
    """

    # 1) PDFをダウンロード
    scrape_pdfs()

    # 2) 各県のPDFを解析してJSON作成
    parse_kanagawa_pdf()
    parse_yamanashi_pdf()
    parse_shizuoka_pdf()

    # 3) JSONを統合し、CSV出力
    combine_json_data()

    # 4) CSVに座標付与 → bear_sightings_with_coords.csv
    df = pd.read_csv('bear_sightings_combined.csv', encoding='utf-8')
    try:
        # 事前に用意したYAMLファイルをロード
        geo_cache = load_geo_cache('areas_with_coords.yml')
        # DataFrameに座標情報を追加
        df = add_coords_from_cache(df, geo_cache)
    except Exception as e:
        print("YAMLロード or 座標付与エラー:", e)
        # 座標付与に失敗しても処理を続行する場合
        df['longitude'] = np.nan
        df['latitude'] = np.nan

    out_csv = 'bear_sightings_with_coords.csv'
    df.to_csv(out_csv, index=False, encoding='utf-8')
    print("最終CSV保存:", out_csv)


if __name__ == "__main__":
    # このファイルが直接実行された場合、メイン処理を呼び出す
    main()

