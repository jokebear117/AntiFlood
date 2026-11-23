# Anti-Flood 데이터셋

2022년 8월 8~9일 강남역 일대 호우를 재현하기 위한 자료다. 2026년 11월 24일(KST)에 수집했다. 서울시 실측 강우를 10분 간격으로 재생하고, 강남역 주변 침수흔적과 결과의 공간 분포를 비교할 수 있다. 당시 배수량과 시간별 침수심을 재현하려면 하수관망과 시설 가동 기록을 추가로 확보해야 한다.

`raw/`에는 제공기관에서 내려받은 파일을, `processed/`에는 사건 구간을 추출하거나 집계한 파일을 둔다. 표의 용량은 바이트(B) 기준이다. ZIP은 압축 무결성을 검사했고, PDF는 페이지를 열어 관련 부분을 확인했다.

## 지형 고도

| 상태 | 원본 파일 | 기준 시점과 검증 |
| --- | --- | --- |
| 부분 확보 | [N37E127_FABDEM_V1-2.tif](raw/dem/N37E127_FABDEM_V1-2.tif) · 29,241,892 B, [fabdem_readme.txt](raw/dem/fabdem_readme.txt) · 18,866 B | Bristol 대학교의 FABDEM V1-2. 공식 묶음 ZIP에서 북위 37~38°, 동경 127~128° 타일 하나만 받아 CRC `a0b509db`와 GeoTIFF 픽셀 읽기를 확인했다. 3,600 × 3,600 Float32, 약 30 m급(1각초), 수평 WGS 84(EPSG:4326), 수직 EGM2008(EPSG:3855, m), NoData `-9999`. 수직 기준은 제작자 설명서에 명시돼 있다. CC BY-NC-SA 4.0으로, 비상업 재배포 시 출처 표시와 동일 조건이 필요하다. [공식 자료](https://doi.org/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn) · [원본 묶음 ZIP](https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/N30E120-N40E130_FABDEM_V1-2.zip) · [제작자 설명서](https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/readme.txt) |
| 신청 필요 | 국토지리정보원 강남역 일대 수치표고모형 | 1~5 m급 지형의 대상 도엽, 2022년 당시 판본, 좌표계·수직 기준·촬영연도는 미확인이다. 국토정보플랫폼에 로그인해 강남역을 검색하고 공개 DEM 목록에서 인접 도엽의 해상도와 내려받기 조건을 확인한다. 포털은 대용량 파일전송 프로그램을 안내한다. 1 m급 또는 과거 판본은 국토조사과(031-210-2713)에 제공 가능 여부를 문의한다. [국토지리정보원 DEM 안내](https://www.data.go.kr/data/15059920/fileData.do) · [국토정보플랫폼](https://map.ngii.go.kr/ms/map/NlipMap.do) |

[강남역 주변 지형 GeoTIFF](processed/fabdem_gangnam_1arcsec.tif)는 원본에서 경도 127.005~127.065°, 위도 37.470~37.535° 구간을 잘라낸 파일(105,823 B)이다. 234행 × 216열을 보간 없이 잘랐으며, 픽셀을 다시 열어 강남역 포함 및 NoData 0개를 확인했다. 사각형은 강남역 주변을 보기 위한 임시 범위이며 5개 배수분구의 전체 포함 여부는 경계 원본을 받은 뒤 확인할 수 있다.

FABDEM은 건물과 수목 높이의 영향을 줄인 지표면 근사 자료다. 2023년 공개한 V1-2의 기반 자료는 Copernicus DEM 2021_1이며, 대체 자료를 쓴 일부 영역을 제외한 주 관측 기간은 2011~2015년이다. 강남 타일의 개별 관측일과 2022년 당시 지형 변화량은 확인하지 못했다. 이 해상도는 저지대와 대략적인 흐름을 살피는 데 쓸 수 있다. 도로 횡단 경사, 연석, 지하 진입부를 확인하려면 더 촘촘한 자료가 필요하다. [FABDEM 제작 논문](https://doi.org/10.1088/1748-9326/ac4d4f) · [Copernicus DEM 제품 설명](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)

## 강우량과 관측소

| 상태 | 원본 파일 | 기준 시점과 검증 |
| --- | --- | --- |
| 확보 완료 | [rainfall_2022.zip](raw/rainfall/rainfall_2022.zip) · 6,402,218 B | 2022년 서울시 월별 CSV 12개, CP949. 8월 파일의 212,458행 중 8월 7~10일 관측 27,050행과 48개 관측소 ID를 확인했다. [서울시 치수안전과 OA-1168](https://data.seoul.go.kr/dataList/OA-1168/F/1/datasetView.do) |
| 부분 확보 | [stations_bessel.csv](raw/rainfall/stations_bessel.csv) · 4,162 B | OA-1168의 위치 목록 47행. 포털 수정일 2025-05-09. 코드·관측소명·주소·X/Y가 있으며, 사건 강우의 코드 47개가 일치하고 `301`이 빠져 있다. [서울시 치수안전과 OA-1168](https://data.seoul.go.kr/dataList/OA-1168/F/1/datasetView.do) |
| 신청 필요 | 기상청 강남(400)·서초(401)·동작(410) AWS 및 서울(108) ASOS | 공식 보고서에서 기상청 1분 관측 집계값을 확보했다. 원시 AWS 파일은 기상자료개방포털 로그인 후 8월 8일과 9일을 각각 조회하거나 파일셋에서 신청한다. 서울시 관측소 코드 체계와 별개다. [기상청 AWS](https://data.kma.go.kr/data/grnd/selectAwsRltmList.do?pgmNo=56) · [ASOS](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36) |

[10분 재생 CSV](processed/rainfall_20220807_10_10min.csv)는 UTF-8이며 `timestamp` ← 자료수집 시각, `station_id` ← 강우량계 코드, `rainfall_mm` ← 10분우량으로 매핑했다. UTC+09:00을 붙이고 시각과 관측소 ID 순으로 정렬했다. 8월 7일 00:09부터 10일 23:59까지 같은 관측소·시각 조합의 중복, 빈 강우량, 음수 강우량은 없었다. 전체 행 중 52행은 통상적인 10분 종료분(09·19·29·39·49·59분)과 달랐고, 예상한 정규 슬롯 27,648개 중 650개에서 해당 시각의 관측을 찾지 못했다. 정규 시각 외 관측도 10분 CSV에 보존했다. 예를 들어 시각이 13:09라면 서울시 정의상 13:00:00~13:09:59의 누적량이다. [서울시 강우량 데이터 설명](https://data.seoul.go.kr/bsp/wgs/dataView/data300View/1115.do)

[시간별 집계 CSV](processed/rainfall_20220807_10_hourly.csv)는 KST 정시를 시작으로 하는 96시간과 48개 지점, 총 4,608행이다. 해당 시간의 정규 관측 6개가 모두 있는 4,417행만 합산했다. 나머지 191행의 `rainfall_mm`은 공란이고, `on_grid_sample_count`에 실제 정규 슬롯 개수를 기록했다. 비정규 시각의 자료는 포함 구간이 겹칠 수 있어 시간 합계에서 제외했다.

위치 파일에는 Bessel이라는 표기만 있고 EPSG 코드, 축 순서, 좌표 스케일, 설치·이전 기준일을 확인할 수 없었다. 일부 관측소명과 주소도 서로 맞지 않는다. 10분 CSV의 `latitude`와 `longitude`는 공란이다. 공간 보간 전 서울시 치수안전과에 2022년 8월 기준 ID별 경위도와 이전 이력을 요청한다. 별도 경위도 자료 OA-22824는 서울시가 OA-1168로 통합한다고 공지했다. 두 서울시 원본의 포털 이용허락범위는 제한 없음으로 표시된다. [서울시 서비스 통합 공지](https://data.seoul.go.kr/together/notice/datasetNoticeView.do?bbsCd=10008&ditcCd=&pageIndex=1&seq=b4c3d22035b7127feaa8fe7e344f5f1a)

## 침수흔적도

**확보 완료.** [inundation_2022.zip](raw/inundation/inundation_2022.zip) 3,651,334 B와 [inundation_fields.pdf](raw/inundation/inundation_fields.pdf) 137,879 B를 받았다. 원본 ZIP은 2026년 1월 7일 게시된 수정본이다. 서울 전역의 폴리곤 19,881건을 읽었으며, 연도 속성 `F_YR`에는 2022년 19,482건과 2023년 399건이 섞여 있다. CRS는 PRJ의 KGD2002 / Unified CS(EPSG:5179, m)이며, DBF 인코딩은 CP949다. 필드 설명 PDF는 2025년 5월 19일 게시 파일로 한 쪽을 열어 면적 단위와 시각 표기 규칙을 확인했다. 포털 이용허락범위는 제한 없음으로 표시된다. [서울시 침수흔적도 OA-15636](https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do)

[강남역 주변 침수 폴리곤](processed/inundation_gangnam_20220808_09.zip)은 EPSG:5179 Shapefile이다. 서울교통공사 강남역 기준점(37.497958°N, 127.027539°E)을 중심으로 동서·남북 각 ±1 km 사각형에 피처의 경계상자가 닿고, `F_YR`이 2022이며 `F_SAT_YMD`에서 8월 8일 또는 9일을 읽을 수 있는 피처를 골랐다. 강남구 58건, 서초구 224건이며 원래 폴리곤을 유지했다. 이 범위는 공식 배수분구 경계를 대신하지 않는다. [서울교통공사 역사 좌표](https://www.data.go.kr/data/15099316/fileData.do)

`F_SHIM`은 침수심(m), `F_AVR_HGT`는 평균 침수위(해발고도, 공식 수직 기준 미확인), `F_AREA`는 침수면적(㎡)이다. `F_SAT_YMD`·`F_END_YMD`, `F_SAT_TM`·`F_END_TM`은 시작·종료 날짜와 시각이다. 날짜에 시각이 붙은 경우, 시각이 한두 자리인 경우, 종료값이 비어 있는 경우가 있어 원본 문자열을 유지했다. 침수흔적도는 조사 이후 만든 공간 자료다. 폴리곤 중첩과 조사 범위를 확인한 뒤 공간 검증에 쓰고, 침수심을 연속 시계열로 해석하거나 면적 필드를 단순 합산하지 않는다. [재해지도 속성정보 구축 지침](https://law.go.kr/flDownload.do?flSeq=140110577)

강우와 침수 원본은 서울시 파일 목록의 다운로드 폼에서 받았다. [공식 파일 서버](https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false)에 POST로 다음 값을 보낸다. 모든 요청의 `seqNo`는 빈 값이다.

| 파일 | `infId` | `infSeq` | `seq` |
| --- | --- | --- | --- |
| 2022년 강우 ZIP | OA-1168 | 3 | 202214 |
| 관측소 위치 CSV | OA-1168 | 3 | 999999 |
| 2022년 침수 ZIP | OA-15636 | 1 | 30 |
| 필드 설명 PDF | OA-15636 | 1 | 98 |

## 2022년 8월 호우와 피해 기록

| 상태 | 원본 파일 | 확인한 근거 |
| --- | --- | --- |
| 확보 완료 | [krihs_2022_flood.pdf](raw/event_2022/krihs_2022_flood.pdf) · 3,555,951 B | 국토연구원 2022-09-07 이슈리포트 67호, 12쪽. 2쪽 그림 1의 AWS 관측 집계, 3쪽 그림 2의 강남대로·서초대로 피해 위치, 4쪽의 반포천 임시 통수와 사후 면적 분석을 확인했다. [원본 PDF](https://www.krihs.re.kr/boardDownload.es?bid=0008&list_no=384324&seq=2) |
| 확보 완료 | [si_infographic_334.jpg](raw/event_2022/si_infographic_334.jpg) · 1,731,476 B | 서울연구원 2022-08-29 인포그래픽, 2,480 × 8,976 픽셀. 1분 AWS·ASOS 관측을 집계한 강남 1시간 최대 116.0 mm와 서초 110.5 mm는 원문에서 확인 가능하다. [게시물](https://www.si.re.kr/bbs/view.do?key=2024100042&pstSn=2208290002) · [본문 이미지](https://www.si.re.kr/common/ckeditor/getImg.do?upKey=bbs&dateKey=202208&fileName=1661737007001.jpg) |
| 확보 완료 | [seoul_city_emergency_briefing_20220812.pdf](raw/event_2022/seoul_city_emergency_briefing_20220812.pdf) · 1,129,536 B | 서울시 물순환안전국의 8월 12일 업무보고, 6쪽. 2~4쪽에 강우, 단계별 대응, 분리터널 통수, 서초 지하상가 피해가 있다. [시의회 첨부 원본](https://ms.smc.seoul.kr/record/appendixDownload.do?download=Y&key=0e4ffd51e00b3613782e78b385145bd61bd7ce551fdcf6469d7aea8106e159a895151257e1ff0461) |
| 확보 완료 | [seoul_council_disaster_review_2022.pdf](raw/event_2022/seoul_council_disaster_review_2022.pdf) · 1,030,214 B | 서울시의회 특별재난지역 지정 촉구 건의안 심사보고서, 13쪽. 7~8쪽의 피해 집계는 서울시 보고 범위이며 강남역 관측값으로 쓰지 않는다. [시의회 첨부 원본](https://ms.smc.seoul.kr/record/appendixDownload.do?key=5d847d1a4baecd320fed95a6f03663b80fb1d793fddd1d43cb32ae605d0213e53891085c8c2dc17a) |
| 확보 완료 | [seoul_mayor_20220808.html](raw/event_2022/seoul_mayor_20220808.html) · 37,648 B | 서울시 시장실 원문 HTML에 8월 8~9일의 상황 보고·현장 방문 시각이 있다. 21시 30분경 기록은 신논현역·신사역 현장 확인 시각이다. [서울시 원문](https://mayor.seoul.go.kr/oh/seoul/videoView.do?curPage=100&photoGallerySn=685) |
| 확보 완료 | [seoul_council_20230619.html](raw/event_2022/seoul_council_20230619.html) · 231,130 B | 서울시의회 제319회 회의록의 사후 발언에 8월 8일 역삼초교 교차로 일대 지하주차장 피해가 나온다. 침수 시작 시각과 깊이는 확인하지 못했다. [시의회 원문](https://mas.smc.seoul.kr/record/recordView.do?key=1eed6e7cb10c3bf05e1385259d319bed9259166fbc6d8800a73c850f2b625ba9cb2f02e36aa28eba) |

[사건 기록 CSV](processed/event_20220808_09.csv)에 KST 시각 또는 기간, 시각 정밀도, 위치, 관측 집계·행정 보고·사후 분석 구분, 값과 단위, 출처와 근거 위치를 남겼다. 시각을 확인한 행을 먼저 시간순으로 배치했다. 보고서의 강우 누적값은 각 집계 기간을 따른다. 2022년 8월 KRIHS 비교 침수면적(통수 전제 235→204 ha)은 사후 자료에 인용된 분석값이다. 유역분리터널의 실제 통수는 공식 기록에서 확인했으며 시간별 유량은 미확보다. 이 섹션의 PDF·JPG·HTML에는 공간 CRS가 없다. 원문 파일별 재배포 허락을 확인하지 못해 로컬 참고용으로 보관한다.

## 배수시설과 하수관망

2022년 관로 수위는 확보했다. 관망 연결, 배수분구 경계, 서초·사평 펌프장 제원과 실제 운영자료는 제공 신청이 필요하다.

| 상태 | 원본 파일 | 기준 시점과 검증 |
| --- | --- | --- |
| 확보 완료 | [하수관로_수위_현황_2022.zip](raw/drainage/하수관로_수위_현황_2022.zip) · 663,993,530 B | 2022년 1~12월 서울시 관로 수위, CP949로 읽을 수 있는 월별 CSV 12개, 전체 ZIP CRC 통과. 주요 필드는 고유번호, 구분코드·명, 측정일자, 측정수위, 통신상태다. 행에 좌표와 시차 표기가 없다. 서울시 API 명세에 수위 단위와 기준면 표기가 없어 적용 전 확인이 필요하다. 관측자료 이용허락범위 제한 없음. [서울특별시 물재생계획과 OA-2527](https://data.seoul.go.kr/dataList/OA-2527/F/1/datasetView.do) |
| 확보 완료 | [RAINPUMP.zip](raw/drainage/RAINPUMP.zip) · 5,949 B | 서울시 파일의 수정일은 2022-04-03이다. ZIP CRC와 Shapefile MultiPoint 118건을 확인했다. `PUMP_NM`에 서초·사평·반포·잠원 등이 있다. 배수구역 연결 확인에 쓸 수 있는 시설 위치 목록이다. `.prj`가 없어 포털의 EPSG:5186(미터) 선언을 참조한다. `.cpg`는 UTF-8로 되어 있지만 DBF 한국어는 CP949로 해독된다. 서초·사평의 `OPR_YN`·`EST_DT`는 공란이고 용량 필드가 없다. 이용허락범위 제한 없음. [서울특별시 치수안전과 OA-21179](https://data.seoul.go.kr/dataList/OA-21179/S/1/datasetView.do) |
| 부분 확보 | [seoul_drainage_pump_inventory_OA-15794.csv](raw/drainage/seoul_drainage_pump_inventory_OA-15794.csv) · 31,013 B | Sheet에서 내보낸 CP949 CSV 96행이다. 2012·2014·2015년 하천기본계획의 시설물명·주소·배수장 최대배수량·펌프규격·전양정·유수지용량 등을 담는다. 좌표와 필드별 수치 단위가 CSV에서 확인되지 않았다. 강남·서초구의 대치·양재 항목이 있고 핵심 대상인 서초·사평 펌프장 행은 없다. 자료는 역사적 설계 참고용이다. 공공누리 4유형(출처표시, 상업적 이용·변경 금지). [서울특별시·서울지방국토관리청 OA-15794](https://data.seoul.go.kr/dataList/OA-15794/S/1/datasetView.do) |
| 확보 완료 | [seoul_sewer_master_plan_2040_tancheon.pdf](raw/drainage/seoul_sewer_master_plan_2040_tancheon.pdf) · 46,539,626 B | 2024년 공개한 2040 하수도정비기본계획 제4장-3 탄천처리구역, PDF 352쪽을 열었다. PDF 184쪽(인쇄면 4-1714)은 서초3·4·5, 논현, 역삼이 강남역 중점관리지역이라고 명시한다. 같은 페이지의 1시간 110 mm는 상향한 방재성능목표 강우량이다. 관로별 설계 통수능·실제 유량의 단위는 별도 원자료에서 확인해야 한다. 공공누리 4유형. [서울특별시 물재생계획과 보고서 목록](https://news.seoul.go.kr/env/archives/561308) · [탄천처리구역 원본 PDF](https://news.seoul.go.kr/env/files/2024/12/6762120e0254a4.52248180.pdf) |
| 확보 완료 | [2022-07-19_seoul_council_311_2.pdf](raw/drainage/2022-07-19_seoul_council_311_2.pdf) · 247,821 B | 서울시의회 제311회 도시안전건설위원회 제2차 회의록 36쪽을 열었다. PDF 27쪽은 반포천 유역분리터널과 하수박스 연결을 2022년 5월에 마치고 6월부터 완전 통수했다고 기록한다. 공사 준공일은 9월 30일이다. 회의록에서 별도 재배포 조건을 확인하지 못했다. [서울시의회 회의록](https://ms.smc.seoul.kr/record/recordView.do?key=e7ba49cb4d2e17853d9c7380fa75c741bf86242b7fa8b21f4d1d5e0247922b419d32eae8515c179d) · [정보소통광장 원본 PDF](https://opengov.seoul.go.kr/og/com/download.php?dtype=basic&nid=29427101&rid=F0000073888665&uri=%2Ffiles%2Fdcdata%2F100050%2F20231011%2FF0000073888665.pdf) · [서울시 건설알림이](https://cis.seoul.go.kr/TotalAlimi_new/PopInfo.action?cmd=info1&pjt_cd=1112018013055) |
| 확보 완료 | [kwra_2026_swmm_banpo.pdf](raw/drainage/kwra_2026_swmm_banpo.pdf) · 4,423,977 B | 한국수자원학회 논문, PDF 15쪽. §3.1–3.3과 Fig. 1·3에 반포 배수구역 7개 분구, 서초·사평 펌프, 강우와 수위 관측 검증 조건이 있다. PDF 4·7쪽(인쇄면 134·137) 확인. 서울시가 제공한 자료의 누락값을 연구팀이 보완해 모형을 구성했다. 논문 페이지의 비상업 조건 문구와 CC BY 4.0 링크가 달라 재배포 조건은 학회 확인이 필요하다. [Kwon 외 2026 원문 및 발행 정보](https://jkwra.or.kr/articles/xml/rraX/) · [원본 PDF](https://jkwra.or.kr/articles/pdf/rraX/kwra-2026-059-02-0.pdf) |

서울시 수위 원본에서 8월 8~9일 서초구(22)·강남구(23) 센서 32개(각각 14·18개), 82,421행을 확인했다. 논문에서 사용한 서초 센서 `22-0002`, `22-0006`, `22-0010`, `22-0012`는 8월 8일 12시부터 9일 05시까지 각 718개 고유 시각에서 수위가 기록됐고 모두 통신양호였다. 1분·2분 간격이 주로 나타났으며 일부 간격은 더 길다. 포털의 30분 표기는 갱신 주기다. 서초와 강남 행은 행정구역 기준으로 확인했으므로 센서 좌표와 연결 관로 식별자를 받은 뒤 모형의 검증 지점으로 연결할 수 있다. 논문의 수위 그래프는 m 단위를 사용한다. [서울시 원본과 API](https://data.seoul.go.kr/dataList/OA-2527/A/1/datasetView.do) · [논문 §3.3 및 Fig. 3](https://jkwra.or.kr/articles/xml/rraX/)

[`sewer_water_level_2022-08-08_09_seocho_gangnam.csv`](processed/sewer_water_level_2022-08-08_09_seocho_gangnam.csv) (4,698,076 B)는 8월 원본에서 두 구의 8월 8~9일 관측만 선택한 UTF-8 BOM CSV다. 관측값과 여섯 컬럼을 유지하고 `측정일자`·`고유번호` 순서로 정렬했다. 관측값 공란 0개, 센서와 관측 시각이 같은 중복 0개, 통신양호 82,421행이며 빠진 분의 값을 보간하지 않았다.

8월 12일 서울시의회에서 물순환안전국장은 호우 당시 분리터널로 물이 흐르는 것을 확인했다고 답했다. 9월 20일 회의에서는 도시기반시설본부장이 터널이 만수로 흐른 것으로 보고받았고 통과량 통계를 보유한다고 답했다. 시각별 통과량은 확보하지 못했다. 서운로 등 관로 확장과 잠원·사평·반포 펌프 교체는 서울시가 2023~2024년 완료 사업으로 보고했다. [8월 12일 회의록](https://ms.smc.seoul.kr/record/recordView.do?key=b606eff5bb8b1b79f670fd2b6dd1eb18f6070d5d9446f34639a85eede92d405e7bfdc0e95bf4a1e2&memberName=) · [9월 20일 회의록](https://ms.smc.seoul.kr/record/recordView.do?key=277afdfa6afc969b0f11cce3c8969c29d67d8a17f1c648d66c3bec51bdb8a453541a7134d71eb65f&keyword=) · [서울시 후속 배수개선](https://news.seoul.go.kr/env/archives/559911)

### 배수자료 확보 순서

1. **신청 필요 — 2022-08-08 기준 하수도관리전산시스템의 관로·맨홀·토구 GIS와 배수분구 경계.** 서울시 물재생계획과 GIS(02-2133-3799), 강남구 치수과 하수팀(02-3423-6614), 서초구 물관리과 하수팀(02-2155-7140)이 신청 창구다. 서울시 GIS 구축 현황 및 연구진에 대한 제공 사례를 확인했다. 프로젝트 범위의 공개 GIS 다운로드 경로는 찾지 못했다. 서울기록원의 `RG303535-SR119889-FI84786-IT1204061`은 과거 논현·역삼·서초4·5의 1:600 관망도 목록이며 정보공개청구로 열람을 신청할 수 있다. 당시 관망에는 일정 기간 변경 이력이 필요하다. [서울시 하수도 GIS](https://news.seoul.go.kr/env/archives/747) · [강남구 치수과](https://www.gangnam.go.kr/dept/info/view.do?ndi_dept_id=3220204) · [서초구 물관리과](https://www.seocho.go.kr/site/seocho/group/emp2020/DepartList.do?searchCdIdx=d00000369) · [서울기록원 소장목록](https://archives.seoul.go.kr/item/1204061)
2. **신청 필요 — 펌프장 시설대장·반포천 분리터널 도면·2022년 8월 운전 기록.** 서울시 치수안전과(02-2133-3871 또는 OA-15794 제원 문의 02-2133-3880), 서초구 물관리과 기전팀, 서울시 도시기반시설본부에 문의한다. 2014년 논문은 서초펌프장 유수지 2,600 m³, 펌프 5대와 대당 분당토출량 280톤을 서술한다. 2022년 적용 및 실제 가동량은 미확인이다. 서울시는 2020년 빗물펌프장 시설용량 증대 타당성조사 용역과 2021년 증설 연차별 추진계획(하천관리과-12672)을 보유한 것으로 시의회 자료에서 확인된다. [서초 펌프장 2014년 연구 56쪽](https://journal.kci.go.kr/cemtp/archive/articlePdf?artiId=ART001908665) · [2026년도 시의회 예산 예비심사 자료](https://ms.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0070043.pdf?time=20260522110638)
3. **신청 필요 — SWMM 입력과 배수분구별 설계 조건.** 배수분구별 관망 연결과 소유역의 면적·불투수율·유출계수·계획 배수량 자료를 서울시 물재생계획과에 문의한다. 2017년 연구는 요청한 5개 분구(7.4 km²), 2026년 연구는 서초1·2를 포함한 7개 분구(12.40 km²)를 사용했다. 2026년 연구팀의 검증용 SWMM `.inp`, 소유역 GIS, 보완값 목록, 관측소 대응표 공개 첨부는 확인하지 못했다. 한국환경연구원 교신저자 또는 연구진에 제공 가능 범위를 문의한다. [5개 분구 선행연구](https://www.j-komes.or.kr/_PR/view/?aidx=10923&bidx=817) · [2026년 연구 논문](https://jkwra.or.kr/articles/xml/rraX/)

**정보공개청구 문안**

> 2022년 8월 8~9일 서울 강남역 일대 침수 재현 연구를 위해, 반포 배수구역의 논현·역삼·서초3·4·5 배수분구와 직접 연결되는 상·하류(서초1·2, 반포천 방류구 포함)의 2022년 8월 8일 기준 공공하수도 자료를 요청합니다. 배수분구 경계와 ID, 관로·맨홀·토구·빗물받이 GIS 및 시설물대장, 상·하류 연결 ID, 관경·단면·길이·경사·관저고·지반고·조도계수, 관로별 설계 최대 통수능(m³/s), 배수분구별 설계 배수량 및 유출계수가 있는 부분을 제공해 주십시오. 서초·사평 빗물펌프장과 연결 시설, 반포천 유역분리터널, 서운로 저지고지수로의 시설물대장·준공도면·변경 이력(통수 개시일 포함)과 8월 7~10일(KST) 가동·장애·수위·유량·토출량·수문 개도 기록도 요청합니다. 수위 센서 ID와 좌표·연결 관로, 측정 단위·기준고·관측 간격, 보유 시 SWMM 입력 파일과 입력값의 기준 시점을 포함해 주십시오. 공간자료는 보유한 원본 형식(GPKG, SHP, DWG/DXF 등), 시계열과 속성은 CSV 등 전자파일로 요청하며 좌표계·단위·필드 설명을 함께 부탁드립니다. 제공이 제한되는 항목은 공개 가능한 필드·공간 범위의 부분 제공 또는 열람 절차와 보유 부서를 안내해 주십시오.

[정보공개포털](https://www.open.go.kr) · [공공데이터 제공 신청](https://www.data.go.kr/tcs/dor/insertDataOfferReqstProcssView.do)

서울 열린데이터광장 다운로드 요청은 POST다. OA-2527은 `https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false`에 `infId=OA-2527&infSeq=3&seq=13&seqNo=`, OA-21179는 같은 주소에 `infId=OA-21179&infSeq=2&seq=1&seqNo=`를 보낸다. OA-15794의 CSV는 [Sheet 화면](https://data.seoul.go.kr/dataList/sheetView.do?infId=OA-15794&srvType=S)이 `https://datafile.seoul.go.kr/bigfile/iot/sheet/csv/download.do`에서 내보낸 파일이다.


## 재현 범위와 다음 작업

현재 자료로 KST 기준 10분 강우 스트리밍 입력을 만들고, 30 m급 지형에서 강남역 주변 저지대를 확인하며, 관측된 침수 폴리곤으로 모의 침수 범위를 비교할 수 있다. 강남·서초 수위 시계열은 센서와 관로의 연결을 확보한 뒤 수위 검증에 쓸 수 있다. 지하공간별 침수 시작 시각, 시간별 지표 침수심과 실제 배수량을 수치로 검증할 자료는 부족하다.

구현을 시작할 때는 10분 CSV를 시각·관측소 ID 순서로 읽고 관측 누락을 별도로 전달한다. 공간 검증 입력은 지형 GeoTIFF와 침수 폴리곤을 같은 수평 좌표계로 맞춰 읽는다. 고도와 시설 수위의 수직 기준을 확인하기 전에는 두 값을 직접 대조하지 않는다.

추가 확보는 당시 관망·배수분구 GIS와 시설 가동 기록을 우선한다. 다음으로 2022년 기준 관측소 경위도와 1~5 m급 지형을 받으면 관측 강우의 공간 보간과 도로 단위 해석을 준비할 수 있다. 지점별 침수 개시·심화·해소 시각이 필요하면 서울시 재난안전대책본부와 강남·서초 관할 구청의 8월 8~9일 상황일지, 도로 통제 시각, 현장 수위·침수심 관측자료 중 공개 가능한 범위를 요청한다.

수집 전 저장소에 별도 Git 제외 규칙은 없었다. 연간 수위 ZIP, 하수도정비기본계획 PDF, FABDEM 원본 타일은 Dataset/.gitignore로 기본 스테이징에서 제외했다. 원본은 로컬에 보관한다.
