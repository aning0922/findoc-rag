# 本地 ARM64 容器交付

## 范围与状态

目标为本机原生 `linux/arm64`：Python 3.12 API 与 Nginx 静态前端两个服务，BGE 在 Linux CPU 上运行，Milvus Lite 保留在 API 进程所管理的本地 runtime 中。2026-09-20 两个镜像实际构建成功；2026-09-22 复用原镜像，完成真实依赖启动、合成 PDF 上传至 ready、替换容器后文档读回，以及独立受控浏览器 Run 创建和重建读回。

真实依赖与受控证据分开：真实路径证明 BGE/Milvus 和文档链；Run 使用 fake embedding/store/provider 与真实业务 API、SQLite，未调用付费 LLM，也不证明真实模型回答质量。持久化承诺限于已 ready 文档和已保存终态 Run，不保证重启后恢复中途任务。当前业务不包含事实确认或计算 runtime。

## 文件职责

- `Dockerfile`：`api` 目标安装锁定运行依赖并复制 Python 应用；`web-build` 使用 Node 24 构建静态文件，`web` 只保存静态文件与 Nginx。
- `.dockerignore`：允许应用及构建输入，排除凭据、宿主依赖、数据库及生成输出。
- `compose.yaml`：固定 ARM64 候选，声明服务网络、运行配置及两个命名卷；只将网页入口绑定到宿主机 `127.0.0.1:8080`。
- `deploy/nginx.conf`：提供页面，将 `/api/…` 转为后端 `/…`，关闭代理缓冲以支持现有 SSE。
- `deploy/container.env.example`：运行配置占位模板，不包含可用凭据。
- `compose.controlled.yaml`：独立受控项目、独立业务卷，复用现有 C1 装配；不得与真实 Compose 文件合并。
- `scripts/seed_container_model_cache.py`：在临时容器中核对并复制 BGE 必需公开文件，不导入宿主凭据。
- `frontend/scripts/verify-container-persistence.mjs`：浏览器真实创建 Run，替换受控容器后刷新 GET，核对结果、事件与卷身份。

## 依赖与兼容性依据

`pyproject.toml` 将 `mineru[all]` 移到 `mineru` 可选依赖。当前 HTTP 入口明确调用快速解析器；既有 MinerU 适配器读取已有 JSON，不调用 MinerU 引擎。默认运行依赖仍含真实 BGE、PyTorch 与 Milvus Lite，未换成受控替身。

旧默认依赖在 Linux 会通过 MinerU 的 `all` 扩展引入 vLLM，进一步引入 xformers 等原生依赖。锁文件中 xformers 只有 x86_64 wheel 和源码包；这意味着 ARM64 不能直接使用该 wheel，不等于已经实际验证源码构建失败。容器候选按当前产品职责拆分依赖，不尝试在本包内建立 vLLM 平台。

锁文件含 Python 3.12/Linux ARM64 的 Torch、FAISS、PyArrow、PyMuPDF 等关键 wheel。2026-09-22 在 Debian Bookworm 镜像中实际完成 BGE 预热、Milvus 初始化与上传索引。Mac 上的 Apple GPU 能力不随容器迁移；Docker Desktop 本次 Linux VM 内存约 7.75 GiB，真实 API 启动后观察到约 3.0 GiB 占用；这不是峰值或容量压测。

## 构建

在项目根目录执行以下命令；它们不需要运行时密钥，不启动应用服务：

```bash
docker build --platform linux/arm64 --target api --progress plain -t findoc-api:local .
docker build --platform linux/arm64 --target web --progress plain -t findoc-web:local .
```

`--platform` 选择已约定的平台；`--target` 选择 Dockerfile 中的最终阶段；`--progress plain` 输出可留存的构建步骤；`-t` 给本地镜像命名；末尾 `.` 指定当前目录为构建上下文。基础镜像使用版本系列标签，仍可随上游补丁变化；实际构建日志中的摘要才标识当次基础镜像，不声称不同日期的镜像字节完全一致。

API 使用 `uv sync --locked --no-default-groups --no-install-project`：要求清单与锁文件一致、不安装默认开发组、不安装项目本身；项目通过 `/app` 工作目录导入。未选择 MinerU extra。构建器缓存保存下载包，不进入最终镜像；它与运行时 BGE 模型缓存不同。

## 启动前置与数据边界

