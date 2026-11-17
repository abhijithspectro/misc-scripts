#!/usr/bin/env bash
# Build CanvOS installer ISOs and provider images for the requested distros.
#
# Usage: canvos-builder.sh --canvos <path> --distros <d1,d2> \
#            --<distro>-versions <v1,v2> [--piraeus]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALID_DISTROS=(kubeadm kubeadm-fips rke2 rke2-fips k3s canonical)
ORAS_ATTEMPTS=3
RETRY_DELAY=5

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'Warning: %s\n' "$*" >&2; }
die()  { printf 'Error: %s\n' "$*" >&2; exit 1; }

# Records a produced artifact (ISO upload, docker push, zot copy) in $LOG_FILE.
record() { printf '%s\n' "$*" >> "$LOG_FILE"; }

# Step tracking for the end-of-run summary.
SUMMARY_PASS=()
SUMMARY_NONFATAL=()
SUMMARY_FAIL=()
CURRENT_STEP=""

begin_step() { CURRENT_STEP="$1"; log "$1"; }

complete_step() {
    [ -n "$CURRENT_STEP" ] && SUMMARY_PASS+=("$CURRENT_STEP")
    CURRENT_STEP=""
}

nonfatal_failure() {
    SUMMARY_NONFATAL+=("$1")
    CURRENT_STEP=""
}

print_summary() {
    local rc=$?
    if [ "$rc" -ne 0 ] && [ -n "$CURRENT_STEP" ]; then
        SUMMARY_FAIL+=("$CURRENT_STEP")
    fi
    CURRENT_STEP=""

    printf '\n==> Summary (exit %d)\n' "$rc"
    printf 'Passed (%d)\n' "${#SUMMARY_PASS[@]}"
    [ ${#SUMMARY_PASS[@]} -gt 0 ] && printf '  - %s\n' "${SUMMARY_PASS[@]}"
    printf 'Non-fatal failures (%d)\n' "${#SUMMARY_NONFATAL[@]}"
    [ ${#SUMMARY_NONFATAL[@]} -gt 0 ] && printf '  - %s\n' "${SUMMARY_NONFATAL[@]}"
    printf 'Failed (%d)\n' "${#SUMMARY_FAIL[@]}"
    [ ${#SUMMARY_FAIL[@]} -gt 0 ] && printf '  - %s\n' "${SUMMARY_FAIL[@]}"
    return 0
}

# Runs a command up to $1 times, waiting $RETRY_DELAY seconds between attempts.
retry() {
    local attempts="$1" n=1
    shift
    until "$@"; do
        if [ "$n" -ge "$attempts" ]; then
            return 1
        fi
        warn "Attempt $n/$attempts failed: $* — retrying in ${RETRY_DELAY}s"
        sleep "$RETRY_DELAY"
        n=$((n + 1))
    done
}

usage() {
    cat <<EOF
Usage: $(basename "$0") --canvos <path> --distros <list> [--<distro>-versions <list>] [--piraeus]

  --canvos <path>             Path to the CanvOS checkout
  --distros <list>            Comma separated distros: ${VALID_DISTROS[*]}
  --<distro>-versions <list>  Comma separated versions, one flag per distro
                              e.g. --kubeadm-versions 1.36.6,1.37.2
  --piraeus[=true|false]      Also build a piraeus non-FIPS ISO, and build the
                              non-FIPS provider images with CUSTOM_TAG=piraeus
                              and UPDATE_KERNEL=true

Environment (read from .env next to this script, or in the current directory):
  ARCH PE_VERSION UBUNTU UBUNTU_FIPS IMAGE_REGISTRY UBUNTU_PRO_KEY
  ZST_PALETTE ZST_VERTEX ZOT_PORT ZOT_PROJECT GOVC_USERNAME
EOF
}

# Variables in .env are exported verbatim (no eval/quote processing) so tokens
# containing quotes or shell metacharacters do not break the script.
load_env() {
    local f line
    for f in "$SCRIPT_DIR/.env" "$PWD/.env"; do
        [ -f "$f" ] || continue
        log "Loading environment from $f"
        while IFS= read -r line || [ -n "$line" ]; do
            line="${line#"${line%%[![:space:]]*}"}"
            case "$line" in
                ''|\#*) continue ;;
                [A-Za-z_]*=*) export "$line" ;;
                *) warn "Ignoring malformed .env line: $line" ;;
            esac
        done < "$f"
        return 0
    done
    warn "No .env file found; relying on the current environment"
}

CANVOS=""
DISTROS=""
PIRAEUS=false
RUN_STAMP=""
LOG_FILE=""
declare -A VERSIONS=()

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --canvos)
                [ $# -ge 2 ] || die "$1 requires a value"
                CANVOS="$2"; shift 2 ;;
            --canvos=*)
                CANVOS="${1#*=}"; shift ;;
            --distros)
                [ $# -ge 2 ] || die "$1 requires a value"
                DISTROS="$2"; shift 2 ;;
            --distros=*)
                DISTROS="${1#*=}"; shift ;;
            --piraeus)
                PIRAEUS=true; shift
                if [ $# -gt 0 ] && { [ "$1" = true ] || [ "$1" = false ]; }; then
                    PIRAEUS="$1"; shift
                fi ;;
            --piraeus=*)
                case "${1#*=}" in
                    true|false) PIRAEUS="${1#*=}" ;;
                    *) die "--piraeus expects true or false" ;;
                esac
                shift ;;
            --*-versions)
                [ $# -ge 2 ] || die "$1 requires a value"
                _set_versions "${1#--}" "$2"; shift 2 ;;
            --*-versions=*)
                _set_versions "${1#--}" "${1#*=}"; shift ;;
            -h|--help)
                usage; exit 0 ;;
            *)
                die "Unknown argument: $1 (see --help)" ;;
        esac
    done
}

