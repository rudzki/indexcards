#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENDOR_DIR="$PROJECT_DIR/app/static/js/vendor/prosemirror"
TMPDIR=$(mktemp -d)

cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

echo "Installing ProseMirror packages in temp directory..."
cd "$TMPDIR"
npm init -y --silent >/dev/null 2>&1
npm install --save \
    prosemirror-model@1.24.1 \
    prosemirror-state@1.4.3 \
    prosemirror-view@1.38.1 \
    prosemirror-schema-basic@1.2.4 \
    prosemirror-schema-list@1.5.1 \
    prosemirror-history@1.4.1 \
    prosemirror-keymap@1.2.2 \
    prosemirror-commands@1.6.2 \
    prosemirror-inputrules@1.4.0 \
    prosemirror-markdown@1.13.2 \
    prosemirror-dropcursor@1.8.1 \
    prosemirror-gapcursor@1.3.2 \
    2>/dev/null

echo "Creating entry point..."
cat > entry.js << 'ENTRY'
export {Schema, DOMParser, DOMSerializer, Fragment, Slice, Mark, Node as ProseMirrorNode} from "prosemirror-model"
export {EditorState, Plugin, PluginKey, TextSelection, NodeSelection, AllSelection} from "prosemirror-state"
export {EditorView, Decoration, DecorationSet} from "prosemirror-view"
export {schema as basicSchema, nodes as basicNodes, marks as basicMarks} from "prosemirror-schema-basic"
export {addListNodes, wrapInList, splitListItem, liftListItem, sinkListItem} from "prosemirror-schema-list"
export {history, undo, redo} from "prosemirror-history"
export {keymap} from "prosemirror-keymap"
export {
    baseKeymap, toggleMark, setBlockType, wrapIn, lift,
    chainCommands, exitCode, joinUp, joinDown, selectParentNode,
    newlineInCode, createParagraphNear, liftEmptyBlock, splitBlock
} from "prosemirror-commands"
export {
    InputRule, inputRules, wrappingInputRule, textblockTypeInputRule,
    smartQuotes, emDash, ellipsis
} from "prosemirror-inputrules"
export {
    schema as markdownSchema,
    defaultMarkdownParser, defaultMarkdownSerializer,
    MarkdownParser, MarkdownSerializer, MarkdownSerializerState
} from "prosemirror-markdown"
export {dropCursor} from "prosemirror-dropcursor"
export {gapCursor} from "prosemirror-gapcursor"
ENTRY

echo "Bundling with esbuild..."
npx esbuild entry.js \
    --bundle \
    --format=esm \
    --minify \
    --outfile=prosemirror-bundle.js \
    2>/dev/null

mkdir -p "$VENDOR_DIR"
cp prosemirror-bundle.js "$VENDOR_DIR/prosemirror-bundle.js"

SIZE=$(wc -c < "$VENDOR_DIR/prosemirror-bundle.js" | tr -d ' ')
SIZE_KB=$((SIZE / 1024))
echo "Done! Bundle: $VENDOR_DIR/prosemirror-bundle.js ($SIZE_KB KB)"
