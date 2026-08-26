#!/bin/bash
# SuperWriter 幂等安装：三宿主技能镜像 + Codex AGENTS.md 路由块 + 依赖技能镜像
set -euo pipefail

die() {
  echo "$*" >&2
  exit 1
}

canonical_path_into() {
  local variable_name="$1"
  local input_path="$2"
  IFS= read -r -d '' "$variable_name" < <(
    python3 -B - "$input_path" <<'PY'
import os
import sys

sys.stdout.write(os.path.realpath(sys.argv[1]))
sys.stdout.write("\0")
PY
  )
}

path_is_within() {
  python3 -B - "$1" "$2" <<'PY'
import os
import sys

child, parent = sys.argv[1:]
try:
    inside = os.path.commonpath((child, parent)) == parent
except ValueError:
    inside = False
raise SystemExit(0 if inside else 1)
PY
}

RAW_HOME="${HOME:-}"
[ -n "$RAW_HOME" ] || die "Unsafe HOME: HOME must be a non-empty absolute path"
[[ "$RAW_HOME" = /* ]] || die "Unsafe HOME: HOME must be an absolute path"
canonical_path_into HOME_ROOT "$RAW_HOME"
[ "$HOME_ROOT" != / ] || die "Unsafe HOME: HOME resolves to filesystem root"
[ -d "$HOME_ROOT" ] || die "Unsafe HOME: HOME is not a directory: $RAW_HOME"

canonical_path_into SRC "$(dirname "$0")"
AGENTS_SKILLS_ROOT="${SUPERWRITER_AGENTS_SKILLS_ROOT:-$RAW_HOME/.agents/skills}"
OPENCODE_SKILLS_ROOT="${SUPERWRITER_OPENCODE_SKILLS_ROOT:-$RAW_HOME/.opencode/skills}"
if [ -z "${WPSCOMPOSER_SKILL_SOURCE:-}" ]; then
  WPSCOMPOSER_SKILL_SOURCE="$SRC/../WPSComposer/skills/WPSComposer"
  for repository_name in WPSComposer WpsComposer; do
    for repository in "$SRC/.."/*; do
      if [ -d "$repository" ] && [ "${repository##*/}" = "$repository_name" ]; then
        WPSCOMPOSER_SKILL_SOURCE="$repository/skills/WPSComposer"
        break 2
      fi
    done
  done
fi
canonical_path_into AGENTS_SKILLS_ROOT "$AGENTS_SKILLS_ROOT"
canonical_path_into OPENCODE_SKILLS_ROOT "$OPENCODE_SKILLS_ROOT"
canonical_path_into WPSCOMPOSER_SKILL_SOURCE "$WPSCOMPOSER_SKILL_SOURCE"

DEPENDENCIES=(grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt)

require_file() {
  [ -f "$1" ] || {
    echo "Missing required skill file: $1" >&2
    exit 1
  }
}

require_file "$SRC/SKILL.md"
dependency_sources=()
for skill in "${DEPENDENCIES[@]}"; do
  canonical_path_into source_skill "$AGENTS_SKILLS_ROOT/$skill"
  require_file "$source_skill/SKILL.md"
  dependency_sources+=("$source_skill")
done
canonical_path_into EXCALIDRAW_SOURCE "$OPENCODE_SKILLS_ROOT/obsidian-excalidraw"
require_file "$EXCALIDRAW_SOURCE/SKILL.md"
require_file "$WPSCOMPOSER_SKILL_SOURCE/SKILL.md"
[ -d "$WPSCOMPOSER_SKILL_SOURCE/scripts/macos_probe" ] || {
  echo "WPSComposer source is incomplete: $WPSCOMPOSER_SKILL_SOURCE" >&2
  exit 1
}

# The default agents dependency source is itself the first managed host. Take
# an immutable transaction snapshot before any target tree can be moved or
# removed, then build every host from that snapshot.
source_snapshot_root="$(mktemp -d /tmp/superwriter-source-snapshot.XXXXXX)"
cleanup_source_snapshot() {
  [ -n "${source_snapshot_root:-}" ] && rm -rf "$source_snapshot_root"
}
trap cleanup_source_snapshot EXIT
snapshot_dependency_sources=()
for dependency_index in "${!DEPENDENCIES[@]}"; do
  skill="${DEPENDENCIES[$dependency_index]}"
  source_skill="${dependency_sources[$dependency_index]}"
  snapshot_skill="$source_snapshot_root/$skill"
  mkdir -p "$snapshot_skill"
  cp -R "$source_skill/." "$snapshot_skill/"
  require_file "$snapshot_skill/SKILL.md"
  snapshot_dependency_sources+=("$snapshot_skill")
done
dependency_sources=("${snapshot_dependency_sources[@]}")

host_roots=()
for host_path in "$RAW_HOME/.agents/skills" "$RAW_HOME/.claude/skills" "$RAW_HOME/.codex/skills"; do
  canonical_path_into host_root "$host_path"
  path_is_within "$host_root" "$HOME_ROOT" || die "Unsafe host path outside HOME: $host_path"
  [ "$host_root" != "$HOME_ROOT" ] || die "Unsafe host path equals HOME: $host_path"
  host_roots+=("$host_root")
done
[ "${host_roots[0]}" != "${host_roots[1]}" ] || die "Unsafe host paths: agents and claude resolve to the same directory"
[ "${host_roots[0]}" != "${host_roots[2]}" ] || die "Unsafe host paths: agents and codex resolve to the same directory"
[ "${host_roots[1]}" != "${host_roots[2]}" ] || die "Unsafe host paths: claude and codex resolve to the same directory"

sources=("$SRC" "${dependency_sources[@]}" "$EXCALIDRAW_SOURCE" "$WPSCOMPOSER_SKILL_SOURCE")
targets=()
for host_root in "${host_roots[@]}"; do
  targets+=("$host_root/superwriter")
  for skill in "${DEPENDENCIES[@]}"; do
    targets+=("$host_root/$skill")
  done
  targets+=("$host_root/obsidian-excalidraw" "$host_root/WPSComposer")
done
if ! python3 -B - "${#sources[@]}" "${sources[@]}" "${targets[@]}" <<'PY'
import os
import sys

source_count = int(sys.argv[1])
sources = sys.argv[2:2 + source_count]
targets = sys.argv[2 + source_count:]
for source in sources:
    for target in targets:
        # Replaying an installer-owned leaf symlink is safe: unlinking it never
        # removes its referent. Directory targets still get full inode/alias checks.
        if os.path.islink(target):
            continue
        canonical_target = os.path.realpath(target)
        try:
            overlaps = os.path.commonpath((source, canonical_target)) == canonical_target
        except ValueError:
            overlaps = False
        if overlaps:
            print(
                f"Unsafe source/target overlap: source {source!r} resolves inside target {target!r}",
                file=sys.stderr,
            )
            raise SystemExit(1)
PY
then
  exit 1
fi

canonical_path_into agents_file "$RAW_HOME/.codex/AGENTS.md"
path_is_within "$agents_file" "$HOME_ROOT" || die "Unsafe AGENTS.md path outside HOME"
[ "$agents_file" != "$HOME_ROOT" ] || die "Unsafe AGENTS.md path equals HOME"
if ! python3 -B - "$agents_file" "${#sources[@]}" "${#host_roots[@]}" \
  "${sources[@]}" "${host_roots[@]}" "${targets[@]}" <<'PY'
import os
import sys

route = sys.argv[1]
source_count = int(sys.argv[2])
host_count = int(sys.argv[3])
items = sys.argv[4:]
boundaries = items[:source_count + host_count]
boundaries.extend(os.path.realpath(path) for path in items[source_count + host_count:])
for boundary in boundaries:
    try:
        overlaps = os.path.commonpath((route, boundary)) == boundary
    except ValueError:
        overlaps = False
    if overlaps:
        print(
            f"Unsafe AGENTS.md overlap: route {route!r} resolves inside source or managed target {boundary!r}",
            file=sys.stderr,
        )
        raise SystemExit(1)
PY
then
  exit 1
fi
if [ -e "$agents_file" ] || [ -L "$agents_file" ]; then
  [ -f "$agents_file" ] || die "Codex route path is not a regular file: $agents_file"
  [ -r "$agents_file" ] || die "Codex route file is not readable: $agents_file"
  if ! awk '
    $0 == "<!-- pipeline:superwriter:start -->" { starts++; start_line=NR }
    $0 == "<!-- pipeline:superwriter:end -->" { ends++; end_line=NR }
    END {
      if (starts == 0 && ends == 0) exit 0
      if (starts == 1 && ends == 1 && start_line < end_line) exit 0
      exit 1
    }
  ' "$agents_file"; then
    die "Invalid Codex route markers: expected zero markers or one ordered exact pair"
  fi
fi

# Validate every destination before creating any staging area.
for host_root in "${host_roots[@]}"; do
  if [ -e "$host_root" ] || [ -L "$host_root" ]; then
    [ -d "$host_root" ] || die "Host skills path is not a directory: $host_root"
    [ ! -L "$host_root" ] || die "Host skills path must not be a leaf symlink: $host_root"
    [ -r "$host_root" ] && [ -w "$host_root" ] || die "Host skills path is not readable and writable: $host_root"
  fi
done

stage_roots=()
stage_new_roots=()
stage_backups=()
preserved_stage_roots=()
host_had_existing=(0 0 0)
host_backup_moved=(0 0 0)
host_committed=(0 0 0)
host_parent_created=(0 0 0)

cleanup_staging() {
  local stage_root preserved_stage preserve cleanup_index cleanup_parent
  for stage_root in "${stage_roots[@]}"; do
    preserve=0
    for preserved_stage in "${preserved_stage_roots[@]-}"; do
      [ "$stage_root" = "$preserved_stage" ] && preserve=1
    done
    [ "$preserve" -eq 1 ] && continue
    [ -n "$stage_root" ] && rm -rf "$stage_root"
  done
  for ((cleanup_index=${#host_roots[@]} - 1; cleanup_index >= 0; cleanup_index--)); do
    if [ "${host_parent_created[$cleanup_index]}" -eq 1 ]; then
      cleanup_parent="$(dirname "${host_roots[$cleanup_index]}")"
      rmdir "$cleanup_parent" 2>/dev/null || true
    fi
  done
  cleanup_source_snapshot
}
trap cleanup_staging EXIT

# Create and populate a complete candidate skills tree for every host.
for index in "${!host_roots[@]}"; do
  host_root="${host_roots[$index]}"
  host_parent="$(dirname "$host_root")"
  parent_existed=0
  [ -d "$host_parent" ] && parent_existed=1
  mkdir -p "$host_parent"
  [ "$parent_existed" -eq 0 ] && host_parent_created[$index]=1
  [ -d "$host_parent" ] && [ -w "$host_parent" ] || die "Host parent is not writable: $host_parent"
  stage_root="$(mktemp -d "$host_parent/.superwriter-install.XXXXXX")"
  stage_new="$stage_root/new-skills"
  stage_backup="$stage_root/backup-skills"
  mkdir -p "$stage_new"
  stage_roots+=("$stage_root")
  stage_new_roots+=("$stage_new")
  stage_backups+=("$stage_backup")

  if [ -d "$host_root" ]; then
    host_had_existing[$index]=1
    cp -a "$host_root/." "$stage_new/"
  fi

  rm -rf "$stage_new/superwriter"
  mkdir -p "$stage_new/superwriter"
  cp "$SRC/SKILL.md" "$stage_new/superwriter/SKILL.md"
  cp -R "$SRC/references" "$stage_new/superwriter/references"

  for dependency_index in "${!DEPENDENCIES[@]}"; do
    skill="${DEPENDENCIES[$dependency_index]}"
    source_skill="${dependency_sources[$dependency_index]}"
    rm -rf "$stage_new/$skill"
    mkdir -p "$stage_new/$skill"
    cp -R "$source_skill/." "$stage_new/$skill/"
  done

  rm -rf "$stage_new/obsidian-excalidraw"
  mkdir -p "$stage_new/obsidian-excalidraw"
  cp -R "$EXCALIDRAW_SOURCE/." "$stage_new/obsidian-excalidraw/"

  rm -rf "$stage_new/WPSComposer"
  ln -s "$WPSCOMPOSER_SKILL_SOURCE" "$stage_new/WPSComposer"

  require_file "$stage_new/superwriter/SKILL.md"
  require_file "$stage_new/obsidian-excalidraw/SKILL.md"
  for skill in "${DEPENDENCIES[@]}"; do
    require_file "$stage_new/$skill/SKILL.md"
  done
  [ -L "$stage_new/WPSComposer" ] && [ -f "$stage_new/WPSComposer/SKILL.md" ] || \
    die "Staged WPSComposer link is incomplete for host: $host_root"
done

# Stage the route file alongside the Codex host transaction.
route_stage="${stage_roots[2]}/new-AGENTS.md"
route_backup="${stage_roots[2]}/backup-AGENTS.md"
: > "$route_stage"
if [ -f "$agents_file" ]; then
  awk '
    $0 == "<!-- pipeline:superwriter:start -->" { skipping=1; next }
    $0 == "<!-- pipeline:superwriter:end -->" { skipping=0; next }
    !skipping { print }
  ' "$agents_file" > "$route_stage"
fi
cat >> "$route_stage" <<'BLOCK'

<!-- pipeline:superwriter:start -->
# SuperWriter 路由

- 触发词：标书 / 投标 / 应标 / 招标文件 / 技术标 → 自动进入 SuperWriter 阶段 0（先读/建流水线状态.md）
- 预授权技能（视为已获指令可直接调用）：markitdown、grilling、grill-me、grill-with-docs、to-spec、domain-modeling、obsidian-excalidraw、ai-image-to-ppt、WPSComposer、superwriter 自身
- 阶段推进规则：阶段 0 为启动预处理；阶段 1–9 为九个业务阶段；流程门仅 0 / 2 / 3 / 5 / 6 / 7 / 8；人工确认点仅门 2 / 门 5 / 门 8；导出为交付验收
- 保密：子代理上下文只带当前客户工作区，禁止跨客户引用
<!-- pipeline:superwriter:end -->
BLOCK

route_had_existing=0
route_backup_moved=0
route_committed=0
[ -f "$agents_file" ] && route_had_existing=1

rollback_transaction() {
  local rollback_index rollback_target rollback_failed
  rollback_failed=0
  set +e
  if [ "$route_committed" -eq 1 ]; then
    if ! rm -f "$agents_file"; then
      rollback_failed=1
    fi
  fi
  if [ "$route_backup_moved" -eq 1 ]; then
    if mv "$route_backup" "$agents_file"; then
      route_backup_moved=0
    else
      preserved_stage_roots+=("${stage_roots[2]}")
      echo "Rollback incomplete: route backup retained at $route_backup" >&2
      rollback_failed=1
    fi
  fi
  for ((rollback_index=${#host_roots[@]} - 1; rollback_index >= 0; rollback_index--)); do
    rollback_target="${host_roots[$rollback_index]}"
    if [ "${host_committed[$rollback_index]}" -eq 1 ]; then
      if ! rm -rf "$rollback_target"; then
        rollback_failed=1
      fi
    fi
    if [ "${host_backup_moved[$rollback_index]}" -eq 1 ]; then
      if mv "${stage_backups[$rollback_index]}" "$rollback_target"; then
        host_backup_moved[$rollback_index]=0
      else
        preserved_stage_roots+=("${stage_roots[$rollback_index]}")
        echo "Rollback incomplete: host backup retained at ${stage_backups[$rollback_index]}" >&2
        rollback_failed=1
      fi
    fi
  done
  set -e
  [ "$rollback_failed" -eq 0 ]
}

# Commit whole host trees only after every candidate and route file is ready.
for index in "${!host_roots[@]}"; do
  host_root="${host_roots[$index]}"
  if [ "${host_had_existing[$index]}" -eq 1 ]; then
    if ! mv "$host_root" "${stage_backups[$index]}"; then
      rollback_transaction || die "Rollback incomplete after host backup failure"
      die "Failed to back up host during transaction: $host_root"
    fi
    host_backup_moved[$index]=1
  fi
  if ! mv "${stage_new_roots[$index]}" "$host_root"; then
    rollback_transaction || die "Rollback incomplete after host commit failure"
    die "Failed to commit host during transaction: $host_root"
  fi
  host_committed[$index]=1
done

if [ "$route_had_existing" -eq 1 ]; then
  if ! mv "$agents_file" "$route_backup"; then
    rollback_transaction || die "Rollback incomplete after route backup failure"
    die "Failed to back up Codex route during transaction"
  fi
  route_backup_moved=1
fi
if ! mv "$route_stage" "$agents_file"; then
  rollback_transaction || die "Rollback incomplete after route commit failure"
  die "Failed to commit Codex route during transaction"
fi
route_committed=1

echo "SuperWriter installed to 3 hosts."
