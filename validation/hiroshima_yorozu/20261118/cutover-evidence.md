# 0298 広島県よろず支援拠点 初回配信照合

2026年11月18日（JST）時点。検証コミット `5fbf4d0b61186ef3c78bc59a51337063a0e1b9a3` の77件に、本番反映直前に掲載されたWP 932を追加した78件。進行管理で初回配信28件、履歴保全50件、判断保留0件を承認済み。

## 照合範囲と判断

- 旧Inoreader購読の「全ての記事」に表示された履歴15件を、最終行まで確認した。旧購読で受信を確認した同一記事は2件（WP 799・668）。別ページの同一催事が1件（WP 817）。保存期間より前の履歴や他の購読からの受信は照合範囲外。
- 旧RSSには一般のお知らせ、セミナー・支援策・募集の案内と事例記事が含まれていた。新方式では公式のお知らせ一覧を監視し、主催セミナー・出張相談会とマンツーマン勉強会の個別募集も直接監視する。旧購読に今回の候補が現れないことだけを根拠に初回配信する判断はしていない。
- 初回配信対象は、受付中で今後の日程がある募集と、利用・予約や相談に影響する案内を選んだ。今後の日程があっても公式で満員の募集は履歴扱い。終了・締切済み、続報で置き換わった経過、過去の一般周知、旧受信確認済みは履歴に保全する。
- 勉強会14件は公式一覧の最新表示で今後の日程と受付中表示を確認した。すでに掲載済みのページで日程が更新される例がある。現行実装は同じWordPress IDの日程更新を新着扱いしないため、今回の有効な募集を初回に載せる。
- `review` は0件。反映直前に対象GUIDの差分と、初回配信候補の受付、開催日、締切、後継告知を確認する。特に11/23締切と11/24以降の募集を優先して確認する。

| 区分 | publish | history | review |
| --- | ---: | ---: | ---: |
| お知らせ | 6 | 20 | 0 |
| セミナー・出張相談会 | 8 | 30 | 0 |
| マンツーマン勉強会 | 14 | 0 | 0 |
| 合計 | 28 | 50 | 0 |

