#!/usr/bin/env python3
"""完成済み pages-articles を取得・検証。展開しない。VM 自己削除も担当。"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE = 'https://dumps.wikimedia.org'
USER_AGENT = 'chishiki-dump-builder/1.0 (public XML bulk download; no article API)'


def request(url, **kwargs):
    return urlopen(Request(url, headers={'User-Agent': USER_AGENT}, **kwargs), timeout=120)


def plan(site, status):
    jobs = status.get('jobs', {})
    for job_name in ('articlesdumprecombine', 'articlesdump'):
        job = jobs.get(job_name, {})
        if job.get('status') != 'done':
            continue
        files = [(name, info) for name, info in job.get('files', {}).items()
                 if re.fullmatch(re.escape(site) + r'-\d{8}-pages-articles(?:\d+)?\.xml(?:-p\d+p\d+)?\.bz2', name)]
        if files:
            combined = [(n, i) for n, i in files if '-pages-articles.xml.bz2' in n]
            return sorted(combined or files)
    raise ValueError(f'{site}: latest に完成済みの articlesdump がありません。途中版は使いません')


def latest_done(site, tries=3):
    """10/3: latest/ に dumpstatus.json は無い（404）。日付のフォルダを新しい順に見て、記事が完成した最初の回を使う。"""
    with request(f'{BASE}/{site}/') as response:
        dates = sorted(set(re.findall(r'href="(\d{8})/"', response.read().decode())), reverse=True)
    for date in dates[:tries]:
        try:
            with request(f'{BASE}/{site}/{date}/dumpstatus.json') as response:
                status = json.load(response)
            status.setdefault('date', date)
            return status, plan(site, status)
        except Exception as e:
            print(f'{site}/{date}: 使わない（{e}）', flush=True)
    raise ValueError(f'{site}: 新しい{tries}回に完成済みの記事ダンプがありません')


def download(site, directory, dry=False):
    status, files = latest_done(site)
    if dry:
        return [(name, info.get('size')) for name, info in files]
    paths = []
    for name, info in files:
        path = directory / name
        partial = path.with_suffix(path.suffix + '.partial')
        if path.exists() or partial.exists():
            raise FileExistsError(f'上書きしません: {path}')
        url = info.get('url') or f'/{site}/{status["date"]}/{name}'
        url = BASE + url if url.startswith('/') else url
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != 'dumps.wikimedia.org':
            raise ValueError('ダンプURLが公式配布先ではありません')
        expected_size = info.get('size')
        expected_sha1 = info.get('sha1')
        if not isinstance(expected_size, int) or not expected_size or not expected_sha1:
            raise ValueError(f'{name}: dumpstatus に size/sha1 がありません')
        print(f'{site}: {name} ({expected_size / 1024**3:.2f} GiB) を取得', flush=True)
        digest = hashlib.sha1()
        # 一時的な接続切れは最初から最大3回。未検証ファイルを入力にしない。
        for attempt in range(3):
            digest = hashlib.sha1()
            try:
                with request(url) as response, partial.open('wb') as out:
                    while chunk := response.read(4 * 1024 * 1024):
                        out.write(chunk)
                        digest.update(chunk)
                if partial.stat().st_size != expected_size or digest.hexdigest() != expected_sha1:
                    raise ValueError(f'{name}: 大きさ/SHA1 の照合失敗')
                partial.rename(path)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        paths.append(str(path.resolve()))
    (directory / f'{site}-dumpstatus.json').write_text(json.dumps(status, ensure_ascii=False, indent=2))
    return paths


def self_delete():
    base = 'http://metadata.google.internal/computeMetadata/v1/'

    def metadata(path):
        with urlopen(Request(base + path, headers={'Metadata-Flavor': 'Google'}), timeout=10) as response:
            return response.read().decode()

    project = metadata('project/project-id')
    zone = metadata('instance/zone').split('/')[-1]
    name = metadata('instance/name')
    # トークンはメモリ内だけ。ログ・引数・ファイルには出さない。
    token = json.loads(metadata('instance/service-accounts/default/token'))['access_token']
    url = f'https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{name}'
    with urlopen(Request(url, method='DELETE', headers={'Authorization': 'Bearer ' + token}), timeout=60) as response:
        json.load(response)
    print('VM 自己削除を要求しました', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path)
    p.add_argument('--site', choices=('jawiki', 'jawikibooks', 'jawikisource'), action='append')
    p.add_argument('--self-delete', action='store_true')
    p.add_argument('--dry', action='store_true', help='一覧だけ見る（取らない）')
    a = p.parse_args()
    if a.self_delete:
        self_delete()
        return
    if not a.directory or not a.site:
        p.error('--directory と --site が必要')
    if a.dry:
        for site in a.site:
            print(site, download(site, a.directory, dry=True))
        return
    a.directory.mkdir(parents=True, exist_ok=True)
    result = {site: download(site, a.directory) for site in a.site}
    (a.directory / 'inputs.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
