const DATA_URL = "data/site_data.json";

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function setActiveNav() {
  const page = document.body.dataset.page;
  document.querySelectorAll(".nav-link").forEach((link) => {
    if (link.dataset.page === page) {
      link.classList.add("active");
      link.setAttribute("aria-current", "page");
    }
  });
}

function buildMiniList(items, renderItem) {
  return items.map(renderItem).join("");
}

function populateHome(data) {
  const overview = data.overview;
  const formatWeek = (value) => value.replace(/-W0?(\d+)$/, " W$1");
  const statHost = document.querySelector("[data-home-stats]");
  const songHost = document.querySelector("[data-home-songs]");
  const artistHost = document.querySelector("[data-home-artists]");

  if (statHost) {
    statHost.innerHTML = `
      <article class="stat-card"><div class="metric-label">Chart Rows</div><div class="metric-value">${formatNumber(overview.rows)}</div></article>
      <article class="stat-card"><div class="metric-label">Unique Artists</div><div class="metric-value">${formatNumber(overview.unique_artists)}</div></article>
      <article class="stat-card"><div class="metric-label">Unique Songs</div><div class="metric-value">${formatNumber(overview.unique_songs)}</div></article>
      <article class="stat-card"><div class="metric-label">Date Range</div><div class="metric-value metric-value-weeks">${formatWeek(overview.week_start)} – ${formatWeek(overview.week_end)}</div></article>
    `;
  }

  if (songHost) {
    songHost.innerHTML = buildMiniList(data.highlights.top_total_weeks.slice(0, 5), (item) => `
      <div class="mini-item">
        <div class="mini-title">${item.song_title}</div>
        <div class="mini-meta">${item.artist} · ${formatNumber(item.total_weeks_on_chart)} chart weeks</div>
      </div>
    `);
  }

  if (artistHost) {
    artistHost.innerHTML = data.highlights.top_artist_weeks.slice(0, 8).map((item) => `
      <article class="artist-card">
        <div class="metric-label">Artist Presence</div>
        <div class="mini-title">${item.artist}</div>
        <div class="mini-meta">${formatNumber(item.total_chart_entries)} chart entries</div>
      </article>
    `).join("");
  }
}

function populateMusic(data) {
  const songHost = document.querySelector("[data-music-songs]");
  const numberOneHost = document.querySelector("[data-music-number-ones]");
  const agencyHost = document.querySelector("[data-music-agencies]");
  const datasetHead = document.querySelector("[data-music-dataset-head]");
  const datasetBody = document.querySelector("[data-music-dataset-body]");

  if (songHost) {
    songHost.innerHTML = data.highlights.top_total_weeks.slice(0, 10).map((item, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>${item.song_title}</td>
        <td>${item.artist}</td>
        <td>${formatNumber(item.total_weeks_on_chart)}</td>
      </tr>
    `).join("");
  }

  if (numberOneHost) {
    numberOneHost.innerHTML = buildMiniList(data.highlights.top_number_one.slice(0, 6), (item) => `
      <div class="mini-item">
        <div class="mini-title">${item.song_title}</div>
        <div class="mini-meta">${item.artist} · ${item.weeks_at_number_one} weeks at #1</div>
      </div>
    `);
  }

  if (agencyHost) {
    agencyHost.innerHTML = data.highlights.agency_overview.slice(0, 6).map((item) => `
      <article class="detail-card">
        <div class="metric-label">Agency Footprint</div>
        <div class="mini-title">${item.agency_name}</div>
        <div class="mini-meta">Production: ${formatNumber(item.production_unique_songs)}</div>
        <div class="mini-meta">Distribution: ${formatNumber(item.distribution_unique_songs)}</div>
      </article>
    `).join("");
  }

  if (datasetHead && datasetBody) {
    const columns = data.dataset_browser.columns;
    datasetHead.innerHTML = `
      <tr>
        ${columns.map((column) => `<th>${column.replaceAll("_", " ")}</th>`).join("")}
      </tr>
    `;
    datasetBody.innerHTML = data.dataset_browser.rows.map((row) => `
      <tr>
        ${columns.map((column) => `<td>${row[column] ?? ""}</td>`).join("")}
      </tr>
    `).join("");
  }
}

async function init() {
  setActiveNav();
  const page = document.body.dataset.page;
  if (page === "exploratory") {
    if (window.initEssentiaExploratoryPage) await window.initEssentiaExploratoryPage();
    return;
  }
  if (!["home", "music"].includes(page)) {
    return;
  }

  const response = await fetch(DATA_URL, { cache: "no-store" });
  const data = await response.json();
  document.querySelectorAll("[data-dataset-summary]").forEach((element) => {
    element.textContent = `${formatNumber(data.overview.unique_songs)} unique songs (artist + title), ${formatNumber(data.overview.unique_releases)} song–artist–album combinations, ${formatNumber(data.overview.unique_artists)} artists, and ${formatNumber(data.overview.rows)} weekly chart rows. Coverage: ${data.overview.week_start} through ${data.overview.week_end}.`;
  });
  document.querySelectorAll("[data-dataset-window]").forEach((element) => {
    element.textContent = `${data.overview.week_start} – ${data.overview.week_end}`;
  });

  if (page === "home") {
    populateHome(data);
    if (window.initExploratoryPage) window.initExploratoryPage(data);
  }

  if (page === "music") {
    populateMusic(data);
  }

}

init().catch((error) => {
  console.error("Failed to initialize site data", error);
});
