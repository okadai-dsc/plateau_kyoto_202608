/**
 * 目的地を選ぶグリッドUI（docs/FRONTEND.md 4.2）。
 *
 * 碁盤の目を模した「抽象的な格子」であって地図ではない。
 * 地図ライブラリは使わない。座標も持たない（docs/SPEC.md 4.5）。
 *
 * 行 = ew（横の通り）、列 = ns（縦の通り）。docs/API.md 3.1 の exists と同じ向き。
 *
 * 現在地は同じ画面のセレクタで随時変わるため、setCurrent() で後から差し替えられる。
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

    // ── 実寸から見た目を決める（表示専用・docs/API.md 2.1） ──
    //
    // 通りの間隔（街区の大きさ）でマスの大きさを、
    // 通りの幅で罫線の太さを決める。実際の京都の比率に近づけるため。
    // 平方根で圧縮しないと、御所の南北（約1.1km）が街区（約120m）の9倍になり
    // 画面に収まらない。
    const GAP_MIN = 22, GAP_MAX = 80, GAP_SCALE = 3.0;
    const LINE_MIN = 1, LINE_MAX = 8, LINE_SCALE = 1 / 6;

    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

    const DEFAULT_GAP = 120;   // 平安京の1町ぶん。pos を持たないデータのときに使う

    /** 次の通りまでの距離(m) から、マスの大きさ(px) を出す */
    function cellSize(streets, index) {
      const here = streets[index];
      const next = streets[index + 1];
      // 最後の1本は次が無いので、ひとつ手前の間隔を流用する
      const gap = next
        ? next.pos - here.pos
        : (index > 0 ? here.pos - streets[index - 1].pos : DEFAULT_GAP);
      const meters = Number.isFinite(gap) && gap > 0 ? gap : DEFAULT_GAP;
      return Math.round(clamp(GAP_SCALE * Math.sqrt(meters), GAP_MIN, GAP_MAX));
    }

    /** 通りの幅(m) から、罫線の太さ(px) を出す */
    const lineWeight = (street) =>
      Math.round(clamp((street.width ?? 0) * LINE_SCALE, LINE_MIN, LINE_MAX));

    const nsSize = grid.ns_streets.map((_, i) => cellSize(grid.ns_streets, i));
    const ewSize = grid.ew_streets.map((_, i) => cellSize(grid.ew_streets, i));

    // 幅の広い通りほど濃い線にする
    const lineColor = (street) =>
      (street.width ?? 0) >= 12 ? 'var(--major-line)' : 'var(--line)';

    // ── 表の組み立て。本数はデータから取る（ハードコードしない） ──
    const table = document.createElement('table');
    table.className = 'grid';

    // 列幅は colgroup でまとめて指定する
    const colgroup = document.createElement('colgroup');
    const headCol = document.createElement('col');
    headCol.className = 'grid-col-head';
    colgroup.appendChild(headCol);
    for (const street of grid.ns_streets) {
      const col = document.createElement('col');
      col.style.width = `${nsSize[street.index]}px`;
      colgroup.appendChild(col);
    }
    table.appendChild(colgroup);

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    const corner = document.createElement('th');
    corner.className = 'grid-corner';
    corner.setAttribute('scope', 'col');
    headRow.appendChild(corner);

    for (const street of grid.ns_streets) {
      const th = document.createElement('th');
      th.className = 'grid-head-col';
      // 主要な通りを強調して、実際の京都の街の見え方に近づける
      if (street.major) th.classList.add('is-major');
      th.setAttribute('scope', 'col');
      th.textContent = street.name;
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');

    for (const ewStreet of grid.ew_streets) {
      const ewIndex = ewStreet.index;
      const tr = document.createElement('tr');
      tr.style.height = `${ewSize[ewIndex]}px`;

      const rowHead = document.createElement('th');
      rowHead.className = 'grid-head-row';
      if (ewStreet.major) rowHead.classList.add('is-major');
      rowHead.setAttribute('scope', 'row');
      rowHead.textContent = ewStreet.name;
      tr.appendChild(rowHead);

      for (const nsStreet of grid.ns_streets) {
        const nsIndex = nsStreet.index;
        const td = document.createElement('td');
        td.className = 'grid-cell';
        // 罫線の太さを通りの実際の幅に合わせる（御池通・堀川通は太く、小路は細く）
        td.style.boxShadow =
          `inset ${lineWeight(nsStreet)}px 0 0 ${lineColor(nsStreet)}, ` +
          `inset 0 ${lineWeight(ewStreet)}px 0 ${lineColor(ewStreet)}`;
        if (inSpotArea.has(key(nsIndex, ewIndex))) td.classList.add('is-spot-area');

        const spotName = spotAt.get(key(nsIndex, ewIndex));
        const label = spotName
          ? `${nsStreet.name} × ${ewStreet.name}（${spotName}）`
          : `${nsStreet.name} × ${ewStreet.name}`;

        if (!exists(nsIndex, ewIndex)) {
          // 存在しない交差点。押せないことが見て分かるようにする
          td.classList.add('is-absent');
          td.setAttribute('aria-label', `${label}（交差点なし）`);
          tr.appendChild(td);
          continue;
        }

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'grid-button';
        button.dataset.ns = nsStreet.id;
        button.dataset.ew = ewStreet.id;
        button.dataset.label = label;

        // 現在地や目的地の表示を外したときに戻す既定の見た目
        const isTower = towerNs === nsIndex && towerEw === ewIndex;
        button.dataset.baseText = isTower ? '塔' : (spotName ? '◉' : '');
        button.title = label;
        if (isTower) {
          button.classList.add('is-tower');
          button.setAttribute('aria-label', `${label}（京都タワー）`);
        } else {
          if (spotName) {
            button.classList.add('is-spot');
            button.dataset.spot = spotName;
          }
          button.setAttribute('aria-label', label);
        }
        button.textContent = button.dataset.baseText;

        button.addEventListener('click', () => selectDestination({ nsIndex, ewIndex }));
        td.appendChild(button);
        cellByKey.set(key(nsIndex, ewIndex), button);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }

    table.appendChild(tbody);

    const scroll = document.createElement('div');
    scroll.className = 'grid-scroll';
    scroll.appendChild(table);

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
    root.appendChild(scroll);
    root.appendChild(legend);

    /** 現在地・目的地の装飾を外して既定の見た目に戻す */
    function resetCell(position) {
      const button = cellAt(position);
      if (!button) return;
      button.classList.remove('is-current', 'is-selected');
      button.disabled = false;
      button.textContent = button.dataset.baseText;
      button.setAttribute('aria-label', button.dataset.label);
    }

    function clearDestination(notify = true) {
      if (!selected) return;
      resetCell(selected);
      selected = null;
      if (notify && onSelect) onSelect(null);
    }

    function selectDestination(position) {
      if (same(position, current)) return;      // 現在地は目的地にできない
      if (same(position, selected)) return;
      clearDestination(false);

      selected = position;
      const button = cellAt(position);
      button.classList.add('is-selected');
      button.textContent = '★';
      button.setAttribute('aria-label', `${button.dataset.label}（目的地）`);

      if (onSelect) onSelect(toIntersection(position));
    }

    /** 現在地を差し替える。セレクタの変更に追従させるために使う */
    function setCurrent(intersection) {
      if (current) resetCell(current);
      current = null;
      if (!intersection) return;

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
      button.textContent = '今';
      button.setAttribute('aria-label', `${button.dataset.label}（現在地）`);
      scrollIntoGrid(button);
    }

    /**
     * 現在地をグリッドの中央に寄せる。
     *
     * scrollIntoView() は親要素も巻き込んでページ全体をスクロールさせ、
     * 同じ画面の上にあるセレクタが視界から外れてしまう。
     * そのためスクロールコンテナだけを動かす。
     */
    function scrollIntoGrid(button) {
      const container = scroll.getBoundingClientRect();
      const target = button.getBoundingClientRect();
      scroll.scrollLeft += (target.left - container.left) - (container.width - target.width) / 2;
      scroll.scrollTop += (target.top - container.top) - (container.height - target.height) / 2;
    }

    /** 観光地チップなど、グリッド外から目的地を指定する */
    function selectAt(intersection) {
      const position = {
        nsIndex: Api.indexOf(intersection.ns),
        ewIndex: Api.indexOf(intersection.ew),
      };
      if (!cellAt(position)) return;
      selectDestination(position);
      scrollIntoGrid(cellAt(position));
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
    };
  }

  return { create };
})();
