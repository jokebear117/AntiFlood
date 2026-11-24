const el = (id) => document.getElementById(id);
const statusLabels = {
  ready: "계산 대기", idle: "계산 대기", running: "계산 중", paused: "일시 정지",
  completed: "계산 완료", error: "실행 오류",
};
const actionLabels = {start: "계산 시작", pause: "일시 정지", resume: "계산 재개"};
const pointHint = "지도에서 지점을 선택해 모의 수심과 타일 상태를 확인하세요";
const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", month: "long", day: "numeric",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});
const scenarioOption = ({title, id}) => new Option(title.replace(/ KST$/, ""), id);

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
let mapBounds = selectedBounds;
let draftBounds;
let selecting = false;
let firstCorner;
let archivedRun;
let historyVersion = 0;
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
function fitRegion(bounds) {
  const padding = Math.min(44, Math.round(map.getContainer().clientHeight * 0.1));
  map.fitBounds([[bounds[0],bounds[1]],[bounds[2],bounds[3]]], {padding, duration: 0});
}
function updateDraft(bounds) {
  draftBounds = bounds?.some((value, i) => value !== mapBounds[i]) ? bounds : undefined;
  el("draft-key").hidden = !draftBounds;
  if (mapReady) map.getSource("draft").setData(draftBounds ? polygon(draftBounds) : {type: "FeatureCollection", features: []});
}
function updateDomain(bounds, fit=false) {
  mapBounds = bounds;
  updateDraft();
  el("map-title").textContent = areaName(bounds);
  if (!mapReady) return;
  map.getSource("domain").setData(polygon(bounds));
  if (fit) fitRegion(bounds);
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
    const previousScenario = el("scenario").value;
    el("scenario").replaceChildren(...catalog.map(scenarioOption));
    if (catalog.some(item => item.id === previousScenario)) el("scenario").value = previousScenario;
    regionReady = true;
    el("region-info").textContent = `셀 ${data.map.valid_cell_count.toLocaleString("ko-KR")}개\n메모리 약 ${data.estimated_memory_mb} MB${data.warning ? "\n"+data.warning : ""}`;
    if (!archivedRun && !replayState.run_id) {
      metadata = {...metadata, ...data.map};
      renderMapMetadata();
      updateDomain(selectedBounds,fit);
    } else {
      updateDraft(selectedBounds);
      if (fit && mapReady) fitRegion(selectedBounds);
    }
  } catch(error) {
    if (version === regionVersion) {
      el("region-info").textContent = error.message;
      el("scenario").replaceChildren();
    }
  } finally { if (version === regionVersion) renderState(replayState); }
}
function presetKey(bounds) {
  return Object.keys(presets).find(key => presets[key].every((value, i) => Math.abs(value - bounds[i]) < .00001));
}
function areaName(bounds) {
  const names = {gangnam:"강남역 주변",yeouido:"여의도 주변",mapo:"마포 주변",songpa:"송파 주변"};
  const key = presetKey(bounds);
  return key ? names[key] : `북위 ${((bounds[1]+bounds[3])/2).toFixed(3)}°, 동경 ${((bounds[0]+bounds[2])/2).toFixed(3)}° 중심`;
}
async function refreshHistory() {
  const previous = el("history").value;
  const runs = await api("/api/runs");
  el("history").replaceChildren(new Option(runs.length ? "기록 선택" : "저장된 실행 없음", ""), ...runs.map(run=>new Option(
    `${areaName(run.map.bounds)}, ${run.frame_count}개 (${run.id.slice(0,6)}) / ${run.scenario.title} / 배수율 ${run.settings?.drain_mm_h ?? run.map.default_drain_mm_h} mm/h`,run.id)));
  el("history").value = previous;
  el("open-run").disabled = !el("history").value;
  el("reuse").disabled = !archivedRun || archivedRun.id !== el("history").value;
}
async function openHistory() {
  const version = ++historyVersion;
  const id = el("history").value;
  if (!id) return;
  try {
    const run = await api(`/api/runs/${id}`);
    if (version !== historyVersion) return;
    commandVersion += 1;
    archivedRun = run;
    resetTimeline(run.id);
    metadata = {...metadata,...run.map};
    frames = run.frames;
    renderMapMetadata();
    updateDomain(metadata.bounds,true);
    renderState({...replayState});
    await selectFrame(frames.length-1);
    if (version !== historyVersion) return;
    el("reuse").disabled=false;
    el("question").disabled=el("ask").disabled=true;
    const historyStatus = {completed:"완료",stopped:"중단",interrupted:"서버 종료로 중단",running:"계산 중",paused:"일시 정지",error:"오류",archived:"이전 기록"}[run.status] || run.status;
    el("history-info").textContent = `저장된 시각 ${run.frames.length}개 (${historyStatus})`;
    el("history-info").hidden = false;
    el("frame-label").focus();
  } catch(error) { if (version === historyVersion) notice(error.message); }
}

