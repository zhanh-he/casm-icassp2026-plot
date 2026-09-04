"use strict";

const SOURCES = [
  { id: "original", label: "Original", color: "#42474d" },
  { id: "reference", label: "Reference", color: "#242629" },
  { id: "direct", label: "Direct", color: "#409eff" },
  { id: "fixed_semimarkov", label: "Fixed Semi-Markov", color: "#ff7a3d" },
  { id: "dbn", label: "DBN adjusted", color: "#59c879" },
  { id: "casm", label: "CASM", color: "#9270ed" },
];

const ui = {
  frame: document.querySelector("#figureFrame"),
  methodButtons: document.querySelector("#methodButtons"),
  play: document.querySelector("#playButton"),
  stop: document.querySelector("#stopButton"),
  progress: document.querySelector("#playProgress"),
  playTime: document.querySelector("#playTime"),
  windowLabel: document.querySelector("#windowLabel"),
  mixAudio: document.querySelector("#mixAudio"),
  clickVolume: document.querySelector("#clickVolume"),
  musicVolume: document.querySelector("#musicVolume"),
  status: document.querySelector("#audioStatus"),
  statusDot: document.querySelector("#statusDot"),
};

let cases = [];
let activeCaseIndex = 0;
let windowStart = 0;
let windowDuration = 18;
let selectedSource = "reference";
let audioContext = null;
let audioBuffer = null;
let audioFileName = "";
let audioBufferStart = 0;
let audioLoadGeneration = 0;
let activeNodes = [];
let playbackStart = 0;
let playbackDuration = 0;
let animationFrame = 0;
let stopTimer = 0;
let figureControlsBound = false;

function setStatus(message, state = "ready") {
  ui.status.textContent = message;
  ui.statusDot.dataset.state = state;
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
  ui.methodButtons.replaceChildren();
  SOURCES.forEach((source) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "method-option";
    button.dataset.source = source.id;
    button.style.setProperty("--method-color", source.color);
    button.textContent = source.label;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(source.id === selectedSource));
    button.disabled = source.id === "original" && !audioBuffer;
    button.addEventListener("click", () => selectSource(source.id));
    ui.methodButtons.append(button);
  });
}

function selectSource(source) {
  if (source === "original" && !audioBuffer) {
    setStatus("The bundled performance is not ready. Reload the page and try again.", "error");
    return;
  }
  stopPlayback();
  selectedSource = source;
  renderSourceButtons();
  const label = sourceDefinition().label;
  const mode = source === "original"
    ? "real performance"
    : (ui.mixAudio.checked && audioBuffer ? "real performance + synthesized clicks" : "synthesized click track");
  setStatus(`${label} selected: ${mode} follows the visible window.`);
}

function visibleEvents(source) {
  const data = currentCase();
  if (!data || source === "original") {
    return { beats: [], downbeats: [] };
  }
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
    if (!AudioContextClass) {
      throw new Error("This browser does not support Web Audio playback.");
    }
    audioContext = new AudioContextClass();
  }
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }
  return audioContext;
}

function scheduleClick(context, when, accent, volume) {
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  const filter = context.createBiquadFilter();
  oscillator.type = "triangle";
  oscillator.frequency.setValueAtTime(accent ? 1560 : 980, when);
  oscillator.frequency.exponentialRampToValueAtTime(accent ? 980 : 620, when + 0.026);
  filter.type = "highpass";
  filter.frequency.value = 420;
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, volume * (accent ? 0.86 : 0.58)), when + 0.002);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + (accent ? 0.075 : 0.048));
  oscillator.connect(filter).connect(gain).connect(context.destination);
  oscillator.start(when);
  oscillator.stop(when + 0.085);
  activeNodes.push(oscillator);
}

function scheduleMusic(context, when, duration) {
  if (!audioBuffer) return duration;
  const source = context.createBufferSource();
  const gain = context.createGain();
  const offset = Math.max(0, windowStart - audioBufferStart);
  const available = Math.max(0, audioBuffer.duration - offset);
  const actualDuration = Math.min(duration, available);
  if (actualDuration <= 0) return 0;
  source.buffer = audioBuffer;
  gain.gain.value = Number(ui.musicVolume.value);
  source.connect(gain).connect(context.destination);
  source.start(when, offset, actualDuration);
  activeNodes.push(source);
  return actualDuration;
}

