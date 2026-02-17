#!/bin/bash
# End-to-end tests for ff-services-pymupdf HTTP API
# Usage: Start the service first, then run this script:
#   uvicorn src.http_server:app --port 8089
#   bash tests/test_e2e_curl.sh

set -e

BASE_URL="${PYMUPDF_URL:-http://localhost:8089}"
PASS=0
FAIL=0
TEST_PDF=""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_pass() { echo -e "${GREEN}PASS${NC}: $1"; PASS=$((PASS + 1)); }
log_fail() { echo -e "${RED}FAIL${NC}: $1 - $2"; FAIL=$((FAIL + 1)); }

# Create a test PDF using Python + PyMuPDF
create_test_pdf() {
    TEST_PDF=$(mktemp /tmp/test_pymupdf_XXXXXX.pdf)
    python3 -c "
import pymupdf
doc = pymupdf.open()

# Page 1: Title + body text
p1 = doc.new_page(width=612, height=792)
p1.insert_text(pymupdf.Point(72, 72), 'Annual Report 2024', fontsize=24, fontname='hebo')
p1.insert_text(pymupdf.Point(72, 120), 'Executive Summary', fontsize=16, fontname='hebo')
p1.insert_text(pymupdf.Point(72, 160), 'This document provides a comprehensive overview of operations for the fiscal year.', fontsize=12, fontname='helv')
p1.insert_text(pymupdf.Point(72, 180), 'Revenue grew significantly across all business segments during the reporting period.', fontsize=12, fontname='helv')

# Page 2: Table with grid lines
p2 = doc.new_page(width=612, height=792)
p2.insert_text(pymupdf.Point(72, 72), 'Financial Summary', fontsize=16, fontname='hebo')

# Draw table grid
sx, sy = 72, 100
cw, rh = 150, 25
for r in range(4):
    y = sy + r * rh
    p2.draw_line(pymupdf.Point(sx, y), pymupdf.Point(sx + 3*cw, y))
for c in range(4):
    x = sx + c * cw
    p2.draw_line(pymupdf.Point(x, sy), pymupdf.Point(x, sy + 3*rh))

headers = ['Quarter', 'Revenue', 'Profit']
data = [['Q1', '\$1.2M', '\$300K'], ['Q2', '\$1.5M', '\$450K']]
for c, h in enumerate(headers):
    p2.insert_text(pymupdf.Point(sx + c*cw + 5, sy + 18), h, fontsize=10, fontname='hebo')
for r, row in enumerate(data):
    for c, cell in enumerate(row):
        p2.insert_text(pymupdf.Point(sx + c*cw + 5, sy + (r+1)*rh + 18), cell, fontsize=10, fontname='helv')

# Page 3: More body text
p3 = doc.new_page(width=612, height=792)
p3.insert_text(pymupdf.Point(72, 72), 'Outlook', fontsize=16, fontname='hebo')
p3.insert_text(pymupdf.Point(72, 110), 'The company expects continued growth in the next fiscal year driven by expansion.', fontsize=12, fontname='helv')

doc.save('$TEST_PDF')
doc.close()
"
    echo "$TEST_PDF"
}

cleanup() {
    [ -f "$TEST_PDF" ] && rm -f "$TEST_PDF"
}
trap cleanup EXIT

echo "=================================="
echo "PyMuPDF Service E2E Tests"
echo "Base URL: $BASE_URL"
echo "=================================="
echo ""

# --- Health Check ---
echo "--- Health & Readiness ---"

response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$response" = "200" ]; then
    log_pass "GET /health returns 200"
else
    log_fail "GET /health" "Expected 200, got $response"
fi

response=$(curl -s "$BASE_URL/health")
if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'extract' in d['operations']" 2>/dev/null; then
    log_pass "Health lists 'extract' operation"
else
    log_fail "Health operations" "Missing 'extract'"
fi

response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/ready")
if [ "$response" = "200" ]; then
    log_pass "GET /ready returns 200"
else
    log_fail "GET /ready" "Expected 200, got $response"
fi

# --- Create test PDF ---
echo ""
echo "--- Creating test PDF ---"
TEST_PDF=$(create_test_pdf)
echo "Test PDF: $TEST_PDF ($(wc -c < "$TEST_PDF") bytes)"
echo ""

# --- Extract JSON ---
echo "--- Extract (JSON) ---"

response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/extract" \
    -F "file=@$TEST_PDF" \
    -F "output_format=json")
http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    log_pass "POST /api/extract (JSON) returns 200"
else
    log_fail "POST /api/extract (JSON)" "Expected 200, got $http_code"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['success']==True" 2>/dev/null; then
    log_pass "Extract JSON: success=true"
else
    log_fail "Extract JSON" "success not true"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['result']['model_used']=='pymupdf'" 2>/dev/null; then
    log_pass "Extract JSON: model_used=pymupdf"
else
    log_fail "Extract JSON" "model_used not pymupdf"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d['result']['paragraphs'])>0" 2>/dev/null; then
    log_pass "Extract JSON: has paragraphs"
