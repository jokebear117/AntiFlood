const el = (id) => document.getElementById(id);
const statusLabels = {
  ready: "대기", idle: "대기", running: "계산 중", paused: "일시정지",
  completed: "계산 완료", error: "오류",
};
const actionLabels = {start: "시작", pause: "일시정지", resume: "재개"};
const pointHint = "지도에서 위치를 선택하면 셀 수심과 Tile 상태를 확인할 수 있어요.";
const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});

let health;
let catalog = [];
let map;
let metadata;
let mapReady = false;
let replayState = {status: "idle"};
let runId;
let frames = [];
let frameIndex = -1;
let follow = true;
let shownFrame;
let pendingFrame;
let viewVersion = 0;
let pointVersion = 0;
let selectedPoint;
let marker;
let busy = false;
let polling = false;
let commandVersion = 0;
let selectedBounds = [127.005,37.470,127.065,37.535];
let selecting = false;
let firstCorner;
let archivedRun;
let regionReady = false;
let regionVersion = 0;
const presets = {
  gangnam: [127.005,37.470,127.065,37.535],
  yeouido: [126.90,37.515,126.945,37.545],
  mapo: [126.90,37.545,126.95,37.58],
  songpa: [127.075,37.49,127.13,37.53],
};
function settings() {
  return {bounds:selectedBounds, drain_mm_h:Number(el("drain").value),
          threads:Number(el("threads").value), boundary:el("boundary").value};
}
function polygon(bounds) {
  const [w,s,e,n] = bounds;
  return {type:"Feature",properties:{},geometry:{type:"Polygon",coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}};
}
function updateDomain(bounds, fit=false) {
  if (!mapReady) return;
  map.getSource("domain").setData(polygon(bounds));
  if (fit) map.fitBounds([[bounds[0],bounds[1]],[bounds[2],bounds[3]]], {padding:45,duration:0});
}
async function previewRegion(fit=true) {
  const version = ++regionVersion;
  regionReady = false;
  renderState(replayState);
  el("region-info").textContent = "지형과 강우 관측을 확인하는 중";
  try {
    const data = await post("/api/region", settings());
    if (version !== regionVersion) return;
    catalog = data.scenarios;
    el("scenario").replaceChildren(...catalog.map(item=>new Option(item.title,item.id)));
    regionReady = true;
    el("region-info").textContent = `${data.map.valid_cell_count.toLocaleString()} 셀 · 메모리 약 ${data.estimated_memory_mb} MB${data.warning ? " · "+data.warning : ""}`;
    updateDomain(selectedBounds,fit);
    if (!archivedRun && !replayState.run_id) {
      metadata = {...metadata, ...data.map};
      renderMapMetadata();
      updateDomain(selectedBounds,fit);
    }
  } catch(error) {
    if (version === regionVersion) {
      el("region-info").textContent = error.message;
      el("scenario").replaceChildren();
    }
  } finally { if (version === regionVersion) renderState(replayState); }
}
function areaName(bounds) {
  const names = {gangnam:"강남역",yeouido:"여의도",mapo:"마포",songpa:"송파"};
  const key = Object.keys(presets).find(key => presets[key].every((n,i)=>Math.abs(n-bounds[i])<.00001));
  return key ? names[key] : `${((bounds[1]+bounds[3])/2).toFixed(3)}°N ${((bounds[0]+bounds[2])/2).toFixed(3)}°E`;
}
async function refreshHistory() {
  const previous = el("history").value;
  const runs = await api("/api/runs");
  el("history").replaceChildren(new Option("기록 선택", ""), ...runs.map(run=>new Option(
    `${areaName(run.map.bounds)} · ${run.scenario.title} · ${run.settings?.drain_mm_h ?? run.map.default_drain_mm_h} mm/h · ${run.frame_count}장 · ${run.id.slice(0,6)}`,run.id)));
  el("history").value = previous;
}
async function openHistory() {
  const id = el("history").value;
  if (!id) return;
  try {
    const run = await api(`/api/runs/${id}`);
    commandVersion += 1;
    archivedRun = run;
    resetTimeline(run.id);
    metadata = {...metadata,...run.map};
    frames = run.frames;
    renderMapMetadata();
    updateDomain(metadata.bounds,true);
    renderState({...replayState});
    await selectFrame(frames.length-1);
    el("live").hidden=false;
    el("reuse").disabled=false;
    el("question").disabled=el("ask").disabled=true;
    el("history-info").textContent = `저장 결과 ${run.id.slice(0,8)} · ${{completed:"완료",stopped:"중단",interrupted:"서버 종료로 중단",running:"계산 중",paused:"일시정지",error:"오류",archived:"이전 기록"}[run.status] || run.status} · ${run.frames.length}장`;
  } catch(error) { notice(error.message); }
}

