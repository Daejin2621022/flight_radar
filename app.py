import streamlit as st
import pandas as pd
import requests
import pydeck as pdk

st.set_page_config(page_title="한반도 실시간 비행기 추적", layout="wide")

st.title("✈️ 한반도 상공 실시간 비행기 이상 탐지 웹앱")
st.write("OpenSky API 데이터에 Z-score 통계 기법을 적용하여 급강하 중인 비행기를 자동으로 감지합니다.")

# -----------------------------------------------------------
# 1. 안전하게 API 정보 가져오기 (Streamlit Secrets 활용)
# -----------------------------------------------------------
try:
    USERNAME = st.secrets["opensky"]["username"]
    PASSWORD = st.secrets["opensky"]["password"]
except KeyError:
    st.error("🚨 시크릿 금고(secrets.toml)에 OpenSky 아이디와 비밀번호가 없습니다! 설정을 확인해주세요.")
    st.stop() # 에러가 나면 아래 코드를 실행하지 않고 멈춥니다.

# -----------------------------------------------------------
# 2. 사이드바 UI 설정
# -----------------------------------------------------------
st.sidebar.header("⚙️ 컨트롤 타워")
refresh_button = st.sidebar.button("🔄 실시간 데이터 새로고침")

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 이상 탐지(Anomaly Detection) 설정")
z_threshold = st.sidebar.slider(
    "급강하 감지 Z-score 기준값",
    min_value=-5.0,
    max_value=5.0,
    value=-3.0,
    step=0.1
)

# -----------------------------------------------------------
# 3. 데이터 수집 (OpenSky API)
# -----------------------------------------------------------
def get_flight_data(user, pwd):
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    
    try:
        response = requests.get(url, params=params, auth=(user, pwd), timeout=30)
        response.raise_for_status() 
        data = response.json()
        
        if data is not None and data.get("states") is not None:
            return data["states"]
        return []
        
    except requests.exceptions.Timeout:
        st.error("서버 응답 지연: OpenSky 서버가 30초 동안 응답하지 않습니다. 잠시 후 새로고침을 눌러주세요.")
        return []
    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return []

raw_data = get_flight_data(USERNAME, PASSWORD)

# -----------------------------------------------------------
# 4. 데이터 전처리 및 Z-score 계산
# -----------------------------------------------------------
if len(raw_data) > 0:
    columns = [
        'icao24', 'callsign', 'origin_country', 'time_position', 'last_contact',
        'longitude', 'latitude', 'baro_altitude', 'on_ground', 'velocity',
        'true_track', 'vertical_rate', 'sensors', 'geo_altitude', 'squawk', 'spi', 'position_source'
    ]
    df = pd.DataFrame(raw_data, columns=columns)
    
    # 필요한 열만 추출하고, 빈 데이터(NaN) 제거
    df = df[['callsign', 'longitude', 'latitude', 'baro_altitude', 'velocity', 'vertical_rate']]
    df = df.dropna(subset=['longitude', 'latitude', 'vertical_rate'])
    df['callsign'] = df['callsign'].astype(str).str.strip().replace('', '알 수 없음')

    # [안전장치] 빈 데이터를 지웠더니 남은 비행기가 하나도 없을 경우를 대비합니다.
    if len(df) == 0:
        st.warning("현재 상공에 비행기는 있지만, 수직 속도(vertical_rate) 데이터를 보내는 비행기가 없습니다.")
    else:
        # --- Z-score 계산 ---
        mean_vr = df['vertical_rate'].mean()
        std_vr = df['vertical_rate'].std()
        
        if std_vr > 0:
            df['z_score'] = (df['vertical_rate'] - mean_vr) / std_vr
        else:
            df['z_score'] = 0.0

        # 상태 및 색상 분류
        df['status'] = df['z_score'].apply(lambda z: '위험(급강하)' if z <= z_threshold else '정상')

        def assign_color(status):
            if status == '위험(급강하)':
                return [255, 0, 0, 255] # 빨간색
            return [255, 200, 0, 180]    # 노란색
            
        df['color'] = df['status'].apply(assign_color)

        # 사이드바 요약 정보
        diving_count = len(df[df['status'] == '위험(급강하)'])
        st.sidebar.success(f"현재 추적 비행기: {len(df)}대")
        if diving_count > 0:
            st.sidebar.error(f"⚠️ 급강하 감지: {diving_count}대!!")
        else:
            st.sidebar.info("✅ 현재 특이 이상 징후 없음")

        # -----------------------------------------------------------
        # 5. Pydeck 3D 지도 시각화
        # -----------------------------------------------------------
        view_state = pdk.ViewState(latitude=36.0, longitude=128.0, zoom=6, pitch=45)

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[longitude, latitude]",
            get_radius=6000,
            get_fill_color="color",
            pickable=True
        )

        tooltip = {
            "html": """
            <b>콜사인:</b> {callsign} <br/>
            <b>상태:</b> {status} <br/>
            <b>수직 속도:</b> {vertical_rate} m/s <br/>
            <b>Z-score:</b> {z_score} <br/>
            <b>현재 고도:</b> {baro_altitude} m
            """,
            "style": {"backgroundColor": "black", "color": "white"}
        }

        r = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style="dark"
        )

        st.pydeck_chart(r)
        
        # -----------------------------------------------------------
        # 6. 데이터 테이블 확인
        # -----------------------------------------------------------
        st.subheader("📊 실시간 항공 통계 및 데이터")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="평균 수직 속도", value=f"{mean_vr:.2f} m/s")
        with col2:
            st.metric(label="수직 속도 표준편차", value=f"{std_vr:.2f}")
            
        st.dataframe(df[['callsign', 'status', 'z_score', 'vertical_rate', 'baro_altitude', 'velocity']])

else:
    st.warning("현재 한반도 상공에서 감지된 비행기 데이터가 없습니다. (잠시 후 다시 시도해보세요)")
