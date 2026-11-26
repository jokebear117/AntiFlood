const el = (id) => document.getElementById(id);
const statusLabels = {
  ready: "계산 대기", idle: "계산 대기", running: "계산 중", paused: "일시 정지",
  completed: "계산 완료", error: "실행 오류",
};
const actionLabels = {start: "계산 시작", pause: "일시 정지", resume: "계산 재개"};
const pointHint = "지도에서 지점을 선택하면 모의 수심, 배수능력, Tile 상태를 표시합니다";
const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", month: "long", day: "numeric",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const scenarioOption = ({title, id}) => new Option(title.replace(/ KST$/, ""), id);

let health;
let catalog = [];
let map;
let referenceMap;
let referenceReady = false;
let referenceMarker;
let referenceFrames = [];
let currentRun;
let layer = "depth";
let playback;
let syncCamera = false;
let observedData;
let metadata;
let mapReady = false;
let replayState = {status: "idle"};
let runId;
let frames = [];
let frameIndex = -1;
let follow = true;
let shownFrame;
let pendingFrame;
let displayedKey;
let viewVersion = 0;
let pointVersion = 0;
let selectedPoint;
let marker;
let busy = false;
let polling = false;
let commandVersion = 0;
let selectedBounds = [126.75,37.42,127.20,37.71];
let mapBounds = selectedBounds;
let draftBounds;
let selecting = false;
let firstCorner;
let archivedRun;
let historyVersion = 0;
let regionReady = false;
let regionVersion = 0;
let stations = new Map();
let showGauges = false;
const drainageLabels = {facility: "서울 밖 가정 배수율 (mm/h)", uniform: "가정 배수율 (mm/h)"};
const presets = {
  seoul: selectedBounds,
  gangnam: [127.005,37.470,127.065,37.535],
  yeouido: [126.90,37.515,126.945,37.545],
  mapo: [126.90,37.545,126.95,37.58],
  songpa: [127.075,37.49,127.13,37.53],
};
function settings() {
  return {bounds:selectedBounds, drain_mm_h:Number(el("drain").value), drainage:el("drainage").value,
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
  for (const view of readyMaps()) view.getSource("domain").setData(
    metadata.domain ? {type:"Feature", properties:{}, geometry:metadata.domain} : polygon(bounds),
  );
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
    el("workspace-alert").hidden = true;
    el("region-info").textContent = `셀 ${data.map.valid_cell_count.toLocaleString("ko-KR")}개\n메모리 약 ${data.estimated_memory_mb} MB${data.warning ? "\n"+data.warning : ""}`;
    if (!archivedRun && !replayState.run_id) {
      metadata = {...metadata, ...data.map};
      renderMapMetadata();
      updateDomain(selectedBounds,fit);
      if (layer === "drainage" && !currentRun) void selectFrame(frameIndex, true);
    } else {
      updateDraft(selectedBounds);
      if (fit && mapReady) fitRegion(selectedBounds);
    }
  } catch(error) {
    if (version === regionVersion) {
      el("region-info").textContent = error.message;
      el("workspace-error").textContent = "새 계산의 입력 자료를 확인하지 못했습니다. " + error.message;
      el("workspace-alert").hidden = false;
      el("scenario").replaceChildren();
    }
  } finally { if (version === regionVersion) renderState(replayState); }
}
function presetKey(bounds) {
  return Object.keys(presets).find(key => presets[key].every((value, i) => Math.abs(value - bounds[i]) < .00001));
}
function areaName(bounds) {
  const names = {seoul:"서울 전역",gangnam:"강남역 주변",yeouido:"여의도 주변",mapo:"마포 주변",songpa:"송파 주변"};
  const key = presetKey(bounds);
  return key ? names[key] : `북위 ${((bounds[1]+bounds[3])/2).toFixed(3)}°, 동경 ${((bounds[0]+bounds[2])/2).toFixed(3)}° 중심`;
}
async function refreshHistory() {
  const previous = el("history").value;
  const runs = await api("/api/runs");
  el("history").replaceChildren(new Option(runs.length ? "기록 선택" : "저장된 실행 없음", ""), ...runs.map(run=>new Option(
    `${areaName(run.map.bounds)} / ${run.reference_id ? "비교" : (run.mode ?? "이전 기록")} (${run.id.slice(0,6)})`,run.id)));
  el("history").value = previous;
  el("open-run").disabled = !el("history").value;
  el("reuse").disabled = !archivedRun || archivedRun.id !== el("history").value;
  return runs;
}
function drainageName(run) {
  return run.map.drainage_source === "facility" ? "시설 기반 배수" :
    `배수율 ${run.settings?.drain_mm_h ?? run.map.default_drain_mm_h} mm/h`;
}
async function openHistory(focus = true) {
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
    await setRun(run);
    if (version !== historyVersion) return;
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
    if (focus) { closePanel(false); el("frame-label").focus(); }
  } catch(error) { if (version === historyVersion) notice(error.message); }
}

function formatTime(value) {
  return value ? dateFormat.format(new Date(value)) : "—";
}

async function api(path, settings) {
  const response = await fetch(path, settings);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `요청을 처리하지 못했습니다 (HTTP ${response.status}).`);
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
  if (message) openPanel("setup-panel", false);
}

function mapMessage(message) {
  el("map-error").hidden = !message;
  el("map-error").textContent = message || "";
}

function setAreaSelection(enabled, keepBounds = false) {
  if (enabled) closePanel(false);
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
  const active = ["running","paused"].includes(state.status);
  const label = archivedRun && !active ? "저장 결과" :
    (state.mode && active ? modeName(state.mode) + " " : "") + (statusLabels[state.status] || statusLabels.idle);
  if (status.textContent !== label) status.textContent = label;
  status.dataset.status = state.status;
  el("computed-time").textContent = formatTime(state.simulated_time_utc);
  const operation = {running: "pause", paused: "resume"}[state.status] || "start";
  document.querySelector('[data-panel="setup-panel"]').textContent = active ? "실행 제어" : "새 계산";
  const primary = el("primary");
  primary.dataset.operation = operation;
  primary.textContent = actionLabels[operation];
  primary.disabled = busy || !health?.replay_ready || (operation === "start" && (!regionReady || selecting || !catalog.length));
  document.querySelector(".run-progress").hidden = !state.run_id;
  el("progress").value = state.progress || 0;
  el("progress-label").textContent = `${Math.round((state.progress || 0)*100)}%`;
  for (const id of ["area","drain","drainage","threads","boundary","mode"]) {
    el(id).disabled = busy || state.status === "running" || state.status === "paused";
  }
  const hasSession = state.status === "running" || state.status === "paused";
  el("select-area").disabled = busy || hasSession || !mapReady;
  el("scenario").disabled = busy || hasSession || catalog.length === 0;
  el("reset").disabled = busy || !state.run_id;
  if (state.error) notice(state.error);
}

