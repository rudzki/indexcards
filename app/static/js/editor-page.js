(function() {
    var title = document.getElementById('title');
    var slug = document.getElementById('slug');
    if (!title || !slug || slug.dataset.isNew !== 'true') return;
    var manual = false;
    function makeSlug(s) {
        return s.toLowerCase().trim()
            .replace(/[^\w\s-]/g, '')
            .replace(/[\s_]+/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-+|-+$/g, '');
    }
    title.addEventListener('input', function() {
        if (!manual) slug.value = makeSlug(title.value);
    });
    slug.addEventListener('input', function() { manual = true; });
    slug.addEventListener('blur', function() {
        if (!slug.value.trim()) { manual = false; slug.value = makeSlug(title.value); }
    });
})();

(function() {
    var showInNav = document.getElementById('show_in_nav');
    var navPositionField = document.getElementById('nav_position_field');
    var navPosition = document.getElementById('nav_position');
    if (!showInNav || !navPositionField) return;
    showInNav.addEventListener('change', function() {
        navPositionField.style.display = showInNav.checked ? '' : 'none';
        if (!showInNav.checked && navPosition) navPosition.value = '';
    });
})();

(function() {
    var btn = document.getElementById('slug-copy-btn');
    var slugInput = document.getElementById('slug');
    var prefixEl = document.querySelector('.slug-prefix');
    if (btn && slugInput) {
        btn.addEventListener('click', function() {
            var prefix = prefixEl ? prefixEl.textContent : (window.location.origin + '/');
            var slug = slugInput.value.trim();
            var url = prefix + slug + '/';
            var icon = btn.querySelector('i');
            function showCheck() {
                if (icon) { icon.className = 'bi bi-check'; setTimeout(function() { icon.className = 'bi bi-clipboard'; }, 1500); }
            }
            if (navigator.clipboard) {
                navigator.clipboard.writeText(url).then(showCheck).catch(function() {
                    fallbackCopy(url); showCheck();
                });
            } else {
                fallbackCopy(url); showCheck();
            }
        });
    }
    function fallbackCopy(text) {
        var ta = document.createElement('textarea');
        ta.value = text; ta.style.cssText = 'position:fixed;opacity:0';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); } catch (e) {}
        document.body.removeChild(ta);
    }
})();

(function() {
    var searchInput = document.getElementById('parent_search');
    var hiddenInput = document.getElementById('parent_id');
    if (!searchInput || !hiddenInput) return;

    var dropdown = null;
    var debounceTimer = null;
    var creating = false;

    function createDropdown() {
        if (dropdown) return;
        dropdown = document.createElement('div');
        dropdown.className = 'parent-dropdown';
        searchInput.parentNode.appendChild(dropdown);
    }

    function removeDropdown() {
        if (dropdown) { dropdown.remove(); dropdown = null; }
    }

    function selectResult(item) {
        searchInput.value = item.title;
        hiddenInput.value = item.id;
        removeDropdown();
    }

    function quickCreate(title) {
        if (creating) return;
        creating = true;
        fetch('/api/entries/quick-create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ title: title }),
        })
            .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
            .then(function(res) {
                creating = false;
                if (!res.ok) {
                    if (window.showToast) showToast('error', res.data.error || 'Could not create entry.');
                    return;
                }
                selectResult(res.data);
            })
            .catch(function() {
                creating = false;
                if (window.showToast) showToast('error', 'Could not create entry.');
            });
    }

    function renderResults(results, q) {
        createDropdown();
        dropdown.innerHTML = '';
        results.forEach(function(item) {
            var div = document.createElement('div');
            div.className = 'parent-result';
            div.textContent = item.title;
            div.addEventListener('mousedown', function(e) {
                e.preventDefault();
                selectResult(item);
            });
            dropdown.appendChild(div);
        });

        var exactMatch = results.some(function(item) {
            return item.title.toLowerCase() === q.toLowerCase();
        });
        if (q && !exactMatch) {
            var createDiv = document.createElement('div');
            createDiv.className = 'parent-result parent-result-create';
            createDiv.textContent = 'Create new entry: "' + q + '"';
            createDiv.addEventListener('mousedown', function(e) {
                e.preventDefault();
                quickCreate(q);
            });
            dropdown.appendChild(createDiv);
        }

        if (!dropdown.children.length) removeDropdown();
    }

    function runSearch(q) {
        fetch('/api/entries/search?q=' + encodeURIComponent(q))
            .then(function(r) { return r.json(); })
            .then(function(results) { renderResults(results, q); });
    }

    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        hiddenInput.value = '';
        var q = searchInput.value.trim();
        debounceTimer = setTimeout(function() { runSearch(q); }, 200);
    });

    searchInput.addEventListener('focus', function() {
        if (dropdown) return;
        runSearch(searchInput.value.trim());
    });

    searchInput.addEventListener('blur', function() {
        setTimeout(removeDropdown, 200);
    });

    searchInput.addEventListener('keydown', function(e) {
        if (!dropdown) return;
        var items = dropdown.querySelectorAll('.parent-result');
        var active = dropdown.querySelector('.parent-result.selected');
        var idx = Array.from(items).indexOf(active);
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (active) active.classList.remove('selected');
            items[(idx + 1) % items.length].classList.add('selected');
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (active) active.classList.remove('selected');
            items[(idx - 1 + items.length) % items.length].classList.add('selected');
        } else if (e.key === 'Enter' && active) {
            e.preventDefault();
            active.dispatchEvent(new MouseEvent('mousedown'));
        } else if (e.key === 'Escape') {
            removeDropdown();
        }
    });
})();

(function() {
    var form = document.querySelector('.editor-form');
    if (!form || !form.dataset.lockType || !form.dataset.lockId) return;
    var LOCK_URL = '/api/lock/' + form.dataset.lockType + '/' + form.dataset.lockId;
    var heartbeat = setInterval(function() {
        fetch(LOCK_URL, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken() },
        });
    }, 30000);
    var releaseBody = function() { return new URLSearchParams({ csrf_token: csrfToken() }); };
    form.addEventListener('submit', function() {
        clearInterval(heartbeat);
        navigator.sendBeacon(LOCK_URL + '/release', releaseBody());
    });
    window.addEventListener('pagehide', function() {
        clearInterval(heartbeat);
        navigator.sendBeacon(LOCK_URL + '/release', releaseBody());
    });
})();
