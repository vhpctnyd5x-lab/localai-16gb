#!/bin/bash
# 深さ0 が難しい方（6段・7段）でどこを落とすかを測り、落とした問いだけ 深さ2 で測り直す（おまかせの決め方の検証用）。
# 前の測定（llama-server）が終わるのを待ってから始める。
cd "$(dirname "$0")"
for i in $(seq 1 720); do pgrep -f "[l]lama-server -m" >/dev/null || break; sleep 10; done
for dan in 6dan 7dan; do
  ./hashiru_fukasa120.sh 0 --mondai ../monosashi/mondai_$dan.jsonl
  /usr/local/bin/python3 - "$dan" <<'PY'
import json, sys
dan = sys.argv[1]
ochi = {r["id"] for r in json.load(open("kekka/fukasa%s_f0.json" % dan, encoding="utf-8"))["一件ずつ"] if not r["○"]}
rows = [l for l in open("../monosashi/mondai_%s.jsonl" % dan, encoding="utf-8") if l.strip() and json.loads(l)["id"] in ochi]
open("kekka/mondai_%s_ochi.jsonl" % dan, "w", encoding="utf-8").writelines(rows)
print("深さ0 が落とした %d 問を kekka/mondai_%s_ochi.jsonl に" % (len(rows), dan))
PY
  [ -s kekka/mondai_${dan}_ochi.jsonl ] && ./hashiru_fukasa120.sh 2 --mondai kekka/mondai_${dan}_ochi.jsonl
done
echo "===== 6段・7段 おわり $(date +%T) ====="
