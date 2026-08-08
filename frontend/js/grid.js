/**
 * 目的地を選ぶグリッドUI（docs/FRONTEND.md 4.2）。
 *
 * 碁盤の目を模した「抽象的な格子」であって地図ではない。
 * 地図ライブラリは使わない。座標も持たない（docs/SPEC.md 4.5）。
 *
 * 行 = ew（横の通り）、列 = ns（縦の通り）。docs/API.md 3.1 の exists と同じ向き。
 *
 * 現在地は別画面のセレクタで決まるため、setCurrent() で後から差し替えられる。
 */
const GridView = (() => {

  /**
   * @param {HTMLElement} root  描画先
   * @param {object} grid       GET /api/grid のレスポンス
   * @param {object} [options]
   * @param {(intersection: {ns: string, ew: string} | null) => void} [options.onSelect]
   *        目的地が変わったときに呼ばれる。解除されたときは null
   */
  function create(root, grid, options = {}) {
    const { onSelect } = options;
    const towerNs = grid.tower ? Api.indexOf(grid.tower.ns) : null;
    const towerEw = grid.tower ? Api.indexOf(grid.tower.ew) : null;

    // ── 観光地。敷地の広がりを淡く示し、代表する交差点に印を置く ──
    const spots = grid.spots ?? [];
    const spotAt = new Map();       // "ns:ew" -> 観光地名
    const inSpotArea = new Set();   // 敷地に含まれる "ns:ew"

    for (const spot of spots) {
      spotAt.set(`${Api.indexOf(spot.at.ns)}:${Api.indexOf(spot.at.ew)}`, spot.name);
      if (!spot.area) continue;
      const [nsFrom, nsTo] = spot.area.ns.map(Api.indexOf);
      const [ewFrom, ewTo] = spot.area.ew.map(Api.indexOf);
      for (let ew = ewFrom; ew <= ewTo; ew += 1) {
        for (let ns = nsFrom; ns <= nsTo; ns += 1) inSpotArea.add(`${ns}:${ew}`);
      }
    }

    let selected = null;   // {nsIndex, ewIndex}
    let current = null;    // {nsIndex, ewIndex}
    const cellByKey = new Map();
    const key = (nsIndex, ewIndex) => `${nsIndex}:${ewIndex}`;

    const exists = (nsIndex, ewIndex) => Boolean(grid.exists?.[ewIndex]?.[nsIndex]);
    const cellAt = (position) => (position ? cellByKey.get(key(position.nsIndex, position.ewIndex)) : null);
    const same = (a, b) => Boolean(a && b && a.nsIndex === b.nsIndex && a.ewIndex === b.ewIndex);
    const toIntersection = ({ nsIndex, ewIndex }) => ({
      ns: grid.ns_streets[nsIndex].id,
      ew: grid.ew_streets[ewIndex].id,
    });

    // ── 全体が必ず見えるグリッド。スクロール前提の表にはしない ──
    const nsCount = grid.ns_streets.length;
    const ewCount = grid.ew_streets.length;
    const ZOOM_LEVELS = [
      { label: '全体', width: '100%', height: '15rem' },
      { label: '標準', width: '155%', height: '24rem' },
      { label: '拡大', width: '230%', height: '34rem' },
    ];
    let zoomIndex = 1;

    const zoomToolbar = document.createElement('div');
    zoomToolbar.className = 'grid-toolbar';

    const zoomOut = document.createElement('button');
    zoomOut.type = 'button';
    zoomOut.className = 'grid-zoom-button';
    zoomOut.textContent = '−';
    zoomOut.setAttribute('aria-label', '縮小');

    const zoomRange = document.createElement('input');
    zoomRange.type = 'range';
    zoomRange.className = 'grid-zoom-range';
    zoomRange.min = '0';
    zoomRange.max = String(ZOOM_LEVELS.length - 1);
    zoomRange.step = '1';
    zoomRange.value = String(zoomIndex);
    zoomRange.setAttribute('aria-label', '地図の拡大率');

    const zoomIn = document.createElement('button');
    zoomIn.type = 'button';
    zoomIn.className = 'grid-zoom-button';
    zoomIn.textContent = '+';
    zoomIn.setAttribute('aria-label', '拡大');

    const zoomFit = document.createElement('button');
    zoomFit.type = 'button';
    zoomFit.className = 'grid-zoom-fit';
    zoomFit.textContent = '全体';
    zoomFit.setAttribute('aria-label', '全体表示');

    const zoomLabel = document.createElement('span');
    zoomLabel.className = 'grid-zoom-label';
    zoomLabel.setAttribute('aria-live', 'polite');

    zoomToolbar.append(zoomOut, zoomRange, zoomIn, zoomFit, zoomLabel);
    zoomOut.addEventListener('click', () => setZoom(zoomIndex - 1));
    zoomIn.addEventListener('click', () => setZoom(zoomIndex + 1));
    zoomFit.addEventListener('click', () => setZoom(0));
    zoomRange.addEventListener('input', () => setZoom(Number(zoomRange.value)));

    const mapWrap = document.createElement('div');
    mapWrap.className = 'grid-map-wrap';

    const mapScroll = document.createElement('div');
    mapScroll.className = 'grid-map-scroll';

    const map = document.createElement('div');
    map.className = 'grid-map';
    map.setAttribute('role', 'group');
    map.setAttribute('aria-label', '目的地を選ぶ碁盤の目');
    map.style.setProperty('--ns-count', nsCount);
    map.style.setProperty('--ew-count', ewCount);

    const edgeLabels = [
      ['is-north', grid.ew_streets[0]?.name],
      ['is-south', grid.ew_streets[ewCount - 1]?.name],
      ['is-east', grid.ns_streets[0]?.name],
      ['is-west', grid.ns_streets[nsCount - 1]?.name],
    ];
    for (const [className, text] of edgeLabels) {
      if (!text) continue;
      const label = document.createElement('span');
      label.className = `grid-edge-label ${className}`;
      label.textContent = text;
      mapWrap.appendChild(label);
    }

    for (const ewStreet of grid.ew_streets) {
      const ewIndex = ewStreet.index;
      for (const nsStreet of grid.ns_streets) {
        const nsIndex = nsStreet.index;
        const spotName = spotAt.get(key(nsIndex, ewIndex));
        const label = spotName
          ? `${nsStreet.name} × ${ewStreet.name}（${spotName}）`
          : `${nsStreet.name} × ${ewStreet.name}`;
        const isTower = towerNs === nsIndex && towerEw === ewIndex;

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'grid-button';
        button.style.gridColumn = String(nsIndex + 1);
        button.style.gridRow = String(ewIndex + 1);
        button.style.setProperty('--ns-line', nsStreet.major ? 'var(--major-line)' : 'var(--line)');
        button.style.setProperty('--ew-line', ewStreet.major ? 'var(--major-line)' : 'var(--line)');
        button.style.setProperty('--ns-line-width', nsStreet.major ? '2px' : '1px');
        button.style.setProperty('--ew-line-width', ewStreet.major ? '2px' : '1px');
        button.dataset.ns = nsStreet.id;
        button.dataset.ew = ewStreet.id;
        button.dataset.label = label;
        button.title = label;

        if (inSpotArea.has(key(nsIndex, ewIndex))) button.classList.add('is-spot-area');
        if (isTower) button.classList.add('is-tower');
        if (spotName) {
          button.classList.add('is-spot');
          button.dataset.spot = spotName;
        }

        if (!exists(nsIndex, ewIndex)) {
          button.classList.add('is-absent');
          button.disabled = true;
          button.setAttribute('aria-label', `${label}（交差点なし）`);
          map.appendChild(button);
          continue;
        }

        button.dataset.baseAria = isTower ? `${label}（京都タワー）` : label;
        button.setAttribute('aria-label', button.dataset.baseAria);
        button.addEventListener('click', () => selectDestination({ nsIndex, ewIndex }));
        cellByKey.set(key(nsIndex, ewIndex), button);
        map.appendChild(button);
      }
    }

    mapScroll.appendChild(map);
    mapWrap.appendChild(mapScroll);

    const nudge = document.createElement('div');
    nudge.className = 'grid-nudge';
    nudge.hidden = true;

    const nudgeButtons = [
      ['is-up', '↑', '上ル', 0, -1],
      ['is-left', '←', '東入ル', -1, 0],
      ['is-right', '→', '西入ル', 1, 0],
      ['is-down', '↓', '下ル', 0, 1],
    ].map(([className, text, label, deltaNs, deltaEw]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `grid-nudge-button ${className}`;
      button.textContent = text;
      button.title = label;
      button.setAttribute('aria-label', `目的地を${label}へ動かす`);
      button.addEventListener('click', () => moveSelection(deltaNs, deltaEw));
      nudge.appendChild(button);
      return { button, deltaNs, deltaEw };
    });

    const legend = document.createElement('ul');
    legend.className = 'grid-legend';
    legend.innerHTML = `
      <li><span class="legend-swatch is-current">今</span>現在地</li>
      <li><span class="legend-swatch is-selected">★</span>目的地</li>
      <li><span class="legend-swatch is-tower">塔</span>京都タワー</li>
      <li><span class="legend-swatch is-spot">◉</span>観光地</li>
      <li><span class="legend-swatch is-absent"></span>交差点なし</li>
    `;

    // 上ル＝北＝画面の上、という対応をグリッド自身に語らせる。
    // このアプリで一番伝えたいことなので、軸に方角の言葉を置く。
    const compass = document.createElement('div');
    compass.className = 'grid-compass';
    compass.innerHTML = `
      <span class="compass-up">↑ 上ル</span>
      <span class="compass-side">
        <span class="compass-east">東入ル ←</span>
        <span class="compass-west">→ 西入ル</span>
      </span>
      <span class="compass-down">↓ 下ル</span>
    `;

    root.innerHTML = '';
    root.appendChild(compass);
    root.appendChild(zoomToolbar);
    root.appendChild(mapWrap);
    root.appendChild(nudge);
    root.appendChild(legend);
    setZoom(zoomIndex, false);

    /** 現在地・目的地の装飾を外して既定の見た目に戻す */
    function resetCell(position) {
      const button = cellAt(position);
      if (!button) return;
      button.classList.remove('is-current', 'is-selected');
      button.disabled = false;
      button.setAttribute('aria-label', button.dataset.baseAria);
    }

    function clearDestination(notify = true) {
      if (!selected) return;
      resetCell(selected);
      selected = null;
      updateNudge();
      if (notify && onSelect) onSelect(null);
    }

    function selectDestination(position) {
      if (same(position, current)) return;      // 現在地は目的地にできない
      if (same(position, selected)) return;
      clearDestination(false);

      selected = position;
      const button = cellAt(position);
      button.classList.add('is-selected');
      button.setAttribute('aria-label', `${button.dataset.label}（目的地）`);
      updateNudge();
      scrollIntoMap(button);

      if (onSelect) onSelect(toIntersection(position));
    }

    /** 現在地を差し替える。セレクタの変更に追従させるために使う */
    function setCurrent(intersection) {
      if (current) resetCell(current);
      current = null;
      if (!intersection) {
        updateNudge();
        return;
      }

      const position = {
        nsIndex: Api.indexOf(intersection.ns),
        ewIndex: Api.indexOf(intersection.ew),
      };
      const button = cellAt(position);
      if (!button) return;

      // 目的地と重なったら目的地を解除する
      if (same(position, selected)) clearDestination();

      current = position;
      button.classList.add('is-current');
      button.disabled = true;
      button.setAttribute('aria-label', `${button.dataset.label}（現在地）`);
      updateNudge();
      scrollIntoMap(button);
    }

    function nextSelectable(from, deltaNs, deltaEw) {
      let nsIndex = from.nsIndex + deltaNs;
      let ewIndex = from.ewIndex + deltaEw;
      while (nsIndex >= 0 && nsIndex < nsCount && ewIndex >= 0 && ewIndex < ewCount) {
        const position = { nsIndex, ewIndex };
        if (exists(nsIndex, ewIndex) && !same(position, current)) return position;
        nsIndex += deltaNs;
        ewIndex += deltaEw;
      }
      return null;
    }

    function moveSelection(deltaNs, deltaEw) {
      if (!selected) return;
      const next = nextSelectable(selected, deltaNs, deltaEw);
      if (!next) return;
      selectDestination(next);
      cellAt(next)?.focus({ preventScroll: true });
      scrollIntoMap(cellAt(next), true);
    }

    function updateNudge() {
      nudge.hidden = !selected;
      if (!selected) return;
      for (const item of nudgeButtons) {
        item.button.disabled = !nextSelectable(selected, item.deltaNs, item.deltaEw);
      }
    }

    function setZoom(nextIndex, keepContext = true) {
      zoomIndex = Math.min(ZOOM_LEVELS.length - 1, Math.max(0, nextIndex));
      const zoom = ZOOM_LEVELS[zoomIndex];
      map.style.width = zoom.width;
      map.style.height = zoom.height;
      zoomRange.value = String(zoomIndex);
      zoomLabel.textContent = zoom.label;
      zoomOut.disabled = zoomIndex === 0;
      zoomIn.disabled = zoomIndex === ZOOM_LEVELS.length - 1;
      zoomFit.disabled = zoomIndex === 0;
      if (keepContext) revealContext();
    }

    function scrollIntoMap(button, center = false) {
      if (!button || mapScroll.offsetParent === null) return;
      const container = mapScroll.getBoundingClientRect();
      const target = button.getBoundingClientRect();
      const outside =
        target.left < container.left ||
        target.right > container.right ||
        target.top < container.top ||
        target.bottom > container.bottom;
      if (!outside && !center) return;
      mapScroll.scrollLeft +=
        (target.left - container.left) - (container.width - target.width) / 2;
      mapScroll.scrollTop +=
        (target.top - container.top) - (container.height - target.height) / 2;
    }

    function revealContext() {
      const target = cellAt(selected) ?? cellAt(current);
      if (!target) return;
      requestAnimationFrame(() => scrollIntoMap(target, true));
    }

    /** 観光地チップなど、グリッド外から目的地を指定する */
    function selectAt(intersection) {
      const position = {
        nsIndex: Api.indexOf(intersection.ns),
        ewIndex: Api.indexOf(intersection.ew),
      };
      if (!cellAt(position)) return;
      selectDestination(position);
      cellAt(position)?.focus({ preventScroll: true });
      scrollIntoMap(cellAt(position), true);
    }

    /** その交差点にある観光地名（無ければ null） */
    function spotNameAt(intersection) {
      if (!intersection) return null;
      const k = key(Api.indexOf(intersection.ns), Api.indexOf(intersection.ew));
      return spotAt.get(k) ?? null;
    }

    return {
      setCurrent,
      selectAt,
      spotNameAt,
      clearDestination,
      getSelected: () => (selected ? toIntersection(selected) : null),
      revealContext,
    };
  }

  return { create };
})();
