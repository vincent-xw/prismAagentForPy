#!/bin/sh
# POSIX 启动入口；兼容直接执行以及通过 sh、bash 调用。
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
exec bash "$SCRIPT_DIR/dev.bash" "$@"
