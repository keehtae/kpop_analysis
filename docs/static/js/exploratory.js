(function () {
  const COLORS = ["#111111", "#a67c52", "#6f675d", "#d0ab7a", "#8d8377", "#c9c0b3"];
  const chartRegistry = [];

  function registerChart(host) {
    const chart = echarts.getInstanceByDom(host) || echarts.init(host, null, { renderer: "svg" });
    if (!chartRegistry.includes(chart)) {
      chartRegistry.push(chart);
    }
    return chart;
  }

  function attachResize() {
    if (window.__kpopAtlasResizeBound) return;
    window.__kpopAtlasResizeBound = true;
    window.addEventListener("resize", () => {
      chartRegistry.forEach((chart) => chart.resize());
    });
  }

  function chartText(title, subtitle) {
    return {
      text: title,
      subtext: subtitle || "",
      left: 0,
      top: 0,
      textStyle: {
        fontFamily: "Baskerville, Iowan Old Style, Palatino Linotype, Times New Roman, serif",
        fontSize: 16,
        fontWeight: "bold",
        color: "#111111",
        overflow: "break",
        width: 320,
      },
      subtextStyle: {
        color: "#676158",
        fontFamily: "Avenir Next, Helvetica Neue, Segoe UI, sans-serif",
        fontSize: 11,
      },
    };
  }

  function gridBase(extra = {}) {
    return {
      left: 70,
      right: 28,
      top: 78,
      bottom: 48,
      containLabel: true,
      ...extra,
    };
  }

  function axisLabel() {
    return {
      color: "#676158",
      fontFamily: "Avenir Next, Helvetica Neue, Segoe UI, sans-serif",
      fontSize: 11,
    };
  }

  function splitLine() {
    return {
      show: true,
      lineStyle: {
        color: "#d6cdc0",
        type: "dashed",
      },
    };
  }

  function truncateLabel(value, maxLength = 28) {
    if (!value) return "";
    return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
  }

  function renderDistributionChart(data) {
    const host = document.querySelector("[data-echart='distribution']");
    if (!host) return;
    const chart = registerChart(host);
    const stats = document.querySelector("[data-distribution-stats]");
    if (stats) stats.textContent = `Mean: ${data.mean} weeks · Median: ${data.median} weeks · Standard deviation: ${data.std_dev} weeks`;
    chart.setOption({
      backgroundColor: "transparent",
      animationDuration: 700,
      title: chartText("Distribution of Total Chart Weeks per Song"),
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(17,17,17,0.94)",
        borderWidth: 0,
        textStyle: { color: "#ffffff" },
        formatter: (params) => {
          const bin = data.bars[params[0].dataIndex];
          return `<strong>${bin.start}–${bin.end} weeks</strong><br>${bin.count.toLocaleString()} songs`;
        },
      },
      grid: gridBase({ left: 20, right: 18, top: 82, bottom: 62 }),
      xAxis: {
        type: "category",
        data: data.bars.map((bin) => `${bin.start}–${bin.end}`),
        name: "Total Weeks on Chart (25-week bins)",
        nameLocation: "middle",
        nameGap: 42,
        axisLabel: { ...axisLabel(), fontSize: 12, rotate: 45, hideOverlap: true },
        axisTick: { alignWithLabel: true },
        axisLine: { lineStyle: { color: "#b7aea2" } },
      },
      yAxis: {
        type: "value",
        name: "Count",
        minInterval: 1,
        axisLabel: { ...axisLabel(), fontSize: 12 },
        splitLine: splitLine(),
      },
      series: [{
        name: "Songs",
        type: "bar",
        barCategoryGap: "4%",
        itemStyle: { color: "#a67c52" },
        label: { show: false },
        data: data.bars.map((bin) => bin.count),
      }],
    });
  }

  function renderHorizontalBar(hostSelector, title, subtitle, labels, values, color, options = {}) {
    const host = document.querySelector(hostSelector);
    if (!host) return;
    const {
      minHeight = 520,
      labelWidth = 140,
      labelLength = 24,
      gridLeft = 160,
      gridRight = 40,
      splitNumber = 5,
      barWidth = 22,
      topOffset = 72,
      axisMaxPad = 1.12,
      compact = false,
    } = options;
    host.style.height = `${Math.max(minHeight, 92 + labels.length * 34)}px`;
    const chart = registerChart(host);
    const labelValuePairs = labels
      .map((label, index) => ({ label, value: values[index] }))
      .sort((left, right) => right.value - left.value);
    const maxValue = Math.max(...labelValuePairs.map((item) => item.value), 0);
    chart.setOption({
      backgroundColor: "transparent",
      animationDuration: 700,
      title: compact ? { ...chartText(title, subtitle), textStyle: { ...chartText(title).textStyle, width: 240, fontSize: 15 } } : chartText(title, subtitle),
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(17,17,17,0.94)",
        borderWidth: 0,
        textStyle: { color: "#ffffff" },
        formatter: (params) => {
          const item = params[0];
          return `<strong>${item.name}</strong><br>${item.value}`;
        },
      },
      grid: gridBase({ left: gridLeft, right: gridRight, top: topOffset, bottom: 28 }),
      xAxis: {
        type: "value",
        max: maxValue ? Math.ceil(maxValue * axisMaxPad) : null,
        splitNumber,
        minInterval: 1,
        axisLabel: axisLabel(),
        splitLine: splitLine(),
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: labelValuePairs.map((item) => item.label),
        axisLabel: {
          ...axisLabel(),
          width: labelWidth,
          overflow: "truncate",
          formatter: (value) => truncateLabel(value, labelLength),
        },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [
        {
          type: "bar",
          data: labelValuePairs.map((item) => item.value),
          barWidth,
          barCategoryGap: "28%",
          itemStyle: {
            color,
            borderRadius: [0, 10, 10, 0],
          },
          label: {
            show: true,
            position: "right",
            color: "#111111",
            fontFamily: "Avenir Next, Helvetica Neue, Segoe UI, sans-serif",
            fontSize: 11,
          },
        },
      ],
    });
  }

  function renderAgencyBars(data) {
    renderHorizontalBar(
      "[data-echart='agency-production']",
      "Top Production Agencies",
      "Unique charting songs",
      data.production.map((item) => item.production_agency),
      data.production.map((item) => item.unique_song_count),
      "#a67c52",
      {
        minHeight: 450,
        labelWidth: 95,
        labelLength: 16,
        gridLeft: 4,
        gridRight: 25,
        splitNumber: 3,
        barWidth: 18,
        compact: true,
      },
    );
    const host = document.querySelector("[data-echart='agency-distribution']");
    if (!host) return;
    const agencies = [...data.distribution].sort((a, b) => b.unique_song_count - a.unique_song_count);
    const chart = registerChart(host);
    chart.setOption({
      backgroundColor: "transparent",
      animationDuration: 700,
      title: chartText("Top Distribution Agencies", "Unique charting songs"),
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(17,17,17,0.94)",
        borderWidth: 0,
        textStyle: { color: "#ffffff" },
        formatter: (params) => `${params.name}<br>${params.value.toLocaleString()} songs`,
      },
      grid: gridBase({ left: 12, right: 18, top: 82, bottom: 22 }),
      xAxis: {
        type: "category",
        data: agencies.map((item) => item.distribution_agency),
        axisLabel: { ...axisLabel(), fontSize: 12, interval: 0, rotate: 45 },
        axisTick: { alignWithLabel: true },
        axisLine: { lineStyle: { color: "#b7aea2" } },
      },
      yAxis: {
        type: "value",
        name: "Count",
        minInterval: 1,
        axisLabel: axisLabel(),
        splitLine: splitLine(),
      },
      series: [{
        name: "Songs",
        type: "bar",
        barCategoryGap: "25%",
        itemStyle: { color: "#111111", borderRadius: [4, 4, 0, 0] },
        label: { show: false },
        data: agencies.map((item) => item.unique_song_count),
      }],
    });
  }


  function renderDistributionGroups(data) {
    const host = document.querySelector("[data-echart='distribution-big-four']");
    if (!host) return;
    const groups = [...data.groups].sort((a, b) => b.unique_song_count - a.unique_song_count);
    registerChart(host).setOption({
      title: chartText("Big 4 Distribution", "Unique songs by distributor / alliance"),
      tooltip: { trigger: "item", formatter: (item) => `${item.name}<br>${item.value.toLocaleString()} songs` },
      grid: gridBase({ left: 12, right: 18, top: 82, bottom: 24 }),
      xAxis: { type: "category", data: groups.map((g) => g.group),
        axisLabel: { ...axisLabel(), fontSize: 12, interval: 0,
          formatter: (name) => name === "Kakao Entertainment" ? "Kakao\nEntertainment" : name === "CJ ENM Alliance" ? "CJ ENM Alliance\n(Genie + Stone)" : name },
        axisTick: { alignWithLabel: true } },
      yAxis: { type: "value", name: "Count", minInterval: 1, axisLabel: axisLabel(), splitLine: splitLine() },
      series: [{ type: "bar", data: groups.map((g) => g.unique_song_count),
        barCategoryGap: "30%", itemStyle: { color: "#a67c52" }, label: { show: false } }],
    });
    const detail = document.querySelector("[data-distribution-group-breakdown]");
    if (!detail) return;
    const paragraphs = groups.map((group) => {
      const p = document.createElement("p");
      p.textContent = `${group.group}: ${group.unique_song_count} unique songs. Credits: ${group.credits.map((c) => `${c.credit} (${c.unique_song_count})`).join("; ")}.`;
      return p;
    });
    const excluded = document.createElement("p");
    excluded.textContent = `Excluded credits: ${data.excluded_credits.map((c) => `${c.credit} (${c.unique_song_count})`).join("; ")}. Across all groups: ${data.included_unique_songs} distinct songs included; ${data.excluded_only_unique_songs} songs have only excluded credits. Group totals can overlap and are not market shares.`;
    detail.replaceChildren(...paragraphs, excluded, ...data.agreement_review.map((review) => {
      const p = document.createElement("p");
      p.textContent = `${review.topic}: ${review.decision} `;
      const link = document.createElement("a");
      link.href = review.url; link.textContent = "Source";
      p.append(link); return p;
    }));
  }

  function renderArtistExplorer(data) {
    const root = document.querySelector("[data-artist-explorer]");
    if (!root) return;

    const controls = root.querySelector("[data-controls]");
    const list = root.querySelector("[data-list]");
    const detailHost = root.querySelector("[data-detail]");
    const chartHost = root.querySelector("[data-chart]");
    const chart = registerChart(chartHost);

    const state = {
      year: String(data.years.at(-1)),
      artists: [data.artists.find((artist) => artist === "CORTIS (코르티스)") || data.artists[0]],
    };

    function artistOptions(selected) {
      return data.artists.map((artist) => `<option value="${artist}" ${artist === selected ? "selected" : ""}>${artist}</option>`).join("");
    }

    function updateDetail(payload) {
      detailHost.innerHTML = payload ? `
        <div class="mini-title">${payload.artist} · Week ${payload.week}</div>
        <div class="mini-meta">Mean rank ${payload.mean_rank}</div>
        <div class="mini-list">
          ${payload.songs.slice(0, 6).map((song) => `
            <div class="mini-item">
              <div class="mini-title">#${song.rank} ${song.song_title}</div>
              <div class="mini-meta">${song.album}</div>
            </div>
          `).join("")}
        </div>
      ` : `
        <div class="mini-title">Hover a point</div>
        <div class="mini-meta">The detail panel updates with the songs charting for that artist on the selected week.</div>
      `;
    }

    function draw() {
      controls.innerHTML = `
        <label class="metric-label">Year</label>
        <select data-year-select>${data.years.map((year) => `<option value="${year}" ${String(year) === state.year ? "selected" : ""}>${year}</option>`).join("")}</select>
        <button type="button" data-add-artist>Add Artist</button>
      `;

      list.innerHTML = state.artists.map((artist, index) => `
        <div class="explorer-row">
          <span class="pill">Line ${index + 1}</span>
          <select data-artist-index="${index}">${artistOptions(artist)}</select>
          <button type="button" data-remove-artist="${index}">Remove</button>
        </div>
      `).join("");

      const series = state.artists.map((artist, index) => ({
        name: artist,
        type: "line",
        showSymbol: true,
        symbolSize: 7,
        smooth: true,
        lineStyle: { width: 3, color: COLORS[index % COLORS.length] },
        itemStyle: { color: COLORS[index % COLORS.length] },
        data: (data.artist_year_map[artist]?.[state.year] || []).map((point) => ({
          value: [point.week, point.mean_rank],
          artist,
          week: point.week,
          mean_rank: point.mean_rank,
          songs: point.songs,
        })),
      })).filter((entry) => entry.data.length > 0);

      chart.off("mouseover");
      chart.setOption({
        backgroundColor: "transparent",
        animationDuration: 500,
        title: chartText("Artist Mean-Rank Explorer", "Select a year and compare weekly mean rank across artists"),
        tooltip: {
          trigger: "item",
          backgroundColor: "rgba(17,17,17,0.94)",
          borderWidth: 0,
          textStyle: { color: "#ffffff" },
          formatter: (params) => {
            const songLines = params.data.songs.slice(0, 4).map((song) => `#${song.rank} ${song.song_title}`).join("<br>");
            return `<strong>${params.seriesName}</strong><br>Week ${params.data.week}<br>Mean rank ${params.data.mean_rank}<br>${songLines}`;
          },
        },
        legend: {
          bottom: 0,
          textStyle: { color: "#676158" },
        },
        grid: gridBase({ bottom: 72 }),
        xAxis: {
          type: "value",
          min: 1,
          max: 53,
          axisLabel: { ...axisLabel(), formatter: "W{value}" },
          splitLine: splitLine(),
        },
        yAxis: {
          type: "value",
          min: 1,
          max: 200,
          inverse: true,
          axisLabel: axisLabel(),
          splitLine: splitLine(),
        },
        series,
      });

      updateDetail(null);
      chart.on("mouseover", (params) => {
        if (params?.data?.songs) updateDetail(params.data);
      });

      root.querySelector("[data-year-select]").addEventListener("change", (event) => {
        state.year = event.target.value;
        draw();
      });

      root.querySelector("[data-add-artist]").addEventListener("click", () => {
        if (state.artists.length >= 4) return;
        const next = data.artists.find((artist) => !state.artists.includes(artist));
        if (next) {
          state.artists.push(next);
          draw();
        }
      });

      list.querySelectorAll("select[data-artist-index]").forEach((select) => {
        select.addEventListener("change", (event) => {
          state.artists[Number(event.target.dataset.artistIndex)] = event.target.value;
          draw();
        });
      });

      list.querySelectorAll("button[data-remove-artist]").forEach((button) => {
        button.addEventListener("click", (event) => {
          state.artists.splice(Number(event.target.dataset.removeArtist), 1);
          if (!state.artists.length) state.artists.push(data.artists[0]);
          draw();
        });
      });
    }

    draw();
  }

  function renderSongExplorer(data) {
    const root = document.querySelector("[data-song-explorer]");
    if (!root) return;

    const toolbar = root.querySelector("[data-toolbar]");
    const list = root.querySelector("[data-song-list]");
    const chartHost = root.querySelector("[data-song-chart]");
    const chart = registerChart(chartHost);

    const defaultArtist = data.artists.includes("방탄소년단") ? "방탄소년단" : data.artists[0];
    const defaultSongs = data.artist_to_songs[defaultArtist];
    const state = {
      selections: [{ artist: defaultArtist, song: defaultSongs.includes("봄날") ? "봄날" : defaultSongs[0] }],
    };

    function songOptions(artist, selected) {
      return (data.artist_to_songs[artist] || []).map((song) => `<option value="${song}" ${song === selected ? "selected" : ""}>${song}</option>`).join("");
    }

    function draw() {
      toolbar.innerHTML = `<button type="button" data-add-song>Add Song</button>`;
      list.innerHTML = state.selections.map((selection, index) => `
        <div class="explorer-row">
          <select data-song-artist="${index}">
            ${data.artists.map((artist) => `<option value="${artist}" ${artist === selection.artist ? "selected" : ""}>${artist}</option>`).join("")}
          </select>
          <select data-song-title="${index}">
            ${songOptions(selection.artist, selection.song)}
          </select>
          <button type="button" data-remove-song="${index}">Remove</button>
        </div>
      `).join("");

      const series = state.selections.map((selection, index) => {
        const key = `${selection.artist}|||${selection.song}`;
        return {
          name: `${selection.artist} - ${selection.song}`,
          type: "line",
          showSymbol: true,
          symbolSize: 6,
          smooth: false,
          lineStyle: { width: 3, color: COLORS[index % COLORS.length] },
          itemStyle: { color: COLORS[index % COLORS.length] },
          data: (data.series_map[key] || []).map((point) => ({
            value: [point.date, point.rank],
            week_label: point.week_label,
            rank: point.rank,
          })),
        };
      }).filter((entry) => entry.data.length > 0);

      chart.setOption({
        backgroundColor: "transparent",
        animationDuration: 500,
        title: chartText("Song Rank History Explorer", "Compare selected tracks across the full chart timeline"),
        tooltip: {
          trigger: "item",
          backgroundColor: "rgba(17,17,17,0.94)",
          borderWidth: 0,
          textStyle: { color: "#ffffff" },
          formatter: (params) => `<strong>${params.seriesName}</strong><br>${params.data.week_label}<br>Rank #${params.data.rank}`,
        },
        legend: {
          bottom: 0,
          textStyle: { color: "#676158" },
        },
        grid: gridBase({ bottom: 72 }),
        xAxis: {
          type: "time",
          axisLabel: {
            ...axisLabel(),
            formatter: (value) => {
              const date = new Date(value);
              return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, "0")}`;
            },
          },
          splitLine: splitLine(),
        },
        yAxis: {
          type: "value",
          min: 1,
          max: 200,
          inverse: true,
          axisLabel: axisLabel(),
          splitLine: splitLine(),
        },
        series,
      });

      toolbar.querySelector("[data-add-song]").addEventListener("click", () => {
        if (state.selections.length >= 4) return;
        const artist = data.artists[0];
        state.selections.push({ artist, song: data.artist_to_songs[artist][0] });
        draw();
      });

      list.querySelectorAll("select[data-song-artist]").forEach((select) => {
        select.addEventListener("change", (event) => {
          const index = Number(event.target.dataset.songArtist);
          const artist = event.target.value;
          state.selections[index] = { artist, song: data.artist_to_songs[artist][0] };
          draw();
        });
      });

      list.querySelectorAll("select[data-song-title]").forEach((select) => {
        select.addEventListener("change", (event) => {
          state.selections[Number(event.target.dataset.songTitle)].song = event.target.value;
          draw();
        });
      });

      list.querySelectorAll("button[data-remove-song]").forEach((button) => {
        button.addEventListener("click", (event) => {
          state.selections.splice(Number(event.target.dataset.removeSong), 1);
          if (!state.selections.length) {
            const artist = data.artists[0];
            state.selections.push({ artist, song: data.artist_to_songs[artist][0] });
          }
          draw();
        });
      });
    }

    draw();
  }

  function renderMovementTables(data) {
    const root = document.querySelector("[data-movement-tables]");
    if (!root) return;

    const toggleHost = root.querySelector("[data-table-toggle]");
    const tableHost = root.querySelector("[data-table-panels]");
    const state = { mode: "overall", year: String(data.years.at(-1)) };
    const columns = ["year", "week", "artist", "song_title", "prev_rank", "rank"];
    const headings = ["Year", "Week", "Artist", "Song", "Previous rank", "Rank", "Change"];
    const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[char]));

    function renderTable(name, rows) {
      const title = name === "climbs" ? "Climbs" : "Drops";
      const fields = [...columns, name === "climbs" ? "rank_change" : "drop_size"];
      return `
        <section class="table-panel">
          <h3 class="metric-label">${title}</h3>
          <div class="table-scroll table-scroll-medium" tabindex="0" role="region" aria-label="${title}, top ${rows.length} results">
            <table class="data-table movement-table" aria-label="${title} — ${state.mode === "overall" ? "Overall" : state.year}">
              <colgroup><col class="movement-year"><col class="movement-week"><col><col><col class="movement-rank"><col class="movement-rank"><col class="movement-rank"></colgroup>
              <thead><tr>${headings.map((heading) => `<th scope="col">${heading}</th>`).join("")}</tr></thead>
              <tbody>
                ${rows.slice(0, 50).map((row) => `<tr>${fields.map((field) => `<td>${escape(row[field])}</td>`).join("")}</tr>`).join("") || '<tr><td colspan="7">No movements for this year.</td></tr>'}
              </tbody>
            </table>
          </div>
        </section>
      `;
    }

    function drawTables() {
      const bundle = state.mode === "overall" ? data.overall : data.yearly[state.year];
      tableHost.innerHTML = renderTable("climbs", bundle.climbs) + renderTable("drops", bundle.drops);
    }

    function draw() {
      toggleHost.innerHTML = ["overall", "yearly"].map((mode) => `
        <button type="button" class="${state.mode === mode ? "active" : ""}" aria-pressed="${state.mode === mode}" data-mode="${mode}">${mode === "overall" ? "Overall" : "By Year"}</button>
      `).join("") + (state.mode === "yearly" ? `
        <label for="movement-year">Year</label>
        <select id="movement-year">${[...data.years].reverse().map((year) => `<option value="${year}" ${String(year) === state.year ? "selected" : ""}>${year}</option>`).join("")}</select>
      ` : "");
      drawTables();
      toggleHost.querySelectorAll("button[data-mode]").forEach((button) => {
        button.addEventListener("click", () => {
          state.mode = button.dataset.mode;
          draw();
        });
      });
      toggleHost.querySelector("select")?.addEventListener("change", (event) => {
        state.year = event.target.value;
        drawTables();
      });
    }

    draw();
  }

  window.initExploratoryPage = function initExploratoryPage(siteData) {
    attachResize();

    renderDistributionChart(siteData.charts.distribution);
    renderHorizontalBar(
      "[data-echart='top-total-weeks']",
      "Top 10 Songs with the Most Total Weeks on the Chart",
      "Song longevity leaders",
      siteData.charts.top_total_weeks.labels,
      siteData.charts.top_total_weeks.values,
      "#a67c52",
    );
    renderHorizontalBar(
      "[data-echart='weeks-at-number-one']",
      "Top 10 Songs with the Most Weeks at Rank #1",
      "Peak hold leaders",
      siteData.charts.weeks_at_number_one.labels,
      siteData.charts.weeks_at_number_one.values,
      "#111111",
      { gridLeft: 4, gridRight: 24, labelWidth: 140, labelLength: 24, axisMaxPad: 1.05 },
    );
    renderAgencyBars(siteData.charts.agency_bars);
    renderDistributionGroups(siteData.distribution_big_four);
    const groups = siteData.big_four.groups;
    renderHorizontalBar("[data-echart='big-four']", "Big 4", "Unique songs by parent group",
      groups.map((item) => item.group), groups.map((item) => item.unique_song_count), "#111111",
      { minHeight: 450, labelWidth: 42, gridLeft: 4, gridRight: 25, barWidth: 26, splitNumber: 3, compact: true });
    const breakdown = document.querySelector("[data-big-four-breakdown]");
    if (breakdown) {
      breakdown.replaceChildren(...groups.map((group) => {
        const paragraph = document.createElement("p");
        paragraph.textContent = `${group.group}: ${group.unique_song_count} unique songs — ${group.labels.map((item) => `${item.label}: ${item.unique_song_count}`).join("; ")}. Label sum: ${group.label_count_sum}; overlaps removed: ${group.label_count_sum - group.unique_song_count}.`;
        return paragraph;
      }));
    }
    renderArtistExplorer(siteData.explorers.artist_mean_rank);
    renderSongExplorer(siteData.explorers.song_rank_history);
    renderMovementTables(siteData.movement_tables);
  };
})();
