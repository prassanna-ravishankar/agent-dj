#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${AGENT_DJ_MRT2_SOURCE:-"$project_root/.cache/magenta-realtime"}
build_dir="$source_dir/build-agent-dj"
extension_dir=${AGENT_DJ_MRT2_EXTENSION:-"$HOME/Library/Application Support/SuperCollider/Extensions/MRT2"}
commit=694a545e4ba0b88bf1150137b129582166d3e07f

if [ ! -d "$source_dir/.git" ]; then
    mkdir -p "$(dirname -- "$source_dir")"
    git clone https://github.com/magenta/magenta-realtime.git "$source_dir"
fi

if [ "$(git -C "$source_dir" remote get-url origin)" != "https://github.com/magenta/magenta-realtime.git" ]; then
    printf '%s\n' "Refusing unexpected source checkout: $source_dir" >&2
    exit 1
fi
if ! git -C "$source_dir" diff --quiet || ! git -C "$source_dir" diff --cached --quiet; then
    printf '%s\n' "Refusing to overwrite local MRT2 source changes: $source_dir" >&2
    exit 1
fi
git -C "$source_dir" fetch --depth 1 origin "$commit"
git -C "$source_dir" checkout --detach "$commit"
if git -C "$source_dir" apply --reverse --check "$project_root/patches/mrt2-weight-morph.patch" 2>/dev/null; then
    : # Already patched.
else
    git -C "$source_dir" apply --check "$project_root/patches/mrt2-weight-morph.patch"
    git -C "$source_dir" apply "$project_root/patches/mrt2-weight-morph.patch"
fi

if ! DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun --find metal >/dev/null 2>&1; then
    DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
        xcodebuild -downloadComponent MetalToolchain
fi

uvx --from cmake==3.31.6 cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
    uvx --from cmake==3.31.6 cmake --build "$build_dir" --target mrt2_sc --parallel 8

mkdir -p "$extension_dir"
install -m 755 "$build_dir/examples/sc/MRT2.scx" "$extension_dir/MRT2.scx"
install -m 644 "$source_dir/examples/sc/MRT2.sc" "$extension_dir/MRT2.sc"
install -m 644 "$source_dir/examples/sc/example.scd" "$extension_dir/example.scd"
install -m 644 "$build_dir/examples/sc/mlx.metallib" "$extension_dir/mlx.metallib"

printf '%s\n' "Installed Agent DJ's pinned MRT2 SuperCollider extension at $extension_dir"
