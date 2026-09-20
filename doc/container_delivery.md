# 容器交付候选

## 范围与状态

目标为本机原生 `linux/arm64`：Python 3.12 API 与 Nginx 静态前端两个服务，BGE 以 Linux CPU 路径为运行候选，Milvus Lite 保留在 API 进程所管理的本地 runtime 中。2026-09-20 两个镜像实际构建成功，仍未完成应用启动、health、合成上传或重启读回验收。

构建成功只证明所选平台上的镜像构建步骤完成；不证明 BGE 权重可下载/加载、Milvus 可启动、模型服务可用或数据可跨重启读回。当前业务仍为已有单用户上传、检索与有限 Agent，不包含事实确认或计算 runtime。

## 文件职责

- `Dockerfile`：`api` 目标安装锁定运行依赖并复制 Python 应用；`web-build` 使用 Node 24 构建静态文件，`web` 只保存静态文件与 Nginx。
- `.dockerignore`：允许应用及构建输入，排除凭据、宿主依赖、数据库及生成输出。
- `compose.yaml`：固定 ARM64 候选，声明服务网络、运行配置及两个命名卷；只将网页入口绑定到宿主机 `127.0.0.1:8080`。
- `deploy/nginx.conf`：提供页面，将 `/api/…` 转为后端 `/…`，关闭代理缓冲以支持现有 SSE。
- `deploy/container.env.example`：运行配置占位模板，不包含可用凭据。

## 依赖与兼容性依据

`pyproject.toml` 将 `mineru[all]` 移到 `mineru` 可选依赖。当前 HTTP 入口明确调用快速解析器；既有 MinerU 适配器读取已有 JSON，不调用 MinerU 引擎。默认运行依赖仍含真实 BGE、PyTorch 与 Milvus Lite，未换成受控替身。

旧默认依赖在 Linux 会通过 MinerU 的 `all` 扩展引入 vLLM，进一步引入 xformers 等原生依赖。锁文件中 xformers 只有 x86_64 wheel 和源码包；这意味着 ARM64 不能直接使用该 wheel，不等于已经实际验证源码构建失败。容器候选按当前产品职责拆分依赖，不尝试在本包内建立 vLLM 平台。

锁文件含 Python 3.12/Linux ARM64 的 Torch、FAISS、PyArrow、PyMuPDF 等关键 wheel 候选。Milvus Lite 官方列出 Ubuntu ARM64 支持；本候选使用 Debian Bookworm 的 Python 镜像，仍需实际加载验证，不能把官方平台列表当作本项目通过证据。Mac 上的 Apple GPU 能力不随容器迁移；Docker Desktop 当前 Linux VM 可用内存约 7.75 GiB，真实 CPU 模型加载和处理峰值未验证。

## 构建

在项目根目录执行以下命令；它们不需要运行时密钥，不启动应用服务：

```bash
docker build --platform linux/arm64 --target api --progress plain -t findoc-api:local .
docker build --platform linux/arm64 --target web --progress plain -t findoc-web:local .
```

`--platform` 选择已约定的平台；`--target` 选择 Dockerfile 中的最终阶段；`--progress plain` 输出可留存的构建步骤；`-t` 给本地镜像命名；末尾 `.` 指定当前目录为构建上下文。基础镜像使用版本系列标签，仍可随上游补丁变化；实际构建日志中的摘要才标识当次基础镜像，不声称不同日期的镜像字节完全一致。

API 使用 `uv sync --locked --no-default-groups --no-install-project`：要求清单与锁文件一致、不安装默认开发组、不安装项目本身；项目通过 `/app` 工作目录导入。未选择 MinerU extra。构建器缓存保存下载包，不进入最终镜像；它与运行时 BGE 模型缓存不同。

## 后续启动前置与数据边界

后续运行前在本机从 `deploy/container.env.example` 创建 `.env.container` 并填入本次授权使用的配置；该文件被 Git 和 Docker 构建上下文排除。不要将凭据放入 Dockerfile、构建参数、前端环境变量或构建日志。Compose 的环境变量注入是本地最小方式，不是专用密钥管理系统。