运行前在本机从 `deploy/container.env.example` 创建 `.env.container` 并填入授权使用的配置，将文件权限限制为 `0600`；该文件被 Git 和 Docker 构建上下文排除。不要将凭据放入 Dockerfile、构建参数、前端环境变量或构建日志。Compose 的环境变量注入是本地最小方式，不是专用密钥管理系统。`from_env` 读取进程环境，不自行加载 `.env`；配置在创建容器时注入。修改环境文件后须重新创建容器，单纯 restart 不会读取新配置。

API 通过既有 `create_isolated_runtime_app_from_env` 工厂启动，`FINDOC_RUNTIME_ROOT=/var/lib/findoc`，数据卷保存 `documents.db`、`objects/`、Milvus 数据和 `agent-runs.db`。`HF_HOME=/var/cache/findoc/huggingface` 与 `TIKTOKEN_CACHE_DIR=/var/cache/findoc/tiktoken` 使用独立模型缓存卷。首次缓存准备只允许复制选定公开模型文件，不整体复制宿主 Hugging Face 目录或登录令牌。缓存可重新获取，业务数据应独立保留。

API 以非 root 用户、单 worker、无 reload 运行，保留当前进程内任务分派边界；不支持重启后继续未完成任务。前端使用上游非 root Nginx 镜像。容器内 API 监听 `0.0.0.0:8000` 供前端连接，Compose 不向宿主机发布该端口；宿主机仅发布回环网页入口。

`healthcheck` 在 API 容器内请求 `/health`；`depends_on: condition: service_healthy` 让 web 等待 API 首次健康。`/health` 返回进程响应状态，不持续探测所有依赖，也不等待文档后台任务；业务上传仍需单独等到 ready。启动过程先核对配置、预热 BGE，再初始化 Milvus；失败阻止应用对外服务。`stop_grace_period: 30s` 给进程正常退出机会，不代表任务可恢复。web 本身没有 Docker healthcheck，其页面和代理通过实际 HTTP/浏览器验证。

## 启动与受控验收命令

以下命令在项目根目录执行，要求 Docker、已有镜像，以及宿主 Node 24/前端 Playwright 依赖（仅浏览器验证需要）。`--env-file /dev/null` 禁止 Compose 默认读取项目 `.env` 进行插值；API 的显式 `env_file: .env.container` 仍会加载。

若复用宿主已有 BGE 缓存，先检查磁盘、内存与源文件；以下辅助容器只把白名单模型文件复制到缓存卷，并核对 SHA-256。没有现成缓存时可由模型库首次下载，需网络和足够资源；本次没有验证空缓存在线下载整套 BGE 的路径。

```bash
export FINDOC_BGE_CACHE="$HOME/.cache/huggingface/hub/models--BAAI--bge-m3"
docker compose --env-file /dev/null -f compose.yaml run --rm --no-deps -T \
  --entrypoint /app/.venv/bin/python \
  --volume "$FINDOC_BGE_CACHE:/model-source:ro" api - \
  < scripts/seed_container_model_cache.py

docker compose --env-file /dev/null -f compose.yaml up -d \
  --no-build --pull never --wait --wait-timeout 600
curl --fail http://127.0.0.1:8080/api/health
curl --fail -F file=@artifacts/demo/synthetic_finance_demo.pdf \
  http://127.0.0.1:8080/api/documents
```

`--rm` 在辅助命令结束后删除辅助容器；`--no-deps` 不启动其他服务；`-T` 不分配终端，允许从标准输入传 Python 源码。挂载的 `:ro` 表示源模型只读。`up -d` 后台启动，`--no-build`/`--pull never` 保证复用已有镜像，`--wait` 等待健康条件，`--wait-timeout` 是本次等待上限。`curl --fail` 遇 HTTP 错误返回非零，`-F` 发送文件表单；上传返回 202 只表示已接受。

记录返回的 `document_id`，用 `GET /api/documents/{document_id}` 等到 ready，再执行以下替换操作并再次 GET 相同 ID。重建 web 使 Nginx 在启动时重新解析 API 服务地址；未验证只替换 API 时 Nginx 的地址自动刷新。

```bash
docker compose --env-file /dev/null -f compose.yaml up -d \
  --no-build --pull never --force-recreate --wait --wait-timeout 600
```