function formatTime(value) {
  return value ? dateFormat.format(new Date(value)) : "—";
}

async function api(path, settings) {
  const response = await fetch(path, settings);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "서버 응답을 읽지 못했어요.");
  }
  return response.json();
}

function post(path, body) {
  return api(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body ?? {}),
  });
}

function notice(message) {
  el("notice").hidden = !message;
  el("notice").textContent = message || "";
}

function mapMessage(message) {
  el("map-error").hidden = !message;
  el("map-error").textContent = message || "";
}

function setEndpoints() {
  const scenario = catalog.find((item) => item.id === (replayState.scenario_id || el("scenario").value));
  el("time-start").textContent = formatTime(frames[0]?.time || scenario?.start);
  el("time-end").textContent = formatTime(frames.at(-1)?.time || scenario?.end);
}

function renderState(state) {
  replayState = state;
  const status = el("status");
  status.textContent = statusLabels[state.status] || statusLabels.idle;
  status.dataset.status = state.status;
  el("computed-time").textContent = formatTime(state.simulated_time_utc);
  const operation = {running: "pause", paused: "resume"}[state.status] || "start";
  const primary = el("primary");
  primary.dataset.operation = operation;
  primary.textContent = actionLabels[operation];
  primary.disabled = busy || !health?.replay_ready || (!regionReady && operation === "start");
  el("progress").value = state.progress || 0;
  el("progress-label").textContent = `${Math.round((state.progress || 0)*100)}%`;
  for (const id of ["area","select-area","drain","threads","boundary"]) {
    el(id).disabled = busy || state.status === "running" || state.status === "paused";
  }
  const hasSession = state.status === "running" || state.status === "paused";
  el("scenario").disabled = busy || hasSession || catalog.length === 0;
  el("reset").disabled = busy || !state.run_id;
  if (state.error) notice(state.error);
  setEndpoints();
}

function renderFrameDetails(frame) {
  el("frame-time").textContent = formatTime(frame?.time);
  el("depth").textContent = frame ? `${frame.max_depth_m.toFixed(3)} m` : "—";
  el("rain").textContent = frame ? `${frame.rain_max_mm.toFixed(1)} mm` : "—";
  el("tiles").textContent = frame ? frame.active_tile_count.toLocaleString("ko-KR") : "—";
  el("cells").textContent = frame ? frame.active_cell_count.toLocaleString("ko-KR") : "—";
  el("workers").textContent = frame ? frame.worker_count.toString() : "—";
  el("observed").textContent = formatTime(frame?.rain_observed_at);
  el("timeline").setAttribute("aria-valuetext", formatTime(frame?.time));
}

function removeFrame() {
  viewVersion += 1;
  pointVersion += 1;
  pendingFrame = shownFrame = selectedPoint = undefined;
  marker?.remove();
  if (mapReady && map.getLayer("flood")) {
    map.removeLayer("flood");
    map.removeSource("depth");
  }
  renderFrameDetails(null);
  el("point").textContent = pointHint;
}