募集状況は [セミナー一覧](https://www.yorozu-hiroshima.go.jp/onestop/seminar/)、[勉強会一覧](https://www.yorozu-hiroshima.go.jp/onestop/1on1/)（2ページ）、各記事の公式ページで確認した。外部主催の申込期限は [広島県](https://www.pref.hiroshima.lg.jp/soshiki/70/jigyousyoukei08.html) と [呉市](https://www.city.kure.lg.jp/soshiki/40/tinnageouen08.html) の案内を参照した。

## 記事ごとの判定

WP欄は `urn:hiroshima-yorozu:wp:<ID>` の末尾。

### お知らせ

| WP | 公式記事 | 結果 | 根拠 |
| ---: | --- | --- | --- |
| 932 | [【開催報告】11月15日「よろずマルシェ＠尾道駅前芝生広場」ご来場ありがとうございました！](https://www.yorozu-hiroshima.go.jp/news/2026marche-closing-report-onomichi/) | `history` | 11/18 14:43 JST掲載。11/15に終了した催事の開催報告。進行管理で履歴保全を承認。 |
| 928 | [メール配信サービスにおける不正アクセス事案に関するご報告及び配信再開について](https://www.yorozu-hiroshima.go.jp/news/%E3%83%A1%E3%83%BC%E3%83%AB%E9%85%8D%E4%BF%A1%E3%82%B5%E3%83%BC%E3%83%93%E3%82%B9%E3%81%AB%E3%81%8A%E3%81%91%E3%82%8B%E4%B8%8D%E6%AD%A3%E3%82%A2%E3%82%AF%E3%82%BB%E3%82%B9%E4%BA%8B%E6%A1%88%E3%81%AB/) | `publish` | 11/16の最終報告とメールマガジン配信再開。10月の経過報告は履歴保全。 |
| 926 | [相談時間変更のお知らせ（令和８年12月１日以降）](https://www.yorozu-hiroshima.go.jp/news/20261116/) | `publish` | 12/1から相談時間が変わる。今後の相談予約に影響。 |
| 923 | [HP申込フォーム利用再開のお知らせ](https://www.yorozu-hiroshima.go.jp/news/hp%E7%94%B3%E8%BE%BC%E3%83%95%E3%82%A9%E3%83%BC%E3%83%A0%E5%88%A9%E7%94%A8%E5%86%8D%E9%96%8B%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B/) | `publish` | 11/16に申込フォームが復旧。障害中の申込者には受付確認が必要な場合がある。 |
| 889 | [「よろずマルシェ」開催のお知らせ【2026年11月15日（日）尾道駅前芝生広場】](https://www.yorozu-hiroshima.go.jp/news/notice-of-marche-cancellation/) | `history` | 11/15開催分の当日案内。開催日経過。 |
| 919 | [HP申込フォーム一次利用停止のお知らせ　11月13日（金）17時15分時点](https://www.yorozu-hiroshima.go.jp/news/hp%E7%94%B3%E8%BE%BC%E3%83%95%E3%82%A9%E3%83%BC%E3%83%A0%E4%B8%80%E6%AC%A1%E5%88%A9%E7%94%A8%E5%81%9C%E6%AD%A2%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B%E3%80%8011%E6%9C%8813%E6%97%A5%EF%BC%88/) | `history` | 11/13のフォーム停止経過。11/16の復旧案内（WP 923）で更新済み。 |
| 915 | [HP申込フォーム一次利用停止のお知らせ　11月13日（金）12時00分時点](https://www.yorozu-hiroshima.go.jp/news/hp%E7%94%B3%E8%BE%BC%E3%83%95%E3%82%A9%E3%83%BC%E3%83%A0%E4%B8%80%E6%AC%A1%E5%88%A9%E7%94%A8%E5%81%9C%E6%AD%A2%E3%81%AE%E3%81%8A%E7%9F%A5%E3%82%89%E3%81%9B/) | `history` | 11/13のフォーム停止経過。11/16の復旧案内（WP 923）で更新済み。 |
| 824 | [【2026年11月15日】「よろずマルシェ」を尾道駅前芝生広場にて開催します！](https://www.yorozu-hiroshima.go.jp/news/2026yorozumarche-onomichi/) | `history` | 11/15の尾道開催案内。開催日経過。 |
| 885 | [「次の世代へ、強い会社をつなぐための経営セミナー」のご案内【広島県】](https://www.yorozu-hiroshima.go.jp/news/20261102/) | `publish` | 11/24開催の広島県主催セミナー。11/23申込期限。主催者の案内も確認。 |
| 881 | [メール配信サービスにおける不正アクセス事案に関するご報告【第４報】](https://www.yorozu-hiroshima.go.jp/news/20261028-02/) | `history` | 10/28の途中経過。11/16の最終報告・配信再開（WP 928）を初回配信。 |
| 877 | [「サイバーセキュリティ特別相談窓口」を設置しました](https://www.yorozu-hiroshima.go.jp/news/20261028/) | `publish` | 相談対象者と連絡先を示す拠点の特別相談窓口開設。申込・相談行動につながる案内。 |
| 873 | [メール配信サービスにおける不正アクセス事案に関するご報告【第３報】](https://www.yorozu-hiroshima.go.jp/news/20261026/) | `history` | 10/26の途中経過。11/16の最終報告・配信再開（WP 928）を初回配信。 |
| 864 | [メール配信サービスにおける不正アクセス事案に関するご報告【第２報】](https://www.yorozu-hiroshima.go.jp/news/20261023/) | `history` | 10/23の途中経過。11/16の最終報告・配信再開（WP 928）を初回配信。 |
| 863 | [メール配信サービスにおける不正アクセス事案に関するお詫びとお知らせ（注意喚起）](https://www.yorozu-hiroshima.go.jp/news/20261022/) | `history` | 10/22の初報。11/16の最終報告・配信再開（WP 928）を初回配信。 |
| 843 | [中国地域M&A・事業承継フォーラムのご案内【中小企業庁・中国経済産業局】](https://www.yorozu-hiroshima.go.jp/news/20261016/) | `history` | 11/9開催・11/5締切の事業承継フォーラム。主催案内で開催日経過を確認。 |
| 830 | [【開催報告】10月11日「よろずマルシェ＠シャレオ中央広場」ご来場ありがとうございました！](https://www.yorozu-hiroshima.go.jp/news/2026marche-closing-report-shareo/) | `history` | 10/11開催分の事後報告。 |
| 799 | [「求人票で差をつける具体的テクニックと生成AIを使ったワークショップ」開催について](https://www.yorozu-hiroshima.go.jp/news/news-20260907/) | `history` | 旧購読で受信確認。旧新でタイトル、記事スラッグ、共催者と本文が一致。新サイトの掲載日表示には差がある。 |
| 785 | [令和８年度 取引適正化・価格転嫁促進セミナーのご案内【広島県】](https://www.yorozu-hiroshima.go.jp/news/20261006/) | `history` | 11/11開催・11/4申込締切。開催日経過。 |
| 779 | [【中小企業庁】賃上げ・最低賃金対応支援特設サイト「ミラサポplus」について](https://www.yorozu-hiroshima.go.jp/news/mirasapo-plus/) | `history` | 国の支援情報をまとめた常設サイトへの案内。旧受信の賃上げ支援記事とは別記事として扱い、初回通知は見送る。 |
| 763 | [【2026年10月11日】「よろずマルシェ」を紙屋町シャレオ中央広場にて開催します！](https://www.yorozu-hiroshima.go.jp/news/2026yorozumarche-shareo/) | `history` | 10/11の紙屋町開催案内。開催日経過。 |
| 151 | [ホームページリニューアルのお知らせ](https://www.yorozu-hiroshima.go.jp/news/homepage-renewal-2026/) | `history` | 10/1のリニューアル完了案内。旧購読で確認した事前メンテナンス告知とは別記事。 |
| 766 | [飲食料品の消費税率引下げに関する対応・支援について](https://www.yorozu-hiroshima.go.jp/news/news-20260930/) | `history` | 9/30掲載の制度対応の概説。補助制度は本文で予定として案内されており、初回通知は見送る。 |
| 758 | [食品寄附マッチングシステム「ひろしま食マッチ」のご紹介【広島市】](https://www.yorozu-hiroshima.go.jp/news/news-20260929/) | `history` | 9/29掲載の常設マッチングサービス紹介。初回通知は見送る。 |
| 676 | [呉市中小企業等賃上げ応援奨励金のご案内【呉市】](https://www.yorozu-hiroshima.go.jp/news/news-20260928/) | `publish` | 呉市奨励金の申請期間中。呉市公式の申請期限は12/28。 |
| 668 | [NEWS!「よろずマルシェ〜あなたが育てる！未来のヒット商品〜」開催！ぜひご来場ください！](https://www.yorozu-hiroshima.go.jp/news/2026yorozumarche/) | `history` | 旧購読で受信確認。URLは変わったが、固有のタイトルと本文の導入が一致。 |
| 37 | [実践よろず塾「よろずマルシェ」出店者募集！](https://www.yorozu-hiroshima.go.jp/news/marche2026/) | `history` | マルシェ出店者募集。7/31の応募期限経過。 |

### セミナー・出張相談会

| WP | 公式記事 | 結果 | 根拠 |
| ---: | --- | --- | --- |
| 865 | [11/18（水）【満席】尾道しまなみ商工会出張相談会](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261118-onomichi-shimanami/) | `history` | 11/18開催。公式で満員・受付終了。 |
| 871 | [11/19（木）14：00～登録者5万人超の現役YouTuberコーディネーターが教える　これならできる！ YouTube超入門＆実践活用術](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261119-imagawa/) | `history` | 11/19開催。公式で満員。 |
| 870 | [11/24（火）【満席】因島商工会議所出張相談会](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261124-innoshima/) | `history` | 11/24開催。公式で満員・受付終了。 |
| 904 | [11/25（水）13:00～無駄な広報をしない秘訣伝えます](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261125-oki/) | `publish` | 11/25開催。公式で受付中。 |
| 883 | [11/26（木）10：00～ 24時間稼働を捨て定時へ！製造業の生産性向上法](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261126-yamamoto/) | `publish` | 11/26開催。公式で受付中。2一覧に掲載された同一GUID。 |
| 930 | [11/26（木）13:00～BCPは「防災」だけではない！会社を守る事業継続計画のつくり方](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261126-kinoshita/) | `publish` | 11/26開催。公式で受付中。 |
| 910 | [11/30（月）10:00～中小企業のセキュリティ対策](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261130-seto/) | `publish` | 11/30開催。公式で受付中。 |
| 850 | [11/30（月）13:30～Instagram✕AI✕Canva✕Edits ショート動画セミナー](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261130-mototani/) | `history` | 11/30開催。公式で満員。 |
| 701 | [12/2（水）15：00～伝わる・繋がる 広告デザインの構造](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261202-akizaki/) | `publish` | 12/2開催。公式で受付中。 |
| 908 | [12/8（火）13:00～Canvaで作る売れるチラシとLP](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261208-oki/) | `publish` | 12/8開催。公式で受付中。 |
| 909 | [12/16（水）9:30～売れるWebマーケティング](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261216-oki/) | `publish` | 12/16開催。公式で受付中。 |
| 913 | [12/16（水）13:30～Muse爆誕！MetaのAIエージェントでSNS運用を効率化](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261216-mototani/) | `publish` | 12/16開催。公式で受付中。 |
| 839 | [11/12（木）13:00～現役アナウンサーが語る プレスリリース入門セミナー](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261112-kanbara/) | `history` | 11/12開催。開催日経過。 |
| 852 | [11/10（火）東広島商工会議所出張相談会](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261110-higashihiroshima/) | `history` | 11/10開催。開催日経過。 |
| 828 | [11/9（月）10:00～成功事例に学ぶ 生産性向上・DX](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261109-takagake/) | `history` | 11/9開催。開催日経過。 |
| 817 | [10/29（木）10:00～求人票で差をつける具体的テクニックと生成AIを使ったワークショップ](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261029-hielcc/) | `history` | 10/29開催。開催日経過。WP 799および旧購読の記事と同じ10/29の催事。新サイト上では別記事。 |
| 829 | [10/28（水）13:30～そもそもスキルって何？Claudeスキル入門](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261028-shimatani/) | `history` | 10/28開催。開催日経過。 |
| 459 | [10/22（木）13:30～CanvaAI×ChatGPT 活用](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261022-mototani/) | `history` | 10/22開催。開催日経過。 |
| 777 | [10/21（水）13:30～今日から始める！SNSブランディング基本の「き」](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261021-akizaki/) | `history` | 10/21開催。開催日経過。 |
| 775 | [10/19（月）13:30～今さら聞けない！Claudeの基本的な使い方](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261019-shimatani/) | `history` | 10/19開催。開催日経過。 |
| 791 | [10/16（金）10:30～カラーでブランディング！色彩のトン・マナ活用](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261016-matsuura/) | `history` | 10/16開催。開催日経過。 |
| 463 | [10/14（水）【満席】因島商工会議所出張相談会](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261014-innoshima/) | `history` | 10/14開催。開催日経過。 |
| 702 | [10/13（火）東広島商工会議所出張相談会](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261013-higashihiroshima/) | `history` | 10/13開催。開催日経過。 |
| 688 | [10/9（金）10：00～実例に学ぶDX 「製造業の生産性向上」のヒント](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261009-yamamoto/) | `history` | 10/9開催。開催日経過。 |
| 465 | [10/8（木）【満席】尾道しまなみ商工会出張相談会](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261008-onomichi-shimanami/) | `history` | 10/8開催。開催日経過。 |
| 640 | [10/2（金）10:30～ターゲットに届く！インスタグラム求人広告入門](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261002-matsuura/) | `history` | 10/2開催。開催日経過。 |
| 467 | [10/1（木）13:30～スマホでできる！商品写真の撮り方](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20261001-akizaki/) | `history` | 10/1開催。開催日経過。 |
| 469 | [9/30（水）13:30～結局どれを使えばいい？自社に合うAIの選び方](https://www.yorozu-hiroshima.go.jp/onestop/seminar/20260930-shimatani/) | `history` | 9/30開催。開催日経過。 |
| 471 | [9/28(月)9:00～売れるチラシ作成法！デモンストレーションあり！](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-28%E6%9C%889%EF%BC%9A00%EF%BD%9E%E5%A3%B2%E3%82%8C%E3%82%8B%E3%83%81%E3%83%A9%E3%82%B7%E4%BD%9C%E6%88%90%E6%B3%95%EF%BC%81%E3%83%87%E3%83%A2%E3%83%B3%E3%82%B9%E3%83%88%E3%83%AC%E3%83%BC%E3%82%B7/) | `history` | 9/28開催。開催日経過。 |
| 473 | [9/25（金）13:30〜紙1枚で事業を整理するリーンキャンバス入門](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-25%EF%BC%88%E9%87%91%EF%BC%8913%EF%BC%9A30%E3%80%9C%E7%B4%991%E6%9E%9A%E3%81%A7%E4%BA%8B%E6%A5%AD%E3%82%92%E6%95%B4%E7%90%86%E3%81%99%E3%82%8B%E3%83%AA%E3%83%BC%E3%83%B3%E3%82%AD%E3%83%A3%E3%83%B3/) | `history` | 9/25開催。開催日経過。 |
| 475 | [9/25（金）9:00～はじめてのCanvaセミナー](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-25%EF%BC%88%E9%87%91%EF%BC%899%EF%BC%9A00%EF%BD%9E%E3%81%AF%E3%81%98%E3%82%81%E3%81%A6%E3%81%AEcanva%E3%82%BB%E3%83%9F%E3%83%8A%E3%83%BC/) | `history` | 9/25開催。開催日経過。 |
| 477 | [9/24（木）13:00～現役アナウンサーが語る プレスリリース入門セミナー](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-24%EF%BC%88%E6%9C%A8%EF%BC%89-13%EF%BC%9A00%EF%BD%9E%E7%8F%BE%E5%BD%B9%E3%82%A2%E3%83%8A%E3%82%A6%E3%83%B3%E3%82%B5%E3%83%BC%E3%81%8C%E8%AA%9E%E3%82%8B-%E3%83%97%E3%83%AC%E3%82%B9%E3%83%AA%E3%83%AA/) | `history` | 9/24開催。開催日経過。 |
| 479 | [9/18（金）10:30～選ばれる食品商談会シート作成セミナー](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-18%EF%BC%88%E9%87%91%EF%BC%8910%EF%BC%9A30%EF%BD%9E%E9%81%B8%E3%81%B0%E3%82%8C%E3%82%8B%E9%A3%9F%E5%93%81%E5%95%86%E8%AB%87%E4%BC%9A%E3%82%B7%E3%83%BC%E3%83%88%E4%BD%9C%E6%88%90%E3%82%BB%E3%83%9F/) | `history` | 9/18開催。開催日経過。 |
| 481 | [9/16（水）13:30～情報整理が変わる！NotebookLM活用術](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-16%EF%BC%88%E6%B0%B4%EF%BC%8913%EF%BC%9A30%EF%BD%9E%E6%83%85%E5%A0%B1%E6%95%B4%E7%90%86%E3%81%8C%E5%A4%89%E3%82%8F%E3%82%8B%EF%BC%81notebooklm%E6%B4%BB%E7%94%A8%E8%A1%93/) | `history` | 9/16開催。開催日経過。 |
| 483 | [9/15（火）【満席】因島商工会議所出張相談会](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-15%EF%BC%88%E7%81%AB%EF%BC%89%E3%80%90%E6%BA%80%E5%B8%AD%E3%80%91%E5%9B%A0%E5%B3%B6%E5%95%86%E5%B7%A5%E4%BC%9A%E8%AD%B0%E6%89%80%E5%87%BA%E5%BC%B5%E7%9B%B8%E8%AB%87%E4%BC%9A/) | `history` | 9/15開催。開催日経過。 |
| 485 | [9/10（木）13:30～Instagram✕AI✕Canva✕Edits](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-10%EF%BC%88%E6%9C%A8%EF%BC%8913%EF%BC%9A30%EF%BD%9Einstagram%E2%9C%95ai%E2%9C%95canva%E2%9C%95edits/) | `history` | 9/10開催。開催日経過。 |
| 394 | [9/3（木）「業務改善助成金」自主申請セミナー](https://www.yorozu-hiroshima.go.jp/onestop/seminar/9-3%EF%BC%88%E6%9C%A8%EF%BC%8913%EF%BC%9A30%EF%BD%9E%E3%80%8C%E6%A5%AD%E5%8B%99%E6%94%B9%E5%96%84%E5%8A%A9%E6%88%90%E9%87%91%E3%80%8D%E8%87%AA%E4%B8%BB%E7%94%B3%E8%AB%8B%E3%82%BB%E3%83%9F%E3%83%8A/) | `history` | 9/3開催。開催日経過。 |
| 626 | [10/23（金）14:00～AIと4Sで無駄を利益に変える生産性向上](https://www.yorozu-hiroshima.go.jp/productivity/seminar/20261023-tanakam/) | `history` | 10/23開催。開催日経過。 |

### マンツーマン勉強会

| WP | 公式記事 | 結果 | 根拠 |
| ---: | --- | --- | --- |
| 410 | [『お金のブロックパズル』入門](https://www.yorozu-hiroshima.go.jp/onestop/1on1/%E3%80%8E%E3%81%8A%E9%87%91%E3%81%AE%E3%83%96%E3%83%AD%E3%83%83%E3%82%AF%E3%83%91%E3%82%BA%E3%83%AB%E3%80%8F%E5%85%A5%E9%96%80/) | `publish` | 公式一覧で受付中。表示日程は11/25・26・30。 |
| 431 | [ゼロから学ぶ　民泊スタート講座](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-minpaku2026/) | `publish` | 公式一覧で受付中。表示日程は11/24、12/1・8・15。 |
| 432 | [利益が出た時のお金の考え方](https://www.yorozu-hiroshima.go.jp/onestop/1on1/hidaka-one-on-one-okane2026/) | `publish` | 公式一覧で受付中。表示日程は11/24、12/1・8・15。 |
| 433 | [うちは対象？１時間でわかる補助金と助成金の“超きほん”](https://www.yorozu-hiroshima.go.jp/onestop/1on1/hidaka-one-on-one2026/) | `publish` | 公式一覧で受付中。表示日程は11/24、12/1・8・15。 |
| 429 | [小さく始める事業づくり塾](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-motoki2026-business/) | `publish` | 公式一覧で受付中。表示日程は12/2・3・15・23。 |
| 427 | [ChatGPTを活用し、収益アップのための新規事業を一緒に考えてみませんか](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-motoki2026-ai1/) | `publish` | 公式一覧で受付中。表示日程は12/2・3・15・23。 |
| 424 | [経営戦略の“棚卸しと再構築”を一緒に考えてみませんか](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-motoki2026-ai2/) | `publish` | 公式一覧で受付中。表示日程は12/2・3・15・23。 |
| 422 | [利益率UPのための“原価・業務”見直しを一緒に考えてみませんか](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-motoki2026-ai3/) | `publish` | 公式一覧で受付中。表示日程は12/2・3・15・23。 |
| 818 | [AIに任せる仕事が見つかる！業務棚卸し1on1](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-shimatani/) | `publish` | 公式一覧で受付中。表示日程は12/8・14・23。 |
| 418 | [「万年人手不足」から脱却！業務効率化の1on1勉強会](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-tamura/) | `publish` | 公式一覧で受付中。表示日程は11/25。 |
| 420 | [面倒な手入力から解放！伝票のAI自動データ化体験](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-tamura-ai/) | `publish` | 公式一覧で受付中。表示日程は11/25。 |
| 416 | [思い悩む時間をゼロに　 マンツーマン資金繰り勉強会](https://www.yorozu-hiroshima.go.jp/onestop/1on1/one-on-one-ueno2026/) | `publish` | 公式一覧で受付中。表示日程は12/3・25。 |
| 414 | [経営判断としての退職勧奨　ー事業者が知るべき実務と注意点ー](https://www.yorozu-hiroshima.go.jp/onestop/1on1/%E7%B5%8C%E5%96%B6%E5%88%A4%E6%96%AD%E3%81%A8%E3%81%97%E3%81%A6%E3%81%AE%E9%80%80%E8%81%B7%E5%8B%A7%E5%A5%A8%E3%80%80%E3%83%BC%E4%BA%8B%E6%A5%AD%E8%80%85%E3%81%8C%E7%9F%A5%E3%82%8B%E3%81%B9%E3%81%8D/) | `publish` | 公式一覧で受付中。表示日程は12/9、2027/1/13。 |
| 412 | [あなたのファンを作る！SNSアカウント即時添削＆クロージング強化！商談ロープレ](https://www.yorozu-hiroshima.go.jp/onestop/1on1/%E3%81%82%E3%81%AA%E3%81%9F%E3%81%AE%E3%83%95%E3%82%A1%E3%83%B3%E3%82%92%E4%BD%9C%E3%82%8B%EF%BC%81sns%E3%82%A2%E3%82%AB%E3%82%A6%E3%83%B3%E3%83%88%E5%8D%B3%E6%99%82%E6%B7%BB%E5%89%8A%EF%BC%86/) | `publish` | 公式一覧で受付中。表示日程は12/10・17。 |
