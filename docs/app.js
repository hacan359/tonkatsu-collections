// Tonkatsu Collections — site logic.
//
// Two views, hash-routed:
//   #/                   home: filter + grid of collections
//   #/c/<collection-id>  detail: full game list with covers, per-collection
//                        search + genre filter
//
// Loads index.json from raw.githubusercontent.com (same source as the app),
// lazy-loads individual .xcollx files when a collection is opened.

const REPO_BASE = 'https://raw.githubusercontent.com/hacan359/tonkatsu-collections/main';
const REPO_BLOB = 'https://github.com/hacan359/tonkatsu-collections/blob/main';
// Tried in order: local copy (committed alongside the site so GitHub Pages
// can serve it) -> raw repo URL (fallback for local dev when the copy is
// stale, e.g. during development).
const INDEX_URLS = ['data/index.json', REPO_BASE + '/index.json'];

const LOGO_MAP = {
  '3do': '3do_50.png',
  'atari-2600': 'atari2600_59.png',
  'atari-7800': 'atari7800_60.png',
  'atari-jaguar': 'jaguar_62.png',
  'dreamcast': 'dreamcast_23.png',
  'gb': 'gameboy_33.png',
  'gba': 'gba_24.png',
  'gbc': 'gbc_22.png',
  'gamecube': 'gamecube_21.png',
  'game-gear': 'gamegear_35.png',
  'genesis': 'genesis_29.png',
  'master-system': 'master-system_64.png',
  'n64': 'n64_4.png',
  'neo-geo': 'neogeo_80.png',
  'nes': 'nes_18.png',
  'pc': 'pc_6.png',
  'ps1': 'ps1_7.png',
  'ps2': 'ps2_8.png',
  'ps3': 'ps3_9.png',
  'ps4': 'ps4_48.png',
  'ps5': 'ps5_167.png',
  'psp': 'psp_38.png',
  'saturn': 'saturn_32.png',
  'sega-32x': 'sega32x_30.png',
  'sega-cd': 'segacd_78.png',
  'snes': 'snes_19.png',
  'switch': 'switch_130.png',
  'turbografx': 'turbografx_86.png',
  'wii': 'wii_5.png',
  'xbox': 'xbox_11.png',
  'xbox-360': 'xbox360_12.png',
  'xbox-one': 'xboxone_49.png',
};
const MEDIA_ICON = { 'movies': '🎬', 'tv-shows': '📺', 'animation': '✨' };
const CATEGORY_LABEL = {
  'complete': 'Complete',
  'curated': 'Curated',
  'hidden-gems': 'Hidden Gems',
  'exclusives': 'Exclusives',
};

const state = {
  index: null,
  collections: [],
  query: '',
  platform: null,
  category: null,
  sort: 'platform',
  // detail view
  detail: null,       // collection object
  detailData: null,   // parsed .xcollx
  detailQuery: '',
  detailGenre: null,
};

const xcollxCache = new Map();   // file -> parsed JSON

// ---------- bootstrap ----------

(async function init() {
  try {
    state.index = await loadIndex();
  } catch (e) {
    showLoadError(e);
    return;
  }
  state.collections = state.index.collections || [];
  for (const c of state.collections) {
    if (/(^|\/)exclusives\.(xcoll|xcollx)$/i.test(c.file || '')) {
      c.category = 'exclusives';
    }
  }
  renderStats();
  renderPlatformMenu();
  renderCategoryMenu();
  attachUiListeners();
  window.addEventListener('hashchange', route);
  route();
})();

