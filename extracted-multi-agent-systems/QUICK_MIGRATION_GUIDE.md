# 快速遷移指南 / Quick Migration Guide

## 🎯 5分鐘快速開始 / 5-Minute Quick Start

### 1. 下載提取包 / Download Extraction Package
```bash
# 如果從GitHub下載
cd /path/to/target/system
git clone https://github.com/codevantaceo/iaops.git
cd iaops
git checkout claude/extract-multi-agent-systems
cp -r extracted-multi-agent-systems /your/target/location/

# 或直接複製目錄
cp -r /home/runner/work/iaops/iaops/extracted-multi-agent-systems /your/target/location/
```

### 2. 安裝依賴 / Install Dependencies (2分鐘)
```bash
cd /your/target/location/extracted-multi-agent-systems
pip install -r requirements.txt
```

### 3. 快速測試 / Quick Test (1分鐘)
```bash
# 測試簡單代理
python examples/simple_agent_test.py

# 測試多代理編排
python examples/multi_agent_example.py
```

---

## 📋 完整遷移步驟 / Complete Migration Steps

### 階段1：準備工作 / Phase 1: Preparation
- [ ] 確認目標系統已安裝Python 3.8+
- [ ] 確認有足夠的磁盤空間（至少1MB）
- [ ] 準備好新的項目目錄結構

### 階段2：文件遷移 / Phase 2: File Migration
- [ ] 複製`extracted-multi-agent-systems`整個目錄
- [ ] 安裝`requirements.txt`中的依賴
- [ ] 驗證所有文件完整性（69個文件）

### 階段3：配置調整 / Phase 3: Configuration
- [ ] 更新`policy-configs/configs/`中的配置文件
- [ ] 調整文件路徑為新系統的路徑
- [ ] 設置必要的環境變量

### 階段4：代碼適配 / Phase 4: Code Adaptation
- [ ] 調整Python導入語句（如需要）
- [ ] 更新模塊路徑引用
- [ ] 適配新系統的API接口

### 階段5：測試驗證 / Phase 5: Testing & Verification
- [ ] 運行示例程序
- [ ] 測試核心功能
- [ ] 驗證代理通信
- [ ] 檢查日誌輸出

---

## 🔄 導入路徑調整示例 / Import Path Adjustment Examples

### 原始導入 / Original Imports
```python
from indestructibleautoops.agents.orchestrator import MultiAgentOrchestrator
from indestructibleautoops.agents.base import Agent
from indestructibleautoops.validation.engine import ValidationEngine
```

### 選項1：直接使用（推薦） / Option 1: Direct Use (Recommended)
```python
# 將extracted-multi-agent-systems添加到Python路徑
import sys
sys.path.insert(0, '/path/to/extracted-multi-agent-systems')

# 然後直接從子目錄導入
from agents.orchestrator import MultiAgentOrchestrator
from agents.base import Agent
from validation.engine import ValidationEngine
```

### 選項2：重命名包 / Option 2: Rename Package
```python
# 將extracted-multi-agent-systems重命名為您的項目名
# mv extracted-multi-agent-systems myproject_agents

from myproject_agents.agents.orchestrator import MultiAgentOrchestrator
from myproject_agents.agents.base import Agent
from myproject_agents.validation.engine import ValidationEngine
```

---

## 📂 目錄映射關係 / Directory Mapping

| 原始位置 | 提取後位置 |
|---------|-----------|
| `src/indestructibleautoops/agents/` | `agents/` |
| `src/indestructibleautoops/validation/` | `validation/` |
| `src/indestructibleautoops/security/` | `security/` |
| `src/indestructibleautoops/adapters/` | `adapters/` |
| `scripts/ci/` | `ci-automation/` |
| `scripts/monitoring/` | `observability/monitoring/` |
| `policy/rego/` | `policy-configs/rego/` |
| `configs/` | `policy-configs/configs/` |

---

## 🛠️ 配置文件調整 / Configuration File Adjustments

### 1. 適配器配置 / Adapter Configuration
文件：`policy-configs/configs/indestructibleautoops.adapters.yaml`

需要調整的內容：
- 文件路徑
- 工作目錄
- 輸出目錄

### 2. 管道配置 / Pipeline Configuration
文件：`policy-configs/configs/indestructibleautoops.pipeline.yaml`

