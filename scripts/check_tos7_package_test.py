#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOS 7 应用包校验器的**变异自测**：证明每条规则都真的能判红。

# 为什么要有这个自测

一个「什么都报绿」的校验器比没有校验器更危险——它会让人以为包合规。
⇒ 本自测对 tos7/ 逐条注入违规（`:latest`、`privileged: true`、
`network_mode: host`、`/Volume*/` 通配、volumes 序列内插注释、缺 user:、
缺 healthcheck、x-app-meta 不在末尾、config.ini 字段漂移、lang 少语言、
CRLF 行尾、禁用端口、具名卷未声明……），断言校验器**每次都红**且报出对应原因。

⇒ 「恒真则必红」：把某条规则的判据改坏（等价于退回旧写法），本自测必须转红。

# 用法

    python3 scripts/check_tos7_package_test.py
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PKG = os.path.join(REPO, "tos7")
CHECKER = os.path.join(HERE, "check_tos7_package.py")


def run_checker(pkg_dir: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, CHECKER, pkg_dir],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


def read(p: str) -> str:
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def write(p: str, s: str) -> None:
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(s)


# ── 变异用例：(名称, 改包内哪个文件的哪个函数, 期望在校验输出里出现的关键词) ──
def m_latest(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace(":4.5.2", ":latest", 1))


def m_privileged(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace("    user: \"1000:1000\"",
                             "    privileged: true\n    user: \"1000:1000\"", 1))


def m_host_network(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace("    user: \"1000:1000\"",
                             "    network_mode: host\n    user: \"1000:1000\"", 1))


def m_volume_wildcard(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace("./data:/app/data",
                             "/Volume*/DockerAppData/pigeonbox/data:/app/data", 1))


def m_comment_in_volumes(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace(
        "      - ./data:/app/data",
        "      # 数据卷\n      - ./data:/app/data", 1))


def m_no_user(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace("    user: \"1000:1000\"\n", "", 1))


