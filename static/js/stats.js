/**
 * 年度统计页
 */
(function () {
    var totalTicketsEl = document.getElementById('totalTickets');
    var totalCitiesEl = document.getElementById('totalCities');
    var totalYearsEl = document.getElementById('totalYears');
    var citiesChangeEl = document.getElementById('citiesChange');
    var yearsChangeEl = document.getElementById('yearsChange');
    var chartBars = document.getElementById('chartBars');
    var currentYearTitle = document.getElementById('currentYearTitle');
    var monthGrid = document.getElementById('monthGrid');
    var typeDonutSegments = document.getElementById('typeDonutSegments');
    var typeTotalCountEl = document.getElementById('typeTotalCount');
    var typeList = document.getElementById('typeList');
    var placeList = document.getElementById('placeList');

    // 年度下拉菜单
    var yearBtn = document.getElementById('yearDropdownBtn');
    var yearMenu = document.getElementById('yearDropdownMenu');
    var yearLabel = document.getElementById('yearDropdownLabel');
    var statusEl = document.getElementById('statsStatus');

    var stats = {};
    var requestId = 0;

    // 类型配色（与图例保持一致）
    var typeColors = {
        '车票': '#1f2937',
        '演出票': '#7B61FF',
        '景区票': '#228B22',
        '证书': '#C9A227',
        '其他': '#e11d48'
    };
    var defaultTypeColor = '#965a38';

    function esc(s) {
        if (s == null) return '';
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function renderOverview() {
        if (totalTicketsEl) totalTicketsEl.textContent = stats.total_tickets || 0;
        if (totalCitiesEl) totalCitiesEl.textContent = stats.total_cities != null ? stats.total_cities : 0;

        var years = stats.years_current || 0;
        if (totalYearsEl) totalYearsEl.textContent = years;

        // 城市变化（所选年份 vs 上一年）
        var citiesThis = stats.cities_current_year || 0;
        var citiesLast = stats.cities_last_year || 0;
        if (citiesChangeEl) {
            var diff = citiesThis - citiesLast;
            var txt;
            if (citiesLast === 0 && citiesThis === 0) {
                txt = '<span class="mx-1">--</span>';
                citiesChangeEl.className = 'text-xs text-gray-400 font-medium';
            } else if (diff > 0) {
                txt = '较上一年 <span class="mx-1">+' + diff + '</span>';
                citiesChangeEl.className = 'text-xs text-green-500 font-medium';
            } else if (diff < 0) {
                txt = '较上一年 <span class="mx-1">' + diff + '</span>';
                citiesChangeEl.className = 'text-xs text-red-500 font-medium';
            } else {
                txt = '较上一年 <span class="mx-1">持平</span>';
                citiesChangeEl.className = 'text-xs text-gray-400 font-medium';
            }
            citiesChangeEl.innerHTML = txt;
        }

        // 年份涵盖变化
        if (yearsChangeEl) {
            var yDiff = (stats.years_current || 0) - (stats.years_last || 0);
            var yTxt;
            if ((stats.years_last || 0) === 0 && (stats.years_current || 0) === 0) {
                yTxt = '较上一年 <span class="mx-1">--</span>';
                yearsChangeEl.className = 'text-xs text-gray-400 font-medium';
            } else if (yDiff > 0) {
                yTxt = '较上一年 <span class="mx-1">+' + yDiff + '</span>';
                yearsChangeEl.className = 'text-xs text-green-500 font-medium';
            } else if (yDiff < 0) {
                yTxt = '较上一年 <span class="mx-1">' + yDiff + '</span>';
                yearsChangeEl.className = 'text-xs text-red-500 font-medium';
            } else {
                yTxt = '较上一年 <span class="mx-1">持平</span>';
                yearsChangeEl.className = 'text-xs text-gray-400 font-medium';
            }
            yearsChangeEl.innerHTML = yTxt;
        }
    }

    function renderYearlyChart() {
        if (!chartBars) return;
        if (!stats.yearly_counts || !stats.yearly_counts.length) {
            chartBars.innerHTML = '<div class="empty-hint text-gray-400 text-sm">暂无年度数据</div>';
            return;
        }

        // 显示倒序前若干年（按年份倒序，新的在上）
        var data = stats.yearly_counts.slice(0, 10);
        // 但绘图时按年份升序排列，从左到右由旧到新
        data.sort(function (a, b) { return parseInt(a.year) - parseInt(b.year); });

        var maxCount = Math.max.apply(null, data.map(function (d) { return d.count; })) || 1;

        var html = '';
        data.forEach(function (item) {
            var pct = (item.count / maxCount) * 100;
            var color = getBarColor(item.year);
            var highlight = (String(item.year) === String(stats.selected_year));

            html += '<div class="stats-bar-wrap">';
            html += '<span class="stats-bar-value">' + item.count + '</span>';
            html += '<div class="stats-bar-track">';
            html += '<div class="stats-bar ' + (highlight ? 'stats-bar--highlight' : '') + '" ';
            html += 'style="height:' + Math.max(pct, 12) + '%;background:' + color + ';" ';
            html += 'title="' + item.year + '年: ' + item.count + '张"></div>';
            html += '</div>';
            html += '<span class="stats-bar-label">' + esc(item.year) + '</span>';
            html += '</div>';
        });

        chartBars.innerHTML = html;
    }

    function getBarColor(year) {
        // 所选年使用棕色，最近一年使用绿色。
        if (String(year) === String(stats.selected_year)) return '#7a4528';
        var years = (stats.yearly_counts || []).slice().sort(function (a, b) { return parseInt(b.year) - parseInt(a.year); });
        if (years.length && String(year) === String(years[0].year)) return '#16a34a';
        return '#eab308';
    }

    function renderMonthlyChart() {
        if (!monthGrid) return;
        var monthNames = ['1月', '2月', '3月', '4月', '5月', '6月',
            '7月', '8月', '9月', '10月', '11月', '12月'];

        if (currentYearTitle) currentYearTitle.textContent = stats.selected_year || '今年';

        var monthlyMap = {};
        (stats.monthly_counts || []).forEach(function (m) {
            monthlyMap[m.month] = m.count;
        });

        var counts = [];
        for (var i = 1; i <= 12; i++) {
            var month = String(i).padStart(2, '0');
            counts.push(monthlyMap[month] || 0);
        }
        var maxCount = Math.max.apply(null, counts) || 1;

        var html = '';
        for (var j = 1; j <= 12; j++) {
            var month = String(j).padStart(2, '0');
            var count = counts[j - 1];
            var pct = maxCount > 0 ? (count / maxCount) * 100 : 0;

            html += '<div class="stats-month-wrap">';
            html += '<span class="stats-month-value">' + (count > 0 ? count : '') + '</span>';
            html += '<div class="stats-month-track">';
            html += '<div class="stats-month-bar ' + (count > 0 ? '' : 'stats-month-bar--empty') + '" ';
            html += 'style="height:' + Math.max(pct, 4) + '%;" ';
            html += 'title="' + monthNames[j - 1] + ': ' + count + '张"></div>';
            html += '</div>';
            html += '<span class="stats-month-label">' + monthNames[j - 1] + '</span>';
            html += '<span class="stats-month-count">' + count + '</span>';
            html += '</div>';
        }

        monthGrid.innerHTML = html;
    }

    function renderTypeSection() {
        if (!typeList) return;
        var types = stats.type_counts || [];
        if (!types.length) {
            if (typeTotalCountEl) typeTotalCountEl.textContent = '0';
            typeList.innerHTML = '<div class="empty-hint text-gray-400 text-sm">暂无类型数据</div>';
            if (typeDonutSegments) typeDonutSegments.innerHTML = '';
            return;
        }

        var total = types.reduce(function (sum, t) { return sum + t.count; }, 0);
        if (typeTotalCountEl) typeTotalCountEl.textContent = total;

        // 渲染环形图分段（使用 path 圆弧绘制，平滑的圆弧段）
        if (typeDonutSegments) {
            var cx = 18;
            var cy = 18;
            var r = 15.91549430918954;
            var startAngle = -90; // 从 12 点方向开始
            var segmentsHtml = '';

            types.forEach(function (item) {
                var pct = total > 0 ? (item.count / total) * 100 : 0;
                if (pct <= 0) return;
                if (pct >= 100) pct = 99.999; // 满圆不能闭合为 0
                var color = typeColors[item.type] || defaultTypeColor;

                var angle = (pct / 100) * 360;
                var endAngle = startAngle + angle;

                var startRad = (startAngle * Math.PI) / 180;
                var endRad = (endAngle * Math.PI) / 180;

                var x1 = cx + r * Math.cos(startRad);
                var y1 = cy + r * Math.sin(startRad);
                var x2 = cx + r * Math.cos(endRad);
                var y2 = cy + r * Math.sin(endRad);

                // large-arc-flag: 角度 > 180° 时为 1
                var largeArc = angle > 180 ? 1 : 0;

                segmentsHtml += '<path '
                    + 'd="M ' + cx + ' ' + cy
                    + ' L ' + x1.toFixed(3) + ' ' + y1.toFixed(3)
                    + ' A ' + r + ' ' + r + ' 0 ' + largeArc + ' 1 ' + x2.toFixed(3) + ' ' + y2.toFixed(3)
                    + ' Z" '
                    + 'fill="' + color + '" '
                    + 'stroke="' + color + '" '
                    + 'stroke-width="0.5" />';

                startAngle = endAngle;
            });
            typeDonutSegments.innerHTML = segmentsHtml;
        }

        // 渲染图例
        var html = '';
        types.forEach(function (item) {
            var pct = total > 0 ? (item.count / total * 100).toFixed(1) : 0;
            var color = typeColors[item.type] || defaultTypeColor;
            html += '<div class="stats-type-row">';
            html += '<div class="flex items-center gap-2">';
            html += '<span class="inline-block w-3 h-3 rounded-full" style="background:' + color + '"></span>';
            html += '<span class="text-sm text-gray-600">' + esc(item.type) + '</span>';
            html += '</div>';
            html += '<span class="text-sm font-medium text-gray-800">' + item.count + '张 (' + pct + '%)</span>';
            html += '</div>';
        });
        typeList.innerHTML = html;
    }

    function renderPlaceList() {
        if (!placeList) return;
        var places = stats.top_places || [];
        if (!places.length) {
            placeList.innerHTML = '<div class="empty-hint text-gray-400 text-sm">暂无地点数据</div>';
            return;
        }

        var maxCount = places[0].count || 1;
        var rankColors = ['#eab308', '#9ca3af', '#b45309'];
        var html = '';
        places.forEach(function (item, idx) {
            var rank = idx + 1;
            var rankStyle = '';
            var rankTextColor = '#fff';
            if (rank === 1) rankStyle = 'background:#eab308;color:#fff;';
            else if (rank === 2) rankStyle = 'background:#d1d5db;color:#fff;';
            else if (rank === 3) rankStyle = 'background:#b45309;color:#fff;';
            else rankStyle = 'background:#f3f4f6;color:#6b7280;';

            html += '<div class="stats-place-row">';
            html += '<div class="stats-place-rank" style="' + rankStyle + '">' + rank + '</div>';
            html += '<span class="stats-place-name">' + esc(item.place) + '</span>';
            html += '<span class="stats-place-count">' + item.count + '次</span>';
            html += '</div>';
        });

        placeList.innerHTML = html;
    }

    function renderAll() {
        renderOverview();
        renderYearlyChart();
        renderMonthlyChart();
        renderTypeSection();
        renderPlaceList();
    }

    // 下拉菜单
    function toggleMenu() {
        if (!yearMenu) return;
        yearMenu.classList.toggle('hidden');
        if (yearBtn) yearBtn.setAttribute('aria-expanded', String(!yearMenu.classList.contains('hidden')));
    }

    function closeMenu() {
        if (!yearMenu) return;
        yearMenu.classList.add('hidden');
        if (yearBtn) yearBtn.setAttribute('aria-expanded', 'false');
    }

    function selectYear(year) {
        closeMenu();
        // 切换年度：重新拉取该年度数据
        loadStats(year);
    }

    if (yearBtn) {
        yearBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleMenu();
        });
    }

    if (yearMenu) {
        yearMenu.addEventListener('click', function (e) {
            var item = e.target.closest('.year-dropdown-item');
            if (!item) return;
            e.preventDefault();
            e.stopPropagation();
            selectYear(item.getAttribute('data-year'));
        });
    }

    document.addEventListener('click', function () {
        closeMenu();
    });

    function loadStats(year) {
        // 只接受最新一次选择的结果，避免快速切换时旧请求覆盖新年份。
        var activeRequest = ++requestId;
        if (statusEl) statusEl.textContent = '正在加载' + (year || '') + '年度数据…';
        var url = '/api/stats/yearly' + (year ? '?year=' + encodeURIComponent(year) : '');
        fetch(url).then(function (r) {
            if (!r.ok) throw new Error('统计请求失败');
            return r.json();
        }).then(function (res) {
            if (activeRequest !== requestId) return;
            if (!res.success || !res.data) throw new Error(res.message || '统计请求失败');
            stats = res.data;
            if (yearLabel && stats.selected_year) yearLabel.textContent = stats.selected_year;
            var items = yearMenu ? yearMenu.querySelectorAll('.year-dropdown-item') : [];
            items.forEach(function (it) {
                it.classList.toggle('active', it.getAttribute('data-year') === stats.selected_year);
            });
            renderAll();
            if (statusEl) statusEl.textContent = stats.total_tickets ? '' : '所选年份暂无票据';
        }).catch(function (err) {
            if (activeRequest !== requestId) return;
            console.warn('加载统计数据失败:', err);
            if (statusEl) statusEl.textContent = '加载失败，请重新选择年份重试。' +
                (stats.selected_year ? '当前仍显示 ' + stats.selected_year + ' 年数据。' : '');
        });
    }

    // 首次加载
    loadStats();
})();
