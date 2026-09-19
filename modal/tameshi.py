# Modal の試し: GPU を数秒借りて名前と空きを見る。 使い方: ~/LocalAI_mirror/venv/bin/modal run modal/tameshi.py
import os, subprocess, modal
app = modal.App("kernel-tameshi")
@app.function(gpu=os.environ.get("GPU", "L4"), timeout=120)
def miru():
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"], capture_output=True, text=True).stdout
    cpu = subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip()
    mem = subprocess.run(["sh", "-c", "free -g | awk 'NR==2{print $2}'"], capture_output=True, text=True).stdout.strip()
    disk = subprocess.run(["sh", "-c", "df -h /tmp | tail -1 | awk '{print $4}'"], capture_output=True, text=True).stdout.strip()
    return f"GPU {out.strip()} / CPU {cpu}コア / RAM {mem}GB / 盤 {disk}"
@app.local_entrypoint()
def main():
    print(miru.remote())
