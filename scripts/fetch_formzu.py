#!/usr/bin/env python3
"""
フォームズ(formzu.com)から受信データCSVを自動ダウンロードするスクリプト
必要な GitHub Secrets:
  FORMZU_ID       : フォームID (例: S950893888)
  FORMZU_PASSWORD : フォームのパスワード
  FORMZU_CSV_URL  : (任意) CSVダウンロードの直接URL（自動検出に失敗した場合に設定）
"""
import requests
from bs4 import BeautifulSoup
import os, sys
from urllib.parse import urljoin

FORM_ID   = os.environ.get('FORMZU_ID', '')
PASSWORD  = os.environ.get('FORMZU_PASSWORD', '')
CSV_URL_OVERRIDE = os.environ.get('FORMZU_CSV_URL', '')  # 直接URLが分かっている場合

if not FORM_ID or not PASSWORD:
    print("❌ FORMZU_ID と FORMZU_PASSWORD が設定されていません", file=sys.stderr)
    print("   GitHub リポジトリ → Settings → Secrets and variables → Actions で設定してください", file=sys.stderr)
    sys.exit(1)

BASE = 'https://www.formzu.com'

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept-Language': 'ja,en-US;q=0.9',
})


def save_csv(text: str):
    with open('logs.csv', 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    lines = text.strip().splitlines()
    print(f"✅ logs.csv を保存しました（{len(lines)-1} 件のデータ）")


def decode_response(content: bytes) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'shift_jis', 'cp932'):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode('utf-8', errors='replace')


# ── ① ログインページを取得してフォームを解析 ──────────────────
print(f"フォームズにログイン中（フォームID: {FORM_ID}）...")
r = s.get(f'{BASE}/login_form', timeout=30)
r.raise_for_status()

soup = BeautifulSoup(r.text, 'html.parser')
form = soup.find('form')
if not form:
    print("❌ ログインフォームが見つかりません", file=sys.stderr)
    sys.exit(1)

action = urljoin(BASE, form.get('action', '/login'))

# フォームの全inputを収集
post_data = {}
for inp in form.find_all('input'):
    n = inp.get('name')
    if n:
        post_data[n] = inp.get('value', '')

# フォームID / パスワードフィールドを自動検出して埋める
for n in list(post_data.keys()):
    nl = n.lower()
    if any(k in nl for k in ('loginid', 'login_id', 'formid', 'form_id', 'userid', 'user')):
        post_data[n] = FORM_ID
        print(f"  フォームIDフィールド検出: {n}")
    elif any(k in nl for k in ('password', 'passwd', 'pass')):
        post_data[n] = PASSWORD
        print(f"  パスワードフィールド検出: {n}")

# ── ③ ログイン実行 ───────────────────────────────────────────
r = s.post(action, data=post_data, allow_redirects=True, timeout=30)
print(f"  ログイン結果: HTTP {r.status_code}  →  {r.url}")

if 'login' in r.url.lower():
    print("❌ ログインに失敗しました。FORMZU_ID と FORMZU_PASSWORD を確認してください。", file=sys.stderr)
    sys.exit(1)

# ── ④ CSVダウンロードリンクを探す ────────────────────────────

# 直接URLが設定されている場合はログイン済みセッションでそこへアクセス
if CSV_URL_OVERRIDE:
    print(f"直接URL指定で取得（ログイン済みセッション使用）: {CSV_URL_OVERRIDE}")
    csv_url = CSV_URL_OVERRIDE
else:
    def find_csv_link(html: str, base: str):
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a'):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            if any(k in href.lower() for k in ('csv', 'download', 'dl')) \
               or any(k in text for k in ('CSV', 'ダウンロード', 'csv')):
                return urljoin(base, href)
        return None

    csv_url = find_csv_link(r.text, r.url)

# 見つからなければ受信データページを直接試みる
if not csv_url:
    candidates = [
        f'{BASE}/fapi/{FORM_ID}/',
        f'https://ws.formzu.net/fapi/{FORM_ID}/',
        f'{BASE}/data/{FORM_ID}/',
        f'{BASE}/admin/{FORM_ID}/',
    ]
    for url in candidates:
        try:
            tr = s.get(url, timeout=15, allow_redirects=True)
            if tr.status_code == 200:
                found = find_csv_link(tr.text, tr.url)
                if found:
                    csv_url = found
                    print(f"  受信データページ発見: {url}")
                    break
        except Exception:
            continue

if not csv_url:
    print("", file=sys.stderr)
    print("❌ CSVダウンロードURLが自動検出できませんでした。", file=sys.stderr)
    print("   フォームズの管理画面でCSVダウンロードページのURLを確認し、", file=sys.stderr)
    print("   GitHub Secrets に FORMZU_CSV_URL として登録してください。", file=sys.stderr)
    sys.exit(1)

# ── ⑤ CSV取得・保存 ─────────────────────────────────────────
print(f"CSV取得中: {csv_url}")
csv_r = s.get(csv_url, timeout=30)
csv_r.raise_for_status()

text = decode_response(csv_r.content)

stripped = text.lstrip()
if stripped.startswith('<') or '<!DOCTYPE' in stripped[:100].upper():
    print(f"❌ HTMLが返されました（CSVではありません）。FORMZU_CSV_URL が正しいか確認してください。", file=sys.stderr)
    print(f"   取得URL: {csv_url}", file=sys.stderr)
    print(f"   レスポンス先頭200文字: {text[:200]}", file=sys.stderr)
    sys.exit(1)

if '\n' not in text or ',' not in text:
    print(f"❌ CSVではないデータが返されました（{len(text)} bytes）", file=sys.stderr)
    sys.exit(1)

save_csv(text)
