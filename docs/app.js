"use strict";

const $ = (selector) => document.querySelector(selector);
const datasets = {};
const pageSize = 25;
let currentPage = 0;
let filtered = [];
let manifest;
const labels = {year:"Year",time:"Week",rank:"Rank",song_title:"Song",song:"Song",artist:"Artist",album:"Album",score:"Chart score",production:"Production",distribution:"Distribution",tempo_bpm:"Tempo (BPM)",duration_sec:"Duration (seconds)"};
const label = (column) => labels[column] || column.replaceAll("_", " ");
const isWeek = (column) => /^\d{2}_\d{2}$/.test(column);

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("The datasets could not be loaded. Please try again later.");
  return response.json();
}

async function loadDataset(name) {
  if (!datasets[name]) {
    const entry = manifest.tables.find((table) => table.table === `gold.${name}`);
    if (!entry) throw new Error("This dataset is not available.");
    datasets[name] = await fetchJson(`./data/${entry.file}`);
  }
  return datasets[name];
}

function updateMeasures() {
  const isAudio = $("#dataset").value === "essentia_and_rankings";
  $("#measure-control").hidden = !isAudio;
  if (!isAudio) return;
  const data = datasets.essentia_and_rankings;
  const previous = $("#measure").value;
  $("#measure").replaceChildren();
  for (const column of data.columns.filter((column) => !["song", "artist", "album"].includes(column))) {
    const option = document.createElement("option");
    option.value = column;
    option.textContent = isWeek(column) ? `Chart score: ${column.replace("_", " week ")}` : label(column);
    $("#measure").append(option);
  }
  $("#measure").value = data.columns.includes(previous) ? previous : (data.columns.includes("tempo_bpm") ? "tempo_bpm" : $("#measure").options[0]?.value || "");
}

function filterRows() {
  const data = datasets[$("#dataset").value];
  const searchable = ["song_title", "song", "artist", "album"].map((column) => data.columns.indexOf(column)).filter((index) => index >= 0);
  const query = $("#search").value.trim().toLocaleLowerCase();
  filtered = data.rows.filter((row) => !query || searchable.some((index) => String(row[index] ?? "").toLocaleLowerCase().includes(query)));
  currentPage = 0;
  render();
}

function formatValue(value) {
  if (value === null || value === undefined) return "—";
  return typeof value === "number" ? value.toLocaleString(undefined, {maximumFractionDigits:4}) : String(value);
}

function render() {
  const name = $("#dataset").value;
  const data = datasets[name];
  const columns = name === "rankings" ? data.columns : ["song", "artist", "album", $("#measure").value].filter((column) => data.columns.includes(column));
  const header = document.createElement("tr");
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = isWeek(column) ? `Score: ${column}` : label(column);
    header.append(cell);
  }
  $("#results thead").replaceChildren(header);
  const body = document.createDocumentFragment();
  for (const row of filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize)) {
    const line = document.createElement("tr");
    for (const column of columns) {
      const cell = document.createElement("td");
      cell.textContent = formatValue(row[data.columns.indexOf(column)]);
      line.append(cell);
    }
    body.append(line);
  }
  $("#results tbody").replaceChildren(body);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  $("#status").textContent = `${filtered.length.toLocaleString()} of ${data.rows.length.toLocaleString()} rows${filtered.length === 0 ? ". Try another search." : ""}`;
  $("#page").textContent = `Page ${currentPage + 1} of ${pageCount}`;
  $("#previous").disabled = currentPage === 0;
  $("#next").disabled = currentPage + 1 >= pageCount;
  $("#download").href = `./data/${name}.json`;
}

$("#dataset").addEventListener("change", async () => {
  $("#status").textContent = "Loading dataset…";
  try { await loadDataset($("#dataset").value); updateMeasures(); filterRows(); }
  catch (error) { $("#status").textContent = error.message; }
});
$("#search").addEventListener("input", () => { if (datasets[$("#dataset").value]) filterRows(); });
$("#measure").addEventListener("change", render);
$("#previous").addEventListener("click", () => { currentPage--; render(); });
$("#next").addEventListener("click", () => { currentPage++; render(); });

async function initialize() {
  try {
    manifest = await fetchJson("./data/manifest.json");
    const [rankings, audio] = await Promise.all([loadDataset("rankings"), loadDataset("essentia_and_rankings")]);
    const sortColumns = ["year", "time", "rank"].map((column) => rankings.columns.indexOf(column));
    rankings.rows.sort((left, right) => {
      for (const index of sortColumns) {
        if (index < 0) continue;
        const difference = Number(left[index]) - Number(right[index]);
        if (difference) return difference;
      }
      return 0;
    });
    $("#ranking-count").textContent = rankings.rows.length.toLocaleString();
    $("#song-count").textContent = audio.rows.length.toLocaleString();
    const year = rankings.columns.indexOf("year");
    const week = rankings.columns.indexOf("time");
    $("#week-count").textContent = new Set(rankings.rows.map((row) => `${row[year]}_${row[week]}`)).size.toLocaleString();
    filterRows();
  } catch (error) { $("#status").textContent = error.message; }
}
initialize();
