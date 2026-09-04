#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a real-case four-decoder contrast visualization."
    )
    parser.add_argument("--asap", type=Path)
    parser.add_argument("--smc221", type=Path, required=True)
    parser.add_argument("--smc117", type=Path, required=True)
    parser.add_argument("--default-case", type=int, default=0, choices=(0, 1))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = [
        {
            "id": "smc-221",
            "label": "SMC 221",
            "screen_rank": 301,
            "summary": (
                "Adjusted DBN recovers a plausible variable-tempo path but remains "
                "less continuous than CASM."
            ),
            "data": json.loads(args.smc221.read_text(encoding="utf-8")),
        },
        {
            "id": "smc-117",
            "label": "SMC 117",
            "screen_rank": 234,
            "summary": (
                "Adjusted DBN reduces dense-path failures, yet unstable IBI "
                "transitions remain; CASM follows the local intervals."
            ),
            "data": json.loads(args.smc117.read_text(encoding="utf-8")),
        },
    ]
    payload = json.dumps(cases, separators=(",", ":"), ensure_ascii=True)
    fragment = TEMPLATE.replace("__CASES__", payload).replace(
        "__DEFAULT_CASE__", str(args.default_case)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(fragment, encoding="utf-8")
    print(args.output)


TEMPLATE = r'''
<div id="decoder-contrast-real-v2" class="decoder-contrast-real">
  <style>
    #decoder-contrast-real-v2 {
      --activation-color: var(--viz-series-6);
      --direct-color: var(--viz-series-1);
      --fixed-color: var(--viz-series-2);
      --dbn-color: var(--viz-series-3);
      --casm-color: var(--viz-series-5);
      color: var(--foreground);
      background: transparent;
      font-family: var(--font-sans);
      width: 100%;
      max-width: 100%;
      min-width: 0;
      padding: 8px 4px 16px;
      box-sizing: border-box;
      position: relative;
      overflow-x: hidden;
      contain: inline-size;
    }
    #decoder-contrast-real-v2 * { box-sizing: border-box; }
    #decoder-contrast-real-v2 .figure-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(230px, 330px);
      gap: 18px;
      align-items: end;
      padding: 0 6px 12px;
      min-width: 0;
    }
    #decoder-contrast-real-v2 h2 {
      margin: 0 0 5px;
      font-weight: 500;
      letter-spacing: 0;
      overflow-wrap: anywhere;
    }
    #decoder-contrast-real-v2 .subtitle,
    #decoder-contrast-real-v2 .case-summary,
    #decoder-contrast-real-v2 .source-line {
      margin: 0;
      letter-spacing: 0;
      overflow-wrap: anywhere;
    }
    #decoder-contrast-real-v2 .case-field { min-width: 0; max-width: 100%; }
    #decoder-contrast-real-v2 .case-field select { max-width: 100%; }
    #decoder-contrast-real-v2 .case-field .form-label { display: block; }
    #decoder-contrast-real-v2 .case-summary {
      padding: 9px 7px;
      border-top: 1px solid var(--border);
      color: var(--muted-foreground);
    }
    #decoder-contrast-real-v2 .metric-table { margin: 2px 0 8px; }
    #decoder-contrast-real-v2 .table-responsive {
      width: 100%;
      max-width: 100%;
      min-width: 0;
      overflow-x: auto;
    }
    #decoder-contrast-real-v2 .method-label {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      white-space: nowrap;
      font-weight: 500;
    }
    #decoder-contrast-real-v2 .method-swatch {
      display: inline-block;
      width: 19px;
      height: 3px;
      background: currentColor;
    }
    #decoder-contrast-real-v2 .direct-color { color: var(--direct-color); }
    #decoder-contrast-real-v2 .fixed-color { color: var(--fixed-color); }
    #decoder-contrast-real-v2 .dbn-color { color: var(--dbn-color); }
    #decoder-contrast-real-v2 .casm-color { color: var(--casm-color); }
    #decoder-contrast-real-v2 .window-control {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      padding: 7px 7px 0;
    }
    #decoder-contrast-real-v2 .window-control input { width: 100%; }
    #decoder-contrast-real-v2 .window-readout { white-space: nowrap; }
    #decoder-contrast-real-v2 .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 7px 16px;
      padding: 8px 7px 2px;
      color: var(--muted-foreground);
    }
    #decoder-contrast-real-v2 .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    #decoder-contrast-real-v2 .legend-activation {
      width: 22px;
      height: 0;
      border-top: 2px solid var(--activation-color);
    }
    #decoder-contrast-real-v2 .legend-diamond {
      width: 8px;
      height: 8px;
      background: var(--foreground);
      transform: rotate(45deg);
    }
    #decoder-contrast-real-v2 .legend-diamond.hollow {
      background: transparent;
      border: 1.5px solid var(--foreground);
    }
    #decoder-contrast-real-v2 .legend-guide {
      width: 0;
      height: 15px;
      border-left: 1px dashed var(--foreground);
      opacity: .55;
    }
    #decoder-contrast-real-v2 .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--foreground);
    }
    #decoder-contrast-real-v2 .legend-tick {
      width: 3px;
      height: 13px;
      background: var(--casm-color);
    }
    #decoder-contrast-real-v2 .legend-symbol {
      color: var(--casm-color);
      font-weight: 500;
    }
    #decoder-contrast-real-v2 .legend-prior {
      display: inline-block;
      width: 23px;
      height: 0;
      border-top: 2px solid currentColor;
    }
    #decoder-contrast-real-v2 .chart-wrap {
      position: relative;
      width: 100%;
      max-width: 100%;
      min-width: 0;
      overflow: hidden;
    }
    #decoder-contrast-real-v2 svg {
      display: block;
      width: 100%;
      height: 790px;
      overflow: visible;
    }
    #decoder-contrast-real-v2 .axis text,
    #decoder-contrast-real-v2 .axis-title,
    #decoder-contrast-real-v2 .lane-label,
    #decoder-contrast-real-v2 .plot-label {
      fill: var(--foreground);
      font-size: 12px;
      letter-spacing: 0;
    }
    #decoder-contrast-real-v2 .axis text,
    #decoder-contrast-real-v2 .lane-label,
    #decoder-contrast-real-v2 .plot-label { opacity: .7; }
    #decoder-contrast-real-v2 .axis path,
    #decoder-contrast-real-v2 .axis line { stroke: var(--border); }
    #decoder-contrast-real-v2 .grid line { stroke: var(--border); opacity: .55; }
    #decoder-contrast-real-v2 .grid path { display: none; }
    #decoder-contrast-real-v2 [data-chart-frame] {
      fill: transparent;
      stroke: var(--border);
    }
    #decoder-contrast-real-v2 .source-line {
      padding: 4px 7px 0;
      color: var(--muted-foreground);
    }
    #decoder-contrast-real-v2 .tooltip {
      position: absolute;
      pointer-events: none;
      z-index: 20;
      opacity: 0;
      min-width: 165px;
      padding: 7px 9px;
      color: var(--popover-foreground);
      background: var(--popover);
      border: 1px solid var(--border);
      box-shadow: 0 4px 14px color-mix(in srgb, var(--foreground) 16%, transparent);
    }
    @media (max-width: 620px) {
      #decoder-contrast-real-v2 .figure-head { grid-template-columns: 1fr; align-items: start; }
      #decoder-contrast-real-v2 .legend-item { white-space: normal; }
      #decoder-contrast-real-v2 svg { height: 810px; }
    }
  </style>

  <div class="figure-head">
    <div>
      <h2>真实案例：四种解码器在同一 activation 上分叉</h2>
      <p class="subtitle text-small"></p>
    </div>
    <label class="case-field form-label" for="decoder-contrast-case-v2">案例
      <select id="decoder-contrast-case-v2" class="form-select"></select>
    </label>
  </div>
  <p class="case-summary text-small" aria-live="polite"></p>

  <div class="table-responsive">
    <table class="table table-sm metric-table">
      <thead><tr><th>Decoder</th><th class="text-end">F1</th><th class="text-end">CMLt</th><th class="text-end">AMLt</th><th class="text-end">Events</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="legend text-small" aria-label="Event and interval legend">
    <span class="legend-item"><i class="legend-activation"></i>beat activation</span>
    <span class="legend-item"><i class="legend-diamond hollow"></i>GroundTruth beat</span>
    <span class="legend-item"><i class="legend-diamond"></i>GroundTruth downbeat</span>
    <span class="legend-item"><i class="legend-guide"></i>GroundTruth alignment guide</span>
    <span class="legend-item"><i class="legend-tick"></i>matched prediction</span>
    <span class="legend-item"><i class="legend-symbol">×</i>false-positive prediction</span>
    <span class="legend-item"><i class="legend-dot"></i>GroundTruth IBI</span>
    <span class="legend-item direct-color"><i class="legend-symbol">◆</i>Direct output IBI</span>
    <span class="legend-item fixed-color"><i class="legend-prior"></i>fixed τ + square output IBI</span>
    <span class="legend-item dbn-color"><i class="legend-symbol">▲</i>DBN output IBI</span>
    <span class="legend-item casm-color"><i class="legend-prior"></i>CASM local τ(t) + circle output IBI</span>
  </div>

  <div class="window-control">
    <input class="form-range" type="range" step="0.02" aria-label="Visible window start">
    <span class="window-readout text-small tabular-nums"></span>
  </div>
  <div class="chart-wrap">
    <svg role="img" aria-labelledby="decoder-contrast-title-v2 decoder-contrast-desc-v2">
      <title id="decoder-contrast-title-v2">Four real beat decoder paths on a shared activation</title>
      <desc id="decoder-contrast-desc-v2">Held-out Beat This activation, GroundTruth beats and downbeats, Direct, fixed Semi-Markov, DBN, and CASM beat paths, followed by four separated interval panels.</desc>
    </svg>
    <div class="tooltip text-small" role="tooltip"></div>
  </div>
  <p class="source-line text-small"></p>

  <script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
  <script>
  (() => {
    const CASES = __CASES__;
    const root = document.getElementById('decoder-contrast-real-v2');
    const select = root.querySelector('.form-select');
    const subtitle = root.querySelector('.subtitle');
    const summary = root.querySelector('.case-summary');
    const tableBody = root.querySelector('tbody');
    const slider = root.querySelector('.form-range');
    const readout = root.querySelector('.window-readout');
    const sourceLine = root.querySelector('.source-line');
    const tooltip = root.querySelector('.tooltip');
    const svg = d3.select(root.querySelector('svg'));
    const requestedCase = Number(new URLSearchParams(window.location.search).get('case') || __DEFAULT_CASE__);
    let activeCase = Number.isInteger(requestedCase) && requestedCase >= 0 && requestedCase < CASES.length ? requestedCase : 0;

    const methods = [
      {id: 'direct', label: 'Direct', short: 'Direct', color: 'direct'},
      {id: 'fixed_semimarkov', label: 'Fixed Semi-Markov', short: 'Fixed SMM', color: 'fixed'},
      {id: 'dbn', label: 'DBN', short: 'DBN', color: 'dbn'},
      {id: 'casm', label: 'CASM', short: 'CASM', color: 'casm'}
    ];
    const css = getComputedStyle(root);
    const colors = {
      activation: css.getPropertyValue('--activation-color').trim(),
      direct: css.getPropertyValue('--direct-color').trim(),
      fixed: css.getPropertyValue('--fixed-color').trim(),
      dbn: css.getPropertyValue('--dbn-color').trim(),
      casm: css.getPropertyValue('--casm-color').trim(),
      foreground: css.getPropertyValue('--foreground').trim(),
      border: css.getPropertyValue('--border').trim()
    };

    CASES.forEach((entry, index) => {
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = entry.label;
      select.appendChild(option);
    });

    function data() { return CASES[activeCase].data; }
    function pct(value) { return (100 * value).toFixed(1); }
    function methodColor(method) { return colors[method.color]; }
    function displayLabel(method, payload, compactLabel = false) {
      if (method.id === 'dbn' && payload.dbn_tuning) {
        return compactLabel ? 'DBN adj.' : 'DBN (adjusted)';
      }
      return compactLabel ? method.short : method.label;
    }

    function updateCase(resetWindow = false) {
      const entry = CASES[activeCase];
      const d = entry.data;
      subtitle.textContent = `${entry.label} · ${d.protocol.role} · Beat This ${d.protocol.fold} OOF · ${d.duration_seconds.toFixed(2)} s`;
      const local = d.casm_analysis.period_seconds.slice().sort((a, b) => a - b);
      const q = p => local[Math.min(local.length - 1, Math.floor(p * local.length))];
      summary.textContent = `${entry.summary} Global fixed τ = ${d.fixed_semimarkov.period_seconds.toFixed(2)} s; CASM local τ 10–90% = ${q(.1).toFixed(2)}–${q(.9).toFixed(2)} s.`;
      tableBody.innerHTML = methods.map(method => {
        const metric = d.decoders[method.id].beat_metrics;
        return `<tr><td><span class="method-label ${method.color}-color"><i class="method-swatch"></i>${displayLabel(method, d)}</span></td><td class="text-end tabular-nums">${pct(metric.fmeasure)}</td><td class="text-end tabular-nums">${pct(metric.cmlt)}</td><td class="text-end tabular-nums">${pct(metric.amlt)}</td><td class="text-end tabular-nums">${metric.event_count}</td></tr>`;
      }).join('');
      const maxStart = Math.max(0, d.duration_seconds - d.window_seconds);
      slider.min = '0';
      slider.max = maxStart.toFixed(2);
      if (resetWindow) slider.value = Math.min(maxStart, d.recommended_window_start).toFixed(2);
      const dbnDetail = d.dbn_tuning ? ` DBN uses one shared illustration-tuned setting across all three displayed cases: min/max BPM ${d.dbn_tuning.parameters.min_bpm}/${d.dbn_tuning.parameters.max_bpm}, transition λ ${d.dbn_tuning.parameters.transition_lambda}; it is not the aggregate DBN baseline.` : '';
      sourceLine.textContent = `Illustration-only selection: 768 high-divergence candidates screened from 4,556 OOF pieces; this case ranked ${entry.screen_rank}. Fixed Semi-Markov is a global-period mechanism replay, not an aggregate baseline. DBN intervals below are decoded output IBIs, not hidden-state traces.${dbnDetail}`;
    }

    function matchedFlags(events, truth, tolerance = .07) {
      return events.map(time => truth.some(target => Math.abs(target - time) <= tolerance));
    }

    function intervals(events, start, end) {
      const selected = events.filter(time => time >= start - 3 && time <= end + 3);
      const rows = [];
      for (let i = 1; i < selected.length; i += 1) {
        const time = (selected[i - 1] + selected[i]) / 2;
        if (time >= start && time <= end) rows.push({time, interval: selected[i] - selected[i - 1]});
      }
      return rows;
    }

    function intervalCurveMae(referenceRows, predictionRows) {
      if (!referenceRows.length || predictionRows.length < 2) return NaN;
      let total = 0;
      let count = 0;
      for (const reference of referenceRows) {
        if (reference.time < predictionRows[0].time || reference.time > predictionRows[predictionRows.length - 1].time) continue;
        let right = 1;
        while (right < predictionRows.length && predictionRows[right].time < reference.time) right += 1;
        if (right >= predictionRows.length) continue;
        const left = predictionRows[right - 1];
        const next = predictionRows[right];
        const weight = next.time === left.time ? 0 : (reference.time - left.time) / (next.time - left.time);
        const estimate = left.interval + weight * (next.interval - left.interval);
        total += Math.abs(reference.interval - estimate);
        count += 1;
      }
      return count ? total / count : NaN;
    }

    function draw() {
      const d = data();
      const start = Number(slider.value || 0);
      const end = Math.min(d.duration_seconds, start + d.window_seconds);
      readout.textContent = `${start.toFixed(2)}–${end.toFixed(2)} s`;
      const node = svg.node();
      const viewportWidth = root.ownerDocument.documentElement.clientWidth;
      const availableWidth = Math.max(320, viewportWidth - root.getBoundingClientRect().left - 4);
      const width = Math.max(320, Math.min(node.clientWidth || 736, availableWidth));
      const height = node.clientHeight || 790;
      const compact = width < 540;
      const margin = {top: 18, right: 18, bottom: 35, left: compact ? 92 : 136};
      const plotWidth = width - margin.left - margin.right;
      const activationTop = margin.top;
      const activationBottom = 150;
      const groundTruthY = 180;
      const laneStart = 212;
      const laneGap = 29;
      const laneBottom = laneStart + laneGap * (methods.length - 1);
      const intervalAreaTop = laneBottom + 39;
      const intervalBottom = height - margin.bottom;
      const panelGap = 7;
      const panelHeight = (intervalBottom - intervalAreaTop - panelGap * 4) / 5;
      const intervalPanels = [
        {id: 'groundtruth', label: 'GroundTruth IBI', short: 'GT IBI'},
        {id: 'direct', label: 'Direct', short: 'Direct'},
        {id: 'fixed', label: 'Fixed Semi-Markov', short: 'Fixed SMM'},
        {id: 'dbn', label: 'DBN', short: 'DBN'},
        {id: 'casm', label: 'CASM', short: 'CASM'}
      ].map((panel, index) => ({
        ...panel,
        top: intervalAreaTop + index * (panelHeight + panelGap),
        bottom: intervalAreaTop + index * (panelHeight + panelGap) + panelHeight
      }));
      const x = d3.scaleLinear().domain([start, end]).range([margin.left, width - margin.right]);
      const yActivation = d3.scaleLinear().domain([0, 1]).range([activationBottom, activationTop]);
      const first = Math.max(0, Math.floor(start * d.fps));
      const last = Math.min(d.beat_probability.length - 1, Math.ceil(end * d.fps));
      const frames = d3.range(first, last + 1).map(index => ({time: index / d.fps, value: d.beat_probability[index]}));
      const truthAll = d.truth.beat_times;
      const truth = truthAll.filter(time => time >= start && time <= end);
      const truthDownbeats = d.truth.downbeat_times.filter(time => time >= start && time <= end);
      const methodIntervals = Object.fromEntries(methods.map(method => [method.id, intervals(d.decoders[method.id].beat_times, start, end)]));
      const referenceIntervals = intervals(truthAll, start, end);
      const localPrior = d.casm_analysis.candidate_times.map((time, index) => ({
        time,
        interval: d.casm_analysis.period_seconds[index],
        confidence: d.casm_analysis.reliability_proxy[index]
      })).filter(row => row.time >= start && row.time <= end);
      const intervalValues = [d.fixed_semimarkov.period_seconds];
      referenceIntervals.forEach(row => intervalValues.push(row.interval));
      methodIntervals.direct.forEach(row => intervalValues.push(row.interval));
      methodIntervals.fixed_semimarkov.forEach(row => intervalValues.push(row.interval));
      methodIntervals.dbn.forEach(row => intervalValues.push(row.interval));
      methodIntervals.casm.forEach(row => intervalValues.push(row.interval));
      localPrior.forEach(row => intervalValues.push(row.interval));
      const extent = d3.extent(intervalValues);
      const pad = Math.max(.12, (extent[1] - extent[0]) * .12);
      const intervalDomain = d3.scaleLinear().domain([Math.max(0, extent[0] - pad), extent[1] + pad]).nice().domain();
      const panelScale = panel => d3.scaleLinear().domain(intervalDomain).range([panel.bottom - 5, panel.top + 5]);

      svg.attr('viewBox', `0 0 ${width} ${height}`);
      svg.selectAll('*').remove();
      const defs = svg.append('defs');
      const activationClip = `contrast-activation-${activeCase}`;
      defs.append('clipPath').attr('id', activationClip).append('rect').attr('x', margin.left).attr('y', activationTop).attr('width', plotWidth).attr('height', activationBottom - activationTop);
      intervalPanels.forEach(panel => {
        panel.clip = `contrast-${panel.id}-${activeCase}`;
        defs.append('clipPath').attr('id', panel.clip).append('rect').attr('x', margin.left).attr('y', panel.top).attr('width', plotWidth).attr('height', panelHeight);
      });
      svg.append('rect').attr('data-chart-frame', '').attr('x', margin.left).attr('y', activationTop).attr('width', plotWidth).attr('height', activationBottom - activationTop);
      svg.append('g').attr('class', 'grid').attr('transform', `translate(${margin.left},0)`).call(d3.axisLeft(yActivation).tickValues([0, .5, 1]).tickSize(-plotWidth).tickFormat(''));
      svg.append('g').attr('class', 'axis').attr('transform', `translate(${margin.left},0)`).call(d3.axisLeft(yActivation).tickValues([0, .5, 1]));
      intervalPanels.forEach(panel => {
        const yPanel = panelScale(panel);
        svg.append('rect').attr('data-chart-frame', '').attr('x', margin.left).attr('y', panel.top).attr('width', plotWidth).attr('height', panelHeight);
        svg.append('g').attr('class', 'axis').attr('transform', `translate(${margin.left},0)`).call(d3.axisLeft(yPanel).ticks(2));
        svg.append('text').attr('class', 'lane-label').attr('x', margin.left - 18).attr('y', (panel.top + panel.bottom) / 2 + 4).attr('text-anchor', 'end')
          .style('fill', panel.id === 'direct' ? colors.direct : panel.id === 'fixed' ? colors.fixed : panel.id === 'dbn' ? colors.dbn : panel.id === 'casm' ? colors.casm : colors.foreground)
          .text(compact ? panel.short : panel.label);
      });
      svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${intervalBottom})`).call(d3.axisBottom(x).ticks(compact ? 4 : 7));
      svg.append('text').attr('class', 'axis-title').attr('data-axis', 'y').attr('x', margin.left).attr('y', 11).text('beat activation probability');
      svg.append('text').attr('class', 'axis-title').attr('data-axis', 'y').attr('x', margin.left).attr('y', intervalAreaTop - 9).text(compact ? 'duration / IBI panels (s, shared scale)' : 'separated duration / decoded IBI panels (s, shared scale)');
      svg.append('text').attr('class', 'axis-title').attr('data-axis', 'x').attr('text-anchor', 'end').attr('x', width - margin.right).attr('y', height - 6).text('time (s)');

      svg.append('path').datum(frames).attr('clip-path', `url(#${activationClip})`).attr('fill', 'none').attr('stroke', colors.activation).attr('stroke-width', 2)
        .attr('d', d3.line().x(row => x(row.time)).y(row => yActivation(row.value)));
      truth.forEach(time => {
        const isDownbeat = truthDownbeats.some(downbeat => Math.abs(downbeat - time) <= .07);
        svg.append('line').attr('x1', x(time)).attr('x2', x(time)).attr('y1', activationTop).attr('y2', laneBottom + 12).attr('stroke', colors.foreground).attr('stroke-width', isDownbeat ? 1.25 : 1).attr('stroke-dasharray', '3 4').attr('opacity', isDownbeat ? .38 : .22);
        svg.append('path').attr('d', d3.symbol().type(d3.symbolDiamond).size(isDownbeat ? 62 : 48)()).attr('transform', `translate(${x(time)},${groundTruthY})`)
          .attr('fill', isDownbeat ? colors.foreground : 'none').attr('stroke', colors.foreground).attr('stroke-width', 1.4)
          .attr('data-tooltip', `GroundTruth ${isDownbeat ? 'downbeat' : 'beat'}: ${time.toFixed(3)} s`);
      });
      svg.append('line').attr('x1', margin.left).attr('x2', width - margin.right).attr('y1', groundTruthY).attr('y2', groundTruthY).attr('stroke', colors.border);
      svg.append('text').attr('class', 'lane-label').attr('x', margin.left - 9).attr('y', groundTruthY + 4).attr('text-anchor', 'end').text(compact ? 'GT' : 'GroundTruth');

      methods.forEach((method, methodIndex) => {
        const y = laneStart + methodIndex * laneGap;
        const allEvents = d.decoders[method.id].beat_times;
        const events = allEvents.filter(time => time >= start && time <= end);
        const eventMatched = matchedFlags(events, truth);
        const color = methodColor(method);
        svg.append('line').attr('x1', margin.left).attr('x2', width - margin.right).attr('y1', y).attr('y2', y).attr('stroke', colors.border);
        const visibleLabel = displayLabel(method, d, compact);
        svg.append('text').attr('class', 'lane-label').attr('x', margin.left - 9).attr('y', y + 4).attr('text-anchor', 'end').style('fill', color).text(visibleLabel);
        events.forEach((time, eventIndex) => {
          const isMatched = eventMatched[eventIndex];
          if (isMatched) {
            svg.append('line').attr('x1', x(time)).attr('x2', x(time)).attr('y1', y - 10).attr('y2', y + 10).attr('stroke', color).attr('stroke-width', 3)
              .attr('data-tooltip', `${visibleLabel} matched beat: ${time.toFixed(3)} s`);
          } else {
            svg.append('text').attr('x', x(time)).attr('y', y + 5).attr('text-anchor', 'middle').attr('fill', color).attr('font-size', 13).attr('font-weight', 500).text('×')
              .attr('data-tooltip', `${visibleLabel} false positive: ${time.toFixed(3)} s`);
          }
        });
      });

      const groundPanel = intervalPanels[0];
      const directPanel = intervalPanels[1];
      const fixedPanel = intervalPanels[2];
      const dbnPanel = intervalPanels[3];
      const casmPanel = intervalPanels[4];
      const yGround = panelScale(groundPanel);
      const yDirect = panelScale(directPanel);
      const yFixed = panelScale(fixedPanel);
      const yDbn = panelScale(dbnPanel);
      const yCasm = panelScale(casmPanel);

      if (referenceIntervals.length) {
        svg.append('path').datum(referenceIntervals).attr('clip-path', `url(#${groundPanel.clip})`).attr('fill', 'none').attr('stroke', colors.foreground).attr('stroke-width', 1).attr('opacity', .38)
          .attr('d', d3.line().x(row => x(row.time)).y(row => yGround(row.interval)));
        svg.selectAll('.groundtruth-ibi').data(referenceIntervals).enter().append('circle').attr('class', 'groundtruth-ibi').attr('cx', row => x(row.time)).attr('cy', row => yGround(row.interval)).attr('r', 3.6)
          .attr('fill', colors.foreground).attr('data-tooltip', row => `GroundTruth IBI: ${row.interval.toFixed(3)} s`);
      }

      const fixedTau = d.fixed_semimarkov.period_seconds;
      svg.append('line').attr('clip-path', `url(#${fixedPanel.clip})`).attr('x1', margin.left).attr('x2', width - margin.right).attr('y1', yFixed(fixedTau)).attr('y2', yFixed(fixedTau)).attr('stroke', colors.fixed).attr('stroke-width', 2).attr('stroke-dasharray', '5 4');
      svg.append('text').attr('class', 'plot-label').attr('x', margin.left + 5).attr('y', yFixed(fixedTau) - 5).style('fill', colors.fixed).text(`global τ = ${fixedTau.toFixed(2)} s`);

      if (localPrior.length) {
        svg.append('path').datum(localPrior).attr('clip-path', `url(#${casmPanel.clip})`).attr('fill', 'none').attr('stroke', colors.casm).attr('stroke-width', 2).attr('stroke-dasharray', '5 3')
          .attr('d', d3.line().x(row => x(row.time)).y(row => yCasm(row.interval)));
        svg.append('text').attr('class', 'plot-label').attr('x', margin.left + 5).attr('y', casmPanel.top + 14).style('fill', colors.casm).text('local τ(t), dashed');
      }

      function plotIntervals(rows, color, symbolType, label, panel, yPanel) {
        if (!rows.length) return;
        svg.append('path').datum(rows).attr('clip-path', `url(#${panel.clip})`).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 1.25).attr('opacity', .72)
          .attr('d', d3.line().x(row => x(row.time)).y(row => yPanel(row.interval)));
        svg.selectAll(`.${label}`).data(rows).enter().append('path').attr('class', label).attr('d', d3.symbol().type(symbolType).size(38)())
          .attr('transform', row => `translate(${x(row.time)},${yPanel(row.interval)})`).attr('fill', color)
          .attr('data-tooltip', row => `${label.replaceAll('-', ' ')} IBI: ${row.interval.toFixed(3)} s`);
      }
      plotIntervals(methodIntervals.direct, colors.direct, d3.symbolDiamond, 'direct-output', directPanel, yDirect);
      plotIntervals(methodIntervals.fixed_semimarkov, colors.fixed, d3.symbolSquare, 'fixed-output', fixedPanel, yFixed);
      plotIntervals(methodIntervals.dbn, colors.dbn, d3.symbolTriangle, 'dbn-output', dbnPanel, yDbn);
      plotIntervals(methodIntervals.casm, colors.casm, d3.symbolCircle, 'casm-output', casmPanel, yCasm);
      [
        [directPanel, methodIntervals.direct, colors.direct],
        [fixedPanel, methodIntervals.fixed_semimarkov, colors.fixed],
        [dbnPanel, methodIntervals.dbn, colors.dbn],
        [casmPanel, methodIntervals.casm, colors.casm]
      ].forEach(([panel, rows, color]) => {
        const mae = intervalCurveMae(referenceIntervals, rows);
        if (!Number.isFinite(mae)) return;
        svg.append('text').attr('class', 'plot-label').attr('x', width - margin.right - 5).attr('y', panel.top + 14).attr('text-anchor', 'end')
          .style('fill', color).text(`window IBI MAE ${mae.toFixed(3)} s`);
      });

      const marks = svg.selectAll('[data-tooltip]');
      marks.on('pointerenter', function(event) {
        tooltip.textContent = this.getAttribute('data-tooltip');
        tooltip.style.opacity = '1';
        const rect = root.getBoundingClientRect();
        tooltip.style.left = `${Math.min(rect.width - 184, Math.max(4, event.clientX - rect.left + 10))}px`;
        tooltip.style.top = `${Math.max(4, event.clientY - rect.top - 42)}px`;
      }).on('pointerleave', () => { tooltip.style.opacity = '0'; });
    }

    select.addEventListener('change', () => {
      activeCase = Number(select.value);
      updateCase(true);
      draw();
    });
    slider.addEventListener('input', draw);
    select.value = String(activeCase);
    updateCase(true);
    draw();
    requestAnimationFrame(() => window.scrollTo(0, 0));
    new ResizeObserver(draw).observe(root.querySelector('.chart-wrap'));
  })();
  </script>
</div>
'''


if __name__ == "__main__":
    main()
