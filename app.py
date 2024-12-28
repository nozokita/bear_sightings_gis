import streamlit as st
import pandas as pd
import folium
from folium import plugins
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

CSV_FILE = "bear_sightings_with_coords.csv"

def load_and_process_data(file_path: str) -> pd.DataFrame:
    """データの読み込みと前処理を行う"""
    df = pd.read_csv(file_path)
    df = df.dropna(subset=['latitude', 'longitude'])
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    return df

def create_folium_map(df: pd.DataFrame, date_range: tuple, selected_cities: list) -> folium.Map:
    """強化されたFolium.Mapオブジェクトを生成"""
    m = folium.Map(
        location=[35.5, 138.5],
        zoom_start=8,
        tiles='CartoDB positron',
        control_scale=True
    )

    # フィルタリング
    # date_rangeの値をdatetime64[ns]に変換
    start_date = pd.Timestamp(date_range[0])
    end_date = pd.Timestamp(date_range[1])
    mask = (df['date'] >= start_date) & (df['date'] <= end_date)
    if selected_cities:
        mask &= df['city'].isin(selected_cities)
    filtered_df = df[mask]

    # 最近1週間の判定
    now = datetime.now()
    one_week_ago = now - timedelta(days=7)
    filtered_df['is_recent'] = filtered_df['date'] >= one_week_ago

    # クラスタリングレイヤーの追加
    marker_cluster = plugins.MarkerCluster(name='クラスター表示')
    
    # ヒートマップレイヤーのデータ準備
    heat_data = [[row['latitude'], row['longitude']] for _, row in filtered_df.iterrows()]
    heat_layer = plugins.HeatMap(
        heat_data,
        name='熱分布表示',
        show=False,
        min_opacity=0.3,
        radius=15
    )

    # 通常のマーカーレイヤー
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

        marker = folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=radius,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=popup_text,
            tooltip=f"{row['city']} ({row['date'].strftime('%Y-%m-%d')})"
        )

        # クラスターマーカーの追加
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=popup_text,
            icon=folium.Icon(color='red' if row['is_recent'] else 'blue', icon='info-sign')
        ).add_to(marker_cluster)

        if row['is_recent']:
            marker.add_to(recent_layer)
        else:
            marker.add_to(old_layer)

    # 各レイヤーを地図に追加
    recent_layer.add_to(m)
    old_layer.add_to(m)
    marker_cluster.add_to(m)
    m.add_child(heat_layer)

    # レイヤーコントロール
    folium.LayerControl(collapsed=False).add_to(m)

    # フルスクリーンボタン
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

def create_time_series_plot(df: pd.DataFrame) -> go.Figure:
    """時系列での目撃件数推移グラフを生成"""
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

def create_city_bar_chart(df: pd.DataFrame) -> go.Figure:
    """市町村別の目撃件数棒グラフを生成"""
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

def main():
    st.set_page_config(layout="wide", page_title="熊出没情報マップ")
    
    st.title("熊出没情報マップ（静岡・山梨・神奈川）")
    
    try:
        df = load_and_process_data(CSV_FILE)
    except FileNotFoundError:
        st.error(f"CSVファイルが見つかりません: {CSV_FILE}")
        return

    # サイドバーフィルター
    st.sidebar.header("データフィルター")
    
    # 日付範囲選択
    min_date = df['date'].min().date()
    max_date = df['date'].max().date()
    date_range = st.sidebar.date_input(
        "期間を選択",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    # 市町村選択
    cities = sorted(df['city'].unique())
    selected_cities = st.sidebar.multiselect(
        "市町村を選択（複数選択可）",
        cities
    )

    # データ概要
    st.sidebar.markdown("### データ概要")
    st.sidebar.markdown(f"- 総データ件数: {len(df):,}件")
    st.sidebar.markdown(f"- 対象期間: {min_date} 〜 {max_date}")
    st.sidebar.markdown(f"- 対象市町村数: {len(cities)}市町村")

    # メインコンテンツを2カラムレイアウトで表示
    col1, col2 = st.columns([2, 1])

    with col1:
        # Folium地図
        st.markdown("### 目撃情報マップ")
        my_map = create_folium_map(df, date_range, selected_cities)
        st_folium(my_map, width=800, height=600)
        st.info("👆 地図の表示方法を切り替えられます（通常表示・クラスター表示・熱分布表示）")

    with col2:
        # 統計情報とグラフ
        st.markdown("### 統計情報")
        
        # タブで表示を切り替え
        tab1, tab2 = st.tabs(["時系列推移", "地域分布"])
        
        with tab1:
            st.plotly_chart(create_time_series_plot(df), use_container_width=True)
        
        with tab2:
            st.plotly_chart(create_city_bar_chart(df), use_container_width=True)

    # フッター
    st.markdown("---")
    st.markdown("""
    ### 使い方
    - サイドバーで期間や市町村を選択してデータをフィルタリングできます
    - 地図は通常表示・クラスター表示・熱分布表示を切り替えられます
    - 統計情報タブでは時系列推移と地域分布を確認できます
    """)

if __name__ == "__main__":
    main()

# streamlit run app.py