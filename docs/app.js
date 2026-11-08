const STORAGE_KEYS = {
  CHECKED_INGREDIENTS: 'kucharka_checked_ingredients',
  CHECKED_STEPS: 'kucharka_checked_steps',
  PORTIONS: 'kucharka_portions',
  TIMERS: 'kucharka_timers'
};

const state = {
  recipes: [],
  searchText: '',
  currentRecipeSlug: null,
  checkedIngredients: {},
  checkedSteps: {},
  portionScale: {},
  timers: [],
  wakeLock: null,
  alertTimer: null,
  audioContext: null
};

const dom = {
  listPage: document.getElementById('listPage'),
  detailPage: document.getElementById('detailPage'),
  recipeList: document.getElementById('recipeList'),
  emptyState: document.getElementById('emptyState'),
  searchInput: document.getElementById('searchInput'),
  backButton: document.getElementById('backButton'),
  appTitle: document.getElementById('appTitle'),
  timerBar: document.getElementById('timerBar'),
  recipeDetail: document.getElementById('recipeDetail'),
  globalAlert: document.getElementById('globalAlert'),
  alertMessage: document.getElementById('alertMessage'),
  alertOkButton: document.getElementById('alertOkButton')
};

function normalizeText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function safeText(value) {
  return String(value || '').trim();
}

function getRecipeIngredients(recipe) {
  if (Array.isArray(recipe?.ingredience)) {
    return recipe.ingredience;
  }
  if (Array.isArray(recipe?.ingredients)) {
    return recipe.ingredients;
  }
  return [];
}

function getRecipeSteps(recipe) {
  if (Array.isArray(recipe?.postup)) {
    return recipe.postup;
  }
  if (Array.isArray(recipe?.steps)) {
    return recipe.steps;
  }
  if (Array.isArray(recipe?.kroky)) {
    return recipe.kroky;
  }
  return [];
}

function formatNumber(value) {
  if (!Number.isFinite(value)) {
    return '0';
  }
  const rounded = Number(value.toFixed(2));
  return String(rounded).replace('.', ',');
}

function parseNumberLike(value) {
  if (value === null || value === undefined) {
    return null;
  }

  const text = String(value).trim();
  if (!text) {
    return null;
  }

  const normalized = text.replace(/\s+/g, ' ').replace(',', '.');

  const fractionMatch = normalized.match(/^([0-9]+)\s+([0-9]+)\/([0-9]+)$/);
  if (fractionMatch) {
    const whole = Number(fractionMatch[1]);
    const numerator = Number(fractionMatch[2]);
    const denominator = Number(fractionMatch[3]);
    if (denominator) {
      return whole + (numerator / denominator);
    }
  }

  const simpleFraction = normalized.match(/^([0-9]+)\/([0-9]+)$/);
  if (simpleFraction) {
    const numerator = Number(simpleFraction[1]);
    const denominator = Number(simpleFraction[2]);
    if (denominator) {
      return numerator / denominator;
    }
  }

  const plainNumber = Number(normalized);
  if (Number.isFinite(plainNumber)) {
    return plainNumber;
  }

  return null;
}

function readJsonStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (error) {
    return fallback;
  }
}

