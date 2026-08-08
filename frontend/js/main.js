/**
 * 画面遷移と各画面の描画。
 *
 * 企画の核心（docs/FRONTEND.md 1章）:
 *   - 地図を出さない
 *   - 歩いている間は画面を見せない。指示は出発前に一覧で覚えてもらう
 */
const App = (() => {
  const state = {
    grid: null,
    from: null,      // {ns, ew}
    to: null,        // {ns, ew}
    route: null,     // POST /api/route のレスポンス
    routeIndex: 0,
    startSelector: null,
    gridView: null,
  };

  const $ = (selector) => document.querySelector(selector);

  // ── 表示補助 ────────────────────────────────────────────────
  const streetNames = new Map();

  function streetName(id) {
    return streetNames.get(id) ?? id;
  }

  function intersectionLabel(intersection) {
    if (!intersection) return '—';
    return `${streetName(intersection.ns)} × ${streetName(intersection.ew)}`;
  }

  function showScreen(name) {
    for (const screen of document.querySelectorAll('.screen')) {
      screen.hidden = screen.id !== `screen-${name}`;
    }
    window.scrollTo(0, 0);
  }

  function showError(message) {
    const banner = $('#error-banner');
    banner.textContent = message;
    banner.hidden = !message;
  }

  // ── 1. 現在地と目的地を1画面で指定する ──────────────────────
  function setupStartScreen() {
    // 現在地はセレクタ、目的地はグリッド。同じ画面に並べる
    state.gridView = GridView.create($('#grid-container'), state.grid, {
      onSelect(intersection) {
        state.to = intersection;
        updateSummary();
      },
    });

    state.startSelector = IntersectionSelector.create($('#start-selector'), state.grid, {
      onChange(value) {
        state.from = value;
        // グリッドの現在地マーカーをセレクタに追従させる
        state.gridView.setCurrent(value);
        state.to = state.gridView.getSelected();
        updateSummary();
      },
    });

    updateSummary();
    $('#btn-go').addEventListener('click', requestRoute);
  }

  function updateSummary() {
    $('#summary-current').textContent = intersectionLabel(state.from);
    $('#summary-destination').textContent = intersectionLabel(state.to);
    $('#btn-go').disabled = !(state.from && state.to);
  }

  async function requestRoute() {
    if (!state.from || !state.to) return;
    showError('');
    $('#btn-go').disabled = true;
    try {
      state.route = await Api.postRoute(state.from, state.to);
      state.routeIndex = 0;
      renderRouteScreen();
      showScreen('route');
    } catch (error) {
      showError(error.message);
    } finally {
      $('#btn-go').disabled = false;
    }
  }

  // ── 3. 経路の指示（最重要画面） ─────────────────────────────
  function renderRouteScreen() {
    const route = state.route;

    // モックは固定の1組しか持たないため、必ずレスポンスの from / to を正とする
    $('#route-from').textContent = intersectionLabel(route.from);
    $('#route-to').textContent = intersectionLabel(route.to);

    const hint = $('#route-hint');
    hint.textContent = route.start?.hint ?? '';
    hint.classList.toggle('is-invisible', route.start?.tower_visible === false);

    renderRouteTabs(route.routes);
    renderSteps(route.routes[state.routeIndex]);
  }

  function renderRouteTabs(routes) {
    const tabs = $('#route-tabs');
    tabs.innerHTML = '';
    tabs.hidden = routes.length <= 1;
    if (routes.length <= 1) return;

    routes.forEach((route, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'route-tab';
      button.classList.toggle('is-active', index === state.routeIndex);
      button.innerHTML = `
        <span class="route-tab-title">経路 ${index + 1}</span>
        <span class="route-tab-meta">タワーが見える ${Math.round(route.visible_ratio * 100)}％ ／ 曲がり ${route.turns}回</span>
      `;
      button.addEventListener('click', () => {
        state.routeIndex = index;
        renderRouteScreen();
      });
      tabs.appendChild(button);
    });
  }

  function renderSteps(route) {
    const list = $('#route-steps');
    list.innerHTML = '';

    route.steps.forEach((step, index) => {
      const item = document.createElement('li');
      item.className = 'step';
      item.classList.toggle('is-blind', step.tower_visible === false);

      const number = document.createElement('span');
      number.className = 'step-number';
      number.textContent = index + 1;

      const body = document.createElement('div');
      body.className = 'step-body';

      // instruction はバックエンドが完成させた文。ここで組み立てない（docs/API.md 3.2）
      const text = document.createElement('p');
      text.className = 'step-instruction';
      text.textContent = step.instruction;
      body.appendChild(text);

      if (step.tower_visible === false) {
        const note = document.createElement('p');
        note.className = 'step-note';
        note.textContent = 'この区間は京都タワーが見えません。通り名を頼りに進んでください。';
        body.appendChild(note);
      }

      item.appendChild(number);
      item.appendChild(body);
      list.appendChild(item);
    });
  }

  // ── 歩行中（画面を見せない） ────────────────────────────────
  function startWalking() {
    $('#overlay-walk').hidden = false;
    document.body.classList.add('is-walking');
  }

  function stopWalking() {
    $('#overlay-walk').hidden = true;
    document.body.classList.remove('is-walking');
  }

  /** 一連の流れを終えて最初に戻る */
  function restart() {
    state.route = null;
    state.gridView.clearDestination();
    state.startSelector.reset();   // onChange 経由で state.from / state.to も戻る
    showError('');
    showScreen('start');
  }

  // ── 起動 ────────────────────────────────────────────────────
  function bindNavigation() {
    $('#btn-route-back').addEventListener('click', () => showScreen('start'));
    $('#btn-walk').addEventListener('click', startWalking);

    $('#btn-peek').addEventListener('click', stopWalking);
    $('#btn-arrived').addEventListener('click', () => {
      stopWalking();
      restart();
    });

    $('#btn-giveup').addEventListener('click', () => {
      $('#giveup-panel').hidden = false;
      $('#giveup-destination').textContent = intersectionLabel(state.route.to);
    });
    $('#btn-giveup-close').addEventListener('click', () => {
      $('#giveup-panel').hidden = true;
    });
  }

  async function init() {
    try {
      state.grid = await Api.getGrid();
    } catch (error) {
      showError(`グリッドの読み込みに失敗しました。${error.message}`);
      return;
    }

    for (const street of [...state.grid.ns_streets, ...state.grid.ew_streets]) {
      streetNames.set(street.id, street.name);
    }

    $('#mock-badge').hidden = !Api.isMock;

    setupStartScreen();
    bindNavigation();
    showScreen('start');
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', App.init);
