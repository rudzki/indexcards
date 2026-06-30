import {
    Schema,
    EditorState, Plugin, PluginKey,
    EditorView,
    markdownSchema,
    addListNodes,
    history, undo, redo,
    keymap,
    baseKeymap, toggleMark, setBlockType, wrapIn, lift,
    chainCommands, exitCode, newlineInCode, createParagraphNear,
    liftEmptyBlock, splitBlock,
    splitListItem, liftListItem, sinkListItem, wrapInList,
    InputRule, inputRules, wrappingInputRule, textblockTypeInputRule,
    smartQuotes, emDash, ellipsis,
    defaultMarkdownParser, defaultMarkdownSerializer,
    MarkdownParser, MarkdownSerializer, MarkdownSerializerState,
    dropCursor, gapCursor,
} from "./vendor/prosemirror/prosemirror-bundle.js";

const schema = new Schema({
    nodes: addListNodes(markdownSchema.spec.nodes, "paragraph block*", "block"),
    marks: markdownSchema.spec.marks,
});

function buildInputRules(schema) {
    let rules = smartQuotes.concat(ellipsis, emDash);

    rules.push(textblockTypeInputRule(/^(#{2,4})\s$/, schema.nodes.heading, match => ({
        level: match[1].length,
    })));
    rules.push(wrappingInputRule(/^\s*>\s$/, schema.nodes.blockquote));
    rules.push(wrappingInputRule(/^\s*(\d+)\.\s$/, schema.nodes.ordered_list, match => ({
        order: +match[1],
    }), (match, node) => node.childCount + node.attrs.order === +match[1]));
    rules.push(wrappingInputRule(/^\s*[-*]\s$/, schema.nodes.bullet_list));
    rules.push(textblockTypeInputRule(/^```$/, schema.nodes.code_block));
    rules.push(new InputRule(/^---$/, (state, match, start, end) => {
        return state.tr.replaceRangeWith(start, end, schema.nodes.horizontal_rule.create());
    }));

    return inputRules({ rules });
}

function buildKeymap(schema) {
    let keys = {};

    keys["Mod-z"] = undo;
    keys["Mod-Shift-z"] = redo;
    keys["Mod-y"] = redo;

    keys["Mod-b"] = toggleMark(schema.marks.strong);
    keys["Mod-i"] = toggleMark(schema.marks.em);
    keys["Mod-`"] = toggleMark(schema.marks.code);

    keys["Enter"] = chainCommands(
        splitListItem(schema.nodes.list_item),
        newlineInCode,
        createParagraphNear,
        liftEmptyBlock,
        splitBlock,
    );
    keys["Mod-Enter"] = exitCode;

    keys["Tab"] = sinkListItem(schema.nodes.list_item);
    keys["Shift-Tab"] = liftListItem(schema.nodes.list_item);

    keys["Mod-k"] = (state, dispatch, view) => {
        if (view) showLinkDialog(view);
        return true;
    };

    return keymap(keys);
}

const mdParser = new MarkdownParser(
    schema,
    defaultMarkdownParser.tokenizer,
    defaultMarkdownParser.tokens,
);

const mdSerializer = new MarkdownSerializer(
    {
        ...defaultMarkdownSerializer.nodes,
        bullet_list(state, node) {
            state.renderList(node, "  ", () => "- ");
        },
        ordered_list(state, node) {
            let start = node.attrs.order || 1;
            state.renderList(node, "  ", (i) => `${start + i}. `);
        },
        list_item(state, node) {
            state.renderContent(node);
        },
    },
    defaultMarkdownSerializer.marks,
);

function markdownToDoc(markdown) {
    if (!markdown || !markdown.trim()) {
        return mdParser.parse("");
    }
    try {
        return mdParser.parse(markdown);
    } catch (e) {
        console.warn("Markdown parse error:", e);
        return mdParser.parse("");
    }
}

function docToMarkdown(doc) {
    return mdSerializer.serialize(doc);
}

function uploadImage(file, view, insertPos) {
    const formData = new FormData();
    formData.append('image', file);
    fetch('/api/upload-image', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (!data.url) return;
            const node = schema.nodes.image.create({ src: data.url, alt: file.name.replace(/\.[^.]+$/, '') });
            view.dispatch(view.state.tr.insert(insertPos, node));
        })
        .catch(() => showToast('error', 'Image upload failed.'));
}

function buildImagePlugin() {
    return new Plugin({
        props: {
            handlePaste(view, event) {
                const items = Array.from(event.clipboardData?.items || []);
                const imageItem = items.find(i => i.type.startsWith('image/'));
                if (!imageItem) return false;
                event.preventDefault();
                const file = imageItem.getAsFile();
                if (file) uploadImage(file, view, view.state.selection.from);
                return true;
            },
            handleDrop(view, event, _slice, moved) {
                if (moved) return false;
                const files = Array.from(event.dataTransfer?.files || []);
                const imageFile = files.find(f => f.type.startsWith('image/'));
                if (!imageFile) return false;
                event.preventDefault();
                const coords = view.posAtCoords({ left: event.clientX, top: event.clientY });
                uploadImage(imageFile, view, coords ? coords.pos : view.state.doc.content.size);
                return true;
            },
        },
    });
}

