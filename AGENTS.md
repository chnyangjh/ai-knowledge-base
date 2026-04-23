# AI 知识库助手 - Agents 规范

## 1. 项目概述

AI 知识库助手是一个自动化的技术动态采集与分析系统，专门针对 AI/LLM/Agent 领域。系统自动从 GitHub Trending 和 Hacker News 等来源采集最新技术动态，通过 AI 分析提取关键信息并结构化存储为 JSON 格式，支持通过 Telegram、飞书等多渠道进行智能分发。

## 2. 技术栈

- **编程语言**: Python 3.12
- **AI 框架**: OpenCode + 国产大模型（如 DeepSeek、GLM、Qwen 等）
- **工作流引擎**: LangGraph（用于构建多 Agent 协作流程）
- **爬虫框架**: OpenClaw（用于网页内容采集）
- **数据存储**: JSON 文件 + SQLite（可选）
- **消息推送**: Telegram Bot API、飞书开放平台 API

## 3. 编码规范

### 3.1 代码格式化与质量
- **代码格式化**: 使用 Black (≥24.0.0) 自动格式化，配置在 `pyproject.toml`
  - 行长度: 88 字符
  - 字符串引号: 遵循 Black 默认规则（双引号转单引号，除非字符串内包含单引号）
  - 执行: pre-commit hook + CI 检查
- **代码质量检查**: 使用 Ruff 进行 linting，替代 flake8/isort
- **类型检查**: 使用 mypy 进行静态类型检查，启用严格模式
- **命名约定**: 
  - 变量、函数、方法：`snake_case`
  - 类名：`CamelCase`
  - 常量：`UPPER_SNAKE_CASE`

### 3.2 文档要求
- **文档风格**: Google 风格文档字符串
- **适用范围**: 所有公开模块级函数、公开类（包括 `__init__` 方法）、公开类方法
- **必需部分**: `Args`、`Returns`、`Raises`、`Examples`（可选但推荐）
- **例外**: `@property` 装饰的方法、私有方法（`_` 前缀）、魔术方法
- **验证工具**: pydocstyle + interrogate（文档覆盖率 ≥ 90%）

### 3.3 代码约定
- **魔法字符串禁令**: 禁止在业务逻辑判断中使用字符串字面量，应使用枚举类替代
  - 例外: 日志消息、错误消息、测试数据、CLI 参数名称、第三方库调用
- **TODO 管理**: `TODO:` 注释不允许提交到 main 分支
  - 检测: pre-commit hook 检查 `TODO:.*` 模式
  - 例外: 测试代码、文档文件、临时分支
  - 替代: 使用 GitHub Issue 跟踪未完成功能
  - 迁移: 现有 TODO 应在 60 天内清理

### 3.4 测试要求
- **测试框架**: pytest + pytest-cov
- **覆盖率要求**: 分支覆盖率 ≥ 80%（整体），新代码 ≥ 90%
- **排除文件**: 配置文件、测试代码本身、第三方库包装器
- **执行时机**: CI/CD 中检查，生成 HTML 报告
- **目录结构**: `tests/` 目录镜像源代码结构

### 3.5 工具链配置
- **统一配置**: 所有工具配置在 `pyproject.toml`
- **pre-commit**: 自动格式化、linting、类型检查、TODO 检测
- **开发依赖**: 版本锁定在 `requirements-dev.txt`
- **CI/CD 流程**: 格式化检查 → 代码质量检查 → 类型检查 → 文档检查 → 测试运行

### 3.6 TypeScript 规范（未来）
- **编译器**: TypeScript 严格模式 (`strict: true`)
- **配置**: `tsconfig.json` 中启用所有严格选项
- **代码检查**: ESLint + TypeScript ESLint 插件
- **执行**: 通过 ESLint 在 CI 中检查

### 3.7 开发工作流
1. `pip install -e ".[dev]"` 安装开发依赖
2. `pre-commit install` 安装 Git hooks
3. 本地开发，自动格式化
4. `pytest` 运行测试
5. CI 验证所有质量门禁

### 3.8 紧急处理
- **临时绕过**: `git commit --no-verify`（需记录理由）
- **规则豁免**: 向项目维护者申请
- **规范更新**: 通过 PR 流程修改，需团队审核

## 4. 项目结构

