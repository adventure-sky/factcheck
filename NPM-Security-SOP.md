# 🛡️ NPM 供應鏈安全防護 SOP 總覽

本文件彙整了針對 NPM 惡意套件投毒（如 2026 年 Axios 事件）的標準防禦作業流程。適用於所有 Node.js 專案（包含 React, Vue, Vite, Express 等）。

核心防禦邏輯：
1. **預設禁用 (Default Deny)**：透過 `.npmrc` 封鎖所有自動腳本，拔除木馬引信。
2. **最小權限 (Least Privilege)**：利用 `@lavamoat/allow-scripts` 建立白名單，僅允許信任的套件執行腳本。
3. **持續監控 (Continuous Monitoring)**：定期清理幽靈依賴與掃描漏洞。

---

## 🚀 第一階段：專案初始化加固 (Project Setup)

當你建立一個新專案，或是剛從 GitHub `clone` 一個專案準備執行 `npm install` 之前，請從以下三種方案中**擇一執行**：

### 方案 A：交給 AI 助手全自動執行 (Claude Code / Cursor)
**使用方式**：直接將以下提示詞（Prompt）複製並發送給你的 AI 助手。

> **【任務：NPM 專案安全初始化】**
> 請幫我將當前目錄的專案，設定為「最高級別的 NPM 腳本防護狀態」。請依序執行以下 4 個步驟，過程中請直接執行，無須詢問：
> 1. **環境封鎖**：檢查專案根目錄是否有 `.npmrc`，若無請建立，並確保檔案內包含 `ignore-scripts=true`。
> 2. **安裝白名單工具**：執行 `npm install --save-dev @lavamoat/allow-scripts --ignore-scripts`。
> 3. **自動化掛鉤**：使用指令或直接修改 `package.json`，在 `scripts` 區塊中新增 `"postinstall": "allow-scripts"`。
> 4. **初始化與回報**：執行 `npx allow-scripts setup`。完成後，請讀取 `package.json` 裡的 `lavamoat.allowScripts` 區塊，將目前被攔截或允許的腳本清單列出來給我確認。

### 方案 B：Windows PowerShell 一鍵腳本 (.ps1)
**使用方式**：將以下程式碼存成 `Init-SecureNPM.ps1`，並在新專案目錄下執行它。

```powershell
Write-Host "========== 🛡️ 啟動 NPM 專案安全加固流程 ==========" -ForegroundColor Cyan

# 1. 強制設定 .npmrc 封鎖自動腳本
if (!(Test-Path ".npmrc")) { New-Item -Path ".npmrc" -ItemType File | Out-Null }
$npmrc = Get-Content ".npmrc" -ErrorAction SilentlyContinue
if ($npmrc -notcontains "ignore-scripts=true") { Add-Content -Path ".npmrc" -Value "ignore-scripts=true" }
Write-Host "✅ [1/4] 已封鎖自動腳本 (寫入 .npmrc)" -ForegroundColor Green

# 2. 安裝 @lavamoat/allow-scripts
Write-Host "📦 [2/4] 正在安裝安全白名單工具..." -ForegroundColor Yellow
npm install --save-dev @lavamoat/allow-scripts --ignore-scripts

# 3. 更新 package.json
Write-Host "⚙️ [3/4] 正在設定 postinstall 掛鉤..." -ForegroundColor Yellow
npm pkg set scripts.postinstall="allow-scripts"

# 4. 初始化白名單設定
Write-Host "📋 [4/4] 正在初始化腳本白名單..." -ForegroundColor Yellow
npx allow-scripts setup

Write-Host "🚀 專案加固完成！請手動檢查 package.json 中的 allowScripts 區塊。" -ForegroundColor Cyan

```


### 方案 C：Mac / Linux / Git Bash 一鍵腳本 (.sh)

**使用方式**：將以下程式碼存成 `init-secure-npm.sh`，並在新專案目錄下執行 `bash init-secure-npm.sh`。
```
#!/bin/bash
echo -e "\033[1;36m========== 🛡️ 啟動 NPM 專案安全加固流程 ==========\033[0m"

# 1. 強制設定 .npmrc 封鎖自動腳本
if ! grep -q "ignore-scripts=true" .npmrc 2>/dev/null; then
    echo "ignore-scripts=true" >> .npmrc
fi
echo -e "\033[1;32m✅ [1/4] 已封鎖自動腳本 (寫入 .npmrc)\033[0m"

# 2. 安裝 @lavamoat/allow-scripts
echo -e "\033[1;33m📦 [2/4] 正在安裝安全白名單工具...\033[0m"
npm install --save-dev @lavamoat/allow-scripts --ignore-scripts

# 3. 更新 package.json
echo -e "\033[1;33m⚙️ [3/4] 正在設定 postinstall 掛鉤...\033[0m"
npm pkg set scripts.postinstall="allow-scripts"

# 4. 初始化白名單設定
echo -e "\033[1;33m📋 [4/4] 正在初始化腳本白名單...\033[0m"
npx allow-scripts setup

echo -e "\033[1;36m🚀 專案加固大功告成！請手動檢查 package.json 中的 allowScripts 區塊。\033[0m"
```

## 🧹 第二階段：專案定期健康檢查 (Routine Hygiene)

建議每月或在發布重大版本前執行一次，確保開發過程中的異動沒有引入新的風險。

**使用方式**：將以下提示詞複製並發送給 AI 助手（Claude Code / Cursor）。

> **【任務：NPM 專案衛生與安全檢查】** 請對當前專案執行全面的健康檢查，並給我一份總結報告：
> 
> 1. **安全性掃描**：執行 `npm audit`。請幫我過濾掉開發環境 (devDependencies) 的低風險警告，只列出會影響「生產環境 (Production)」的重大漏洞，並提供修復建議（嚴禁直接使用 --force）。
>     
> 2. **減少攻擊面**：執行 `npx depcheck`，找出完全沒有被程式碼引用的「幽靈套件」，並列出清單詢問我是否要解除安裝。
>     
> 3. **腳本白名單審核**：讀取 `package.json` 中的 `lavamoat.allowScripts` 區塊，將設定為 `true` 的套件列出來，讓我確認是否有不認識的異常腳本。
>     
> 4. **核心版本鎖定檢查**：檢查 `dependencies` 中是否有關鍵的網路或編譯套件（例如 `axios`）使用了帶有 `^` 或 `~` 的範圍版本，若有請提醒我鎖定精確版本。
>