function initEditor(textarea) {
    const editorDiv = document.createElement("div");
    editorDiv.className = "ProseMirror-container";
    textarea.parentNode.insertBefore(editorDiv, textarea);
    textarea.style.display = "none";

    const doc = markdownToDoc(textarea.value);

    const state = EditorState.create({
        doc,
        plugins: [
            buildInputRules(schema),
            buildKeymap(schema),
            keymap(baseKeymap),
            history(),
            dropCursor(),
            gapCursor(),
            buildImagePlugin(),
            new Plugin({
                view() {
                    return {
                        update(view) {
                            textarea.value = docToMarkdown(view.state.doc);
                        },
                    };
                },
            }),
        ],
    });

    const view = new EditorView(editorDiv, { state });
    return view;
}

function triggerImageUpload(view) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/png,image/jpeg,image/gif,image/webp';
    input.addEventListener('change', () => {
        const file = input.files[0];
        if (file) uploadImage(file, view, view.state.selection.from);
    });
    input.click();
}

function setupToolbar(toolbar, view) {
    toolbar.innerHTML = "";

    const buttons = [
        { label: "B", title: "Bold (Ctrl+B)", action: () => toggleMark(schema.marks.strong)(view.state, view.dispatch), style: "font-weight:bold" },
        { label: "I", title: "Italic (Ctrl+I)", action: () => toggleMark(schema.marks.em)(view.state, view.dispatch), style: "font-style:italic" },
        { sep: true },
        { label: "H2", title: "Heading 2", action: () => setBlockType(schema.nodes.heading, { level: 2 })(view.state, view.dispatch) },
        { label: "H3", title: "Heading 3", action: () => setBlockType(schema.nodes.heading, { level: 3 })(view.state, view.dispatch) },
        { label: "H4", title: "Heading 4", action: () => setBlockType(schema.nodes.heading, { level: 4 })(view.state, view.dispatch) },
        { label: "¶", title: "Paragraph", action: () => setBlockType(schema.nodes.paragraph)(view.state, view.dispatch) },
        { sep: true },
        { label: "❝", title: "Blockquote", action: () => wrapIn(schema.nodes.blockquote)(view.state, view.dispatch) },
        { icon: "bi-list-ul", title: "Bullet List", action: () => wrapInList(schema.nodes.bullet_list)(view.state, view.dispatch) },
        { icon: "bi-list-ol", title: "Numbered List", action: () => wrapInList(schema.nodes.ordered_list)(view.state, view.dispatch) },
        { icon: "bi-hr", title: "Horizontal Rule", action: () => {
            const { tr, selection } = view.state;
            view.dispatch(tr.replaceSelectionWith(schema.nodes.horizontal_rule.create()));
        }},
        { sep: true },
        { icon: "bi-link-45deg", title: "Insert Link (Ctrl+K)", action: () => showLinkDialog(view) },
        { icon: "bi-image", title: "Insert Image", action: () => triggerImageUpload(view) },
        { icon: "bi-code", title: "Inline Code (Ctrl+`)", action: () => toggleMark(schema.marks.code)(view.state, view.dispatch) },
        { sep: true },
        { icon: "bi-arrow-counterclockwise", title: "Undo (Ctrl+Z)", action: () => undo(view.state, view.dispatch) },
        { icon: "bi-arrow-clockwise", title: "Redo (Ctrl+Shift+Z)", action: () => redo(view.state, view.dispatch) },
    ];

    buttons.forEach(b => {
        if (b.sep) {
            const sep = document.createElement("span");
            sep.className = "toolbar-sep";
            toolbar.appendChild(sep);
            return;
        }
        const btn = document.createElement("button");
        btn.type = "button";
        if (b.icon) {
            btn.innerHTML = `<i class="bi ${b.icon}"></i>`;
        } else {
            btn.textContent = b.label;
        }
        btn.title = b.title;
        if (b.style) btn.setAttribute("style", b.style);
        btn.addEventListener("mousedown", e => {
            e.preventDefault();
            b.action();
            view.focus();
        });
        toolbar.appendChild(btn);
    });
}

