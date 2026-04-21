#!/usr/bin/env bash
# PoolAIssistant production uptime probe.
#
# Asserts BOTH status code AND a marker substring for each endpoint. This
# catches the silent-500 mode: on our Hostinger host a PHP fatal returns
# Content-Length: 0 with status 500, and historically no one noticed that
# the admin login was doing exactly this for weeks. Checking the body
# forces that failure mode into a red workflow run.

set -uo pipefail

declare -i failures=0
declare -a failed_checks=()

probe() {
    local name="$1"
    local method="$2"
    local url="$3"
    local expected_code="$4"
    local body_marker="$5"
    shift 5
    local curl_extra=("$@")

    # Retry on status "000" (curl network-level failure: connection refused,
    # DNS, TLS, timeout). Runner<->Hostinger has transient blips a few times a
    # day that otherwise page on every incident. Real site failures produce a
    # real HTTP code, not 000, so they bypass the retry.
    local status body attempt=0
    while (( attempt < 3 )); do
        body=$(curl -sS --max-time 20 -o /tmp/body.$$ -w '%{http_code}' \
            -X "$method" "${curl_extra[@]}" "$url" 2>/tmp/err.$$ || true)
        status="$body"
        [[ "$status" != "000" ]] && break
        attempt=$((attempt + 1))
        sleep 5
    done

    if [[ "$status" != "$expected_code" ]]; then
        echo "FAIL  $name"
        echo "      expected status $expected_code, got $status"
        echo "      url: $method $url"
        [[ -s /tmp/err.$$ ]] && echo "      curl: $(cat /tmp/err.$$)"
        failures+=1
        failed_checks+=("$name (status $status, wanted $expected_code)")
        return
    fi
    if [[ -n "$body_marker" ]] && ! grep -qF "$body_marker" /tmp/body.$$; then
        echo "FAIL  $name"
        echo "      status $status ok, but missing marker: $body_marker"
        echo "      first 200 bytes:"
        head -c 200 /tmp/body.$$ | sed 's/^/      /'
        echo ""
        failures+=1
        failed_checks+=("$name (marker missing)")
        return
    fi
    echo "ok    $name"
}

rm -f /tmp/body.$$ /tmp/err.$$

probe \
    "admin login page"                          \
    GET                                         \
    "https://poolaissistant.modprojects.co.uk/admin/login.php" \
    200 "login"

probe \
    "admin login POST returns invalid-creds"    \
    POST                                        \
    "https://poolaissistant.modprojects.co.uk/admin/login.php" \
    200 "Invalid username or password"          \
    -d "username=probe&password=probe"

probe \
    "staff PWA login page"                      \
    GET                                         \
    "https://poolaissistant.modprojects.co.uk/staff/login.php" \
    200 "Staff"

probe \
    "staff PWA login POST returns invalid-creds" \
    POST                                        \
    "https://poolaissistant.modprojects.co.uk/staff/login.php" \
    200 "Invalid username or password"          \
    -d "username=probe&password=probe"

probe \
    "staff PWA manifest"                        \
    GET                                         \
    "https://poolaissistant.modprojects.co.uk/staff/manifest.json" \
    200 "PoolAI Staff"

probe \
    "customer portal login page"                \
    GET                                         \
    "https://poolai.modprojects.co.uk/login.php" \
    200 "PoolAIssistant"

probe \
    "drift verify endpoint needs auth (401)"    \
    POST                                        \
    "https://poolaissistant.modprojects.co.uk/api/admin/_verify.php" \
    401 ""                                      \
    -H "Accept: application/json"               \
    -H "Content-Type: application/json"         \
    -d '{"paths":[]}'

rm -f /tmp/body.$$ /tmp/err.$$

if (( failures > 0 )); then
    echo ""
    echo "==== $failures probe(s) failed: ===="
    printf '  - %s\n' "${failed_checks[@]}"
    exit 1
fi
echo ""
echo "All probes passed."
