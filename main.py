import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import io

# -----------------------------------------------------------------------------
# 1. 스트림릿 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="전국 폭염일수 현황 지도",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 전국 폭염일수 현황 및 분석")
st.caption("연도별 폭염일수 지도와 상세 관측 데이터를 한눈에 확인하세요.")

# -----------------------------------------------------------------------------
# 2. 데이터 로드 및 전처리 함수
# -----------------------------------------------------------------------------
@st.cache_data
def load_heatwave_data(file_path="heatwave.csv"):
    """
    하나의 CSV 파일에 섹션별로 나누어진 폭염 데이터를 분리하여 읽어옵니다.
    utf-8 인코딩 실패 시 cp949(EUC-KR)로 재시도합니다.
    """
    content = None
    # 인코딩 처리 (utf-8 실패 시 cp949 시도)
    for encoding in ['utf-8', 'cp949', 'utf-8-sig']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.readlines()
            break
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            st.error(f"⚠️ `{file_path}` 파일을 찾을 수 없습니다. GitHub 저장소 루트에 올렸는지 확인해 주세요.")
            return None, None, None

    if content is None:
        st.error("⚠️ 파일 인코딩을 읽는 데 실패했습니다. (utf-8 또는 cp949 사용 필요)")
        return None, None, None

    # 섹션 위치 찾기
    sec1_idx, sec2_idx, sec3_idx = None, None, None
    for i, line in enumerate(content):
        if "가장 긴 폭염" in line:
            sec1_idx = i
        elif "가장 빠른/가장 늦은 폭염" in line:
            sec2_idx = i
        elif "전국 폭염일수" in line:
            sec3_idx = i

    # 각 섹션별 텍스트 추출 및 판다스 데이터프레임 변환
    def parse_section(lines):
        if not lines:
            return pd.DataFrame()
        # 빈 줄 제거
        valid_lines = [l for l in lines if l.strip()]
        if not valid_lines:
            return pd.DataFrame()
        csv_data = "".join(valid_lines)
        return pd.read_csv(io.StringIO(csv_data))

    # 데이터프레임 생성 (제목 줄 제외하고 읽기)
    df_longest = parse_section(content[sec1_idx+1 : sec2_idx]) if sec1_idx is not None else pd.DataFrame()
    df_extreme = parse_section(content[sec2_idx+1 : sec3_idx]) if sec2_idx is not None and sec3_idx is not None else pd.DataFrame()
    df_raw = parse_section(content[sec3_idx+1 :]) if sec3_idx is not None else pd.DataFrame()

    return df_longest, df_extreme, df_raw

@st.cache_data
def load_geojson():
    """대한민국 시군구 경계 GeoJSON 데이터를 불러옵니다."""
    url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"⚠️ GeoJSON 지도를 불러오는데 실패했습니다: {e}")
        return None

# 데이터 로드
df_longest, df_extreme, df_raw = load_heatwave_data()
geojson_data = load_geojson()

if df_raw is None or df_raw.empty:
    st.stop()  # 데이터가 없으면 앱 실행 중단

# -----------------------------------------------------------------------------
# 3. 기상청 관측지점 -> 행정구역(시군구) 매핑
# -----------------------------------------------------------------------------
# 주요 기상 관측지점 이름을 GeoJSON의 '시군구' 이름과 일치하도록 매핑하는 딕셔너리
STATION_TO_SIGUNGU = {
    "강릉": "강릉시", "대관령": "평창군", "추풍령": "영동군", "속초": "속초시",
    "춘천": "춘천시", "원주": "원주시", "인제": "인제군", "홍천": "홍천군",
    "태백": "태백시", "정선군": "정선군", "철원": "철원군", "동해": "동해시",
    "서울": "종로구", "인천": "중구", "수원": "수원시", "파주": "파주시",
    "이천": "이천시", "양평": "양평군", "강화": "강화군", "백령도": "옹진군",
    "대전": "유성구", "청주": "청주시", "충주": "충주시", "보은": "보은군",
    "제천": "제천시", "전주": "전주시", "군산": "군산시", "목포": "목포시",
    "여수": "여수시", "광주": "북구", "순천": "순천시", "완도": "완도군",
    "진도군": "진도군", "부안": "부안군", "임실": "임실군", "정읍": "정읍시",
    "남원": "남원시", "장수": "장수군", "대구": "중구", "포항": "포항시",
    "울산": "중구", "부산": "중구", "창원": "창원시", "안동": "안동시",
    "울진": "울진군", "포항": "포항시", "경주시": "경주시", "거제": "거제시",
    "통영": "통영시", "밀양": "밀양시", "산청": "산청군", "거창": "거창군",
    "합천": "합천군", "제주": "제주시", "서귀포": "서귀포시", "성산": "서귀포시",
    "고산": "제주시"
}

