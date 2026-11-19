/* HTML and the complete search index are built from data/audio_features.yaml.
   Chart links are rendered by build_methodology.py from x-chart-links. */
(() => {
  const input = document.getElementById('dictionary-query');
  const clear = document.getElementById('clear-search');
  const rows = [...document.querySelectorAll('[data-variable]')];
  const groups = [...document.querySelectorAll('.dictionary-group')];
  const frameNote = document.getElementById('frame-note');
  const normalize = value => value.normalize('NFKC').toLowerCase()
    .replace(/(\d),(?=\d{3}(?:\D|$))/g, '$1').replace(/[–—−]/g, '-').replace(/[_\s]+/g, ' ').trim();
  const index = rows.map(row => ({row, text: normalize(row.dataset.search)}));

  function filter() {
    const query = normalize(input.value);
    let visible = 0;
    index.forEach(item => {
      item.row.hidden = !item.text.includes(query);
      if (!item.row.hidden) visible++;
    });
    groups.forEach(group => {
      group.hidden = ![...group.querySelectorAll('[data-variable]')].some(row => !row.hidden);
    });
    frameNote.hidden = !groups.some(group => group.dataset.frame === 'true' && !group.hidden);
    document.getElementById('search-count').textContent = `${visible} of ${rows.length} variables`;
    document.getElementById('no-results').hidden = visible !== 0;
    clear.disabled = input.value.length === 0;
  }
  function reset() {
    input.value = '';
    filter();
  }
  input.addEventListener('input', filter);
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape') reset();
  });
  clear.addEventListener('click', () => {reset(); input.focus();});

  // A permalink or group jump always reveals its target, even after filtering.
  function revealHash() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = document.getElementById(id);
    if (target && (target.matches('[data-variable], .dictionary-group'))) {
      reset();
      target.scrollIntoView({block: 'start'});
    }
  }
  document.querySelector('.dictionary-outline').addEventListener('click', event => {
    if (event.target.closest('a')) reset();
  });
  window.addEventListener('hashchange', revealHash);
  document.querySelector('.dictionary-search').hidden = false;
  filter();
  if (location.hash) revealHash();
})();