def m_no_healthcheck(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    s = read(f)
    # 删掉**第一个**服务的整个 healthcheck 块（缩进 4 的键 + 其下缩进 6 的项）
    s2 = re.sub(r"\n    healthcheck:\n(?:      [^\n]*\n)+", "\n", s, count=1)
    assert s2 != s, "healthcheck 块没匹配上"
    write(f, s2)


def m_app_meta_not_last(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    s = read(f)
    # 把 x-app-meta 段改名 ⇒ 最后一个顶层键不再是 x-app-meta
    s2 = s.replace("x-app-meta:", "x-app-meta-moved:", 1)
    assert s2 != s
    write(f, s2)


def m_config_extra_field(pkg: str) -> None:
    f = os.path.join(pkg, "config.ini")
    write(f, read(f).replace('"id": "pigeonbox"',
                             '"id": "pigeonbox",\n  "md5": ""', 1))


def m_config_missing_field(pkg: str) -> None:
    f = os.path.join(pkg, "config.ini")
    write(f, read(f).replace('  "user": "pigeonbox",\n', "", 1))


def m_config_bad_icon(pkg: str) -> None:
    f = os.path.join(pkg, "config.ini")
    write(f, read(f).replace('"icon": "/images/icons/pigeonbox.svg"',
                             '"icon": "/images/icons/pigeonbox-docker.svg"', 1))


def m_lang_missing_language(pkg: str) -> None:
    f = os.path.join(pkg, "pigeonbox.lang")
    s = read(f)
    i = s.index("[pt-pt]")
    write(f, s[:i])


def m_lang_missing_field(pkg: str) -> None:
    f = os.path.join(pkg, "pigeonbox.lang")
    s = read(f)
    write(f, s.replace('name = "PigeonBox File Locker"\n', "", 1))


def m_crlf(pkg: str) -> None:
    f = os.path.join(pkg, "config.ini")
    write(f, read(f).replace("\n", "\r\n"))


def m_bad_port(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace('"12345:8080"', '"3306:8080"', 1))


def m_named_volume_undeclared(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace("./data:/app/data", "pbdata:/app/data", 1))


def m_old_version(pkg: str) -> None:
    f = os.path.join(pkg, "docker-compose.yml")
    write(f, read(f).replace('version: "3.8"', 'version: "3.7"', 1))


def m_missing_compose(pkg: str) -> None:
    os.remove(os.path.join(pkg, "docker-compose.yml"))


def m_extra_file(pkg: str) -> None:
    write(os.path.join(pkg, "pigeonbox-extra.txt"), "stray\n")


def m_bad_svg(pkg: str) -> None:
    f = os.path.join(pkg, "pigeonbox.svg")
    write(f, "not an svg\n")


def m_config_not_json(pkg: str) -> None:
    f = os.path.join(pkg, "config.ini")
    write(f, "{ this is not json\n")


def m_ghcr_image(pkg: str) -> None:
    """镜像源换成 ghcr.io（TOS 商店拒收 ⇒ 送审必被打回）。

    2026-10-31：这条规则从**黄灯**升级为**红灯**（生态镜像线已双推 Docker Hub）
    ⇒ 必须钉住它**能判红**且报红（否则升级只是把一条永不触发的黄灯换成红灯）。
    """
    f = os.path.join(pkg, "docker-compose.yml")
    s = read(f)
    s = s.replace("image: docker.io/pigeonbox/server:", "image: ghcr.io/pigeonbox/server:")
    write(f, s)


def m_quay_image(pkg: str) -> None:
    """镜像源换成 quay.io（另一种被拒的 registry）。"""
    f = os.path.join(pkg, "docker-compose.yml")
    s = read(f)
    s = s.replace("image: docker.io/pigeonbox/frontend:", "image: quay.io/pigeonbox/frontend:")
    write(f, s)


CASES = [
    ("镜像用 :latest", m_latest, "latest"),
    ("privileged: true", m_privileged, "privileged"),
    ("network_mode: host", m_host_network, "network_mode"),
    ("数据挂载写 /Volume*/ 通配", m_volume_wildcard, "通配"),
    ("volumes 序列内插注释", m_comment_in_volumes, "注释行"),
    ("服务缺 user:", m_no_user, "user:"),
    ("服务缺 healthcheck", m_no_healthcheck, "healthcheck"),
    ("x-app-meta 不在末尾", m_app_meta_not_last, "x-app-meta"),
    ("config.ini 多出非官方字段", m_config_extra_field, "非官方字段"),
    ("config.ini 缺官方字段", m_config_missing_field, "缺官方字段"),
    ("config.ini 的 icon 路径不符", m_config_bad_icon, "icon"),
    ("config.ini 不是合法 JSON", m_config_not_json, "JSON"),
    ("lang 少一种语言", m_lang_missing_language, "缺语言"),
    ("lang 缺字段", m_lang_missing_field, "缺字段"),
    ("CRLF 行尾", m_crlf, "CRLF"),
    ("host 端口在禁用清单内", m_bad_port, "禁用清单"),
    ("具名卷未在顶层声明", m_named_volume_undeclared, "顶层 volumes"),
    ("compose 版本低于 3.8", m_old_version, "version"),
    ("缺 docker-compose.yml", m_missing_compose, "docker-compose.yml 不存在"),
    ("包里多出文件", m_extra_file, "多余文件"),
    ("svg 不是 svg", m_bad_svg, "不是 SVG"),
    ("镜像源是 ghcr.io（TOS 拒收）", m_ghcr_image, "Docker Hub"),
    ("镜像源是 quay.io（TOS 拒收）", m_quay_image, "Docker Hub"),
]


def main() -> int:
    # 基线：不改任何东西时必须绿
    code, out = run_checker(PKG)
    if code != 0:
        print("✗ 基线就红（当前 tos7/ 不合规），先修包：")
        print(out)
        return 1
    print("✓ 基线：当前 tos7/ 全绿")

    failures = []
    for name, mutate, keyword in CASES:
        tmp = tempfile.mkdtemp(prefix="tos7-mut-")
        pkg = os.path.join(tmp, "tos7")
        shutil.copytree(PKG, pkg)
        try:
            mutate(pkg)
            code, out = run_checker(pkg)
            if code == 0:
                failures.append(f"{name}: 变异后仍报绿（该规则判据无效）")
                print(f"  ✗ {name}: 变异后仍报绿")
            elif keyword not in out:
                failures.append(f"{name}: 报红了但没提到 {keyword!r}")
                print(f"  ✗ {name}: 报红了但没提到 {keyword!r}")
            else:
                print(f"  ✓ {name}: 判红且提到 {keyword!r}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"\n✗ {len(failures)} 条规则判据无效：")
        for f in failures:
            print("   -", f)
        return 1
    print(f"\n✓ {len(CASES)} 条规则的判据全部有效（每条都能判红）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