function formatTime(value) {
  return value ? dateFormat.format(new Date(value)) : "—";
}

async function api(path, settings) {
  const response = await fetch(path, settings);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "요청에 실패했습니다. 입력값을 확인하고 다시 시도하세요.");
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

function setAreaSelection(enabled, keepBounds = false) {
  selecting = enabled;
  firstCorner = undefined;
  if (!enabled && !keepBounds) {
    el("area").value = presetKey(selectedBounds) ?? "custom";
  }
  el("map").classList.toggle("map-selecting", enabled);
  el("select-area").setAttribute("aria-expanded", enabled);
  el("select-area").textContent = enabled ? "범위 지정 취소" : "지도에서 지정";
  el("selection-guide").hidden = !enabled;
  el("selection-hint").textContent = enabled ? "계산 범위의 첫 꼭짓점을 선택하세요" : "";
  renderState(replayState);
}

function renderState(state) {
  replayState = state;
  const status = el("status");
  const label = statusLabels[state.status] || statusLabels.idle;
  if (status.textContent !== label) status.textContent = label;
  status.dataset.status = state.status;
  el("computed-time").textContent = formatTime(state.simulated_time_utc);
  const operation = {running: "pause", paused: "resume"}[state.status] || "start";
  const primary = el("primary");
  primary.dataset.operation = operation;
  primary.textContent = actionLabels[operation];
  primary.disabled = busy || !health?.replay_ready || (operation === "start" && (!regionReady || selecting || !catalog.length));
  el("progress").value = state.progress || 0;
  el("progress-label").textContent = `${Math.round((state.progress || 0)*100)}%`;
  for (const id of ["area","drain","threads","boundary"]) {
    el(id).disabled = busy || state.status === "running" || state.status === "paused";
  }
  const hasSession = state.status === "running" || state.status === "paused";
  el("select-area").disabled = busy || hasSession || !mapReady;
  el("scenario").disabled = busy || hasSession || catalog.length === 0;
  el("reset").disabled = busy || !state.run_id;
  if (state.error) notice(state.error);
}

function renderFrameDetails(frame) {
  el("frame-time").textContent = frame ? formatTime(frame.time) : "저장된 결과 없음";
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
  const source = el("frame-source");
  source.hidden = !archivedRun && !runId;
  source.textContent = archivedRun ? "저장된 실행" : "현재 실행";
  slider.max = Math.max(0, frames.length - 1);
  slider.value = Math.max(frameIndex, 0);
  slider.disabled = frames.length < 2;
  el("latest").disabled = follow || !frames.length;
  el("latest").textContent = archivedRun ? "마지막 저장 시각으로" : "최신 시각으로";
  el("live").hidden = !archivedRun;
  el("time-start").parentElement.hidden = frames.length < 2;
  el("time-start").textContent = formatTime(frames[0]?.time);
  el("time-end").textContent = formatTime(frames.at(-1)?.time);
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
      mapMessage("수심 지도를 불러오지 못했습니다. 시간 막대에서 시각을 다시 선택하세요.");
    }
  } finally {
    if (version === viewVersion) pendingFrame = undefined;
  }
}

async function showPoint(point, frame = shownFrame) {
  const version = ++pointVersion;
  if (!frame) {
    el("point").textContent = "계산 결과를 저장하면 선택한 지점의 모의 수심을 표시합니다";
    return;
  }
  el("point").textContent = "선택한 지점의 수심을 불러오는 중";
  const search = new URLSearchParams({lon: point.lng, lat: point.lat});
  try {
    const result = await api(`/api/frames/${frame.id}/point?${search}`);
    if (version !== pointVersion) return;
    const rain = result.rain.map((item) => `${item.name} ${item.mm.toFixed(1)} mm`).join(", ");
    el("point").textContent =
      `모의 수심 ${result.depth_m.toFixed(3)} m, 타일 ${result.tile_id} (${result.active ? "계산에 포함" : "계산에서 제외"})\n` +
      `10분 강우량 ${rain || "자료 없음"}`;
  } catch (error) {
    if (version === pointVersion) el("point").textContent = error.message;
  }
}