function renderFrameDetails(frame) {
  el("streaming-title").querySelector("small").textContent = frame && !hasPeriods(frame)
    ? "선택적 갱신 (이전 방식)" : "지역별 계산";
  el("frame-time").textContent = frame ? formatTime(frame.time) : "저장된 결과 없음";
  el("depth").textContent = frame ? `${frame.max_depth_m.toFixed(3)} m` : "—";
  el("rain").textContent = frame ? `${frame.rain_max_mm.toFixed(1)} mm` : "—";
  el("tiles").textContent = frame ? num(frame.active_tile_count, 0) +
    (frame.active_tile_ratio == null ? "" : " / " + percent(frame.active_tile_ratio)) : "—";
  el("cells").textContent = frame ? frame.active_cell_count.toLocaleString("ko-KR") : "—";
  el("workers").textContent = frame ? frame.worker_count.toString() : "—";
  el("observed").textContent = formatTime(frame?.rain_observed_at);
  el("timeline").setAttribute("aria-valuetext", formatTime(frame?.time));
  renderMetrics(frame);
}

function removeFrame() {
  viewVersion += 1;
  pointVersion += 1;
  pendingFrame = displayedKey = shownFrame = selectedPoint = undefined;
  marker?.remove();
  referenceMarker?.remove();
  for (const view of readyMaps()) setOverlay(view);
  el("window-series").replaceChildren();
  el("window-note").hidden = false;
  el("reference-empty").hidden = false;
  el("streaming-empty").hidden = false;
  renderFrameDetails(null);
  el("point").textContent = pointHint;
  if (!el("point-panel").hidden) closePanel(false);
  renderCharts();
  updateGauges();
}

function resetTimeline(id) {
  runId = id;
  frames = [];
  referenceFrames = [];
  currentRun = undefined;
  stopPlayback();
  el("header-scenario").textContent = "서울 침수 계산 비교";
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
  const timeline = timelineFrames();
  slider.max = Math.max(0, timeline.length - 1);
  slider.value = Math.max(frameIndex, 0);
  slider.disabled = timeline.length < 2;
  el("play").disabled = timeline.length < 2;
  el("latest").disabled = follow || !frames.length;
  el("latest").textContent = archivedRun ? "마지막 저장 시각으로" : "최신 시각으로";
  el("live").hidden = !archivedRun;
  el("time-start").parentElement.hidden = timeline.length < 2;
  el("time-start").textContent = formatTime(timeline[0]?.time);
  el("time-end").textContent = formatTime(timeline.at(-1)?.time);
}


const num = (value, digits = 1) => Number(value).toLocaleString("ko-KR", {maximumFractionDigits: digits});
const percent = (value) => value == null ? "미측정" : num(value * 100) + "%";
const modeName = (mode) => mode === "reference" ? "Reference" : "Streaming";
const hasPeriods = (frame) => ["subthreshold_tile_temporal_blocking", "dry_tile_temporal_blocking", "full_grid_synchronous"]
  .includes(frame?.calculation_policy);
const readyMaps = () => [mapReady && map, referenceReady && referenceMap].filter(Boolean);
const timelineFrames = () => referenceFrames.length > frames.length ? referenceFrames : frames;

async function setRun(run) {
  const reference = run.reference_id && (currentRun?.reference_id === run.reference_id && referenceFrames.length
    ? referenceFrames : (await api("/api/runs/" + run.reference_id)).frames);
  if (run.id !== runId) return;
  currentRun = run;
  referenceFrames = reference || [];
  el("header-scenario").textContent = run.scenario.title;
  renderMetrics(shownFrame);
}

function setOverlay(view, image) {
  if (!image) {
    if (view.getSource("depth")) {
      view.removeLayer("flood");
      view.removeSource("depth");
    }
    return;
  }
  if (!view.getSource("depth")) {
    view.addSource("depth", {type:"image", coordinates:metadata.frame_coordinates});
    view.addLayer({id:"flood",type:"raster",source:"depth",
      paint:{"raster-fade-duration":0,"raster-resampling":"nearest"}}, "domain-outline");
  }
  view.getSource("depth").updateImage({image, coordinates:metadata.frame_coordinates});
}

async function decodeImage(url) {
  if (!url) return undefined;
  const image = new Image();
  image.src = url;
  await image.decode();
  return image;
}

function choosePoint(point, Marker) {
  selectedPoint = point;
  el("point-reading").textContent = "지점 정보를 확인하는 중";
  marker ??= new Marker({color:"#1b64b5",scale:.65});
  referenceMarker ??= new Marker({color:"#1b64b5",scale:.65});
  marker.setLngLat(point).addTo(map);
  referenceMarker.setLngLat(point).addTo(referenceMap);
  openPanel("point-panel", false);
  void showPoint(point);
}

function renderMetrics(frame) {
  const data = frame?.comparison;
  el("speedup").textContent = data?.speedup == null ? "미측정" : num(data.speedup, 2) + "×";
  el("reduction").textContent = percent(data?.cell_reduction);
  el("rmse").textContent = data ? num(data.rmse_m * 1000, 2) + " mm" : "미측정";
  el("flood-rmse").hidden = data?.flood_rmse_m == null;
  el("flood-rmse").textContent = data?.flood_rmse_m == null ? "" :
    "침수 영역 " + num(data.flood_rmse_m * 1000, 2) + " mm";
  el("iou").textContent = !data ? "미측정" : data.iou == null ? "침수 없음" : percent(data.iou);
  el("latency").textContent = frame?.update_latency_seconds == null ? "미측정" : num(frame.update_latency_seconds, 2) + "초";
  const bars = el("performance-chart");
  const compact = (value) => Number(value).toLocaleString("ko-KR", {notation: "compact", maximumFractionDigits: 2});
  bars.textContent = data
    ? "이 시각까지 누적 계산 시간 Reference " + num(data.reference_seconds, 1) + "초, Streaming " +
      num(frame.calculation_seconds, 1) + "초. 수평 유동 셀 갱신 Reference " + compact(data.reference_cell_updates) +
      "회, Streaming " + compact(frame.cumulative_cell_updates) + "회."
    : "두 모드의 같은 시각 결과가 저장되면 누적 계산량을 비교합니다.";
  const total = currentRun?.performance;
  el("total-performance").textContent = total ? "전체 실행 " + num(total.speedup, 2) + "×, 시간 감소율 " +
    percent(total.time_reduction) + ", 수평 유동 계산량 감소율 " + percent(total.cell_reduction) : "";
}

