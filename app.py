# -*- coding: utf-8 -*-
"""
熊の目撃情報 (with_coords.csv) を読み込み、
Streamlit で地図表示(Folium)や統計グラフ(Plotly)を表示するアプリ。

初めてソースコードを読む方でもわかりやすいよう、
細かいコメントを追加しています。
"""

import streamlit as st
import pandas as pd
import folium
from folium import plugins
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

# 座標付きの熊目撃情報が格納されているCSVファイル
CSV_FILE = "bear_sightings_with_coords.csv"

def load_and_process_data(file_path: str) -> pd.DataFrame:
    """
    CSVファイルからデータを読み込み、必要な前処理を行ってDataFrameを返す。

    主な処理:
      1. CSV読み込み
      2. 緯度(latitude), 経度(longitude) が欠損の行を除去 (地図表示のため)
      3. 日付(date)を日時型に変換
      4. 日付(date)が欠損の行を除去
    """
    # CSVファイルを読み込み、PandasのDataFrameを生成
    df = pd.read_csv(file_path)

    # latitude, longitude のいずれかがNaNの場合は使えないため除去
    df = df.dropna(subset=['latitude', 'longitude'])

    # 日付をpd.Timestampに変換し、変換できないものはNaTになる
    df['date'] = pd.to_datetime(df['date'], errors='coerce')

    # 日付がNaT（欠損）の行も可視化できないため除外
    df = df.dropna(subset=['date'])

    return df


def create_folium_map(df: pd.DataFrame, date_range: tuple, selected_cities: list) -> folium.Map:
    """
    Foliumを使って地図オブジェクトを生成し、マーカー等を追加して返す。

    引数:
      - df: 目撃情報が格納されたDataFrame (date, city, location, latitude, longitude)
      - date_range: (開始日, 終了日) のタプル (streamlitのdate_inputで取得)
      - selected_cities: ユーザーが選択した市町村のリスト

    返り値:
      - folium.Map オブジェクト
    """
    # 地図生成時の初期表示位置とズームレベル
    # 例として [35.5, 138.5]（日本の中央近辺）を中心に、ズームを8程度に設定
    m = folium.Map(
        location=[35.5, 138.5],
        zoom_start=8,
        tiles='CartoDB positron',  # 地図のスタイル
        control_scale=True        # スケールコントロールを表示するか
    )

    # == 日付によるフィルタリング ==
    # date_rangeはstreamlit.date_inputの返り値: (datetime.date, datetime.date) のタプル
    # これをPandasのTimestamp型に変換
    start_date = pd.Timestamp(date_range[0])
    end_date = pd.Timestamp(date_range[1])

    # DataFrameの日付がstart_date〜end_dateの範囲にある行だけ抽出
    mask = (df['date'] >= start_date) & (df['date'] <= end_date)

    # == 市町村によるフィルタリング ==
    # selected_citiesが空でなければ、そこに含まれる市町村だけを抽出
    if selected_cities:
        mask &= df['city'].isin(selected_cities)

    # フィルタされたDataFrameを用意
    filtered_df = df[mask]

    # == 過去1週間のデータを特別に色分けするためのフラグ列を追加 ==
    now = datetime.now()
    one_week_ago = now - timedelta(days=7)
    # is_recent: 過去7日以内のデータならTrue、それ以外はFalse
    filtered_df['is_recent'] = filtered_df['date'] >= one_week_ago

    # == MarkerCluster（複数点をまとめるクラスタ表示）を追加 ==
    marker_cluster = plugins.MarkerCluster(name='クラスター表示')

    # == ヒートマップ表示用データ ==
    # ヒートマップは位置情報(緯度・経度)のみ使用する
    heat_data = [[row['latitude'], row['longitude']] for _, row in filtered_df.iterrows()]

    # ヒートマップレイヤーを生成 (最初は非表示に設定: show=False)
    heat_layer = plugins.HeatMap(
        heat_data,
        name='熱分布表示',
        show=False,        # LayerControlでユーザーが切り替えできるように
        min_opacity=0.3,   # 不透明度の下限
        radius=15          # 各地点のぼかし範囲
    )

    # == 通常のマーカーレイヤーを2種類に分割 (最近1週間 / それ以前) ==
    recent_layer = folium.FeatureGroup(name='過去1週間の目撃情報', show=True)
    old_layer = folium.FeatureGroup(name='過去の目撃情報', show=True)

    # フィルタ済みの各行に対して、CircleMarker（またはMarker）を追加
    for _, row in filtered_df.iterrows():
        # 過去1週間データなら赤色(#dc2626)・少し大きめ
        # それ以外なら青色(#1d4ed8)・少し小さめ
        color = '#dc2626' if row['is_recent'] else '#1d4ed8'
        radius = 8 if row['is_recent'] else 6

        # ポップアップで表示したいHTML文（日時や場所など）
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

        # CircleMarker（円形のマーカー）を配置
        marker = folium.CircleMarker(
            location=[row['latitude'], row['longitude']],  # [緯度, 経度]
            radius=radius,     # マーカーの大きさ
            color=color,       # 枠線の色
            fill=True,         # 中を塗りつぶすか
            fill_opacity=0.7,  # 塗りつぶしの透明度
            popup=popup_text,  # クリック時に表示するHTML
            tooltip=f"{row['city']} ({row['date'].strftime('%Y-%m-%d')})"  # マウスオーバー時のツールチップ
        )

        # MarkerClusterには通常のMarkerを追加
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=popup_text,
            icon=folium.Icon(
                color='red' if row['is_recent'] else 'blue',
                icon='info-sign'
            )
        ).add_to(marker_cluster)

        # 最近1週間ならrecent_layer、それ以外はold_layerに追加
        if row['is_recent']:
            marker.add_to(recent_layer)
        else:
            marker.add_to(old_layer)

    # 作成したレイヤーを地図に追加
    recent_layer.add_to(m)
    old_layer.add_to(m)
    marker_cluster.add_to(m)
    m.add_child(heat_layer)

    # レイヤーコントロール（チェックボックス）を地図に表示
    folium.LayerControl(collapsed=False).add_to(m)

    # 全画面表示ボタンプラグイン
    plugins.Fullscreen(
        position='topleft',      # ボタン配置位置
        title='全画面表示',       # ボタンにマウスを乗せた際の表示
        title_cancel='全画面解除',
        force_separate_button=True
    ).add_to(m)

    # ミニマップを追加（右下に小さな地図を表示）
    minimap = plugins.MiniMap(toggle_display=True, position='bottomright')
    m.add_child(minimap)

    return m


