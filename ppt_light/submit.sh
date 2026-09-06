#!/bin/bash
set -e
N="$1"
cd "/c/Users/Liii/Desktop/聆心-代码文件/ppt_light"
WIN=$(cygpath -w "$(pwd)")
echo "=== validate $N ==="
/c/Users/Liii/.workbuddy/binaries/node/versions/22.22.2-2/slidep-validate "slides/${N}.slide" --project "$WIN" 2>&1 | tail -3
echo "=== upsert $N ==="
/c/Users/Liii/.workbuddy/binaries/node/versions/22.22.2-2/slidep upsert-dsl "$WIN\\聆心演示-浅色.pptx" --dsl-file "slides/${N}.slide" --validate 2>&1 | tail -2
