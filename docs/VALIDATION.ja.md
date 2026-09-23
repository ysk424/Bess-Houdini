# 検証結果

2026-09-24、Windows / Steam版Houdini Indie **22.0.429** / Python **3.13.10** / PySide6 **6.8.3** / Codex CLI **0.156.1**。

| 検証 | 結果 |
| --- | --- |
| HOMテスト7件 | 成功。Box作成・寸法変更・コンテキスト取得、例外と部分変更、読み取り専用、別スレッド拒否、停止／古いturnの拒否、追加指示の失敗処理、履歴、同梱ヘルプ |
| インストーラー／MCP設定テスト2件 | 成功。dry-run、対象行だけの変更、バックアップ、再実行、CLIの設定キー |
| Qtオフスクリーン描画 | 成功。通常幅と狭い幅、日本語複数行、モデルプリセット |
| 実App Server・モデル呼び出しなし | 成功。ChatGPT認証、モデル一覧、動的ツール登録、MCPツール無効化 |
| 実GPT-6 Sol / medium | 成功。内部ツールでバージョン確認、GeometryとBoxを作成、size=(1,2,3)をHOMで確認 |
| 実GPT-6 Luna / medium | 成功。切断後に読み取り専用で会話再開、前のノード名を回答 |
| Houdini実GUI | 成功。Python Panel登録・表示・接続、Undo／Redo、PNG画面取得、パネル破棄時のCodex終了。テストHoudini終了コード0 |

新規hythonと新規GUIプロセスを使い、利用者の既存作品は編集していません。
モデルによる実接続検証では2回の会話送信を行いました。

同日、Python Panelのメニュー表示指定漏れを修正。`includeInToolbarMenu` と `includeInPaneTabMenu` を追加し、
モデルに接続しない新規GUI検証 `tests/menu_smoke.py` で `hou.pypanel.menuInterfaces()` の先頭が `bess_houdini` になることを確認しました。
既存のGUIテストにもメニュー登録の検証を追加しています。

## 再実行

```powershell
$bessHython = 'C:/Program Files (x86)/Steam/steamapps/common/Houdini Indie/bin/hython.exe'
& $bessHython tests/houdini_smoke.py
& $bessHython tests/install_smoke.py
& $bessHython tests/qt_smoke.py
& $bessHython tests/app_server_smoke.py
# 以下だけモデル利用枠を消費
& $bessHython tests/app_server_smoke.py --live
```

GUI検証は `tests/gui_smoke.py`。必ず新規テストプロセスで使用してください。シーンにテスト用ノードを作り、自動終了します。
設定フォルダーは `test-output/gui-prefs22.0` へインストールし、子プロセスの `HOUDINI_USER_PREF_DIR` は
`<repo>/test-output/gui-prefs__HVER__` とします。Houdiniはこの環境変数に `__HVER__` がないと無視します。
`BESS_TEST_ROOT=<repo>`、`SteamAppId=502570` を子プロセスに設定し、Houdini Indieのインストール先を作業フォルダーとして、
`bin/hindie.steam.exe -foreground waitforui <repo>/tests/gui_smoke.py` を起動します。
結果は `test-output/gui-result.json`、画面は `test-output/houdini-panel.png` と `houdini-window.png`。
正常判定ではJSONに加えてプロセス終了コード0を確認してください。

## 範囲と限界

- 実GUIではパネルの表示・接続・操作・画像・終了を検証。入力については下記の追加検証を参照。OSの日本語IMEの実際のキー操作と、モデルによる画像内容の認識は未検証。
- 応答中の追加指示は受理／拒否を処理する実装と拒否時のテストあり。実モデルに対する追加指示・停止のタイミング競合は未検証。
- 長時間シミュレーション、レンダー、専用ジョブ管理、強制停止は初版の検証対象外。
- Astraの実応答は未検証。モデル一覧で利用候補として取得できることは確認。
- 動的ツールAPIは実験的。Codex CLI更新時の互換性を保証しません。

## 入力フォーカスの修正

2026-09-24、Houdini内のドッキングしたPython Panelで、入力欄のクリック後にフォーカスがルートの `BessPanel` へ移り、入力できない症状を再現。
ルートのフォーカスプロキシを文字入力欄に設定し、読み取り専用状態も変更がある場合だけ更新するよう修正しました。
`tests/gui_input_smoke.py` はCodex接続を差し替えた新規GUIで、QtTestによるクリック、更新タイマー後のフォーカス維持、半角キー入力、Enter改行、
日本語のIME確定イベント、入力内容の維持を検証します。修正前はフォーカスの検証が失敗し、修正後は成功・終了コード0を確認しました。

## IME変換中の入力への対策

同日、実際のIMEで3文字以上を変換できないという報告に対応し、入力欄をサブクラス化していたCtrl+Enter判定を削除しました。
入力欄は標準 `QPlainTextEdit` とし、案内文を欄外のラベルへ移動。送信はボタンで行います。
50msのタイマーはCodexの通信受信に使いますが、状態が変わらない間はUI更新を行わず、
受理待ちの途中にも入力欄の読み取り専用状態を変更しません。

`tests/ime_smoke.py` で未確定文字を「に」から「日本語の入力を確認しています」まで段階的に送り、
タイマーと応答表示の更新を挟んでも未確定文字・フォーカスが維持され、最後に全文を確定できることを確認しました。
受理待ち中の追加入力、状態不変時にUIのsetterを呼ばないことも検証しています。
これらはQtのIMEイベントを使うテストであり、実際のWindows IME候補ウィンドウを操作した検証ではありません。
Houdini実GUIのドッキングしたPython Panelでも同じ段階的な未確定入力を検証し、
「hello＋改行＋日本語の入力を確認」の保持、設定欄から戻った後の入力フォーカスを確認しました。テストプロセスは終了コード0です。

その後の利用者による実IME検証では、入力欄へのフォーカス移動前後でIMEモードが一致している場合に入力でき、
一致していない場合に入力できないことが報告されました。Bessは入力モードを明示的に設定していません。
フォーカス後にIMEモードを合わせる回避方法をREADMEに記載しています。人工的なIMEイベントのテストだけでは、この症状を再現できません。
