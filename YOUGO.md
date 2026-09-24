# 用語対応表

独自の呼び方を、一般的な日本語・英語と短い説明に対応づけます。意味は repo 内の README と説明文を基にしています。「？」は説明文から意味を一意に決められない語です。

入口は [README.md](README.md)、実験の経緯は [LOG.md](LOG.md) を参照してください。

| この repo の用語 | 一般的な日本語 | English | 説明 |
|---|---|---|---|
| 頭・頭脳 | 言語モデルの重み／ローカル LLM | model weights / local LLM | Qwen など、入力を読み、文章や構造化出力を作るモデル。 |
| カーネル・手下 | ツール実行層 | tool runtime | 決まった用件や道具を選び、検査して実行する仕組み。 |
| 深さ | 推論に使う予算・手数 | reasoning budget / inference steps | この repo では出力トークン上限や呼び出し回数で段階化する設定。 |
| 物差し | 評価用問題集 | evaluation set / benchmark | 正解率などを比べる問題と採点方法。 |
| 段 | 難易度段階 | difficulty tier | 問題を必要な手順数などで分けた区分。 |
| 囮 | ひっかけ情報・無関係情報 | distractor | 問題文に含まれるが、解答に使わない情報。 |
| 門番 | 実行前の許可・安全確認 | permission gate | 操作の種類を見て実行を許す、確認を求める、または止める層。 |
| 協働の輪 | モデルとツールの反復実行 | agent loop | モデルが1手を出し、カーネルが実行・確認し、結果を次の手に渡す流れ。 |
| 部品 | 最小の実行可能な機能 | callable tool / capability | 組み立て役が一つずつ置いて実行・確認する機能単位。 |
| 札 | 発話・用件に対応する登録済み規則 | pattern rule / intent mapping | kernel_ikisaki.py の説明では、言い方と用件・部品を対応させる登録項目。 |
| 部屋 | 隔離された一時実行環境 | sandbox | shigoto.py と kazoeru.py の説明では、コードの書込み先を閉じ、ネットや外部ファイルへの接触を制限する環境。 |
| 探り | 速さの試し測り | probe | 頭脳を立てた後に 短い頼みを1回投げ、読み・書きの t/s を見る（dougu/actions_hakaru.sh）。 |
| 基準比 | 同じ機械での基準との比 | same-runner baseline ratio | 計算機の CPU がジョブごとに違うので、同じ機械で 元の頭脳も測り、実験 ÷ 基準 で読む。 |
| 見た・未見 | 開発に使った／使っていない問題集 | seen / held-out | 見た問題集の伸びは信じず、未見の問題集で確かめる。 |
| 技・技の帳面 | 手順の覚え書き | skill notes / cached procedures | 協働の輪で うまくいった手順を残し、似た頼みで参考にする（kernel/kyoudou.py）。 |
| ふるい | 候補の選別 | screening / filter | dougu/jikken/KEKKA.md の「圧縮のふるい」は、候補を測定し採否を分ける記録。 |
| 直感役 | 早い用件判定器 | intent classifier / fast path | chokkan。入力が道具の用件か会話かを判定し、該当する道具へ早く振り分ける役。 |
| 数え上げ | 組合せの列挙・計数 | enumeration / counting | 型が合う問題を Python の決まった計算で解き、モデルに計算を任せない方式。 |
