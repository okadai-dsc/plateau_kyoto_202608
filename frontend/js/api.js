/**
 * データ取得層。
 *
 * モック ⇄ 実API の切り替えは、このファイル冒頭の USE_MOCK だけで完結する。
 * 他のファイルは Api.* しか呼ばないこと。
 *
 * 契約: docs/API.md
 */
const Api = (() => {
  // ── モックに戻すときはここを true にする。変更箇所はここ1つだけ ──
  const USE_MOCK = false;

  const API_BASE = '/api';
  const MOCK_BASE = '../mock';

  /** street id ("ns-03") から添字を取り出す。id 形式は docs/API.md 2.1 */
  function indexOf(streetId) {
    return parseInt(streetId.split('-')[1], 10);
  }

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`取得に失敗しました (${res.status}): ${url}`);
    return res.json();
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      // エラー形式は docs/API.md 4章
      const message = data && data.message ? data.message : `通信に失敗しました (${res.status})`;
      const err = new Error(message);
      err.code = data && data.error;
      throw err;
    }
    return data;
  }

  /** グリッド定義。起動時に1回だけ呼ぶ。 */
  async function getGrid() {
    return USE_MOCK
      ? getJSON(`${MOCK_BASE}/grid.json`)
      : getJSON(`${API_BASE}/grid`);
  }

  /**
   * 経路を取得する。
   *
   * モックは固定の1組（docs/API.md 3.2 の例）しか持たないため、
   * 選択内容にかかわらず同じ内容が返る。
   * 画面は必ずレスポンスの from / to を正として描画すること。
   */
  async function postRoute(from, to) {
    return USE_MOCK
      ? getJSON(`${MOCK_BASE}/route.json`)
      : postJSON(`${API_BASE}/route`, { from, to });
  }

  /** Google Mapsリンクを、Kyoterの目的地交差点へ変換する。 */
  async function resolveDestination(url) {
    if (USE_MOCK) throw new Error('モックではGoogle Mapsリンクを解決できません');
    return postJSON(`${API_BASE}/resolve-destination`, { url });
  }

  // 到着の答え合わせ（POST /api/arrival）は v1 では使わない。
  // バックエンドには実装が残っているが、画面からは呼ばない。

  return { isMock: USE_MOCK, getGrid, postRoute, resolveDestination, indexOf };
})();