function audioCoversVisibleWindow() {
  if (!audioBuffer) return false;
  const data = currentCase();
  const end = Math.min(data.duration_seconds, windowStart + windowDuration);
  const audioEnd = audioBufferStart + audioBuffer.duration;
  return windowStart >= audioBufferStart - 0.05 && end <= audioEnd + 0.05;
}

async function playSelection() {
  const data = currentCase();
  if (!data) return;
  if (selectedSource === "original" && !audioBuffer) {
    setStatus("The bundled performance is not ready. Reload the page and try again.", "error");
    return;
  }
  const shouldPlayMusic = selectedSource === "original" || (ui.mixAudio.checked && audioBuffer);
  if (shouldPlayMusic && !audioCoversVisibleWindow()) {
    const start = audioBufferStart.toFixed(2);
    const end = (audioBufferStart + (audioBuffer?.duration || 0)).toFixed(2);
    setStatus(`Music covers ${start}-${end} s. Reload the demo to restore the complete performance.`, "error");
    return;
  }

  stopPlayback();
  try {
    const context = await ensureAudioContext();
    const now = context.currentTime + 0.06;
    const windowEnd = Math.min(data.duration_seconds, windowStart + windowDuration);
    let duration = windowEnd - windowStart;
    if (shouldPlayMusic) {
      const musicDuration = scheduleMusic(context, now, duration);
      if (selectedSource === "original") duration = musicDuration;
    }

    if (selectedSource !== "original") {
      const events = visibleEvents(selectedSource);
      const clickVolume = Number(ui.clickVolume.value);
      events.beats
        .filter((time) => time >= windowStart && time <= windowEnd)
        .forEach((time) => {
          const accent = events.downbeats.some((downbeat) => Math.abs(downbeat - time) <= 0.07);
          scheduleClick(context, now + time - windowStart, accent, clickVolume);
        });
    }

    playbackStart = now;
    playbackDuration = Math.max(0.01, duration);
    ui.play.disabled = true;
    ui.stop.disabled = false;
    ui.progress.value = 0;
    const playbackMode = selectedSource === "original"
      ? " with the real performance"
      : (shouldPlayMusic ? " with the real performance and synthesized clicks" : " as clicks only");
    setStatus(`${sourceDefinition().label} playing${playbackMode} from ${windowStart.toFixed(2)} s.`, "playing");
    stopTimer = window.setTimeout(() => stopPlayback(true), (duration + 0.15) * 1000);
    updatePlaybackProgress();
  } catch (error) {
    stopPlayback();
    setStatus(error.message || "Playback could not start.", "error");
  }
}

function stopPlayback(completed = false) {
  if (stopTimer) window.clearTimeout(stopTimer);
  stopTimer = 0;
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
  animationFrame = 0;
  activeNodes.forEach((node) => {
    try { node.stop(); } catch (_) { /* already stopped */ }
  });
  activeNodes = [];
  ui.play.disabled = false;
  ui.stop.disabled = true;
  if (completed) {
    ui.progress.value = 1;
    ui.playTime.textContent = `${formatTime(playbackDuration)} / ${formatTime(playbackDuration)}`;
    setStatus(`${sourceDefinition().label} window completed.`);
  } else if (cases.length) {
    const end = Math.min(currentCase().duration_seconds, windowStart + windowDuration);
    ui.progress.value = 0;
    ui.playTime.textContent = `${formatTime(0)} / ${formatTime(end - windowStart)}`;
    setStatus(`${sourceDefinition().label} ready at ${windowStart.toFixed(2)} s.`);
  }
  drawPlayhead(null);
}

function updatePlaybackProgress() {
  if (!audioContext || !playbackDuration) return;
  const elapsed = Math.min(playbackDuration, Math.max(0, audioContext.currentTime - playbackStart));
  ui.progress.value = elapsed / playbackDuration;
  ui.playTime.textContent = `${formatTime(elapsed)} / ${formatTime(playbackDuration)}`;
  drawPlayhead(windowStart + elapsed);
  if (elapsed < playbackDuration) {
    animationFrame = window.requestAnimationFrame(updatePlaybackProgress);
  }
}

