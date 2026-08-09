/**
 * その交差点に立って目印の方を見た景色（docs/SPEC.md 2.6 段階C）。
 *
 * PLATEAU の建物(LOD1)を目線1.5mから透視投影した線画。
 * 「東に山が見えます」だけでは三方が山の京都では絞れないので、
 * **形を見せて実景と一致させてもらう**。
 *
 * 線画は目印が一点として定まる交差点にしか無い。
 * 無いときは文章の指示だけになる（Skyline は使わない）。
 */
const Scene = (() => {
  /**
   * @param {HTMLElement} container
   * @param {object|null} scene  route.start.scene
   * @returns {boolean} 描けたか
   */
  function render(container, scene) {
    container.innerHTML = '';
    if (!scene?.url) {
      container.hidden = true;
      return false;
    }

    const figure = document.createElement('figure');
    figure.className = 'scene-figure';

    const image = document.createElement('img');
    image.className = 'scene-image';
    image.src = scene.url;
    image.alt = `${scene.name}の方（方位${scene.azimuth}度）を向いたときの景色`;
    image.loading = 'eager';
    image.decoding = 'async';
    figure.appendChild(image);

    const caption = document.createElement('figcaption');
    caption.className = 'scene-caption';
    caption.textContent = `${scene.name}の方を向くと、この景色になります`;
    figure.appendChild(caption);

    container.appendChild(figure);
    container.hidden = false;
    return true;
  }

  return { render };
})();
