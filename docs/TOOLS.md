# 作業二工具定義

三個 Agent 工具都是真正可執行的 Python 功能。模型只能選擇已註冊的名稱；參數由 Pydantic 嚴格驗證，額外欄位與不正確型別會被拒絕。完整 JSON Schema 見 `evidence/tool-schemas.json` 或 `/api/tools`。

| 名稱 | 目的 | 輸入 | 輸出 |
| --- | --- | --- | --- |
| `get_kitchen_state` | 讀取當前營運事實 | 空物件 `{}` | 模擬時間、版本、訂單、工序、工作站、廚師 |
| `propose_schedule` | 依 FIFO 及雙重資源限制建立派工建議 | `state_version` 必填整數；`strategy` 僅接受 `fifo` | 提案 ID、狀態版本、候選指派、工時、優先理由及受阻工序 |
| `get_order_risks` | 查詢指定或全部訂單的完成狀態及延誤風險 | 可選 `order_id` | 原承諾時間、完成狀態、最早完成下界及限制說明 |

## 錯誤處理

統一結構：

```json
{"ok": false, "error": {"code": "STALE_STATE", "message": "廚房狀態已改變，請重新查詢再排程。"}}
```

- `INVALID_ARGUMENTS`：缺欄位、額外欄位、不支援的策略或型別不符；不執行工具內容。
- `UNKNOWN_TOOL`：模型要求未註冊或寫入工具；拒絕執行。
- `STALE_STATE`：呼叫者的版本與資料庫不同；重新查詢再計算。
- `NO_FEASIBLE_TASK`：沒有就緒且能同時取得設備與廚師的工序；回傳阻塞原因，不能編造指派。
- `UNKNOWN_ORDER`：無此訂單；回報錯誤並要求正確編號。

## 排程步驟

1. 從 `READY` 工序中依就緒時間、訂單接受時間、穩定工序 ID 排序。
2. 排除已保留或執行中的資源，查找相容且可用的工作站與廚師。
3. 同批次每選一項即更新暫時占用集合，避免同人或同站出現兩次。
4. 沒有資源的高順位任務不阻擋其他可行任務。
5. 保存提案但不正式占用資源；人工確認時在寫入交易重新檢查版本及結果，再共同保留設備與廚師。

## 人工操作端點

`POST /api/proposals/{id}/confirm`、`POST /api/events`、`POST /api/orders`、`POST /api/clock` 不在 LLM 工具清單中。只供本機介面與測試使用，不能把模型輸出的工具名稱直接路由到這些端點。

同一提案重複確認只生效一次。同一事件 ID 重送回傳原結果；若 ID 相同但內容不同，拒絕為 `EVENT_ID_CONFLICT`。工序須先保留再開始，先開始才可完成。故障工作站若有執行或保留中的任務，返回 `ACTIVE_WORK_REQUIRES_REVIEW`；雛形尚無完整安全中止流程。

## 狀態與時間

`WAITING → READY → RESERVED → RUNNING → DONE`。

`WAITING` 表示前置工序尚未完成；`READY` 只代表依賴滿足，不代表目前能取得設備與廚師。`RESERVED` 已共同保留資源但尚未開工。所有標準工時與承諾時間皆以模擬分鐘表示，完成以人工事件為準。
