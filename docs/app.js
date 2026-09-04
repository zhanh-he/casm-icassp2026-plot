"use strict";

const SOURCES = [
  { id: "original", label: "Original", color: "#42474d" },
  { id: "reference", label: "GroundTruth", color: "#242629" },
  { id: "direct", label: "Direct", color: "#409eff" },
  { id: "fixed_semimarkov", label: "Fixed Semi-Markov", color: "#ff7a3d" },
  { id: "dbn", label: "DBN adjusted", color: "#59c879" },
  { id: "casm", label: "CASM", color: "#9270ed" },
];

const ui = {
  frame: document.querySelector("#figureFrame"),
  music: document.querySelector("#musicPlayer"),
};

let cases = [];
let activeCaseIndex = 0;
let windowStart = 0;
let windowDuration = 18;
let selectedSource = "reference";
let audioContext = null;
let musicReady = false;
let musicStart = 0;
let musicDuration = 0;
let audioLoadGeneration = 0;
let activeNodes = [];
let playbackDuration = 0;
let playbackMediaStart = 0;
let animationFrame = 0;
let stopTimer = 0;
let isPlaying = false;
let figureControlsBound = false;

function figureDocument() {
  return ui.frame.contentDocument;
}

function inlineElement(selector) {
  return figureDocument()?.querySelector(selector);
}

function setStatus(message, state = "ready") {
  const status = inlineElement("#audition-status");
  const dot = inlineElement("#audition-status-dot");
  if (status) status.textContent = message;
  if (dot) dot.dataset.state = state;
}

function currentCase() {
  return cases[activeCaseIndex]?.data;
}

function currentCaseRecord() {
  return cases[activeCaseIndex];
}

function sourceDefinition(id = selectedSource) {
  return SOURCES.find((source) => source.id === id);
}

