# 作業二驗證紀錄

驗證日期：2026-11-21。全部使用虛構訂單，沒有連接真實餐廳。

## 已確認的本機環境

- Apple M4、16 GiB 記憶體、macOS ARM64。
- Python 3.14.7，依賴版本見 `requirements.txt`。
- Ollama 0.40.16，模型 `qwen3:4b`，Q4_K_M，下載大小 2,497,293,931 bytes。
- 模型 digest：`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`。
- Ollama 原生 `/api/chat`、實際 GPU 載入與工具循環均已執行，沒有使用雲端模型，也沒有切換成 demo。

## 自動測試與工具證據

本機 39 個測試通過，報告見 `evidence/pytest-results.xml`；容器內同樣 39 個測試通過，見 `evidence/container-pytest.txt`。兩者都有一個 Starlette/httpx 測試用戶端棄用警告，不影響目前測試，但未來升級應重新檢查。測試包含資源互斥、前置工序、並行確認、事件去重、狀態持久化、版本過期、錯誤參數、模型故障、呼叫上限與回答保護。

`demo-*` 是固定規則測試替身；不得當作真實模型證據。`stale-proposal.json` 是資料庫交易層實測。`ollama-unavailable.json` 是對刻意未開啟的本機端點實際發送 HTTP 後取得的失敗。

## 真實模型結果

- `evidence/ollama-success.json`：模型先查狀態，再呼叫 FIFO 提案；初次成功測量為兩次工具呼叫、約 71 秒。
- `evidence/container-ollama-success.json`：修正提示與工具說明後，在 Podman 內完整實測約 85 秒、兩次工具呼叫。最終回覆正確列出兩項提案與就緒時間優先原因；這份作為主要成功展示紀錄。
- `evidence/ollama-no-resources.json`：停用炒台與湯台後，工具回報 `NO_FEASIBLE_TASK`。
- `evidence/ollama-unknown-order.json`：查詢 O999，工具回報 `UNKNOWN_ORDER`。
- 失敗案例可用 `scripts/verify_live_agent.py` 重跑。每次使用獨立資料庫，驗證錯誤碼且廚房狀態未變。

## 實測發現與修正

1. 模型曾將 `fifo` 寫成 `FIFO`：嚴格參數驗證拒絕，模型可讀取錯誤後修正。系統提示已強調小寫。
2. 模型曾在 `content` 中輸出思考標記：程式過濾已識別的標記內容，不將其當作公開回覆；相應測試已加入。
3. 模型曾混淆設備停用與資源佔用：排程工具現在提供更明確的受阻原因。
4. 模型曾在無可行任務後仍建議確認派工：最後一個工具失敗時，改由程式依工具資料產生可見錯誤回覆，原公開回答留在 `model_answer` 供分析。
5. Ollama 在受限執行環境中無法使用 Metal，改以正常主機程序啟動後已成功載入 GPU。

模型仍可能用詞不精確。`completed` 只代表工具流程走完，不代表自然語言每句均正確；派工資料以工具回傳為準，人工確認仍會重新檢查狀態。小模型目前回應需要數十秒到約兩分鐘，這是課程雛形，尚未做效能優化。

## Podman 驗證

映像建置已成功，映像 ID 見 `evidence/container-image.txt`。容器內 39 個測試通過，且可由 `host.containers.internal:11434` 讀到主機已安裝的 qwen3:4b；Ollama 維持只監聽主機回送位址，沒有為此開放區域網路。

`evidence/container-workflow.json` 記錄完整 API 流程成功：真實模型查詢及提案 → 人工操作端點確認兩項派工 → O001 烹調開工 → 推進四分鐘 → 完成烹調 → 後續出餐工序變成 READY。測試可由 `scripts/verify_running_app.py` 對**全新的展示資料卷**重跑，會修改該虛構廚房狀態，不應直接用於已操作過的資料庫。

正常停止容器及虛擬機後，重新啟動虛擬機並以同一命名資料卷建立新容器；狀態與重啟前完全一致，原 Agent 紀錄仍可讀取。證據見 `evidence/container-restart.json`。此測試也發現並修正啟動腳本不能重用既有資料卷的問題。

瀏覽器實測可讀到真實模型紀錄與重啟後工序狀態；歷史提案標示「僅供檢視」，不顯示確認按鈕。最新容器版本再次通過 39 個測試。

