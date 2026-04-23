# AI 知识库助手

自动化的技术动态采集与分析系统，专门针对 AI/LLM/Agent 领域。

## 功能特性

- **自动采集**: 从 GitHub Trending、Hacker News 等来源采集最新技术动态
- **智能分析**: 使用 LLM 分析内容，提取摘要、关键点、标签
- **结构化存储**: 将处理后的知识条目保存为结构化 JSON 格式
- **多渠道分发**: 支持通过 Telegram、飞书等渠道进行智能分发

## 技术栈

- **编程语言**: Python 3.12
- **AI 框架**: OpenCode + 国产大模型（DeepSeek、GLM、Qwen 等）
- **工作流引擎**: LangGraph（用于构建多 Agent 协作流程）
- **爬虫框架**: OpenClaw（用于网页内容采集）
- **数据存储**: JSON 文件 + SQLite（可选）
- **消息推送**: Telegram Bot API、飞书开放平台 API

## 快速开始

### 安装依赖

```bash
# 安装核心依赖
pip install -e .

# 安装开发依赖
pip install -e ".[dev]"

# 安装 pre-commit hooks
pre-commit install
```

### 运行测试

```bash
pytest
```

## 项目结构

```
ai-knowledge-base/
├── .opencode/              # OpenCode 配置文件
│   ├── agents/            # Agent 定义文件
│   └── skills/            # 技能模块
├── knowledge/             # 知识库数据
│   ├── raw/              # 原始采集数据
│   └── articles/         # 处理后的知识条目
├── config/               # 配置文件
├── utils/                # 工具函数
├── tests/                # 测试代码
├── requirements.txt      # Python 依赖
└── AGENTS.md            # Agent 规范文档
```

## 编码规范

本项目遵循严格的编码规范，详见 [AGENTS.md](AGENTS.md) 中的编码规范章节。主要要求：

- **代码格式化**: 使用 Black 自动格式化
- **代码质量**: 使用 Ruff 进行 linting
- **类型检查**: 使用 mypy 进行静态类型检查
- **文档要求**: Google 风格文档字符串，文档覆盖率 ≥ 90%
- **测试要求**: 分支覆盖率 ≥ 80%，新代码 ≥ 90%

## 开发工作流

1. 安装开发依赖：`pip install -e ".[dev]"`
2. 安装 Git hooks：`pre-commit install`
3. 创建 feature 分支进行开发
4. 运行测试：`pytest`
5. 提交代码（pre-commit hooks 会自动检查）
6. 创建 Pull Request

## 许可证

MIT License