def create_time_series_plot(df: pd.DataFrame) -> go.Figure:
    """
    Plotlyを使って、時系列（date単位）の目撃件数推移を折れ線グラフで可視化する。
    """
    # 日付単位の件数を集計
    daily_counts = df.groupby('date').size().reset_index(name='count')

    # Figureを作成
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
        height=400  # グラフの高さ
    )
    return fig


def create_city_bar_chart(df: pd.DataFrame) -> go.Figure:
    """
    Plotlyを使って、市町村別の目撃件数を棒グラフで上位10件のみ可視化する。
    """
    # city列を集計し、多い順にソートして10件取得
    city_counts = df['city'].value_counts().head(10)

    fig = go.Figure(go.Bar(
        x=city_counts.values,   # 件数をX軸（横方向）
        y=city_counts.index,    # 市町村名をY軸（縦方向）
        orientation='h'         # 横向きバーにする
    ))
    fig.update_layout(
        title='市町村別熊目撃件数（上位10件）',
        xaxis_title='目撃件数',
        yaxis_title='市町村',
        height=400
    )
    return fig


def main():
    """
    Streamlitアプリのメイン関数。
    1. CSV読み込み
    2. 日付や市町村のフィルタリングUI
    3. Folium地図表示
    4. 時系列グラフ・地域分布グラフ表示
    """
    # ページ基本設定: レイアウト幅をWideにし、タイトルをセット
    st.set_page_config(layout="wide", page_title="熊出没情報マップ")

    # アプリのタイトル
    st.title("熊出没情報マップ（静岡・山梨・神奈川）")

    # CSVファイルの読み込み (bear_sightings_with_coords.csv)
    try:
        df = load_and_process_data(CSV_FILE)
    except FileNotFoundError:
        st.error(f"CSVファイルが見つかりません: {CSV_FILE}")
        return

    # == サイドバーのフィルタ設定 ==
    st.sidebar.header("データフィルター")

    # 1) 日付範囲の指定ウィジェット
    min_date = df['date'].min().date()  # dfにある最小の日付 (datetime.date型へ変換)
    max_date = df['date'].max().date()  # dfにある最大の日付
    date_range = st.sidebar.date_input(
        "期間を選択",
        value=(min_date, max_date),  # 初期値として全期間を選択
        min_value=min_date,
        max_value=max_date
    )

    # 2) 市町村のマルチセレクト
    cities = sorted(df['city'].unique())
    selected_cities = st.sidebar.multiselect(
        "市町村を選択（複数選択可）",
        cities  # サジェストリスト
    )

    # 3) データ概要の表示
    st.sidebar.markdown("### データ概要")
    st.sidebar.markdown(f"- **総データ件数**: {len(df):,} 件")
    st.sidebar.markdown(f"- **対象期間**: {min_date} 〜 {max_date}")
    st.sidebar.markdown(f"- **対象市町村数**: {len(cities)} 市町村")

    # == メインコンテンツ: 2カラムレイアウト ==
    col1, col2 = st.columns([2, 1])

    # (左カラム) 地図表示
    with col1:
        st.markdown("### 目撃情報マップ")
        # フィルタ条件を渡してFolium地図を生成
        my_map = create_folium_map(df, date_range, selected_cities)
        # st_foliumを使ってStreamlit上に描画 (width, height指定可)
        st_folium(my_map, width=800, height=600)
        # 注意や補足などを表示
        st.info("👆 地図の表示方法を切り替えられます（通常表示・クラスター表示・熱分布表示）")

    # (右カラム) 統計グラフ表示
    with col2:
        st.markdown("### 統計情報")

        # タブ（タブ1: 時系列推移, タブ2: 地域分布）
        tab1, tab2 = st.tabs(["時系列推移", "地域分布"])

        with tab1:
            # 日次の目撃件数推移グラフ
            st.plotly_chart(create_time_series_plot(df), use_container_width=True)

        with tab2:
            # 市町村別の棒グラフ
            st.plotly_chart(create_city_bar_chart(df), use_container_width=True)

    # == フッター的な説明文など ==
    st.markdown("---")
    st.markdown("""
    ### 使い方
    1. サイドバーで期間や市町村を選択してデータをフィルタリングできます  
    2. 地図は「通常表示」「クラスター表示」「熱分布表示」など、レイヤーコントロールで切り替え可能です  
    3. 統計情報タブでは、時系列推移と地域分布を確認できます
    """)


# スクリプトが直接実行された場合のみ main() を呼び出す
if __name__ == "__main__":
    main()