_set_versions() {
    local key="$1" value="$2"
    key="${key%-versions}"
    VERSIONS["$key"]="$value"
}

validate() {
    local tool
    for tool in docker govc oras git; do
        command -v "$tool" >/dev/null 2>&1 || die "$tool not found in PATH"
    done

    [ -n "$CANVOS" ] || die "--canvos is required"
    [ -n "$DISTROS" ] || die "--distros is required"
    [ -d "$CANVOS" ] || die "CanvOS path does not exist: $CANVOS"
    CANVOS="$(readlink -f "$CANVOS")"
    [ -f "$CANVOS/Earthfile" ] || die "$CANVOS does not look like a CanvOS checkout (no Earthfile)"
    [ -x "$CANVOS/earthly.sh" ] || die "$CANVOS/earthly.sh is missing or not executable"

    IFS=',' read -r -a DISTRO_LIST <<< "$DISTROS"
    local d v known found
    for d in "${DISTRO_LIST[@]}"; do
        found=false
        for known in "${VALID_DISTROS[@]}"; do
            [ "$d" = "$known" ] && found=true
        done
        $found || die "Invalid distro '$d' (valid: ${VALID_DISTROS[*]})"

        [ -n "${VERSIONS[$d]:-}" ] || die "Missing --$d-versions for distro '$d'"
        local -a _versions=()
        IFS=',' read -r -a _versions <<< "${VERSIONS[$d]}"
        for v in "${_versions[@]}"; do
            [[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Invalid version '$v' for distro '$d'"
        done
    done

    local any_fips=false
    for d in "${DISTRO_LIST[@]}"; do
        is_fips "$d" && any_fips=true
    done

    local required=(ARCH PE_VERSION UBUNTU IMAGE_REGISTRY GOVC_USERNAME ZST_PALETTE ZOT_PORT ZOT_PROJECT)
    $any_fips && required+=(UBUNTU_FIPS UBUNTU_PRO_KEY ZST_VERTEX)
    for v in "${required[@]}"; do
        [ -n "${!v:-}" ] || die "Environment variable $v is not set"
    done
}

is_fips() { [[ "$1" == *fips* ]]; }

# rke2 FIPS is expressed upstream as K8S_DISTRIBUTION=rke2 + FIPS_ENABLED=true
# (see the Earthfile provider-image branches), so the distro name is normalised
# for the k8s_version.json key and the provider image tag.
effective_distro() {
    case "$1" in
        rke2-fips) printf 'rke2' ;;
        *) printf '%s' "$1" ;;
    esac
}

