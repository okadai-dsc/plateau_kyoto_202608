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

**実際の京都の通りで動いている。**（南北32本 × 東西28本、交差点896・うち実在658）

- 通り名と並び順は通り名数え歌ほかの公開情報に基づく
- 京都御苑・二条城などで途切れる通りも再現している
- 京都タワー = 烏丸通 × 塩小路通
- **緯度経度は一切使っていない**

ただし以下は**まだ仮**であり、実データ（docs/SPEC.md 4.8）で置き換える。

| 項目 | 状態 |
|---|---|
| 通りの延び方（span） | 概算。正確な道路ネットワークデータで置き換える |
| 京都タワー・大文字・稜線の可視性 | 仮。PLATEAU から計算した結果を外部から受け取る |

**方角の手がかりは4層。うち L4「大きい通り」だけは PLATEAU 不要で、現在の実装が最終形。**
（通りに沿った視線は建物に遮られないので、遮蔽計算が要らない）

L4 は「車がよく通っている方角」で気づかせる。歩かせも、標識を読ませもしない。

```
北の方を車がよく通っています。あちらが御池通です。御池通の方が上ルです。
```

| レイヤ | 目印 | 種別 | 実在交差点479のうち |
|---|---|---|---|
| L1 | 京都タワー | 人工物 | 38 (7.9%) |
| L2 | 愛宕山 | 単独峰 | 317 (66.2%) |
| L3 | 大文字 | 単独峰 | 37 (7.7%) |
| L4 | 東山 | 連なり | 74 (15.4%) |
| L5 | 北山 | 連なり | 13 (2.7%) |
| L6-L8 | 比叡山 / 稜線 / 大きい通り | | 0 |
| | 方角が出ない | | 3 (0.6%) |

優先順位は標高ではなく **同定しやすさ順**。単独峰は一点を指せるが、
連なりは方角しか教えてくれないので下位に置き、**個別の山を名指ししない**。

### データの差し替え方

編集するのは1ファイルだけ。

```
tools/kyoto_streets.json    通りの並び順・延び方・タワーの位置
```

```bash
python3 tools/gen_mock.py    # 下記5ファイルを再生成する
```

```
backend/app/data/streets.json   通りの定義
backend/app/data/exists.json    交差点の実在マスク
backend/app/data/visible.json   京都タワーの可視性
mock/grid.json                  APIのサンプル（フロント単体開発用）
mock/route.json
```
