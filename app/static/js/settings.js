(function() {
    var toggle = document.getElementById('multiuser_enabled');
    var options = document.getElementById('multiuser-options');
    if (!toggle || !options) return;
    function update() {
        if (toggle.checked) {
            options.classList.remove('settings-disabled');
            options.querySelectorAll('input, select').forEach(function(el) { el.disabled = false; });
        } else {
            options.classList.add('settings-disabled');
            options.querySelectorAll('input, select').forEach(function(el) { el.disabled = true; });
        }
    }
    toggle.addEventListener('change', update);
})();

// Warn before turning groups off (or multi-user off, which forces groups off)
// while entries are restricted to groups — doing so re-exposes them under normal
// visibility rules.
(function() {
    var groups = document.getElementById('groups_enabled');
    var multiuser = document.getElementById('multiuser_enabled');
    var form = groups && groups.closest('form');
    if (!groups || !form) return;
    var wasEnabled = groups.checked;
    var count = parseInt(groups.getAttribute('data-grouped-count'), 10) || 0;
    form.addEventListener('submit', function(e) {
        var nowEnabled = groups.checked && (!multiuser || multiuser.checked);
        if (wasEnabled && !nowEnabled && count > 0) {
            var msg = count + ' ' + (count === 1 ? 'entry is' : 'entries are')
                + ' restricted to groups and will become visible under normal rules. Continue?';
            if (!window.confirm(msg)) e.preventDefault();
        }
    });
})();

(function() {
    var dataEl = document.getElementById('icon-names-data');
    if (!dataEl) return;
    var icons = JSON.parse(dataEl.textContent);
    var input = document.getElementById('site_icon');
    var pickBtn = document.getElementById('icon-pick-btn');
    var picker = document.getElementById('icon-picker');
    var grid = document.getElementById('icon-grid');
    var search = document.getElementById('icon-search');
    var clearBtn = document.getElementById('icon-clear');
    var currentEl = document.querySelector('.icon-picker-current');
    var countEl = document.getElementById('icon-count');
    if (!pickBtn || !picker) return;

    var BATCH = 200;
    var filtered = [];
    var rendered = 0;

    function selectIcon(name) {
        input.value = name;
        updateCurrent(name);
        picker.style.display = 'none';
    }

    function makeBtn(name) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'icon-picker-item' + (name === input.value ? ' icon-picker-selected' : '');
        btn.title = name;
        btn.innerHTML = '<i class="bi bi-' + name + '"></i>';
        btn.addEventListener('click', function() { selectIcon(name); });
        return btn;
    }

    function renderBatch() {
        var end = Math.min(rendered + BATCH, filtered.length);
        var frag = document.createDocumentFragment();
        for (var i = rendered; i < end; i++) frag.appendChild(makeBtn(filtered[i]));
        grid.appendChild(frag);
        rendered = end;
    }

    function renderGrid(filter) {
        grid.innerHTML = '';
        var q = (filter || '').toLowerCase();
        filtered = q ? icons.filter(function(n) { return n.indexOf(q) !== -1; }) : icons;
        rendered = 0;
        renderBatch();
        countEl.textContent = filtered.length + ' icons';
    }

    grid.addEventListener('scroll', function() {
        if (rendered < filtered.length && grid.scrollTop + grid.clientHeight >= grid.scrollHeight - 40) {
            renderBatch();
        }
    });

    function updateCurrent(name) {
        if (name) {
            currentEl.innerHTML = '<i class="bi bi-' + name + '" id="icon-preview"></i> '
                + '<span id="icon-label">' + name + '</span> '
                + '<button type="button" class="btn btn-xs" id="icon-clear">Clear</button> '
                + '<button type="button" class="btn btn-primary btn-xs" id="icon-pick-btn">Change</button>';
        } else {
            currentEl.innerHTML = '<span id="icon-label" class="field-hint">None selected</span> '
                + '<button type="button" class="btn btn-primary btn-xs" id="icon-pick-btn">Choose icon…</button>';
        }
        document.getElementById('icon-pick-btn').addEventListener('click', togglePicker);
        var cb = document.getElementById('icon-clear');
        if (cb) cb.addEventListener('click', function() { input.value = ''; updateCurrent(''); });
    }

    function togglePicker() {
        if (picker.style.display === 'none') {
            picker.style.display = '';
            renderGrid('');
            search.value = '';
            search.focus();
        } else {
            picker.style.display = 'none';
        }
    }

    pickBtn.addEventListener('click', togglePicker);
    if (clearBtn) clearBtn.addEventListener('click', function() { input.value = ''; updateCurrent(''); });
    var debounce;
    search.addEventListener('input', function() {
        clearTimeout(debounce);
        debounce = setTimeout(function() { renderGrid(search.value); }, 150);
    });
})();
