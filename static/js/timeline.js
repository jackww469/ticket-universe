/**
 * 时间轴日记重构版 - 基于样例页面样式
 * 左侧 320px 时间轴（年份折叠、月份筛选、搜索）
 * 右侧 70%+ 票根展示（日期徽章 + 主图 + 结构化信息 + 同月份缩略图）
 */
(function () {
    var loadingEl = document.getElementById('timelineLoading');
    var emptyEl = document.getElementById('timelineEmpty');
    var sidebarEl = document.getElementById('tl2Sidebar');
    var viewerEl = document.getElementById('tl2Viewer');
    var yearListEl = document.getElementById('tl2YearList');
    var monthFilterEl = document.getElementById('tl2MonthFilter');
    var searchInputEl = document.getElementById('tl2SearchInput');

        var noResultEl = document.getElementById('tl2SearchNoResult');
    var viewerEmptyEl = document.getElementById('tl2ViewerEmpty');
    var viewerCardEl = document.getElementById('tl2ViewerCard');
    var mainImageEl = document.getElementById('tl2MainImage');

    // Date badge elements
    var dateYearEl = document.getElementById('tl2DateYear');
    var dateMonthEl = document.getElementById('tl2DateMonth');
    var dateDayEl = document.getElementById('tl2DateDay');
    var dateWeekdayEl = document.getElementById('tl2DateWeekday');

    // Meta elements
    var metaGridEl = document.getElementById('tl2MetaGrid');

    // Notes elements
    var notesMetaEl = document.getElementById('tl2NotesMeta');
    var notesTextEl = document.getElementById('tl2NotesText');

    // Notes edit modal
    var notesModal = document.getElementById('tl2NotesModal');
    var notesBackdrop = document.getElementById('tl2NotesBackdrop');
    var notesClose = document.getElementById('tl2NotesClose');
    var notesCancel = document.getElementById('tl2NotesCancel');
    var notesSave = document.getElementById('tl2NotesSave');
    var notesTextarea = document.getElementById('tl2NotesTextarea');

    // Gallery elements
    var galleryEl = document.getElementById('tl2Gallery');
    var searchWrapEl = document.getElementById('tl2SearchWrap');
    var searchClearEl = document.getElementById('tl2SearchClear');
    var searchInfoEl = document.getElementById('tl2SearchInfo');

    var allData = [];
    var filteredData = [];
    var groups = {};
    var selectedId = null;
    var collapsedYears = {};
    var isSearchActive = false;

    var weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

    function esc(s) {
        if (s == null) return '';
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function highlightText(text, query) {
        if (!query || !text) return esc(text || '');
        var escaped = esc(text);
        var q = esc(query.trim());
        var regex = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        return escaped.replace(regex, '<mark style="background:#FDE8C8;color:#8B4513;padding:0 1px;border-radius:2px;">$1</mark>');
    }

    function parseDate(t) {
        if (!t) return { year: '未分类', month: '00', day: '' };
        var p = String(t).trim().split('-');
        var y = p[0] || '未分类';
        var m = p[1] || '00';
        var d = p[2] || '';
        return { year: y, month: m, day: d };
    }

    function getWeekday(dateStr) {
        if (!dateStr) return '';
        var parts = dateStr.split('-');
        if (parts.length < 3) return '';
        var date = new Date(parts[0], parseInt(parts[1]) - 1, parts[2]);
        return weekDays[date.getDay()];
    }

    function reGroup(data) {
        var g = {};
        data.forEach(function (item) {
            var d = parseDate(item.time);
            if (!g[d.year]) g[d.year] = {};
            if (!g[d.year][d.month]) g[d.year][d.month] = [];
            g[d.year][d.month].push(item);
        });
        return g;
    }

    function getTicketIcon(item) {
        if (item.type === '证书') return '🏅';
        if (item.type === '车票') return '🎫';
        if (item.type === '演出票') return '🎭';
        if (item.type === '景区票') return '🌿';
        return '🏷️';
    }

    function getTypeIcon(type) {
        var icons = {
            '车票': '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect height="14" rx="2" width="20" x="2" y="5"></rect><path d="M2 10h20"></path></svg>',
            '证书': '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>',
            '演出票': '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.382-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>',
            '景区票': '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M3 21v-4m18 4v-4M3 7l9-4 9 4M4 10h16v11H4V10z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>'
        };
        return icons[type] || '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>';
    }

    function extractField(text, pattern) {
        if (!text) return '';
        var m = String(text).match(pattern);
        return m ? m[1] : '';
    }

    function extractTrainNo(text) {
        return extractField(text, /\b([A-Z]?\d{2,5})\s*次?\b/i);
    }

    function extractSeat(text) {
        if (!text) return '';
        var m = String(text).match(/(?:座位?[：:]\s*)?(.+?)(?:车厢|号|$)/i);
        return m ? m[1].trim() : '';
    }

    function passFilter(item) {
        var q = (searchInputEl.value || '').trim().toLowerCase();
        var m = monthFilterEl.value || '';
        var dt = parseDate(item.time);
        if (m && dt.month !== m) return false;
        if (!q) return true;
        var blob = [
            item.type, item.platform, item.time, item.place, item.notes, item.ocr_text
        ].join(' ').toLowerCase();
        return blob.indexOf(q) >= 0;
    }

    function applyFilter() {
        filteredData = allData.filter(passFilter);
        groups = reGroup(filteredData);
        var q = (searchInputEl.value || '').trim();
        isSearchActive = !!q;

        if (searchWrapEl) {
            if (isSearchActive) {
                searchWrapEl.classList.add('has-value');
            } else {
                searchWrapEl.classList.remove('has-value');
            }
        }

        if (searchInfoEl) {
            if (isSearchActive) {
                searchInfoEl.classList.add('visible');
                if (filteredData.length === 0) {
                    searchInfoEl.textContent = '未找到匹配的票据';
                } else {
                    searchInfoEl.textContent = '找到 ' + filteredData.length + ' 条匹配的票据';
                }
            } else {
                searchInfoEl.classList.remove('visible');
                searchInfoEl.textContent = '';
            }
        }

        if (!filteredData.length) {
            selectedId = null;
            renderSidebar();
            renderViewer();
            return;
        }
        if (!selectedId || !filteredData.some(function (x) { return x.id === selectedId; })) {
            selectedId = filteredData[0].id;
        }
        renderSidebar();
        renderViewer();
    }

    function renderSidebar() {
        var years = Object.keys(groups).sort();
        if (!years.length) {
            yearListEl.innerHTML = '<div class="tl2-no-result">没有匹配的票根</div>';
            return;
        }
        var html = '<div class="tl2-vert-line"></div>';
        years.forEach(function (year) {
            var isCollapsed = !!collapsedYears[year];
            var months = Object.keys(groups[year]).sort();
            var yearTotal = 0;
            months.forEach(function (mm) { yearTotal += groups[year][mm].length; });
            html += '<div class="tl2-year ' + (isCollapsed ? 'is-collapsed' : '') + '" data-year="' + esc(year) + '">';
            html += '<div class="tl2-year-head">';
            html += '<div class="tl2-year-dot"></div>';
            html += '<div class="tl2-year-title">';
            html += '<h3 class="tl2-year-label">' + esc(year) + '年</h3>';
            html += '<span class="tl2-year-count">' + yearTotal + '</span>';
            html += '</div>';
            html += '</div>';
            html += '<div class="tl2-year-body">';
            months.forEach(function (month) {
                html += '<div class="tl2-month">';
                html += '<div class="tl2-month-head">';
                html += '<div class="tl2-month-dot"></div>';
                html += '<span class="tl2-month-label">' + esc(month) + '月</span>';
                html += '</div>';
                html += '<div class="tl2-ticket-list">';
                groups[year][month].forEach(function (item) {
                    var active = item.id === selectedId ? 'is-active' : '';
                    var q = (searchInputEl.value || '').trim();
                    var ticketText = '<span class="tl2-ticket-text">' + (isSearchActive
                        ? highlightText((item.type || '票据') + ' · ' + (item.time || ''), q)
                        : esc(item.type || '票据') + ' · ' + esc(item.time || '')) + '</span>';
                    html += '<div class="tl2-ticket ' + active + '" data-id="' + item.id + '">';
                    html += '<span class="tl2-ticket-icon">' + getTicketIcon(item) + '</span>';
                    html += ticketText;
                    html += '<svg class="tl2-ticket-arrow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"></path></svg>';
                    html += '</div>';
                });
                html += '</div></div>';
            });
            html += '</div></div>';
        });
        yearListEl.innerHTML = html;
    }

    function renderViewer() {
        if (!selectedId) {
            viewerEmptyEl.style.display = 'none';
            viewerCardEl.style.display = 'none';
            if (noResultEl) {
                noResultEl.style.display = 'flex';
            }
            return;
        }
        var item = filteredData.find(function (x) { return x.id === selectedId; });
        if (!item) {
            viewerEmptyEl.style.display = 'none';
            viewerCardEl.style.display = 'none';
            if (noResultEl) {
                noResultEl.style.display = 'flex';
            }
            return;
        }
        viewerEmptyEl.style.display = 'none';
        viewerCardEl.style.display = 'flex';
        if (noResultEl) {
            noResultEl.style.display = 'none';
        }

        // Update main image
        mainImageEl.src = item.image_url || '';
        mainImageEl.alt = (item.type || '票据') + ' ' + (item.time || '');

        // Update date badge
        var dt = parseDate(item.time);
        dateYearEl.textContent = dt.year || '----';
        dateMonthEl.textContent = dt.month || '--';
        dateDayEl.textContent = dt.day || '--';
        dateWeekdayEl.textContent = getWeekday(item.time);

        // Build meta grid
        var metaItems = [];
        metaItems.push({
            icon: getTypeIcon(item.type),
            label: '票据类型',
            value: item.type || '其他'
        });

        // Extract OCR info for train tickets
        var ocrText = item.ocr_text || item.notes || '';
        var fromStation = extractField(ocrText, /(?:出发|从|起)[：:]\s*([^\s,，]+(?:站)?)/i) || item.from_station || '';
        var toStation = extractField(ocrText, /(?:到达|至|终点)[：:]\s*([^\s,，]+(?:站)?)/i) || item.to_station || '';
        var trainTime = extractField(ocrText, /(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2})/i) || item.time || '';
        var trainNo = extractTrainNo(ocrText) || item.train_no || '';
        var seat = extractSeat(ocrText) || item.seat || '';

        if (fromStation) {
            metaItems.push({
                icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><circle cx="12" cy="10" r="3" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></circle></svg>',
                label: '出发站',
                value: fromStation
            });
        }
        if (toStation) {
            metaItems.push({
                icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><line x1="4" x2="4" y1="22" y2="15" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></line></svg>',
                label: '到达站',
                value: toStation
            });
        }
        if (trainTime) {
            metaItems.push({
                icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></circle><polyline points="12 6 12 12 16 14" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></polyline></svg>',
                label: '乘车时间',
                value: trainTime
            });
        }
        if (trainNo) {
            metaItems.push({
                icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect height="16" rx="2" width="16" x="4" y="4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></rect><path d="M4 10h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><path d="M10 4v16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><path d="M14 4v16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>',
                label: '车次',
                value: trainNo
            });
        }
        // Notes section (always shown if notes exist)
        if (item.notes) {
            metaItems.push({
                icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 13V7.5C19 5.01472 16.9853 3 14.5 3C12.0147 3 10 5.01472 10 7.5V13" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><path d="M5 13H19C20.1046 13 21 13.8954 21 15V19C21 20.1046 20.1046 21 19 21H5C3.89543 21 3 20.1046 3 19V15C3 13.8954 3.89543 13 5 13Z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>',
                label: '备注',
                value: item.notes
            });
        }

        // Add place if available and not already covered
        if (item.place && !fromStation && !toStation) {
            metaItems.push({
                icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><circle cx="12" cy="10" r="3" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></circle></svg>',
                label: '地点',
                value: item.place
            });
        }

        var metaHtml = '';
        metaItems.forEach(function (meta) {
            metaHtml += '<div class="tl2-meta-item">';
            metaHtml += '<div class="tl2-meta-icon">' + meta.icon + '</div>';
            metaHtml += '<div class="tl2-meta-body">';
            metaHtml += '<div class="tl2-meta-label">' + esc(meta.label) + '</div>';
            metaHtml += '<div class="tl2-meta-value">' + esc(meta.value) + '</div>';
            metaHtml += '</div></div>';
        });
        metaGridEl.innerHTML = metaHtml;

        // Update notes
        var notesMeta = item.time;
        if (item.place) {
            notesMeta += ' | ' + item.place;
        }
        if (item.type) {
            notesMeta += ' | ' + item.type;
        }
        notesMetaEl.textContent = notesMeta;
        notesTextEl.textContent = item.notes || item.ocr_text || '暂无备注';

        // Build gallery (same month tickets)
        var sameMonth = filteredData.filter(function (x) {
            var d = parseDate(x.time);
            return d.year === dt.year && d.month === dt.month;
        });

        var galleryHtml = '';
        sameMonth.forEach(function (x) {
            var active = x.id === selectedId ? 'is-active' : '';
            if (x.image_url) {
                galleryHtml += '<div class="tl2-gallery-thumb ' + active + '" data-id="' + x.id + '">';
                galleryHtml += '<img src="' + esc(x.image_url) + '" alt="">';
                galleryHtml += '</div>';
            }
        });
        galleryHtml += '<button class="tl2-gallery-add">';
        galleryHtml += '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 12h14"></path><path d="M12 5v14"></path></svg>';
        galleryHtml += '<span>添加票根</span>';
        galleryHtml += '</button>';

        galleryEl.innerHTML = galleryHtml;
    }

    function initMonthFilter(data) {
        var months = {};
        data.forEach(function (item) {
            var m = parseDate(item.time).month;
            if (m && m !== '00') months[m] = true;
        });
        var arr = Object.keys(months).sort();
        monthFilterEl.innerHTML = '<option value="">全部月份</option>' + arr.map(function (m) {
            return '<option value="' + m + '">' + m + '月</option>';
        }).join('');
    }

    function bindEvents() {
        // Sidebar ticket click
        yearListEl.addEventListener('click', function (e) {
            var ticket = e.target.closest('.tl2-ticket');
            if (ticket) {
                selectedId = Number(ticket.getAttribute('data-id'));
                renderSidebar();
                renderViewer();
                return;
            }

            var yearHead = e.target.closest('.tl2-year-head');
            if (yearHead) {
                var year = yearHead.closest('.tl2-year').getAttribute('data-year');
                collapsedYears[year] = !collapsedYears[year];
                renderSidebar();
            }
        });

        // Gallery thumbnail click & Add button (event delegation on galleryEl)
        galleryEl.addEventListener('click', function (e) {
            var thumb = e.target.closest('.tl2-gallery-thumb');
            if (thumb) {
                selectedId = Number(thumb.getAttribute('data-id'));
                renderSidebar();
                renderViewer();
                return;
            }
            var addBtn = e.target.closest('.tl2-gallery-add');
            if (addBtn) {
                window.location.href = '/upload';
            }
        });

        monthFilterEl.addEventListener('change', applyFilter);
        searchInputEl.addEventListener('input', function () {
            clearTimeout(window.__tlSearchTimer);
            window.__tlSearchTimer = setTimeout(applyFilter, 120);
        });
        if (searchClearEl) {
            searchClearEl.addEventListener('click', function () {
                searchInputEl.value = '';
                applyFilter();
                searchInputEl.focus();
            });
        }

        // Notes edit modal
        var editBtn = document.querySelector('.tl2-notes-edit-btn');
        if (editBtn && notesModal) {
            editBtn.addEventListener('click', function () {
                var item = filteredData.find(function (x) { return x.id === selectedId; });
                notesTextarea.value = item ? (item.notes || '') : '';
                notesModal.classList.add('is-open');
                notesTextarea.focus();
            });
        }
        function closeNotesModal() {
            notesModal.classList.remove('is-open');
        }
        if (notesBackdrop) notesBackdrop.addEventListener('click', closeNotesModal);
        if (notesClose) notesClose.addEventListener('click', closeNotesModal);
        if (notesCancel) notesCancel.addEventListener('click', closeNotesModal);
        if (notesSave) {
            notesSave.addEventListener('click', function () {
                var newNotes = notesTextarea.value;
                var item = filteredData.find(function (x) { return x.id === selectedId; });
                if (!item) return;
                notesSave.disabled = true;
                notesSave.textContent = '保存中...';
                fetch('/api/tickets/' + selectedId + '/notes', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ notes: newNotes })
                })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    notesSave.disabled = false;
                    notesSave.textContent = '保存';
                    if (res.success) {
                        item.notes = newNotes;
                        notesTextEl.textContent = newNotes || '暂无备注';
                        renderViewer();
                        closeNotesModal();
                    } else {
                        alert(res.message || '保存失败');
                    }
                })
                .catch(function () {
                    notesSave.disabled = false;
                    notesSave.textContent = '保存';
                    alert('保存失败，请重试');
                });
            });
        }
    }

    fetch('/api/tickets/timeline')
        .then(function (r) { return r.json(); })
        .then(function (res) {
            loadingEl.style.display = 'none';
            if (!res.success || !res.data || !res.data.length) {
                emptyEl.style.display = 'flex';
                return;
            }
            emptyEl.style.display = 'none';
            sidebarEl.style.display = 'flex';
            viewerEl.style.display = 'flex';

            allData = (res.data || []).slice().sort(function (a, b) {
                return String(a.time || '').localeCompare(String(b.time || ''));
            });
            initMonthFilter(allData);
            bindEvents();
            applyFilter();
        })
        .catch(function () {
            loadingEl.style.display = 'none';
            emptyEl.style.display = 'flex';
        });
})();