function showLinkDialog(view) {
    const existing = document.querySelector(".link-dialog");
    if (existing) existing.remove();

    const dialog = document.createElement("div");
    dialog.className = "link-dialog";
    dialog.innerHTML = `
        <div class="link-dialog-backdrop"></div>
        <div class="link-dialog-content">
            <label>Search entries or paste URL:</label>
            <input type="text" class="link-dialog-input" placeholder="Start typing…" autofocus>
            <div class="link-dialog-results"></div>
            <div class="link-dialog-actions">
                <button type="button" class="link-dialog-cancel">Cancel</button>
                <button type="button" class="link-dialog-insert">Insert Link</button>
            </div>
        </div>
    `;
    document.body.appendChild(dialog);

    const input = dialog.querySelector(".link-dialog-input");
    const results = dialog.querySelector(".link-dialog-results");
    let selectedUrl = null;
    let debounceTimer = null;

    input.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        const q = input.value.trim();
        if (q.length < 1) { results.innerHTML = ""; return; }

        if (q.startsWith("http://") || q.startsWith("https://") || q.startsWith("/")) {
            selectedUrl = q;
            results.innerHTML = `<div class="link-result selected">Use: ${q}</div>`;
            return;
        }

        debounceTimer = setTimeout(() => {
            fetch(`/api/entries/search?q=${encodeURIComponent(q)}`)
                .then(r => r.json())
                .then(entries => {
                    if (entries.length === 0) {
                        results.innerHTML = `<div class="link-result-empty">No entries found. You can paste a full URL instead.</div>`;
                        selectedUrl = null;
                        return;
                    }
                    results.innerHTML = entries.map(e =>
                        `<div class="link-result" data-slug="${e.slug}">
                            <strong>${e.title}</strong>
                            ${e.summary ? `<span class="link-result-summary">${e.summary}</span>` : ""}
                        </div>`
                    ).join("");
                    selectedUrl = `/${entries[0].slug}/`;
                    results.querySelector(".link-result").classList.add("selected");
                });
        }, 200);
    });

    results.addEventListener("click", e => {
        const item = e.target.closest(".link-result");
        if (!item) return;
        results.querySelectorAll(".link-result").forEach(r => r.classList.remove("selected"));
        item.classList.add("selected");
        const slug = item.dataset.slug;
        selectedUrl = slug ? `/${slug}/` : input.value;
    });

    function insertLink() {
        const url = selectedUrl || input.value.trim();
        if (!url) return close();

        const { state, dispatch } = view;
        const { from, to, empty } = state.selection;
        const linkMark = schema.marks.link.create({ href: url });

        if (empty) {
            const linkText = url.startsWith("/") ? url.replace(/\//g, "").replace(/-/g, " ") : url;
            const textNode = schema.text(linkText, [linkMark]);
            dispatch(state.tr.replaceSelectionWith(textNode));
        } else {
            dispatch(state.tr.addMark(from, to, linkMark));
        }
        close();
        view.focus();
    }

    function close() {
        dialog.remove();
    }

    dialog.querySelector(".link-dialog-backdrop").addEventListener("click", close);
    dialog.querySelector(".link-dialog-cancel").addEventListener("click", close);
    dialog.querySelector(".link-dialog-insert").addEventListener("click", insertLink);

    input.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); insertLink(); }
        if (e.key === "Escape") close();
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            const items = results.querySelectorAll(".link-result");
            if (items.length === 0) return;
            const current = results.querySelector(".link-result.selected");
            let idx = Array.from(items).indexOf(current);
            if (e.key === "ArrowDown") idx = Math.min(idx + 1, items.length - 1);
            else idx = Math.max(idx - 1, 0);
            items.forEach(r => r.classList.remove("selected"));
            items[idx].classList.add("selected");
            items[idx].scrollIntoView({ block: "nearest" });
            const slug = items[idx].dataset.slug;
            selectedUrl = slug ? `/${slug}/` : input.value;
        }
    });

    requestAnimationFrame(() => input.focus());
}

document.addEventListener("DOMContentLoaded", () => {
    const textarea = document.getElementById("body_markdown");
    const toolbar = document.getElementById("editor-toolbar");
    const previewDiv = document.getElementById("editor-preview");

    if (!textarea || !toolbar) return;

    const form = textarea.closest("form");
    const entryId = form.dataset.entryId || "new";
    const autosaveKey = `autosave-${entryId}`;

    // Check for auto-saved content before initializing ProseMirror
    const saved = localStorage.getItem(autosaveKey);
    if (saved && saved !== textarea.value) {
        textarea.value = saved;
        showToast("warn", "Restored from auto-save", 8000);
    }

    const view = initEditor(textarea);
    setupToolbar(toolbar, view);

    const initialContent = textarea.value;
    let submitting = false;
    form.addEventListener("submit", () => {
        submitting = true;
        localStorage.removeItem(autosaveKey);
    });
    window.addEventListener("beforeunload", e => {
        if (!submitting && textarea.value !== initialContent) {
            e.preventDefault();
        }
    });

    // Auto-save every 10 seconds
    setInterval(() => {
        const current = textarea.value;
        if (current) {
            localStorage.setItem(autosaveKey, current);
        }
    }, 10000);

    // Word count and reading time
    const statsDiv = document.getElementById("editor-stats");
    if (statsDiv) {
        function updateStats() {
            const text = textarea.value.trim();
            const words = text ? text.split(/\s+/).length : 0;
            const minutes = Math.max(1, Math.ceil(words / 200));
            statsDiv.textContent = `${words} word${words !== 1 ? 's' : ''} · ${minutes} min read`;
        }
        textarea.addEventListener("input", updateStats);
        // Also update when ProseMirror syncs to textarea
        new MutationObserver(updateStats).observe(textarea, { attributes: true, childList: true });
        // Poll for ProseMirror changes since it sets .value programmatically
        setInterval(updateStats, 1000);
        updateStats();
    }

    if (previewDiv) previewDiv.remove();
});
