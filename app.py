import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
import numpy as np

# 페이지 레이아웃을 넓게 쓰고, 탭 아이콘 변경
st.set_page_config(page_title="한반도 실시간 비행기 추적", page_icon="✈️", layout="wide")

# --- 커스텀 디자인 (CSS) ---
st.markdown("""
    <style>
    /* 메인 타이틀 디자인을 조금 더 세련되게 변경 */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        color: #1E88E5;
        margin-bottom: 0rem;
    }
    .sub-title {
        font-size: 1.1rem;
        color: #6c757d;
        margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">✈️ 한반도 상공 실시간 비행기 레이더</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">OpenSky API + Z-score 통계 기법을 활용한 급강하 이상 탐지 시스템</p>', unsafe_allow_html=True)

# -----------------------------------------------------------
# 1. 사이드바 UI 설정
# -----------------------------------------------------------
st.sidebar.header("⚙️ 컨트롤 타워")
refresh_button = st.sidebar.button("🔄 실시간 데이터 새로고침", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 이상 탐지 민감도 설정")

z_threshold = st.sidebar.slider(
    "급강하 감지 Z-score 기준값 (낮을수록 엄격함)",
    min_value=-5.0,
    max_value=-1.0,
    value=-3.0,
    step=0.1,
    help="통상적으로 -3.0 이하면 통계적으로 매우 이례적인 급강하로 판단합니다."
)

# -----------------------------------------------------------
# 2. 데이터 수집 (OpenSky API)
# -----------------------------------------------------------
def get_flight_data():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    
    try:
        USERNAME = st.secrets["opensky"]["username"]
        PASSWORD = st.secrets["opensky"]["password"]
        
        response = requests.get(url, params=params, auth=(USERNAME, PASSWORD), timeout=30)
        response.raise_for_status() 
        data = response.json()
        
        if data is not None and data.get("states") is not None:
            return data["states"]
        return []
        
    except requests.exceptions.Timeout:
        st.error("서버 응답 지연: OpenSky 서버가 30초 동안 응답하지 않습니다.")
        return []
    except KeyError:
        st.error("🚨 Streamlit Settings -> Secrets에 아이디와 비밀번호가 설정되지 않았습니다!")
        return []
    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return []

with st.spinner('위성에서 한반도 상공 데이터를 수신 중입니다...'):
    raw_data = get_flight_data()

# -----------------------------------------------------------
# 3. 데이터 전처리 및 핵심 로직
# -----------------------------------------------------------
if len(raw_data) > 0:
    columns = [
        'icao24', 'callsign', 'origin_country', 'time_position', 'last_contact',
        'longitude', 'latitude', 'baro_altitude', 'on_ground', 'velocity',
        'true_track', 'vertical_rate', 'sensors', 'geo_altitude', 'squawk', 'spi', 'position_source'
    ]
    df = pd.DataFrame(raw_data, columns=columns)
    
    df = df[['callsign', 'longitude', 'latitude', 'baro_altitude', 'velocity', 'vertical_rate']]
    df = df.dropna(subset=['longitude', 'latitude', 'vertical_rate'])
    df['callsign'] = df['callsign'].astype(str).str.strip().replace('', '알 수 없음')

    if len(df) == 0:
        st.warning("현재 상공에 비행기는 있지만, 수직 속도 데이터를 보내는 비행기가 없습니다.")
    else:
        # Z-score 계산
        mean_vr = df['vertical_rate'].mean()
        std_vr = df['vertical_rate'].std()
        
        if std_vr > 0:
            df['z_score'] = (df['vertical_rate'] - mean_vr) / std_vr
        else:
            df['z_score'] = 0.0

        # 상태 분류
        df['status'] = df['z_score'].apply(lambda z: '위험(급강하)' if z <= z_threshold else '정상')

        # [디자인 포인트] 위험한 비행기는 색상(빨강)과 크기(15000)를 훨씬 크게 부여합니다!
        def assign_color_and_size(row):
            if row['status'] == '위험(급강하)':
                return pd.Series([[255, 75, 75, 255], 15000]) # 빨간색, 큰 사이즈
            return pd.Series([[255, 200, 0, 150], 6000])      # 노란색, 기본 사이즈
            
        df[['color', 'radius']] = df.apply(assign_color_and_size, axis=1)

        diving_count = len(df[df['status'] == '위험(급강하)'])

        # -----------------------------------------------------------
        # 4. 상단 대시보드 요약 (새로운 디자인 배치)
        # -----------------------------------------------------------
        st.markdown("### 📊 실시간 항공 통계 요약")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(label="탐지된 총 비행기", value=f"{len(df)} 대")
        with col2:
            # 위험 비행기가 있으면 빨간색 느낌이 나도록 이모지 강조
            alert_label = "🚨 위험(급강하) 비행기" if diving_count > 0 else "✅ 위험(급강하) 비행기"
            st.metric(label=alert_label, value=f"{diving_count} 대")
        with col3:
            st.metric(label="평균 수직 속도", value=f"{mean_vr:.2f} m/s")
        with col4:
            st.metric(label="수직 속도 표준편차", value=f"{std_vr:.2f}")

        st.markdown("---")

        # -----------------------------------------------------------
        # 5. Pydeck 3D 지도 시각화
        # -----------------------------------------------------------
        view_state = pdk.ViewState(latitude=36.0, longitude=128.0, zoom=6, pitch=45)

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[longitude, latitude]",
            get_radius="radius",       # 이제 고정값이 아니라 데이터에 따라 크기가 변합니다!
            get_fill_color="color",
            pickable=True,
            stroked=True,
            get_line_color=[0, 0, 0, 255],
            line_width_min_pixels=1
        )

        tooltip = {
            "html": """
            <div style='font-family: sans-serif;'>
                <b style='font-size: 1.2em;'>✈️ {callsign}</b><br/>
                <hr style='margin: 5px 0;'/>
                <b>상태:</b> {status} <br/>
                <b>수직 속도:</b> <span style='color:#ff4b4b;'>{vertical_rate} m/s</span><br/>
                <b>현재 고도:</b> {baro_altitude} m <br/>
                <b>위험 지수(Z):</b> {z_score}
            </div>
            """,
            "style": {"backgroundColor": "#2c3e50", "color": "white", "borderRadius": "8px", "padding": "10px"}
        }

        r = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style="dark" # 지도를 더 세련되게 어둡게 유지
        )

        st.pydeck_chart(r)
        
        # -----------------------------------------------------------
        # 6. 스마트 데이터 테이블 (조건부 서식 적용)
        # -----------------------------------------------------------
        st.subheader("📋 세부 비행 데이터")
        
        # [디자인 포인트] 표에서 '위험(급강하)'인 줄은 옅은 빨간색으로 하이라이트 합니다.
        def highlight_danger_row(row):
            if row['status'] == '위험(급강하)':
                return ['background-color: rgba(255, 75, 75, 0.2)'] * len(row)
            return [''] * len(row)
            
        display_df = df[['callsign', 'status', 'z_score', 'vertical_rate', 'baro_altitude', 'velocity']]
        styled_df = display_df.style.apply(highlight_danger_row, axis=1).format({'z_score': "{:.2f}"})
        
        st.dataframe(styled_df, use_container_width=True)

else:
    st.warning("현재 한반도 상공에서 감지된 비행기 데이터가 없습니다. (잠시 후 다시 시도해보세요)")