function addKey(target, label, color) {
  const item = document.createElement("span");
  const swatch = document.createElement("i");
  swatch.style.backgroundColor = color;
  item.append(swatch, label);
  target.append(item);
}

function renderLayerLegend(frame = shownFrame) {
  const key = el("layer-key");
  key.hidden = layer === "depth" || layer === "drainage";
  key.replaceChildren();
  renderScale();
  const periods = !frame || hasPeriods(frame);
  document.querySelector('[data-layer="active"]').textContent = periods ? "계산 간격" : "활성 Tile";
  const entries = {
    active: periods
      ? [["마지막 간격 ≤15초","#1e89d2"],["15초 초과 ~ 30초","#f6c24a"],["30초 초과","#e06624"]]
      : [["Dry","#8c9ba8"],["Low Risk","#f6c24a"],["Halo","#e06624"],["High Risk","#b43626"],["전체 격자 계산","#1e89d2"]],
    difference: [["−5cm 이하","#164fb1"],["−5cm ~ −1mm","#55a4d5"],["+1mm ~ +5cm","#f49851"],["+5cm 이상","#b83a1b"]],
    observed: [["2022년 8월 8~9일 서울시 침수흔적도","#8e2366"]],
  }[layer] ?? [];
  for (const [name,color] of entries) addKey(key,name,color);
  const summary = el("observed-summary");
  summary.hidden = layer !== "observed";
  const ref = currentRun?.reference?.observed_overlap ??
    (currentRun?.mode === "reference" ? currentRun.observed_overlap : null);
  const stream = currentRun?.mode === "streaming" ? currentRun.observed_overlap : null;
  summary.textContent = ref || stream
    ? "침수 기록과 겹치는 비율 (사건 최대 수심 5cm 이상)  Reference " + percent(ref?.observed_coverage) +
      " / Streaming " + percent(stream?.observed_coverage) + ". 기록 범위 안에서 비교합니다."
    : "사건 최대 수심은 계산이 완료된 실행에서 표시합니다.";
}

async function selectFrame(index, force = false) {
  frameIndex = index;
  updateTimeline();
  renderCharts();
  const frame = frames[index];
  const pair = frame?.reference_frame_id ? referenceFrames.find(item => item.id === frame.reference_frame_id) : referenceFrames[index];
  const ref = frame?.mode === "reference" ? frame : pair;
  const stream = frame?.mode === "reference" ? undefined : frame;
  const shown = frame ?? ref;
  const key = [shown?.id, layer].join("/");
  if (!force && key === pendingFrame) return;
  if (!force && key === displayedKey) {
    if (pendingFrame) {
      viewVersion += 1;
      pendingFrame = undefined;
    }
    return;
  }
  renderLayerLegend(shown);
  if (!mapReady) {
    renderFrameDetails(shown);
    return;
  }
  const version = ++viewVersion;
  pendingFrame = key;
  try {
    const periodLayer = layer === "active" && hasPeriods(shown);
    const refUrl = ref && (!periodLayer || hasPeriods(ref)) &&
      "/api/frames/" + ref.id + ".png" + (periodLayer ? "?layer=period" : "");
    const suffix = periodLayer ? "?layer=period" :
      layer === "active" || layer === "difference" ? "?layer=" + layer : "";
    const streamUrl = stream && (layer !== "difference" || stream.reference_frame_id) &&
      (layer !== "active" || stream.mode === "streaming") && "/api/frames/" + stream.id + ".png" + suffix;
    const observation = layer === "observed";
    const drainageLayer = layer === "drainage";
    if (observation && !observedData) observedData = await api("/api/map/observed");
    if (drainageLayer) {
      const url = currentRun ? "/api/runs/" + currentRun.id + "/drainage.png" : "/api/region/drainage.png?v=" + regionVersion;
      const image = await decodeImage(url).catch(() => undefined);
      if (version !== viewVersion) return;
      for (const view of readyMaps()) {
        setOverlay(view, image);
        setVisibility(view, "observed-fill", false);
        setVisibility(view, "pumps", true);
      }
      el("reference-empty").hidden = el("streaming-empty").hidden = true;
      shownFrame = shown;
      displayedKey = key;
      renderFrameDetails(shown);
      updateGauges();
      mapMessage(image ? "" : "이 실행에는 배수능력 지도가 저장되지 않았습니다. 새로 계산하면 표시됩니다.");
      if (selectedPoint) await showPoint(selectedPoint, shown);
      return;
    }
    const completed = currentRun?.status === "completed";
    const maximumUrl = (id) => id && "/api/runs/" + id + "/maximum.png";
    const [refImage, streamImage] = await Promise.all([
      referenceReady && decodeImage(observation
        ? maximumUrl(currentRun?.reference_id ?? (completed && currentRun?.mode === "reference" && currentRun?.id)) : refUrl),
      decodeImage(observation ? maximumUrl(completed && currentRun?.mode === "streaming" && currentRun?.id) : streamUrl),
    ]);
    if (version !== viewVersion) return;
    for (const view of readyMaps()) {
      setVisibility(view, "pumps", false);
      setOverlay(view, view === map ? streamImage : refImage);
      if (observation && !view.getSource("observed")) {
        view.addSource("observed", {type:"geojson",data:observedData,attribution:"서울시 OA-15636 침수흔적도"});
        view.addLayer({id:"observed-fill",type:"fill",source:"observed",paint:{"fill-color":"#8e2366","fill-opacity":.50}});
      } else if (view.getLayer("observed-fill")) {
        view.setLayoutProperty("observed-fill","visibility",observation ? "visible" : "none");
      }
    }
    el("reference-empty").hidden = Boolean(refImage) || observation;
    el("streaming-empty").hidden = Boolean(streamImage) || observation;
    el("reference-empty").textContent = periodLayer && ref && !hasPeriods(ref)
      ? "이 Reference에는 계산 간격 기록이 없습니다" : "이 시각에 Reference 결과가 없습니다";
    el("streaming-empty").textContent = stream && layer === "difference" ? "같은 시각의 Reference 결과가 필요합니다" :
      "이 시각에 Streaming 결과가 없습니다";
    shownFrame = shown;
    displayedKey = key;
    renderFrameDetails(shown);
    updateGauges();
    mapMessage("");
    if (selectedPoint) await showPoint(selectedPoint, shown);
  } catch (error) {
    if (version === viewVersion) mapMessage(observedData || layer !== "observed"
      ? "선택한 지도 자료를 불러오지 못했습니다." : error.message);
  } finally {
    if (version === viewVersion) pendingFrame = undefined;
  }
}

