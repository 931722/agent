# 作業二失敗情境與證據

以下區分「模型連線失敗」「工具失敗」與「規則模擬」，不把固定規則執行結果寫成真實 LLM 推理成果。可執行 `python scripts/export_evidence.py` 重新產生證據；腳本使用臨時資料庫。

## 案例一 所有相容烹調工作站停用

- 輸入：停用 `wok-1`、`soup-1`，再要求「安排下一批工作」。
- 原因：有就緒工序，但沒有相容且可用的工作站。
- 觀察：狀態查詢成功；排程工具返回 `NO_FEASIBLE_TASK`、空指派及每個受阻工序的理由，Agent 回報問題而沒有指派不存在的設備。
- 處理：現場確認設備恢復後重新查詢與產生提案；不跳過資源限制。
- 證據：`evidence/ollama-no-resources.json` 是真實本機模型流程；`evidence/demo-no-resources.json` 是固定規則工具測試，兩者分開保存。

## 案例二 產生提案後設備狀態變更

- 輸入：在版本 1 產生 FIFO 提案，接著停用炒台，再確認舊提案。
- 原因：提案依據的資源狀態已過期。
- 觀察：確認被拒絕為 `STALE_STATE`，不產生部分保留或重複派工。
- 處理：重新查詢、重算，再由使用者確認新提案。
- 證據：`evidence/stale-proposal.json`，以及並行確認測試 `test_two_concurrent_proposals_only_one_reserves`。此為真實工具／交易層測試，非模型執行紀錄。

## 案例三 Ollama 連線失敗

- 輸入：對刻意未啟動服務的本機端點送出「安排下一批工作」。
- 原因：Ollama 不可連線，例如未啟動、位址錯誤或容器無法連線到主機。
- 觀察：返回 `MODEL_UNAVAILABLE`，工具呼叫次數為 0；保留 `mode=ollama`，不自動變成 demo。
- 處理：啟動 Ollama、確認模型已下載，或修正容器主機連線位址後再執行。
- 證據：`evidence/ollama-unavailable.json`。這是實際發送 HTTP 後的失敗，不是成功使用模型。

## 其他已測行為

另以真實模型詢問不存在的訂單 O999，`get_order_risks` 返回 `UNKNOWN_ORDER`，模型說明無資料並要求核對編號。證據為 `evidence/ollama-unknown-order.json`。

錯誤參數被拒絕、模型未註冊工具被拒絕、工具循環達上限即停止、完成事件重送只生效一次、估計工時到達不會自動完成工序。模型逾時時返回 `MODEL_TIMEOUT`；找不到模型時返回 `MODEL_NOT_FOUND`。

以 `.venv/bin/python scripts/verify_live_agent.py` 可重新執行兩種真實模型失敗情境。每次使用獨立的虛構資料庫，不修改正在展示的營運狀態。腳本檢查預期錯誤碼及狀態未變；實際測量與限制見 `VALIDATION.md`。