async function poll() {
  if (polling || busy || !health?.replay_ready) return;
  polling = true;
  const version = commandVersion;
  try {
    const state = await api("/api/simulation/state");
    if (version !== commandVersion) return;
    if (archivedRun) {
      renderState(state);
      return;
    }
    if (state.run_id !== runId) {
      resetTimeline(state.run_id);
      if (state.run_id) {
        const run = await api(`/api/runs/${state.run_id}`);
        if (version !== commandVersion) return;
        metadata = {...metadata,...run.map};
        renderMapMetadata();
        updateDomain(metadata.bounds,true);
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
    if (version === commandVersion) notice("계산 상태를 불러오지 못했습니다. 로컬 서버가 실행 중인지 확인하세요.");
  } finally {
    polling = false;
  }
}

async function command(operation) {
  if (busy) return;
  historyVersion += 1;
  busy = true;
  commandVersion += 1;
  notice("");
  renderState(replayState);
  try {
    const body = operation === "start" ? {...settings(),scenario_id: el("scenario").value} : undefined;
    const state = await post(`/api/simulation/${operation}`, body);
    const wasViewingArchive = Boolean(archivedRun);
    if (operation === "start" || operation === "reset") {
      archivedRun=undefined;
      el("history-info").hidden = true;
      el("reuse").disabled=true;
    }
    if (state.run_id !== runId || (wasViewingArchive && !archivedRun)) resetTimeline(state.run_id);
    if (operation === "start") {
      const run = await api(`/api/runs/${state.run_id}`);
      metadata = {...metadata,...run.map};
      renderMapMetadata();
      updateDomain(metadata.bounds,true);
    }
    renderState(state);
    if (operation === "reset") await previewRegion(false);
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
        ? `가정 배수율 지도를 사용합니다. 지도에 값이 없는 셀에는 ${metadata.default_drain_mm_h} mm/h를 적용합니다.`
        : "가정 배수율 지도를 사용합니다.")
      : `가정 배수율은 ${metadata.default_drain_mm_h} mm/h입니다.`,
    mixed: `배수율 입력이 없는 셀에는 가정값 ${metadata.default_drain_mm_h} mm/h를 적용합니다.`,
    observed: "지역별 배수율 입력값을 사용합니다.",
  }[metadata.drainage_source];
  const boundary = metadata.boundary === "open" ? "허용합니다" : "차단합니다";
  el("assumptions").textContent =
    `30 m 지형 격자의 각 셀에는 가장 가까운 관측소의 강우량을 10분 동안 일정하게 적용합니다. ${drain} 외곽 유출을 ${boundary}.`;
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
  updateDomain(metadata.bounds);
  if (!health.map_ready) throw new Error("지도 파일이 없습니다. 설치와 실행 안내의 데이터 준비 단계를 확인하세요.");
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
        draft: {type:"geojson",data:{type:"FeatureCollection",features:[]}},
        domain: {type: "geojson", data: {
          type: "Feature", properties: {},
          geometry: {type: "Polygon", coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
        }},
      },
      layers: [
        {id: "background", type: "background", paint: {"background-color": "#dde8e0"}},
        {id: "streets", type: "raster", source: "osm", layout: {visibility: "none"}, paint: {"raster-opacity": .82, "raster-saturation": -.55}},
        {id: "relief", type: "hillshade", source: "dem", paint: {"hillshade-shadow-color": "#315b57", "hillshade-highlight-color": "#fffef7", "hillshade-exaggeration": .66}},
        {id:"coverage-outline",type:"line",source:"coverage",paint:{"line-color":"#52735f","line-width":1.5,"line-dasharray":[5,3]}},
        {id: "domain-outline", type: "line", source: "domain", paint: {"line-color": "#244f61", "line-width": 2, "line-dasharray": [3, 2]}},
        {id: "draft-outline", type: "line", source: "draft", paint: {"line-color": "#9c4c21", "line-width": 2, "line-dasharray": [3, 2]}},
      ],
      terrain: {source: "dem", exaggeration: 1},
    },
  });
  map.setMaxBounds([[126.68,37.38],[127.22,37.74]]);
  map.addControl(new NavigationControl({visualizePitch: true}), "top-right");
  map.addControl(new ScaleControl({unit: "metric"}), "bottom-right");
  map.addControl(new AttributionControl({compact: true}), "bottom-right");
  map.on("error", (event) => {
    if (event.sourceId === "osm") {
      mapMessage("도로 지도를 불러오지 못했습니다. 지형과 모의 수심은 계속 볼 수 있습니다.");
    } else if (event.sourceId === "dem") {
      mapMessage("지형을 불러오지 못했습니다. 로컬 서버 상태를 확인하세요.");
    } else {
      console.error(event.error);
    }
  });
  map.on("load", () => {
    mapReady = true;
    el("map-loading").hidden = true;
    updateDomain(mapBounds, true);
    map.jumpTo({pitch: 42});
    for (const id of ["fit", "seoul", "pitch", "streets"]) el(id).disabled = false;
    renderState(replayState);
    if (west < 127.027539 && east > 127.027539 && south < 37.497958 && north > 37.497958) {
      const label = document.createElement("span");
      label.className = "map-name";
      label.textContent = "강남역";
      new Marker({element: label, anchor: "bottom"}).setLngLat([127.027539, 37.497958]).addTo(map);
    }
    if (frameIndex >= 0) void selectFrame(frameIndex);
  });
  el("fit").addEventListener("click", () => fitRegion(mapBounds));
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
        el("selection-hint").textContent = "대각선 반대편 꼭짓점을 선택하세요";
      } else {
        selectedBounds = [Math.min(firstCorner.lng,event.lngLat.lng),Math.min(firstCorner.lat,event.lngLat.lat),
                          Math.max(firstCorner.lng,event.lngLat.lng),Math.max(firstCorner.lat,event.lngLat.lat)];
        el("area").value = "custom";
        setAreaSelection(false, true);
        void previewRegion(false);
        el("select-area").focus();
      }
      return;
    }
    selectedPoint = event.lngLat;
    marker ??= new Marker({color: "#1b64b5", scale: .65});
    marker.setLngLat(selectedPoint).addTo(map);
    void showPoint(selectedPoint);
  });
}

