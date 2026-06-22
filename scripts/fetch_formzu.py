#!/usr/bin/env python3
"""
フォームズ(formzu.com)から受信データCSVを自動ダウンロードするスクリプト
必要な GitHub Secrets:
  FORMZU_ID       : フォームID (例: S950893888)
  FORMZU_PASSWORD : フォームのパスワード
  FORMZU_CSV_URL  : (任意) ログデータ管理ページのURL（自動検出に失敗した場合に設定）
"""
import requests
from bs4 import BeautifulSoup
import os, sys
from urllib.parse import urljoin

FORM_ID   = os.environ.get('FORMZU_ID', '')
PASSWORD  = os.environ.get('FORMZU_PASSWORD', '')
CSV_URL_OVERRIDE = os.environ.get('FORMZU_CSV_URL', '')

if not FORM_ID or not PASSWORD:
    print("❌ FORMZU_ID と FORMZU_PASSWORD が設定されていません", file=sys.stderr)
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


def is_html(text: str) -> bool:
    s = text.lstrip()
    return s.startswith('<') or '<!DOCTYPE' in s[:100].upper()


def try_csv_from_page(html: str, page_url: str) -> str | None:
    """管理ページのHTMLからCSVダウンロードを試みる（リンクまたはフォーム送信）。"""
    soup = BeautifulSoup(html, 'html.parser')

    # ① <a href="...csv..."> スタイルのリンクを探す
    for a in soup.find_all('a'):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        if any(k in href.lower() for k in ('csv', 'download', 'dl')) \
           or any(k in text for k in ('CSV', 'ダウンロード')):
            url = urljoin(page_url, href)
            print(f"  CSVリンク発見: {url}")
            r = s.get(url, timeout=30)
            t = decode_response(r.content)
            if not is_html(t):
                return t

    # ② <form> 内の「CSVファイルダウンロード」ボタンを探してPOST
    for form in soup.find_all('form'):
        csv_btn = None
        for el in form.find_all(['input', 'button', 'a']):
            label = el.get_text(strip=True) or el.get('value', '')
            if any(k in label for k in ('CSV', 'csv', 'ダウンロード')):
                csv_btn = el
                break
        if not csv_btn:
            continue

        action = urljoin(page_url, form.get('action', page_url))
        method = form.get('method', 'post').lower()
        data = {}
        for inp in form.find_all('input'):
            n = inp.get('name')
            if n:
                data[n] = inp.get('value', '')
        # ボタン自身のname/valueも送る
        if csv_btn.get('name'):
            data[csv_btn.get('name')] = csv_btn.get('value', '')

        print(f"  CSVフォーム送信: {method.upper()} {action}  data={list(data.keys())}")
        if method == 'post':
            r = s.post(action, data=data, timeout=30)
        else:
            r = s.get(action, params=data, timeout=30)

        t = decode_response(r.content)
        if not is_html(t):
            return t
        print(f"  フォーム送信後もHTMLが返されました（{len(t)} chars）")

    return None


# ── ① ログイン ────────────────────────────────────────────────
print(f"フォームズにログイン中（フォームID: {FORM_ID}）...")
r = s.get(f'{BASE}/login_form', timeout=30)
r.raise_for_status()

soup = BeautifulSoup(r.text, 'html.parser')
form = soup.find('form')
if not form:
    print("❌ ログインフォームが見つかりません", file=sys.stderr)
    sys.exit(1)

action = urljoin(BASE, form.get('action', '/login'))
post_data = {}
for inp in form.find_all('input'):
    n = inp.get('name')
    if n:
        post_data[n] = inp.get('value', '')

for n in list(post_data.keys()):
    nl = n.lower()
    if any(k in nl for k in ('loginid', 'login_id', 'formid', 'form_id', 'userid', 'user')):
        post_data[n] = FORM_ID
        print(f"  フォームIDフィールド検出: {n}")
    elif any(k in nl for k in ('password', 'passwd', 'pass')):
        post_data[n] = PASSWORD
        print(f"  パスワードフィールド検出: {n}")

r = s.post(action, data=post_data, allow_redirects=True, timeout=30)
print(f"  ログイン結果: HTTP {r.status_code}  →  {r.url}")

if 'login' in r.url.lower():
    print("❌ ログインに失敗しました。FORMZU_ID と FORMZU_PASSWORD を確認してください。", file=sys.stderr)
    sys.exit(1)

# ── ② 管理ページを特定してCSVを取得 ──────────────────────────
text = None

# FORMZU_CSV_URL が設定されている場合はそのページへアクセス
if CSV_URL_OVERRIDE:
    print(f"管理ページにアクセス中: {CSV_URL_OVERRIDE}")
    page_r = s.get(CSV_URL_OVERRIDE, timeout=30)
    page_r.raise_for_status()
    candidate_text = decode_response(page_r.content)
    if not is_html(candidate_text):
        # 直接CSVが返された場合
        text = candidate_text
    else:
        # 管理ページのHTMLだった場合 → ボタン/フォームを探してダウンロード
        print("  HTMLページを検出。CSVダウンロードボタンを探しています...")
        text = try_csv_from_page(candidate_text, page_r.url)

# 未取得なら自動検出を試みる
if not text:
    candidates = [
        f'{BASE}/fapi/{FORM_ID}/',
        f'https://ws.formzu.net/fapi/{FORM_ID}/',
        f'{BASE}/data/{FORM_ID}/',
        f'{BASE}/admin/{FORM_ID}/',
        r.url,  # ログイン後のページ
    ]
    for url in candidates:
        try:
            tr = s.get(url, timeout=15, allow_redirects=True)
            if tr.status_code != 200:
                continue
            t = decode_response(tr.content)
            if is_html(t):
                found = try_csv_from_page(t, tr.url)
                if found:
                    text = found
                    print(f"  CSV取得成功（自動検出）: {url}")
                    break
            else:
                text = t
                print(f"  CSV取得成功（直接）: {url}")
                break
        except Exception as e:
            print(f"  {url} → エラー: {e}")
            continue

if not text:
    print("", file=sys.stderr)
    print("❌ CSVを自動取得できませんでした。", file=sys.stderr)
    print("   フォームズ管理画面の「ログデータ」ページのURLを", file=sys.stderr)
    print("   GitHub Secrets の FORMZU_CSV_URL に登録してください。", file=sys.stderr)
    sys.exit(1)

# ── ③ バリデーション & 保存 ──────────────────────────────────
if is_html(text):
    print(f"❌ 最終的にHTMLが返されました。FORMZU_CSV_URL を確認してください。", file=sys.stderr)
    print(f"   先頭200文字: {text[:200]}", file=sys.stderr)
    sys.exit(1)

if '\n' not in text or ',' not in text:
    print(f"❌ CSVではないデータが返されました（{len(text)} bytes）", file=sys.stderr)
    sys.exit(1)

save_csv(text)
