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
    startSelector: null,
    gridView: null,
    resolvedDestination: null,
    isApplyingResolvedDestination: false,
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

  function sameIntersection(a, b) {
    return Boolean(a && b && a.ns === b.ns && a.ew === b.ew);
  }

  function showScreen(name) {
    for (const screen of document.querySelectorAll('.screen')) {
      screen.hidden = screen.id !== `screen-${name}`;
    }
    // 指示の画面ではヘッダを縮めて、手順に集中させる
    document.body.classList.toggle('is-routing', name === 'route');
    document.body.classList.toggle('is-destination', name === 'destination');
    document.body.classList.toggle('is-intro', name === 'intro');
    window.scrollTo(0, 0);
  }

  function showError(message) {
    const banner = $('#error-banner');
    banner.textContent = message;
    banner.hidden = !message;
  }

  // ── 1. 現在地 → 2. 目的地を分けて指定する ───────────────────
  function setupStartScreen() {
    state.gridView = GridView.create($('#grid-container'), state.grid, {
      onSelect(intersection) {
        state.to = intersection;
        if (
          !state.isApplyingResolvedDestination &&
          !sameIntersection(intersection, state.resolvedDestination?.at)
        ) {
          clearResolvedDestination();
        }
        updateDestinationState();
      },
    });

    state.startSelector = IntersectionSelector.create($('#start-selector'), state.grid, {
      onChange(value) {
        state.from = value;
        state.gridView.setCurrent(value);
        state.to = state.gridView.getSelected();
        updateStartState();
        updateDestinationState();
      },
    });

    renderSpotChips();
    bindDestinationResolver();
    updateStartState();
    updateDestinationState();
    $('#btn-start-next').addEventListener('click', () => {
      if (!state.from) return;
      updateDestinationState();
      showScreen('destination');
      state.gridView.revealContext();
    });
    $('#btn-destination-back').addEventListener('click', () => showScreen('start'));
    $('#btn-go').addEventListener('click', requestRoute);
  }

  /**
   * 観光地から目的地を選べるようにする。
   *
   * 観光客が行きたいのは「三条 × 河原町」ではなく「錦市場」なので、
   * 通り名を知らなくても目的地を指定できる入口を用意する（docs/SPEC.md 4.5.3）。
   */
  function renderSpotChips() {
    const container = $('#spot-chips');
    const spots = state.grid.spots ?? [];
    container.innerHTML = '';
    container.hidden = spots.length === 0;
    if (!spots.length) return;

    for (const spot of spots) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'spot-chip';
      chip.textContent = spot.name;
      chip.title = intersectionLabel(spot.at);
      chip.addEventListener('click', () => {
        clearResolvedDestination();
        state.gridView.selectAt(spot.at);
        highlightChip(spot.name);
      });
      container.appendChild(chip);
    }
  }

  function highlightChip(name) {
    for (const chip of document.querySelectorAll('.spot-chip')) {
      chip.classList.toggle('is-active', chip.textContent === name);
    }
  }

  function updateStartState() {
    $('#btn-start-next').disabled = !state.from;
  }

  function updateDestinationState() {
    const summary = $('#summary');
    const spotName = state.to ? state.gridView.spotNameAt(state.to) : null;

    if (!state.from) {
      summary.hidden = true;
    } else {
      summary.hidden = false;
      summary.innerHTML = state.to
        ? `<span class="summary-from">${intersectionLabel(state.from)}</span>` +
          `<span class="summary-arrow">→</span>` +
          `<span class="summary-to">${destinationLabel(state.to)}</span>`
        : `<span class="summary-from">${intersectionLabel(state.from)}</span>` +
          `<span class="summary-hint">目的地を選んでください</span>`;
    }

    highlightChip(spotName);
    $('#btn-go').disabled = !(state.from && state.to);
  }

  function bindDestinationResolver() {
    const form = $('#destination-link-form');
    const input = $('#destination-link-input');
    const button = $('#btn-resolve-destination');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const url = input.value.trim();
      if (!url) {
        setDestinationLinkStatus('Google Mapsリンクを貼ってください', 'error');
        return;
      }

      setDestinationLinkStatus('読み取り中です');
      button.disabled = true;

      try {
        const result = await Api.resolveDestination(url);
        state.resolvedDestination = {
          at: result.destination,
          label: result.label,
          distanceM: result.distance_m,
        };

        state.isApplyingResolvedDestination = true;
        const selected = state.gridView.selectAt(result.destination);
        state.isApplyingResolvedDestination = false;

        if (!selected) {
          state.resolvedDestination = null;
          setDestinationLinkStatus('現在地と同じ場所は目的地にできません', 'error');
          updateDestinationState();
          return;
        }

        const distanceText = result.distance_m > 0 ? `（約${result.distance_m}m）` : '';
        setDestinationLinkStatus(`${result.label}に合わせました${distanceText}`, 'success');
        updateDestinationState();
      } catch (error) {
        state.resolvedDestination = null;
        setDestinationLinkStatus(error.message, 'error');
        updateDestinationState();
      } finally {
        state.isApplyingResolvedDestination = false;
        button.disabled = false;
      }
    });

    input.addEventListener('input', () => {
      if (!input.value.trim()) clearResolvedDestination();
    });
  }

  function setDestinationLinkStatus(message, tone = '') {
    const status = $('#destination-link-status');
    status.textContent = message;
    status.classList.toggle('is-success', tone === 'success');
    status.classList.toggle('is-error', tone === 'error');
  }

  function clearResolvedDestination() {
    state.resolvedDestination = null;
    setDestinationLinkStatus('');
  }

  async function requestRoute() {
    if (!state.from || !state.to) return;
    showError('');
    $('#btn-go').disabled = true;
    try {
      state.route = await Api.postRoute(state.from, state.to);
      renderRouteScreen();
      showScreen('route');
    } catch (error) {
      showError(error.message);
    } finally {
      $('#btn-go').disabled = false;
    }
  }

  // ── 3. 方角と本数（最重要画面） ────────────────────────
  //
  // 経路は指定しない。碁盤の目では上ル/下ル と 東入ル/西入ル を
  // どの順に消化しても着くので、覚えるのは方角2つと本数2つで足りる。
  function renderRouteScreen() {
    const route = state.route;

    $('#route-from').textContent = intersectionLabel(route.from);
    $('#route-to').textContent = destinationLabel(route.to);

    const hint = $('#route-hint');
    hint.textContent = route.start?.hint ?? '';
    // 目印が1つも見えないときだけ警告色にする（見えているなら方角が分かる）
    hint.classList.toggle('is-invisible', !route.start?.landmark?.bearing);

    // 目印の方を向いた景色。線画がある交差点だけ出る（docs/SPEC.md 2.6）
    Scene.render($('#scene'), route.start?.scene ?? null);

    const list = $('#route-moves');
    list.innerHTML = '';
    for (const move of route.moves) {
      const item = document.createElement('li');
      item.className = 'move';
      // 文はバックエンドが作る（instruction）。ここでは構造化された値を並べるだけ
      item.setAttribute('aria-label', move.instruction);
      item.innerHTML = `
        <span class="move-direction">${move.direction}</span>
        <span class="move-target">${move.to_street_name}<span class="move-made">まで</span></span>
        <span class="move-count">およそ${move.count}本</span>
      `;
      list.appendChild(item);
    }
  }

  /** 目的地に観光地名があれば添える */
  function destinationLabel(intersection) {
    if (sameIntersection(intersection, state.resolvedDestination?.at)) {
      return state.resolvedDestination.label;
    }
    const spot = state.gridView?.spotNameAt(intersection);
    const label = intersectionLabel(intersection);
    return spot ? `${spot}（${label}）` : label;
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
    clearResolvedDestination();
    $('#destination-link-input').value = '';
    state.gridView.clearDestination();
    state.startSelector.reset();   // onChange 経由で state.from / state.to も戻る
    showError('');
    showScreen('intro');
  }

  // ── 起動 ────────────────────────────────────────────────────
  function bindNavigation() {
    $('#btn-intro-start').addEventListener('click', () => showScreen('start'));
    $('#btn-route-back').addEventListener('click', () => {
      showScreen('destination');
      state.gridView.revealContext();
    });
    $('#btn-walk').addEventListener('click', startWalking);

    $('#btn-peek').addEventListener('click', stopWalking);
    $('#btn-arrived').addEventListener('click', () => {
      stopWalking();
      restart();
    });

    $('#btn-giveup').addEventListener('click', () => {
      $('#giveup-panel').hidden = false;
      $('#giveup-destination').textContent = destinationLabel(state.route.to);
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
    showScreen('intro');
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', App.init);
