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
    arrivalSelector: null,
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

  // ── 1. 現在地の入力 ─────────────────────────────────────────
  function setupStartScreen() {
    state.startSelector = IntersectionSelector.create($('#start-selector'), state.grid, {
      onChange(value) {
        $('#btn-start-confirm').disabled = !value;
      },
    });

    $('#btn-start-confirm').addEventListener('click', () => {
      state.from = state.startSelector.getValue();
      if (!state.from) return;
      setupDestinationScreen();
      showScreen('destination');
    });
  }

  // ── 2. 目的地の選択（グリッドUI） ───────────────────────────
  function setupDestinationScreen() {
    $('#destination-current').textContent = intersectionLabel(state.from);
    $('#btn-dest-confirm').disabled = true;
    state.to = null;

    GridView.create($('#grid-container'), state.grid, {
      current: state.from,
      onSelect(intersection) {
        state.to = intersection;
        $('#destination-selected').textContent = intersectionLabel(intersection);
        $('#btn-dest-confirm').disabled = false;
      },
    });
    $('#destination-selected').textContent = '—';
  }

  async function requestRoute() {
    if (!state.from || !state.to) return;
    showError('');
    $('#btn-dest-confirm').disabled = true;
    try {
      state.route = await Api.postRoute(state.from, state.to);
      state.routeIndex = 0;
      renderRouteScreen();
      showScreen('route');
    } catch (error) {
      showError(error.message);
    } finally {
      $('#btn-dest-confirm').disabled = false;
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

  // ── 4. 到着の入力と講評（優先度低） ─────────────────────────
  function setupArrivalScreen() {
    $('#arrival-target').textContent = intersectionLabel(state.route.to);
    $('#arrival-result').hidden = true;

    if (!state.arrivalSelector) {
      state.arrivalSelector = IntersectionSelector.create($('#arrival-selector'), state.grid, {
        onChange(value) {
          $('#btn-arrival-check').disabled = !value;
        },
      });
    } else {
      state.arrivalSelector.reset();
    }
    $('#btn-arrival-check').disabled = true;
  }

  async function checkArrival() {
    const actual = state.arrivalSelector.getValue();
    if (!actual) return;
    showError('');
    try {
      const result = await Api.postArrival(state.route.to, actual);
      renderArrivalResult(result);
    } catch (error) {
      showError(error.message);
    }
  }

  function renderArrivalResult(result) {
    const box = $('#arrival-result');
    box.hidden = false;
    box.classList.toggle('is-correct', result.correct);

    const headline = result.correct ? '着いてはります。' : 'すこし ずれてはります。';
    const gaps = [];
    if (result.off_by.ew) {
      gaps.push(`${Math.abs(result.off_by.ew)}本 ${result.off_by.ew > 0 ? '下' : '上'}`);
    }
    if (result.off_by.ns) {
      gaps.push(`${Math.abs(result.off_by.ns)}本 ${result.off_by.ns > 0 ? '西' : '東'}`);
    }

    // 講評文（comment）はバックエンドが生成する。未接続時は数値のズレだけ出す
    box.innerHTML = `
      <p class="arrival-headline">${headline}</p>
      ${gaps.length ? `<p class="arrival-gap">ずれ: ${gaps.join(' / ')}</p>` : ''}
      <p class="arrival-comment">${result.comment ?? '（講評はバックエンド接続後に表示されます）'}</p>
    `;
  }

  // ── 起動 ────────────────────────────────────────────────────
  function bindNavigation() {
    $('#btn-dest-back').addEventListener('click', () => showScreen('start'));
    $('#btn-dest-confirm').addEventListener('click', requestRoute);

    $('#btn-route-back').addEventListener('click', () => showScreen('destination'));
    $('#btn-walk').addEventListener('click', startWalking);

    $('#btn-peek').addEventListener('click', stopWalking);
    $('#btn-arrived').addEventListener('click', () => {
      stopWalking();
      setupArrivalScreen();
      showScreen('arrival');
    });

    $('#btn-giveup').addEventListener('click', () => {
      $('#giveup-panel').hidden = false;
      $('#giveup-destination').textContent = intersectionLabel(state.route.to);
    });
    $('#btn-giveup-close').addEventListener('click', () => {
      $('#giveup-panel').hidden = true;
    });

    $('#btn-arrival-check').addEventListener('click', checkArrival);
    $('#btn-restart').addEventListener('click', () => {
      state.from = null;
      state.to = null;
      state.route = null;
      state.startSelector.reset();
      showScreen('start');
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