function saveJsonStorage(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function getIngredientState(recipeSlug, index) {
  return Boolean((state.checkedIngredients[recipeSlug] || {})[index]);
}

function setIngredientState(recipeSlug, index, value) {
  const slugMap = state.checkedIngredients[recipeSlug] || {};
  slugMap[index] = value;
  state.checkedIngredients[recipeSlug] = slugMap;
  saveJsonStorage(STORAGE_KEYS.CHECKED_INGREDIENTS, state.checkedIngredients);
}

function getStepState(recipeSlug, index) {
  return Boolean((state.checkedSteps[recipeSlug] || {})[index]);
}

function setStepState(recipeSlug, index, value) {
  const slugMap = state.checkedSteps[recipeSlug] || {};
  slugMap[index] = value;
  state.checkedSteps[recipeSlug] = slugMap;
  saveJsonStorage(STORAGE_KEYS.CHECKED_STEPS, state.checkedSteps);
}

function getPortionScale(recipeSlug) {
  return Number(state.portionScale[recipeSlug] || 1);
}

function setPortionScale(recipeSlug, value) {
  state.portionScale[recipeSlug] = value;
  saveJsonStorage(STORAGE_KEYS.PORTIONS, state.portionScale);
}

function parseRecipePortions(recipe) {
  const value = safeText(recipe.porce);
  const match = value.match(/([0-9]+(?:[.,][0-9]+)?|[0-9]+\s+[0-9]+\/[0-9]+|[0-9]+\/[0-9]+)/);
  if (!match) {
    return null;
  }
  const parsed = parseNumberLike(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
}

function getScaledIngredientText(item, multiplier) {
  const raw = safeText(item.mnozstvi);
  const parsed = parseNumberLike(raw);
  if (parsed === null) {
    return `${raw} ${safeText(item.jednotka)} ${safeText(item.nazev)}`.trim();
  }

  const scaled = parsed * multiplier;
  const quantity = formatNumber(scaled);
  return `${quantity} ${safeText(item.jednotka)} ${safeText(item.nazev)}`.trim();
}

async function fetchJsonWithFallback(url) {
  try {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error('Chyba při načtení dat');
    }
    return await response.json();
  } catch (error) {
    const cachedResponse = await caches.match(url);
    if (cachedResponse) {
      return cachedResponse.json();
    }
    throw new Error('Nepodařilo se načíst recepty. Zkontrolujte připojení nebo cache aplikace.');
  }
}

async function loadRecipes() {
  try {
    const data = await fetchJsonWithFallback('./recepty.json');
    state.recipes = Array.isArray(data) ? data : [];
    if (!state.recipes.length) {
      dom.emptyState.classList.remove('hidden');
      dom.emptyState.textContent = 'V databázi nejsou žádné recepty.';
    }
  } catch (error) {
    dom.emptyState.classList.remove('hidden');
    dom.emptyState.textContent = error.message || 'Nepodařilo se načíst recepty.';
    state.recipes = [];
  }
}

function renderList() {
  const query = normalizeText(dom.searchInput.value);
  const filtered = state.recipes.filter((recipe) => {
    const titleMatch = normalizeText(recipe.nazev).includes(query);
    const ingredientsMatch = getRecipeIngredients(recipe).some((ingredient) => {
      const text = `${ingredient.nazev || ''} ${ingredient.jednotka || ''} ${ingredient.mnozstvi || ''}`;
      return normalizeText(text).includes(query);
    });
    return !query || titleMatch || ingredientsMatch;
  });

  dom.recipeList.innerHTML = '';

  if (!filtered.length) {
    dom.emptyState.classList.remove('hidden');
    dom.emptyState.textContent = 'Žádné recepty neodpovídají hledání.';
    return;
  }

  dom.emptyState.classList.add('hidden');

  filtered.forEach((recipe) => {
    const card = document.createElement('article');
    card.className = 'recipe-card';

    const button = document.createElement('button');
    button.type = 'button';
    button.addEventListener('click', () => {
      window.location.hash = `#/recept/${encodeURIComponent(recipe.slug)}`;
    });

    const thumb = document.createElement('img');
    thumb.className = 'recipe-thumb';
    thumb.alt = recipe.nazev || 'Recept';
    thumb.src = recipe.foto ? `./obrazky/${encodeURIComponent(recipe.foto)}` : './icons/192.png';
    thumb.loading = 'lazy';

    const body = document.createElement('div');
    body.className = 'card-body';

    const title = document.createElement('h2');
    title.className = 'recipe-title';
    title.textContent = recipe.nazev || 'Bez názvu';

    const meta = document.createElement('div');
    meta.className = 'recipe-meta';

    const cas = document.createElement('span');
    cas.className = 'meta-pill';
    cas.textContent = recipe.cas || 'Čas neuveden';

    const porce = document.createElement('span');
    porce.className = 'meta-pill';
    porce.textContent = recipe.porce || 'Počet porcí neuveden';

    const obtiznost = document.createElement('span');
    obtiznost.className = 'meta-pill';
    obtiznost.textContent = recipe.obtiznost || 'Obtížnost neuvedena';

    meta.append(cas, porce, obtiznost);
    body.append(title, meta);
    button.append(thumb, body);
    card.appendChild(button);
    dom.recipeList.appendChild(card);
  });
}

function showListPage() {
  dom.listPage.classList.add('active');
  dom.detailPage.classList.remove('active');
  dom.backButton.classList.add('hidden');
  dom.appTitle.textContent = 'Kuchařka';
}

function showDetailPage(recipeSlug) {
  const recipe = state.recipes.find((item) => item.slug === recipeSlug);
  if (!recipe) {
    showListPage();
    return;
  }

  state.currentRecipeSlug = recipeSlug;
  dom.listPage.classList.remove('active');
  dom.detailPage.classList.add('active');
  dom.backButton.classList.remove('hidden');
  dom.appTitle.textContent = recipe.nazev || 'Detail receptu';

  const detail = dom.recipeDetail;
  detail.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'detail-header';

  if (recipe.foto) {
    const img = document.createElement('img');
    img.className = 'detail-photo';
    img.src = `./obrazky/${encodeURIComponent(recipe.foto)}`;
    img.alt = recipe.nazev || 'Fotografie receptu';
    header.appendChild(img);
  }

  const content = document.createElement('div');
  content.className = 'detail-content';

  const title = document.createElement('h2');
  title.className = 'detail-title';
  title.textContent = recipe.nazev || 'Bez názvu';

  const metaRow = document.createElement('div');
  metaRow.className = 'meta-row';

  const items = [
    recipe.cas || 'Čas neuveden',
    recipe.porce || 'Počet porcí neuveden',
    recipe.obtiznost || 'Obtížnost neuvedena'
  ];

  items.forEach((item) => {
    const badge = document.createElement('span');
    badge.className = 'meta-pill';
    badge.textContent = item;
    metaRow.appendChild(badge);
  });

  const portionRow = document.createElement('div');
  portionRow.className = 'detail-section';
  const portionTitle = document.createElement('h3');
  portionTitle.className = 'section-title';
  portionTitle.textContent = 'Přepočet porcí';

  const portionBar = document.createElement('div');
  portionBar.className = 'portion-bar';

  const minusButton = document.createElement('button');
  minusButton.type = 'button';
  minusButton.className = 'portion-button';
  minusButton.textContent = '−';
  minusButton.addEventListener('click', () => {
    adjustPortions(recipeSlug, -0.25);
  });

  const value = document.createElement('span');
  value.className = 'portion-value';
  const scale = getPortionScale(recipeSlug);
  value.textContent = `${formatNumber(scale)}×`;

  const plusButton = document.createElement('button');
  plusButton.type = 'button';
  plusButton.className = 'portion-button';
  plusButton.textContent = '+';
  plusButton.addEventListener('click', () => {
    adjustPortions(recipeSlug, 0.25);
  });

  portionBar.append(minusButton, value, plusButton);
  portionRow.append(portionTitle, portionBar);

  const ingredientsSection = document.createElement('div');
  ingredientsSection.className = 'detail-section';
  const ingredientsTitle = document.createElement('h3');
  ingredientsTitle.className = 'section-title';
  ingredientsTitle.textContent = 'Ingredience';

  const ingredientList = document.createElement('ul');
  ingredientList.className = 'list-box';

  getRecipeIngredients(recipe).forEach((ingredient, index) => {
    const item = document.createElement('li');
    item.className = 'check-item';
    if (getIngredientState(recipeSlug, index)) {
      item.classList.add('done');
    }

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'check-toggle';
    toggle.setAttribute('aria-label', 'Označit ingredienci');
    if (getIngredientState(recipeSlug, index)) {
      toggle.classList.add('checked');
    }
    toggle.addEventListener('click', () => {
      const nextValue = !getIngredientState(recipeSlug, index);
      setIngredientState(recipeSlug, index, nextValue);
      renderDetailForCurrentRecipe();
    });

    const text = document.createElement('span');
    text.className = 'ingredient-text';
    text.textContent = getScaledIngredientText(ingredient, scale);

    item.append(toggle, text);
    ingredientList.appendChild(item);
  });

  ingredientsSection.append(ingredientsTitle, ingredientList);

  const stepsSection = document.createElement('div');
  stepsSection.className = 'detail-section';
  const stepsTitle = document.createElement('h3');
  stepsTitle.className = 'section-title';
  stepsTitle.textContent = 'Postup';

  const stepsList = document.createElement('div');
  stepsList.className = 'list-box';

  getRecipeSteps(recipe).forEach((step, index) => {
    const card = document.createElement('div');
    card.className = 'step-item';
    if (getStepState(recipeSlug, index)) {
      card.classList.add('done');
    }

    const row = document.createElement('div');
    row.className = 'step-header';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'check-toggle';
    if (getStepState(recipeSlug, index)) {
      toggle.classList.add('checked');
    }
    toggle.addEventListener('click', () => {
      const nextValue = !getStepState(recipeSlug, index);
      setStepState(recipeSlug, index, nextValue);
      renderDetailForCurrentRecipe();
    });

    const text = document.createElement('span');
    text.className = 'step-text';
    text.textContent = `${index + 1}. ${step.text || 'Krok bez textu'}`;

    row.append(toggle, text);

    const actions = document.createElement('div');
    actions.className = 'step-actions';

    const timerMinutes = Number(step.casovac_min);
    if (Number.isFinite(timerMinutes) && timerMinutes > 0) {
      const timerButton = document.createElement('button');
      timerButton.type = 'button';
      timerButton.className = 'primary-button';
      timerButton.textContent = `Spustit časovač (${timerMinutes} min)`;
      timerButton.addEventListener('click', () => {
        startTimer(recipeSlug, index, timerMinutes, `Krok ${index + 1}: ${safeText(step.text).slice(0, 42) || 'Časovač'}`);
      });
      actions.appendChild(timerButton);
    }

    card.append(row, actions);
    stepsList.appendChild(card);
  });

  stepsSection.append(stepsTitle, stepsList);

  const tipSection = document.createElement('div');
  tipSection.className = 'detail-section';
  if (safeText(recipe.tip)) {
    const tipTitle = document.createElement('h3');
    tipTitle.className = 'section-title';
    tipTitle.textContent = 'Tip';
    const tipBox = document.createElement('div');
    tipBox.className = 'tip-box';
    tipBox.textContent = recipe.tip;
    tipSection.append(tipTitle, tipBox);
  }

  content.append(title, metaRow, portionRow, ingredientsSection, stepsSection, tipSection);
  detail.append(header, content);
}

function renderDetailForCurrentRecipe() {
  if (!state.currentRecipeSlug) {
    return;
  }
  showDetailPage(state.currentRecipeSlug);
}

function adjustPortions(recipeSlug, delta) {
  const current = getPortionScale(recipeSlug);
  const next = Math.max(0.25, Number((current + delta).toFixed(2)));
  setPortionScale(recipeSlug, next);
  renderDetailForCurrentRecipe();
}

function routeFromHash() {
  const hash = window.location.hash || '#/';
  const match = hash.match(/^#\/recept\/(.+)$/);

  if (match) {
    const decoded = decodeURIComponent(match[1]);
    state.currentRecipeSlug = decoded;
    showDetailPage(decoded);
    requestWakeLock();
    return;
  }

  state.currentRecipeSlug = null;
  showListPage();
  requestWakeLock();
}

function renderTimerBar() {
  const activeTimers = state.timers.filter((timer) => timer && (timer.running || timer.remainingMs > 0 || timer.endAt));

  dom.timerBar.innerHTML = '';
  if (!activeTimers.length) {
    dom.timerBar.classList.remove('visible');
    return;
  }

  activeTimers.forEach((timer) => {
    const item = document.createElement('div');
    item.className = 'timer-pill';

    const label = document.createElement('strong');
    label.textContent = timer.label || 'Časovač';

    const countdown = document.createElement('span');
    countdown.textContent = formatCountdown(getRemainingMs(timer));

    const toggleButton = document.createElement('button');
    toggleButton.type = 'button';
    toggleButton.textContent = timer.running ? 'Pozastavit' : 'Spustit';
    toggleButton.addEventListener('click', () => {
      if (timer.running) {
        pauseTimer(timer.id);
      } else {
        resumeTimer(timer.id);
      }
    });

    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.textContent = 'Zrušit';
    cancelButton.addEventListener('click', () => {
      cancelTimer(timer.id);
    });

    const addMinuteButton = document.createElement('button');
    addMinuteButton.type = 'button';
    addMinuteButton.textContent = '+1 min';
    addMinuteButton.addEventListener('click', () => {
      addMinute(timer.id);
    });

    item.append(label, countdown, toggleButton, cancelButton, addMinuteButton);
    dom.timerBar.appendChild(item);
  });

  dom.timerBar.classList.add('visible');
}

function formatCountdown(ms) {
  const safeMs = Math.max(0, Math.ceil(ms / 1000) * 1000);
  const totalSeconds = Math.floor(safeMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function getRemainingMs(timer) {
  if (timer.running && timer.endAt) {
    return Math.max(0, Number(timer.endAt) - Date.now());
  }

  if (Number.isFinite(timer.remainingMs)) {
    return Math.max(0, Number(timer.remainingMs));
  }

  if (timer.durationMs) {
    return Math.max(0, Number(timer.durationMs));
  }

  return 0;
}

function persistTimers() {
  saveJsonStorage(STORAGE_KEYS.TIMERS, state.timers);
}

function startTimer(recipeSlug, stepIndex, minutes, label) {
  ensureAudioContext();
  const timerId = `timer-${recipeSlug}-${stepIndex}-${Date.now()}`;
  const timer = {
    id: timerId,
    recipeSlug,
    stepIndex,
    label,
    durationMs: minutes * 60 * 1000,
    remainingMs: minutes * 60 * 1000,
    endAt: Date.now() + minutes * 60 * 1000,
    running: true
  };

  state.timers.push(timer);
  persistTimers();
  renderTimerBar();
}

function pauseTimer(timerId) {
  const timer = state.timers.find((item) => item.id === timerId);
  if (!timer || !timer.running) {
    return;
  }

  timer.remainingMs = Math.max(0, Number(timer.endAt) - Date.now());
  timer.running = false;
  timer.endAt = null;
  persistTimers();
  renderTimerBar();
}

function resumeTimer(timerId) {
  const timer = state.timers.find((item) => item.id === timerId);
  if (!timer || timer.running) {
    return;
  }

  const remainingMs = Number(timer.remainingMs) || Number(timer.durationMs) || 0;
  timer.remainingMs = remainingMs;
  timer.endAt = Date.now() + remainingMs;
  timer.running = true;
  persistTimers();
  renderTimerBar();
}

function cancelTimer(timerId) {
  state.timers = state.timers.filter((timer) => timer.id !== timerId);
  persistTimers();
  renderTimerBar();
}

function addMinute(timerId) {
  const timer = state.timers.find((item) => item.id === timerId);
  if (!timer) {
    return;
  }

  const nextDuration = (getRemainingMs(timer) || timer.durationMs || 0) + 60 * 1000;
  timer.durationMs = nextDuration;
  timer.remainingMs = nextDuration;
  timer.endAt = Date.now() + nextDuration;
  timer.running = true;
  persistTimers();
  renderTimerBar();
}

function tickTimers() {
  const now = Date.now();
  let changed = false;

  state.timers = state.timers.filter((timer) => {
    if (timer.running && timer.endAt && Number(timer.endAt) <= now) {
      timer.running = false;
      timer.remainingMs = 0;
      timer.endAt = null;
      showTimerAlert(timer.label || 'Časovač');
      changed = true;
      return true;
    }

    if (!timer.running && timer.endAt && Number(timer.endAt) <= now) {
      timer.remainingMs = 0;
      timer.endAt = null;
      changed = true;
    }

    if (timer.running && timer.endAt) {
      timer.remainingMs = Math.max(0, Number(timer.endAt) - now);
    }

    return true;
  });

  if (changed) {
    persistTimers();
  }

  renderTimerBar();
}

function ensureAudioContext() {
  if (!('AudioContext' in window || 'webkitAudioContext' in window)) {
    return null;
  }

  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  if (!state.audioContext) {
    state.audioContext = new AudioCtor();
  }

  if (state.audioContext.state === 'suspended') {
    state.audioContext.resume();
  }

  return state.audioContext;
}

function playAlertTone() {
  const context = ensureAudioContext();
  if (!context) {
    return;
  }

  const oscillator = context.createOscillator();
  const gainNode = context.createGain();
  oscillator.type = 'sine';
  oscillator.frequency.value = 880;
  gainNode.gain.value = 0.12;
  oscillator.connect(gainNode);
  gainNode.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + 0.2);
}

function showTimerAlert(label) {
  playAlertTone();
  if ('vibrate' in navigator) {
    navigator.vibrate([200, 120, 200, 120, 400]);
  }

  dom.alertMessage.textContent = `${label} skončil.`;
  dom.globalAlert.classList.remove('hidden');
  if (state.alertTimer) {
    clearTimeout(state.alertTimer);
  }
  state.alertTimer = setTimeout(() => {
    dom.globalAlert.classList.add('hidden');
  }, 10000);
}

dom.alertOkButton.addEventListener('click', () => {
  dom.globalAlert.classList.add('hidden');
  if (state.alertTimer) {
    clearTimeout(state.alertTimer);
    state.alertTimer = null;
  }
});

async function requestWakeLock() {
  if (!('wakeLock' in navigator)) {
    return;
  }

  if (state.currentRecipeSlug) {
    try {
      if (state.wakeLock && state.wakeLock.released === false) {
        return;
      }
      state.wakeLock = await navigator.wakeLock.request('screen');
    } catch (error) {
      state.wakeLock = null;
    }
    return;
  }

  if (state.wakeLock) {
    try {
      await state.wakeLock.release();
    } catch (error) {
      // ignore
    }
    state.wakeLock = null;
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    requestWakeLock();
  }
});

async function refreshServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    return;
  }

  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));
  await navigator.serviceWorker.register('./service-worker.js');
}

function bindEvents() {
  dom.searchInput.addEventListener('input', (event) => {
    state.searchText = event.target.value;
    renderList();
  });

  dom.backButton.addEventListener('click', () => {
    window.location.hash = '#/';
  });

  refreshServiceWorker().catch(() => {});
}

async function initApp() {
  state.checkedIngredients = readJsonStorage(STORAGE_KEYS.CHECKED_INGREDIENTS, {});
  state.checkedSteps = readJsonStorage(STORAGE_KEYS.CHECKED_STEPS, {});
  state.portionScale = readJsonStorage(STORAGE_KEYS.PORTIONS, {});
  state.timers = readJsonStorage(STORAGE_KEYS.TIMERS, []);

  bindEvents();
  await loadRecipes();
  renderList();
  window.addEventListener('hashchange', routeFromHash);
  routeFromHash();
  renderTimerBar();
  setInterval(tickTimers, 1000);
}

dom.backButton.classList.add('hidden');
initApp();
