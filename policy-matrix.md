# 安全策略決策矩陣 (Policy Decision Matrix - Bonus 1)

本矩陣定義 GitHub Agentic Workflows `approve-workflow-run` Safe-Output Handler 在接收到 Agent 核准請求時，底層 Deterministic Policy Gate 的判定真值表（Truth Table）。

---

## 1. 策略判定維度定義

- **`Fork Allowed (F)`**: Safe-output 設定是否明確啟用 `fork: true`。
- **`Workflow Allowed (W)`**: 目標 Workflow 是否在 `allowed-workflows` 白名單清單內。
- **`PR Authorized (P)`**: 目標 PR 是否在 `allowed-pull-requests` 範圍內。
- **`Protected Files Clean (C)`**: PR 是否**未**修改任何受保護之機密/工作流程檔案（`Clean = true` 表示無違規修改）。
- **`Run State Waiting (S)`**: 目標 GitHub Actions Run 是否處於 `waiting / action required / awaiting approval` 狀態。

---

## 2. 決策真值矩陣表 (Decision Truth Table)

| 情境編號 | Fork 啟用 (`F`) | 白名單命中 (`W`) | PR 授權範圍 (`P`) | 無保護檔案修改 (`C`) | 處於 Waiting 狀態 (`S`) | 最終裁決 (Verdict) | 阻斷原因 / 處理邏輯 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **S01** | `true` | `true` | `true` | `true` | `true` | **`ALLOW`** | **唯一合法核准路徑**：呼叫 GitHub Approval API。 |
| **S02** | `false` | `true` | `true` | `true` | `true` | **`DENY`** | 拒絕：未授權 Fork PR 執行（預設安全策略）。 |
| **S03** | `true` | `false` | `true` | `true` | `true` | **`DENY`** | 拒絕：Workflow 不在 `allowed-workflows` 白名單。 |
| **S04** | `true` | `true` | `false` | `true` | `true` | **`DENY`** | 拒絕：PR 編號超出授權範圍。 |
| **S05** | `true` | `true` | `true` | `false` | `true` | **`DENY`** | 拒絕：PR 包含 `.github/workflows/` 等敏感檔案變更。 |
| **S06** | `true` | `true` | `true` | `true` | `false` | **`DENY`** | 拒絕：Run 非處於 Waiting 狀態（可能已完成或取消）。 |
| **S07** | `false` | `false` | `any` | `any` | `any` | **`DENY`** | 拒絕：多重條件違規，直接阻斷。 |

---

## 3. 安全架構原則與不可違背條件

1. **短路求值與全條件通過原則 (All-AND Gate)**：
   - 決策邏輯為嚴格的五元邏輯交集：
     $$\text{Decision} = F \land W \land P \land C \land S$$
   - 任何一項為 `false`，Handler 立即終止並拋出 `DENIED` 錯誤，不與 GitHub Write API 進行通訊。
2. **Prompt-Independent Security**：
   - 即使 Agent 因 Prompt Injection 產生幻覺或惡意輸出 `approve_workflow_run`，Handler 仍透過本矩陣強制執行冷酷的規則檢驗，實現真正的架構層防禦。
