# 滋賀県3フィード 本番化準備 vol.3（未反映）

基準main: `27b1fa1c01f8446074c742cae21d6d697a72fbf2`（2026-11-06確認）。
取得検証: `93fcee58efac0ced4b69ed275d5317548f9a0d27`。
本実装は最新mainへの**追加のみ**。検証ブランチ全体のマージは禁止し、同梱patchの追加ファイルだけを取り込む。
GitHub main反映・Inoreader操作・Excel更新はこの準備作業では行っていない。
準備コードは反映用patchとGit bundleで保持する。準備ブランチへのリモート保存は自動承認審査で却下され、実施していない。

## 437候補の扱いと承認事項

| 初回方式 | 通常RSSに含む初回item | 履歴 | 判断 |
| --- | ---: | --- | --- |
| `full-history` | 284 / 117 / 36、計437 | 全件 | 一括でRSS上の確認対象にできる。初回受信が集中する可能性がある。 |
| `archive-summary` | 各分類の履歴案内1件、計3 | 同じ437件の履歴RSS＋HTML一覧 | **集中回避を優先する場合の推奨**。過去分の確認は一覧で別途必要。 |
| 段階配信（比較のみ） | 仮に合計30件/日なら15回 | 全件をキュー保持 | 復旧記事の配信に時間がかかり、継続監視と混在する。今回は不採用案。 |

2方式のコード・生成例を準備しているが、方式は未決定。
初回はworkflowの`bootstrap_policy`で承認した方式を明示する。既定の`existing`では初期化できない。
以後はstateに記録した方式を継続し、無承認の方式変更・再初期化を拒否する。

`archive-summary`も437候補を削除しない。原本候補は`validation/candidate/`でSHA-256固定。
`archive/*.xml`と`archive/*.html`に全件を保持し、初回以降に初めて検知したURLを通常RSSにも追加する。
本番初回に437候補以外のURLが取得できた場合は、履歴案内3件に加え、その記事も配信する。
過去の日付の新規検知も追加する。単純な日付カットで遡及掲載を落とさない。
これらの件数はRSSのitem数であり、Inoreaderの通知数・全件受信を保証する値ではない。

## 取得期間・識別・分類

- 取得開始日: `2026-09-03`固定。取得終了日: 実行日のAsia/Tokyo日付。毎日全期間を再検索して抜けを抑える。
- 公式検索の分類列を採用。旧「催し」と新「イベント」は完全一致とは扱わない。
- 初回437候補はURL437件一意。新規GUIDは公式URL（isPermaLink=true）。タイトルから旧URL/GUIDを推測変換しない。
- 既存URLのitemはGUID・資料提供日・タイトル・本文ごと保持。再分類時も初回配置を保持して重複配信せず、stateに分類変更を記録する。
- 同一URLの記事訂正は新着通知しない。別URLに移動した同内容記事の自動同一視はしないため、内容重複が残る可能性がある。
- 資料提供日をpubDateに使用し、公式に時刻がないため00:00 JSTを補完。実際の公開時刻や検知時刻とは区別する。
- 履歴案内のGUIDは分類別の固定URN。案内pubDateは初期化日00:00 JSTであることを本文に記載する。
- `boundary-20260902.json`: 前回報告書から引き継いだ9件（お知らせ7・イベント2・募集0）。旧受信との全件照合は未完了。437件に混ぜず保留し、全期間の復旧完了とは扱わない。

旧公式RSSの購読と既存記事は保持する。新規補完フィードの追加なので旧購読のGUID連続性は成立しない。
旧購読と補完記事の内容重複は残り得る。Inoreaderから旧履歴を削除・再登録する手順は含めない。

## 出力先（本番反映後の予定）

| 分類 | 通常購読用RSS | 全件履歴RSS | 閲覧用履歴一覧 |
| --- | --- | --- | --- |
| お知らせ | `support-0205-shiga-notice.xml` | `archive/support-0205-shiga-notice.xml` | `archive/support-0205-shiga-notice.html` |
| イベント | `support-0205-shiga-event.xml` | `archive/support-0205-shiga-event.xml` | `archive/support-0205-shiga-event.html` |
| 募集 | `support-0205-shiga-recruit.xml` | `archive/support-0205-shiga-recruit.xml` | `archive/support-0205-shiga-recruit.html` |