function renderWindows(frame, indices) {
  const target = el("window-series");
  target.replaceChildren();
  el("window-note").hidden = Boolean(indices?.length);
  if (!indices?.length) return;
  const source = frames.filter(item => item.mode === "streaming");
  const series = [
    ["rain_interval_mm","10분 강우","#087e94"],["sliding_mm","최근 60분","#3153ab"],
    ["decaying_mm","감쇠 점수","#a6602a"],
  ].map(([key,label,color]) => ({
    label,color,values:source.map(item => Math.max(...indices.map(i => item[key][i]))),
  }));
  const maximum = Math.max(1, ...series.flatMap(item => item.values));
  const svg = document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.setAttribute("viewBox","0 0 360 113");
  svg.setAttribute("role","img");
  svg.setAttribute("aria-label","Tile 강우 시계열, 최대 " + num(maximum) + " mm");
  const x = (i) => 30 + 325 * i / Math.max(1, source.length - 1);
  const y = (value) => 91 - value / maximum * 79;
  const element = (tag, attrs, text) => {
    const node = document.createElementNS(svg.namespaceURI, tag);
    for (const [key,value] of Object.entries(attrs)) node.setAttribute(key,value);
    if (text != null) node.textContent = text;
    svg.append(node);
  };
  for (const v of [0,maximum/2,maximum]) {
    element("line",{x1:30,x2:355,y1:y(v),y2:y(v),stroke:"#d8e2e8"});
    element("text",{x:0,y:y(v)+4,fill:"#526672","font-size":13},num(v));
  }
  element("text",{x:30,y:107,fill:"#526672","font-size":13},formatTime(source[0]?.time));
  element("text",{x:355,y:107,fill:"#526672","font-size":13,"text-anchor":"end"},formatTime(source.at(-1)?.time));
  const i = source.findIndex(item => item.id === frame.id);
  if (i >= 0) element("line",{x1:x(i),x2:x(i),y1:10,y2:91,stroke:"#82909e","stroke-dasharray":"3 3"});
  const legend = document.createElement("div");
  legend.className = "chart-key";
  for (const {label,color,values} of series) {
    element("polyline",{points:values.map((v,j) => [x(j),y(v)].join(",")).join(" "),fill:"none",stroke:color,"stroke-width":2});
    if (i >= 0) element("circle",{cx:x(i),cy:y(values[i]),r:3,fill:color});
    addKey(legend,label,color);
  }
  target.append(svg,legend);
}

async function showPoint(point, frame = shownFrame) {
  const version = ++pointVersion;
  const search = new URLSearchParams({lon:point.lng,lat:point.lat});
  // The drainage rate is an input, so it can be inspected before any result exists.
  const drainSearch = new URLSearchParams({lon:point.lng,lat:point.lat,...(currentRun ? {run:currentRun.id} : {})});
  let drainError = "";
  const drainInfo = await api("/api/drainage/point?" + drainSearch).catch((error) => { drainError = error.message; return null; });
  if (version !== pointVersion) return;
  const drain = drainInfo ? "\n배수능력 " + num(drainInfo.drain_mm_h) + " mm/h, " +
    ({assumed: "가정값", sewer: "시설 제원 추정값", pump: "시설 제원 추정값"}[drainInfo.drain_source] ?? "") +
    "\n근거: " + drainInfo.basis : "";
  if (!frame) {
    el("point-reading").textContent = drainInfo ? `배수능력 ${num(drainInfo.drain_mm_h)} mm/h · 계산 전` : drainError;
    el("point").textContent = drainInfo ? drain.trimStart() + "\n계산 결과를 저장하면 이 지점의 모의 수심도 표시합니다." : drainError;
    return;
  }
  try {
    const result = await api("/api/frames/" + frame.id + "/point?" + search);
    if (version !== pointVersion) return;
    el("point-reading").textContent = `${modeName(frame.mode)} 모의 수심 ${num(result.depth_m*1000, 1)} mm` + (result.reference_depth_m == null ? "" : ` / Reference ${num(result.reference_depth_m*1000, 1)} mm`) + (drainInfo ? `\n배수능력 ${num(drainInfo.drain_mm_h)} mm/h (추정·가정값)` : "");
    const mode = ["Dry","Low Risk","Halo","High Risk","전체 격자 계산"][result.tile_mode];
    if (mode || hasPeriods(result)) {
      const reasons = ["10분 강우","60분 누적","감쇠 점수","잔류 수심","고위험 Tile 인접","이전 단계 유입","이번 10분 구간에 이미 활성"]
        .filter((_,bit) => result.reasons & (1 << bit));
      const start = Date.parse(currentRun?.scenario.start);
      const last = result.last_update_seconds < 0 || !Number.isFinite(start) ? "기록 없음" :
        formatTime(start + result.last_update_seconds * 1000);
      const ref = result.reference_depth_m;
      const calculation = hasPeriods(result)
        ? " · 전체 격자 계산\n" + (result.calculation_policy === "full_grid_synchronous" ? "동기 계산" : "지역별 적응형 계산") +
          " · 이 Tile의 마지막 간격 " + (result.tile_step_seconds == null ? "기록 없음" : num(result.tile_step_seconds, 2) + "초") +
          " · 계산 시각 " + formatTime(result.time)
        : " · " + mode + " · " +
          (result.active ? "수평 유동 계산" : (mode === "Dry" ? "건조 상태" : "강우·배수만 계산")) +
          "\n선택 조건 " + (reasons.join(", ") || "활성 기준 미달") + " · 마지막 수평 유동 " + last;
      el("point").textContent =
        "Tile " + result.tile_id + calculation +
        (result.rain_interval_mm == null ? "" :
        "\n관측소별 최댓값  10분 " + num(result.rain_interval_mm) + " mm / 60분 " + num(result.sliding_mm) +
        " mm / 감쇠 " + num(result.decaying_mm) + " mm") +
        (frame.mode === "reference" ? "\nReference " + num(result.depth_m*1000,2) + " mm" :
          "\nReference " + (ref == null ? "자료 없음" : num(ref*1000,2) + " mm") +
          " / Streaming " + num(result.depth_m*1000,2) + " mm" +
          (ref == null ? "" : " / 차이 " + num(result.difference_m*1000,2) + " mm")) +
        (result.max_tile_depth_m == null ? "" : " · Tile 최대 " + num(result.max_tile_depth_m*1000,2) + " mm") + drain;
      renderWindows(frame,result.gauge_indices);
    } else {
      el("point").textContent = "Tile " + result.tile_id + " · " + modeName(frame.mode) +
        " 수심 " + num(result.depth_m*1000,2) + " mm" + drain;
      renderWindows(frame);
    }
  } catch (error) {
    if (version === pointVersion) {
      el("point-reading").textContent = "지점 정보를 불러오지 못했습니다.";
      el("point").textContent = error.message;
      renderWindows(frame);
    }
  }
}