function formatTime(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const remainder = safe - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(2).padStart(5, "0")}`;
}

function renderSourceButtons() {
  const buttons = figureDocument()?.querySelectorAll("[data-audition-source]") || [];
  buttons.forEach((button) => {
    const selected = button.dataset.auditionSource === selectedSource;
    button.setAttribute("aria-pressed", String(selected));
    button.dataset.playing = String(selected && isPlaying);
    button.disabled = !musicReady;
  });
  const stop = inlineElement("#audition-stop");
  if (stop) stop.disabled = !isPlaying;
}

function visibleEvents(source) {
  const data = currentCase();
  if (!data || source === "original") return { beats: [], downbeats: [] };
  if (source === "reference") {
    return {
      beats: data.truth.beat_times,
      downbeats: data.truth.downbeat_times,
    };
  }
  return {
    beats: data.decoders[source].beat_times,
    downbeats: data.decoders[source].downbeat_times,
  };
}

async function ensureAudioContext() {
  if (!audioContext) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) throw new Error("This browser does not support click-track playback.");
    audioContext = new AudioContextClass();
  }
  if (audioContext.state !== "running") await audioContext.resume();
  return audioContext;
}

function scheduleClick(context, when, accent) {
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  const filter = context.createBiquadFilter();
  oscillator.type = "triangle";
  oscillator.frequency.setValueAtTime(accent ? 1560 : 980, when);
  oscillator.frequency.exponentialRampToValueAtTime(accent ? 980 : 620, when + 0.026);
  filter.type = "highpass";
  filter.frequency.value = 420;
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(accent ? 1.0 : 0.78, when + 0.002);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + (accent ? 0.075 : 0.052));
  oscillator.connect(filter).connect(gain).connect(context.destination);
  oscillator.start(when);
  oscillator.stop(when + 0.085);
  activeNodes.push(oscillator);
}

function audioCoversVisibleWindow() {
  if (!musicReady) return false;
  const end = Math.min(currentCase().duration_seconds, windowStart + windowDuration);
  return windowStart >= musicStart - 0.05 && end <= musicStart + musicDuration + 0.05;
}

async function playSelection() {
  const data = currentCase();
  if (!data || !musicReady) {
    setStatus("The performance is still loading. Please try again in a moment.", "error");
    return;
  }
  if (!audioCoversVisibleWindow()) {
    setStatus("The performance does not cover this window. Reload the demo.", "error");
    return;
  }

  stopPlayback();
  try {
    const windowEnd = Math.min(data.duration_seconds, windowStart + windowDuration);
    playbackDuration = Math.max(0.01, windowEnd - windowStart);
    playbackMediaStart = windowStart - musicStart;
    ui.music.currentTime = playbackMediaStart;
    ui.music.volume = 1;
    ui.music.muted = false;
    ui.music.playbackRate = 1;

    const contextPromise = selectedSource === "original" ? Promise.resolve(null) : ensureAudioContext();
    const musicPromise = ui.music.play();
    const [context] = await Promise.all([contextPromise, musicPromise]);

    if (selectedSource !== "original") {
      const events = visibleEvents(selectedSource);
      const anchor = musicStart + ui.music.currentTime;
      const now = context.currentTime + 0.025;
      events.beats
        .filter((time) => time >= anchor - 0.01 && time <= windowEnd)
        .forEach((time) => {
          const accent = events.downbeats.some((downbeat) => Math.abs(downbeat - time) <= 0.07);
          scheduleClick(context, now + Math.max(0, time - anchor), accent);
        });
    }

    isPlaying = true;
    renderSourceButtons();
    setStatus(`${sourceDefinition().label} playing from ${windowStart.toFixed(2)} s.`, "playing");
    stopTimer = window.setTimeout(() => stopPlayback(true), (playbackDuration + 0.2) * 1000);
    updatePlaybackProgress();
  } catch (error) {
    stopPlayback();
    setStatus(`Playback failed: ${error.message || "the browser rejected audio playback."}`, "error");
  }
}

function stopPlayback(completed = false) {
  if (stopTimer) window.clearTimeout(stopTimer);
  stopTimer = 0;
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
  animationFrame = 0;
  ui.music.pause();
  activeNodes.forEach((node) => {
    try { node.stop(); } catch (_) { /* already stopped */ }
  });
  activeNodes = [];
  isPlaying = false;
  renderSourceButtons();

  const progress = inlineElement("#audition-progress");
  const time = inlineElement("#audition-time");
  if (completed) {
    if (progress) progress.value = 1;
    if (time) time.textContent = `${formatTime(playbackDuration)} / ${formatTime(playbackDuration)}`;
    setStatus(`${sourceDefinition().label} window completed.`);
  } else if (cases.length) {
    if (progress) progress.value = 0;
    if (time) time.textContent = `${formatTime(0)} / ${formatTime(windowDuration)}`;
    setStatus(`${sourceDefinition().label} ready at ${windowStart.toFixed(2)} s.`);
  }
  drawPlayhead(null);
}

function updatePlaybackProgress() {
  if (!isPlaying || !playbackDuration) return;
  const elapsed = Math.min(playbackDuration, Math.max(0, ui.music.currentTime - playbackMediaStart));
  const progress = inlineElement("#audition-progress");
  const time = inlineElement("#audition-time");
  if (progress) progress.value = elapsed / playbackDuration;
  if (time) time.textContent = `${formatTime(elapsed)} / ${formatTime(playbackDuration)}`;
  drawPlayhead(windowStart + elapsed);
  if (elapsed < playbackDuration && !ui.music.paused) {
    animationFrame = window.requestAnimationFrame(updatePlaybackProgress);
  }
}

function drawPlayhead(time) {
  const svg = figureDocument()?.querySelector("#decoder-contrast-real-v2 svg");
  if (!svg) return;
  const existing = svg.querySelector("#audition-playhead");
  if (time == null) {
    existing?.remove();
    return;
  }
  const viewBox = svg.viewBox.baseVal;
  const width = viewBox.width || svg.clientWidth;
  const left = width < 540 ? 92 : 136;
  const right = 18;
  const ratio = Math.min(1, Math.max(0, (time - windowStart) / windowDuration));
  const x = left + ratio * (width - left - right);
  const line = existing || figureDocument().createElementNS("http://www.w3.org/2000/svg", "line");
  line.id = "audition-playhead";
  line.setAttribute("x1", x);
  line.setAttribute("x2", x);
  line.setAttribute("y1", 18);
  line.setAttribute("y2", viewBox.height - 35);
  line.setAttribute("stroke", "#202327");
  line.setAttribute("stroke-width", "1.5");
  line.setAttribute("opacity", "0.78");
  line.setAttribute("pointer-events", "none");
  if (!existing) svg.append(line);
}

function clearAudio() {
  audioLoadGeneration += 1;
  musicReady = false;
  musicStart = 0;
  musicDuration = 0;
  ui.music.pause();
  ui.music.removeAttribute("src");
  ui.music.load();
  if (selectedSource === "original") selectedSource = "reference";
  renderSourceButtons();
}

function waitForPlayable() {
  return new Promise((resolve, reject) => {
    let timeout = 0;
    const cleanup = () => {
      window.clearTimeout(timeout);
      ui.music.removeEventListener("canplay", onReady);
      ui.music.removeEventListener("error", onError);
    };
    const onReady = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error(ui.music.error?.message || "the MP3 could not be loaded."));
    };
    ui.music.addEventListener("canplay", onReady);
    ui.music.addEventListener("error", onError);
    timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("audio loading timed out."));
    }, 15000);
  });
}

async function loadBundledAudio() {
  const record = currentCaseRecord();
  const bundled = record?.public_audio;
  const generation = ++audioLoadGeneration;
  if (!bundled) {
    clearAudio();
    setStatus("No bundled performance is available for this case.", "error");
    return;
  }

  musicReady = false;
  renderSourceButtons();
  setStatus(`Loading the complete ${record.label} performance...`);
  try {
    const playable = waitForPlayable();
    ui.music.src = bundled.url;
    ui.music.load();
    await playable;
    if (generation !== audioLoadGeneration || record !== currentCaseRecord()) return;
    musicStart = Number(bundled.start_seconds);
    musicDuration = Number.isFinite(ui.music.duration)
      ? ui.music.duration
      : Number(bundled.duration_seconds);
    musicReady = true;
    renderSourceButtons();
    setStatus(`${record.label} complete performance ready.`);
  } catch (error) {
    if (generation !== audioLoadGeneration) return;
    clearAudio();
    setStatus(`Could not load the performance: ${error.message}`, "error");
  }
}

function mountInlineAuditionControls() {
  const documentInside = figureDocument();
  if (!documentInside || documentInside.querySelector("#audition-toolbar")) return;
  const table = documentInside.querySelector("#decoder-contrast-real-v2 table");
  if (!table) return;

  const style = documentInside.createElement("style");
  style.textContent = `