状態ファイルは`support_shiga/state.json`。9つの公開出力をハッシュで結び、欠落・破損を検知する。
通常RSSが空になる出力は作らない。案内方式でも各1件以上ある。

## workflowと競合処理

`.github/workflows/update-support-0205-shiga.yml`は毎日07:17 JSTまたは手動実行。
pushトリガーは持たず、main以外での実行を止める。同一workflowの並行実行を抑制する。
他の自治体workflowの定期実行・権限・コード・RSSは変更しない。

1. 安全性テストを実行。
2. origin/mainをfetchし、そのコミットから一時worktreeを作成。
3. 取得・全ページ・全分類・履歴・GUID・ハッシュを検証して別ディレクトリに全10ファイルを生成。
4. 全件成功した場合だけ出力を一時worktreeへコピー。許可した10ファイルだけで1commitを作成。
5. 通常のfast-forward pushのみ実行。force-push・生成済みファイルのrebaseは行わない。
6. 競合時は新mainから再生成。自治体RSSと他実行が追加した滋賀県記事を保持する。最大3回で停止。
7. 実装そのものがmainで変わっていた場合は古いコードでの更新を止め、最新コードでの再実行を求める。

HTTP失敗、途中ページ失敗、空抽出、分類・件数・日付・URL・ページ送り異常、欠落/破損したstate/RSS、
初期化の途中残骸、保存途中の障害では本番へcommitしない。一時worktree内の途中ファイルは公開されない。
検索は最大100ページ（limit=300）。上限超過は停止し、黙って履歴を切り捨てない。
将来件数が増えたら日付分割取得等を別途検討する。取得中に公式の件数が変動した場合も再実行が必要。

## 承認後の反映手順

1. 最新mainを取得し、同梱patchを`git apply --check`。追加だけであることと、既存自治体RSS/workflowに差分がないことを確認する。
2. patchを適用し、下記28テストとworkflow検査を実行する。先行の検証ブランチ全体はマージしない。
3. 準備コードのみをmainへ反映する。最初のscheduled実行はstate未作成のため初期化できない。
4. 手動workflowで承認した`bootstrap_policy`を選び、`publish=false`で本番環境からの取得・件数を確認する。
5. 同じ方式で`publish=true`を実行。3通常RSS・3履歴RSS・3一覧・stateの1commitを確認する。
6. Pages完了後に予定URLの200・XML・件数・GUID・HTMLリンクを照合する。GITHUB_TOKENによるcommit後にPagesのビルド/デプロイが走るかを実測し、走らなければ公開手順を確認する。自動公開を未検証のまま断定しない。
7. 別途許可された作業として、旧購読を残してInoreaderへ新3本を追加し、緑表示・代表記事/履歴案内・公式リンクを確認する。
8. 9/2の9件と437履歴の業務上の照合が必要。受信・対象範囲確認後に進行管理へ報告し、巡回解除/Excel更新を判断する。

本番環境の新workflow実行・Pages公開・Inoreader受信は今回未実施。
vol.2のActions実取得成功を引き継いでおり、今回の取得元再調査は行っていない。
PagesやInoreaderで未確認の事項は本番反映後の確認項目として残す。

## 再現コマンド（ローカルで本番を書き換えない）

```bash
python3 -m pip install requests==2.34.2 beautifulsoup4==4.15.0 PyYAML==6.0.3
python3 -m unittest discover -s validation -p 'test_shiga_candidate.py' -v
python3 -m unittest discover -s tests/shiga_preparation -v
python3 -m support_shiga.publish --bootstrap-policy archive-summary \
  --today 2026-11-06 --fixtures validation/fixtures --output /tmp/shiga-preview-new
```

出力先は存在しない新規ディレクトリを指定。`--fixtures/--today`は非公開検証専用。
公開モードは日付固定やfixtureを拒否する。通常実行では現在のJST日付を利用する。
検証用bareリポジトリへのpushテストはローカルのみで実施し、実GitHub mainへはpushしない。
