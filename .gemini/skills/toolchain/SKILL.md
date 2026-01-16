---
name: toolchain
description: 工具链集成规范，包含工具选择决策树和各工具使用指南
---

# 工具链集成

## 核心原则

- 工具是手段，按需使用，避免僵化流程
- 所有引用资料**必须写明来源与用途**，保持可追溯
- 检索失败时，必须在日志中声明并改用替代方法

---

## 工具选择决策树

```
需要本地文件操作？
├─ 文件读写 → view_file / write_to_file
├─ 单处编辑 → replace_file_content
├─ 多处编辑 → multi_replace_file_content
├─ 搜索文件 → find_by_name
└─ 搜索内容 → grep_search

需要编程文档？
├─ 官方文档/API → context7（最高优先级）
└─ 博客/教程 → read_url_content / search_web

需要 GitHub 操作？
├─ 搜索代码 → github.search_code
├─ 读取文件 → github.get_file_contents
└─ PR/Issue → github.create_*/update_*
```

---

## 文件操作工具

| 工具 | 用途 | 场景 |
|------|------|------|
| `view_file_outline` | 查看文件结构 | **首选**，探索文件 |
| `view_file` | 读取文件内容 | 深入阅读 |
| `find_by_name` | 按名称搜索 | 找文件 |
| `grep_search` | 按内容搜索 | 找代码 |
| `write_to_file` | 创建新文件 | 新建 |
| `replace_file_content` | 单处编辑 | 简单修改 |
| `multi_replace_file_content` | 多处编辑 | 复杂修改 |

---

## context7 使用（编程文档优先）

**触发条件**：任何关于编程库、框架、SDK、API 的问题

```bash
# 1. 获取库 ID
context7 resolve-library-id libraryName="react"

# 2. 获取文档
context7 get-library-docs context7CompatibleLibraryID="库ID" topic="hooks"
```

**优势**：专门优化编程上下文，token高效，最新官方文档

---

## github.search_code 使用

**触发条件**：搜索开源实现示例，学习最佳实践

```bash
github.search_code query="具体功能" language:"typescript"
```

**比 firecrawl 更精准**，适合找实现参考

---

## 约束条件

- 新建文件时**不超过100行**
- 超过100行先建框架，再通过编辑添加内容
- **优先使用专用工具**，避免 bash 命令
- 使用**绝对路径**以保证可靠性
