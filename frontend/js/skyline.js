/**
 * 方角の目印を「方位帯」に描く（docs/SPEC.md 2.6 の段階A）。
 *
 * 帯の中央が目印の方位。つまり **目印を正面に見た状態** の絵になっていて、
 * 指示文「〇〇を正面に見て、右手が上ルです」とそのまま対応する。
 * 帯のどこに「上ル」が来るかで、体をどちら向きに回せばよいかが分かる。
 *
 * 地図ではない。方位と仰角だけを持つ抽象的な帯。
 */
const Skyline = (() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // 横 1単位 = 1度。帯は全周360度ぶん
  const SPAN = 360;
  const HEIGHT = 108;
  const HORIZON = 84;

  // 山は仰角2〜8度しかないのに角幅は10〜36度ある（docs/SPEC.md 2.6）。
  // そのままの比率だとほぼ平らな線になるので、縦だけ引き伸ばす。
  const EXAGGERATION = 6;

  const CARDINALS = [
    { azimuth: 0, label: '北', up: true },
    { azimuth: 90, label: '東' },
    { azimuth: 180, label: '南' },
    { azimuth: 270, label: '西' },
  ];

  /** 真方位 → 帯の中でのx。目印の方位が中央(SPAN/2)に来る */
  const toX = (azimuth, center) => (azimuth - center + SPAN * 1.5) % SPAN;

  const el = (name, attrs, text) => {
    const node = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs)) {
      node.setAttribute(key, String(value));
    }
    if (text !== undefined) node.textContent = text;
    return node;
  };

  /**
   * @param {HTMLElement} container
   * @param {object|null} landmark  route.start.landmark
   * @returns {boolean} 描けたか（方位が無い目印では描けない）
   */
  function render(container, landmark) {
    container.innerHTML = '';

    const azimuth = landmark?.azimuth;
    const elevation = landmark?.elevation;
    // 稜線や「大きい通り」は方位が度で出ないので帯にできない
    if (typeof azimuth !== 'number' || typeof elevation !== 'number') {
      container.hidden = true;
      return false;
    }

    const svg = el('svg', {
      viewBox: `0 0 ${SPAN} ${HEIGHT}`,
      class: 'skyline-svg',
      // 等比で拡縮する。none にすると文字が横に潰れる
      role: 'img',
      'aria-label':
        `${landmark.name}は方位${Math.round(azimuth)}度、仰角${elevation}度。帯の中央が${landmark.name}です`,
    });

    svg.appendChild(el('rect', {
      x: 0, y: 0, width: SPAN, height: HORIZON, class: 'skyline-sky',
    }));
    svg.appendChild(el('line', {
      x1: 0, y1: HORIZON, x2: SPAN, y2: HORIZON, class: 'skyline-horizon',
    }));

    for (const cardinal of CARDINALS) {
      const x = toX(cardinal.azimuth, azimuth);
      const klass = cardinal.up ? 'skyline-tick is-up' : 'skyline-tick';
      const margin = cardinal.up ? 34 : 10;

      // 端に来たものは反対側にも出す。真後ろの「上ル」が見切れないように
      // （京都タワーが目印＝真南を向くときは必ずこうなる）
      // 折り返し先が帯の外に出るものは描かない。目盛りだけ消えてラベルが
      // 端に取り残される（線の無い幽霊ラベルになる）
      const positions = [x];
      const mirrored = x < SPAN / 2 ? x + SPAN : x - SPAN;
      if (mirrored >= 0 && mirrored <= SPAN) positions.push(mirrored);

      for (const at of positions) {
        svg.appendChild(el('line', {
          x1: at, y1: HORIZON - 10, x2: at, y2: HORIZON + 6, class: klass,
        }));
        svg.appendChild(el('text', {
          x: Math.min(Math.max(at, margin), SPAN - margin),
          y: HEIGHT - 6,
          class: cardinal.up ? 'skyline-label is-up' : 'skyline-label',
        }, cardinal.up ? `${cardinal.label}（上ル）` : cardinal.label));
      }
    }

    // 目印の形（docs/SPEC.md 2.6 段階B）。
    // 見かけの角幅は度で来るので、横1単位=1度の帯にそのまま置ける。
    const peakY = HORIZON - elevation * EXAGGERATION;
    const center = SPAN / 2;
    const width = typeof landmark.angular_width === 'number' ? landmark.angular_width : 0;
    const half = Math.max(width / 2, 4);

    if (landmark.kind === 'range') {
      // 連なりは台形。稜線なので頂点を持たず、肩を落とした形にする
      const shoulder = Math.min(half * 0.35, 18);
      svg.appendChild(el('polygon', {
        points: [
          `${center - half},${HORIZON}`,
          `${center - half + shoulder},${peakY}`,
          `${center + half - shoulder},${peakY}`,
          `${center + half},${HORIZON}`,
        ].join(' '),
        class: 'skyline-mark is-range',
      }));
    } else if (landmark.kind === 'peak') {
      svg.appendChild(el('polygon', {
        points: `${center - half},${HORIZON} ${center},${peakY} ${center + half},${HORIZON}`,
        class: 'skyline-mark',
      }));
    } else {
      // 人工物（京都タワー）は細い縦棒
      svg.appendChild(el('rect', {
        x: center - 3, y: peakY, width: 6, height: HORIZON - peakY, class: 'skyline-mark',
      }));
    }
    svg.appendChild(el('text', {
      x: center, y: Math.max(peakY - 5, 11), class: 'skyline-name',
    }, landmark.name));

    container.appendChild(svg);

    const note = document.createElement('p');
    note.className = 'skyline-note';
    const widthText = width ? ` / 幅${Math.round(width)}°` : '';
    note.textContent =
      `方位${Math.round(azimuth)}° / 仰角${elevation}°${widthText}`
      + `（高さは${EXAGGERATION}倍に強調）`;
    container.appendChild(note);

    container.hidden = false;
    return true;
  }

  return { render };
})();