function drawPlayhead(time) {
  const documentInside = ui.frame.contentDocument;
  const svg = documentInside?.querySelector("#decoder-contrast-real-v2 svg");
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
  const line = existing || documentInside.createElementNS("http://www.w3.org/2000/svg", "line");
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
  audioBuffer = null;
  audioFileName = "";
  audioBufferStart = 0;
  ui.mixAudio.checked = false;
  ui.mixAudio.disabled = true;
  ui.musicVolume.disabled = true;
  if (selectedSource === "original") selectedSource = "reference";
  renderSourceButtons();
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

  audioBuffer = null;
  audioFileName = "";
  renderSourceButtons();
  setStatus(`Loading the complete ${record.label} performance...`);
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) throw new Error("This browser does not support Web Audio playback.");
    if (!audioContext) audioContext = new AudioContextClass();
    const response = await fetch(bundled.url);
    if (!response.ok) throw new Error(`Audio returned ${response.status}.`);
    const decoded = await audioContext.decodeAudioData(await response.arrayBuffer());
    if (generation !== audioLoadGeneration || record !== currentCaseRecord()) return;
    audioBuffer = decoded;
    audioBufferStart = Number(bundled.start_seconds);
    audioFileName = bundled.source_file;
    ui.mixAudio.disabled = false;
    ui.mixAudio.checked = true;
    ui.musicVolume.disabled = false;
    renderSourceButtons();
    setStatus(`${record.label} complete performance loaded; every decoder is mixed against the same recording.`);
  } catch (error) {
    if (generation !== audioLoadGeneration) return;
    clearAudio();
    setStatus(`Could not load the performance: ${error.message}`, "error");
  }
}

function syncFromFigure(caseChanged = false) {
  const documentInside = ui.frame.contentDocument;
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
  ui.windowLabel.textContent = `${cases[activeCaseIndex].label} · ${windowStart.toFixed(2)}-${end.toFixed(2)} s`;
  ui.playTime.textContent = `${formatTime(0)} / ${formatTime(end - windowStart)}`;
  if (!audioBuffer) {
    setStatus(`Loading the complete ${cases[activeCaseIndex].label} performance...`);
  } else if (!audioCoversVisibleWindow()) {
    setStatus("The bundled performance does not cover this window. Reload the demo.", "error");
  } else {
    setStatus(`${audioFileName} loaded; playback follows ${windowStart.toFixed(2)}-${end.toFixed(2)} s.`);
  }
}

function bindFigureControls() {
  if (figureControlsBound) return;
  const documentInside = ui.frame.contentDocument;
  const caseSelect = documentInside?.querySelector("#decoder-contrast-case-v2");
  const slider = documentInside?.querySelector(".window-control input");
  if (!caseSelect || !slider) {
    setStatus("The visualization did not initialize. Reload the page or check network access to D3.", "error");
    return;
  }
  figureControlsBound = true;
  caseSelect.addEventListener("change", () => window.setTimeout(() => syncFromFigure(true), 0));
  slider.addEventListener("input", () => {
    stopPlayback();
    syncFromFigure(false);
  });
  const resizeFrame = () => {
    const height = Math.max(950, documentInside.documentElement.scrollHeight + 6);
    ui.frame.style.height = `${height}px`;
  };
  resizeFrame();
  new ResizeObserver(resizeFrame).observe(documentInside.body);
  syncFromFigure(false);
}

async function initialize() {
  try {
    const response = await fetch("data/cases.json");
    if (!response.ok) throw new Error(`Case data returned ${response.status}.`);
    cases = await response.json();
    renderSourceButtons();
    void loadBundledAudio();
    if (window.lucide) window.lucide.createIcons();
    ui.frame.addEventListener("load", bindFigureControls, { once: true });
    if (ui.frame.contentDocument?.readyState === "complete") bindFigureControls();
  } catch (error) {
    setStatus(`Could not load the demo data: ${error.message}`, "error");
    ui.play.disabled = true;
  }
}

ui.play.addEventListener("click", playSelection);
ui.stop.addEventListener("click", () => stopPlayback(false));
document.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || ["INPUT", "BUTTON", "SELECT"].includes(document.activeElement?.tagName)) return;
  event.preventDefault();
  if (ui.play.disabled) stopPlayback(false);
  else playSelection();
});

initialize();
