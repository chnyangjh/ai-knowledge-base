# AI 知识库助手 · 详细编码规范 v1.0

## 1. 概述

本规范定义了 AI 知识库助手项目的代码质量标准和开发流程要求，确保代码可维护性、一致性和自动化验证。

## 2. Python 代码规范

### 2.1 代码格式化
- **工具**: Black 格式化工具
- **版本**: ≥24.0.0（通过 `pyproject.toml` 锁定）
- **配置**:
  ```toml
  [tool.black]
  line-length = 88
  target-version = ['py312']
  include = '\.pyi?$'
  exclude = '''
  /(
    \.eggs
    | \.git
    | \.hg
    | \.mypy_cache
    | \.tox
    | \.venv
    | _build
    | buck-out
    | build
    | dist
  )/
  '''
  ```
- **执行方式**: 
  - 开发环境: 通过 pre-commit hook 自动格式化
  - CI/CD: 通过 `black --check` 验证格式一致性
- **迁移策略**: 现有代码应在 30 天内完成格式化迁移，新代码必须符合规范

### 2.2 代码质量检查
- **工具**: Ruff (替代 flake8, isort)
- **配置**:
  ```toml
  [tool.ruff]
  target-version = "py312"
  line-length = 88
  select = [
    "E",  # pycodestyle errors
    "W",  # pycodestyle warnings
    "F",  # pyflakes
    "I",  # isort
    "B",  # flake8-bugbear
    "C4", # flake8-comprehensions
    "UP", # pyupgrade
  ]
  ignore = ["E501"]  # line-length handled by black
  
  [tool.ruff.per-file-ignores]
  "__init__.py" = ["F401"]  # unused imports allowed in __init__.py
  ```

### 2.3 类型检查
- **工具**: mypy
- **配置**:
  ```toml
  [tool.mypy]
  python_version = "3.12"
  warn_return_any = true
  warn_unused_configs = true
  disallow_untyped_defs = true
  disallow_incomplete_defs = true
  check_untyped_defs = true
  disallow_untyped_decorators = true
  no_implicit_optional = true
  warn_redundant_casts = true
  warn_unused_ignores = true
  warn_no_return = true
  ```

## 3. 文档规范

### 3.1 文档字符串
- **风格**: Google 风格文档字符串
- **适用范围**: 
  - 所有公开模块级函数
  - 所有公开类（包括 `__init__` 方法）
  - 所有公开类方法
  - 例外: `@property` 装饰的方法、私有方法（`_` 前缀）、魔术方法
- **必需部分**:
  - 单行简要描述
  - `Args`: 每个参数的名称、类型、描述
  - `Returns`: 返回值的类型和描述
  - `Raises`: 可能抛出的异常类型和触发条件
  - `Examples`: 简单的使用示例（可选但推荐）
- **示例**:
  ```python
  def fetch_data(url: str, timeout: float = 30.0) -> Dict[str, Any]:
      """从指定 URL 获取数据。
      
      Args:
          url: 目标资源的完整 URL
          timeout: 请求超时时间（秒），默认 30.0
          
      Returns:
          包含响应数据的字典，结构因 API 而异
          
      Raises:
          requests.exceptions.Timeout: 请求超时
          ValueError: URL 格式无效或响应状态码错误
          
      Examples:
          >>> data = fetch_data("https://api.example.com/data")
          >>> print(data["status"])
      """
  ```

### 3.2 文档质量验证
- **工具**: pydocstyle (检查文档字符串格式)
- **配置**: 仅检查公开函数和类
- **覆盖率工具**: interrogate (要求文档字符串覆盖率 ≥ 90%)
- **例外**: 测试文件、配置文件的文档覆盖率要求可降低至 50%

## 4. 代码约定

### 4.1 魔法字符串禁令
- **禁止范围**: 业务逻辑判断中的字符串字面量
  ```python
  # 禁止
  if status == "pending":
      process_pending()
  
  # 允许 - 使用枚举
  from enum import Enum
  
  class Status(Enum):
      PENDING = "pending"
      APPROVED = "approved"
      REJECTED = "rejected"
  
  if status == Status.PENDING:
      process_pending()
  ```
- **例外情况**:
  - 日志消息字符串
  - 错误消息字符串
  - 测试数据
  - CLI 参数名称
  - 第三方库 API 调用所需的字符串
  - 配置文件中的字符串值
- **验证方式**: 通过自定义 lint 规则或代码审查检查

### 4.2 TODO 注释管理
- **禁止提交**: `TODO:` 注释不允许提交到 main 分支
- **检测模式**: 正则表达式 `TODO:.*` (包括 `TODO(username):`, `TODO(2025-01):` 等变体)
- **例外情况**:
  - 测试代码中的临时 TODO
  - 文档文件中的 TODO
  - 临时分支、feature 分支
- **替代方案**: 未完成的功能应创建 GitHub Issue 跟踪
- **执行机制**: pre-commit hook 检查，失败时阻止提交
- **迁移计划**: 现有 TODO 注释应在 60 天内清理或转换为 Issue

## 5. 测试规范