# -----------------------------------------------------------------------------
# 4. 사이드바 및 연도 선택
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 검색 조건")

# CSV 내 '년도' 또는 '연도' 컬럼 자동 인식
year_col = '년도' if '년도' in df_raw.columns else ('연도' if '연도' in df_raw.columns else df_raw.columns[0])

# 연도 목록 추출 및 슬라이더 생성
available_years = sorted(df_raw[year_col].dropna().unique())
selected_year = st.sidebar.slider(
    "조회할 연도를 선택하세요",
    min_value=int(min(available_years)),
    max_value=int(max(available_years)),
    value=int(max(available_years))
)

# -----------------------------------------------------------------------------
# 5. 선택된 연도 데이터 집계
# -----------------------------------------------------------------------------
# 선택 연도 데이터 필터링
df_selected_year = df_raw[df_raw[year_col] == selected_year]

# 지점별 폭염일수 계산 (원자료가 발생 일자별 레코드인 경우 건수를 카운트, 이미지 집계본이면 sum)
station_col = '지점' if '지점' in df_selected_year.columns else '관측지점'
if '폭염일수' in df_selected_year.columns:
    df_counts = df_selected_year.groupby(station_col)['폭염일수'].sum().reset_index()
else:
    df_counts = df_selected_year.groupby(station_col).size().reset_index(name='폭염일수')

# 관측지점명을 행정구역(시군구) 이름으로 매핑
df_counts['시군구'] = df_counts[station_col].map(lambda x: STATION_TO_SIGUNGU.get(x, x))

# -----------------------------------------------------------------------------
# 6. 상단 요약 지표 (Metric Cards)
# -----------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)

avg_days = df_counts['폭염일수'].mean() if not df_counts.empty else 0
max_row = df_counts.loc[df_counts['폭염일수'].idxmax()] if not df_counts.empty else None
total_stations = len(df_counts)

with col1:
    st.metric("전국 평균 폭염일수", f"{avg_days:.1f} 일")
with col2:
    if max_row is not None:
        st.metric("최다 폭염 관측지", f"{max_row[station_col]} ({max_row['폭염일수']}일)")
    else:
        st.metric("최다 폭염 관측지", "-")
with col3:
    st.metric("총 관측지점 수", f"{total_stations} 곳")

st.divider()

# -----------------------------------------------------------------------------
# 7. 지도 시각화 (Choropleth)
# -----------------------------------------------------------------------------
st.subheader(f"🗺️ {selected_year}년 전국 시군구별 폭염일수 지도")

if geojson_data:
    # 지도 중심점 (대한민국 중심 좌표)
    m = folium.Map(location=[36.2, 127.8], zoom_start=7, tiles="cartodbpositron")

    # 단계구분도(Choropleth) 생성
    folium.Choropleth(
        geo_data=geojson_data,
        name="choropleth",
        data=df_counts,
        columns=["시군구", "폭염일수"],
        key_on="feature.properties.시군구",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name=f"{selected_year}년 폭염일수 (일)",
        na_color="#ffffff"
    ).add_to(m)

    # 스트림릿에 Folium 지도 출력
    st_folium(m, width="100%", height=500, returned_objects=[])
else:
    st.warning("지도를 표시할 수 없습니다.")

st.divider()

# -----------------------------------------------------------------------------
# 8. 하단 데이터 표 구성
# -----------------------------------------------------------------------------
# 8-1. 상위/하위 10곳 표
st.subheader(f"📊 {selected_year}년 폭염일수 상위 / 하위 관측지")
col_top, col_bottom = st.columns(2)

with col_top:
    st.markdown("**🔥 폭염일수 상위 10곳**")
    top_10 = df_counts.sort_values(by="폭염일수", ascending=False).head(10)[[station_col, "폭염일수"]]
    st.dataframe(top_10, use_container_width=True, hide_index=True)

with col_bottom:
    st.markdown("**🧊 폭염일수 하위 10곳**")
    bottom_10 = df_counts.sort_values(by="폭염일수", ascending=True).head(10)[[station_col, "폭염일수"]]
    st.dataframe(bottom_10, use_container_width=True, hide_index=True)

st.divider()

# 8-2. 역대 기록 표 (가장 긴 폭염 & 가장 빠른/늦은 폭염)
col_sec1, col_sec2 = st.columns(2)

with col_sec1:
    st.subheader("⏳ 역대 가장 긴 폭염 기록")
    if not df_longest.empty:
        st.dataframe(df_longest, use_container_width=True, hide_index=True)
    else:
        st.info("관련 데이터가 없습니다.")

with col_sec2:
    st.subheader("📅 가장 빠른 / 가장 늦은 폭염")
    if not df_extreme.empty:
        st.dataframe(df_extreme, use_container_width=True, hide_index=True)
    else:
        st.info("관련 데이터가 없습니다.")
