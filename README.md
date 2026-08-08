# Kyoter

**地図を見ずに、目的地まで到達する。**

京都の住所システム（上ル / 下ル / 東入ル / 西入ル）そのものをナビゲーション言語として使う。
方角は京都タワーがどちらに見えるかで知る。

> Kyoter = 観光客っぽくなく移動できる。**スマホを見ながら歩かないから。**

企画と仕様は [docs/SPEC.md](docs/SPEC.md) を参照。

## 起動

```bash
python3 -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
./.venv/bin/python -m uvicorn backend.app.main:app --reload
```

→ http://localhost:8000

バックエンドが API と画面の両方を配信する。

## テスト

```bash
./.venv/bin/python -m pytest backend/tests
```

## 構成

```
backend/    Python + FastAPI。経路の分解と京都語の指示文の生成
frontend/   素の HTML / CSS / JS（ビルド不要）
mock/       API のサンプルレスポンス（フロント単体開発用）
tools/      仮データの生成スクリプト
docs/       仕様書
```

| ドキュメント | 内容 |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | 企画・背景・決定事項 |
| [docs/API.md](docs/API.md) | 共通契約（型定義と JSON スキーマ） |
| [docs/BACKEND.md](docs/BACKEND.md) | バックエンド仕様 |
| [docs/FRONTEND.md](docs/FRONTEND.md) | フロントエンド仕様 |

## 現在の状態

通りは**仮名**（縦 `A通`〜`L通` / 横 `1通`〜`16通`）で動いている。
**緯度経度は一切使っていない。**

実データ（PLATEAU 由来）を受け取ったら、以下を差し替えるだけで本番になる。

```
backend/app/data/streets.json   通りの定義
backend/app/data/exists.json    交差点の実在マスク
backend/app/data/visible.json   京都タワーの可視性
```

仮データは `python3 tools/gen_mock.py` で再生成できる。
