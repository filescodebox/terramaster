#!/bin/sh
# 组装 TOS 7 官方 Docker 应用包（4 文件 tar.gz）。
#
# 官方模板的打包步骤（README 第 8 步）：
#   tar -czf <appid>.tar.gz config.ini <appid>.lang <appid>.svg docker-compose.yml
#
# 本脚本在此之上加四道闸：
#   1. 先跑合规校验（scripts/check_tos7_package.py）——有红灯就别打包；
#   2. 打包清单**恰好 4 个文件**（官方：.tar.gz 里不得有多余文件，README.md 也不打进去）；
#   3. **按目标平台改写包内 config.ini 的 platform**（TOS 要求一平台一提交）；
#   4. 打完再断言包内条目数 == 4（防「打包脚本自己漂了」）。
#
# 用法：./scripts/build-tos7-package.sh [appid] [platform]
#   appid    默认 pigeonbox（须与 tos7/config.ini 的 id 一致）
#   platform 默认 x86_64（TOS 要求一平台一提交：x86_64 / aarch64 各打一次）
#
# ⚠️ **platform 必须真的写进包里**（2026-10-31 修的真缺陷）：
#   官方要求 config.ini 的 `platform` 一次只能填一个，而 TOS 要求**一平台一提交**
#   ⇒ 打 aarch64 包时必须把包内 config.ini 的 platform 改成 aarch64。
#   此前本脚本的 platform 参数**只进了文件名、没进包内容** ⇒ 打出来的
#   `pigeonbox-aarch64.tar.gz` 里 config.ini 仍写 platform=x86_64
#   ⇒ **送审必被平台打回**（架构不符）。
#   ⇒ 现在按「暂存目录 + 改写暂存副本」实现，**不改仓库里的 config.ini**
#   （仓库那份是模板：platform 保持 x86_64 默认、version 随版本线抬）。
set -eu

APPID="${1:-pigeonbox}"
PLATFORM="${2:-x86_64}"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PKG_DIR="$ROOT/tos7"
OUT_DIR="$ROOT/dist"
OUT="$OUT_DIR/${APPID}-${PLATFORM}.tar.gz"

cd "$ROOT"

# 平台取值必须是官方那两个（config.ini 的 platform 字段只接受这两个）
case "$PLATFORM" in
  x86_64|aarch64) ;;
  *) echo "✗ platform 只能是 x86_64 或 aarch64，实际 $PLATFORM" >&2; exit 1 ;;
esac

# ① 合规校验：有红灯（违反 TOS 硬规则）就不打包
python3 scripts/check_tos7_package.py

# ② 打包清单必须恰好 4 个文件
for f in config.ini "${APPID}.lang" "${APPID}.svg" docker-compose.yml; do
  if [ ! -f "$PKG_DIR/$f" ]; then
    echo "✗ 缺文件：tos7/$f" >&2
    exit 1
  fi
done

# ③ 暂存 4 个文件，并把 platform / version 写进**暂存副本**的 config.ini
#    （config.ini 虽是 .ini 后缀，内容其实是 JSON ⇒ 用 python 改写，零依赖）
STAGE="$(mktemp -d)"
OK=0
trap 'rc=$?; rm -rf "$STAGE"; if [ "$rc" -ne 0 ]; then exit $rc; fi; if [ "$OK" != 1 ]; then exit 1; fi; exit 0' EXIT
cp "$PKG_DIR/config.ini" "$STAGE/config.ini"
cp "$PKG_DIR/${APPID}.lang" "$STAGE/"
cp "$PKG_DIR/${APPID}.svg" "$STAGE/"
cp "$PKG_DIR/docker-compose.yml" "$STAGE/"
PRODUCT_VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
python3 - "$STAGE/config.ini" "$PLATFORM" "$PRODUCT_VER" <<'PYEOF'
import json
import sys

path, platform, version = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
cfg["platform"] = platform
cfg["version"] = version
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
    f.write("\n")
PYEOF
# 改写后自检：暂存副本里的 platform 必须是目标平台（防「改写没生效」）
got=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["platform"])' "$STAGE/config.ini")
if [ "$got" != "$PLATFORM" ]; then
  echo "✗ 暂存 config.ini 的 platform 改写未生效：期望 $PLATFORM，实际 $got" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
rm -f "$OUT"
# tar -C：让包内路径是平铺的 4 个文件（不带 tos7/ 前缀）
#
# ⚠️ **COPYFILE_DISABLE=1 不可省**（2026-10-31 实测的真缺陷）：
#   macOS 的 bsdtar 遵循 AppleDouble 约定 ⇒ 建包时会**额外塞进** `._<文件名>`
#   条目（资源叉/扩展属性的伴生文件）⇒ 包内从 4 个文件变成 8 个条目
#   ⇒ **TOS 只收恰好 4 个文件 ⇒ 送审必被打回**。
#   ⚠️ 更阴的是：**bsdtar 自己的 `tar -tzf` 会把这些条目藏起来**（只显示 4 个）
#   ⇒ 用 `tar -tzf | grep -c .` 断言包内条目数**恰好瞎在这一点上** ⇒ 脚本自检通过、
#   包却是坏的。
#   ⇒ 故：① 建包时 COPYFILE_DISABLE=1（Linux 上无害）；② 断言改用**标准读取器**
#     （python tarfile）——与平台用标准库解包的视角一致。
COPYFILE_DISABLE=1 tar -czf "$OUT" -C "$STAGE" \
  config.ini "${APPID}.lang" "${APPID}.svg" docker-compose.yml

# ④ 断言包内条目数 == 4 且无 AppleDouble 垃圾（用标准读取器看，不是 bsdtar）
#    断言与计数合并成一步：stdout 只吐条目数，错误信息走 stderr，
#    退出码非 0 ⇒ `set -e` 下脚本立刻中止（**不能只报错还 exit 0**——
#    2026-10-31 实测：末尾 echo 引用未定义变量时，macOS 的 /bin/sh 打印
#    "unbound variable" 却**仍以 0 退出** ⇒ 本地 `&&` 链假绿、CI 才红）。
count=$(python3 - "$OUT" <<'PYEOF'
import sys
import tarfile

path = sys.argv[1]
with tarfile.open(path, "r:gz") as t:
    names = t.getnames()
junk = [n for n in names if n.startswith("._") or "/._" in n]
if len(names) != 4:
    print(f"✗ 包内应为 4 个文件，实际 {len(names)} 个：{names}", file=sys.stderr)
    sys.exit(1)
if junk:
    print(f"✗ 包内混入 macOS AppleDouble 垃圾条目：{junk}", file=sys.stderr)
    sys.exit(1)
print(len(names))
PYEOF
)

# ⚠️ 变量紧跟中文标点时必须写 ${VAR}：非 UTF-8 locale 下 bash 会把多字节字符的
#    首字节算进变量名（${OUT}（ ⇒ 报 "OUT?: unbound variable"）。
echo "✓ 已产出 ${OUT}（${count} 个文件，platform=${PLATFORM}，version=${PRODUCT_VER}）"
tar -tzf "$OUT"
OK=1
