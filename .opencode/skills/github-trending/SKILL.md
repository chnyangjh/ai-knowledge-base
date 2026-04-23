---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 使用场景

当需要从 GitHub 采集热门开源项目信息，特别是 AI/LLM/Agent 领域的最新动态时，使用此技能。适用于知识库系统的数据采集环节，为后续分析和分发提供原始数据。

## 执行步骤

### 1. 搜索热门仓库（GitHub API）
使用 WebFetch 工具调用 GitHub Trending API 或直接访问 GitHub Trending 页面（https://github.com/trending），获取原始 HTML 或 JSON 数据。注意遵守 GitHub 的 rate limiting 规则。

### 2. 提取信息
从获取的数据中提取每个仓库的关键信息，包括：
- 仓库名称（name）
- 仓库 URL（url）
- 星标数（stars）
- 主要编程语言（language）
- 主题标签（topics）
- 仓库描述（description）

### 3. 过滤
对提取的仓库进行过滤，确保符合 AI 知识库的收录标准：
- **纳入**：与 AI/LLM/Agent 相关的项目（通过 topics、description、name 关键词匹配）
- **排除**：Awesome 列表类项目（名称包含 "awesome-" 或描述中包含 "curated list"）
- **排除**：非技术类项目（如文档、教程、个人博客等）

### 4. 去重
与已有知识库数据（`knowledge/raw/` 目录下的历史文件）进行比对，排除已收录的仓库，避免重复采集。

### 5. 撰写中文摘要
为每个过滤后的仓库生成简洁的中文摘要，遵循公式：
**项目名 + 做什么 + 为什么值得关注**

示例：
- "LangChain：一个用于构建 LLM 应用的框架，值得关注因为它提供了统一的接口连接多种 LLM 模型和数据源。"
- "AutoGPT：一个实验性开源项目，展示了 GPT-4 的自主任务完成能力，值得关注因为它推动了自主 AI 代理的发展。"

### 6. 排序取 Top15
按星标数（stars）降序排序，选取前 15 个最受欢迎的项目。如果星标数相同，按最近更新时间排序。

### 7. 输出 JSON
将处理后的数据保存到 `knowledge/raw/github-trending-YYYY-MM-DD.json` 文件，其中 YYYY-MM-DD 为采集日期。

## 注意事项

1. **遵守规则**：严格遵守 GitHub 的 robots.txt 和 rate limiting 规则，采集间隔不低于 5 分钟。
2. **错误处理**：网络请求必须设置合理的超时时间（默认 30 秒），并有重试机制。
3. **数据安全**：不采集私有仓库信息，不处理敏感数据。
4. **版权尊重**：所有采集内容仅用于个人学习和研究，分发时必须注明原始来源。
5. **质量优先**：优先收录有实际代码、活跃维护、文档完善的项目。

## 输出格式

输出文件为 JSON 格式，结构如下：

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2024-01-01T12:00:00Z",
  "items": [
    {
      "name": "项目名称",
      "url": "https://github.com/owner/repo",
      "summary": "中文摘要：项目名+做什么+为什么值得关注",
      "stars": 1234,
      "language": "Python",
      "topics": ["llm", "agent", "framework"]
    }
  ]
}
```

**字段说明**：
- `source`: 固定为 "github_trending"，表示数据来源
- `skill`: 固定为 "github-trending"，表示使用的技能名称
- `collected_at`: ISO 8601 格式的采集时间戳（UTC）
- `items`: 项目数组，最多 15 个元素
  - `name`: 仓库名称（不含 owner 前缀）
  - `url`: 完整的 GitHub 仓库 URL
  - `summary`: 生成的中文摘要
  - `stars`: 星标数（整数）
  - `language`: 主要编程语言（字符串，可能为 null）
  - `topics`: 主题标签数组（字符串数组）

**文件命名**：`github-trending-YYYY-MM-DD.json`，例如 `github-trending-2024-01-01.json`
**保存路径**：`knowledge/raw/` 目录下，按日期组织

## 验证要求

1. 每次运行后检查输出文件是否存在且格式正确
2. 确保 items 数组不超过 15 个元素
3. 验证所有 URL 均为有效的 GitHub 仓库链接
4. 确认 collected_at 为当前时间（UTC）
5. 检查 summary 字段是否符合中文摘要公式