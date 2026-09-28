"""画面の写真を撮る（headless Chrome。9/28）。
  python3 dougu/gamen_shashin.py 出力先フォルダ 名前=URL[@幅x高さ] ...
Chrome は撮った後も残ることがあるので、時間で止める。砂箱の外で動かす。"""
import os, subprocess, sys, tempfile
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
prof = tempfile.mkdtemp(prefix="gamen-chrome-")
for arg in sys.argv[2:]:
    name, url = arg.split("=", 1)
    size = "1280x800"
    if "@" in url.rsplit("/", 1)[-1]:
        url, size = url.rsplit("@", 1)
    w, h = size.split("x")
    png = os.path.join(out, name + ".png")
    semai = int(w) < 500   # Chrome の窓は 500px より狭くならない → 真ん中の枠に開いて、sips で真ん中を切る
    if semai:
        waku = os.path.join(prof, name + "_waku.html")
        open(waku, "w").write(f'<body style="margin:0"><iframe src="{url}" style="width:{w}px;height:{h}px;border:0;display:block;margin-left:{(500 - int(w)) // 2}px"></iframe>')
        url, w0 = "file://" + waku, w
        w = "500"
    cmd = [CHROME, "--headless=new", f"--user-data-dir={prof}", "--no-first-run", "--disable-gpu",
           "--hide-scrollbars", "--allow-file-access-from-files", f"--window-size={w},{h}", "--virtual-time-budget=4000",
           f"--screenshot={png}", url]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        p.wait(timeout=45)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try: os.killpg(p.pid, 9)
        except ProcessLookupError: pass
    if semai and os.path.exists(png):
        subprocess.run(["sips", "-c", h, w0, png, "--out", png], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(name, "撮れた" if os.path.exists(png) else "撮れない")