### 5.1 测试覆盖率
- **工具**: pytest + pytest-cov
- **覆盖率类型**: 分支覆盖率 (branch coverage)
- **要求**: 整体代码库覆盖率 ≥ 80%
- **新代码要求**: 新增或修改的代码覆盖率 ≥ 90%
- **排除文件**:
  - 配置文件 (`config/` 目录)
  - 测试代码本身
  - 第三方库包装器
  - 数据模型定义文件
- **执行时机**: CI/CD 流水线中检查，不阻塞本地开发
- **报告格式**: HTML 报告，保存到 `coverage/html/`

### 5.2 测试结构
- **目录结构**: `tests/` 目录镜像源代码结构
- **命名约定**: 
  - 测试文件: `test_<module_name>.py`
  - 测试函数: `test_<function_name>_<scenario>`
- **测试分类**:
  - 单元测试: 测试独立函数和类
  - 集成测试: 测试模块间交互
  - 端到端测试: 测试完整工作流

## 6. 工具链配置

### 6.1 统一配置文件
所有工具配置集中在 `pyproject.toml`:
```toml
[build-system]
requires = ["setuptools", "wheel"]

[project]
name = "ai-knowledge-base"
version = "0.1.0"
description = "AI 知识库助手 - 自动化技术动态采集与分析系统"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "requests>=2.31.0",
    "pydantic>=2.5.0",
    "langgraph>=0.0.40",
]

[tool.black]
# ... black 配置

[tool.ruff]
# ... ruff 配置

[tool.mypy]
# ... mypy 配置

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=ai_knowledge_base --cov-report=html --cov-report=term-missing"
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
```

### 6.2 pre-commit 配置
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.0.0
    hooks:
      - id: black
        language_version: python3.12
  
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix]
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
  
  - repo: local
    hooks:
      - id: forbid-todo
        name: Forbid TODO comments
        entry: bash -c '! grep -r "TODO:" --include="*.py" .'
        language: system
        pass_filenames: false
```

## 7. 开发工作流

### 7.1 本地开发
```bash
# 安装依赖
pip install -e ".[dev]"

# 安装 pre-commit hooks
pre-commit install

# 运行测试
pytest

# 检查代码质量
ruff check .
black --check .
mypy .
```

### 7.2 CI/CD 流程
1. **代码格式化检查**: `black --check .`
2. **代码质量检查**: `ruff check .`
3. **类型检查**: `mypy .`
4. **文档检查**: `pydocstyle --convention=google .`
5. **测试运行**: `pytest --cov --cov-fail-under=80`
6. **构建验证**: 确保可成功构建和导入

### 7.3 紧急情况处理
- **临时绕过**: 通过 `git commit --no-verify` 可跳过检查（需记录理由）
- **规则豁免**: 特殊情况下可向项目维护者申请规则豁免
- **规范更新**: 规范本身应通过 PR 流程修改，需团队审核

## 8. TypeScript 规范（未来扩展）

### 8.1 基本配置
```json
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2022",
    "module": "ESNext",
    "lib": ["ES2022", "DOM"],
    "outDir": "./dist",
    "rootDir": "./src",
    "moduleResolution": "node",
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

### 8.2 ESLint 配置
```javascript
// eslint.config.js
import typescriptEslint from '@typescript-eslint/eslint-plugin';
import typescriptParser from '@typescript-eslint/parser';

export default [
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: typescriptParser,
      ecmaVersion: 'latest',
      sourceType: 'module'
    },
    plugins: {
      '@typescript-eslint': typescriptEslint
    },
    rules: {
      '@typescript-eslint/explicit-function-return-type': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': 'error'
    }
  }
];
```

## 9. 版本与维护

### 9.1 版本管理
- **规范版本**: 本规范版本号独立于项目版本
- **更新流程**: 规范修改需通过团队评审和投票
- **兼容性**: 新规范版本应提供迁移指南

### 9.2 工具版本锁定
```txt
# requirements-dev.txt
black==24.0.0
ruff==0.1.6
mypy==1.8.0
pytest==7.4.4
pytest-cov==4.1.0
pydocstyle==6.3.0
interrogate==1.5.0
pre-commit==3.6.0
```

## 10. 附录

### 10.1 常见问题
**Q: 如何处理遗留代码的格式化问题？**
A: 使用 `black .` 批量格式化，然后逐文件 review 确保功能正常。

**Q: 魔法字符串禁令是否影响日志消息？**
A: 不影响，日志消息属于例外情况。

**Q: 测试覆盖率不达标怎么办？**
A: 优先为新代码补充测试，遗留代码逐步改进，可申请临时豁免。

**Q: 如何添加新的代码检查规则？**
A: 通过修改 `pyproject.toml` 中的工具配置，需团队评审。

### 10.2 参考资源
- [Black 文档](https://black.readthedocs.io/)
- [Ruff 文档](https://docs.astral.sh/ruff/)
- [mypy 文档](https://mypy.readthedocs.io/)
- [Google Python 风格指南](https://google.github.io/styleguide/pyguide.html)

---

*最后更新: 2025-04-18*  
*版本: 1.0*  
*维护者: AI 知识库助手团队*  
*生效日期: 发布后 30 天*