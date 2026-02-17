#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$(dirname "$CLIENT_DIR")")"
PROTO_DIR="$REPO_ROOT/proto"
OUT_DIR="$CLIENT_DIR/src/generated"

mkdir -p "$OUT_DIR"

PROTOC_GEN_TS_PROTO="$CLIENT_DIR/node_modules/.bin/protoc-gen-ts_proto"

if [ ! -f "$PROTOC_GEN_TS_PROTO" ]; then
  echo "Error: ts-proto not found. Run 'npm install' in packages/client-ts first."
  exit 1
fi

echo "Generating TypeScript gRPC client from proto..."
protoc \
  --plugin="protoc-gen-ts_proto=$PROTOC_GEN_TS_PROTO" \
  --ts_proto_out="$OUT_DIR" \
  --ts_proto_opt=outputServices=grpc-js \
  --ts_proto_opt=esModuleInterop=true \
  --ts_proto_opt=importSuffix=.js \
  -I "$PROTO_DIR" \
  "$PROTO_DIR/pymupdf_worker.proto"

echo "Generated TypeScript client at $OUT_DIR"