async function init() {
  try {
    [health, catalog] = await Promise.all([api("/api/health"), api("/api/scenarios")]);
    el("scenario").replaceChildren(...catalog.map(scenarioOption));
    el("question").disabled = el("ask").disabled = !(health.agent_ready && health.replay_ready);
    if (!health.agent_ready) el("agent-status").textContent = "Solar에 질문하려면 서버에 UPSTAGE_API_KEY를 설정하세요.";
    renderState({status: health.replay_ready ? "ready" : "error", error: health.error});
    await initMap();
    await previewRegion(false);
    void refreshHistory();
    if (health.replay_ready) {
      void poll();
      window.setInterval(poll, 700);
    }
  } catch (error) {
    el("map-loading").hidden = true;
    mapMessage(health ? error.message : "로컬 서버에 연결할 수 없습니다. 서버를 실행한 뒤 페이지를 새로고침하세요.");
    renderState({status: "error", error: health?.error});
  }
}

el("primary").addEventListener("click", () => command(el("primary").dataset.operation));
el("reset").addEventListener("click", () => command("reset"));
for (const id of ["drain", "threads", "boundary"]) {
  el(id).addEventListener("change", () => { void previewRegion(false); });
}
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
    setAreaSelection(false);
    void previewRegion();
  } else if (!selecting) {
    el("select-area").click();
  }
});
el("select-area").addEventListener("click", () => {
  setAreaSelection(!selecting);
  if (selecting) el("cancel-selection").focus();
});
el("cancel-selection").addEventListener("click", () => {
  setAreaSelection(false);
  el("select-area").focus();
});
el("seoul").addEventListener("click", () => map?.fitBounds([[126.75,37.42],[127.18,37.70]],{padding:25,duration:0}));
el("history").addEventListener("change", () => {
  el("open-run").disabled = !el("history").value;
  el("reuse").disabled = !archivedRun || archivedRun.id !== el("history").value;
});
el("open-run").addEventListener("click",openHistory);
el("live").addEventListener("click", async () => {
  historyVersion += 1;
  commandVersion += 1;
  archivedRun=undefined;
  el("question").disabled=el("ask").disabled=!(health.agent_ready && health.replay_ready);
  el("history-info").hidden = true;
  el("reuse").disabled = true;
  resetTimeline(undefined);
  el("frame-label").focus();
  await poll();
  if (!replayState.run_id) await previewRegion(false);
});
el("reuse").addEventListener("click", async () => {
  if (!archivedRun) return;
  const run = archivedRun;
  const config = run.settings || {bounds:run.map.bounds,drain_mm_h:run.map.default_drain_mm_h,threads:run.threads_requested,boundary:run.map.boundary};
  selectedBounds=config.bounds;
  el("drain").value=config.drain_mm_h;
  el("threads").value=config.threads;
  el("boundary").value=config.boundary;
  el("area").value=presetKey(selectedBounds) ?? "custom";
  await previewRegion(false);
  el("scenario").value=run.scenario.id;
});
void init();
