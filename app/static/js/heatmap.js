(function () {
    var dataEl = document.getElementById('heatmap-data');
    var root = document.getElementById('heatmap-root');
    if (!dataEl || !root) return;

    const DATA = JSON.parse(dataEl.textContent);

    const CELL = 11;
    const GAP = 2;
    const STEP = CELL + GAP;
    const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const monthStart = new Date(today.getFullYear(), today.getMonth() - 11, 1);
    const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0);

    const gridStart = new Date(monthStart);
    gridStart.setDate(monthStart.getDate() - monthStart.getDay());
    const gridEnd = new Date(monthEnd);
    gridEnd.setDate(monthEnd.getDate() + (6 - monthEnd.getDay()));

    const WEEKS = Math.ceil((gridEnd - gridStart) / (7 * 24 * 60 * 60 * 1000));

    const outer = document.createElement('div');
    outer.className = 'heatmap-outer';

    const dayCol = document.createElement('div');
    dayCol.className = 'heatmap-day-labels';
    ['', '', 'Mon', '', 'Wed', '', 'Fri', ''].forEach(t => {
        const s = document.createElement('span');
        s.textContent = t;
        dayCol.appendChild(s);
    });
    outer.appendChild(dayCol);

    const scrollWrap = document.createElement('div');
    scrollWrap.className = 'heatmap-scroll';

    const monthRow = document.createElement('div');
    monthRow.className = 'heatmap-months';

    const grid = document.createElement('div');
    grid.className = 'heatmap-grid';

    const monthPositions = [];
    let lastMonth = -1;

    for (let w = 0; w < WEEKS; w++) {
        for (let d = 0; d < 7; d++) {
            const date = new Date(gridStart);
            date.setDate(gridStart.getDate() + w * 7 + d);

            if (d === 0 && date.getMonth() !== lastMonth) {
                lastMonth = date.getMonth();
                if (date >= monthStart) {
                    monthPositions.push({ col: w, label: MONTH_NAMES[date.getMonth()] });
                }
            }

            const dateStr = date.toISOString().slice(0, 10);
            const entries = DATA[dateStr] || [];
            const count = entries.length;
            const future = date > today;

            const cell = document.createElement('div');
            cell.className = 'heatmap-cell';
            if (!future) {
                const level = count === 0 ? 0 : count <= 2 ? 1 : count <= 5 ? 2 : 3;
                cell.dataset.level = level;
                if (count > 0) {
                    cell.dataset.date = dateStr;
                    cell.dataset.entries = JSON.stringify(entries);
                }
            } else {
                cell.dataset.future = '1';
            }
            grid.appendChild(cell);
        }
    }

    monthPositions.forEach(({ col, label }) => {
        const span = document.createElement('span');
        span.textContent = label;
        span.style.left = (col * STEP) + 'px';
        monthRow.appendChild(span);
    });

    scrollWrap.appendChild(monthRow);
    scrollWrap.appendChild(grid);
    outer.appendChild(scrollWrap);
    root.appendChild(outer);

    const tip = document.createElement('div');
    tip.className = 'heatmap-tip';
    tip.style.display = 'none';
    document.body.appendChild(tip);

    let hideTimer = null;

    function showTip(cell) {
        clearTimeout(hideTimer);
        const entries = JSON.parse(cell.dataset.entries);
        const [y, m, d] = cell.dataset.date.split('-').map(Number);
        const dateLabel = new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

        tip.innerHTML =
            '<div class="heatmap-tip-date">' + dateLabel + '</div>' +
            '<ul class="heatmap-tip-list">' +
            entries.map(e =>
                '<li><a href="/' + e.slug + '/">' + e.title + '</a>' +
                (e.is_new ? ' <span class="heatmap-tip-new">new</span>' : '') +
                (e.changelog ? '<span class="heatmap-tip-log"> — ' + e.changelog + '</span>' : '') +
                '</li>'
            ).join('') +
            '</ul>';

        tip.style.display = 'block';
        const r = cell.getBoundingClientRect();
        const tw = tip.offsetWidth, th = tip.offsetHeight;
        let left = r.left + r.width / 2 - tw / 2;
        let top = r.top - th - 8;
        if (top < 8) top = r.bottom + 8;
        left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
        tip.style.left = left + 'px';
        tip.style.top = (top + window.scrollY) + 'px';
    }

    function hideTip() {
        hideTimer = setTimeout(() => { tip.style.display = 'none'; }, 400);
    }

    grid.addEventListener('mouseover', e => {
        const cell = e.target.closest('.heatmap-cell[data-entries]');
        if (cell) showTip(cell);
    });
    grid.addEventListener('mouseleave', hideTip);
    tip.addEventListener('mouseenter', () => clearTimeout(hideTimer));
    tip.addEventListener('mouseleave', hideTip);
})();