cleanup_docker() {
    log "Cleaning up docker images on this host"
    docker images -q 2>/dev/null | sort -u | xargs -r docker rmi -f >/dev/null 2>&1 || true
    docker system prune -f >/dev/null 2>&1 || true
    log "Docker cleanup done"
}

restore_generated_inputs() {
    local -a files=()
    mapfile -t files < <(git -C "$CANVOS" ls-files -- k8s_version.json 'ubuntu-fips/*/pro-attach-config.yaml')
    [ ${#files[@]} -gt 0 ] || return 0
    git -C "$CANVOS" checkout -- "${files[@]}" 2>/dev/null || true
}

sync_canvos() {
    log "Syncing $CANVOS with origin/main"
    cd "$CANVOS"
    if [ -n "$(git status --porcelain --untracked-files=no -- k8s_version.json 'ubuntu-fips/*/pro-attach-config.yaml' 2>/dev/null)" ]; then
        log "Restoring generated build inputs (k8s_version.json, pro-attach-config.yaml)"
        restore_generated_inputs
    fi
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        git status --short >&2
        die "CanvOS working tree has uncommitted changes; commit or stash them first"
    fi
    git checkout main
    git pull origin main
}

build_ubuntu_kairos() {
    [ -n "${UBUNTU_FIPS:-}" ] || die "UBUNTU_FIPS is not set"
    [ -n "${UBUNTU_PRO_KEY:-}" ] || die "UBUNTU_PRO_KEY is not set"

    local fips_dir="$CANVOS/ubuntu-fips/$UBUNTU_FIPS"
    [ -d "$fips_dir" ] || die "No FIPS build directory at $fips_dir"

    local attach_config="$fips_dir/pro-attach-config.yaml"
    local escaped="${UBUNTU_PRO_KEY//\\/\\\\}"
    escaped="${escaped//&/\\&}"
    escaped="${escaped//|/\\|}"
    log "Setting Ubuntu Pro token in $attach_config"
    sed -i "s|^token:.*|token: \"${escaped}\"|" "$attach_config"

    local init_version suffix
    init_version="$(sed -n 's/^ARG KAIROS_INIT_VERSION=//p' "$CANVOS/Earthfile" | head -1)"
    suffix="$(sed -n 's/^ARG BASE_IMAGE_SUFFIX=//p' "$CANVOS/Earthfile" | head -1)"
    [ -n "$init_version" ] || die "KAIROS_INIT_VERSION not found in Earthfile"
    [ -n "$suffix" ] || die "BASE_IMAGE_SUFFIX not found in Earthfile"

    local final_image="$IMAGE_REGISTRY/kairos-ubuntu:${UBUNTU_FIPS}-core-${ARCH}-generic-${init_version}${suffix}"
    local build_image="$IMAGE_REGISTRY/kairos-ubuntu-build:${UBUNTU_FIPS}-${ARCH}"

    begin_step "ubuntu-kairos base image build and push ($final_image)"
    ( cd "$fips_dir" && bash ./build.sh "$build_image" )

    docker image inspect "$build_image" >/dev/null 2>&1 \
        || die "build.sh did not produce an image tagged $build_image"
    docker tag "$build_image" "$final_image"
    docker rmi "$build_image" >/dev/null 2>&1 || true

    log "Pushing $final_image"
    docker push "$final_image"
    record "docker-push image=$final_image"
    complete_step

    restore_generated_inputs
}

# Sets VARIANT_OS_VERSION, VARIANT_CUSTOM_TAG, VARIANT_UPDATE_KERNEL and
# VARIANT_EXTRA for the given build variant (default|piraeus|fips).
variant_args() {
    local variant="$1"
    VARIANT_OS_VERSION="$UBUNTU"
    VARIANT_CUSTOM_TAG="non-fips"
    VARIANT_UPDATE_KERNEL=false
    VARIANT_EXTRA=()
    case "$variant" in
        default)
            export UBUNTU_PRO_ATTACH=false
            VARIANT_EXTRA=(--FIPS_ENABLED=false --UBUNTU_PRO_ATTACH=false) ;;
        piraeus)
            export UBUNTU_PRO_ATTACH=false
            VARIANT_CUSTOM_TAG="piraeus"
            VARIANT_UPDATE_KERNEL=true
            VARIANT_EXTRA=(--FIPS_ENABLED=false --UBUNTU_PRO_ATTACH=false) ;;
        fips)
            [ -n "${UBUNTU_FIPS:-}" ] || die "UBUNTU_FIPS is not set"
            [ -n "${UBUNTU_PRO_KEY:-}" ] || die "UBUNTU_PRO_KEY is not set"
            # earthly.sh only forwards the token as a BuildKit secret when
            # UBUNTU_PRO_ATTACH is set in its environment; the build arg alone
            # reaches the Earthfile and leaves --secret UBUNTU_PRO_KEY unset.
            export UBUNTU_PRO_KEY
            export UBUNTU_PRO_ATTACH=true
            VARIANT_OS_VERSION="$UBUNTU_FIPS"
            VARIANT_CUSTOM_TAG="fips"
            VARIANT_EXTRA=(
                --FIPS_ENABLED=true
                --KAIROS_BASE_IMAGE_URL="$IMAGE_REGISTRY"
                --UBUNTU_PRO_ATTACH=true
            ) ;;
        *)
            die "Unknown variant '$variant'" ;;
    esac
}

