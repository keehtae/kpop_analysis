(() => {
  "use strict";
  const charts = new Map();
  let data;
  const labels = {
    onset_rate: "Onset Rate", danceability: "Danceability",
    loudness_ebu128_integrated: "Integrated Loudness", loudness_ebu128_loudness_range: "Loudness Range",
    chords_changes_rate: "Chord Changes Rate", chords_number_rate: "Chord Number Rate",
  };
  const number = (value) => value == null ? "—" : Number(value).toLocaleString(undefined, {maximumFractionDigits: 4});
  const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]);

  function chart(host) {
    if (!charts.has(host)) charts.set(host, echarts.init(host, null, {renderer: "svg"}));
    return charts.get(host);
  }

  function base(title) {
    const style = data.style;
    return {
      backgroundColor: "transparent", animationDuration: 500,
      textStyle: {fontFamily: style.body, color: style.ink},
      title: {text: title, left: 0, top: 0,
        textStyle: {fontFamily: style.display, fontSize: 16, fontWeight: "bold", color: style.ink}},
      grid: {left: 55, right: 25, top: 65, bottom: 65, containLabel: true},
      tooltip: {trigger: "item", confine: true, backgroundColor: "rgba(17,17,17,0.94)",
        borderWidth: 0, textStyle: {color: "#ffffff", fontFamily: style.body, fontSize: 14}},
    };
  }

  function valueAxis(name) {
    return {type: "value", name, nameLocation: "middle", nameGap: 38, scale: true,
      nameTextStyle: {fontFamily: data.style.body, fontSize: 14, color: data.style.muted},
      axisLabel: {fontFamily: data.style.body, fontSize: 14, color: data.style.muted},
      axisLine: {lineStyle: {color: data.style.line}},
      splitLine: {lineStyle: {color: data.style.line, type: "dashed"}}};
  }

  function boxplot(host, column, title, unit = "") {
    const box = data.boxplots[column];
    const option = base(title);
    option.xAxis = valueAxis(unit);
    option.yAxis = {type: "category", data: [""], show: false};
    option.tooltip.formatter = (point) => {
      if (point.seriesType === "scatter") {
        const item = point.data;
        return `${escape(item.song)}<br>${escape(item.artist)}<br>${escape(item.album)}<br>${number(item.value[0])}`;
      }
      if (!box.whiskers) return "—";
      return ["Lower whisker", "Q1", "Median", "Q3", "Upper whisker"]
        .map((label, index) => `${label}: ${number(box.whiskers[index])}`).join("<br>");
    };
    option.series = [
      {type: "boxplot", data: box.whiskers ? [box.whiskers] : [],
        boxWidth: [30, 55], itemStyle: {color: data.style.fill, borderColor: data.style.accent, borderWidth: 2}},
      {type: "scatter", symbolSize: 8,
        itemStyle: {color: data.style.accent, opacity: 0.9},
        data: box.outliers.map((item, index) => ({...item, value: [item.value, 0],
          symbolOffset: [0, box.outliers.length > 1 ? -18 + 36 * index / (box.outliers.length - 1) : 0]}))},
    ];
    chart(host).setOption(option, true);
  }

  function histogram(host) {
    const histogram = data.histograms[host.dataset.audioHistogram];
    const option = base(host.dataset.title);
    option.xAxis = {
      type: "category", name: host.dataset.unit, nameLocation: "middle", nameGap: 48,
      data: histogram.bars.map((bin) => `${number(bin.start)}–${number(bin.end)}`),
      axisLabel: {rotate: 35, hideOverlap: true, fontFamily: data.style.body, fontSize: 14, color: data.style.muted},
      nameTextStyle: {fontFamily: data.style.body, fontSize: 14, color: data.style.muted},
      axisLine: {lineStyle: {color: data.style.line}}, axisTick: {alignWithLabel: true},
    };
    option.yAxis = {...valueAxis("Count"), scale: false, minInterval: 1};
    option.tooltip.formatter = (point) => {
      const bin = histogram.bars[point.dataIndex];
      return `${number(bin.start)}–${number(bin.end)}<br>Count: ${number(bin.count)}`;
    };
    option.series = [{type: "bar", barCategoryGap: "4%", data: histogram.bars.map((bin) => bin.count),
      itemStyle: {color: data.style.accent}}];
    chart(host).setOption(option, true);
  }

  function keyChart() {
    const view = document.querySelector("#key-view").value;
    const counts = data.krumhansl[view];
    const name = {key: "Key", scale: "Scale", combined: "Key + Scale"}[view];
    const option = base(`Krumhansl ${name}`);
    option.xAxis = {type: "category", data: counts.map((item) => item.label),
      axisLabel: {rotate: view === "combined" ? 45 : 0, fontFamily: data.style.body, fontSize: 14, color: data.style.muted},
      axisLine: {lineStyle: {color: data.style.line}}};
    option.yAxis = {...valueAxis("Count"), scale: false, minInterval: 1};
    option.tooltip.formatter = (point) => `${escape(point.name)}<br>Count: ${number(point.value)}`;
    option.series = [{type: "bar", data: counts.map((item) => item.count), itemStyle: {color: data.style.accent}}];
    chart(document.querySelector("#key-chart")).setOption(option, true);
  }

  function summaryTable(group, selected) {
    const host = document.querySelector(`[data-audio-summary="${group}"]`);
    const summaries = data.summaries[group];
    const columns = selected ? [selected] : Object.keys(summaries);
    const table = document.createDocumentFragment();
    const head = document.createElement("thead");
    const heading = document.createElement("tr");
    for (const label of ["Statistic", ...columns.map((column) => labels[column] || column.replace("mfcc_mean_", "MFCC "))]) {
      const cell = document.createElement("th"); cell.scope = "col"; cell.textContent = label; heading.append(cell);
    }
    head.append(heading); table.append(head);
    const body = document.createElement("tbody");
    for (const stat of ["max", "min", "mean", "median", "mode"]) {
      const row = document.createElement("tr");
      const label = document.createElement("th"); label.scope = "row"; label.textContent = stat[0].toUpperCase() + stat.slice(1); row.append(label);
      for (const column of columns) { const cell = document.createElement("td"); cell.textContent = number(summaries[column][stat]); row.append(cell); }
      body.append(row);
    }
    table.append(body); host.replaceChildren(table);
  }

  function spectralCharts() {
    const value = document.querySelector("#spectral-value").value;
    const unit = value === "flux" ? "" : "Hz";
    const name = value[0].toUpperCase() + value.slice(1);
    boxplot(document.querySelector("#spectral-mean"), `spectral_${value}_mean`, `${name} Mean`, unit);
    boxplot(document.querySelector("#spectral-stdev"), `spectral_${value}_stdev`, `${name} Standard Deviation`, unit);
  }

  function mfccChart() {
    const index = document.querySelector("#mfcc-value").value;
    const column = `mfcc_mean_${index}`;
    boxplot(document.querySelector("#mfcc-chart"), column, `MFCC ${index}`);
    summaryTable("mfcc", column);
  }

  window.initEssentiaExploratoryPage = async () => {
    const response = await fetch("data/essentia_exploratory.json", {cache: "no-store"});
    if (!response.ok) throw new Error("Essentia chart data could not be loaded.");
    data = await response.json();
    document.querySelectorAll("[data-audio-box]").forEach((host) => boxplot(host, host.dataset.audioBox, host.dataset.title, host.dataset.unit));
    document.querySelectorAll("[data-audio-histogram]").forEach(histogram);
    summaryTable("audio"); summaryTable("chords");
    keyChart(); spectralCharts(); mfccChart();
    document.querySelector("#key-view").addEventListener("change", keyChart);
    document.querySelector("#spectral-value").addEventListener("change", spectralCharts);
    document.querySelector("#mfcc-value").addEventListener("change", mfccChart);
    window.addEventListener("resize", () => charts.forEach((item) => item.resize()));
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(() => charts.forEach((item) => item.resize()));
      document.querySelectorAll(".audio-chart-grid > .chart-card").forEach((host) => observer.observe(host));
    }
  };
})();
