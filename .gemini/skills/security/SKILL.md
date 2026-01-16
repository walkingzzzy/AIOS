---
name: security
description: 安全编码规范，包含输入验证、认证授权、数据保护和常见漏洞防护
---

# 安全编码规范

## 输入验证

### 原则
```
✅ 验证所有外部输入
✅ 白名单优于黑名单
✅ 在边界处验证
✅ 失败时拒绝
```

### 常见验证
| 类型 | 验证内容 |
|------|---------|
| 字符串 | 长度、格式、编码 |
| 数字 | 范围、精度 |
| 文件 | 类型、大小、扩展名 |
| URL | 协议、域名白名单 |

---

## 常见漏洞防护

### SQL 注入
```typescript
// ❌ 错误
const query = `SELECT * FROM users WHERE id = ${userId}`;

// ✅ 正确
const query = 'SELECT * FROM users WHERE id = ?';
db.query(query, [userId]);
```

### XSS
```typescript
// ❌ 错误
element.innerHTML = userInput;

// ✅ 正确
element.textContent = userInput;
// 或使用 DOMPurify
element.innerHTML = DOMPurify.sanitize(userInput);
```

### CSRF
```
✅ 使用 CSRF Token
✅ SameSite Cookie 属性
✅ 验证 Origin/Referer
```

---

## 敏感数据处理

### 禁止
```
❌ 日志中记录密码/密钥
❌ 硬编码凭证
❌ 明文存储密码
❌ 在 URL 中传递敏感信息
```

### 必须
```
✅ 使用环境变量存储密钥
✅ 密码使用 bcrypt 哈希
✅ HTTPS 传输
✅ 最小权限原则
```

---

## 认证授权

| 原则 | 说明 |
|------|------|
| 最小权限 | 只授予必要权限 |
| 默认拒绝 | 未明确允许则拒绝 |
| 深度防御 | 多层验证 |
| 会话管理 | 安全的 token 存储 |

---

## 安全清单

```markdown
□ 所有输入已验证？
□ 输出已编码/转义？
□ 敏感数据已加密？
□ 无硬编码凭证？
□ 依赖项无已知漏洞？
□ 错误信息不泄露敏感信息？
```

> 💡 **相关 skills**: [error-handling](../error-handling/SKILL.md), [code-standards](../code-standards/SKILL.md)