API 通过既有 `create_isolated_runtime_app_from_env` 工厂启动，`FINDOC_RUNTIME_ROOT=/var/lib/findoc`，数据卷保存文档库、上传对象、Milvus 数据和 Agent Run 库。`HF_HOME=/var/cache/findoc/huggingface` 指定独立模型缓存卷；不复制宿主机 Hugging Face 目录或登录令牌。缓存文件可重建，业务数据应独立保留。

API 以非 root 用户、单 worker、无 reload 运行，保留当前进程内任务分派边界；不支持重启后继续未完成任务。前端使用上游非 root Nginx 镜像。容器内 API 监听 `0.0.0.0:8000` 供前端连接，Compose 不向宿主机发布该端口；宿主机仅发布回环网页入口。

`depends_on` 当前只表达启动顺序，不证明 API 已就绪。health 配置、实际代理/SSE、模型缓存初始化权限、合成上传到 ready、重启后文档/Run 读回均待后续运行验收；本文件不把它们列为已完成。启动过程会在配置核对后先预热 BGE，再初始化 Milvus；BGE 预热失败应阻止半初始化启动。

## 构建证据

2026-09-20 已通过以下构建前检查：

- `uv lock --offline` 与 `uv lock --offline --check`：锁文件一致，仅调整项目的 MinerU extra 关系，未改变包版本。
- `uv sync --locked --no-default-groups --no-install-project --python-platform aarch64-unknown-linux-gnu --dry-run --offline`：目标平台安装计划可生成；只模拟，不修改本机虚拟环境，也未证明目标包实际下载/安装成功。
- `uv export --locked --offline --no-default-groups --no-hashes --no-header --format requirements.txt`：默认依赖导出保留 FlagEmbedding、Torch、PyMilvus、Milvus Lite 和快速解析依赖，不含 MinerU、vLLM、xformers。
- `docker compose --env-file /dev/null config --no-env-resolution --no-interpolate --quiet`：配置可解析。参数分别禁用默认 `.env` 输入、服务环境文件解析及变量插值，检查过程中不读取实际凭据；不证明容器启动。

两条上述 `docker build` 命令均以退出码 0 完成：

| 目标 | 实际结果 | 镜像 ID |
|---|---|---|
| `findoc-api:local` | Linux ARM64，运行用户 `10001:10001`；Python 3.12.14，实际安装 107 个运行依赖 | `sha256:87c5f32a587d99d7eaa7cbf6abc8058da7fc8ce1ed2ef1105518340c8c67d640` |
| `findoc-web:local` | Linux ARM64，运行用户 `101`；实际完成 `npm ci`、TypeScript 检查、Vite 构建及 Nginx 镜像导出 | `sha256:76f4e3b822048047a09b80f1b3851f336990f3b5a7043baf09be038af6344fc9` |

基础镜像使用系列标签，本次容器 Python 为 3.12.14，与宿主项目环境的 3.12.13 补丁版本不同。部分前置构建层命中已有缓存；依赖安装和前端编译实际执行，不称全流程无缓存构建。

原始日志：[API](../artifacts/container-build/api-attempt-1.log)、[前端](../artifacts/container-build/web-attempt-1.log)。[构建证据清单](../artifacts/container-build/build-evidence.json)记录命令、镜像身份、平台、用户及关键输入 SHA-256。构建时基线提交为 `96e0244`，配置当时为未提交增量；清单中的 `source_uncommitted` 保留构建发生时的状态，后续提交不回写原始证据。两次首次实际构建均成功，没有实际构建失败可用作失败案例。安装通过未验证真实模块导入、BGE 权重加载、Milvus 初始化或业务运行。

未调用真实模型，未启动应用服务，未操作其他项目容器或删除已有镜像/数据卷。新增的两个本地镜像及本次构建缓存保留。