function stopPlayback() {
  clearInterval(playback);
  playback = undefined;
  el("play").textContent = "재생";
}

function togglePlayback() {
  if (playback) {
    stopPlayback();
    return;
  }
  follow = false;
  if (frameIndex >= timelineFrames().length - 1) void selectFrame(0);
  el("play").textContent = "재생 일시 정지";
  playback = setInterval(() => {
    if (frameIndex >= timelineFrames().length - 1) stopPlayback();
    else void selectFrame(frameIndex + 1);
  }, 850);
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
        await setRun(run);
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
      renderCharts();
    }
    const completed = state.status === "completed" && previousStatus !== "completed" && state.run_id;
    if (completed) {
      await setRun(await api(`/api/runs/${state.run_id}`));
    }
    if (follow && frames.length) await selectFrame(frames.length - 1, Boolean(completed && layer === "observed"));
    else if (completed && layer === "observed") await selectFrame(frameIndex, true);
    else if (frameIndex >= 0 && frames[frameIndex]?.id !== shownFrame?.id) await selectFrame(frameIndex);
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
    const body = operation === "start" ? {...settings(),scenario_id: el("scenario").value,mode:el("mode").value} : undefined;
    const state = await post(`/api/simulation/${operation}`, body);
    const wasViewingArchive = Boolean(archivedRun);
    if (operation === "start" || operation === "reset") {
      archivedRun=undefined;
      el("history-info").hidden = true;
      el("reuse").disabled=true;
    }
    if (state.run_id !== runId || (wasViewingArchive && !archivedRun)) resetTimeline(state.run_id);
    if (operation === "start" && state.run_id && state.status !== "error") {
      const run = await api(`/api/runs/${state.run_id}`);
      await setRun(run);
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
  el("scope").textContent = `계산 범위 ${south.toFixed(3)}–${north.toFixed(3)}°N, ${west.toFixed(3)}–${east.toFixed(3)}°E`;
  const summary = metadata.drainage;
  const outside = summary?.cells?.assumed ?? metadata.drainage_fallback_cells;
  const drain = {
    facility: `배수능력은 시설 제원 기반 추정값입니다. 서울시 셀은 지선 하수관 설계 강우강도 ${num(summary?.sewer_mm_h ?? 78.7)} mm/h까지 배수하고, 빗물펌프장 배수구역 근사 범위는 자치구별 펌프 용량을 배수면적으로 나눈 값으로 제한합니다.` +
      (outside ? ` 서울 밖 셀 ${outside.toLocaleString("ko-KR")}개에는 가정값 ${metadata.default_drain_mm_h} mm/h를 적용합니다.` : ""),
    assumed: metadata.drainage_raster_source
      ? (metadata.drainage_fallback_cells
        ? `가정 배수율 지도를 사용합니다. 지도에 값이 없는 셀에는 ${metadata.default_drain_mm_h} mm/h를 적용합니다.`
        : "가정 배수율 지도를 사용합니다.")
      : `모든 셀에 가정 배수율 ${metadata.default_drain_mm_h} mm/h를 적용합니다.`,
    mixed: `배수율 입력이 없는 셀에는 가정값 ${metadata.default_drain_mm_h} mm/h를 적용합니다.`,
    observed: "지역별 배수율 입력값을 사용합니다.",
  }[metadata.drainage_source] ?? "";
  const boundary = metadata.boundary === "open" ? "허용합니다" : "차단합니다";
  el("assumptions").textContent =
    `지형은 FABDEM 30 m 격자, 강우는 각 셀에서 가장 가까운 서울시 관측소의 10분 우량을 일정하게 나눠 적용합니다. ${drain} 외곽 유출을 ${boundary}. 수심은 모의 결과이며 실측값이 아닙니다.`;
  const stats = el("drainage-summary");
  stats.replaceChildren();
  if (summary?.cells) {
    const total = Object.values(summary.cells).reduce((a, b) => a + b, 0) || 1;
    for (const [label, value] of [
      ["평균 배수능력", num(summary.mean_mm_h) + " mm/h"],
      ["펌프 용량 제한", percent(summary.cells.pump / total)],
      ["가정값 적용", percent(summary.cells.assumed / total)],
    ]) {
      const item = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = value;
      item.append(dt, dd);
      stats.append(item);
    }
  }
  renderScale();
  el("legend").closest(".legend").hidden = false;
}

function renderScale() {
  if (!metadata) return;
  const drainage = layer === "drainage";
  const bins = drainage ? (metadata.drainage_legend ?? []).map(bin => ({min: bin.min_mm_h, rgb: bin.rgb}))
    : metadata.legend.map(bin => ({min: bin.min_m, rgb: bin.rgb}));
  el("legend-title").textContent = drainage ? "유효 배수능력 (mm/h)" : "모의 수심 (cm)";
  el("legend-note").textContent = drainage ? "시설 제원 기반 추정값, 회색은 가정값" : "1 mm 미만은 투명";
  el("legend").closest(".depth-key").hidden = layer === "active" || layer === "difference";
  el("legend").replaceChildren();
  bins.forEach((bin, i) => {
    const segment = document.createElement("span");
    const swatch = document.createElement("i");
    const next = bins[i + 1];
    segment.className = "legend-bin";
    swatch.style.backgroundColor = `rgb(${bin.rgb.join(",")})`;
    const label = value => drainage ? String(value) : num(value * 100, 1);
    segment.append(swatch, next ? `${label(bin.min)}–${label(next.min)}` : `${label(bin.min)} 이상`);
    el("legend").append(segment);
  });
}

function setVisibility(view, id, visible) {
  if (view.getLayer(id)) view.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
}

// Gauge circles show the 10-minute rainfall each station reported for the displayed time.
function updateGauges() {
  const gauges = currentRun?.gauges ?? metadata?.gauges ?? [];
  const frame = shownFrame;
  const features = gauges.map((gauge, i) => {
    const place = stations.get(gauge.id) ?? gauge;
    if (place.lon == null) return null;
    const mm = frame?.rain_interval_mm?.[i];
    return {type: "Feature", properties: {mm: mm ?? -1, name: gauge.name},
            geometry: {type: "Point", coordinates: [place.lon, place.lat]}};
  }).filter(Boolean);
  for (const view of readyMaps()) {
    view.getSource("gauges")?.setData({type: "FeatureCollection", features});
    setVisibility(view, "gauges", showGauges);
  }
}

function svgElement(svg, tag, attrs, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text != null) node.textContent = text;
  svg.append(node);
  return node;
}

function chartFrame(label, height) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 400 ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", label);
  return svg;
}

