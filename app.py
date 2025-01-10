# -*- coding: utf-8 -*-
"""
熊の目撃情報 (with_coords.csv) を読み込み、
Streamlit で地図表示(Folium)や統計グラフ(Plotly)を表示するアプリ。
"""

import streamlit as st
import pandas as pd
import yaml
import folium
from folium import plugins
from streamlit_folium import st_folium
from math import sin, cos, sqrt, atan2, radians
from pathlib import Path
from datetime import datetime, timedelta
import plotly.graph_objects as go
import subprocess
import sys

# 座標付きの熊目撃情報が格納されているCSVファイル
CSV_FILE = "bear_sightings_with_coords.csv"
# 駅情報と路線情報のYAMLファイル
YAML_FILE = "lines.yaml"


# ----------------------------------------------
# 距離計算 (ハーバーサインの公式)
# ----------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    """
    2点の緯度経度 (lat1, lon1) と (lat2, lon2) から
    地球上の距離(km)を求める。
    """
    R = 6371.0
    lat1_r = radians(lat1)
    lon1_r = radians(lon1)
    lat2_r = radians(lat2)
    lon2_r = radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = sin(dlat / 2)**2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return distance


def get_lines_near_sighting(sighting_lat, sighting_lon, lines_data, radius_km=5):
    """
    目撃地点 (sighting_lat, sighting_lon) が
    半径 radius_km km以内にある路線名をリストで返す。
    """
    near_lines = []
    for line in lines_data['lines']:
        for st_data in line['stations']:
            dist = haversine(sighting_lat, sighting_lon, st_data['lat'], st_data['lon'])
            if dist <= radius_km:
                near_lines.append(line['name'])
                break  # 同じ路線で重複チェックしないため
    return near_lines


# ----------------------------------------------
# YAMLファイルを読み込む関数
# ----------------------------------------------
def load_lines_from_yaml(file_path: str):
    """
    YAMLファイル (lines.yaml) を読み込み、辞書型を返す。
    想定構造:
    {
      'lines': [
        {
          'name': 'Minobu',
          'stations': [
            {'name': '富士', 'lat': 35.xxx, 'lon': 138.xxx},
            ...
          ]
        },
        ...
      ]
    }
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data


# ----------------------------------------------
# Folium: 路線（ポリライン）を追加
# ----------------------------------------------
def add_railway_lines_to_map(m: folium.Map, lines_data: dict):
    """
    Folium.Mapオブジェクト m に対して、
    lines_data 内の路線（stationsの緯度経度リスト）を
    ポリラインとして描画する。
    """
    for line in lines_data['lines']:
        line_name = line['name']
        station_coords = [(st['lat'], st['lon']) for st in line['stations']]

        folium.PolyLine(
            locations=station_coords,
            color='orange',  # 線の色
            weight=3,     # 線の太さ
            popup=line_name
        ).add_to(m)
    return m


# ----------------------------------------------
# Folium: 駅マーカーを小さめのCircleMarkerで追加
# ----------------------------------------------
def add_stations_to_map(m: folium.Map, lines_data: dict):
    """
    路線データ内の駅を CircleMarker (半径3) で地図に描画。
    """
    for line in lines_data['lines']:
        for st_info in line['stations']:
            folium.CircleMarker(
                location=[st_info['lat'], st_info['lon']],
                radius=3,           # 小さめ
                color='green',      # 枠線色
                fill=True,
                fill_color='green',
                fill_opacity=0.7,
                popup=f"{st_info['name']}駅"
            ).add_to(m)
    return m


# ----------------------------------------------
# CSV読み込み & 前処理
# ----------------------------------------------
def load_and_process_data(file_path: str) -> pd.DataFrame:
    """
    CSVからデータを読み込み、緯度経度や日付が欠損の行を除外して返す。
    """
    df = pd.read_csv(file_path)

    # 緯度、経度がNaNの行を除去
    df = df.dropna(subset=['latitude', 'longitude'])

    # 日付をdatetimeに変換し、変換不可の行を除去
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])

    return df


