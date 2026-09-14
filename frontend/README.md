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

### 受控浏览器 E2E

这条测试使用预置ready合成文档和fake embedding／检索store／provider，但保留真实浏览器、Vite代理、FastAPI、Agent loop、结果验证与临时SQLite。它不上传文档、不读取`.env`、不调用模型或真实Milvus，也不证明真实模型和检索质量。

本地前置为Node 24、仓库根目录现有`.venv`中的受控后端依赖，以及与项目版本一致的Chromium：

```bash
nvm use
npm --prefix frontend ci
cd frontend
npx playwright install chromium
npm run test:e2e
```

`npm run test:e2e`每次创建新的绝对临时runtime，默认把受控API和Vite分别绑定到`127.0.0.1:18080`和`127.0.0.1:14173`，端口已占用时直接失败而不复用未知服务。可用`FINDOC_E2E_API_PORT`与`FINDOC_E2E_WEB_PORT`成对覆盖。Playwright先以`/health`等待进程，再由浏览器核对`/api/documents`确实返回受控文档；退出时由Playwright和启动脚本回收服务与临时目录。失败入口为`frontend/playwright-report/index.html`。

新的CI环境只需从锁文件安装`e2e`依赖组，不必安装MinerU、FlagEmbedding、sentence-transformers或Milvus：

```bash
uv sync --only-group e2e --frozen
```

`--only-group e2e`适合新的专用环境；不要用它覆盖仍需完整开发依赖的现有`.venv`。GitHub Actions候选还会运行Node纯测试、lint、build、受控后端定向测试和单Chromium E2E；本地通过不代表远端工作流已经运行。

当前不实现多页面、复杂状态库、富文本、PDF预览、对话持久化、token逐字直通或CSS美化。