function resetTimeline(id) {
  runId = id;
  frames = [];
  frameIndex = -1;
  follow = true;
  removeFrame();
  updateTimeline();
}

function updateTimeline() {
  const slider = el("timeline");
  slider.max = Math.max(0, frames.length - 1);
  slider.value = Math.max(frameIndex, 0);
  slider.disabled = frames.length < 2;
  el("latest").disabled = follow || !frames.length;
  setEndpoints();
}

async function selectFrame(index) {
  frameIndex = index;
  updateTimeline();
  const frame = frames[index];
  if (!frame || frame.id === shownFrame?.id || frame.id === pendingFrame) return;
  if (!mapReady) {
    renderFrameDetails(frame);
    return;
  }
  const version = ++viewVersion;
  pendingFrame = frame.id;
  try {
    const image = new Image();
    image.src = `/api/frames/${frame.id}.png`;
    await image.decode();
    if (version !== viewVersion || index !== frameIndex) return;

    // Use the decoded image so the selected timestamp and the visible raster change together.
    const source = map.getSource("depth");
    if (source) {
      source.updateImage({image});
    } else {
      map.addSource("depth", {type: "image", coordinates: metadata.frame_coordinates});
      map.getSource("depth").updateImage({image});
      map.addLayer({
        id: "flood", type: "raster", source: "depth",
        paint: {"raster-fade-duration": 0, "raster-resampling": "nearest"},
      }, "domain-outline");
    }
    shownFrame = frame;
    renderFrameDetails(frame);
    if (selectedPoint) await showPoint(selectedPoint, frame);
  } catch {
    if (version === viewVersion) {
      mapMessage("수심 지도를 불러오지 못했어요. 시간 슬라이더에서 결과를 다시 선택해 주세요.");
    }
  } finally {
    if (version === viewVersion) pendingFrame = undefined;
  }
}

async function showPoint(point, frame = shownFrame) {
  const version = ++pointVersion;
  if (!frame) {
    el("point").textContent = "계산 결과가 생기면 선택한 위치의 수심을 표시해요.";
    return;
  }
  el("point").textContent = "선택 위치의 수심을 조회하는 중";
  const search = new URLSearchParams({lon: point.lng, lat: point.lat});
  try {
    const result = await api(`/api/frames/${frame.id}/point?${search}`);
    if (version !== pointVersion) return;
    const rain = result.rain.map((item) => `${item.name} ${item.mm.toFixed(1)} mm`).join(" / ");
    el("point").textContent =
      `셀 수심 ${result.depth_m.toFixed(3)} m · Tile ${result.tile_id}\n` +
      `${result.active ? "최근 계산에 포함" : "최근 계산에서 제외"} · 10분 우량 ${rain}`;
  } catch (error) {
    if (version === pointVersion) el("point").textContent = error.message;
  }
}

async function poll() {
  if (polling || busy || archivedRun || !health?.replay_ready) return;
  polling = true;
  const version = commandVersion;
  try {
    const state = await api("/api/simulation/state");
    if (version !== commandVersion) return;
    if (state.run_id !== runId) {
      resetTimeline(state.run_id);
      if (state.run_id) {
        const run = await api(`/api/runs/${state.run_id}`);
        metadata = {...metadata,...run.map};
        renderMapMetadata();
        updateDomain(metadata.bounds);
      }
    }
    const previousStatus = replayState.status;
    renderState(state);
    if (state.frame_count > frames.length) {
      const batch = await api(`/api/simulation/frames?offset=${frames.length}`);
      if (version !== commandVersion || batch.run_id !== runId) return;
      frames.push(...batch.frames);
    }
    if (follow && frames.length) await selectFrame(frames.length - 1);
    updateTimeline();
    if ((state.status === "completed" || state.status === "error") && previousStatus !== state.status) void refreshHistory();
  } catch {
    if (version === commandVersion) notice("서버 상태를 읽지 못했어요. 로컬 서버가 실행 중인지 확인해 주세요.");
  } finally {
    polling = false;
  }
}