Podman 6.2.0 的官方機器映像在首次開機遇到 Ignition 建立使用者失敗（`cannot lock /etc/group`）。相同症狀有[上游問題回報](https://github.com/podman-container-tools/podman/issues/28439)，但不能據此斷定本機原因完全相同。用 6.2 初始化、5.6 啟動的混合嘗試也沒有穩定運作；最後用 5.6.2 執行檔初始化及啟動 5.6 官方映像的 `kitchen-agent-hw2-v56` 成功，主客端均為 5.6.2。舊機器已停止且未刪除。這是本次測得可運作的組合，不代表建議在正式服務長期使用舊版環境。

## 尚需完成的繳交動作

- 將原始碼、文件與經確認的證據提交自己的 GitHub repository，提供網址給老師與助教。
- 本專案尚未自動建立或上傳 GitHub repository。

## 2026-11-22 模型移至 Disk

依使用者要求，將模型移到 `/Volumes/Disk/file/Ollama/models`。先保留內部相對連結複製，逐檔核對 SHA-256，再重啟 Ollama 並確認實際模型程序使用 Disk 路徑。qwen3:4b 完成一次 32-token 推論測試後，再次核對來源與目的檔案，移除本機副本。

已搬離本機的模型資料共 2,497,301,536 bytes（約 2.50 GB）。`/Users/eason/.ollama/models` 現在僅為指向 Disk 的符號連結；啟動腳本設定同一路徑，找不到磁碟資料夾時會停止。此變更未修改 Agent 工具與排程邏輯，驗證項目為腳本語法、檔案完整性、模型實際載入位置與推論。

## 2026-11-22 Podman 資料移至 Disk

將 `~/.local/share/containers` 的全部資料（含三部虛擬機、機器映像快取及 SSH 身分檔）複製到 `/Volumes/Disk/file/Podman/data`；`~/.config/containers` 複製到 `/Volumes/Disk/file/Podman/config`。兩個原路徑改成符號連結，保留現有設定中的絕對路徑。稀疏磁碟逐塊複製，所有一般檔案逐檔核對 SHA-256；已停止虛擬機留下的 socket 不複製，由啟動程序重建。

從 Disk 啟動 `kitchen-agent-hw2-v56` 後，確認原映像 ID 與資料卷建立時間相同；重新啟動出餐容器，廚房狀態與搬移前完全一致，原成功 Agent 紀錄可讀取。`lsof` 確認虛擬機實際開啟 `/Volumes/Disk/file/Podman/data/podman/machine/applehv/kitchen-agent-hw2-v56-arm64.raw`。驗證通過後移除本機重複備份，摘要見 `evidence/podman-disk-migration.json`。

啟動腳本已加入磁碟資料夾檢查；請先接上 Disk，並在退出磁碟前停止容器、虛擬機與 Ollama。此次為儲存位置調整，驗證資料完整性與實際啟動／狀態保留，未更改 Agent 或排程演算法。

## 2026-11-22 網頁備份後重置

新增「重置模擬」按鈕與網頁內確認視窗。`POST /api/simulation/reset` 需帶目前狀態版本；重置時取得 SQLite 寫入交易，先以獨立讀取連線建立完整備份並檢查完整性，成功後才恢復初始廚房與清除提案、事件、Agent 紀錄。備份失敗會回報錯誤且不重置。狀態版本持續增加，避免重用舊版本。模型正在處理時拒絕重置；重置操作未暴露為模型工具。

本機與新版 Podman 容器均通過 43 個測試。新增測試覆蓋備份內四張資料表、重置後持久化、舊提案失效、備份失敗不改資料、備份下載、過期版本、跨來源拒絕及模型忙碌時拒絕重置。沿用一個 Starlette/httpx 棄用警告。

以 happy-dom 執行實際前端腳本，連接獨立 8001 測試服務：取消後狀態不變；確認後從第 7 分鐘、四張訂單恢復第 2 分鐘、三張訂單，清空一筆 Agent 紀錄；備份下載回傳有效 SQLite，按鈕狀態恢復。此為 DOM 互動與 HTTP 整合驗證；原生瀏覽器確認視窗測試遇到自動化限制，最終改用網頁內 dialog，尚未完成最終版本的原生瀏覽器點擊驗證。正式 8000 資料未執行重置，只更新容器；備份會存於 Disk 資料卷的 `/app/data/backups/`。

## 2026-11-22 工作站占用狀態顯示

工作站卡片改由實際 RESERVED/RUNNING 工序判定「已保留／製作中」，無活動工序時顯示「空閒」，設備停用時顯示「已停用」。活動工序另列訂單、菜色、階段、廚師；工作中停用按鈕禁用。設備啟用文字另列，避免把設備開關與占用狀態混淆。

以獨立 Store 產生空閒、保留、製作、完成、停用五個狀態，再透過 happy-dom 執行實際前端腳本，五種卡片文字、工序資訊與按鈕可用狀態均符合預期。JavaScript 語法檢查通過。新版容器已啟動，靜態資源版本更新；API 回傳的現有廚房狀態與更新前完全一致。本次僅調整顯示，未更改排程邏輯。
