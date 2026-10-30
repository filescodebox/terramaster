# TOS 7 官方 Docker 应用包（铁威马）

本目录是升级到 **TOS 7 官方 Docker 应用包**（应用中心形态）的包体。
TOS 7 的 Docker 应用 = **恰好 4 个文件**的 tar.gz：

```
pigeonbox.tar.gz
├── config.ini          # 应用元数据（JSON）
├── pigeonbox.lang      # 多语言文件（14 种语言）
├── pigeonbox.svg       # 应用图标（SVG，viewBox 推荐 0 0 512 512）
└── docker-compose.yml  # 容器编排
```

> ⚠️ `README.md`（本文件）**不打包**（官方模板原话：打包前删除）。
> 打包命令：`tar -czf pigeonbox.tar.gz config.ini pigeonbox.lang pigeonbox.svg docker-compose.yml`

**地面真相**（一切规则以它为准，别凭印象写）：

- 官方开发指南 `TOS 7 Application Development Guide/09_Docker_Development.md`
- 官方模板 `TOS 7-template-docker/`
- 仓库：<https://github.com/terramaster-tos/tos-app-pkg-tools>

本目录的合规性由 **`scripts/check_tos7_package.py`** 机器校验（CI 强制），
校验器自身的判据有效性由 **`scripts/check_tos7_package_test.py`** 变异自测保证
（每条规则都注入一次违规、断言必须判红）。

---

## 一、官方规则要点（逐条对应 Chapter 9 §9.3）

| # | 规则 | 本包落点 |
|---|---|---|
| 1 | Compose Spec **3.8+** | `version: "3.8"` |
| 2 | 有 Web UI 的应用必须带顶层 **`x-app-meta`**（含 `web.port` / `web.protocol`），且**附在文件末尾** | `x-app-meta.web.port = 12345`（**host** 端口）、`protocol = http` |
| 3 | **`volumes` / `ports` 序列内不得有注释行** —— 平台逐行解析这两块，遇到 `#` 会**提前中断该块** ⇒ 挂载目录的 chown 被**静默跳过** | 两个序列都保持连续无注释 |
| 4 | 数据必须挂载。宿主侧路径用**相对路径** `./data`（平台落到 `/Volume<N>/DockerAppData/<appid>/`） | `volumes: ./data:/app/data` |
| 5 | host 端口**禁用清单**：22 / 80 / 443 / 445 / 3306 / 5050 / 5432 / 6379 / 8181 / 8443；推荐区间 8000–19999 | `12345:8080` |
| 6 | **禁** `privileged: true`；非 root 用 `user:` 钉 UID:GID | `1000:1000` / `101:101`（见下） |
| 7 | 显式 `TZ` **非必需**（容器读宿主时区）；设了就保持一致 | `TZ=${TZ:-Asia/Shanghai}` |
| 8 | 容器名在 Docker daemon 上**全局唯一**即可 | `pigeonbox-server` / `pigeonbox-frontend` |
| 9 | `restart: unless-stopped` | 两个服务都设 |
| 10 | **禁** `network_mode: host`（用端口映射代替） | 未使用 |
| 11 | **每个服务**都要有 `healthcheck`；多容器用 `depends_on: condition: service_healthy` | 两个服务都有；frontend 等 backend healthy |
| 12 | 具名卷必须在**顶层 `volumes:`** 声明，否则 Compose 直接拒整个项目 | 本包全用 bind mount，无需顶层声明 |
| 13 | 全部文件 **LF** 行尾（禁 CRLF） | 校验器强制 |

### 两个 `user:` 的取值不是猜的

取自**各自镜像自己的 Dockerfile**：

| 服务 | 镜像 | 运行用户 | 出处 |
|---|---|---|---|
| `pigeonbox` | `ghcr.io/pigeonbox/server` | `1000:1000` | `server/Dockerfile`：`adduser -D -u 1000` + `USER app` |
| `pigeonbox-frontend` | `ghcr.io/pigeonbox/frontend` | `101:101` | `frontend-core/Dockerfile`：基于 `nginxinc/nginx-unprivileged`（uid/gid=101 非 root） |

官方规则原文：「If the image hard-codes its runtime user and does not support PUID/PGID,
set it to that image's own UID:GID（guide 10.3.1）」——本包正是这种情况。

### 首启不需要注入管理员口令

镜像自带的 `/app/docker-entrypoint.sh` 已把两件事下沉到镜像层：

1. JWT 密钥留空 ⇒ 首启生成强随机值并持久化到数据目录（重启/升级不丢）；
2. `PB_ADMIN_PASSWORD` 留空 ⇒ 自动切 `/setup` **首启向导**模式
   （不播种弱口令 `admin/admin123`；core 的生产门禁仍在，只是换成「自己当场建一个」）。

⇒ TOS 应用包没有 `.env` 机制，也**不需要**——安装后浏览器打开
`http://<NAS_IP>:12345` 走完 `/setup` 建管理员即可。