common_args() {
    COMMON_ARGS=(
        "--ARCH=$ARCH"
        "--PE_VERSION=$PE_VERSION"
        "--CLUSTERCONFIG=spc.tgz"
        "--OS_DISTRIBUTION=ubuntu"
        "--IMAGE_REGISTRY=$IMAGE_REGISTRY"
    )
}

iso_name_for() {
    printf 'palette-edge-installer-ubuntu-%s-%s-%s' "$VARIANT_OS_VERSION" "$PE_VERSION" "$VARIANT_CUSTOM_TAG"
}

push_iso() {
    local iso="$1"
    local user="${GOVC_USERNAME%@*}"
    # One timestamp per run keeps every ISO from this invocation together and
    # leaves the filename identical to the local build output.
    local dest="ISO/$user/$RUN_STAMP/$(basename "$iso")"
    log "Uploading $(basename "$iso") to $dest"
    govc datastore.upload "$iso" "$dest"
    record "iso local=$iso datastore=$dest"
}

build_iso() {
    local variant="$1"
    variant_args "$variant"
    common_args

    local iso_name
    iso_name="$(iso_name_for)"

    local args=(
        "${COMMON_ARGS[@]}"
        "--OS_VERSION=$VARIANT_OS_VERSION"
        "--CUSTOM_TAG=$VARIANT_CUSTOM_TAG"
        "--UPDATE_KERNEL=$VARIANT_UPDATE_KERNEL"
        "--ISO_NAME=$iso_name"
        "${VARIANT_EXTRA[@]}"
    )

    begin_step "installer ISO ($variant) build and upload ($iso_name)"
    ( cd "$CANVOS" && ./earthly.sh +iso "${args[@]}" )

    local iso_path="$CANVOS/build/$iso_name.iso"
    if [ ! -f "$iso_path" ]; then
        warn "$iso_path not found, falling back to the newest ISO in $CANVOS/build"
        iso_path="$(find "$CANVOS/build" -maxdepth 1 -type f -name '*.iso' -printf '%T@ %p\n' 2>/dev/null \
            | sort -n | tail -1 | cut -d' ' -f2- || true)"
    fi
    [ -n "$iso_path" ] && [ -f "$iso_path" ] || die "Installer ISO for $variant not found in $CANVOS/build"

    push_iso "$iso_path"
    complete_step
}

