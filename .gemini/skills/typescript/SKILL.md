---
name: typescript
description: TypeScript 最佳实践，包含类型系统、严格模式、常见模式和性能优化
---

# TypeScript 最佳实践

## 类型系统

### 严格模式（必须）
```json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true
  }
}
```

### 类型优先级
```
✅ 接口（interface） - 可扩展、声明合并
✅ 类型别名（type） - 联合、交叉、工具类型
❌ any - 禁止使用
⚠️ unknown - 需要类型守卫
```

---

## 常用模式

### 类型守卫
```typescript
function isUser(obj: unknown): obj is User {
  return typeof obj === 'object' && obj !== null && 'id' in obj;
}
```

### 泛型约束
```typescript
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}
```

### 工具类型
| 类型 | 用途 |
|------|------|
| `Partial<T>` | 所有属性可选 |
| `Required<T>` | 所有属性必需 |
| `Pick<T, K>` | 选取部分属性 |
| `Omit<T, K>` | 排除部分属性 |
| `Record<K, V>` | 键值对映射 |

---

## 禁止事项

```
❌ 使用 any 类型
❌ 类型断言 as any
❌ @ts-ignore 注释
❌ 非空断言 ! 滥用
❌ 隐式类型推断复杂对象
```

---

## 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 接口 | PascalCase，I 前缀可选 | `User`, `IUserService` |
| 类型 | PascalCase | `UserRole` |
| 枚举 | PascalCase | `Status.Active` |
| 泛型 | 单字母大写 | `T`, `K`, `V` |

> 💡 **相关 skills**: [code-standards](../code-standards/SKILL.md), [react](../react/SKILL.md)