#audition-toolbar { margin: 12px 0 20px; padding: 13px 0 14px; border-top: 1px solid #dce1e5; border-bottom: 1px solid #dce1e5; }
.audition-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
.audition-heading strong { font-size: 12px; font-weight: 700; }
.audition-window { color: #697079; font-size: 11px; font-variant-numeric: tabular-nums; }
.audition-buttons { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)) 38px; gap: 6px; }
.audition-method, .audition-stop { min-height: 36px; border: 1px solid #dce1e5; border-radius: 5px; background: #fff; color: #202327; cursor: pointer; font: inherit; font-size: 11px; font-weight: 650; }
.audition-method { position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 6px 7px 6px 10px; overflow: hidden; }
.audition-method::after { content: ""; position: absolute; inset: auto 0 0; height: 3px; background: var(--method-color); }
.audition-method:hover:not(:disabled), .audition-stop:hover:not(:disabled) { background: #f5f7f8; border-color: #aeb6bd; }
.audition-method[aria-pressed="true"] { background: color-mix(in srgb, var(--method-color) 10%, white); border-color: var(--method-color); }
.audition-method[data-playing="true"] .play-glyph { border-left-color: var(--method-color); }
.audition-method:disabled, .audition-stop:disabled { cursor: not-allowed; opacity: .45; }
.play-glyph { width: 0; height: 0; border-top: 5px solid transparent; border-bottom: 5px solid transparent; border-left: 7px solid currentColor; }
.audition-stop { display: inline-flex; align-items: center; justify-content: center; padding: 0; }
.stop-glyph { width: 9px; height: 9px; background: currentColor; }
.audition-transport { display: grid; grid-template-columns: minmax(120px, 1fr) 120px; align-items: center; gap: 10px; margin-top: 10px; }
.audition-progress { width: 100%; height: 6px; border: 0; border-radius: 0; overflow: hidden; background: #d9dde1; }
.audition-progress::-webkit-progress-bar { background: #d9dde1; }
.audition-progress::-webkit-progress-value { background: #2bb8b2; }
.audition-time { color: #697079; font-size: 11px; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.audition-status-row { display: flex; align-items: center; gap: 7px; margin-top: 8px; }
.audition-status-dot { flex: 0 0 auto; width: 7px; height: 7px; border-radius: 50%; background: #2bb8b2; }
.audition-status-dot[data-state="playing"] { background: #9270ed; }
.audition-status-dot[data-state="error"] { background: #d85555; }
.audition-status { margin: 0; color: #697079; font-size: 11px; line-height: 1.4; }
@media (max-width: 820px) { .audition-buttons { grid-template-columns: repeat(3, minmax(0, 1fr)); } .audition-stop { grid-column: 1 / -1; width: 38px; } }
@media (max-width: 520px) { .audition-heading { align-items: flex-start; flex-direction: column; gap: 3px; } .audition-buttons { grid-template-columns: repeat(2, minmax(0, 1fr)); } .audition-stop { grid-column: 1 / -1; } .audition-transport { grid-template-columns: 1fr 108px; } .audition-time { font-size: 10px; } }
`;
  documentInside.head.append(style);

  const toolbar = documentInside.createElement("section");
  toolbar.id = "audition-toolbar";
  toolbar.setAttribute("aria-label", "Quick audition");

  const heading = documentInside.createElement("div");
  heading.className = "audition-heading";
  const title = documentInside.createElement("strong");
  title.textContent = "Quick audition";
  const windowLabel = documentInside.createElement("span");
  windowLabel.id = "audition-window";
  windowLabel.className = "audition-window";
  heading.append(title, windowLabel);

  const buttons = documentInside.createElement("div");
  buttons.className = "audition-buttons";
  SOURCES.forEach((source) => {
    const button = documentInside.createElement("button");
    button.type = "button";
    button.className = "audition-method";
    button.dataset.auditionSource = source.id;
    button.style.setProperty("--method-color", source.color);
    button.setAttribute("aria-label", `Play ${source.label}`);
    const glyph = documentInside.createElement("span");
    glyph.className = "play-glyph";
    glyph.setAttribute("aria-hidden", "true");
    const label = documentInside.createElement("span");
    label.textContent = source.label;
    button.append(glyph, label);
    button.addEventListener("click", () => {
      stopPlayback();
      selectedSource = source.id;
      renderSourceButtons();
      void playSelection();
    });
    buttons.append(button);
  });

  const stop = documentInside.createElement("button");
  stop.id = "audition-stop";
  stop.type = "button";
  stop.className = "audition-stop";
  stop.setAttribute("aria-label", "Stop playback");
  stop.title = "Stop playback";
  const stopGlyph = documentInside.createElement("span");
  stopGlyph.className = "stop-glyph";
  stopGlyph.setAttribute("aria-hidden", "true");
  stop.append(stopGlyph);
  stop.addEventListener("click", () => stopPlayback(false));
  buttons.append(stop);

  const transport = documentInside.createElement("div");
  transport.className = "audition-transport";
  const progress = documentInside.createElement("progress");
  progress.id = "audition-progress";
  progress.className = "audition-progress";
  progress.max = 1;
  progress.value = 0;
  progress.setAttribute("aria-label", "Playback progress");
  const time = documentInside.createElement("output");
  time.id = "audition-time";
  time.className = "audition-time";
  transport.append(progress, time);

  const statusRow = documentInside.createElement("div");
  statusRow.className = "audition-status-row";
  const dot = documentInside.createElement("span");
  dot.id = "audition-status-dot";
  dot.className = "audition-status-dot";
  dot.setAttribute("aria-hidden", "true");
  const status = documentInside.createElement("p");
  status.id = "audition-status";
  status.className = "audition-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  statusRow.append(dot, status);

  toolbar.append(heading, buttons, transport, statusRow);
  table.insertAdjacentElement("afterend", toolbar);
  renderSourceButtons();
}

function syncFromFigure(caseChanged = false) {
  mountInlineAuditionControls();
  const documentInside = figureDocument();
  const caseSelect = documentInside?.querySelector("#decoder-contrast-case-v2");
  const slider = documentInside?.querySelector(".window-control input");
  if (!caseSelect || !slider || !cases.length) return;
  const nextCase = Number(caseSelect.value);
  if (caseChanged || nextCase !== activeCaseIndex) {
    stopPlayback();
    activeCaseIndex = nextCase;
    clearAudio();
    void loadBundledAudio();
  }
  windowStart = Number(slider.value);
  windowDuration = Number(currentCase().window_seconds);
  const end = Math.min(currentCase().duration_seconds, windowStart + windowDuration);
  const windowLabel = inlineElement("#audition-window");
  const time = inlineElement("#audition-time");
  if (windowLabel) windowLabel.textContent = `${cases[activeCaseIndex].label} | ${windowStart.toFixed(2)}-${end.toFixed(2)} s`;
  if (time) time.textContent = `${formatTime(0)} / ${formatTime(end - windowStart)}`;
  if (!musicReady) {
    setStatus(`Loading the complete ${cases[activeCaseIndex].label} performance...`);
  } else if (!audioCoversVisibleWindow()) {
    setStatus("The bundled performance does not cover this window. Reload the demo.", "error");
  } else {
    setStatus(`${sourceDefinition().label} ready at ${windowStart.toFixed(2)} s.`);
  }
}

function bindFigureControls() {
  if (figureControlsBound) return;
  const documentInside = figureDocument();
  const caseSelect = documentInside?.querySelector("#decoder-contrast-case-v2");
  const slider = documentInside?.querySelector(".window-control input");
  if (!caseSelect || !slider) return;
  figureControlsBound = true;
  mountInlineAuditionControls();
  caseSelect.addEventListener("change", () => window.setTimeout(() => syncFromFigure(true), 0));
  slider.addEventListener("input", () => {
    stopPlayback();
    syncFromFigure(false);
  });
  const resizeFrame = () => {
    const height = Math.max(980, documentInside.documentElement.scrollHeight + 6);
    ui.frame.style.height = `${height}px`;
  };
  resizeFrame();
  new ResizeObserver(resizeFrame).observe(documentInside.body);
  syncFromFigure(false);
}

async function initialize() {
  try {
    const response = await fetch("data/cases.json?v=20260905-3");
    if (!response.ok) throw new Error(`Case data returned ${response.status}.`);
    cases = await response.json();
    void loadBundledAudio();
    if (window.lucide) window.lucide.createIcons();
    ui.frame.addEventListener("load", bindFigureControls, { once: true });
    if (ui.frame.contentDocument?.readyState === "complete") bindFigureControls();
  } catch (error) {
    setStatus(`Could not load the demo data: ${error.message}`, "error");
  }
}

ui.music.addEventListener("ended", () => {
  if (isPlaying) stopPlayback(true);
});

document.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || ["INPUT", "BUTTON", "SELECT"].includes(document.activeElement?.tagName)) return;
  event.preventDefault();
  if (isPlaying) stopPlayback(false);
  else void playSelection();
});

initialize();