`--force-recreate` 更换容器，继续使用原命名卷，不重新构建镜像。实际默认卷名为 `findoc-d1_runtime-data` 与 `findoc-d1_model-cache`，容器目录名相同不意味着与其他项目共用卷。改变 Compose 项目名可能指向新卷；改变数据根时必须同步修改 `FINDOC_RUNTIME_ROOT`、挂载目标及目录权限。

无付费模型的 Run 验证使用独立文件与项目，不读取 `.env.container`：

```bash
docker compose --env-file /dev/null -f compose.controlled.yaml up -d \
  --no-build --pull never --wait --wait-timeout 90
node frontend/scripts/verify-container-persistence.mjs
```

脚本访问 `127.0.0.1:18081`，点击页面创建 Run，然后精确替换受控项目的 api/web 容器，保留 `findoc-d1-controlled_controlled-runtime-data`。核对容器 ID 变化、镜像与卷不变、刷新只 GET、结果与事件一致。测试代码只读挂载，生产默认 factory 不变。受控预置文档和空 Milvus 标记不是上传/索引证据；Run 本身经真实 API、业务逻辑及 SQLite 创建，未直接写库或复制旧库。

仅停止服务时分别使用 `docker compose --env-file /dev/null -f <文件> stop`；需要删除本项目容器和网络时使用相同前缀的 `down`。两者都保留命名卷；`down -v` 会删除卷，本次验证不使用。重新创建完整服务使用上面的 `up` 命令。

## 2026-09-22 运行证据与限制

| 项目 | 真实观察 |
|---|---|
| 镜像 | 复用下方两个 09-20 镜像，没有重建或拉取 |
| 缓存和权限 | BGE snapshot `5617a9f61b028005a4858fdac845db406aefb181` 的 12 个白名单文件摘要一致；两个卷根目录属于 `10001:10001` 且 API 用户可写 |
| 真实业务 | BGE CPU 预热、Milvus 初始化、合成 PDF 上传返回 202，后续 GET 为 ready |
| 容器替换 | 真实 api/web 的 ID 均变化，挂载的两个卷不变；同一文档完整响应一致，原 PDF 内容摘要一致，浏览器展示 ready |
| 受控 Run | Chromium 经 Nginx 创建 answered；替换受控 api/web 后刷新，GET 原 Run/结果/事件一致，浏览器总计一次创建 POST |
| 启动失败边界 | 无网络的一次性容器调用同一真实 factory；缺 `LLM_API_KEY` 抛 KeyError，业务根目录未创建 |

本次 `.env.container` 使用无有效供应商凭据的配置，LLM URL 指向容器自身不可用端口；配置构造不调用供应商。BGE 缓存准备完成后显式开启 HF/Transformers 离线模式。模型配置存在性通过不代表真实凭据可用。首次上传期间观察到 health 为 200、文档停留 parsing；之后分词文件取得并完成 ready。新配置将 tiktoken 编码表也保存在缓存卷中；其 SHA-256 为 `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`。未断言具体网络故障原因。

结构化证据：[真实文档](../artifacts/container-runtime/real-document.json)、[受控 Run](../artifacts/container-runtime/controlled-run.json)、[环境及检查清单](../artifacts/container-runtime/runtime-evidence.json)、[缓存摘要](../artifacts/container-runtime/model-cache.json)。截图：[真实文档读回](../artifacts/container-runtime/real-restored.png)、[受控结果读回](../artifacts/container-runtime/controlled-restored.png)。证据仅含合成数据和必要运行身份，不保存完整 env/config。

仍未验证：付费 LLM 与真实 Agent 回答、SSE 经 Nginx 的实际流式传输、未完成任务恢复、其他架构/平台、全新网络环境下载 BGE、资源峰值及并发容量。现有试验没有修改默认业务装配来绕过重依赖。

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

原始日志：[API](../artifacts/container-build/api-attempt-1.log)、[前端](../artifacts/container-build/web-attempt-1.log)。[构建证据清单](../artifacts/container-build/build-evidence.json)记录命令、镜像身份、平台、用户及关键输入 SHA-256。构建时基线提交为 `96e0244`，配置当时为未提交增量；清单中的 `source_uncommitted` 保留构建发生时的状态，后续提交不回写原始证据。两次首次实际构建均成功，没有实际构建失败可用作失败案例。这些构建日志本身不证明模块加载和业务运行；后续运行证据见上节。

09-20 构建时未调用真实模型或启动应用服务，未操作其他项目容器或删除已有镜像/数据卷。该历史事实保留；09-22 新增的运行验证与状态单列在上节。
