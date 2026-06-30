(function() {
    var picker = document.getElementById('brand_color_picker');
    var text = document.getElementById('brand_color');
    var resetBtn = document.getElementById('brand_color_reset');
    var previews = document.getElementById('brand_previews');
    var darkSwatch = document.getElementById('preview_dark_swatch');
    var lightSwatch = document.getElementById('preview_light_swatch');
    var darkHex = document.getElementById('preview_dark_hex');
    var lightHex = document.getElementById('preview_light_hex');
    if (!picker || !text) return;

    function hexToHsl(hex) {
        var r = parseInt(hex.slice(1,3),16)/255, g = parseInt(hex.slice(3,5),16)/255, b = parseInt(hex.slice(5,7),16)/255;
        var max = Math.max(r,g,b), min = Math.min(r,g,b), l = (max+min)/2, h = 0, s = 0;
        if (max !== min) {
            var d = max - min;
            s = l > 0.5 ? d/(2-max-min) : d/(max+min);
            if (max===r)      h = (g-b)/d + (g<b?6:0);
            else if (max===g) h = (b-r)/d + 2;
            else              h = (r-g)/d + 4;
            h /= 6;
        }
        return [h, s, l];
    }

    function hslToHex(h, s, l) {
        if (s === 0) { var v = Math.round(l*255); return '#'+('0'+v.toString(16)).slice(-2).repeat(3); }
        function c(p, q, t) {
            t = ((t%1)+1)%1;
            if (t<1/6) return p+(q-p)*6*t;
            if (t<0.5) return q;
            if (t<2/3) return p+(q-p)*(2/3-t)*6;
            return p;
        }
        var q = l<0.5 ? l*(1+s) : l+s-l*s, p = 2*l-q;
        var r = Math.round(c(p,q,h+1/3)*255), g = Math.round(c(p,q,h)*255), b = Math.round(c(p,q,h-1/3)*255);
        return '#'+('0'+r.toString(16)).slice(-2)+('0'+g.toString(16)).slice(-2)+('0'+b.toString(16)).slice(-2);
    }

    function deriveLight(hex) {
        var hsl = hexToHsl(hex);
        return hslToHex(hsl[0], Math.min(hsl[1], 0.85), Math.min(hsl[2], 0.42));
    }

    function isHex(v) { return /^#[0-9a-fA-F]{6}$/.test(v); }

    function update(hex) {
        if (!isHex(hex)) return;
        var light = deriveLight(hex);
        darkSwatch.style.background = hex;
        lightSwatch.style.background = light;
        darkHex.textContent = hex;
        lightHex.textContent = light;
        previews.style.display = '';
    }

    picker.addEventListener('input', function() {
        text.value = picker.value;
        update(picker.value);
    });

    text.addEventListener('input', function() {
        var v = text.value.trim();
        if (isHex(v)) { picker.value = v; update(v); }
        else if (!v) { previews.style.display = 'none'; }
    });

    resetBtn.addEventListener('click', function() {
        text.value = '';
        picker.value = '#9aa7b4';
        previews.style.display = 'none';
    });

    if (isHex(text.value)) { picker.value = text.value; update(text.value); }
})();

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
                + '<button type="button" class="btn-small" id="icon-clear">Clear</button> '
                + '<button type="button" class="btn-small" id="icon-pick-btn">Change</button>';
        } else {
            currentEl.innerHTML = '<span id="icon-label" class="field-hint">None selected</span> '
                + '<button type="button" class="btn-small" id="icon-pick-btn">Choose icon…</button>';
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
