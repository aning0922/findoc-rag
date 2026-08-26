# FinDoc 浏览器薄壳

React、TypeScript 和 Vite 实现的单页学习原型，负责上传PDF、轮询文档状态、选择ready文档、通过POST读取SSE问答流，并展示可信答案、正常拒答、安全错误和服务端验证引用。

## 本地运行

在仓库根目录执行：

```bash
nvm use
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
```

Vite将`/api`代理到`http://127.0.0.1:8000`。后端应单独启动且不使用`--reload`，避免内存文档任务因重载丢失。

## 质量门

```bash
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run lint
```

当前不实现多页面、复杂状态库、富文本、PDF预览、对话持久化、token逐字直通或CSS美化。