# ----------------------------------------------
# 熊目撃情報をFolium地図に描画する関数
# ----------------------------------------------
def create_folium_map(df: pd.DataFrame, date_range: tuple) -> folium.Map:
    """
    Foliumを使って地図を生成し、熊目撃情報のマーカーを追加して返す。
    ヒートマップは削除し、MarkerCluster + 過去1週間/過去の2レイヤー表示のみ実装。
    """
    # 地図生成（日本の中央あたり, zoom=8）
    m = folium.Map(
        location=[35.5, 138.5],
        zoom_start=8,
        tiles='CartoDB positron',
        control_scale=True
    )

    # 日付フィルタ
    start_date = pd.Timestamp(date_range[0])
    end_date = pd.Timestamp(date_range[1])
    now_date = pd.Timestamp(datetime.now().date())

    data_min = df['date'].min()
    if start_date < data_min:
        start_date = data_min
    if end_date > now_date:
        end_date = now_date

    mask = (df['date'] >= start_date) & (df['date'] <= end_date)
    filtered_df = df[mask]

    # 過去1週間のフラグ
    now = datetime.now()
    one_week_ago = now - timedelta(days=7)
    filtered_df['is_recent'] = filtered_df['date'] >= one_week_ago

    # MarkerCluster
    marker_cluster = plugins.MarkerCluster(name='クラスター表示')
    marker_cluster.add_to(m)

    # 2つのレイヤー（過去1週間/過去の目撃情報）
    recent_layer = folium.FeatureGroup(name='過去1週間の目撃情報', show=True)
    old_layer = folium.FeatureGroup(name='過去の目撃情報', show=True)

    for _, row in filtered_df.iterrows():
        color = '#dc2626' if row['is_recent'] else '#1d4ed8'
        radius = 8 if row['is_recent'] else 6

        popup_text = f"""
        <div style='font-family: Arial; min-width: 200px;'>
            <h4 style='margin-bottom: 10px; color: {color};'>熊の目撃情報</h4>
            <table>
                <tr><td><strong>日付:</strong></td><td>{row['date'].strftime('%Y-%m-%d')}</td></tr>
                <tr><td><strong>市町村:</strong></td><td>{row['city']}</td></tr>
                <tr><td><strong>地点:</strong></td><td>{row['location']}</td></tr>
                <tr><td><strong>緯度:</strong></td><td>{row['latitude']:.6f}</td></tr>
                <tr><td><strong>経度:</strong></td><td>{row['longitude']:.6f}</td></tr>
            </table>
        </div>
        """

        # CircleMarker
        circle_marker = folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=popup_text,
            tooltip=f"{row['city']} ({row['date'].strftime('%Y-%m-%d')})"
        )

        # Cluster 用の Marker
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=popup_text,
            icon=folium.Icon(
                color='red' if row['is_recent'] else 'blue',
                icon='info-sign'
            )
        ).add_to(marker_cluster)

        # レイヤー振り分け
        if row['is_recent']:
            circle_marker.add_to(recent_layer)
        else:
            circle_marker.add_to(old_layer)

    # レイヤーを地図に追加
    recent_layer.add_to(m)
    old_layer.add_to(m)

    # レイヤーコントロール
    folium.LayerControl(collapsed=False).add_to(m)

    # 全画面表示
    plugins.Fullscreen(
        position='topleft',
        title='全画面表示',
        title_cancel='全画面解除',
        force_separate_button=True
    ).add_to(m)

    # ミニマップ
    minimap = plugins.MiniMap(toggle_display=True, position='bottomright')
    m.add_child(minimap)

    return m


# ----------------------------------------------
# 時系列グラフ（Plotly）
# ----------------------------------------------
def create_time_series_plot(df: pd.DataFrame) -> go.Figure:
    """
    日別の熊目撃件数を折れ線で表示。
    """
    daily_counts = df.groupby('date').size().reset_index(name='count')
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily_counts['date'],
        y=daily_counts['count'],
        mode='lines+markers',
        name='目撃件数'
    ))
    fig.update_layout(
        title='日別熊目撃件数の推移',
        xaxis_title='日付',
        yaxis_title='目撃件数',
        height=400
    )
    return fig


# ----------------------------------------------
# 地域分布グラフ（Plotly）
# ----------------------------------------------
def create_city_bar_chart(df: pd.DataFrame) -> go.Figure:
    """
    市町村別の目撃件数を上位10件だけ棒グラフで表示。
    """
    city_counts = df['city'].value_counts().head(10)
    fig = go.Figure(go.Bar(
        x=city_counts.values,
        y=city_counts.index,
        orientation='h'
    ))
    fig.update_layout(
        title='市町村別熊目撃件数（上位10件）',
        xaxis_title='目撃件数',
        yaxis_title='市町村',
        height=400
    )
    return fig


# ----------------------------------------------
# スクリプト呼び出しで更新する関数 (任意)
# ----------------------------------------------
def update_bear_data():
    """
    scraping_and_processing.py を実行し、熊目撃情報を更新（任意）。
    """
    try:
        progress_text = "データ更新中..."
        progress_bar = st.progress(0)

        result = subprocess.run(
            [sys.executable, "scraping_and_processing.py"],
            capture_output=True,
            text=True
        )

        progress_bar.progress(100)

        if result.returncode == 0:
            st.success("データの更新が完了しました！")
            st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            st.error(f"データの更新に失敗しました。\nError: {result.stderr}")

        progress_bar.empty()

    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")


