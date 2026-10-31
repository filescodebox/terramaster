#!/usr/bin/env python3
"""build-tos7-package.sh 的**行为自测**：证明「平台真的写进包里」这条判据有效。

## 为什么必须做

2026-10-31 实测的真缺陷：TOS 要求 config.ini 的 `platform` 一次只能填一个，
且**一平台一提交** ⇒ 打 aarch64 包时必须把包内 config.ini 改成 aarch64。
而脚本的 platform 参数此前**只进了文件名、没进包内容** ⇒ 打出来的
`pigeonbox-aarch64.tar.gz` 里仍写 `platform: x86_64` ⇒ **送审必被平台打回**。

⚠️ 这类缺陷**不可能靠读代码看出来**（参数确实被接收了）⇒ 必须真跑脚本、
真解包、真读包里的 config.ini。

## 纪律

- **真跑真脚本**（子进程跑 `build-tos7-package.sh`），不测副本；
- 断言落在**包内内容**上，不是「脚本有没有接受参数」。

用法：python3 scripts/build_tos7_package_test.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = HERE / "build-tos7-package.sh"
CONFIG_INI = REPO / "tos7" / "config.ini"
VERSION_FILE = REPO / "VERSION"


def build(platform: str) -> tuple[int, str, Path]:
    """真跑打包脚本，返回 (exit_code, 输出, 产物路径)。"""
    out = REPO / "dist" / f"pigeonbox-{platform}.tar.gz"
    if out.exists():
        out.unlink()
    p = subprocess.run([str(SCRIPT), "pigeonbox", platform],
                       capture_output=True, text=True, timeout=180, cwd=REPO)
    return p.returncode, (p.stdout + p.stderr), out


def package_config(tar_path: Path) -> dict:
    """从 tar.gz 里读出 config.ini 并解析（包内是平铺的 4 个文件）。"""
    with tarfile.open(tar_path, "r:gz") as tar:
        names = tar.getnames()
        if len(names) != 4:
            raise AssertionError(f"包内应为 4 个文件，实际 {len(names)}：{names}")
        f = tar.extractfile("config.ini")
        assert f is not None
        return json.loads(f.read().decode("utf-8"))


def main() -> int:
    failures = []
    repo_ver = VERSION_FILE.read_text(encoding="utf-8").strip()
    config_before = CONFIG_INI.read_text(encoding="utf-8")

    for platform in ("x86_64", "aarch64"):
        code, out, tar_path = build(platform)
        if code != 0:
            failures.append(f"{platform}: 打包失败 exit={code}\n{out}")
            print(f"  ✗ {platform}: 打包失败 exit={code}\n{out}")
            continue
        # ⚠️ **不能只看退出码**（2026-10-31 实测的盲区）：
        #    macOS 的 /bin/sh 在 `set -u` 下遇到未定义变量、或在语法错误时，
        #    **打印错误却仍以 0 退出** ⇒ 只判 exit code 的自测会把
        #    「脚本报了错」当成「脚本跑通了」⇒ 本地假绿、CI 才红。
        #    ⇒ ① 正向断言：成功必须打出成功标记（黑名单会漏词，见下）；
        #      ② 反向断言：输出里不得有错误痕迹。
        bad = [m for m in ("unbound variable", "parameter not set", "syntax error",
                           "Traceback", "✗", "Error")
               if m in out]
        if bad:
            failures.append(f"{platform}: 退出码是 0 但输出里有错误痕迹 {bad}：\n{out}")
            print(f"  ✗ {platform}: 退出码 0 但输出有错误痕迹 {bad}")
            continue
        if "✓ 已产出" not in out:
            failures.append(f"{platform}: 输出里没有成功标记「✓ 已产出」"
                            f"（脚本报错却 exit 0 ⇒ 只判退出码会假绿）：\n{out}")
            print(f"  ✗ {platform}: 输出里没有成功标记「✓ 已产出」")
            continue
        if not tar_path.exists():
            failures.append(f"{platform}: 产物不存在 {tar_path}")
            print(f"  ✗ {platform}: 产物不存在")
            continue
        try:
            cfg = package_config(tar_path)
        except AssertionError as exc:
            failures.append(f"{platform}: {exc}")
            print(f"  ✗ {platform}: {exc}")
            continue
        # 核心判据：包内 config.ini 的 platform 必须是**本次请求的平台**
        if cfg.get("platform") != platform:
            failures.append(f"{platform}: 包内 config.ini 的 platform 是 "
                            f"{cfg.get('platform')!r}，应为 {platform!r}"
                            f"（平台参数没写进包里 ⇒ 送审必被拒）")
            print(f"  ✗ {platform}: 包内 platform={cfg.get('platform')!r}"
                  f"（应为 {platform!r}）")
        elif cfg.get("version") != repo_ver:
            failures.append(f"{platform}: 包内 version={cfg.get('version')!r}，"
                            f"应为 VERSION {repo_ver!r}")
            print(f"  ✗ {platform}: 包内 version={cfg.get('version')!r}"
                  f"（应为 {repo_ver!r}）")
        else:
            print(f"  ✓ {platform}: 包内 config.ini "
                  f"platform={cfg['platform']} version={cfg['version']}，"
                  f"恰好 4 个文件")

    # 仓库里的 config.ini 必须**不被**打包脚本改动（暂存副本，不是原地改）
    if CONFIG_INI.read_text(encoding="utf-8") != config_before:
        failures.append("打包脚本改了仓库里的 tos7/config.ini"
                        "（应只改暂存副本）")
        print("  ✗ 打包脚本改了仓库里的 tos7/config.ini（应只改暂存副本）")
    else:
        print("  ✓ 仓库里的 tos7/config.ini 未被改动（只改暂存副本）")

    # 非法平台必须被拒（否则会打出「名字叫 aarch64、内容是 x86_64」的包）
    code, out, _ = build("mips64")
    if code == 0:
        failures.append("非法平台 mips64 应被拒绝，实际打包成功")
        print("  ✗ 非法平台 mips64 应被拒绝，实际打包成功")
    else:
        print("  ✓ 非法平台被拒绝（不会打出名不副实的包）")

    if failures:
        print(f"\n✗ {len(failures)} 条判据无效：")
        for f in failures:
            print("   -", f)
        return 1
    print("\n✓ 4 条判据全部有效（平台写进包/版本对齐/不改仓库/非法平台被拒）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
