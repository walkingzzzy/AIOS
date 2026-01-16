---
name: TypeScript Best Practices
version: 1.0.0
description: TypeScript 开发最佳实践指南，包含类型系统、架构模式和常见问题解决方案
category: development
keywords: [typescript, ts, 类型系统, 泛型, 接口, 类型推导]
author: AIOS Team
enabled: true
priority: 8
---

# TypeScript 最佳实践

## 类型定义原则

### 1. 优先使用 interface 而非 type
```typescript
// 推荐
interface User {
    id: string;
    name: string;
}

// 仅在需要联合类型或映射类型时使用 type
type Status = 'active' | 'inactive';
```

### 2. 严格的类型检查
确保 tsconfig.json 启用：
```json
{
    "compilerOptions": {
        "strict": true,
        "noUncheckedIndexedAccess": true,
        "noImplicitReturns": true
    }
}
```

### 3. 泛型使用
```typescript
// 良好的泛型约束
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
    return obj[key];
}
```

## 常见模式

### 类型守卫
```typescript
function isUser(value: unknown): value is User {
    return typeof value === 'object' && value !== null && 'id' in value;
}
```

### 工具类型活用
- `Partial<T>` - 所有属性可选
- `Required<T>` - 所有属性必需
- `Pick<T, K>` - 选取部分属性
- `Omit<T, K>` - 排除部分属性
- `Record<K, V>` - 构建对象类型

## 常见错误避免

1. 避免使用 `any`，使用 `unknown` 替代
2. 不要过度使用类型断言 (`as`)
3. 处理 `null` 和 `undefined` 要显式
4. 正确使用 `readonly` 防止意外修改