async function command(operation) {
  if (busy) return;
  busy = true;
  commandVersion += 1;
  notice("");
  renderState(replayState);
  try {
    const body = operation === "start" ? {...settings(),scenario_id: el("scenario").value} : undefined;
    if (operation === "start" || operation === "reset") {
      archivedRun=undefined;
      el("live").hidden=true;
      el("history-info").textContent="";
      el("reuse").disabled=true;
    }
    const state = await post(`/api/simulation/${operation}`, body);
    if (state.run_id !== runId) resetTimeline(state.run_id);
    if (operation === "start") {
      const run = await api(`/api/runs/${state.run_id}`);
      metadata = {...metadata,...run.map};
      renderMapMetadata();
      updateDomain(metadata.bounds,true);
    }
    renderState(state);
    void refreshHistory();
  } catch (error) {
    notice(error.message);
  } finally {
    busy = false;
    renderState(replayState);
    void poll();
  }
}

function renderMapMetadata() {
  const [west, south, east, north] = metadata.bounds;
  el("scope").textContent = `${south.toFixed(3)}–${north.toFixed(3)}°N, ${west.toFixed(3)}–${east.toFixed(3)}°E`;
  const drain = {
    assumed: metadata.drainage_raster_source
      ? (metadata.drainage_fallback_cells
        ? `가정 배수율 지도 · 빈 셀 ${metadata.default_drain_mm_h} mm/h`
        : "가정 배수율 지도")
      : `가정 배수율 ${metadata.default_drain_mm_h} mm/h`,
    mixed: `입력 배수율과 가정값 ${metadata.default_drain_mm_h} mm/h`,
    observed: "지역별 배수율 입력",
  }[metadata.drainage_source];
  const boundary = metadata.boundary === "open" ? "외곽 유출 허용" : "닫힌 외곽";
  el("assumptions").textContent =
    `30 m 지형 격자 · ${drain} · ${boundary}. 가장 가까운 관측소의 10분 우량을 구간 안에서 일정하게 적용해요.`;
  el("legend").replaceChildren();
  metadata.legend.forEach((bin, i) => {
    const segment = document.createElement("span");
    const swatch = document.createElement("i");
    const next = metadata.legend[i + 1];
    segment.className = "legend-bin";
    swatch.style.backgroundColor = `rgb(${bin.rgb.join(",")})`;
    segment.append(swatch, next ? `${bin.min_m}–${next.min_m}` : `${bin.min_m} 이상`);
    el("legend").append(segment);
  });
  el("legend").closest(".legend").hidden = false;
}