function chartKey(entries) {
  const key = document.createElement("div");
  key.className = "chart-key";
  for (const [name, color] of entries) addKey(key, name, color);
  return key;
}

function seriesByMode() {
  return {
    stream: frames.filter(item => item.mode !== "reference"),
    reference: referenceFrames.length ? referenceFrames : frames.filter(item => item.mode === "reference"),
  };
}

function renderCharts() {
  renderSeries();
  renderLatency();
}

function cursor(svg, x, top, bottom) {
  if (frameIndex >= 0) svgElement(svg, "line", {x1: x(frameIndex), x2: x(frameIndex), y1: top - 4, y2: bottom, stroke: "#163a60", "stroke-width": 1.2});
}

// Rainfall input (bars) against the simulated maximum depth (lines) for every stored time.
function renderSeries() {
  const target = el("time-series");
  target.replaceChildren();
  const timeline = timelineFrames();
  el("series-note").hidden = timeline.length > 0;
  if (!timeline.length) return;
  const {stream, reference} = seriesByMode();
  const n = timeline.length;
  const index = new Map(timeline.map((item, i) => [item.time, i]));
  const left = 34, right = 366, top = 8, bottom = 96;
  const x = (i) => left + (right - left) * (i + .5) / n;
  const rainMax = Math.max(5, ...timeline.map(item => item.rain_max_mm));
  const depthMax = Math.max(.05, ...[...stream, ...reference].map(item => item.max_depth_m));
  const yRain = (value) => bottom - (bottom - top) * value / rainMax;
  const yDepth = (value) => bottom - (bottom - top) * value / depthMax;
  const svg = chartFrame(`시각별 최대 강우 ${num(rainMax)} mm, 최대 모의 수심 ${num(depthMax, 2)} m`, 116);
  for (const v of [0, rainMax / 2, rainMax]) {
    svgElement(svg, "line", {x1: left, x2: right, y1: yRain(v), y2: yRain(v), stroke: "#e3ecf3"});
    svgElement(svg, "text", {x: left - 4, y: yRain(v) + 3, fill: "#526672", "font-size": 14, "text-anchor": "end"}, num(v));
  }
  for (const v of [depthMax / 2, depthMax]) {
    svgElement(svg, "text", {x: right + 4, y: yDepth(v) + 3, fill: "#1b64b5", "font-size": 14}, num(v, 2));
  }
  const width = Math.max(.6, (right - left) / n - .6);
  timeline.forEach((item, i) => {
    const mean = item.rain_interval_mm.reduce((a, b) => a + b, 0) / item.rain_interval_mm.length;
    svgElement(svg, "rect", {x: x(i) - width / 2, y: yRain(item.rain_max_mm), width, height: bottom - yRain(item.rain_max_mm), fill: "#9fd3e0"});
    svgElement(svg, "rect", {x: x(i) - width / 2, y: yRain(mean), width, height: bottom - yRain(mean), fill: "#2a8fa8"});
  });
  for (const [series, color, dash] of [[reference, "#6a6788", "4 3"], [stream, "#1b64b5", ""]]) {
    const points = series.filter(item => index.has(item.time))
      .map(item => [x(index.get(item.time)), yDepth(item.max_depth_m)].join(",")).join(" ");
    if (points) svgElement(svg, "polyline", {points, fill: "none", stroke: color, "stroke-width": 1.8, "stroke-dasharray": dash});
  }
  cursor(svg, x, top, bottom);
  svgElement(svg, "text", {x: left, y: 110, fill: "#526672", "font-size": 14}, formatTime(timeline[0].time));
  svgElement(svg, "text", {x: right, y: 110, fill: "#526672", "font-size": 14, "text-anchor": "end"}, formatTime(timeline.at(-1).time));
  const hit = svgElement(svg, "rect", {x: left, y: top - 4, width: right - left, height: bottom - top + 4, fill: "transparent", class: "series-hit"});
  hit.addEventListener("click", (event) => {
    const box = svg.getBoundingClientRect();
    const position = (event.clientX - box.left) / box.width * 400;
    const i = Math.min(n - 1, Math.max(0, Math.floor((position - left) / (right - left) * n)));
    stopPlayback();
    follow = i === frames.length - 1;
    void selectFrame(i);
  });
  target.append(svg, chartKey([
    ["관측소 최대 10분 강우 (mm)", "#9fd3e0"], ["관측소 평균 (mm)", "#2a8fa8"],
    ["Streaming 최대 수심 (m)", "#1b64b5"], ["Reference 최대 수심 (m)", "#6a6788"],
  ]));
}

// Update time per input; archived selective runs also show the active-cell share.
function renderLatency() {
  const target = el("latency-series");
  target.replaceChildren();
  const timeline = timelineFrames();
  if (!timeline.length) return;
  const {stream, reference} = seriesByMode();
  const n = timeline.length;
  const index = new Map(timeline.map((item, i) => [item.time, i]));
  const left = 34, right = 366, top = 8, bottom = 80;
  const x = (i) => left + (right - left) * (i + .5) / n;
  const maxSeconds = Math.max(.01, ...[...stream, ...reference].map(item => item.update_latency_seconds));
  const y = (value) => bottom - (bottom - top) * value / maxSeconds;
  const cells = metadata?.valid_cell_count || 1;
  const svg = chartFrame(`10분 입력당 갱신 시간, 최대 ${num(maxSeconds, 2)}초`, 98);
  const share = stream.filter(item => index.has(item.time) && item.mode === "streaming" && !hasPeriods(item));
  if (share.length) {
    const xs = share.map(item => x(index.get(item.time)));
    const points = share.map((item, i) => [xs[i], bottom - (bottom - top) * item.active_cell_count / cells].join(","));
    svgElement(svg, "polygon", {points: [`${xs[0]},${bottom}`, ...points, `${xs.at(-1)},${bottom}`].join(" "), fill: "#f6c24a", "fill-opacity": .35});
    svgElement(svg, "text", {x: right + 4, y: top + 3, fill: "#a6602a", "font-size": 14}, "100%");
  }
  for (const v of [0, maxSeconds / 2, maxSeconds]) {
    svgElement(svg, "line", {x1: left, x2: right, y1: y(v), y2: y(v), stroke: "#e3ecf3"});
    svgElement(svg, "text", {x: left - 4, y: y(v) + 3, fill: "#526672", "font-size": 14, "text-anchor": "end"}, num(v, 2));
  }
  for (const [series, color, dash] of [[reference, "#6a6788", "4 3"], [stream, "#1b64b5", ""]]) {
    const points = series.filter(item => index.has(item.time))
      .map(item => [x(index.get(item.time)), y(item.update_latency_seconds)].join(",")).join(" ");
    if (points) svgElement(svg, "polyline", {points, fill: "none", stroke: color, "stroke-width": 1.6, "stroke-dasharray": dash});
  }
  cursor(svg, x, top, bottom);
  svgElement(svg, "text", {x: left, y: 94, fill: "#526672", "font-size": 14}, "10분 입력 하나를 반영하는 데 걸린 시간 (초)");
  target.append(svg, chartKey([
    ["Streaming", "#1b64b5"], ["Reference", "#6a6788"], ...(share.length ? [["Streaming 활성 셀 비율", "#f6c24a"]] : []),
  ]));
}

