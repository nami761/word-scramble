# 西小 読み聞かせ記録ノート — 引継ぎドキュメント

GitHub Pages でフォームズ(formzu.com)の受信データを自動表示するシステムです。
新しいフォームを同じ仕組みで表示したい場合はこのドキュメントを参照してください。

---

## システム構成

```
フォームズ(formzu.com)
  ↓ GitHub Actions（1時間ごと自動 + ボタンで手動起動）
  ↓ scripts/fetch_formzu.py でCSVダウンロード → logs.csv に保存
  ↓ GitHub Pages (master ブランチ)
logs.html でCSVを読み込み表示
```

**手動更新ボタンの仕組み:**

```
ユーザーがページの「フォームズから取得」ボタンをクリック
  ↓ POST https://formzu-trigger.nami761.workers.dev
  ↓ Cloudflare Worker（GITHUB_TOKEN を秘密変数として保持）
  ↓ GitHub API: workflow_dispatch で update-logs.yml を起動
  ↓ Actions が fetch_formzu.py を実行 → logs.csv を更新
  ↓ logs.html が5秒ごとにCSVをポーリングして自動更新（最大90秒待機）
```

---

## リポジトリ構成

| ファイル | 役割 |
|---|---|
| `logs.html` | 表示ページ（GitHub Pages） |
| `logs.csv` | フォームズから取得したデータ（Actions が自動更新） |
| `scripts/fetch_formzu.py` | フォームズにログインしてCSVを取得するスクリプト |
| `.github/workflows/update-logs.yml` | Actions ワークフロー（1時間ごと + 手動） |
| `index.html` | トップページ |

---

## 新しいフォームを追加する手順

### 1. GitHub Secrets を設定

リポジトリの **Settings → Secrets and variables → Actions** で以下を登録：

| Secret名 | 内容 |
|---|---|
| `FORMZU_ID` | フォームID（例: `S950893888`） |
| `FORMZU_PASSWORD` | フォームのパスワード |
| `FORMZU_CSV_URL` | フォーム管理画面の「ログデータ」ページURL（例: `https://www.formzu.com/fapi/S950893888/?go=log`）|

> `FORMZU_CSV_URL` は formzu.com にログイン後、対象フォームの「受信データ」→「ログデータ」ページのURLをコピーして設定する。

### 2. ワークフローが動くことを確認

Actions タブ → **Update Form Logs** → **Run workflow** ボタンが表示されること。
（表示されない場合はリポジトリの **デフォルトブランチが master** であることを確認）

### 3. 表示ページ（logs.html）のCSVカラム設定を合わせる

フォームの項目数・順序に合わせて `logs.html` の `COL` を修正：

```javascript
const COL = {
  time:  0,  // 日付（送信日時）
  name:  1,  // 読み手名
  date:  2,  // 読み聞かせ日
  grade: 3,  // 学年
  book:  4,  // 本のタイトル
  note:  5,  // 子どもたちの様子
  memo:  6,  // その他メモ
};
```

実際のCSVヘッダーは Actions のログか、`logs.csv` の1行目で確認できる。

### 4. Cloudflare Worker を設定（手動取得ボタン用）

既存の Worker `formzu-trigger` は `nami761/word-scramble` リポジトリの
`update-logs.yml` を起動するように設定済み。

**別リポジトリ用に新しく作る場合:**

1. [Cloudflare Workers](https://workers.cloudflare.com/) でアカウント作成
2. 新しい Worker を作成し、以下のコードを貼り付ける：

```javascript
export default {
  async fetch(request, env) {
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: cors });
    }
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: cors });
    }
    const res = await fetch(
      'https://api.github.com/repos/【オーナー】/【リポジトリ名】/actions/workflows/update-logs.yml/dispatches',
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
          'Accept': 'application/vnd.github+json',
          'Content-Type': 'application/json',
          'User-Agent': 'Cloudflare-Worker',
        },
        body: JSON.stringify({ ref: 'master' }),
      }
    );
    if (res.status === 204) {
      return new Response(JSON.stringify({ ok: true }), {
        headers: { ...cors, 'Content-Type': 'application/json' },
      });
    }
    const text = await res.text();
    return new Response(JSON.stringify({ ok: false, error: text }), {
      status: 500,
      headers: { ...cors, 'Content-Type': 'application/json' },
    });
  },
};
```

3. Worker の **Settings → Variables and Secrets** で `GITHUB_TOKEN` を追加
   - GitHub の **Settings → Developer settings → Personal access tokens (fine-grained)**
   - 対象リポジトリに `Actions: Read and write` 権限を付与して生成
   - トークンの値を Worker の Secret として保存（Encrypt にチェック）

4. `logs.html` の `triggerFetch()` 内のWorker URLを新しいURLに変更：
   ```javascript
   const res = await fetch('https://【新しいWorker名】.workers.dev', { method: 'POST' });
   ```

---

## 現在の設定値（このリポジトリ）

| 項目 | 値 |
|---|---|
| GitHub Pages URL | `https://nami761.github.io/word-scramble/logs.html` |
| フォームURL | `https://ws.formzu.net/dist/S950893888/` |
| Cloudflare Worker | `https://formzu-trigger.nami761.workers.dev` |
| Actions ワークフロー | `.github/workflows/update-logs.yml` |
| 自動更新間隔 | 1時間ごと（cron: `0 * * * *`） |

---

## トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| Actions が失敗する | `FORMZU_CSV_URL` を「ログデータ」ページのURLで設定する |
| CSVがHTMLになる | formzuのログインセッション失敗。Secret の FORMZU_ID/PASSWORD を確認 |
| 「Run workflow」ボタンが出ない | リポジトリのデフォルトブランチを `master` に変更する |
| ボタンを押しても反応しない | Cloudflare Worker の GITHUB_TOKEN が期限切れの可能性。再発行して再設定 |
| 列がずれて表示される | `logs.csv` の1行目（ヘッダー）を確認し、`logs.html` の `COL` を合わせる |
