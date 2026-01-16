---
name: react
description: React 开发最佳实践，包含 Hooks、组件设计、状态管理和性能优化
---

# React 最佳实践

## Hooks 使用规则

### 强制规则
```
✅ 只在顶层调用 Hooks
✅ 只在函数组件中调用
❌ 条件/循环中调用 Hooks
❌ 普通函数中调用 Hooks
```

### 常用 Hooks
| Hook | 用途 |
|------|------|
| `useState` | 状态管理 |
| `useEffect` | 副作用处理 |
| `useMemo` | 缓存计算结果 |
| `useCallback` | 缓存函数引用 |
| `useRef` | 保存可变值 |

---

## 组件设计

### 原则
```
✅ 单一职责 - 一个组件做一件事
✅ 组合优于继承
✅ 提升状态到最近共同祖先
✅ 受控组件优先
```

### 文件结构
```
components/
├── UserCard/
│   ├── index.tsx      # 主组件
│   ├── UserCard.tsx   # 实现
│   ├── styles.css     # 样式
│   └── types.ts       # 类型
```

---

## 性能优化

### 避免不必要渲染
```typescript
// ✅ 使用 memo
const UserCard = memo(({ user }: Props) => <div>{user.name}</div>);

// ✅ 使用 useMemo
const sortedList = useMemo(() => list.sort(), [list]);

// ✅ 使用 useCallback
const handleClick = useCallback(() => {}, []);
```

### 懒加载
```typescript
const LazyComponent = lazy(() => import('./HeavyComponent'));
```

---

## 状态管理

| 场景 | 方案 |
|------|------|
| 组件内状态 | useState |
| 跨组件共享 | Context + useReducer |
| 复杂全局状态 | Zustand / Redux |
| 服务端状态 | React Query / SWR |

---

## 禁止事项

```
❌ 直接修改 state
❌ useEffect 依赖数组缺失
❌ 在渲染中执行副作用
❌ props drilling 超过3层
```

> 💡 **相关 skills**: [typescript](../typescript/SKILL.md), [test-driven-development](../test-driven-development/SKILL.md)
