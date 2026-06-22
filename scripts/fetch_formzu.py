#!/usr/bin/env python3
"""
フォームズ(formzu.com)から受信データCSVを自動ダウンロードするスクリプト
必要な GitHub Secrets:
  FORMZU_ID       : フォームID (例: S950893888)
  FORMZU_PASSWORD : フォームのパスワード
  FORMZU_CSV_URL  : (任意) ログデータ管理ページのURL（自動検出に失敗した場合に設定）
"""
import re
import requests
from bs4 import BeautifulSoup
import os, sys
from urllib.parse import urljoin, urlparse, parse_qs

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

    # URLのクエリパラメータを取得（id= など）
    url_params = {k: v[0] for k, v in parse_qs(urlparse(page_url).query).items()}
    parsed = urlparse(page_url)
    base_action = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # ⓪ JavaScriptの goDownLoadMailLog / ダウンロード関数を解析
    for script in soup.find_all('script'):
        src = script.string or ''
        if not any(k in src for k in ('goDownLoad', 'MailLog', 'csv', 'CSV')):
            continue
        # 関数定義を探す
        fn_match = re.search(
            r'function\s+\w*[Dd]own[Ll]oad\w*\s*\([^)]*\)\s*\{(.*?)\}',
            src, re.DOTALL)
        if fn_match:
            fn_body = fn_match.group(1)
            print(f"  JS関数本体: {fn_body[:400]}", file=sys.stderr)
            # go.value = '...' パターンを探す
            m = re.search(r'\.go\.value\s*=\s*[\'"]([^\'"]+)[\'"]', fn_body)
            if m:
                go_val = m.group(1)
                print(f"  JS go値発見: {go_val}")
                # そのフォームを探してsubmit
                for form in soup.find_all('form'):
                    action = urljoin(page_url, form.get('action', page_url))
                    data = {}
                    for inp in form.find_all('input'):
                        n = inp.get('name')
                        if n:
                            data[n] = inp.get('value', '')
                    for sel in form.find_all('select'):
                        n = sel.get('name')
                        if n:
                            opt = sel.find('option', selected=True) or sel.find('option')
                            data[n] = opt.get('value', '') if opt else ''
                    for k, v in url_params.items():
                        if k not in data:
                            data[k] = v
                    data['go'] = go_val
                    print(f"  JS go値でPOST: {action}")
                    r = s.post(action, data=data, timeout=30)
                    t = decode_response(r.content)
                    if not is_html(t):
                        return t
        # URLパターンを探す（window.location やリダイレクト）
        url_matches = re.findall(r'[\'"]([^\'"]*assemble-form[^\'"]*)[\'"]', src)
        for url_candidate in url_matches:
            print(f"  JSのURL候補: {url_candidate}", file=sys.stderr)

    # ① <a href="...csv..."> スタイルのリンクを探す
    for a in soup.find_all('a'):
        href = a.get('href', '')
        label = a.get_text(strip=True)
        if any(k in href.lower() for k in ('csv', 'download', 'dl')) \
           or any(k in label for k in ('CSV', 'ダウンロード')):
            url = urljoin(page_url, href)
            print(f"  CSVリンク発見: {url}")
            r = s.get(url, timeout=30)
            t = decode_response(r.content)
            if not is_html(t):
                return t

    # ② GETで直接CSVダウンロードURLを試す（formzuのパターン）
    form_id_in_url = url_params.get('id', FORM_ID)
    for go_val in ('csv_dl', 'log_csv', 'logcsv', 'download', 'csvdownload', 'dl',
                   'show-log-csv', 'log-csv', 'logdata_csv', 'csv'):
        try:
            params = dict(url_params)
            params['go'] = go_val
            r = s.get(base_action, params=params, timeout=30)
            t = decode_response(r.content)
            if not is_html(t):
                print(f"  CSV取得成功 GET go={go_val}")
                return t
        except Exception:
            pass

    # ③ <form> 内のCSVボタンを探してPOST（select要素も含める）
    for form in soup.find_all('form'):
        csv_btn = None
        for el in form.find_all(['input', 'button', 'a']):
            label = el.get_text(strip=True) or el.get('value', '')
            if any(k in label for k in ('CSV', 'csv', 'ダウンロード')):
                csv_btn = el
                break
        if not csv_btn:
            continue

        # ボタン情報を診断出力
        print(f"  ボタン発見: tag={csv_btn.name} type={csv_btn.get('type')} "
              f"name={csv_btn.get('name')} value={csv_btn.get('value')} "
              f"onclick={str(csv_btn.get('onclick',''))[:80]}", file=sys.stderr)

        action = urljoin(page_url, form.get('action', page_url))
        method = form.get('method', 'post').lower()

        # フォームのinput/selectを収集
        data = {}
        for inp in form.find_all('input'):
            n = inp.get('name')
            if n:
                data[n] = inp.get('value', '')
        for sel in form.find_all('select'):
            n = sel.get('name')
            if n:
                opt = sel.find('option', selected=True) or sel.find('option')
                data[n] = opt.get('value', '') if opt else ''

        # URLのクエリパラメータ（id= など）をPOSTデータに追加
        for k, v in url_params.items():
            if k not in data:
                data[k] = v

        # ボタン自身のname/valueも送る
        if csv_btn.get('name'):
            data[csv_btn.get('name')] = csv_btn.get('value', '')

        # go パラメータ値を試す
        go_values_to_try = [data.get('go', '')] + ['csv_dl', 'log_csv', 'logcsv',
                                                    'download', 'csvdownload', 'dl']
        for go_val in go_values_to_try:
            if not go_val:
                continue
            data['go'] = go_val
            print(f"  CSVフォーム送信: {method.upper()} {action} go={go_val}")
            try:
                if method == 'post':
                    r = s.post(action, data=data, timeout=30)
                else:
                    r = s.get(action, params=data, timeout=30)
                t = decode_response(r.content)
                if not is_html(t):
                    return t
            except Exception as e:
                print(f"  go={go_val}: エラー {e}")

        print(f"  フォームからCSVを取得できませんでした（go値を全て試しました）")

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
