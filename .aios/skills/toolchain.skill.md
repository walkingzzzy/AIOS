---
name: 工具链集成
version: 1.0.0
description: 工具链集成规范，包含工具选择决策树和各工具的使用指南
category: development
keywords: [工具, context7, github, firecrawl, desktop-commander, 检索]
author: AIOS Team
enabled: true
priority: 9
---

# 工具链集成

## 工具选择决策树

```
需要本地文件操作？
├─ 文件读写/搜索 → desktop-commander（最高优先级）
├─ 数据分析（CSV/JSON） → desktop-commander.start_process + interact_with_process
└─ 进程管理 → desktop-commander.start_process

需要编程相关信息？
├─ 官方文档/API参考 → context7（最高优先级）
└─ 最新博客/文章/教程 → firecrawl（通用后备）

需要操作 GitHub？
├─ 搜索代码 → github.search_code
├─ 读取文件/文档 → github.get_file_contents
├─ 管理 PR/Issue → github.create_*/update_*
└─ 代码审查 → github.request_copilot_review
```

---

## desktop-commander（最高优先级）

**核心能力**：
| 功能 | 方法 |
|------|------|
| 文件操作 | `read_file`、`write_file`、`edit_block` |
| 目录管理 | `list_directory`、`create_directory`、`move_file` |
| 搜索 | `start_search`（流式返回结果） |
| 进程管理 | `start_process`、`interact_with_process` |
| 数据分析 | 支持 Python/Node.js REPL |

**最佳实践**：
- 本地 CSV/JSON/数据文件分析**必用**此工具
- **绝对优先**于 bash cat/grep/find 命令
- 使用绝对路径以保证可靠性
- 精确编辑使用 `edit_block`（比 sed/awk 更安全）

---

## context7（编程文档优先）

**调用方式**：
```bash
# 1. 首先获取库 ID
context7 resolve-library-id libraryName="库名"

# 2. 获取文档
context7 get-library-docs context7CompatibleLibraryID="库ID" topic="主题"
```

**优势**：
- 专门优化编程上下文
- Token 高效
- 最新官方文档

**示例场景**：
- React hooks 用法
- Next.js 路由
- MongoDB 查询语法

---

## github（代码搜索和协作）

**核心能力**：
| 功能 | 方法 |
|------|------|
| 代码搜索 | `search_code`、`search_repositories` |
| PR 管理 | `create_pull_request`、`merge_pull_request` |
| Issue 管理 | `create_issue`、`update_issue` |
| 代码审查 | `create_and_submit_pull_request_review` |
| 文件操作 | `create_or_update_file`、`push_files` |

**最佳实践**：
- 搜索代码用 `search_code`（比 firecrawl 更精准）
- 创建 PR 前先调用 `get_pull_request_diff`

---

## firecrawl（通用网页检索）

**调用方式**：
| 方法 | 用途 |
|------|------|
| `firecrawl_search` | 搜索并抓取（推荐） |
| `firecrawl_scrape` | 单页抓取（已知 URL） |
| `firecrawl_map` | 网站结构发现 |

**触发条件**：
- context7 无法满足
- 需要最新博客/文章/教程

---

## 约束条件

- 新建文件时**不超过100行**
- 超过100行先新建基础框架，再通过编辑添加内容
- 所有引用资料**必须写明来源与用途**
- 检索失败时在日志中声明并改用替代方法