find_provider_image() {
    local distro="$1" version="$2" tag_prefix="$IMAGE_REGISTRY/ubuntu:" image
    image="$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
        | grep -F "$tag_prefix$distro-$version-$PE_VERSION-$VARIANT_CUSTOM_TAG" \
        | grep -Ev -- '-(amd64|arm64)(-|$)' \
        | sort -u \
        | head -1 \
        || true)"
    if [ -z "$image" ]; then
        image="$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
            | grep -F "$tag_prefix$distro-$version-" \
            | grep -Ev -- '-(amd64|arm64)(-|$)' \
            | sort -u \
            | head -1 \
            || true)"
    fi
    printf '%s' "$image"
}

build_provider_images() {
    local distro version variant k8s_distro
    for distro in "${DISTRO_LIST[@]}"; do
        local -a _versions=()
        IFS=',' read -r -a _versions <<< "${VERSIONS[$distro]}"
        for version in "${_versions[@]}"; do
            k8s_distro="$(effective_distro "$distro")"
            if is_fips "$distro"; then
                variant=fips
            elif $PIRAEUS; then
                variant=piraeus
            else
                variant=default
            fi
            variant_args "$variant"
            common_args

            begin_step "provider image $k8s_distro $version ($variant) build and push"
            rm -f "$CANVOS/k8s_version.json"
            printf '{\n  "%s": [\n    "%s"\n  ]\n}\n' "$k8s_distro" "$version" > "$CANVOS/k8s_version.json"

            local args=(
                "${COMMON_ARGS[@]}"
                "--K8S_DISTRIBUTION=$k8s_distro"
                "--OS_VERSION=$VARIANT_OS_VERSION"
                "--CUSTOM_TAG=$VARIANT_CUSTOM_TAG"
                "--UPDATE_KERNEL=$VARIANT_UPDATE_KERNEL"
                "--ISO_NAME=$(iso_name_for)"
                "${VARIANT_EXTRA[@]}"
            )
            ( cd "$CANVOS" && ./earthly.sh +build-provider-images "${args[@]}" )

            local image
            image="$(find_provider_image "$k8s_distro" "$version")"
            [ -n "$image" ] || die "No provider image found for $distro $version"
            log "Provider image built: $image"

            log "Pushing $image"
            docker push "$image"
            record "docker-push image=$image"
            complete_step

            local zot="$ZST_PALETTE"
            if is_fips "$distro"; then
                zot="$ZST_VERTEX"
            fi
            local zot_image="$zot:$ZOT_PORT/$ZOT_PROJECT/$image"
            begin_step "zot copy $image -> $zot_image"
            if retry "$ORAS_ATTEMPTS" oras copy "$image" "$zot_image" --to-insecure; then
                record "zot-copy source=$image target=$zot_image"
                complete_step
            else
                warn "zot copy failed after $ORAS_ATTEMPTS attempts: $image -> $zot_image"
                record "zot-copy-failed source=$image target=$zot_image"
                nonfatal_failure "zot copy $image -> $zot_image failed after $ORAS_ATTEMPTS attempts"
            fi
        done
    done
}

main() {
    parse_args "$@"
    load_env
    validate
    RUN_STAMP="$(date +%Y%m%d-%H%M%S)"
    LOG_FILE="$SCRIPT_DIR/canvos-builder-$RUN_STAMP.log"
    : > "$LOG_FILE"
    log "Logging artifacts to $LOG_FILE"
    trap print_summary EXIT

    local d any_fips=false any_non_fips=false
    for d in "${DISTRO_LIST[@]}"; do
        if is_fips "$d"; then any_fips=true; else any_non_fips=true; fi
    done

    cleanup_docker
    sync_canvos

    if $any_fips; then
        build_ubuntu_kairos
        cleanup_docker
    fi

    $any_non_fips && build_iso default
    $any_non_fips && $PIRAEUS && build_iso piraeus
    $any_fips && build_iso fips

    build_provider_images
    restore_generated_inputs

    cleanup_docker
    log "Done"
}

main "$@"
