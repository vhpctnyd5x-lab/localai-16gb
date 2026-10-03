# ダンプから知識の箱を作る

作成だけ。Cloud起動・課金・削除・手元への転送はClaudeが本人の承認を得てから行う。kernel変更・commit・pushはしない。

## 手順

1. `bash gcloud/chishiki/hajimeru.sh`（起動したら手を離す）→ `bash gcloud/chishiki/mimamoru.sh ~/.cache/chishiki-gcp/<RUN_ID>.env` を裏で（止めても何も消さない。呼び直せば続きから。終わりに SA・IAM を片付ける）。gcloudの既定プロジェクトを使用。e2-standard-8 Spot、32GiBメモリ、100GB pd-standard、us-central1-a、最大12時間。完了または失敗まで前で待つ。Spot中断を成功扱いにしない。
2. 表示されたGCSの実行別フォルダから、承認後に `chishiki.sqlite3`・`chishiki.sha256`・`chishiki.json` を同じフォルダへ取得。`shasum -a 256 -c chishiki.sha256` をそのフォルダで実行。
3. Python **3.11以上**の仮想環境で `pip install -r gcloud/chishiki/requirements.txt`。
4. `python gcloud/chishiki/torikomu.py 保存先/chishiki.sqlite3 --dry-run`。
5. `python gcloud/chishiki/torikomu.py 保存先/chishiki.sqlite3`。既定の先は `~/Library/Application Support/kernel-ai/gakushuu/chishiki.sqlite3`。別の箱は `--target パス`。取り込み中はSQLiteの書き込みロックを保持するため、学習の書き込みと同時に走らせない。

Cloud SDK、課金設定、Compute/IAM/Storage APIを有効化できる権限、VM・バケット・サービスアカウント・カスタムロールの作成とIAM付与の権限、SAの利用権限が必要。defaultネットワークを使用するため、defaultネットワークがないプロジェクトでは作成台本のネットワーク指定を変える。

バケットは非公開・STANDARD・VMと同じリージョンに作る。既存バケットなら `BUCKET=名前` で指定。専用SAはそのバケットのオブジェクト操作と自分のVMの削除だけ。終わりにVM消失を確認してSA/IAM付与を片付ける。custom roleとバケット・成果物は残る。既存の同名custom roleに権限を足したり変更したりしない。

## 変換と互換性

- `fetch.py` は公式 `latest/dumpstatus.json` の**完成済み** pages-articles を選ぶ。結合版がなければ分割版を全て取得。日付付きURLで固定し、size/SHA1を照合。最新が未完成なら止める（以前の月へ勝手に切り替えない）。bz2を伸ばさずXMLを逐次読む。
- namespace 0、転送ではない記事を対象。Wikipediaだけ、平文化した本文2000 UTF-8バイト以上、一覧・曖昧さ回避・数字の年号だけ・`kernel/gakushuu.py`の`_TRIVIA`17語を含む題を除く。300,000件を固定seedの一様抽出にする。抽出は知識分野の均等配分ではない。
- テンプレート・表・ref・参照節・ファイル/カテゴリを除去。`mwparserfromhell`使用。最大8000字。Wikibooks/Wikisourceは同じ平文化、Wikipediaの長さ/雑学フィルタは適用しない。青空文庫はUTF-8またはcp932を厳密に復号し、ルビ・編集注・凡例・末尾の底本欄を落とす。
- 題は完全一致で一意。順番はWikipedia→Wikibooks→Wikisource→青空文庫。異なる出どころの同題作品も一つになる（指定どおり）。各記事のURL、出どころ、取り込み日時を残す。ダンプのmetadataと青空文庫のGit commitもGCSへ保存。
- `chishiki` 自体を既存どおりFTS5にし、`chishiki_trigram`を同じrowidで維持。`tsunagari(moto,saki,shurui)` の本文/リンク枝を保存。本文枝はcasefold部分一致をAho–Corasickで一括照合（既存の総当たりを30万回呼ばない）。`枝再構築=1` を保存して起動時の総当たりを防ぐ。枝の行数はデータ次第で大きくなる。
- 取り込みは先にSQLite backupで控えを取り、本文・trigram・枝を**一つのトランザクション**で追加。既存の本文・リンクを上書きしない。旧→新と新→旧の本文枝も追加。途中終了はrollback／journal recovery、再実行は同題を省略。控えは取り込み先の隣に残す。`--dry-run`は読取専用で題の追加数だけを計算、依存パッケージ・控え・変更は不要。
- 強制終了直後のhot journalは通常取り込みの最初の接続で回復する。回復前の `--dry-run` が読取専用エラーになったら通常取り込みで回復させる。控えも検証後に `.partial` から改名するため、途中の控えを完成品と取り違えない。
- 最終のSQLite/FTS/trigram整合性を確認し、SHA256と件数・枝数・所要秒・バイト数を `chishiki.json` に記録してからアップロード完了扱いにする。

## 費用・時間・容量（大規模未実測）

`hajimeru.sh` の先頭に内訳と料金元を記載。us-central1のSpot参考値は8×$0.00872＋32×$0.001169＝**約$0.107/時**。pd-standard 100GB約$4/月、外部IPv4約$0.005/時、GCS約$0.020/GiB月、日本への転送約$0.12/GiB。Spot価格は変動する。無料枠・税・為替は含めない。

4〜12時間を仮置きして、2〜4GiBなら計約 **$0.8〜2**、6〜15GiBなら **$1.3〜3.5**。一回のSpot完走の見積もりで、やり直しは別。30万件・8000字上限で**2〜4GBに収まる保証はない**（FTSが本文を二重に持ち、索引・枝も加わる）。必要なら `MAX_CHARS=3000` などで上限を下げて測る。100GBの作業ディスクには圧縮ダンプ・青空文庫・途中の箱・最終の箱・SQLite journalが共存し、容量不足なら失敗する。

無料待機ではない。VMの最大時間と起動側の削除を設定。成果物はバケットに残り、例えば15GiBなら約$0.30/月が続く。履歴/soft-delete設定によって古い物の保存料金も続く。自動でバケットを空にしない。

本環境からWikimediaのURLはHTTP 403で、実ダンプの配布metadata・転送速度は未検証。小さなローカル試験だけでは大規模時間・容量・Cloud IAM・Spot供給を実証しない。Spot中断からのcheckpoint再開はなく、承認後に新規実行する。XMLのテンプレートにしかない内容や表は意図的に失われる。

青空文庫には保護期間終了前の許諾作品も含まれる。取得元URLと原典の利用条件は維持する。[取得元の説明](https://github.com/aozorahack/aozorabunko_text)、[Wikimediaダンプ](https://dumps.wikimedia.org/)。

## 手元の試験

`PYTHON=仮想環境/bin/python bash gcloud/chishiki/tamesu.sh`

数記事の自作bz2 XML、cp932/UTF-8の青空見本を一時フォルダに作る。実DBは**読取専用でbackupした一時コピーだけ**に取り込む。4種類の出どころ、フィルタ、8000字、同題保護、trigram検索、両向き枝、控え、dry-run無変更、再実行、割り込みとSIGKILLからの復旧、分割ダンプ、抽出上限を確認。Cloudコマンドは実行しない。