---

## 二、本轮修正的 5 处规则描述（与官方冲突）

下面 5 条是本目录此前的 README 写的，**与官方 Chapter 9 冲突**，照着写会踩坑：

| # | 原描述 | 官方实际（Chapter 9 出处） | 为什么原描述危险 |
|---|---|---|---|
| 1 | 「数据必须挂 `/Volume*/DockerAppData/<appid>/`」 | §9.3 Rule 4：**平台不展开 `*`**。写 `/Volume*/…` 会**真的建出一个名为 `/Volume*` 的目录**，数据写到那儿，不在应用数据根里、卸载时也不被「删除数据」清掉。应用侧应写**相对路径** `./data`，平台负责落到 `/Volume<N>/DockerAppData/<appid>/` | 直接照写 ⇒ 数据落在字面量 `/Volume*` 目录，备份/卸载/迁移全错位 |
| 2 | 「`container_name` 须等于应用 id」 | 官方**自相矛盾**：模板清单写「== id」，但 §9.3 Rule 8 写「容器名可自定义，只要在 Docker daemon 上全局唯一」；且官方模板自己的**多容器示例**用的就是 `app-db` / `app-web` 这种**非 id** 名 | 多容器应用**不可能**两个服务都叫 id ⇒ 按 Rule 8（全局唯一）裁决 |
| 3 | 「必须显式 TZ」 | §9.3 Rule 7：显式 TZ **非必需**（容器默认读宿主时区），模板里的 TZ 只是示例 | 把它当硬规则会让「不设 TZ」被误判为违规 |
| 4 | 「host port NOT in disabled list: 22, 80, 443, 8181, 5050」 | §9.3 Rule 5 的**完整**禁用清单是 22 / 80 / 443 / **445 / 3306 / 5432 / 6379 / 8443** / 5050 / 8181（模板注释里那份短清单**不完整**） | 按短清单选端口可能撞上 3306 / 6379 / 8443 等系统端口 ⇒ 送审被拒 |
| 5 | （未提） | §9.3 Rule 3：**`volumes` / `ports` 序列内不得有注释行** | 平台逐行解析这两块，遇 `#` 提前中断 ⇒ 挂载目录的 chown 被**静默跳过**（不报错，但权限错） |

另修一处**命名误解**：官方模板里的文件叫 `myapp-docker.lang` / `myapp-docker.svg`，
是因为模板的 appid 恰好叫 `myapp-docker`；官方 README 的替换步骤是
「Globally replace "myapp-docker" with your application id（**including file names**）」。
⇒ 本包的命名就是 `pigeonbox.lang` / `pigeonbox.svg`，**不带 `-docker` 后缀**。
同时图标须**平铺到包根**（4 文件包只收文件，不收目录）。

---

## 三、还没就绪的（送审前置）

| # | 事项 | 性质 | 现状 |
|---|---|---|---|
| 1 | **镜像须同步到 Docker Hub** | **生态层决策，待拍板** | TOS 应用商店**只收 Docker Hub 镜像**，拒收 ghcr.io / quay.io / 私有仓库。本包 `docker-compose.yml` 里两处 image 仍是生态现行源 `ghcr.io` ⇒ **送审前必须换成 Docker Hub 引用**。是否给生态镜像线新增 Docker Hub 发布通道（牵动 server 仓 release 流水线的凭据与 tag 矩阵）= 生态层决策。校验器把这一条报成**黄灯**（送审前置未就绪），不是规则违规。 |
| 2 | `tos7/` 不在列车的物化清单里 | 流程缺口 | 列车 bump 只物化 `VERSION` / `deploy/compose.yml` / `deploy/env.example`，**不含 `tos7/`** ⇒ 包里钉的镜像 tag 不会随列车自动抬 ⇒ 须**手工同步**。校验器把这一条报成**黄灯**。 |
| 3 | 多架构送审 | 平台要求 | `config.ini` 的 `platform` 一次只能填一个（`x86_64` 或 `aarch64`），TOS 要求**一平台一提交** ⇒ 需按架构各打包一次。 |
| 4 | 真机验证 | 需设备 | TOS 5/6/7 真机装包 → 起服务 → 分享/取件闭环。 |
| 5 | 送审 | 需账号 | developer.terra-master.com 平台自动校验 + 人工审核。 |

---

## 四、参考

- 官方开发指南 + 模板：<https://github.com/terramaster-tos/tos-app-pkg-tools>
  - `TOS 7 Application Development Guide/09_Docker_Development.md`
  - `TOS 7-template-docker/`（`config.ini` / `docker-compose.yml` / `myapp-docker.lang` / `myapp-docker.svg` / `README.md`）
- 官方开发指南（全集）：`TOS 7 Application Development Guide/`
- 现行可用形态（Docker Manager 粘贴 compose）：<https://github.com/pigeonbox/terramaster/releases>
- 生态主仓：<https://github.com/pigeonbox/pigeonbox>