async function initMap() {
  metadata = await api("/api/map");
  renderMapMetadata();
  if (!health.map_ready) throw new Error("MapLibre 파일이 없어요. README의 데이터 준비 명령을 실행해 주세요.");
  const {Map, Marker, NavigationControl, ScaleControl, AttributionControl} = await import("/assets/vendor/maplibre-gl.mjs");
  const [west, south, east, north] = metadata.bounds;
  const bounds = [[west, south], [east, north]];
  const tileTemplate = `${window.location.origin}/api/terrain/{z}/{x}/{y}.png`;
  const rasterBounds = [126.7,37.4,127.2,37.72];
  const coverage = metadata.dem_bounds.map(([w,s,e,n])=>polygon([Math.max(w,126.7),Math.max(s,37.4),Math.min(e,127.2),Math.min(n,37.72)]));
  map = new Map({
    container: "map", bounds, fitBoundsOptions: {padding: 45},
    pitch: 42, maxPitch: 70, maxZoom: 17, minZoom: 10, attributionControl: false,
    style: {
      version: 8,
      sources: {
        dem: {type: "raster-dem", tiles: [tileTemplate], tileSize: 256, maxzoom: 13, bounds: rasterBounds, encoding: "terrarium",
              attribution: '<a href="https://doi.org/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn">FABDEM V1-2 · Bristol/Fathom · CC BY-NC-SA 4.0</a>'},
        osm: {type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256,
              maxzoom: 19, attribution: '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>'},
        coverage: {type:"geojson",data:{type:"FeatureCollection",features:coverage}},
        domain: {type: "geojson", data: {
          type: "Feature", properties: {},
          geometry: {type: "Polygon", coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
        }},
      },
      layers: [
        {id: "background", type: "background", paint: {"background-color": "#dfe7e3"}},
        {id: "streets", type: "raster", source: "osm", layout: {visibility: "none"}, paint: {"raster-opacity": .82, "raster-saturation": -.55}},
        {id: "relief", type: "hillshade", source: "dem", paint: {"hillshade-shadow-color": "#426462", "hillshade-highlight-color": "#fffdf4", "hillshade-exaggeration": .58}},
        {id:"coverage-outline",type:"line",source:"coverage",paint:{"line-color":"#47765f","line-width":1,"line-dasharray":[5,3]}},
        {id: "domain-outline", type: "line", source: "domain", paint: {"line-color": "#27596d", "line-width": 2, "line-dasharray": [3, 2]}},
      ],
      terrain: {source: "dem", exaggeration: 1},
    },
  });
  map.setMaxBounds([[126.68,37.38],[127.22,37.74]]);
  map.addControl(new NavigationControl({visualizePitch: true}), "top-right");
  map.addControl(new ScaleControl({unit: "metric"}), "bottom-right");
  map.addControl(new AttributionControl({compact: false}), "bottom-right");
  map.on("error", (event) => {
    if (event.sourceId === "osm") {
      mapMessage("도로 지도에 연결하지 못했어요. 3D 지형과 수심은 계속 볼 수 있어요.");
    } else if (event.sourceId === "dem") {
      mapMessage("3D 지형을 불러오지 못했어요. 로컬 서버 상태를 확인해 주세요.");
    } else {
      console.error(event.error);
    }
  });
  map.on("load", () => {
    updateDomain(metadata.bounds);
    mapReady = true;
    map.jumpTo({pitch: 42});
    for (const id of ["fit", "pitch", "streets"]) el(id).disabled = false;
    if (west < 127.027539 && east > 127.027539 && south < 37.497958 && north > 37.497958) {
      const label = document.createElement("span");
      label.className = "map-name";
      label.textContent = "강남역";
      new Marker({element: label, anchor: "bottom"}).setLngLat([127.027539, 37.497958]).addTo(map);
    }
    if (frameIndex >= 0) void selectFrame(frameIndex);
  });
  el("fit").addEventListener("click", () => updateDomain(archivedRun ? archivedRun.map.bounds : selectedBounds,true));
  el("pitch").addEventListener("click", () => {
    const enabled = el("pitch").getAttribute("aria-pressed") !== "true";
    el("pitch").setAttribute("aria-pressed", enabled);
    map.setTerrain(enabled ? {source: "dem", exaggeration: 1} : null);
    map.jumpTo({pitch: enabled ? 42 : 0});
  });
  el("streets").addEventListener("click", () => {
    const enabled = el("streets").getAttribute("aria-pressed") !== "true";
    el("streets").setAttribute("aria-pressed", enabled);
    map.setLayoutProperty("streets", "visibility", enabled ? "visible" : "none");
    if (!enabled) mapMessage("");
  });
  map.on("click", (event) => {
    if (selecting) {
      if (!firstCorner) {
        firstCorner = event.lngLat;
        el("region-info").textContent="대각선의 반대쪽 꼭짓점을 선택해 주세요.";
      } else {
        selectedBounds = [Math.min(firstCorner.lng,event.lngLat.lng),Math.min(firstCorner.lat,event.lngLat.lat),
                          Math.max(firstCorner.lng,event.lngLat.lng),Math.max(firstCorner.lat,event.lngLat.lat)];
        selecting=false;
        firstCorner=undefined;
        el("map").classList.remove("map-selecting");
        el("select-area").textContent="영역 선택";
        updateDomain(selectedBounds);
        void previewRegion(false);
      }
      return;
    }
    selectedPoint = event.lngLat;
    marker ??= new Marker({color: "#164e80", scale: .65});
    marker.setLngLat(selectedPoint).addTo(map);
    void showPoint(selectedPoint);
  });
}

async function init() {
  try {
    [health, catalog] = await Promise.all([api("/api/health"), api("/api/scenarios")]);
    for (const item of catalog) el("scenario").add(new Option(item.title, item.id));
    el("question").disabled = el("ask").disabled = !(health.agent_ready && health.replay_ready);
    if (!health.agent_ready) el("agent-status").textContent = "서버에 UPSTAGE_API_KEY를 설정하면 질문할 수 있어요.";
    renderState({status: health.replay_ready ? "ready" : "error", error: health.error});
    await initMap();
    await previewRegion(false);
    void refreshHistory();
    if (health.replay_ready) {
      void poll();
      window.setInterval(poll, 700);
    }
  } catch {
    renderState({status: "error", error: "로컬 서버에 연결할 수 없어요. 실행 후 이 페이지를 새로고침해 주세요."});
  }
}

el("primary").addEventListener("click", () => command(el("primary").dataset.operation));
el("reset").addEventListener("click", () => command("reset"));
el("scenario").addEventListener("change", setEndpoints);
el("timeline").addEventListener("input", (event) => {
  const index = Number(event.target.value);
  follow = index === frames.length - 1;
  void selectFrame(index);
});
el("latest").addEventListener("click", () => {
  follow = true;
  void selectFrame(frames.length - 1);
});
el("agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = el("question").value.trim();
  if (!question) return;
  el("ask").disabled = true;
  el("answer").textContent = "최신 계산 결과를 확인하는 중";
  try {
    const result = await post("/api/agent/query", {question});
    el("answer").textContent = result.answer;
  } catch (error) {
    el("answer").textContent = error.message;
  } finally {
    el("ask").disabled = false;
  }
});

