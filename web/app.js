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
  primary.disabled = busy || !health?.replay_ready || !el("scenario").value;
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
  if (polling || busy || !health?.replay_ready) return;
  polling = true;
  const version = commandVersion;
  try {
    const state = await api("/api/simulation/state");
    if (version !== commandVersion) return;
    if (state.run_id !== runId) resetTimeline(state.run_id);
    renderState(state);
    if (state.frame_count > frames.length) {
      const batch = await api(`/api/simulation/frames?offset=${frames.length}`);
      if (version !== commandVersion || batch.run_id !== runId) return;
      frames.push(...batch.frames);
    }
    if (follow && frames.length) await selectFrame(frames.length - 1);
    updateTimeline();
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
    const body = operation === "start" ? {scenario_id: el("scenario").value} : undefined;
    const state = await post(`/api/simulation/${operation}`, body);
    if (state.run_id !== runId) resetTimeline(state.run_id);
    renderState(state);
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
  const rasterBounds = [west - .03, south - .025, east + .03, north + .025];
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
        domain: {type: "geojson", data: {
          type: "Feature", properties: {},
          geometry: {type: "Polygon", coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
        }},
      },
      layers: [
        {id: "background", type: "background", paint: {"background-color": "#dfe7e3"}},
        {id: "streets", type: "raster", source: "osm", layout: {visibility: "none"}, paint: {"raster-opacity": .82, "raster-saturation": -.55}},
        {id: "relief", type: "hillshade", source: "dem", paint: {"hillshade-shadow-color": "#426462", "hillshade-highlight-color": "#fffdf4", "hillshade-exaggeration": .58}},
        {id: "domain-outline", type: "line", source: "domain", paint: {"line-color": "#27596d", "line-width": 2, "line-dasharray": [3, 2]}},
      ],
      terrain: {source: "dem", exaggeration: 1},
    },
  });
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
  el("fit").addEventListener("click", () => map.fitBounds(bounds, {padding: 45, duration: 0}));
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
    initMap().catch((error) => mapMessage(error.message));
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

void init();
