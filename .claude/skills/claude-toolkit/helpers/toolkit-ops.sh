#!/bin/bash
# Claude Toolkit Helper Functions
# Reusable bash functions for claude-toolkit skill

# Configuration
REMOTE_REPO="RH-StahlyEngineering/RH-Stahly_Claude_Toolkit"
REMOTE_BRANCH="master"
REMOTE_BASE=".claude"
GLOBAL_LOCAL_BASE="C:/Users/rharbach/.claude"
PROJECT_LOCAL_BASE=".claude"
LOCAL_BASE="${GLOBAL_LOCAL_BASE}"  # Default, can be overridden
SYNCABLE_FOLDERS=("agents" "commands" "skills" "plugins")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# List remote contents at a given path
# Usage: list_remote [path]
list_remote() {
    local path="${1:-}"
    local api_path="${REMOTE_BASE}"
    [[ -n "$path" ]] && api_path="${REMOTE_BASE}/${path}"

    gh api "repos/${REMOTE_REPO}/contents/${api_path}" \
        --jq '.[] | "\(.type)\t\(.name)\t\(.sha)"' 2>/dev/null

    return $?
}

# Get content of a single remote file
# Usage: get_remote_file <path>
get_remote_file() {
    local path="$1"
    gh api "repos/${REMOTE_REPO}/contents/${REMOTE_BASE}/${path}" \
        --jq '.content' 2>/dev/null | base64 -d
    return $?
}

# Get SHA of a remote file (for comparison)
# Usage: get_remote_sha <path>
get_remote_sha() {
    local path="$1"
    gh api "repos/${REMOTE_REPO}/contents/${REMOTE_BASE}/${path}" \
        --jq '.sha' 2>/dev/null
    return $?
}

# Get local file hash for comparison
# Usage: get_local_hash <path>
get_local_hash() {
    local path="$1"
    local full_path="${LOCAL_BASE}/${path}"
    if [[ -f "$full_path" ]]; then
        sha256sum "$full_path" | cut -d' ' -f1
    else
        echo ""
    fi
}

# Check if path exists remotely
# Usage: remote_exists <path>
# Returns: 0 if exists, 1 if not
remote_exists() {
    local path="$1"
    gh api "repos/${REMOTE_REPO}/contents/${REMOTE_BASE}/${path}" &>/dev/null
    return $?
}

# Check if path exists locally
# Usage: local_exists <path>
# Returns: 0 if exists, 1 if not
local_exists() {
    local path="$1"
    [[ -e "${LOCAL_BASE}/${path}" ]]
    return $?
}

# Pull a single file from remote
# Usage: pull_file <remote_path>
pull_file() {
    local path="$1"
    local local_path="${LOCAL_BASE}/${path}"
    local local_dir
    local_dir="$(dirname "$local_path")"

    # Create parent directory
    mkdir -p "$local_dir"

    # Fetch and write content
    local content
    content=$(get_remote_file "$path")
    if [[ $? -eq 0 ]]; then
        echo "$content" > "$local_path"
        echo -e "${GREEN}✓${NC} Pulled: $path"
        return 0
    else
        echo -e "${RED}✗${NC} Failed to pull: $path"
        return 1
    fi
}

# List all files in a remote folder recursively
# Usage: list_remote_recursive <path>
list_remote_recursive() {
    local path="$1"
    gh api "repos/${REMOTE_REPO}/git/trees/${REMOTE_BRANCH}?recursive=1" \
        --jq ".tree[] | select(.path | startswith(\"${REMOTE_BASE}/${path}\")) | select(.type==\"blob\") | .path" \
        2>/dev/null
}

# Pull an entire folder from remote
# Usage: pull_folder <path>
pull_folder() {
    local path="$1"
    local files
    files=$(list_remote_recursive "$path")

    if [[ -z "$files" ]]; then
        echo -e "${YELLOW}No files found in remote path: $path${NC}"
        return 1
    fi

    local total
    local count=0
    local failed=0
    total=$(echo "$files" | wc -l)

    while IFS= read -r file; do
        ((count++))
        # Remove .claude/ prefix to get relative path
        local rel_path="${file#${REMOTE_BASE}/}"
        echo -e "${BLUE}📥${NC} Pulling [$count/$total]: $rel_path"

        if ! pull_file "$rel_path"; then
            ((failed++))
        fi
    done <<< "$files"

    if [[ $failed -gt 0 ]]; then
        echo -e "${YELLOW}⚠️  $failed of $total files failed to pull${NC}"
        return 1
    else
        echo -e "${GREEN}✅ Successfully pulled $total files${NC}"
        return 0
    fi
}

