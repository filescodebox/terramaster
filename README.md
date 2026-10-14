# PigeonBox TerraMaster TOS

[![CI](https://github.com/pigeonbox/terramaster/actions/workflows/ci.yml/badge.svg)](https://github.com/pigeonbox/terramaster/actions/workflows/ci.yml)
[![Release](https://github.com/pigeonbox/terramaster/actions/workflows/release.yml/badge.svg)](https://github.com/pigeonbox/terramaster/releases)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)

PigeonBox（文件快递柜，匿名口令分享文本/文件）的 **铁威马 TerraMaster TOS 部署包**：官方 Docker 镜像（`ghcr.io/pigeonbox/server` + `frontend`）的 docker compose 项目导入部署。

- **TOS 5 / 6 / 7 全覆盖**：三代的 Docker 管理器都有「项目」功能，导入即部署
- 默认端口 `12345` 合规（TOS 保留 22/80/443/8181/5050，推荐第三方用 8000-19999）
- JWT 密钥首启自动生成并持久化到数据目录，重启/升级不丢
- 开机自启：编排内已置 `restart: unless-stopped`（另请把 Docker 应用设为自动启动）
- 默认关闭开放注册（NAS 场景，管理员建号）
- 设备直传：server 镜像自 1.21.0 起随包 p2pc，compose 部署即具设备直传能力；admin「系统配置→P2P」分区热启停联邦与设备直传

> TOS 没有免审的第三方应用通道：应用中心手动安装只收 `.tpk`/`.deb`，TOS 7 官方
> Docker 应用包（4 文件）走平台送审且**拒收 ghcr 镜像**——为二期路线（见 [tos7/](./tos7/README.md)）；
> 当前形态零门槛、覆盖三代系统、更新最即时。

## 安装（5 分钟）

1. 应用中心确认已装 **Docker**（TOS 7 叫 Container/ Docker Manager；TOS 7 未装会提示自动装 DockerEngine）
2. 下载本仓 [Releases](https://github.com/pigeonbox/terramaster/releases) 的部署包 zip 并解压
3. 打开 **Docker Manager**（Docker 应用）→ 左侧 **项目** → 右上角 **添加**
4. 项目名 `pigeonbox`，项目路径选数据卷（如 `/Volume1/Docker/pigeonbox`），
   配置来源选「**你的电脑**」上传 `compose.yml`（或「创建 YAML 文件」后把全文粘入），并把 `PB_ADMIN_PASSWORD` 一行改为你的强密码（**必填**：安全生产模式，留空=容器拒绝启动）
5. 点 **验证 YAML**（校验通过「应用」才可点）→ **应用**
6. 浏览器访问 `http://NAS的IP:12345`，管理员 `admin`，密码=第 4 步设置的值

### 常用调参（导入前直接在 YAML 里改）

| 位置 | 默认 | 说明 |
|---|---|---|
| `ports: "12345:8080"` | `12345` | 对外端口（避开 22/80/443/8181/5050） |
| `/volume1/docker/pigeonbox/data:/app/data` | 见左 | 数据目录（建议改到数据卷，如 `/Volume1/Docker/pigeonbox/data`） |
| `PB_ADMIN_PASSWORD` | 空 | 管理员密码（**必填**：留空=容器拒绝启动；首次启动以此建号） |
| `PB_USER_ALLOW_REGISTRATION` | `false` | 开放注册开关 |

装好后的日常修改：Docker Manager → 项目 → 编辑 compose → 重新部署，配置持久在项目里。

## ghcr 拉取失败（国内网络）

TOS 的 `registry-mirrors` 加速只对 docker.io 生效，对 ghcr 无效，可行做法：

- 镜像前缀替换：`ghcr.io/pigeonbox/server` → `ghcr.nju.edu.cn/pigeonbox/server`（改 compose 后重新部署）
- 离线导入：任意外网机器 `docker pull` + `docker save` 出 tar，上传 NAS 后
  Docker Manager → 本地镜像 → 导入，再部署项目

## 数据与备份

- 数据全在 compose 里的数据目录（默认 `/volume1/docker/pigeonbox/data`：
  `fileCodeBox.db`、上传文件、`.jwt_secret`；**建议放到数据卷**）
- 备份 = 停止项目后复制该目录
- 删除项目**不会**删数据目录；彻底清理请手动删除

## 常见问题

- **验证 YAML 不通过**：检查粘贴是否完整（首行 `services:`），或 TOS 版本过旧（TOS 5 需 Docker Manager 2.0+）
- **容器反复重启/页面 502**：等 1-2 分钟（后端健康检查通过后前端才放行）；仍异常看容器日志
- **取件/上传报权限错误**：数据目录属主需与容器内运行身份一致（uid 1000），SSH 执行
  `chown -R 1000:1000 <数据目录>` 后重新部署项目
- **重启后容器没起来**：把 Docker 应用设为「自动启动」（桌面图标右键 → 设置），compose 的
  `restart: unless-stopped` 才有宿主前提

## 升级

改 compose 里两处镜像 tag（`server`/`frontend` 的 `:vX.Y.Z`，与 [server 仓 Releases](https://github.com/pigeonbox/server/releases) 对齐）→ 重新部署。数据目录不动，配置/数据全保留。

## 开发与构建

共享资产（`compose.yml` / `env.example`）的**真相源在生态主仓 [`deploy/nas/`](https://github.com/pigeonbox/pigeonbox/tree/main/deploy/nas)**：改编排/默认值请改 hub 模板后执行 `bash deploy/nas/sync.sh sync --all`（单仓 `sync --platform <p> --dir <仓>`），**勿直接改本仓这两个文件**——CI 有「与 hub 模板对齐」漂移门禁，模板一动未同步的仓全部变红。跟随 server 新镜像版本走发布列车 v2：hub `make train-bump TRAIN=x.y.z`（`release/trainctl` 状态机）统一完成镜像钉版刷新与各仓打 tag。
```sh
./scripts/build-zip.sh 0.1.0     # → dist/pigeonbox-terramaster-0.1.0.zip(发布资产)
docker compose -f deploy/compose.yml config -q   # 模板校验
```

打 `v*` tag 自动：组装部署包 → 挂本仓 Release → 回挂生态主仓 `terramaster-v*` Release（需 `TERRAMASTER_PAT`，未配置时 CI 放行失败、本地 `gh release upload` 兜底）。

**真机验证状态**：compose 模板过 CI；TOS 真机项目导入验证待补（欢迎反馈 issue）。

## TOS 7 官方应用包二期

见 [tos7/README.md](./tos7/README.md)：4 文件 Docker 应用包（config.ini + lang + svg + compose），
需先把镜像同步到 Docker Hub（商店拒收 ghcr），经 developer.terra-master.com 送审上架。

## 参考

- [terramaster-tos/tos-app-pkg-tools](https://github.com/terramaster-tos/tos-app-pkg-tools)（官方 TOS 7 应用开发指南与模板）
- [TOS 6 Docker Manager 官方文档](https://help.terra-master.com/cn/docs/TOS6/application/docker-manager)（项目导入流程）
- [TOS 应用中心手动安装](https://help.terra-master.com/cn/docs/TOS6/tos-desktop/app-center)
- ghcr 国内加速前缀 `ghcr.nju.edu.cn`（南京大学镜像站,可用性随时间变化）

## License

Apache-2.0（与生态一致，见 [LICENSE](./LICENSE)）。
