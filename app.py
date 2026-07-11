import streamlit as st
import requests
import pandas as pd

# 🚨 여기에 본인의 OpenSky 아이디와 비밀번호를 직접 입력하세요!
USERNAME = "daejin2621022-api-client"
PASSWORD = "YGDWJqIvskDeOUyNsHnvyjxkaJwAlL9o"

def get_korea_flights(username, password):
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": 33.0, 
        "lamax": 39.0, 
        "lomin": 124.0, 
        "lomax": 132.0
    }
    
    try:
        response = requests.get(url, params=params, auth=(username, password), timeout=30)
        response.raise_for_status() 
        data = response.json()
        
        if data['states'] is not None:
            columns = [
                'icao24', 'callsign', 'origin_country', 'time_position', 
                'last_contact', 'longitude', 'latitude', 'baro_altitude', 
                'on_ground', 'velocity', 'true_track', 'vertical_rate', 
                'sensors', 'geo_altitude', 'squawk', 'spi', 'position_source'
            ]
            df = pd.DataFrame(data['states'], columns=columns)
            return df
        else:
            return pd.DataFrame()

    except Exception as e:
        # Streamlit 화면에 에러 메시지를 띄워줍니다.
        st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return None

# --- 웹앱 화면 꾸미기 ---
st.title("✈️ 한반도 실시간 비행기 레이더")
st.write("OpenSky Network API를 활용하여 한반도 상공의 비행기를 보여줍니다.")

# 1. 데이터 가져오기 (코드에 적어둔 아이디/비번 사용)
df_flights = get_korea_flights(USERNAME, PASSWORD)

# 2. 데이터가 잘 들어왔다면 화면에 출력하기
if df_flights is not None and not df_flights.empty:
    st.success(f"현재 총 {len(df_flights)}대의 비행기가 한반도 상공에 있습니다!")
    
    # 표 보여주기
    st.dataframe(df_flights[['callsign', 'origin_country', 'longitude', 'latitude', 'baro_altitude']])
    
    # 5단계 미리보기: 지도에 비행기 위치 점 찍기
    st.map(df_flights, latitude='latitude', longitude='longitude')
    
else:
    st.warning("현재 한반도 상공에 조회되는 비행기가 없거나, 아이디/비밀번호가 틀렸을 수 있습니다.")
