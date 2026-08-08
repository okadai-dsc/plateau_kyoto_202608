/**
 * 交差点を指定する2セレクタ（docs/FRONTEND.md 4.1）。
 *
 * 英語圏の `5th Ave × 42nd St` と同じ構造。縦の通りと横の通りを別々に選ぶ。
 *
 * 要件:
 *   1. 選択式のみ。自由入力は不可（表記ゆれ・誤字を起こさない）
 *   2. 並び順は index 順。50音順にしない（実際の街の並びと一致させる）
 *   3. 片方を選んだら、もう片方を実在する通りだけに絞る
 */
const IntersectionSelector = (() => {

  /**
   * @param {HTMLElement} root   描画先
   * @param {object} grid        GET /api/grid のレスポンス
   * @param {object} [options]
   * @param {(value: {ns: string, ew: string} | null) => void} [options.onChange]
   * @param {(intersection: {ns: string, ew: string}) => boolean} [options.isSelectable]
   *        追加の選択可否。実在マスクとは別の制約（例: 現在地と同じ交差点を禁止）に使う
   */
  function create(root, grid, options = {}) {
    const { onChange, isSelectable } = options;

    root.innerHTML = `
      <div class="selector">
        <label class="selector-field">
          <span class="selector-label">縦の通り</span>
          <select class="selector-ns"></select>
        </label>
        <span class="selector-cross" aria-hidden="true">×</span>
        <label class="selector-field">
          <span class="selector-label">横の通り</span>
          <select class="selector-ew"></select>
        </label>
      </div>
      <p class="selector-note" role="status"></p>
    `;

    const nsSelect = root.querySelector('.selector-ns');
    const ewSelect = root.querySelector('.selector-ew');
    const note = root.querySelector('.selector-note');

    // 実在マスク: exists[ew_index][ns_index]（docs/API.md 3.1）
    const exists = (nsIndex, ewIndex) => Boolean(grid.exists?.[ewIndex]?.[nsIndex]);

    /** 実在マスクに加えて、呼び出し側の制約も満たすか */
    function allowed(nsIndex, ewIndex) {
      if (!exists(nsIndex, ewIndex)) return false;
      if (!isSelectable) return true;
      return isSelectable({
        ns: grid.ns_streets[nsIndex].id,
        ew: grid.ew_streets[ewIndex].id,
      });
    }

    function fill(select, streets) {
      select.innerHTML = '<option value="">— 選択 —</option>';
      // index 順のまま並べる。並べ替えないこと（要件2）
      for (const street of streets) {
        const option = document.createElement('option');
        option.value = street.id;
        option.textContent = street.name;
        select.appendChild(option);
      }
    }

    fill(nsSelect, grid.ns_streets);
    fill(ewSelect, grid.ew_streets);

    /**
     * 相手のセレクタを、選択済みの通りと実際に交差する通りだけに絞る（要件3）。
     * 選択肢は消さずに disabled にする。位置が動かず、なぜ選べないかも分かるため。
     */
    function applyFilter() {
      const nsId = nsSelect.value;
      const ewId = ewSelect.value;

      for (const option of ewSelect.options) {
        if (!option.value) continue;
        const ewIndex = Api.indexOf(option.value);
        option.disabled = nsId ? !allowed(Api.indexOf(nsId), ewIndex) : false;
      }
      for (const option of nsSelect.options) {
        if (!option.value) continue;
        const nsIndex = Api.indexOf(option.value);
        option.disabled = ewId ? !allowed(nsIndex, Api.indexOf(ewId)) : false;
      }

      // 相手を変えた結果、選択済みの値が無効になった場合は解除する
      let cleared = false;
      if (ewSelect.value && ewSelect.selectedOptions[0]?.disabled) {
        ewSelect.value = '';
        cleared = true;
      }
      if (nsSelect.value && nsSelect.selectedOptions[0]?.disabled) {
        nsSelect.value = '';
        cleared = true;
      }
      note.textContent = cleared
        ? 'その組み合わせの交差点は無いため、選び直してください。'
        : '';
    }

    function getValue() {
      if (!nsSelect.value || !ewSelect.value) return null;
      return { ns: nsSelect.value, ew: ewSelect.value };
    }

    function handleChange() {
      applyFilter();
      if (onChange) onChange(getValue());
    }

    nsSelect.addEventListener('change', handleChange);
    ewSelect.addEventListener('change', handleChange);
    applyFilter();

    return {
      getValue,
      reset() {
        nsSelect.value = '';
        ewSelect.value = '';
        applyFilter();
        if (onChange) onChange(null);
      },
      /** 外部の制約（isSelectable）が変わったときに絞り込みを引き直す */
      refresh: applyFilter,
    };
  }

  return { create };
})();
