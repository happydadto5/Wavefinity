#!/usr/bin/env bash
# Build using Emscripten 4.0.10, CMake and Ninja. Network needed only here.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git clone https://github.com/elalish/manifold.git "$tmp/manifold"
git -C "$tmp/manifold" checkout 541c33bd2ab9b1a72816bdecff90566c0a3ee56c
cp "$here/bridge64.cpp" "$tmp/manifold/bridge64.cpp"
cat >> "$tmp/manifold/CMakeLists.txt" <<'CMAKE'
add_executable(bridge64 bridge64.cpp)
target_link_libraries(bridge64 PRIVATE manifold)
target_link_options(bridge64 PRIVATE --bind -sMODULARIZE=1 -sEXPORT_ES6=1 -sALLOW_MEMORY_GROWTH=1 -sDISABLE_EXCEPTION_CATCHING=0)
target_compile_options(bridge64 PRIVATE -fexceptions)
CMAKE
emcmake cmake -S "$tmp/manifold" -B "$tmp/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DMANIFOLD_TEST=OFF -DMANIFOLD_JSBIND=OFF \
  -DMANIFOLD_CROSS_SECTION=OFF -DMANIFOLD_PAR=OFF
cmake --build "$tmp/build" --target bridge64
cp "$tmp/build/bridge64.js" "$here/bridge64.mjs"
cp "$tmp/build/bridge64.wasm" "$here/bridge64.wasm"
