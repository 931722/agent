> 此文件描述原開發電腦的專案內工具與 Disk 設定。從 GitHub 下載後，請先依 README 的一般安裝方式操作；模型與虛擬機不包含在儲存庫內。

# 此電腦的專案內執行環境

這次使用官方發行檔放在專案內，沒有寫入 Homebrew 的軟體目錄，也沒有啟用登入後自動常駐服務。使用 Ollama 0.40.16、Podman 5.6.2，均已用各發行版本的官方 SHA-256 清單核對下載檔。原先下載的 Podman 6.2.0 虛擬機啟動失敗，保留供診斷，目前腳本優先使用 5.6.2。這是此電腦的課程展示安排；其他電腦請依 README 使用官方支援的安裝方式重新驗證。

## 位置

- `.local-tools/ollama/`：Ollama 官方命令列執行檔與相依函式庫。
- `.local-tools/podman-5.6.2/podman.pkg/Payload/podman/`：使用中的官方 macOS ARM64 安裝包展開執行檔；沒有執行系統安裝腳本。
- `/Volumes/Disk/file/Ollama/models/`：模型資料，2026-11-22 搬到 Disk 磁碟。
- `~/.ollama/models`：指向上述磁碟資料夾的符號連結，不存放另一份模型。
- `/Volumes/Disk/file/Podman/data/`：Podman 虛擬磁碟、映像、容器及資料卷（容器資料位於虛擬磁碟內）。
- `/Volumes/Disk/file/Podman/config/`：Podman 設定與連線資訊。
- `~/.local/share/containers`、`~/.config/containers`：分別指向上述 Disk 資料夾的符號連結。
- `scripts/ollama-local.sh`、`scripts/podman-local.sh`：專案內啟動入口。

不要把 `.local-tools` 或模型檔提交 GitHub。容器建置也不需要包含這些主機工具。

## Ollama

從專案根目錄執行：

```sh
sh scripts/ollama-local.sh serve
```

啟動腳本已將 `OLLAMA_MODELS` 設為 `/Volumes/Disk/file/Ollama/models`，後續模型下載也使用這個位置。這是 [Ollama 官方支援的模型路徑設定](https://docs.ollama.com/faq#how-do-i-set-them-to-a-different-location)。使用前請接上 Disk；找不到模型資料夾時腳本會停止，不會改下載到本機。使用中不要退出磁碟；先停止 Ollama 再退出。

在另一個終端下載模型（已下載時會重用）：

```sh
sh scripts/ollama-local.sh pull qwen3:4b
```

使用真實模型啟動程式：

```sh
.venv/bin/python -m app --mode ollama serve
```

## Podman

本次使用獨立虛擬機 `kitchen-agent-hw2-v56`，2 CPU、2 GiB RAM、20 GiB 的虛擬磁碟上限（實際占用依資料成長），只指定掛載此專案到 `/workspace`。主機與虛擬機內 Podman 同為 5.6.2。失敗的 `kitchen-agent-hw2`、`kitchen-agent-hw2-stable` 已停止，沒有作業容器資料，不要啟動它們。

2026-11-22 已將 Podman 大型資料搬到 Disk。使用前請接上磁碟；腳本找不到資料時會停止。原本的設定路徑透過符號連結存取，因此啟動指令相同。Ollama 與 Podman 的程式本身仍在專案 `.local-tools`；大型模型、虛擬磁碟與容器資料存於 Disk。執行時仍需要本機記憶體及少量暫存空間。

```sh
sh scripts/podman-local.sh machine start kitchen-agent-hw2-v56
sh scripts/podman-local.sh system connection default kitchen-agent-hw2-v56
sh scripts/podman-local.sh info
sh scripts/podman-start.sh
```

若虛擬機提示 `already running`，表示已啟動，可繼續下一步。`podman-start.sh` 會檢查出餐容器：已運作就提示網頁位址，已停止則啟動既有容器，不會因重複名稱而建立失敗。修改程式後若要重新建置，先停止出餐容器，再執行腳本。

如需重新初始化一部尚不存在的同名機器：

```sh
sh scripts/podman-local.sh machine init --image docker://quay.io/podman/machine-os:5.6 --cpus 2 --memory 2048 --disk-size 20 --volume "$PWD:/workspace" kitchen-agent-hw2-v56
```

停止容器及虛擬機：

```sh
sh scripts/podman-local.sh stop kitchen-agent-hw2
sh scripts/podman-local.sh machine stop kitchen-agent-hw2-v56
```

退出 Disk 前，先依序停止容器、停止 Podman 虛擬機，並停止 Ollama；不要在虛擬機運作中拔除磁碟。

Ollama 若在終端前景執行，以 Ctrl+C 停止。未設定系統開機或登入自動啟動。

## 驗證限制

是否已成功載入模型、執行真實工具流程、啟動 Podman VM 與建置映像，請看 `VALIDATION.md`，不能單以存在執行檔判定驗證成功。

本次已完成上述驗證及正常重啟測試。網頁位址為 `http://127.0.0.1:8000`。保留的展示資料在第 6 分鐘：O001 烹調已完成、出餐可排程，O002 烹調已保留。可在「最近的 Agent 紀錄」查看先前真實模型流程；歷史提案只供檢視，接續派工請提出新的需求。

每次本機模型提問可能需要約一至兩分鐘。請等待結果，不必重複送出。停止後重新展示時，先在一個終端啟動 Ollama，在另一個終端啟動上述 Podman 虛擬機與專案腳本；若服務已啟動，就不需重複啟動。

## 從頭重跑模擬

在網頁上方按「重置模擬」，閱讀確認訊息後確認。系統會先完整備份目前資料庫（含訂單、工序、提案、事件及 Agent 紀錄），再恢復初始三張訂單、第 2 分鐘、初始設備與廚師狀態，並清空目前提案、事件及 Agent 紀錄。狀態版本會繼續增加，避免舊提案重新變有效。

備份保存於容器 `/app/data/backups/`，與資料庫同在 Disk 的 `kitchen-agent-data` 資料卷內；成功訊息提供下載連結。每次重置保留獨立備份，不覆寫之前備份。備份失敗會保留原資料；模型正在回答時暫時不能重置。尚無網頁還原備份功能，請保留需要的備份檔。
