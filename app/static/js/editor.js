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
    marks: markdownSchema.spec.marks.append({
        s: {
            parseDOM: [{ tag: 's' }, { tag: 'del' }, { style: 'text-decoration=line-through' }],
            toDOM() { return ['s', 0]; },
        },
    }),
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
    rules.push(new InputRule(/~~([^~\s][^~]*)~~$/, (state, match, start, end) => {
        const markType = schema.marks.s;
        if (!markType) return null;
        return state.tr.replaceWith(start, end, schema.text(match[1], [markType.create()]));
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

try { defaultMarkdownParser.tokenizer.enable('strikethrough'); } catch (e) {}

const mdParser = new MarkdownParser(
    schema,
    defaultMarkdownParser.tokenizer,
    { ...defaultMarkdownParser.tokens, s: { mark: 's' } },
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
    {
        ...defaultMarkdownSerializer.marks,
        s: { open: '~~', close: '~~', mixable: true, expelEnclosingWhitespace: true },
    },
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

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function uploadImage(file, view, insertPos) {
    const formData = new FormData();
    formData.append('image', file);
    fetch('/api/upload-image', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken() },
        body: formData,
    })
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

function buildWikiLinkPlugin() {
    let popup = null;
    let results = [];
    let selectedIdx = 0;
    let queryStart = null;
    let debounceTimer = null;
    let currentQuery = '';

    function closePopup() {
        if (popup) { popup.remove(); popup = null; }
        results = [];
        selectedIdx = 0;
        queryStart = null;
        clearTimeout(debounceTimer);
    }

    function renderPopup(view) {
        if (!popup) return;
        popup.innerHTML = '';
        if (results.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'wikilink-empty';
            empty.textContent = 'No entries found';
            popup.appendChild(empty);
            return;
        }
        results.forEach((entry, i) => {
            const div = document.createElement('div');
            div.className = 'wikilink-result' + (i === selectedIdx ? ' selected' : '') +
                (entry.create ? ' wikilink-result-create' : '');
            if (entry.create) {
                div.textContent = 'Create new entry: "' + entry.title + '"';
            } else {
                const title = document.createElement('strong');
                title.textContent = entry.title;
                div.appendChild(title);
                if (entry.summary) {
                    const s = document.createElement('span');
                    s.className = 'wikilink-summary';
                    s.textContent = entry.summary;
                    div.appendChild(s);
                }
            }
            div.addEventListener('mousedown', e => {
                e.preventDefault();
                insertWikiLink(view, entry);
            });
            popup.appendChild(div);
        });
    }

    function positionPopup(view, cursorPos) {
        if (!popup) return;
        positionFloatingPopup(popup, view, cursorPos);
    }

    function insertWikiLink(view, entry) {
        if (queryStart === null) return;
        const { state } = view;
        const start = queryStart;
        const to = state.selection.from;

        if (entry.create) {
            closePopup();
            fetch('/api/entries/quick-create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                body: JSON.stringify({ title: entry.title }),
            })
                .then(r => r.json().then(data => ({ ok: r.ok, data })))
                .then(({ ok, data }) => {
                    if (!ok) {
                        if (window.showToast) showToast('error', data.error || 'Could not create entry.');
                        return;
                    }
                    const linkMark = schema.marks.link.create({ href: `/${data.slug}/` });
                    view.dispatch(view.state.tr.replaceWith(start, to, schema.text(data.title, [linkMark])));
                    view.focus();
                })
                .catch(() => {
                    if (window.showToast) showToast('error', 'Could not create entry.');
                });
            return;
        }

        const linkMark = schema.marks.link.create({ href: `/${entry.slug}/` });
        view.dispatch(state.tr.replaceWith(start, to, schema.text(entry.title, [linkMark])));
        closePopup();
        view.focus();
    }

    return new Plugin({
        view() {
            return {
                update(view) {
                    const { $from } = view.state.selection;
                    const textBefore = $from.parent.textContent.slice(0, $from.parentOffset);
                    const match = textBefore.match(/\[\[([^\]]*)$/);

                    if (!match) { closePopup(); return; }

                    const query = match[1];
                    queryStart = $from.pos - query.length - 2;
                    currentQuery = query;

                    if (!popup) {
                        popup = document.createElement('div');
                        popup.className = 'wikilink-popup';
                        document.body.appendChild(popup);
                        const hint = document.createElement('div');
                        hint.className = 'wikilink-empty';
                        hint.textContent = 'Type to search entries…';
                        popup.appendChild(hint);
                    }

                    positionPopup(view, $from.pos);

                    clearTimeout(debounceTimer);
                    if (!query) return;

                    debounceTimer = setTimeout(() => {
                        fetch(`/api/entries/search?q=${encodeURIComponent(query)}`)
                            .then(r => r.json())
                            .then(data => {
                                if (query !== currentQuery) return;
                                const exactMatch = data.some(e => e.title.toLowerCase() === query.toLowerCase());
                                results = exactMatch ? data : data.concat([{ create: true, title: query }]);
                                selectedIdx = 0;
                                renderPopup(view);
                                positionPopup(view, view.state.selection.$from.pos);
                            })
                            .catch(() => {});
                    }, 150);
                },
                destroy() { closePopup(); },
            };
        },
        props: {
            handleKeyDown(view, event) {
                if (!popup) return false;
                if (event.key === 'Escape') { closePopup(); return true; }
                if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    selectedIdx = Math.min(selectedIdx + 1, results.length - 1);
                    renderPopup(view);
                    return true;
                }
                if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    selectedIdx = Math.max(selectedIdx - 1, 0);
                    renderPopup(view);
                    return true;
                }
                if (event.key === 'Enter' && results.length > 0) {
                    insertWikiLink(view, results[selectedIdx]);
                    return true;
                }
                return false;
            },
        },
    });
}

let toolbarStateUpdater = null;

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
            buildWikiLinkPlugin(),
            new Plugin({
                view() {
                    return {
                        update(view) {
                            textarea.value = docToMarkdown(view.state.doc);
                            toolbarStateUpdater && toolbarStateUpdater(view.state);
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

function isMarkActive(state, markType) {
    const { from, $from, to, empty } = state.selection;
    if (empty) return !!(state.storedMarks || $from.marks()).find(m => m.type === markType);
    return state.doc.rangeHasMark(from, to, markType);
}

function isNodeActive(state, nodeType, attrs) {
    const { $from } = state.selection;
    if (nodeType === schema.nodes.blockquote ||
        nodeType === schema.nodes.bullet_list ||
        nodeType === schema.nodes.ordered_list) {
        for (let d = $from.depth; d > 0; d--) {
            if ($from.node(d).type === nodeType) return true;
        }
        return false;
    }
    const node = $from.parent;
    if (node.type !== nodeType) return false;
    if (!attrs) return true;
    return Object.keys(attrs).every(k => node.attrs[k] === attrs[k]);
}

function setupToolbar(toolbar, view) {
    toolbar.innerHTML = "";

    const buttons = [
        { label: "B", title: "Bold (Ctrl+B)", action: () => toggleMark(schema.marks.strong)(view.state, view.dispatch), style: "font-weight:bold", activeMark: () => schema.marks.strong },
        { label: "I", title: "Italic (Ctrl+I)", action: () => toggleMark(schema.marks.em)(view.state, view.dispatch), style: "font-style:italic", activeMark: () => schema.marks.em },
        { label: "S̶", title: "Strikethrough", action: () => toggleMark(schema.marks.s)(view.state, view.dispatch), style: "text-decoration:line-through", activeMark: () => schema.marks.s },
        { sep: true },
        { label: "H2", title: "Heading 2", action: () => setBlockType(schema.nodes.heading, { level: 2 })(view.state, view.dispatch), activeNode: () => schema.nodes.heading, activeNodeAttrs: { level: 2 } },
        { label: "H3", title: "Heading 3", action: () => setBlockType(schema.nodes.heading, { level: 3 })(view.state, view.dispatch), activeNode: () => schema.nodes.heading, activeNodeAttrs: { level: 3 } },
        { label: "H4", title: "Heading 4", action: () => setBlockType(schema.nodes.heading, { level: 4 })(view.state, view.dispatch), activeNode: () => schema.nodes.heading, activeNodeAttrs: { level: 4 } },
        { label: "¶", title: "Paragraph", action: () => setBlockType(schema.nodes.paragraph)(view.state, view.dispatch), activeNode: () => schema.nodes.paragraph },
        { sep: true },
        { label: "❝", title: "Blockquote", action: () => wrapIn(schema.nodes.blockquote)(view.state, view.dispatch), activeNode: () => schema.nodes.blockquote },
        { icon: "bi-list-ul", title: "Bullet List", action: () => wrapInList(schema.nodes.bullet_list)(view.state, view.dispatch), activeNode: () => schema.nodes.bullet_list },
        { icon: "bi-list-ol", title: "Numbered List", action: () => wrapInList(schema.nodes.ordered_list)(view.state, view.dispatch), activeNode: () => schema.nodes.ordered_list },
        { icon: "bi-hr", title: "Horizontal Rule", action: () => {
            const { tr } = view.state;
            view.dispatch(tr.replaceSelectionWith(schema.nodes.horizontal_rule.create()));
        }},
        { sep: true },
        { icon: "bi-link-45deg", title: "Insert Link (Ctrl+K)", action: () => showLinkDialog(view) },
        { icon: "bi-image", title: "Insert Image", action: () => triggerImageUpload(view) },
        { icon: "bi-code", title: "Inline Code (Ctrl+`)", action: () => toggleMark(schema.marks.code)(view.state, view.dispatch), activeMark: () => schema.marks.code },
        { sep: true },
        { icon: "bi-arrow-counterclockwise", title: "Undo (Ctrl+Z)", action: () => undo(view.state, view.dispatch) },
        { icon: "bi-arrow-clockwise", title: "Redo (Ctrl+Shift+Z)", action: () => redo(view.state, view.dispatch) },
    ];

    const activeChecks = [];

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

        if (b.activeMark) {
            activeChecks.push({ btn, check: (state) => isMarkActive(state, b.activeMark()) });
        } else if (b.activeNode) {
            activeChecks.push({ btn, check: (state) => isNodeActive(state, b.activeNode(), b.activeNodeAttrs) });
        }
    });

    return (state) => {
        activeChecks.forEach(({ btn, check }) => {
            btn.classList.toggle('active', !!check(state));
        });
    };
}

function positionFloatingPopup(popup, view, pos) {
    const coords = view.coordsAtPos(pos);
    const popW = popup.offsetWidth || 300;
    let left = coords.left + window.scrollX;
    let top = coords.bottom + window.scrollY + 4;
    left = Math.max(8, Math.min(left, window.innerWidth - popW - 8));
    popup.style.left = left + "px";
    popup.style.top = top + "px";
}

function showLinkDialog(view) {
    const existing = document.querySelector(".link-dialog");
    if (existing) existing.remove();

    const dialog = document.createElement("div");
    dialog.className = "link-dialog";
    dialog.innerHTML = `
        <input type="text" class="link-dialog-input" placeholder="Search entries or paste URL…" autofocus>
        <div class="link-dialog-results"></div>
    `;
    document.body.appendChild(dialog);

    const anchorPos = view.state.selection.from;
    positionFloatingPopup(dialog, view, anchorPos);

    const input = dialog.querySelector(".link-dialog-input");
    const results = dialog.querySelector(".link-dialog-results");
    let selectedUrl = null;
    let selectedTitle = null;
    let debounceTimer = null;
    let creating = false;

    function quickCreateAndInsert(title) {
        if (creating) return;
        creating = true;
        fetch("/api/entries/quick-create", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
            body: JSON.stringify({ title }),
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                creating = false;
                if (!ok) {
                    if (window.showToast) showToast("error", data.error || "Could not create entry.");
                    return;
                }
                selectedUrl = `/${data.slug}/`;
                selectedTitle = data.title;
                insertLink();
            })
            .catch(() => {
                creating = false;
                if (window.showToast) showToast("error", "Could not create entry.");
            });
    }

    input.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        const q = input.value.trim();
        if (q.length < 1) { results.innerHTML = ""; return; }

        if (q.startsWith("http://") || q.startsWith("https://") || q.startsWith("/")) {
            selectedUrl = q;
            selectedTitle = null;
            results.innerHTML = `<div class="link-result selected">Use: ${q}</div>`;
            return;
        }

        debounceTimer = setTimeout(() => {
            fetch(`/api/entries/search?q=${encodeURIComponent(q)}`)
                .then(r => r.json())
                .then(entries => {
                    let html = entries.map(e =>
                        `<div class="link-result" data-slug="${e.slug}" data-title="${escapeHtml(e.title)}">
                            <strong>${escapeHtml(e.title)}</strong>
                            ${e.summary ? `<span class="link-result-summary">${escapeHtml(e.summary)}</span>` : ""}
                        </div>`
                    ).join("");

                    const exactMatch = entries.some(e => e.title.toLowerCase() === q.toLowerCase());
                    if (!exactMatch) {
                        html += `<div class="link-result link-result-create" data-create="${escapeHtml(q)}">Create new entry: "${escapeHtml(q)}"</div>`;
                    }

                    if (!html) {
                        results.innerHTML = `<div class="link-result-empty">No entries found. You can paste a full URL instead.</div>`;
                        selectedUrl = null;
                        selectedTitle = null;
                        return;
                    }

                    results.innerHTML = html;
                    const first = results.querySelector(".link-result");
                    first.classList.add("selected");
                    if (entries.length) {
                        selectedUrl = `/${entries[0].slug}/`;
                        selectedTitle = entries[0].title;
                    } else {
                        selectedUrl = null;
                        selectedTitle = null;
                    }
                    positionFloatingPopup(dialog, view, anchorPos);
                });
        }, 200);
    });

    results.addEventListener("click", e => {
        const item = e.target.closest(".link-result");
        if (!item) return;
        if (item.dataset.create) {
            quickCreateAndInsert(item.dataset.create);
            return;
        }
        results.querySelectorAll(".link-result").forEach(r => r.classList.remove("selected"));
        item.classList.add("selected");
        const slug = item.dataset.slug;
        selectedUrl = slug ? `/${slug}/` : input.value;
        selectedTitle = item.dataset.title || null;
        insertLink();
    });

    function insertLink() {
        const url = selectedUrl || input.value.trim();
        if (!url) return close();

        const { state, dispatch } = view;
        const { from, to, empty } = state.selection;
        const linkMark = schema.marks.link.create({ href: url });

        if (empty) {
            const linkText = selectedTitle || (url.startsWith("/") ? url.replace(/\//g, "").replace(/-/g, " ") : url);
            const textNode = schema.text(linkText, [linkMark]);
            dispatch(state.tr.replaceSelectionWith(textNode));
        } else {
            dispatch(state.tr.addMark(from, to, linkMark));
        }
        close();
        view.focus();
    }

    function onOutsideClick(e) {
        if (!dialog.contains(e.target)) close();
    }

    function close() {
        document.removeEventListener("mousedown", onOutsideClick);
        dialog.remove();
    }

    setTimeout(() => document.addEventListener("mousedown", onOutsideClick), 0);

    input.addEventListener("keydown", e => {
        if (e.key === "Enter") {
            e.preventDefault();
            const active = results.querySelector(".link-result.selected");
            if (active && active.dataset.create) {
                quickCreateAndInsert(active.dataset.create);
            } else {
                insertLink();
            }
        }
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
            if (items[idx].dataset.create) {
                selectedUrl = null;
                selectedTitle = null;
            } else {
                const slug = items[idx].dataset.slug;
                selectedUrl = slug ? `/${slug}/` : input.value;
                selectedTitle = items[idx].dataset.title || null;
            }
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

    const saved = localStorage.getItem(autosaveKey);
    if (saved && saved !== textarea.value) {
        textarea.value = saved;
        showToast("warn", "Restored from auto-save", 8000);
    }

    const view = initEditor(textarea);
    toolbarStateUpdater = setupToolbar(toolbar, view);

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

    // Stats bar: word count (left) + autosave status (right)
    let lastAutosavedContent = textarea.value;
    let lastAutosaveAt = null;

    const statsDiv = document.getElementById("editor-stats");
    if (statsDiv) {
        const wordSpan = document.createElement('span');
        const saveSpan = document.createElement('span');
        saveSpan.className = 'editor-save-status';
        statsDiv.appendChild(wordSpan);
        statsDiv.appendChild(saveSpan);

        function updateStats() {
            const text = textarea.value.trim();
            const words = text ? text.split(/\s+/).length : 0;
            const minutes = Math.max(1, Math.ceil(words / 200));
            wordSpan.textContent = `${words} word${words !== 1 ? 's' : ''} · ${minutes} min read`;

            const current = textarea.value;
            if (current !== lastAutosavedContent) {
                saveSpan.textContent = 'Unsaved';
                saveSpan.className = 'editor-save-status editor-save-status--dirty';
            } else if (lastAutosaveAt) {
                const secs = Math.round((Date.now() - lastAutosaveAt) / 1000);
                saveSpan.textContent = secs < 60 ? `Saved ${secs}s ago` : '';
                saveSpan.className = 'editor-save-status';
            } else {
                saveSpan.textContent = '';
            }
        }

        setInterval(updateStats, 1000);
        updateStats();
    }

    // Autosave every 10 seconds
    setInterval(() => {
        const current = textarea.value;
        if (current) {
            localStorage.setItem(autosaveKey, current);
            lastAutosavedContent = current;
            lastAutosaveAt = Date.now();
        }
    }, 10000);

    if (previewDiv) previewDiv.remove();
});