# Push changes to remote using git workflow
# Usage: push_to_remote <local_path> <commit_message>
push_to_remote() {
    local path="$1"
    local message="${2:-Update $path via claude-toolkit}"
    local temp_dir
    temp_dir=$(mktemp -d)

    echo -e "${BLUE}📤${NC} Preparing to push: $path"

    # Clone repo
    cd "$temp_dir" || return 1
    if ! gh repo clone "$REMOTE_REPO" . -- --depth 1 2>/dev/null; then
        echo -e "${RED}✗${NC} Failed to clone repository"
        rm -rf "$temp_dir"
        return 1
    fi

    # Ensure target directory exists
    local target_dir
    target_dir="${REMOTE_BASE}/$(dirname "$path")"
    mkdir -p "$target_dir"

    # Copy file(s)
    cp -r "${LOCAL_BASE}/${path}" "${REMOTE_BASE}/${path}"

    # Stage, commit, and push
    git add "${REMOTE_BASE}/${path}"

    if ! git diff --cached --quiet; then
        git commit -m "$message"

        if git push origin "$REMOTE_BRANCH" 2>/dev/null; then
            echo -e "${GREEN}✅${NC} Successfully pushed: $path"
            cd / || return 1
            rm -rf "$temp_dir"
            return 0
        else
            echo -e "${RED}✗${NC} Push rejected - remote has changes"
            cd / || return 1
            rm -rf "$temp_dir"
            return 2  # Special code for push rejection
        fi
    else
        echo -e "${YELLOW}ℹ️${NC} No changes to push"
        cd / || return 1
        rm -rf "$temp_dir"
        return 0
    fi
}

# Compare local and remote file
# Usage: compare_file <path>
# Output: IDENTICAL, MODIFIED, LOCAL_ONLY, REMOTE_ONLY, NOT_FOUND
compare_file() {
    local path="$1"
    local local_exists=false
    local remote_exists=false

    [[ -e "${LOCAL_BASE}/${path}" ]] && local_exists=true
    gh api "repos/${REMOTE_REPO}/contents/${REMOTE_BASE}/${path}" &>/dev/null && remote_exists=true

    if [[ "$local_exists" == true && "$remote_exists" == true ]]; then
        # Both exist - compare content
        local remote_content
        local local_content
        remote_content=$(get_remote_file "$path")
        local_content=$(cat "${LOCAL_BASE}/${path}")

        if [[ "$remote_content" == "$local_content" ]]; then
            echo "IDENTICAL"
        else
            echo "MODIFIED"
        fi
    elif [[ "$local_exists" == true ]]; then
        echo "LOCAL_ONLY"
    elif [[ "$remote_exists" == true ]]; then
        echo "REMOTE_ONLY"
    else
        echo "NOT_FOUND"
    fi
}

# Check if path is in syncable folders
# Usage: is_syncable <path>
is_syncable() {
    local path="$1"
    for folder in "${SYNCABLE_FOLDERS[@]}"; do
        if [[ "$path" == "$folder"* ]]; then
            return 0
        fi
    done
    return 1
}

# Clean up temp directories
# Usage: cleanup_temp <dir>
cleanup_temp() {
    local dir="$1"
    if [[ -d "$dir" && "$dir" == /tmp/* ]]; then
        rm -rf "$dir"
    fi
}

# Print formatted table header
print_header() {
    echo "═══════════════════════════════════════════════════════════"
    printf "%-12s │ %s\n" "Status" "Path"
    echo "────────────┼──────────────────────────────────────────────"
}

# Print formatted table footer
print_footer() {
    echo "═══════════════════════════════════════════════════════════"
}

# Check gh CLI authentication
# Returns 0 if authenticated, 1 if not
check_auth() {
    gh auth status &>/dev/null
    return $?
}

# Attempt to authenticate with gh CLI
attempt_auth() {
    echo -e "${YELLOW}Authentication required. Starting gh auth login...${NC}"
    gh auth login
    return $?
}
