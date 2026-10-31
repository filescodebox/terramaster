#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOS 7 官方 Docker 应用包（tos7/）合规校验器。

# 为什么要有这个脚本

TOS 7 应用商店对 Docker 应用的校验规则**只存在于官方开发指南**里
（github.com/terramaster-tos/tos-app-pkg-tools →
`TOS 7 Application Development Guide/09_Docker_Development.md`），
散落在章节正文、官方模板的注释清单、以及模板 README 的 Compliance Checklist 三处，
且**彼此不完全一致**（例：官方模板清单写「container_name == 应用 id」，
而 Chapter 9 §9.3 Rule 8 写「容器名可自定义，只要在 Docker daemon 上全局唯一」——
官方模板自己的多容器示例用的也是 `app-db` / `app-web` 这种**非 id** 名）。

⇒ 靠人记这些规则 = 必然漂移。本脚本把**能定论**的规则逐条变成机器判据，
CI 强制：包漂了当场红，不等到送审被平台打回。

# 两级判定

- **红灯（规则违规）**：违反 TOS 平台的硬规则 ⇒ 送审必被打回 ⇒ 退出码非 0。
- **黄灯（送审前置未就绪）**：不是本仓能单方面决定的 ⇒ 只提示，不阻断。
  当前一条：黄灯 compose 里的镜像 tag 与本仓 VERSION 不一致。
  ⇒ 该条现为**漂移哨兵**：`tos7/docker-compose.yml` 已进列车 bump 的物化清单
  （`SetPinnedImageTag`），正常态恒绿；黄 ⇒ 说明物化被绕过或版本被手工改过。

2026-10-31：原「黄灯-1 镜像源不是 Docker Hub」已**升级为红灯**——
  生态镜像线新增 Docker Hub 发布通道后，「镜像源不是本仓能单方面决定的」
  这个前提不成立 ⇒ 它是平台必拒的规则违规 ⇒ 留在黄灯等于门禁永远不响。

# 零依赖