```
ai-knowledge-base/
├── .opencode/              # OpenCode 配置文件
│   ├── agents/            # Agent 定义文件
│   │   ├── collector.py   # 采集 Agent
│   │   ├── analyzer.py    # 分析 Agent
│   │   └── curator.py     # 整理 Agent
│   └── skills/            # 技能模块
│       ├── web_scraper.py # 网页抓取技能
│       ├── llm_analyzer.py # LLM 分析技能
│       └── notifier.py    # 通知技能
├── knowledge/             # 知识库数据
│   ├── raw/              # 原始采集数据
│   │   └── YYYY-MM-DD/   # 按日期组织的原始数据
│   └── articles/         # 处理后的知识条目
│       └── YYYY-MM/      # 按月组织的知识文章
├── config/               # 配置文件
│   ├── settings.py       # 主配置文件
│   └── credentials.example.py # 凭证示例
├── utils/                # 工具函数
├── tests/                # 测试代码
├── requirements.txt      # Python 依赖
├── README.md            # 项目说明
└── AGENTS.md            # Agent 规范文档
```

## 5. 知识条目 JSON 格式

```json
{
  "id": "unique_uuid_v4",
  "title": "文章标题或项目名称",
  "source": "github_trending|hacker_news|manual",
  "source_url": "原始来源 URL",
  "content": "原始内容或摘要",
  "summary": "AI 生成的简洁摘要（200-300 字）",
  "key_points": [
    "关键点 1",
    "关键点 2",
    "关键点 3"
  ],
  "tags": ["llm", "agent", "framework", "research"],
  "category": "framework|library|paper|news|tool",
  "language": "zh|en",
  "author": "作者或组织",
  "published_at": "2024-01-01T00:00:00Z",
  "collected_at": "2024-01-01T12:00:00Z",
  "analyzed_at": "2024-01-01T12:30:00Z",
  "status": "raw|analyzed|curated|published|archived",
  "metadata": {
    "github_stars": 1234,
    "hacker_news_score": 256,
    "hacker_news_comments": 42,
    "technical_level": "beginner|intermediate|advanced"
  },
  "distribution": {
    "telegram": {
      "sent_at": "2024-01-01T13:00:00Z",
      "message_id": "123456"
    },
    "feishu": {
      "sent_at": "2024-01-01T13:05:00Z",
      "message_id": "abcdef"
    }
  }
}
```

**字段说明**:
- `id`: 唯一标识符，使用 UUID v4
- `status`: 条目状态，从 `raw`（原始采集）到 `published`（已分发）的工作流状态
- `metadata`: 扩展信息，根据来源不同包含不同的指标数据
- `distribution`: 分发记录，记录各渠道的分发状态和时间戳

## 6. Agent 角色概览

| 角色 | 名称 | 主要职责 | 使用工具/技能 | 输出 |
|------|------|----------|---------------|------|
| **采集 Agent** | `Collector` | 从 GitHub Trending、Hacker News 等源采集数据 | OpenClaw 爬虫、API 客户端、RSS 解析 | 原始数据（HTML/JSON）保存到 `knowledge/raw/` |
| **分析 Agent** | `Analyzer` | 使用 LLM 分析内容，提取摘要、关键点、标签 | LLM 分析技能、文本处理工具 | 结构化知识条目（JSON）保存到暂存区 |
| **整理 Agent** | `Curator` | 质量审核、去重、分类、补充元数据 | 去重算法、分类模型、人工审核界面 | 最终知识条目保存到 `knowledge/articles/` |

**工作流**:
```
采集 → 分析 → 整理 → 分发
```

## 7. 红线（绝对禁止的操作）

1. **禁止硬编码敏感信息**
   - 绝对不要在代码中直接写入 API 密钥、令牌、密码等敏感信息
   - 所有凭证必须通过环境变量或配置文件读取

2. **禁止破坏性操作**
   - 禁止删除原始采集数据（`knowledge/raw/` 目录只增不删）
   - 禁止修改已分发的知识条目（如需修正，创建新版本）

3. **禁止过度请求**
   - 遵守目标网站的 robots.txt 和 rate limiting 规则
   - 采集间隔不得低于 5 分钟，避免对目标服务器造成压力

4. **禁止数据泄露**
   - 未经脱敏处理的原始数据不得发送到外部 LLM 服务
   - 含有个人身份信息（PII）的内容必须匿名化处理

5. **禁止绕过验证**
   - 所有外部 API 调用必须有错误处理和重试机制
   - 网络请求必须设置合理的超时时间（默认 30 秒）

6. **禁止静默失败**
   - 所有异常必须被记录和上报，不能 silently fail
   - 关键操作必须有确认机制和回滚能力

7. **禁止侵犯版权**
   - 采集的内容仅用于个人学习和研究
   - 分发时必须注明原始来源和作者
   - 遵守相关开源协议和版权规定

## 8. 扩展建议

- **监控**: 添加 Agent 运行状态监控和健康检查
- **缓存**: 对频繁访问的外部 API 添加缓存层
- **回溯**: 支持重新分析历史数据（当分析模型更新时）
- **插件**: 支持自定义数据源和分发渠道插件

---

*最后更新: 2025-04-18*  
*维护者: AI 知识库助手团队*