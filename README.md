# 智慧中餐館出餐排程 Agent

作業二報告：[Word 文件](docs/智慧中餐館出餐排程Agent_作業二報告.docx)

GitHub：https://github.com/931722/agent

作業二的可執行雛形：使用本機 Ollama 理解店員需求，呼叫真正的 Python 工具，查詢廚房、建立 FIFO 派工提案與檢查訂單風險。介面提供人工確認、開工及完成回報，並保存完整的可觀察工具軌跡。

**資料都是虛構的單店模擬資料。** 時間由按鈕推進，並非真實餐廳。`demo` 是固定規則測試替身，不是 LLM；不會在 Ollama 出錯時自動切換模式。

## 作業二對照

| 課程要求 | 本專案對應 |
| --- | --- |
| 可執行 Agent 原始碼 | `app/agent.py`、`app/__main__.py`、`app/main.py` |
| 至少一個真實 Tool | `app/tools.py` 的三個工具，呼叫資料庫及 FIFO 排程程式 |
| Tool 名稱、目的、輸入、輸出、錯誤處理 | `docs/TOOLS.md`、`GET /api/tools` |
| 輸入 → 決策 → Tool → Observation → 回覆 | 頁面執行流程、`GET /api/traces/{id}`、CLI JSON 輸出 |
| 至少兩個失敗案例 | `docs/FAILURE_CASES.md`、`docs/evidence/` |
| 狀態與記憶 | SQLite 保存營運狀態、事件、提案、執行紀錄；每次對話獨立 |
| Podman | `Containerfile`、`scripts/podman-start.sh` |
| README、執行環境及測試 | 本文件、`requirements.txt`、`tests/` |
| GitHub repository link | https://github.com/931722/agent，提交網址給老師與助教 |

目前的驗證結果和仍未驗證項目請看 `docs/VALIDATION.md`。第一次規劃與本次範圍差異見 `docs/HOMEWORK2.md`。

## 快速開始

需要 Python 3.11 以上；目前依賴鎖定版本以 Python 3.14 驗證。從專案根目錄執行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

若只想先測試工具與畫面，明確指定模擬模式：

```sh
.venv/bin/python -m app --mode demo serve
```

開啟 <http://127.0.0.1:8000>。第一次使用新資料庫會建立三張訂單、三個工作站、兩位廚師與五種菜色。

## 使用本機 Ollama

