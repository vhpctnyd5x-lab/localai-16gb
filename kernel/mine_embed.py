#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mine_embed.py -- 巨大モデルから「単語カードの表」だけを抜き取る

モデル全体(1TB級)は落とさない。safetensors のヘッダを読んで
埋め込みテンソルのバイト位置を突き止め、そこだけを範囲指定で取る。
"""
import urllib.request, urllib.error, json, struct, os, sys, time

def head_range(url, a, b, timeout=60):
    r = urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"})
    return urllib.request.urlopen(r, timeout=timeout).read()

def find_tensor(url, name):
    """ヘッダを読んで、目当てのテンソルの位置と形を返す"""
    n = struct.unpack("<Q", head_range(url, 0, 7))[0]
    hdr = json.loads(head_range(url, 8, 8 + n - 1))
    if name not in hdr:
        raise KeyError(f"{name} が無い。あるのは: {list(hdr)[:5]}...")
    v = hdr[name]
    a, b = v["data_offsets"]
    return dict(start=8 + n + a, end=8 + n + b - 1,
                shape=v["shape"], dtype=v["dtype"], size=b - a)

def fetch(url, start, end, out, chunk=64 * 1024 * 1024):
    """範囲指定で、少しずつ落とす。途中で切れても続きから再開できる"""
    total = end - start + 1
    done = os.path.getsize(out) if os.path.exists(out) else 0
    if done >= total:
        print(f"  すでに取得済み ({done/1e9:.2f} GB)"); return
    t0 = time.time()
    with open(out, "ab") as f:
        while done < total:
            a = start + done
            b = min(a + chunk - 1, end)
            for attempt in range(5):
                try:
                    buf = head_range(url, a, b, timeout=180); break
                except Exception as e:
                    print(f"    やり直し {attempt+1}/5: {e}"); time.sleep(2)
            else:
                raise RuntimeError("5回試して失敗")
            f.write(buf); f.flush()
            done += len(buf)
            el = time.time() - t0
            sp = done / el / 1e6 if el else 0
            print(f"  {done/1e9:6.2f} / {total/1e9:.2f} GB  "
                  f"({100*done/total:5.1f}%)  {sp:.1f} MB/s", flush=True)

if __name__ == "__main__":
    repo   = sys.argv[1] if len(sys.argv) > 1 else "moonshotai/Kimi-K2-Instruct"
    shard  = sys.argv[2] if len(sys.argv) > 2 else "model-1-of-61.safetensors"
    tname  = sys.argv[3] if len(sys.argv) > 3 else "model.embed_tokens.weight"
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mined")
    os.makedirs(outdir, exist_ok=True)
    url = f"https://huggingface.co/{repo}/resolve/main/{shard}"
    print(f"■ {repo}")
    info = find_tensor(url, tname)
    print(f"  形    : {info['shape']} ({info['dtype']})")
    print(f"  大きさ: {info['size']/1e9:.2f} GB")
    tag = repo.split("/")[-1]
    out = os.path.join(outdir, f"{tag}.embed.bin")
    with open(os.path.join(outdir, f"{tag}.embed.json"), "w") as f:
        json.dump({"repo": repo, **{k: v for k, v in info.items()}}, f, indent=2)
    fetch(url, info["start"], info["end"], out)
    print(f"  → {out}")
