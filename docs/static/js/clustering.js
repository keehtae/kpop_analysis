(() => {
  "use strict";
  const colors = ["#111111", "#a67c52", "#6f675d", "#d0ab7a", "#8d8377", "#c9c0b3", "#4d6656", "#647b8c", "#8c6070", "#967c43"];
  const ink = "#111111", accent = "#a67c52", muted = "#676158", line = "#d6cdc0";
  const body = "Avenir Next, Helvetica Neue, Segoe UI, sans-serif";
  const display = "Baskerville, Iowan Old Style, Palatino Linotype, Times New Roman, serif";
  const diverging = [[0, "#526b80"], [0.5, "#fbf8f2"], [1, accent]];
  const labels = {danceability: "Danceability", spectral_flux_mean: "Spectral Flux", spectral_centroid_mean: "Spectral Centroid",
    loudness_ebu128_loudness_range: "Loudness Range", tempo_bpm: "Tempo", dissonance_mean: "Dissonance",
    k: "K", within_cluster_SSE: "Within-cluster SSE", covariance_eigenvalue_ratio: "Covariance Eigenvalue Ratio",
    p95_distance: "95th Percentile Distance", song_id: "Song ID", davies_bouldin: "Davies–Bouldin"};
  const label = (key) => labels[key] || key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  const number = (value) => value == null ? "—" : Number(value).toLocaleString(undefined, {maximumFractionDigits: 4});
  const config = {responsive: true, displaylogo: false, scrollZoom: false};
  const states = new Map();
  const $ = (root, selector) => root.querySelector(selector);
  const select = (state, key) => $(state.root, `[data-control="${key}"]`);
  const run = (state) => state.report.runs[state.dataset];

  async function fetchJson(path) {
    const response = await fetch(path, {cache: "no-store"});
    if (!response.ok) throw new Error("The clustering results could not be loaded.");
    return response.json();
  }

  function axis(title = "") {
    return {title: {text: title, font: {family: body, size: 14, color: muted}},
      tickfont: {family: body, size: 14, color: muted}, gridcolor: line,
      zerolinecolor: line, linecolor: line, automargin: true};
  }

  function layout(title) {
    return {title: {text: title, x: 0, xanchor: "left", font: {family: display, size: 16, color: ink}},
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: {family: body, size: 14, color: ink}, colorway: colors,
      margin: {l: 55, r: 20, t: 55, b: 65},
      legend: {orientation: "h", x: 0, y: -0.18, font: {size: 14}},
      hoverlabel: {bgcolor: ink, bordercolor: ink, font: {family: body, color: "#ffffff", size: 14}},
      xaxis: axis(), yaxis: axis()};
  }

  function draw(state, name, traces, options) {
    const host = $(state.root, `[data-chart="${name}"]`);
    const promise = Plotly.react(host, traces, options, config);
    state.pending.push(Promise.resolve(promise));
  }

  function renderTable(host, rows) {
    host.replaceChildren();
    if (!rows.length) {
      const row = document.createElement("tr"), cell = document.createElement("td");
      cell.textContent = "No rows"; row.append(cell); host.append(row); return;
    }
    const columns = Object.keys(rows[0]);
    const head = document.createElement("thead"), header = document.createElement("tr");
    for (const column of columns) { const cell = document.createElement("th"); cell.scope = "col"; cell.textContent = label(column); header.append(cell); }
    head.append(header); host.append(head);
    const content = document.createElement("tbody");
    for (const record of rows) {
      const row = document.createElement("tr");
      for (const column of columns) {
        const cell = document.createElement("td"), value = record[column];
        cell.textContent = value == null ? "—" : column === "proportion" ? `${number(value * 100)}%` :
          column === "feature" || column === "feature_1" || column === "feature_2" ? label(value) :
          typeof value === "number" ? number(value) : Array.isArray(value) ? value.map(label).join(", ") :
          typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
        row.append(cell);
      }
      content.append(row);
    }
    host.append(content);
  }

  function csvDownload(rows, filename) {
    if (!rows.length) return;
    const columns = Object.keys(rows[0]);
    const quote = (value) => '"' + String(value == null ? "" : Array.isArray(value) ? value.join("; ") : value).replaceAll('"', '""') + '"';
    const content = [columns.map(quote).join(","), ...rows.map((row) => columns.map((column) => quote(row[column])).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", content], {type: "text/csv;charset=utf-8"}));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function tableData(state) {
    const result = run(state), points = result.points;
    const assignments = points.songs.map((song, index) => ({...song, cluster: points.cluster[index],
      ...Object.fromEntries(state.report.features.map((feature, j) => [feature, points.original[index][j]])),
      distance_to_centroid: points.distance[index], silhouette: points.silhouette[index]}));
    return {...result, assignments, centroids: result[`centroids_${select(state, "centroid-scale").value}`],
      diagnostics: [{k: 1, inertia: result.baseline_inertia, silhouette: null, davies_bouldin: null, rank_sum: null, used_for_final_model: false},
        ...result.diagnostics.map((row) => ({...row, used_for_final_model: row.k === result.k_used}))],
      outlier_fences: state.report.outlier_fences, removed_songs: state.report.removed_songs};
  }

  function assignmentsTable(state) {
    const query = select(state, "search").value.toLocaleLowerCase().trim();
    const rows = state.tables.assignments.filter((row) => !query || `${row.song} ${row.artist} ${row.album}`.toLocaleLowerCase().includes(query));
    const pages = Math.max(1, Math.ceil(rows.length / 25)); state.page = Math.min(state.page, pages - 1);
    renderTable($(state.root, '[data-model-table="assignments"]'), rows.slice(state.page * 25, (state.page + 1) * 25));
    $(state.root, "[data-assignment-page]").textContent = `${number(rows.length)} songs · Page ${state.page + 1} of ${pages}`;
    $(state.root, '[data-page="previous"]').disabled = state.page === 0;
    $(state.root, '[data-page="next"]').disabled = state.page + 1 === pages;
  }

  function metrics(state) {
    const result = run(state), host = $(state.root, "[data-model-metrics]"); host.replaceChildren();
    for (const [title, value] of [["Songs", result.songs], ["K", result.k_used], ["Silhouette", result.final_metrics.silhouette], ["Davies–Bouldin", result.final_metrics.davies_bouldin]]) {
      const card = document.createElement("article"), caption = document.createElement("div"), metric = document.createElement("div");
      card.className = "stat-card"; caption.className = "metric-label"; metric.className = "metric-value";
      caption.textContent = title; metric.textContent = number(value); card.append(caption, metric); host.append(card);
    }
  }

  function correlation(state) {
    const result = run(state), features = state.report.features.map(label);
    draw(state, "correlation", [{type: "heatmap", z: result.correlation, x: features, y: features,
      zmin: -1, zmax: 1, zmid: 0, colorscale: diverging, texttemplate: "%{z:.2f}",
      textfont: {size: 14}, colorbar: {title: {text: "Pearson r"}},
      hovertemplate: "%{y}<br>%{x}<br>r = %{z:.4f}<extra></extra>"}],
      {...layout("Correlation Matrix"), xaxis: {...axis(), tickangle: -30}, yaxis: {...axis(), autorange: "reversed"}});
  }

  function distributions(state) {
    const result = run(state), feature = select(state, "distribution-feature").value;
    const index = state.report.features.indexOf(feature), histogram = result.distributions[feature];
    const widths = histogram.edges.slice(1).map((value, i) => value - histogram.edges[i]);
    draw(state, "histogram", [{type: "bar", x: widths.map((width, i) => histogram.edges[i] + width / 2),
      y: histogram.counts, width: widths, marker: {color: accent, line: {color: "#fbf8f2", width: 1}},
      hovertemplate: "%{x:.5g}<br>Songs: %{y}<extra></extra>"}],
      {...layout(label(feature)), bargap: 0, xaxis: axis(label(feature)), yaxis: axis("Songs")});
    draw(state, "boxplot", [{type: "box", x: result.points.original.map((row) => row[index]), orientation: "h",
      quartilemethod: "linear", boxpoints: "outliers", name: label(feature),
      marker: {color: accent, size: 5}, line: {color: accent}, fillcolor: "rgba(166,124,82,0.15)"}],
      {...layout("Boxplot"), showlegend: false, xaxis: axis(label(feature)), yaxis: {...axis(), visible: false}});
  }

  function scatterplots(state) {
    const result = run(state), points = result.points, scale = select(state, "scale").value;
    const values = points[scale], colored = select(state, "color").value === "clusters";
    const [first, second] = select(state, "pair").value.split(",").map(Number);
    const featureLabels = state.report.features.map((feature) => label(feature) + (scale === "standardized" ? " (z-score)" : ""));
    const traces3d = [], traces2d = [];
    for (const cluster of colored ? result.cluster_summary.map((row) => row.cluster) : [null]) {
      const indices = points.cluster.map((value, index) => ({value, index})).filter((item) => cluster == null || item.value === cluster).map((item) => item.index);
      const color = cluster == null ? "#8d8377" : colors[(cluster - 1) % colors.length];
      const name = `${cluster == null ? "Songs" : "Cluster " + cluster} (n=${indices.length})`;
      const metadata = indices.map((index) => [points.songs[index].song, points.songs[index].artist, points.songs[index].album]);
      const common = {mode: "markers", name, legendgroup: String(cluster), customdata: metadata};
      traces3d.push({...common, type: "scatter3d", x: indices.map((i) => values[i][0]), y: indices.map((i) => values[i][1]), z: indices.map((i) => values[i][2]),
        marker: {size: 4, opacity: .7, color},
        hovertemplate: `%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}<br>${featureLabels[0]}: %{x:.5g}<br>${featureLabels[1]}: %{y:.5g}<br>${featureLabels[2]}: %{z:.5g}<extra>%{fullData.name}</extra>`});
      traces2d.push({...common, type: "scatter", x: indices.map((i) => values[i][first]), y: indices.map((i) => values[i][second]),
        marker: {size: 6, opacity: .6, color},
        hovertemplate: `%{customdata[0]}<br>%{customdata[1]}<br>${featureLabels[first]}: %{x:.5g}<br>${featureLabels[second]}: %{y:.5g}<extra>%{fullData.name}</extra>`});
      if (colored) {
        const center = result[`centroids_${scale}`].find((row) => row.cluster === cluster);
        const coordinates = state.report.features.map((feature) => center[feature]);
        traces3d.push({type: "scatter3d", mode: "markers", name: `Centroid ${cluster}`, legendgroup: String(cluster), showlegend: false,
          x: [coordinates[0]], y: [coordinates[1]], z: [coordinates[2]], marker: {size: 9, symbol: "diamond", color, line: {color: ink, width: 2}},
          hovertemplate: `Centroid ${cluster}<br>${featureLabels[0]}: %{x:.5g}<br>${featureLabels[1]}: %{y:.5g}<br>${featureLabels[2]}: %{z:.5g}<extra></extra>`});
      }
    }
    const sceneAxis = (name) => ({...axis(name), backgroundcolor: "rgba(0,0,0,0)", showbackground: false});
    draw(state, "scatter3d", traces3d, {...layout("3D Clusters"), margin: {l: 0, r: 0, t: 45, b: 100},
      scene: {xaxis: sceneAxis(featureLabels[0]), yaxis: sceneAxis(featureLabels[1]), zaxis: sceneAxis(featureLabels[2]),
        aspectmode: scale === "standardized" ? "data" : "cube", uirevision: state.entry.name},
      uirevision: `${state.dataset}-${scale}`, legend: {...layout("").legend, y: -.05}});
    draw(state, "scatter2d", traces2d, {...layout("Pairwise Scatterplot"),
      xaxis: axis(featureLabels[first]), yaxis: axis(featureLabels[second]),
      uirevision: `${state.dataset}-${scale}-${first}-${second}`});
  }

  function diagnostics(state) {
    const result = run(state), ks = result.diagnostics.map((row) => row.k);
    for (const metric of ["inertia", "silhouette", "davies_bouldin"]) {
      const withBaseline = metric === "inertia", x = withBaseline ? [1, ...ks] : ks;
      const y = withBaseline ? [result.baseline_inertia, ...result.diagnostics.map((row) => row[metric])] : result.diagnostics.map((row) => row[metric]);
      const optimum = withBaseline ? null : result.diagnostics.reduce((best, row) =>
        (metric === "silhouette" ? row[metric] > best[metric] : row[metric] < best[metric]) ? row : best).k;
      const lines = [result.k_used, ...(optimum != null && optimum !== result.k_used ? [optimum] : [])];
      draw(state, metric, [{type: "scatter", mode: "lines+markers", x, y,
        marker: {size: 7, color: accent}, line: {color: accent, width: 2}, hovertemplate: `K=%{x}<br>${label(metric)}: %{y:.5g}<extra></extra>`}],
        {...layout(metric === "silhouette" ? "Silhouette Score" : label(metric)),
          xaxis: {...axis("K"), tickmode: "array", tickvals: x}, yaxis: axis(),
          shapes: lines.map((value, index) => ({type: "line", x0: value, x1: value, y0: 0, y1: 1, yref: "paper", line: {color: index ? muted : ink, dash: index ? "dot" : "dash", width: 1}})),
          annotations: [{x: result.k_used, y: 1, yref: "paper", text: `K=${result.k_used}`, showarrow: false, yshift: 10, font: {size: 14, color: ink}}]});
    }
  }

  function clusterCharts(state) {
    const result = run(state), ks = result.diagnostics.map((row) => row.k);
    const maximum = Math.max(...ks), counts = ks.map((k) => Array.from({length: maximum}, (_, index) =>
      result.candidate_cluster_sizes.find((row) => row.k === k && row.cluster === index + 1)?.songs ?? null));
    draw(state, "candidate-sizes", [{type: "heatmap", x: Array.from({length: maximum}, (_, i) => i + 1), y: ks, z: counts,
      text: counts.map((row) => row.map((value) => value == null ? "" : String(value))), texttemplate: "%{text}", textfont: {size: 14},
      colorscale: [[0, "#fbf8f2"], [1, "#79532f"]], zmin: 0, hoverongaps: false,
      colorbar: {title: {text: "Songs"}}, hovertemplate: "K=%{y}<br>Cluster %{x}<br>Songs: %{z}<extra></extra>"}],
      {...layout("Cluster Counts by K"), xaxis: {...axis("Cluster"), dtick: 1}, yaxis: {...axis("K"), type: "category", autorange: "reversed"}});
    const z = result.centroids_standardized.map((row) => state.report.features.map((feature) => row[feature]));
    const limit = Math.max(.1, ...z.flat().map(Math.abs));
    draw(state, "centroid-heatmap", [{type: "heatmap", z, x: state.report.features.map(label), y: result.cluster_summary.map((row) => String(row.cluster)),
      zmin: -limit, zmax: limit, zmid: 0, colorscale: diverging, texttemplate: "%{z:.2f}", textfont: {size: 14},
      colorbar: {title: {text: "Mean z-score"}}, hovertemplate: "Cluster %{y}<br>%{x}<br>%{z:.4f}<extra></extra>"}],
      {...layout("Standardized Centroids"), xaxis: {...axis(), tickangle: -25}, yaxis: {...axis("Cluster"), type: "category", autorange: "reversed"}});
    draw(state, "cluster-sizes", [{type: "bar", x: result.cluster_summary.map((row) => row.cluster), y: result.cluster_summary.map((row) => row.size),
      marker: {color: result.cluster_summary.map((row) => colors[(row.cluster - 1) % colors.length])}, hovertemplate: "Cluster %{x}<br>Songs: %{y}<extra></extra>"}],
      {...layout("Cluster Sizes"), xaxis: {...axis("Cluster"), dtick: 1}, yaxis: axis("Songs")});
  }

  function profiles(state) {
    const result = run(state), feature = select(state, "profile-feature").value;
    const index = state.report.features.indexOf(feature), distribution = result.distributions[feature];
    const edges = distribution.profile_edges, widths = edges.slice(1).map((value, i) => value - edges[i]);
    const density = [], boxes = [];
    for (const group of distribution.clusters) {
      const cluster = group.cluster, color = colors[(cluster - 1) % colors.length];
      const values = result.points.original.filter((_, i) => result.points.cluster[i] === cluster).map((row) => row[index]);
      const name = `Cluster ${cluster} (n=${values.length})`;
      density.push({type: "bar", name, legendgroup: String(cluster),
        x: widths.map((width, i) => edges[i] + width / 2), y: group.density, width: widths,
        marker: {color}, opacity: .5, customdata: group.counts.map((count, i) => [edges[i], edges[i + 1], count, group.shares[i]]),
        hovertemplate: "%{customdata[0]:.5g}–%{customdata[1]:.5g}<br>Density: %{y:.5g}<br>Songs: %{customdata[2]}<br>Share: %{customdata[3]:.1%}<extra>%{fullData.name}</extra>"});
      boxes.push({type: "box", y: values, name: String(cluster), marker: {color, size: 5}, line: {color},
        fillcolor: color, opacity: .65, quartilemethod: "linear", boxpoints: "outliers", showlegend: false});
    }
    draw(state, "profile-density", density, {...layout(label(feature)), barmode: "overlay", bargap: 0,
      xaxis: axis(label(feature)), yaxis: axis("Density")});
    draw(state, "profile-boxes", boxes, {...layout("Boxplots by Cluster"), xaxis: {...axis("Cluster"), type: "category"}, yaxis: axis(label(feature))});
  }

  async function render(state) {
    state.pending = []; state.tables = tableData(state); metrics(state);
    state.root.querySelectorAll("[data-model-table]").forEach((host) => {
      if (host.dataset.modelTable !== "assignments") renderTable(host, state.tables[host.dataset.modelTable]);
    });
    assignmentsTable(state); correlation(state); distributions(state); scatterplots(state);
    diagnostics(state); clusterCharts(state); profiles(state);
    const p = state.report.preprocessing;
    $(state.root, "[data-preprocessing]").textContent = `Input: ${number(p.input_songs)} · Invalid feature rows: ${number(p.invalid_rows)} · Repeated feature rows: ${number(p.duplicate_feature_rows)} · IQR outliers: ${number(state.report.removed_songs.length)}`;
    await Promise.all(state.pending);
  }

  function options(host, items) {
    host.replaceChildren();
    for (const [value, text] of items) { const option = document.createElement("option"); option.value = value; option.textContent = text; host.append(option); }
  }

  async function loadModel(root, entry) {
    if (states.has(root)) return states.get(root).loading;
    const state = {root, entry, dataset: "all", page: 0, pending: []}; states.set(root, state);
    state.loading = (async () => {
      try {
        state.report = await fetchJson(`data/clustering/${entry.file}`);
        $(root, "[data-model-features]").textContent = state.report.features.map(label).join(" · ");
        for (const key of ["distribution-feature", "profile-feature"]) options(select(state, key), state.report.features.map((feature) => [feature, label(feature)]));
        const pairs = []; state.report.features.forEach((feature, i) => state.report.features.forEach((other, j) => { if (j > i) pairs.push([`${i},${j}`, `${label(feature)} / ${label(other)}`]); }));
        options(select(state, "pair"), pairs);
        $(root, ".model-results").hidden = false;
        await render(state); $(root, "[data-model-status]").hidden = true;
        select(state, "dataset").addEventListener("change", async () => {
          state.dataset = select(state, "dataset").value; state.page = 0;
          const controls = [...root.querySelectorAll("select")]; controls.forEach((control) => {control.disabled = true;});
          try { await render(state); } finally { controls.forEach((control) => {control.disabled = false;}); }
        });
        for (const key of ["scale", "color", "pair"]) select(state, key).addEventListener("change", () => {state.pending = []; scatterplots(state);});
        select(state, "distribution-feature").addEventListener("change", () => {state.pending = []; distributions(state);});
        select(state, "profile-feature").addEventListener("change", () => {state.pending = []; profiles(state);});
        select(state, "centroid-scale").addEventListener("change", () => {state.tables = tableData(state); renderTable($(root, '[data-model-table="centroids"]'), state.tables.centroids);});
        select(state, "search").addEventListener("input", () => {state.page = 0; assignmentsTable(state);});
        $(root, '[data-page="previous"]').addEventListener("click", () => {state.page--; assignmentsTable(state);});
        $(root, '[data-page="next"]').addEventListener("click", () => {state.page++; assignmentsTable(state);});
        root.querySelectorAll("[data-download]").forEach((button) => button.addEventListener("click", () => csvDownload(state.tables[button.dataset.download], `${entry.file.replace('.json', '')}-${state.dataset}-${button.dataset.download}.csv`)));
        root.querySelectorAll("details").forEach((detail) => detail.addEventListener("toggle", () => {if (detail.open) root.querySelectorAll(".model-chart").forEach((host) => {if (host.data) Plotly.Plots.resize(host);});}));
      } catch (error) {
        $(root, "[data-model-status]").textContent = error.message;
        $(root, "[data-model-status]").hidden = false;
        throw error;
      }
    })();
    return state.loading;
  }

  window.initClusteringPage = async () => {
    const manifest = await fetchJson("data/clustering/manifest.json");
    renderTable(document.querySelector("#model-comparison-table"), manifest.comparison);
    document.querySelector("#download-comparison").addEventListener("click", () => csvDownload(manifest.comparison, "model-comparison.csv"));
    const roots = [...document.querySelectorAll("[data-model]")];
    await loadModel(roots[0], manifest.models[0]);
    if (typeof IntersectionObserver !== "undefined") {
      const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
        if (entry.isIntersecting) {observer.unobserve(entry.target); const index = roots.indexOf(entry.target); loadModel(entry.target, manifest.models[index]).catch(console.error);}
      }), {rootMargin: "300px"});
      roots.slice(1).forEach((root) => observer.observe(root));
    } else {
      for (let i = 1; i < roots.length; i++) await loadModel(roots[i], manifest.models[i]);
    }
  };
})();