安裝 [Ollama](https://ollama.com/download/mac)，啟動服務，下載支援工具呼叫的模型。此專案預設 `qwen3:4b`，官方標示下載約 2.5 GB；可依硬體改用另一個支援 tool calling 的模型，換模型後要重新測試。

```sh
ollama serve
```

在另一個終端：

```sh
ollama pull qwen3:4b
.venv/bin/python scripts/doctor.py
.venv/bin/python -m app serve
```

若 `ollama serve` 顯示通訊埠已占用，先確認是否已有 Ollama 服務，不要重複啟動。

`.env` 預設如下：

```dotenv
AGENT_MODE=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT=120
MAX_TOOL_CALLS=6
DB_PATH=data/kitchen.sqlite3
```

Ollama 原生 `/api/chat` 接受 `tools`，模型提出工具呼叫後由程式驗證並執行，再把結果送回模型。系統不執行模型任意產生的 Python、SQL 或 shell。參考 [Ollama Tool calling](https://docs.ollama.com/capabilities/tool-calling)。

若此電腦使用專案內的官方執行檔，請看 `docs/LOCAL_SETUP.md`，不需要把專案路徑寫進全系統設定。

## 展示流程

1. 提問「請安排下一批工作，說明優先原因」。
2. 展開執行流程：`get_kitchen_state` 應先取得版本，再由 `propose_schedule` 產生提案。
3. 初始狀態可同時派 O001 蛋炒飯給阿明與炒台一，以及 O002 蛋花湯給小陳與湯台一。
4. 按「確認派工」，兩項工作變成已保留。提案過期時會拒絕，需重新排程。
5. 按「開工」，再手動推進模擬時間。工序**不會**因估計時間到達而自動完成。
6. 按「完成」，該工序釋放資源，後續出餐工序變成可排程。
7. 再次要求排程，確認系統依新狀態決策。
8. 下載 JSON 執行紀錄。交作業前確認紀錄的 `mode` 是 `ollama`、包含真實工具呼叫與有效結果；`demo` 只能說明測試環境。

文字查詢每次獨立，不保留前一次聊天上下文；「剛才那張單」請改用明確訂單編號。廚房狀態仍持續保存在資料庫。

## 重置模擬

網頁上方按「重置模擬」，再按「備份並重置」。系統先保存完整 SQLite 備份，才恢復初始三張訂單與第 2 分鐘，清空目前派工、事件及 Agent 紀錄。成功訊息提供備份下載連結；備份保留於資料卷 `backups/`，每次獨立保存。備份失敗時不重置，模型回答中暫時不能重置。狀態版本持續增加以防舊提案失效後重新有效。

## CLI 與證據匯出

```sh
.venv/bin/python -m app --mode demo --db work/demo-cli.sqlite3 chat '安排下一批工作' --output work/demo-trace.json
.venv/bin/python -m app --mode ollama --db work/live-cli.sqlite3 chat '請安排下一批工作，說明優先原因' --output docs/evidence/ollama-success.json
.venv/bin/python scripts/export_evidence.py
```

成功 CLI 正常結束；模型或工具失敗返回非零狀態。匯出腳本在臨時資料庫產生獨立案例，不會修改操作中的資料庫。

執行紀錄包含輸入、工具選擇、名稱與參數、觀察到的工具結果、最後回覆、模式、模型、時間和錯誤碼。只保存可觀察的決策與操作，不保存模型隱藏推理。

最後一個工具失敗時，程式會依錯誤碼與工具資料產生可見回覆，避免模型在失敗後仍要求確認派工。此時 `answer_source=tool_error_guard`，`model_answer` 保留模型的公開原回答，便於比較及失敗案例分析。`thinking` 欄位及 `<think>` 標記內文字不保存；模型被截斷而沒有公開回答時，記錄為失敗。

## 用 Podman 執行

安裝 [Podman](https://podman.io/docs/installation)。macOS 需要 Linux 虛擬機：

```sh
podman machine init
podman machine start
podman info
```

先停止占用 8000 的本機開發服務，保持 Ollama 運作，再執行：

```sh
sh scripts/podman-start.sh
```

腳本會建置映像、建立命名資料卷，並將網頁只映射到本機 `127.0.0.1:8000`。容器中的模型位址為 `http://host.containers.internal:11434`，不能用容器自己的 `127.0.0.1`。不同 Podman VM／主機環境可能需要調整 Ollama 監聽或網路設定；以容器內實際連線測試為準。

先驗證不需模型的容器流程：

```sh
AGENT_MODE=demo sh scripts/podman-start.sh
```

容器內執行同一套測試：

```sh
podman run --rm kitchen-agent:hw2 python -m pytest -q
```

停止正在執行的容器：

```sh
podman stop kitchen-agent-hw2
```

命名資料卷保留訂單和紀錄。需要全新資料時使用新的資料卷名稱，不要為了重跑展示刪除尚未備份的紀錄。

## 測試

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest --junitxml=docs/evidence/pytest-results.xml -q
```

測試覆蓋 FIFO、雙資源互斥、工序依賴、同時確認、資料重啟恢復、事件去重、非法操作、過期狀態、工具參數、未知工具、模型錯誤和呼叫上限。測試成功不等於已完成真實 LLM 或 Podman 測試；三者分別記錄。

## 架構與限制

```text
文字需求 → Ollama 選工具 → Python 工具驗證 → SQLite 查詢／FIFO 演算法
                              ↓                    ↓
                         工具結果 ← 派工提案與限制
                              ↓
                         Ollama 整理回覆
                              ↓
                     人工確認 → 開工 → 完成
                              ↓
                     SQLite 更新與下一次查詢
```

- 本次是單一 Agent 加受控 Tool Use，不宣稱實作完整 ReAct；不需要加入所有課程技術。
- 排程是**當下可開工的一批** FIFO 建議；不是全域最佳化，也沒有 Hybrid、SJF、EDF 比較。
- 每份菜簡化為「烹調 → 出餐」兩階段；工序全程占用一站一人，不含備料、合鍋、清潔、無人燉煮或品質保溫最佳化。
- 每個請求讀取最新資料，建立提案不保留資源；人工確認時在同一 SQLite 寫入交易重新驗證，避免重複派工。
- 工具不允許 LLM 確認派工或直接寫入營運狀態，這些是介面／API 操作。
- 目前「最早完成下界」忽略資源競爭，**不是 ETA**；不以重算掩蓋原承諾時間。
- 僅供本機單人課程展示，沒有多使用者登入及角色權限，不應公開到網路或接真實餐廳。
- 以 SQLite 取代規劃中的 PostgreSQL，減少單店雛形部署元件；不代表多店可擴展架構。

## GitHub 繳交

建議納入 `app/`、`tests/`、`scripts/`、`docs/`、`Containerfile`、`.containerignore`、`.env.example`、`requirements.txt`、`pyproject.toml` 與本 README。不要上傳 `.env`、模型、虛擬環境或包含未公開營運資料的 SQLite 檔。提供你的 repository URL 給老師及助教；本專案不會自動建立公開儲存庫。
