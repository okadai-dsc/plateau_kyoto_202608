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

    // ── 表の組み立て。本数はデータから取る（ハードコードしない） ──
    const table = document.createElement('table');
    table.className = 'grid';

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    const corner = document.createElement('th');
    corner.className = 'grid-corner';
    corner.setAttribute('scope', 'col');
    headRow.appendChild(corner);

    for (const street of grid.ns_streets) {
      const th = document.createElement('th');
      th.className = 'grid-head-col';
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

      const rowHead = document.createElement('th');
      rowHead.className = 'grid-head-row';
      rowHead.setAttribute('scope', 'row');
      rowHead.textContent = ewStreet.name;
      tr.appendChild(rowHead);

      for (const nsStreet of grid.ns_streets) {
        const nsIndex = nsStreet.index;
        const td = document.createElement('td');
        td.className = 'grid-cell';
        const label = `${nsStreet.name} × ${ewStreet.name}`;

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
        button.dataset.baseText = isTower ? '塔' : '';
        if (isTower) {
          button.classList.add('is-tower');
          button.setAttribute('aria-label', `${label}（京都タワー）`);
        } else {
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
      <li><span class="legend-swatch is-absent"></span>交差点なし</li>
    `;

    root.innerHTML = '';
    root.appendChild(scroll);
    root.appendChild(legend);

    /** 現在地・目的地の装飾を外して既定の見た目に戻す */
    function resetCell(position) {
      const button = cellAt(position);
      if (!button) return;
      button.classList.remove('is-current', 'is-selected');
      button.disabled = false;
      button.textContent = button.dataset.baseText;
      button.setAttribute('aria-label',
        button.dataset.label + (button.dataset.baseText ? '（京都タワー）' : ''));
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

    return {
      setCurrent,
      clearDestination,
      getSelected: () => (selected ? toIntersection(selected) : null),
    };
  }

  return { create };
})();
