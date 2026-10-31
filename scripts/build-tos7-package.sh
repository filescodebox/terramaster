#!/bin/sh
# 组装 TOS 7 官方 Docker 应用包（4 文件 tar.gz）。
#
# 官方模板的打包步骤（README 第 8 步）：
#   tar -czf <appid>.tar.gz config.ini <appid>.lang <appid>.svg docker-compose.yml
#
# 本脚本在此之上加三道闸：
#   1. 先跑合规校验（scripts/check_tos7_package.py）——有红灯就别打包；
#   2. 打包清单**恰好 4 个文件**（官方：.tar.gz 里不得有多余文件，README.md 也不打进去）；
#   3. 打完再断言包内条目数 == 4（防「打包脚本自己漂了」）。
#
# 用法：./scripts/build-tos7-package.sh [appid] [platform]
#   appid    默认 pigeonbox（须与 tos7/config.ini 的 id 一致）
#   platform 默认 x86_64（TOS 要求一平台一提交：x86_64 / aarch64 各打一次）
#
# ⚠️ 产物是**送审包**的前提，不是送审包本身：TOS 应用商店只收 Docker Hub 镜像，
#    而 tos7/docker-compose.yml 里的 image 目前仍是 ghcr.io ⇒ 送审前必须先换成
#    Docker Hub 引用（生态层决策待拍板，见 tos7/README.md「还没就绪的」）。

set -eu

APPID="${1:-pigeonbox}"
PLATFORM="${2:-x86_64}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PKG_DIR="$ROOT/tos7"
OUT_DIR="$ROOT/dist"
OUT="$OUT_DIR/${APPID}-${PLATFORM}.tar.gz"

cd "$ROOT"

# ① 合规校验：有红灯（违反 TOS 硬规则）就不打包
python3 scripts/check_tos7_package.py

# ② 打包清单必须恰好 4 个文件
for f in config.ini "${APPID}.lang" "${APPID}.svg" docker-compose.yml; do
  if [ ! -f "$PKG_DIR/$f" ]; then
    echo "✗ 缺文件：tos7/$f" >&2
    exit 1
  fi
done

mkdir -p "$OUT_DIR"
rm -f "$OUT"
# tar -C：让包内路径是平铺的 4 个文件（不带 tos7/ 前缀）
tar -czf "$OUT" -C "$PKG_DIR" \
  config.ini "${APPID}.lang" "${APPID}.svg" docker-compose.yml

# ③ 断言包内条目数 == 4
count=$(tar -tzf "$OUT" | grep -c . || true)
if [ "$count" != "4" ]; then
  echo "✗ 包内应为 4 个文件，实际 $count 个：" >&2
  tar -tzf "$OUT" >&2
  exit 1
fi

# ⚠️ 变量紧跟中文标点时必须写 ${VAR}：非 UTF-8 locale 下 bash 会把多字节字符的
#    首字节算进变量名（${OUT}（ ⇒ 报 "OUT?: unbound variable"）。
echo "✓ 已产出 ${OUT}（${count} 个文件，platform=${PLATFORM}）"
tar -tzf "$OUT"