async function loadIndex() {
  let lastErr;
  for (const url of INDEX_URLS) {
    try {
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error('No index source reachable');
}

function showLoadError(e) {
  const el = document.getElementById('cards');
  el.innerHTML = `<div class="empty">Failed to load index: ${escapeHtml(e.message)}</div>`;
}

// ---------- routing ----------

function route() {
  const hash = window.location.hash || '';
  const m = hash.match(/^#\/c\/([\w-]+)$/);
  if (m) {
    const id = m[1];
    const c = state.collections.find(x => x.id === id);
    if (c) {
      openDetail(c);
      return;
    }
  }
  closeDetail();
}

// ---------- home rendering ----------

function renderStats() {
  const cs = state.collections;
  const total = cs.length;
  const games = cs
    .filter(c => c.mediaType === 'game')
    .reduce((s, c) => s + (c.itemsCount || 0), 0);
  const exclusives = cs
    .filter(c => c.category === 'exclusives')
    .reduce((s, c) => s + (c.itemsCount || 0), 0);
  const platforms = new Set(
    cs.filter(c => c.platform).map(c => c.platform),
  ).size;
  setStat('collections', total);
  setStat('games', games);
  setStat('exclusives', exclusives);
  setStat('platforms', platforms);
}

function setStat(name, value) {
  const el = document.querySelector(`[data-stat="${name}"]`);
  if (el) el.textContent = value.toLocaleString();
}

function renderPlatformMenu() {
  const menu = document.querySelector('[data-menu="platform"]');
  const items = [{ id: null, label: 'All platforms' }];
  for (const p of state.index.platforms || []) {
    items.push({ id: p.id, label: p.name });
  }
  for (const m of state.index.mediaTypes || []) {
    items.push({ id: m.id, label: m.name });
  }
  const counts = countBy(state.collections, c => c.platform || c.mediaType);
  menu.innerHTML = items.map(it => {
    const count = it.id ? counts.get(it.id) || 0 : state.collections.length;
    const sel = state.platform === it.id ? ' selected' : '';
    return `<div class="opt${sel}" data-pick="${it.id ?? ''}">
        <span>${escapeHtml(it.label)}</span><span class="count">${count}</span>
      </div>`;
  }).join('');
  menu.onclick = ev => {
    const opt = ev.target.closest('.opt');
    if (!opt) return;
    state.platform = opt.dataset.pick || null;
    document.getElementById('platform-dropdown').removeAttribute('open');
    updateDropdownLabel('platform-dropdown',
      state.platform
        ? items.find(i => i.id === state.platform)?.label
        : 'All platforms');
    renderPlatformMenu();
    renderHome();
  };
}

function renderCategoryMenu() {
  const menu = document.querySelector('[data-menu="category"]');
  const counts = countBy(state.collections, c => c.category);
  const ids = [...counts.keys()].filter(Boolean).sort();
  const items = [{ id: null, label: 'All categories' },
    ...ids.map(id => ({ id, label: CATEGORY_LABEL[id] || id }))];
  menu.innerHTML = items.map(it => {
    const count = it.id ? counts.get(it.id) : state.collections.length;
    const sel = state.category === it.id ? ' selected' : '';
    return `<div class="opt${sel}" data-pick="${it.id ?? ''}">
        <span>${escapeHtml(it.label)}</span><span class="count">${count}</span>
      </div>`;
  }).join('');
  menu.onclick = ev => {
    const opt = ev.target.closest('.opt');
    if (!opt) return;
    state.category = opt.dataset.pick || null;
    document.getElementById('category-dropdown').removeAttribute('open');
    updateDropdownLabel('category-dropdown',
      state.category
        ? CATEGORY_LABEL[state.category] || state.category
        : 'All categories');
    renderCategoryMenu();
    renderHome();
  };
}

function updateDropdownLabel(id, text) {
  document.querySelector(`#${id} .label`).textContent = text;
}

function renderHome() {
  const filtered = applyFilters(state.collections);
  const sorted = applySort(filtered);
  const cards = document.getElementById('cards');
  const empty = document.getElementById('empty');
  document.getElementById('result-count').textContent =
    sorted.length === state.collections.length
      ? `${sorted.length} collections`
      : `${sorted.length} of ${state.collections.length} collections`;
  if (sorted.length === 0) {
    cards.innerHTML = '';
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  cards.innerHTML = sorted.map(cardHtml).join('');
  cards.querySelectorAll('.card').forEach((el, i) => {
    el.addEventListener('click', ev => {
      if (ev.target.closest('a')) return;
      window.location.hash = `#/c/${sorted[i].id}`;
    });
  });
}

function applyFilters(list) {
  const q = state.query.toLowerCase();
  return list.filter(c => {
    if (state.platform && c.platform !== state.platform && c.mediaType !== state.platform) return false;
    if (state.category && c.category !== state.category) return false;
    if (q) {
      const hay = [c.name, c.description, c.platformName, c.author]
        .filter(Boolean).join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function applySort(list) {
  const a = [...list];
  switch (state.sort) {
    case 'items-desc': a.sort((x, y) => (y.itemsCount || 0) - (x.itemsCount || 0)); break;
    case 'items-asc': a.sort((x, y) => (x.itemsCount || 0) - (y.itemsCount || 0)); break;
    case 'name': a.sort((x, y) => x.name.localeCompare(y.name)); break;
    case 'platform':
    default:
      a.sort((x, y) => {
        const k1 = (x.platformName || x.mediaType || '').localeCompare(y.platformName || y.mediaType || '');
        if (k1 !== 0) return k1;
        return (x.category || '').localeCompare(y.category || '');
      });
  }
  return a;
}

function cardHtml(c) {
  const logo = logoFor(c);
  const items = (c.itemsCount || 0).toLocaleString();
  const size = formatBytes(c.size);
  const sub = [c.platformName, `${items} items`, size, c.format === 'full' ? 'Full' : 'Light']
    .filter(Boolean);
  return `<article class="card" data-id="${escapeHtml(c.id)}">
    <div class="card-head">
      <div class="card-logo${logo.placeholder ? ' placeholder' : ''}">${logo.html}</div>
      <div style="flex:1;min-width:0">
        <h3 class="card-title">${escapeHtml(c.name)}</h3>
        <div class="card-meta">${sub.map(escapeHtml).join('<span class="sep">·</span>')}</div>
      </div>
    </div>
    <div class="card-tags">
      <span class="tag ${c.category || 'curated'}">${escapeHtml(CATEGORY_LABEL[c.category] || c.category || 'curated')}</span>
      <span class="tag format-${c.format}">${c.format === 'full' ? 'with metadata' : 'IDs only'}</span>
    </div>
    <div class="card-actions">
      <a class="btn primary small" href="${REPO_BASE}/${encodeURI(c.file)}" download onclick="event.stopPropagation()">Download</a>
      <a class="btn secondary small" href="#/c/${encodeURIComponent(c.id)}">Open</a>
    </div>
  </article>`;
}

function logoFor(c) {
  const slug = c.platform || c.mediaType;
  if (slug && LOGO_MAP[slug]) {
    // Local path first (works when site served from repo root for dev, and
    // on GitHub Pages once logos are pushed). onerror falls back to raw URL
    // — useful for previewing newly added logos before they're on the remote.
    const local = `../logos/${LOGO_MAP[slug]}`;
    const remote = `${REPO_BASE}/logos/${LOGO_MAP[slug]}`;
    return {
      html: `<img src="${local}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${remote}'">`,
      placeholder: false,
    };
  }
  if (slug && MEDIA_ICON[slug]) {
    return { html: MEDIA_ICON[slug], placeholder: true };
  }
  return { html: '🎮', placeholder: true };
}

// ---------- detail view ----------

async function openDetail(c) {
  state.detail = c;
  state.detailData = null;
  state.detailQuery = '';
  state.detailGenre = null;

  document.getElementById('home-view').hidden = true;
  document.getElementById('detail-view').hidden = false;
  window.scrollTo({ top: 0, behavior: 'instant' });

  document.title = `${c.name} — Tonkatsu Collections`;
  document.getElementById('detail-title').textContent = c.name;
  document.getElementById('detail-desc').textContent = c.description || '';
  document.getElementById('detail-meta').textContent = [
    c.platformName,
    `${(c.itemsCount || 0).toLocaleString()} items`,
    formatBytes(c.size),
    c.format === 'full' ? 'Full export' : 'Light export',
    CATEGORY_LABEL[c.category] || c.category,
  ].filter(Boolean).join(' · ');
  document.getElementById('detail-download').href = `${REPO_BASE}/${encodeURI(c.file)}`;
  document.getElementById('detail-raw').href = `${REPO_BLOB}/${encodeURI(c.file)}`;

  const grid = document.getElementById('detail-games');
  grid.innerHTML = '<div class="empty">Loading…</div>';

  if (c.format !== 'full') {
    grid.innerHTML = `<div class="empty">This is a <strong>light</strong> collection — only game IDs are stored. Import it into Tonkatsu Box to see the full list with covers and metadata.</div>`;
    document.getElementById('genre-dropdown').hidden = true;
    document.getElementById('detail-count').textContent = '';
    return;
  }

  try {
    const data = await fetchXcollx(c.file);
    state.detailData = data;
    renderGenreMenu();
    renderDetailGames();
    attachDetailListeners();
  } catch (e) {
    grid.innerHTML = `<div class="empty">Could not load collection file: ${escapeHtml(e.message)}</div>`;
  }
}

async function fetchXcollx(file) {
  if (xcollxCache.has(file)) return xcollxCache.get(file);
  // Try repo-relative path first (works when the site is served from the
  // repo root for local dev). Fall back to raw GitHub content for the
  // deployed GitHub Pages build.
  const candidates = [`../${encodeURI(file)}`, `${REPO_BASE}/${encodeURI(file)}`];
  let lastErr;
  for (const url of candidates) {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      xcollxCache.set(file, data);
      return data;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error('Collection file not reachable');
}

function renderGenreMenu() {
  const dd = document.getElementById('genre-dropdown');
  const games = state.detailData?.media?.games || [];
  const counts = new Map();
  for (const g of games) {
    for (const gn of splitGenres(g.genres)) {
      counts.set(gn, (counts.get(gn) || 0) + 1);
    }
  }
  if (counts.size === 0) {
    dd.hidden = true;
    return;
  }
  dd.hidden = false;
  const items = [
    { id: null, label: 'All genres' },
    ...[...counts.entries()].sort((a, b) => b[1] - a[1]).map(([g, n]) => ({ id: g, label: g, n })),
  ];
  const menu = dd.querySelector('.menu');
  menu.innerHTML = items.map(it => {
    const sel = state.detailGenre === it.id ? ' selected' : '';
    const cnt = it.id ? counts.get(it.id) : games.length;
    return `<div class="opt${sel}" data-pick="${escapeHtml(it.id ?? '')}">
        <span>${escapeHtml(it.label)}</span><span class="count">${cnt}</span>
      </div>`;
  }).join('');
  menu.onclick = ev => {
    const opt = ev.target.closest('.opt');
    if (!opt) return;
    state.detailGenre = opt.dataset.pick || null;
    dd.removeAttribute('open');
    updateDropdownLabel('genre-dropdown',
      state.detailGenre || 'All genres');
    renderGenreMenu();
    renderDetailGames();
  };
}

function splitGenres(s) {
  if (!s) return [];
  return String(s).split(',').map(x => x.trim()).filter(Boolean);
}

function renderDetailGames() {
  const games = state.detailData?.media?.games || [];
  const q = state.detailQuery.toLowerCase();
  const genre = state.detailGenre;
  const filtered = games.filter(g => {
    if (genre && !splitGenres(g.genres).includes(genre)) return false;
    if (q && !(g.name || '').toLowerCase().includes(q)) return false;
    return true;
  });
  filtered.sort((a, b) => (b.rating || 0) - (a.rating || 0));
  document.getElementById('detail-count').textContent =
    filtered.length === games.length
      ? `${filtered.length} games`
      : `${filtered.length} of ${games.length} games`;

  const grid = document.getElementById('detail-games');
  if (filtered.length === 0) {
    grid.innerHTML = `<div class="empty">No games match the filters.</div>`;
    return;
  }
  grid.innerHTML = filtered.map(g => {
    const cover = g.cover_url || '';
    const year = g.release_date
      ? new Date(g.release_date * 1000).getFullYear()
      : '';
    const rating = g.rating ? Math.round(g.rating) : null;
    const genres = splitGenres(g.genres).slice(0, 2).join(', ');
    const url = g.external_url || '#';
    return `<article class="game-cell">
      <a href="${escapeHtml(url)}" target="_blank" rel="noopener">
        <div class="cover${cover ? '' : ' placeholder'}"${cover ? ` style="background-image:url('${cover}')"` : ''}>
          ${cover ? '' : escapeHtml(g.name || '?')}
        </div>
      </a>
      <div class="game-meta">
        <div class="name" title="${escapeHtml(g.name || '')}">${escapeHtml(g.name || '')}</div>
        <div class="sub">
          ${year ? `<span>${year}</span>` : ''}
          ${rating ? `<span class="rating">★ ${rating}</span>` : ''}
        </div>
        ${genres ? `<div class="genres">${escapeHtml(genres)}</div>` : ''}
      </div>
    </article>`;
  }).join('');
}

let _detailListenersAttached = false;
function attachDetailListeners() {
  if (_detailListenersAttached) return;
  _detailListenersAttached = true;
  document.getElementById('detail-search').addEventListener('input', ev => {
    state.detailQuery = ev.target.value.trim();
    renderDetailGames();
  });
}

function closeDetail() {
  document.getElementById('home-view').hidden = false;
  document.getElementById('detail-view').hidden = true;
  document.title = 'Tonkatsu Collections — pre-built game, movie & anime libraries for Tonkatsu Box';
  state.detail = null;
  // Re-render home in case stats need refresh.
  if (state.index) renderHome();
}

// ---------- UI ----------

function attachUiListeners() {
  const search = document.getElementById('search');
  const wrap = document.querySelector('.search');
  search.addEventListener('input', () => {
    state.query = search.value.trim();
    wrap.classList.toggle('has-value', search.value !== '');
    renderHome();
  });
  document.getElementById('clear').addEventListener('click', () => {
    search.value = '';
    state.query = '';
    wrap.classList.remove('has-value');
    renderHome();
    search.focus();
  });
  document.getElementById('sort').addEventListener('change', ev => {
    state.sort = ev.target.value;
    renderHome();
  });
  document.getElementById('back-to-home').addEventListener('click', ev => {
    ev.preventDefault();
    window.location.hash = '';
  });

  // Close dropdowns on outside click.
  document.addEventListener('click', ev => {
    document.querySelectorAll('details.dropdown[open]').forEach(d => {
      if (!d.contains(ev.target)) d.removeAttribute('open');
    });
  });
}

// ---------- utils ----------

function countBy(list, fn) {
  const m = new Map();
  for (const x of list) {
    const k = fn(x);
    if (k == null) continue;
    m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function formatBytes(n) {
  if (!n) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