需要調整的內容：
- 步驟路徑
- 依賴項路徑
- 輸出路徑

### 3. 策略配置 / Policy Configuration
文件：`policy-configs/configs/indestructibleautoops.policies.yaml`

需要調整的內容：
- 策略規則路徑
- Rego文件路徑

---

## 🔧 常見問題解決 / Troubleshooting

### 問題1：導入錯誤 / Import Errors
```
ModuleNotFoundError: No module named 'indestructibleautoops'
```

**解決方案：**
- 調整導入路徑（參考上面的導入路徑調整示例）
- 或添加目錄到Python路徑

### 問題2：配置文件找不到 / Configuration File Not Found
```
FileNotFoundError: 'configs/...'
```

**解決方案：**
- 使用絕對路徑
- 或設置正確的工作目錄

### 問題3：依賴缺失 / Missing Dependencies
```
ModuleNotFoundError: No module named 'click'
```

**解決方案：**
```bash
pip install -r requirements.txt
```

---

## 📊 核心組件使用示例 / Core Component Usage Examples

### 1. 使用MultiAgentOrchestrator
```python
from agents.orchestrator import MultiAgentOrchestrator
from agents.coordination import Task

# 創建編排器
orchestrator = MultiAgentOrchestrator()

# 註冊代理
orchestrator.register_agents()

# 創建任務
task = Task(
    id="task-1",
    description="Process data",
    priority=1
)

# 執行任務
result = orchestrator.execute_task(task)
```

### 2. 使用ValidationEngine
```python
from validation.engine import ValidationEngine
from validation.strict_validator import StrictValidator

# 創建驗證引擎
engine = ValidationEngine()

# 添加驗證器
engine.add_validator(StrictValidator())

# 執行驗證
results = engine.validate(data)
```

### 3. 使用SecurityScanner
```python
from security.scanner import SecurityScanner

# 創建掃描器
scanner = SecurityScanner()

# 掃描文件
report = scanner.scan_file("path/to/file")

# 檢查結果
if report.is_secure:
    print("File is secure")
```

---

## 🎓 學習資源 / Learning Resources

### 必讀文檔 / Must-Read Documentation
1. **README.md** - 系統完整文檔
2. **EXTRACTION_MANIFEST.md** - 文件清單與說明
3. **提取完成通知.md** - 提取完成報告

### 示例代碼 / Example Code
1. `examples/multi_agent_example.py` - 多代理使用示例
2. `examples/simple_agent_test.py` - 簡單代理測試
3. `examples/simple_orchestrator_test.py` - 編排器測試

### 核心代碼閱讀順序 / Code Reading Order
1. `agents/base.py` - 理解基礎代理抽象
2. `agents/orchestrator.py` - 理解編排引擎
3. `agents/concrete/` - 查看具體代理實現
4. `validation/engine.py` - 理解驗證系統
5. `automation-engines/engine.py` - 理解自動化引擎

---

## ✅ 遷移檢查清單 / Migration Checklist

### 遷移前 / Before Migration
- [ ] 閱讀README.md
- [ ] 閱讀EXTRACTION_MANIFEST.md
- [ ] 了解系統架構
- [ ] 準備目標環境

### 遷移中 / During Migration
- [ ] 複製所有文件
- [ ] 安裝依賴
- [ ] 調整配置
- [ ] 修改導入路徑
- [ ] 更新文件路徑

### 遷移後 / After Migration
- [ ] 運行示例程序
- [ ] 測試核心功能
- [ ] 驗證日誌輸出
- [ ] 檢查錯誤處理
- [ ] 性能測試
- [ ] 文檔更新

---

## 📞 獲取幫助 / Getting Help

如果遇到問題，請：
1. 查看README.md中的詳細文檔
2. 檢查EXTRACTION_MANIFEST.md中的文件列表
3. 參考examples/目錄中的示例代碼
4. 查看原始倉庫：https://github.com/codevantaceo/iaops

---

## 🎉 完成！ / Complete!

恭喜！您已經準備好遷移多代理系統了。

**Congratulations! You are ready to migrate the multi-agent system.**

記得：
- 保持原始代碼的歸屬
- 根據需要調整配置
- 充分測試後再部署到生產環境

祝您使用愉快！/ Happy migrating!
