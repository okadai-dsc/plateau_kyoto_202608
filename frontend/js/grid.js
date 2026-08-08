/**
 * 目的地を選ぶグリッドUI（docs/FRONTEND.md 4.2）。
 *
 * 碁盤の目を模した「抽象的な格子」であって地図ではない。
 * 地図ライブラリは使わない。座標も持たない（docs/SPEC.md 4.5）。
 *
 * 行 = ew（横の通り）、列 = ns（縦の通り）。docs/API.md 3.1 の exists と同じ向き。
 */
const GridView = (() => {

  /**
   * @param {HTMLElement} root  描画先
   * @param {object} grid       GET /api/grid のレスポンス
   * @param {object} [options]
   * @param {{ns: string, ew: string} | null} [options.current]  現在地
   * @param {(intersection: {ns: string, ew: string}) => void} [options.onSelect]
   */
  function create(root, grid, options = {}) {
    const { current, onSelect } = options;
    const towerNs = grid.tower ? Api.indexOf(grid.tower.ns) : null;
    const towerEw = grid.tower ? Api.indexOf(grid.tower.ew) : null;

    let selected = null;
    const cellByKey = new Map();
    const key = (nsIndex, ewIndex) => `${nsIndex}:${ewIndex}`;

    const exists = (nsIndex, ewIndex) => Boolean(grid.exists?.[ewIndex]?.[nsIndex]);
    const isCurrent = (nsIndex, ewIndex) =>
      Boolean(current) &&
      Api.indexOf(current.ns) === nsIndex &&
      Api.indexOf(current.ew) === ewIndex;

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
          td.textContent = '';
          tr.appendChild(td);
          continue;
        }

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'grid-button';
        button.dataset.ns = nsStreet.id;
        button.dataset.ew = ewStreet.id;

        if (towerNs === nsIndex && towerEw === ewIndex) {
          button.classList.add('is-tower');
          button.textContent = '塔';
          button.setAttribute('aria-label', `${label}（京都タワー）`);
        } else if (isCurrent(nsIndex, ewIndex)) {
          button.classList.add('is-current');
          button.disabled = true;
          button.textContent = '今';
          button.setAttribute('aria-label', `${label}（現在地）`);
        } else {
          button.setAttribute('aria-label', label);
        }

        button.addEventListener('click', () => select(nsIndex, ewIndex));
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

    function select(nsIndex, ewIndex) {
      if (selected) {
        const previous = cellByKey.get(key(selected.nsIndex, selected.ewIndex));
        if (previous) {
          previous.classList.remove('is-selected');
          if (!previous.classList.contains('is-tower')) previous.textContent = '';
        }
      }
      selected = { nsIndex, ewIndex };
      const button = cellByKey.get(key(nsIndex, ewIndex));
      button.classList.add('is-selected');
      button.textContent = '★';

      if (onSelect) {
        onSelect({
          ns: grid.ns_streets[nsIndex].id,
          ew: grid.ew_streets[ewIndex].id,
        });
      }
    }

    return {
      getSelected() {
        if (!selected) return null;
        return {
          ns: grid.ns_streets[selected.nsIndex].id,
          ew: grid.ew_streets[selected.ewIndex].id,
        };
      },
    };
  }

  return { create };
})();