el("area").addEventListener("change", () => {
  if (presets[el("area").value]) {
    selectedBounds=presets[el("area").value];
    void previewRegion();
  } else el("select-area").click();
});
el("select-area").addEventListener("click", () => {
  selecting=!selecting;
  firstCorner=undefined;
  el("area").value="custom";
  el("map").classList.toggle("map-selecting",selecting);
  el("select-area").textContent=selecting ? "선택 취소" : "영역 선택";
  el("region-info").textContent=selecting ? "계산 사각형의 두 꼭짓점을 차례로 선택해 주세요." : "영역 선택을 취소했어요.";
});
el("seoul").addEventListener("click", () => map?.fitBounds([[126.75,37.42],[127.18,37.70]],{padding:25,duration:0}));
el("open-run").addEventListener("click",openHistory);
el("live").addEventListener("click", () => {
  archivedRun=undefined;
  el("question").disabled=el("ask").disabled=!(health.agent_ready && health.replay_ready);
  el("live").hidden=true;
  el("history-info").textContent="";
  resetTimeline(undefined);
  void poll();
});
el("reuse").addEventListener("click", async () => {
  if (!archivedRun) return;
  const run = archivedRun;
  const config = run.settings || {bounds:run.map.bounds,drain_mm_h:run.map.default_drain_mm_h,threads:run.threads_requested,boundary:run.map.boundary};
  selectedBounds=config.bounds;
  el("drain").value=config.drain_mm_h;
  el("threads").value=config.threads;
  el("boundary").value=config.boundary;
  el("area").value="custom";
  await previewRegion(false);
  el("scenario").value=run.scenario.id;
  notice("저장된 조건을 불러왔어요. 실행 중인 계산이 있으면 초기화 후 시작해 주세요.");
});
void init();