async function initMap() {
  metadata = await api("/api/map");
  stations = new globalThis.Map(metadata.gauges.map(gauge => [gauge.id, gauge]));
  renderMapMetadata();
  updateDomain(metadata.bounds);
  if (!health.map_ready) throw new Error("지도 파일이 없습니다. 설치와 실행 안내의 데이터 준비 단계를 확인하세요.");
  const {Map, Marker, NavigationControl, ScaleControl, AttributionControl} = await import("/assets/vendor/maplibre-gl.mjs");
  const [west, south, east, north] = metadata.bounds;
  const bounds = [[west, south], [east, north]];
  const tileTemplate = `${window.location.origin}/api/terrain/{z}/{x}/{y}.png`;
  const rasterBounds = [126.7,37.4,127.2,37.72];
  const coverage = metadata.dem_bounds.map(([w,s,e,n])=>polygon([Math.max(w,126.7),Math.max(s,37.4),Math.min(e,127.2),Math.min(n,37.72)]));
  const createMap = (container) => new Map({
    container, bounds, fitBoundsOptions: {padding: 45},
    pitch: 0, maxPitch: 70, maxZoom: 17, minZoom: 8, attributionControl: false,
    style: {
      version: 8,
      sources: {
        dem: {type: "raster-dem", tiles: [tileTemplate], tileSize: 256, maxzoom: 13, bounds: rasterBounds, encoding: "terrarium",
              attribution: '<a href="https://doi.org/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn">FABDEM V1-2 · Bristol/Fathom · CC BY-NC-SA 4.0</a>'},
        osm: {type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256,
              maxzoom: 19, attribution: '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>'},
        coverage: {type:"geojson",data:{type:"FeatureCollection",features:coverage}},
        draft: {type:"geojson",data:{type:"FeatureCollection",features:[]}},
        gauges: {type:"geojson",data:{type:"FeatureCollection",features:[]},attribution:"서울시 OA-1168 강우량"},
        pumps: {type:"geojson",data:"/api/map/pumps",attribution:"서울시 OA-21179 빗물펌프장"},
        city: {type:"geojson",data:"/api/map/seoul", attribution:"통계청 SGIS 시도 경계 (2025)"},
        domain: {type: "geojson", data: {
          type: "Feature", properties: {},
          geometry: {type: "Polygon", coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
        }},
      },
      layers: [
        {id: "background", type: "background", paint: {"background-color": "#eef1f1"}},
        {id: "streets", type: "raster", source: "osm", layout: {visibility: "none"}, paint: {"raster-opacity": .82, "raster-saturation": -.55}},
        {id: "relief", type: "hillshade", source: "dem", paint: {"hillshade-shadow-color": "#315b57", "hillshade-highlight-color": "#fffef7", "hillshade-exaggeration": .12}},
        {id:"coverage-outline",type:"line",source:"coverage",layout:{visibility:"none"},paint:{"line-color":"#52735f","line-width":1.5,"line-dasharray":[5,3]}},
        {id: "domain-outline", type: "line", source: "domain", paint: {"line-color": "#244f61", "line-width": 2, "line-dasharray": [3, 2]}},
        {id:"city-outline",type:"line",source:"city",paint:{"line-color":"#683b80","line-width":1.5}},
        {id: "draft-outline", type: "line", source: "draft", paint: {"line-color": "#9c4c21", "line-width": 2, "line-dasharray": [3, 2]}},
        {id: "pumps", type: "circle", source: "pumps", layout: {visibility: "none"}, paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 3, 14, 7],
          "circle-color": ["case", ["==", ["get", "rate_mm_h"], null], "#8a8a8a",
            ["step", ["get", "rate_mm_h"], "#d64c34", 40, "#f0964a", 55, "#e0b23c", 70, "#3c8caf"]],
          "circle-stroke-color": "#fff", "circle-stroke-width": 1.5,
        }},
        {id: "gauges", type: "circle", source: "gauges", paint: {
          "circle-radius": ["case", ["<", ["get", "mm"], 0], 4,
            ["interpolate", ["linear"], ["get", "mm"], 0, 4, 5, 7, 15, 11, 30, 16]],
          "circle-color": ["case", ["<", ["get", "mm"], 0], "#ffffff",
            ["interpolate", ["linear"], ["get", "mm"], 0, "#e8f3f7", 5, "#7cc4d8", 15, "#2a8fa8", 30, "#0b4f6c"]],
          "circle-opacity": .9, "circle-stroke-color": "#0b4f6c", "circle-stroke-width": 1.2,
        }},
      ],

    },
  });
  map = createMap("map");
  referenceMap = createMap("reference-map");
  for (const [from, to] of [[map, referenceMap], [referenceMap, map]]) {
    from.on("move", () => {
      if (syncCamera) return;
      syncCamera = true;
      to.jumpTo({center:from.getCenter(), zoom:from.getZoom(), bearing:from.getBearing(), pitch:from.getPitch()});
      syncCamera = false;
    });
  }
  referenceMap.addControl(new AttributionControl({compact: true}), "bottom-right");
  referenceMap.on("load", () => {
    referenceReady = true;
    updateDomain(mapBounds);
    updateGauges();
    if (frameIndex >= 0 || layer !== "depth") void selectFrame(frameIndex, true);
  });
  referenceMap.on("click", (event) => {
    if (!selecting) choosePoint(event.lngLat, Marker);
  });
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
    map.jumpTo({pitch: 0});
    for (const id of ["fit", "seoul", "pitch", "streets", "split", "gauges"]) el(id).disabled = false;
    updateGauges();
    renderState(replayState);
    if (west < 127.027539 && east > 127.027539 && south < 37.497958 && north > 37.497958) {
      const label = document.createElement("span");
      label.className = "map-name";
      label.textContent = "강남역";
      new Marker({element: label, anchor: "bottom"}).setLngLat([127.027539, 37.497958]).addTo(map);
    }
    if (frameIndex >= 0 || layer !== "depth") void selectFrame(frameIndex, true);
  });
  el("gauges").addEventListener("click", () => {
    showGauges = el("gauges").getAttribute("aria-pressed") !== "true";
    el("gauges").setAttribute("aria-pressed", showGauges);
    updateGauges();
  });
  el("fit").addEventListener("click", () => fitRegion(mapBounds));
  el("pitch").addEventListener("click", () => {
    const enabled = el("pitch").getAttribute("aria-pressed") !== "true";
    el("pitch").setAttribute("aria-pressed", enabled);
    for (const view of readyMaps()) view.setTerrain(enabled ? {source: "dem", exaggeration: 1} : null);
    map.jumpTo({pitch: enabled ? 42 : 0});
  });
  el("streets").addEventListener("click", () => {
    const enabled = el("streets").getAttribute("aria-pressed") !== "true";
    el("streets").setAttribute("aria-pressed", enabled);
    for (const view of readyMaps()) view.setLayoutProperty("streets", "visibility", enabled ? "visible" : "none");
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
        openPanel("setup-panel", false);
        el("select-area").focus();
      }
      return;
    }
    choosePoint(event.lngLat, Marker);
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
    const runs = await refreshHistory();
    if (health.replay_ready) {
      await poll();
      const demo = runs.find(run => run.reference_id && run.status === "completed" &&
        run.map.drainage_source === "facility" && run.frame_count === run.scenario.interval_count &&
        presetKey(run.map.bounds) === "seoul");
      if (!replayState.run_id && demo) {
        el("history").value = demo.id;
        await openHistory(false);
      }
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
el("drainage").addEventListener("change", () => {
  el("drain-label").textContent = drainageLabels[el("drainage").value];
  el("drainage-info").textContent = el("drainage").value === "facility"
    ? "하수관 설계 강우강도와 자치구별 빗물펌프장 용량으로 셀마다 배수능력을 정합니다."
    : "모든 셀에 같은 가정 배수율을 적용합니다. 실제 시설 자료를 반영하지 않습니다.";
});
for (const id of ["drain", "drainage", "threads", "boundary"]) {
  el(id).addEventListener("change", () => { void previewRegion(false); });
}
el("timeline").addEventListener("input", (event) => {
  const index = Number(event.target.value);
  stopPlayback();
  follow = index === frames.length - 1;
  void selectFrame(index);
});
el("latest").addEventListener("click", () => {
  stopPlayback();
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
  openPanel("setup-panel", false);
  el("select-area").focus();
});
el("seoul").addEventListener("click", () => map && fitRegion(presets.seoul));
el("history").addEventListener("change", () => {
  el("open-run").disabled = !el("history").value;
  el("reuse").disabled = !archivedRun || archivedRun.id !== el("history").value;
});
el("open-run").addEventListener("click", () => openHistory());
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
  openPanel("setup-panel");
  const config = run.settings || {bounds:run.map.bounds,drain_mm_h:run.map.default_drain_mm_h,threads:run.threads_requested,boundary:run.map.boundary};
  selectedBounds=config.bounds;
  el("drain").value=config.drain_mm_h;
  el("threads").value=config.threads;
  el("boundary").value=config.boundary;
  el("drainage").value=config.drainage ?? (run.map.drainage_source === "facility" ? "facility" : "uniform");
  el("drainage").dispatchEvent(new Event("change"));
  el("mode").value=run.reference_id ? "compare" : (run.mode ?? "compare");
  el("area").value=presetKey(selectedBounds) ?? "custom";
  await previewRegion(false);
  el("scenario").value=run.scenario.id;
});
el("play").addEventListener("click", togglePlayback);
for (const button of document.querySelectorAll("[data-layer]")) {
  button.addEventListener("click", () => {
    layer = button.dataset.layer;
    for (const option of document.querySelectorAll("[data-layer]")) {
      option.setAttribute("aria-pressed", String(option === button));
    }
    void selectFrame(frameIndex, true);
  });
}
let panelTrigger;
const panelNames = {"setup-panel":"새 계산", "history-panel":"저장 결과", "inputs-panel":"조건과 한계", "analysis-panel":"결과 분석", "point-panel":"선택 지점", "agent-panel":"Solar에 질문"};
function resizeMaps() {
  map?.resize();
  referenceMap?.resize();
}
function openPanel(id, focus = true) {
  if (focus) panelTrigger = document.activeElement;
  for (const key of Object.keys(panelNames)) {
    el(key).hidden = key !== id;
    if (el(key).tagName === "DETAILS") el(key).open = key === id;
  }
  el("panel-title").textContent = panelNames[id];
  el("workspace-panel").hidden = false;
  document.body.classList.add("panel-open");
  document.querySelectorAll("[data-panel]").forEach(button => button.setAttribute("aria-expanded", String(button.dataset.panel === id)));
  resizeMaps();
  if (focus) el("close-panel").focus();
}
function closePanel(restoreFocus = true) {
  el("workspace-panel").hidden = true;
  document.body.classList.remove("panel-open");
  document.querySelectorAll("[data-panel]").forEach(button => button.setAttribute("aria-expanded", "false"));
  resizeMaps();
  if (restoreFocus && panelTrigger?.isConnected) panelTrigger.focus();
}
function setCompare(enabled) {
  el("split").setAttribute("aria-pressed", String(enabled));
  el("map-view").setAttribute("aria-pressed", String(!enabled));
  el("map-pair").classList.toggle("single", !enabled);
  if (enabled) openPanel("analysis-panel");
  else closePanel(false);
  resizeMaps();
  if (mapReady) fitRegion(mapBounds);
}
el("split").addEventListener("click", () => setCompare(true));
el("map-view").addEventListener("click", () => setCompare(false));
document.querySelectorAll("[data-panel]").forEach(button => button.addEventListener("click", () => {
  if (!el("workspace-panel").hidden && !el(button.dataset.panel).hidden) closePanel();
  else openPanel(button.dataset.panel);
}));
el("close-panel").addEventListener("click", () => closePanel());
document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    if (selecting) { setAreaSelection(false); openPanel("setup-panel"); return; }
    document.querySelectorAll(".map-tools").forEach(tool => tool.open = false);
    if (!el("workspace-panel").hidden) closePanel();
  }
});
document.querySelectorAll(".map-tools").forEach(tool => tool.addEventListener("toggle", () => {
  if (tool.open) document.querySelectorAll(".map-tools").forEach(other => { if (other !== tool) other.open = false; });
}));
el("analysis-kind").addEventListener("change", () => {
  const performance = el("analysis-kind").value === "performance";
  el("rain-analysis").hidden = performance;
  el("performance-analysis").hidden = !performance;
  el("analysis-metrics").hidden = !performance;
});
el("retry-region").addEventListener("click", () => previewRegion(false));
new ResizeObserver(resizeMaps).observe(document.querySelector(".map-area"));
void init();