else
    log_fail "Extract JSON" "No paragraphs"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); paras=d['result']['paragraphs']; assert any(p.get('role')=='title' for p in paras)" 2>/dev/null; then
    log_pass "Extract JSON: detected title role"
else
    log_fail "Extract JSON" "No title role detected"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); paras=d['result']['paragraphs']; assert any(p.get('role')=='sectionHeading' for p in paras)" 2>/dev/null; then
    log_pass "Extract JSON: detected sectionHeading role"
else
    log_fail "Extract JSON" "No sectionHeading role detected"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); p=d['result']['paragraphs'][0]; assert 'font' in p and 'size' in p['font']" 2>/dev/null; then
    log_pass "Extract JSON: paragraphs have font metadata"
else
    log_fail "Extract JSON" "Missing font metadata"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d['result']['content_blocks'])>0" 2>/dev/null; then
    log_pass "Extract JSON: has content_blocks"
else
    log_fail "Extract JSON" "No content_blocks"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['processing_time_ms']>=0" 2>/dev/null; then
    log_pass "Extract JSON: has processing_time_ms"
else
    log_fail "Extract JSON" "Missing processing_time_ms"
fi

# --- Extract HTML ---
echo ""
echo "--- Extract (HTML) ---"

response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/extract" \
    -F "file=@$TEST_PDF" \
    -F "output_format=html")
http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    log_pass "POST /api/extract (HTML) returns 200"
else
    log_fail "POST /api/extract (HTML)" "Expected 200, got $http_code"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '<html>' in d['result']" 2>/dev/null; then
    log_pass "Extract HTML: contains <html> tag"
else
    log_fail "Extract HTML" "Missing <html> tag"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '<h1>' in d['result']" 2>/dev/null; then
    log_pass "Extract HTML: has <h1> title tag"
else
    log_fail "Extract HTML" "Missing <h1> tag"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '<h2>' in d['result']" 2>/dev/null; then
    log_pass "Extract HTML: has <h2> heading tag"
else
    log_fail "Extract HTML" "Missing <h2> tag"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '<p>' in d['result']" 2>/dev/null; then
    log_pass "Extract HTML: has <p> body tag"
else
    log_fail "Extract HTML" "Missing <p> tag"
fi

# --- Page Range ---
echo ""
echo "--- Extract with Page Range ---"

response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/extract" \
    -F "file=@$TEST_PDF" \
    -F "output_format=json" \
    -F "pages=1,3")
http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    log_pass "POST /api/extract (pages=1,3) returns 200"
else
    log_fail "POST /api/extract (pages=1,3)" "Expected 200, got $http_code"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['metadata']['pages_processed']=='2'" 2>/dev/null; then
    log_pass "Extract page range: processed 2 pages"
else
    log_fail "Extract page range" "Did not process 2 pages"
fi

# --- Detect Text Layer ---
echo ""
echo "--- Detect Text Layer ---"

response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/detect-text-layer" \
    -F "file=@$TEST_PDF")
http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    log_pass "POST /api/detect-text-layer returns 200"
else
    log_fail "POST /api/detect-text-layer" "Expected 200, got $http_code"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['result']['total_pages']==3" 2>/dev/null; then
    log_pass "Detect: found 3 pages"
else
    log_fail "Detect" "Expected 3 pages"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert all(p['has_text_layer'] for p in d['result']['pages'])" 2>/dev/null; then
    log_pass "Detect: all pages have text layer"
else
    log_fail "Detect" "Some pages missing text layer"
fi

# --- Base64 /process endpoint ---
echo ""
echo "--- Process (base64 mode) ---"

PDF_B64=$(base64 < "$TEST_PDF" | tr -d '\n')

response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/process" \
    -H "Content-Type: application/json" \
    -d "{\"operation\":\"extract\",\"data\":\"$PDF_B64\",\"options\":{\"output_format\":\"json\"}}")
http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    log_pass "POST /process (base64) returns 200"
else
    log_fail "POST /process (base64)" "Expected 200, got $http_code"
fi

if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['success']==True" 2>/dev/null; then
    log_pass "Process base64: success=true"
else
    log_fail "Process base64" "success not true"
fi

# --- Error Handling ---
echo ""
echo "--- Error Handling ---"

response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/process" \
    -H "Content-Type: application/json" \
    -d '{"operation":"nonexistent","data":"dGVzdA==","options":{}}')
if [ "$response" = "400" ]; then
    log_pass "Unsupported operation returns 400"
else
    log_fail "Unsupported operation" "Expected 400, got $response"
fi

response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/process" \
    -H "Content-Type: application/json" \
    -d '{"operation":"extract","data":"!!!invalid!!!","options":{}}')
if [ "$response" = "400" ]; then
    log_pass "Invalid base64 returns 400"
else
    log_fail "Invalid base64" "Expected 400, got $response"
fi

# --- Summary ---
echo ""
echo "=================================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "=================================="

if [ $FAIL -gt 0 ]; then
    exit 1
fi
