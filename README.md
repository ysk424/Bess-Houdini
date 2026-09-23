# Bess

**Houdini の魔術パートナー。**

Houdini Indie（Steam版）の中でCodexと会話し、開いているシーンを操作する日本語Python Panelです。
表示名は **Bess**、リポジトリ名は `Bess-Houdini`、Python・パネル・パッケージの識別子は `bess_houdini`。
Bess Houdini（Harry Houdiniの妻・舞台パートナー）に由来します。

## 環境

- Windows / Steam版Houdini Indie 22以降、Python 3.13 / PySide6
- Codex CLI（開発環境: 0.156.1）とChatGPTログイン
- Codexのモデル利用可否・利用枠はログインしているアカウントに従います

Steamで配信されるHoudini Indieを対象にしています。SteamVRランタイムには依存しません。
APIキーの入力は不要です。認証は公式Codex CLIが管理し、Bessはトークンを読み取ったり保存したりしません。

## インストール

```powershell
git clone https://github.com/ysk424/Bess-Houdini.git
cd Bess-Houdini
./install.ps1
```

インストーラーの実行には、Windows側のPython 3.10以降が必要です。Houdini内では同梱のPythonを使用します。

SteamのライブラリからHoudini Indieを探し、hythonで実際の設定フォルダーを確認して登録します。
別のライブラリなら `./install.ps1 -HoudiniDir 'D:/SteamLibrary/steamapps/common/Houdini Indie'`。
プレビューは `-DryRun`。旧houdini-mcpの既知の自動起動行をバックアップして停止する場合は `-DisableLegacyMcp`。
既存Codexのグローバル設定は変更しません。すでに動いているMCPプロセスは終了しません。

Houdiniを再起動して、ペインの **＋ → New Pane Tab Type → Misc → Python Panel** を開き、インターフェースで **Bess** を選びます。
またはシェルフ一覧から **Bess** を追加し、Bessボタンで独立パネルを開きます。
Python Shellからは `import bess_houdini; bess_houdini.show()` でも開けます。

ソースはこのチェックアウトを参照するため、インストール後はフォルダーを移動しないでください。
パネル／シェルフ定義を変更した場合は再インストールしてください。

## 使い方

パネルを開くとCodexに接続します。未認証なら「ChatGPTでログイン」を押します。
入力は標準のQt複数行テキスト欄です。日本語を確定してから「送信」ボタンで送ります。
独自のキー判定やCtrl+Enter送信は行いません。EnterはIME確定または改行に使います。
「送信」の左隣にある「ペースト」で、クリップボードの文章をカーソル位置へ貼り付けられます。選択中の文章があれば置き換えます。
mimiで「コピーして閉じる」→ Bessで「ペースト」→「送信」と押せば、キーボードを使わずに指示できます。
応答中は「追加指示を送る」を使えます。受理されるまでは送った入力を保持します。
受理待ち中も編集でき、書き換えていた場合は受理後も新しい下書きを消しません。
「停止」で以後のHoudini操作を拒否し、Codexに中断を要求します。

| プリセット | モデル | 推論量 |
| --- | --- | --- |
| 問い合わせ（初期値） | GPT-6 Luna | medium |
| 制作 | GPT-6 Sol | medium |
| 難しい仕事 | GPT-6 Astra | xhigh |

モデル一覧はCodexから取得します。利用不可のモデルへ暗黙に切り替えません。
モデルと推論量を個別に変更できます。切替は次の送信に適用します。
履歴から会話を再開できます。スクロールして読むときは「最新の発言を追う」をオフにします。
「設定」で作業フォルダー、codex.exe、PC・Houdini操作の許可を指定し、切断・再接続で反映します。
初回の未保存シーンではBess設定フォルダー内の `workspace/`、保存済みシーンでは `$HIP` を作業フォルダーの初期値にします。
操作許可は初期状態でオン。オフではCodexの読み取り専用設定を使い、HoudiniのPython実行ツールを渡しません。

### 日本語IMEで入力が途中で止まる場合

Houdini内の入力欄へフォーカスを移すと、移動前とIMEモードが一致せず、日本語の未確定入力が途中で止まる場合があります。
利用環境では、入力欄側とIMEのモードが一致していると入力できることを確認しています。

