#!/bin/bash
# 協働の輪を 実物の 30B で試す。llama-server を立てて、頼みを順に投げて、必ず止める（止め忘れない）。
# 使い方: dougu/tameshi_kyoudou.sh "頼み1" "頼み2" …   （run_in_background で呼ぶ）
K=~/LocalAI_mirror; cd "$K/kernel"
"$K/llama-latest/build/bin/llama-server" -m "$K/models/Qwen3-30B-A3B-Q2_K.gguf" -t 6 -ngl 0 -dev none -c 32768 -np 1 -cb -ub 256 \
  --cache-reuse 16 -fa off --reasoning-format none --host 127.0.0.1 --port 8080 > "$K/koukai/dougu/kekka/llama_tameshi.log" 2>&1 &
P=$!; trap 'kill $P 2>/dev/null' EXIT
for i in $(seq 1 60); do curl -sf -m 2 http://127.0.0.1:8080/health >/dev/null && break; sleep 3; done
for q in "$@"; do
  python3 - "$q" <<'PY'
import sys, time, json, glob, os, kyoudou as K
t = time.time(); a = K.kotaeru(sys.argv[1])
f = max(glob.glob("kiroku/*.jsonl"), key=os.path.getmtime)
L = [json.loads(l) for l in open(f)]
te = sum(1 for r in L if r["段階"] == "提案")
print("■", sys.argv[1]); print("  答え:", a[:300].replace("\n", " / ")); print("  手:", te, " 秒:", round(time.time() - t))
for r in L:
    if r["段階"] in ("提案", "無効な出力"):
        print("   ", r["手"], json.dumps(r["内容"].get("操作", r["内容"]), ensure_ascii=False)[:150])
PY
done