# ----------------------------------------------
# メイン関数 (Streamlitアプリの入口)
# ----------------------------------------------
def main():
    """
    Streamlitアプリのメイン処理
    1. CSVファイルの読み込み
    2. YAMLファイルの路線読み込み
    3. サイドバーでデータ更新ボタン・日付フィルタ・路線フィルタを表示
    4. Folium地図で熊目撃情報マップを表示
    5. 時系列グラフ・地域分布グラフをタブ表示
    """
    # ページのレイアウトとタイトル設定
    st.set_page_config(layout="wide", page_title="熊出没情報GIS")

    # タイトル
    st.title("熊出没情報GIS")

    # -------------------- サイドバー --------------------
    st.sidebar.header("データフィルター")

    # 情報更新ボタン（任意）
    if st.sidebar.button("🔄 情報を更新", help="最新の熊出没情報を取得します"):
        update_bear_data()

    # 最終更新日時の表示
    if 'last_update' in st.session_state:
        st.sidebar.info(f"最終更新: {st.session_state.last_update}")

    # CSV存在チェック
    csv_path = Path(CSV_FILE)
    if not csv_path.exists():
        st.error(f"データファイルが見つかりません: {CSV_FILE}")
        st.info("「情報を更新」ボタンを押して、データを取得してください。")
        return

    # -------------------- データ読み込み --------------------
    try:
        df = load_and_process_data(CSV_FILE)
    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {str(e)}")
        return

    # -------------------- 路線データ読み込み --------------------
    lines_data = None
    if Path(YAML_FILE).exists():
        try:
            lines_data = load_lines_from_yaml(YAML_FILE)
        except Exception as e:
            st.warning(f"路線データの読み込みに失敗: {e}")
    else:
        st.warning(f"路線データYAMLが見つかりません: {YAML_FILE}")

    # --- 熊目撃データに「lines_near」列を追加(路線フィルタ用) ---
    if lines_data:
        df['lines_near'] = df.apply(
            lambda row: get_lines_near_sighting(
                row['latitude'], row['longitude'],
                lines_data, radius_km=5  # 半径5kmで判定
            ),
            axis=1
        )
    else:
        df['lines_near'] = [[] for _ in range(len(df))]

    # -------------------- 日付範囲フィルタ (サイドバー) --------------------
    # 日付範囲の指定
    min_date = df['date'].min().date()
    today = datetime.now().date()

    date_range = st.sidebar.date_input(
        "期間を選択",
        value=(min_date, today),
        help="日付範囲を指定してください。"
    )

    # 日付選択が適切かチェック
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        st.error("日付範囲を正しく指定してください（開始日と終了日の2つが必要です）。")
        return

    # -------------------- 路線フィルタ (サイドバー) --------------------
    if lines_data:
        all_line_names = [line['name'] for line in lines_data['lines']]
        line_options = ["すべて"] + all_line_names
        selected_line = st.sidebar.selectbox("路線を選択", line_options)
        if selected_line != "すべて":
            mask_line = df['lines_near'].apply(lambda lines: selected_line in lines)
            df = df[mask_line]

    # -------------------- データ概要をサイドバーに表示 --------------------
    st.sidebar.markdown("### データ概要")
    st.sidebar.markdown(f"- **総データ件数**: {len(df):,} 件")
    st.sidebar.markdown(f"- **期間**: {df['date'].min().date()} 〜 {df['date'].max().date()}")
    st.sidebar.markdown(f"- **対象市町村数**: {df['city'].nunique()} 市町村")

    # -------------------- 2カラムレイアウト (地図 + 統計情報) --------------------
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### 目撃情報マップ")
        # 熊目撃マップ作成
        my_map = create_folium_map(df, date_range)
        # 路線 & 駅マーカーを追加 (YAMLがあれば)
        if lines_data:
            add_railway_lines_to_map(my_map, lines_data)
            add_stations_to_map(my_map, lines_data)
        else:
            st.info("路線データがないため、路線表示はありません。")

        # 地図を表示
        st_folium(my_map, width=800, height=600)

    with col2:
        st.markdown("### 統計情報")
        # 時系列グラフと地域分布グラフをタブ切り替えで表示
        tab1, tab2 = st.tabs(["時系列推移", "地域分布"])

        with tab1:
            st.plotly_chart(create_time_series_plot(df), use_container_width=True)

        with tab2:
            st.plotly_chart(create_city_bar_chart(df), use_container_width=True)

    # -------------------- フッター --------------------
    st.markdown("---")
    st.markdown("""
    ### 使い方
    1. サイドバーの「情報を更新」ボタンで最新データを取得できます
    2. サイドバーで期間と路線を選択してデータをフィルタリングできます（市町村フィルタは削除）
    3. 地図は「通常表示」「クラスター表示」など、レイヤーコントロールで切り替え可能です
    4. 統計情報タブでは、時系列推移と市町村別の目撃件数を確認できます
    """)


# ----------------------------------------------
# メイン起動
# ----------------------------------------------
if __name__ == "__main__":
    main()


# streamlit run app.py