1. Bessのメッセージ欄をクリックします。
2. **クリックした後で**IMEの状態（「A」／「あ」）を確認し、使う入力モードに切り替えます。
3. 日本語を入力・確定してから「送信」を押します。

BessはIMEのオン／オフや半角／全角を強制しません。独自のキー入力監視も行いません。
HoudiniのPython Panel上で発生する入力モードの問題として、この回避方法を案内しています。
Houdini・Qt・Windows IMEのどの層で状態が食い違うかは未特定です。

## 構成

Houdini Python Panel ⇄ 標準入出力JSON-RPC ⇄ Codex App Server。
Houdini側の通信待受ポートやMCPサーバーは不要です。
既存MCPは子プロセス／スレッドに限定して無効化し、会話開始前に外部MCPツールが残っていないことを確認します。
PC上の通常のCodex設定やログインは利用しますが、BessではAppsとPluginsを無効にしています。

Houdini専用の入口は4つです。

| ツール | 内容 |
| --- | --- |
| `houdini_context` | シーン、選択、フレーム、指定ネットワーク、ノードのエラー |
| `houdini_python` | 現在のHoudiniメインスレッドでPython/HOMを実行、stdout・result・例外を返す |
| `houdini_screenshot` | Houdiniメインウィンドウ全体の画像をCodexへ返す（GUIのみ） |
| `houdini_docs` | 同梱ヘルプのパス検索・本文取得（英語のノード/API名で検索） |

Python実行は通常のノード操作をUndoグループにまとめます。ファイル保存、外部コマンド、環境変更はUndoでは復元できません。
任意PythonはHoudiniプロセスの権限で動き、Codexのコマンド用サンドボックスには入りません。
失敗したPythonに部分変更が残る場合があります。長い同期cookやシミュレーションはUIを止め、実行が戻るまで「停止」も効きません。
初版には長時間シミュレーション専用のジョブ管理・強制停止・自動ロールバックはありません。
重い作業は短い段階に分けるか、別ファイルを対象に外部プロセスで実行する方針です。
ヘルプ検索は全文BM25検索ではなく、同梱アーカイブのパス検索です。旧MCPの検索インデックスには依存しません。

## 保存と削除

設定と表示用会話は `$HOUDINI_USER_PREF_DIR/bess_houdini/` に保存します。
Codex本来の履歴はCodex自身が保存します。認証・会話を `.hiplc` に埋め込みません。
アンインストールは設定フォルダー内の `packages/bess_houdini.json`、`python_panels/Bess.pypanel`、`toolbar/bess_houdini.shelf` を削除して再起動。
会話は上記 `bess_houdini/` に残ります。旧MCP自動起動を復元する場合はインストーラーの `.bess-backup-*` を確認してください。

## 検証

結果は [docs/VALIDATION.ja.md](docs/VALIDATION.ja.md) を参照。
テストは新規hython/GUIプロセスと一時フォルダーで行います。実際のモデル呼び出しは利用枠を消費します。
動的ツールAPIは実験的なのでCodex CLI更新時に再検証してください。

公式仕様: [Codex App Server](https://learn.chatgpt.com/docs/app-server)、[Houdini Python Panel](https://www.sidefx.com/docs/houdini/ref/windows/pythonpaneleditor.html)。

## 名前と制作

名前の由来: [PBS — Houdiniの年表](https://cgi.pbs.org/wgbh/amex/houdini/timeline/index.html)。
`BESS` は [Berkeley Extensible Software Switch](https://github.com/omec-project/bess) などでも使用されています。
ソフトウェア内部では `bess_houdini` を用い、短い `bess` モジュール名を登録しません。

制作: 塚本吉彦、2026年日本制作。
Codex通信・会話管理は同著作者の「助人」を基にしています。

## ライセンス

MITライセンスで公開しています。著作権表記は Copyright (c) 2026 塚本吉彦。全文は [LICENSE](LICENSE) を参照してください。
本リポジトリに含まれるコードと文書が対象です。Codex、Houdini、Steam、Houdiniのヘルプ本文は同梱していません。
それぞれの権利と利用条件は各提供元に帰属します。SideFX、OpenAI、Valveの公式製品ではありません。