刻意不引入 PyYAML：TOS 平台自己就是**逐行解析** compose 的
（§9.3-3：安装器逐行读 volumes/ports 块，遇到 "#" 提前中断），
本脚本也按行解析 ⇒ 判定口径与平台一致，且任何环境都能跑。
"""
from __future__ import annotations

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 可选参数：待校验的包目录（默认本仓 tos7/）。自测脚本用临时副本跑变异验证。
PKG = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(REPO, "tos7")

# ── 官方规则常量（出处：Chapter 9 §9.3 / §9.3 Rule 5）────────────────────────
DISABLED_HOST_PORTS = {22, 80, 443, 445, 3306, 5050, 5432, 6379, 8181, 8443}
RECOMMENDED_PORT_RANGE = (8000, 19999)
REQUIRED_LANGUAGES = [
    "en-us", "zh-cn", "zh-hk", "fr-fr", "de-de", "it-it", "es-es",
    "hu-hu", "ja-jp", "ko-kr", "pl-pl", "ru-ru", "tr-tr", "pt-pt",
]
# 官方 docker 模板 config.ini 的字段集（多一个少一个都要红——未知字段会被
# 平台忽略，等于白写；缺字段则平台按默认值填，行为与预期不符）。
OFFICIAL_CONFIG_KEYS = {
    "id", "icon", "publisher", "path", "exec", "open_path", "resize", "maxmin",
    "width", "height", "help", "version", "recommend", "beta", "low_version",
    "category", "depend", "relation", "platform", "official",
    "application_type", "system_id", "package", "compose_project", "user",
    "all_user_display", "allow_open_in_mobile",
}
# 打包清单：恰好 4 个文件（README.md 打包前必须删除，官方模板原话）
PACKAGE_FILES = ("config.ini", "{appid}.lang", "{appid}.svg", "docker-compose.yml")
PACKAGE_EXCLUDED = ("README.md",)

red: list[str] = []
yellow: list[str] = []


def fail(msg: str) -> None:
    red.append(msg)


def warn(msg: str) -> None:
    yellow.append(msg)


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def find_line(text: str, needle: str) -> int:
    """返回 needle 首次出现的行号（1 起）；找不到返回 0。

    为什么要有：错误消息要指到**具体行**（平台逐行解析 compose，
    「第 47 行」比「某处」有用得多）。
    """
    for i, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return i
    return 0


# ── 1. 打包清单：恰好 4 个文件 ───────────────────────────────────────────────
def check_package_files(appid: str) -> None:
    present = sorted(
        f for f in os.listdir(PKG)
        if os.path.isfile(os.path.join(PKG, f)) and not f.startswith(".")
    )
    expected = sorted(f.format(appid=appid) for f in PACKAGE_FILES)
    missing = [f for f in expected if f not in present]
    extra = [
        f for f in present
        if f not in expected and f not in PACKAGE_EXCLUDED
    ]
    if missing:
        fail(f"打包清单缺文件：{missing}（官方要求恰好 4 个：{expected}）")
    if extra:
        fail(f"打包清单有多余文件：{extra}（只有 {list(PACKAGE_EXCLUDED)} 可豁免，"
             f"且打包前须删除 README.md）")
    # images/ 这类目录不属于 4 文件清单
    for d in sorted(os.listdir(PKG)):
        if os.path.isdir(os.path.join(PKG, d)):
            fail(f"打包清单里有目录 {d}/（4 文件包只收文件；"
                 f"图标须平铺到包根 <appid>.svg）")


# ── 2. 行尾必须 LF（官方 §9.3 Compliance Checklist）─────────────────────────
def check_lf(paths: list[str]) -> None:
    for p in paths:
        full = os.path.join(PKG, p)
        if not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            data = f.read()
        if b"\r\n" in data:
            fail(f"{p}: 含 CRLF 行尾，官方要求全部 LF")


# ── 3. config.ini：字段集 + 关键值 ──────────────────────────────────────────
def check_config_ini(appid: str) -> dict:
    path = os.path.join(PKG, "config.ini")
    if not os.path.isfile(path):
        fail("config.ini 不存在")
        return {}
    raw = read(path)
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"config.ini 不是合法 JSON：{e}")
        return {}

    keys = set(cfg.keys())
    missing = OFFICIAL_CONFIG_KEYS - keys
    extra = keys - OFFICIAL_CONFIG_KEYS
    if missing:
        fail(f"config.ini 缺官方字段：{sorted(missing)}"
             f"（官方模板 TOS 7-template-docker/config.ini）")
    if extra:
        fail(f"config.ini 有非官方字段：{sorted(extra)}"
             f"（平台会忽略未知字段 ⇒ 白写；且与官方模板对不齐）")

    if cfg.get("id") != appid:
        fail(f"config.ini 的 id 应为 {appid!r}，实际 {cfg.get('id')!r}")
    if cfg.get("application_type") != "docker":
        fail(f"config.ini 的 application_type 必须为 'docker'，实际 {cfg.get('application_type')!r}")
    if "DockerEngine" not in (cfg.get("depend") or []):
        fail("config.ini 的 depend 必须含 'DockerEngine'（TOS 7 不预装 Docker）")
    if "docker" not in (cfg.get("relation") or []):
        fail("config.ini 的 relation 必须含 'docker'")
    if cfg.get("compose_project") != cfg.get("id"):
        fail(f"config.ini 的 compose_project 应等于 id（官方模板：{appid!r}）")
    if not str(cfg.get("user") or "").strip():
        fail("config.ini 的 user 为空（官方：平台侧系统用户名，必填）")
    if cfg.get("icon") != f"/images/icons/{appid}.svg":
        fail(f"config.ini 的 icon 应为 /images/icons/{appid}.svg，"
             f"实际 {cfg.get('icon')!r}")
    if not isinstance(cfg.get("category"), list):
        fail(f"config.ini 的 category 应为数组（官方模板是数组），"
             f"实际 {type(cfg.get('category')).__name__}")
    if cfg.get("platform") not in ("x86_64", "aarch64"):
        fail(f"config.ini 的 platform 必须是 x86_64 或 aarch64，"
             f"实际 {cfg.get('platform')!r}")
    return cfg


# ── 4. lang：14 种语言齐全 ──────────────────────────────────────────────────
def check_lang(appid: str) -> None:
    path = os.path.join(PKG, f"{appid}.lang")
    if not os.path.isfile(path):
        fail(f"{appid}.lang 不存在")
        return
    text = read(path)
    found = re.findall(r"^\[([a-z]{2}-[a-z]{2})\]\s*$", text, re.M)
    missing = [l for l in REQUIRED_LANGUAGES if l not in found]
    if missing:
        fail(f"{appid}.lang 缺语言：{missing}（官方要求 14 种齐全，"
             f"未翻译的按官方模板口径填英文）")
    extra = [l for l in found if l not in REQUIRED_LANGUAGES]
    if extra:
        fail(f"{appid}.lang 有官方清单外的语言：{extra}")
    for lang in found:
        block = re.search(rf"^\[{re.escape(lang)}\]\s*$(.*?)(?=^\[|\Z)",
                          text, re.M | re.S)
        body = block.group(1) if block else ""
        for key in ("name", "auth", "descript", "release_note", "important"):
            if not re.search(rf"^\s*{key}\s*=\s*\".+\"\s*$", body, re.M):
                fail(f"{appid}.lang [{lang}] 缺字段 {key}")


# ── 5. svg：存在且是 svg ────────────────────────────────────────────────────
def check_svg(appid: str) -> None:
    path = os.path.join(PKG, f"{appid}.svg")
    if not os.path.isfile(path):
        fail(f"{appid}.svg 不存在")
        return
    text = read(path)
    if "<svg" not in text:
        fail(f"{appid}.svg 不是 SVG")


# ── 6. compose：逐条官方规则 ───────────────────────────────────────────────
def parse_services(lines: list[str]) -> dict[str, list[str]]:
    """把 services: 下的每个服务切成 (缩进, 行) 列表。

    刻意用行解析而非 YAML 库：TOS 平台自己就是逐行解析 compose 的
    （§9.3-3），判定口径与平台一致 ⇒ 平台会踩的坑，这里也会踩。
    """
    services: dict[str, list[str]] = {}
    in_services = False
    svc_indent = None
    cur = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if in_services:
            if svc_indent is None:
                # services: 下的第一个非空行 = 第一个服务名
                cur = stripped.split(":")[0].strip()
                services[cur] = []
                svc_indent = indent
                continue
            if indent < svc_indent:
                in_services = False  # 离开 services 块（如顶层 x-app-meta:）
                continue
            if indent == svc_indent:
                cur = stripped.split(":")[0].strip()
                services[cur] = []
                continue
            if cur is not None:
                services[cur].append(line)
            continue
        if re.match(r"^services\s*:\s*$", stripped):
            in_services = True
            svc_indent = None
    return services


def seq_entries(lines: list[str], key: str) -> list[str]:
    """取某个 key: 下面的序列项（- xxx），并带上「该项之前是否有注释行」标记。"""
    out: list[tuple[str, bool, int]] = []
    inside = False
    base_indent = None
    pending_comment = False
    for ln_no, line in enumerate(lines):
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if not inside:
            if re.match(rf"^{re.escape(key)}\s*:\s*$", stripped):
                inside = True
                base_indent = indent
            continue
        if indent <= base_indent:
            break  # 序列结束
        if stripped.startswith("#"):
            pending_comment = True
            continue
        if stripped.startswith("-"):
            out.append((stripped[1:].strip(), pending_comment, ln_no + 1))
            pending_comment = False
    return out


def check_compose(appid: str, cfg: dict) -> None:
    path = os.path.join(PKG, "docker-compose.yml")
    if not os.path.isfile(path):
        fail("docker-compose.yml 不存在")
        return
    text = read(path)
    lines = text.splitlines()

    # §9.3-1 版本
    m = re.search(r"^version\s*:\s*[\"']?([0-9.]+)", text, re.M)
    if not m:
        fail("compose 缺 version: 字段（官方要求 Compose Spec 3.8+）")
    else:
        ver = tuple(int(x) for x in m.group(1).split("."))
        if ver < (3, 8):
            fail(f"compose version {m.group(1)} 低于官方要求的 3.8")

    # 禁 :latest
    for i, line in enumerate(lines, 1):
        if re.search(r"image\s*:.*:latest\b", line):
            fail(f"compose 第 {i} 行：镜像用了 :latest（官方明令禁止，必须钉版本号）")

    # 禁 privileged / host 网络
    for i, line in enumerate(lines, 1):
        if re.match(r"^\s*privileged\s*:\s*true\s*$", line):
            fail(f"compose 第 {i} 行：privileged: true 严格禁止（§9.3-6）")
        if re.match(r"^\s*network_mode\s*:\s*[\"']?host", line):
            fail(f"compose 第 {i} 行：network_mode: host 严格禁止（§9.3-8）")

    services = parse_services(lines)
    if not services:
        fail("compose 里解析不到 services 段")

    # §9.3-3 volumes / ports 序列内不得有注释行
    for key in ("volumes", "ports"):
        for item, has_comment, ln in seq_entries(lines, key):
            if has_comment:
                fail(f"compose 第 {ln} 行：{key} 序列内出现注释行"
                     f"（§9.3-3：平台逐行解析该块，遇 '#' 提前中断 ⇒ 挂载目录 chown 被跳过）")

    # §9.3-4 数据挂载：禁 /Volume*/ 通配
    for name, body in services.items():
        for key in ("volumes",):
            for item, _c, ln in seq_entries(body, key):
                if "/Volume*/" in item:
                    fail(f"compose 第 {ln} 行：数据挂载写了 /Volume*/ 通配"
                         f"（§9.3-4：平台不展开 '*'，会真的建出 /Volume* 目录）")
                if re.match(r"^/Volume\d+/", item.split(":")[0]):
                    fail(f"compose 第 {ln} 行：宿主侧写了具体 /VolumeN/ 路径"
                         f"（官方推荐相对路径 ./data，平台会落到应用数据根）")

    # §9.3-5 host 端口禁用清单
    for name, body in services.items():
        for item, _c, ln in seq_entries(body, "ports"):
            m2 = re.match(r"^[\"']?(\d+)", item)
            if not m2:
                continue
            host_port = int(m2.group(1))
            if host_port in DISABLED_HOST_PORTS:
                fail(f"compose 第 {ln} 行：host 端口 {host_port} 在官方禁用清单内"
                     f"（{sorted(DISABLED_HOST_PORTS)}）")
            elif not (RECOMMENDED_PORT_RANGE[0] <= host_port <= RECOMMENDED_PORT_RANGE[1]):
                warn(f"compose 第 {ln} 行：host 端口 {host_port} 不在官方推荐区间 "
                     f"{RECOMMENDED_PORT_RANGE[0]}-{RECOMMENDED_PORT_RANGE[1]}")

    # §9.3-6 每个服务都要有非 root user
    for name, body in services.items():
        has_user = any(re.match(r"^\s*user\s*:", l) for l in body)
        if not has_user:
            fail(f"服务 {name} 缺 user: 字段（§9.3-6：非 root UID:GID 必填）")

    # §9.3-10 每个服务都要有 healthcheck
    for name, body in services.items():
        if not any(re.match(r"^\s*healthcheck\s*:", l) for l in body):
            fail(f"服务 {name} 缺 healthcheck（§9.3-10：每个服务都必须有）")

    # §9.3-2 x-app-meta：必须在文件末尾，且含 web.port / web.protocol
    top_lines = [l for l in lines if re.match(r"^[A-Za-z_][\w-]*\s*:", l)]
    top_keys = [l.strip() for l in top_lines]
    if not top_keys or top_keys[-1] != "x-app-meta:":
        fail("compose 的最后一个顶层键必须是 x-app-meta:（§9.3-2：Web UI 应用必填且须附在末尾）")
    if "x-app-meta:" not in top_keys:
        fail("compose 缺 x-app-meta 段（§9.3-2）")
    else:
        start = next(i for i, l in enumerate(lines)
                     if re.match(r"^x-app-meta\s*:", l))
        tail = "\n".join(lines[start:])
        if "port:" not in tail or "protocol:" not in tail:
            fail("x-app-meta 段缺 web.port / web.protocol（§9.3-2）")

    # 具名卷必须在顶层 volumes: 声明
    declared = set(re.findall(r"^\s{2}([\w.-]+)\s*:", text, re.M))
    for name, body in services.items():
        for item, _c, ln in seq_entries(body, "volumes"):
            src = item.split(":")[0].strip()
            if src and not src.startswith((".", "/")) and src not in declared:
                fail(f"compose 第 {ln} 行：具名卷 {src!r} 未在顶层 volumes: 声明"
                     f"（否则 Compose 直接拒整个项目，应用中心装不上）")

    # ── 红灯：镜像源必须是 Docker Hub（送审硬前置，平台必拒）────────────
    # 2026-10-31：这一条从**黄灯**升级为**红灯**。
    #   理由：① 生态镜像线已新增 Docker Hub 发布通道（pigeonbox/server 仓
    #   release 流水线一次构建双推 ghcr + Docker Hub）⇒ 「镜像源不是本仓能
    #   单方面决定的」这个前提**已不成立**；② TOS 商店拒收非 Docker Hub
    #   镜像 ⇒ 这是**平台必拒**的规则违规，与其他红灯同级。
    #   ⇒ 留着黄灯 = 门禁永远不响 ⇒ 等于没有门禁。
    images = re.findall(r"^\s*image\s*:\s*(\S+)", text, re.M)
    for img in images:
        if not (img.startswith("docker.io/") or "/" in img and
                img.split("/", 1)[0] in ("docker.io", "index.docker.io")):
            fail(f"compose 第 {find_line(text, img)} 行：镜像 {img} 不是 Docker Hub 引用"
                 f"（TOS 应用商店拒收 ghcr.io / quay.io / 私有仓库 ⇒ 送审必被打回）"
                 f"；生态镜像线已双推 Docker Hub ⇒ 请把 image 换成 "
                 f"docker.io/<namespace>/<name>:<version>")

    # ── 黄灯：镜像 tag 与本仓 VERSION 对齐（版本漂移）────────────────────────
    ver_file = os.path.join(REPO, "VERSION")
    if os.path.isfile(ver_file):
        repo_ver = read(ver_file).strip().lstrip("v")
        for img in images:
            m3 = re.search(r":([^:/]+)$", img)
            if m3 and m3.group(1) not in ("latest",) and m3.group(1) != repo_ver:
                warn(f"镜像 {img} 钉的版本与本仓 VERSION（{repo_ver}）不一致"
                     f"（tos7/docker-compose.yml 已在列车 bump 的物化清单里 ⇒ "
                     f"正常应自动同步；此黄灯说明物化被绕过或版本被手工改过）")


def main() -> int:
    appid = "pigeonbox"
    check_package_files(appid)
    check_lf([f.format(appid=appid) for f in PACKAGE_FILES])
    check_lf(list(PACKAGE_EXCLUDED))
    cfg = check_config_ini(appid)
    check_lang(appid)
    check_svg(appid)
    check_compose(appid, cfg)

    print("── TOS 7 应用包校验 ──")
    for m in yellow:
        print(f"  ⚠ 送审前置未就绪：{m}")
    for m in red:
        print(f"  ✗ 规则违规：{m}")
    if red:
        print(f"✗ {len(red)} 条规则违规（送审必被打回）")
        return 1
    print(f"✓ TOS 7 应用包规则全绿（黄灯 {len(yellow)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
