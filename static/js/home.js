/**
 * 首页搜索：支持关键词 + 类型筛选，跳转到列表页并复用筛选逻辑
 */
(function () {
    var keywordEl = document.getElementById('homeSearchKeyword');
    var btn = document.getElementById('homeSearchBtn');
    var typeBtn = document.getElementById('homeSearchTypeBtn');
    var typeMenu = document.getElementById('homeSearchTypeMenu');
    var typeLabel = document.getElementById('homeSearchTypeLabel');
    var typeChevron = document.getElementById('homeSearchTypeChevron');
    var searchBar = document.getElementById('homeSearchBar');

    var currentType = '全部';

    function openMenu() {
        if (!typeMenu || !typeBtn) return;
        // Hero 容器有 overflow-hidden，避免被裁剪；把菜单升级为 fixed 定位
        var rect = typeBtn.getBoundingClientRect();
        typeMenu.style.position = 'fixed';
        typeMenu.style.top = (rect.bottom + 6) + 'px';
        typeMenu.style.left = rect.left + 'px';
        typeMenu.style.zIndex = '60';
        typeMenu.classList.remove('hidden');
        typeMenu.classList.add('is-open');
        if (typeChevron) typeChevron.classList.add('is-open');
    }

    function closeMenu() {
        if (!typeMenu) return;
        typeMenu.style.position = '';
        typeMenu.style.top = '';
        typeMenu.style.left = '';
        typeMenu.style.zIndex = '';
        typeMenu.classList.add('hidden');
        typeMenu.classList.remove('is-open');
        if (typeChevron) typeChevron.classList.remove('is-open');
    }

    function toggleMenu() {
        if (!typeMenu) return;
        if (typeMenu.classList.contains('hidden')) {
            openMenu();
        } else {
            closeMenu();
        }
    }

    function selectType(type) {
        currentType = type || '全部';
        if (typeLabel) typeLabel.textContent = currentType;
        if (typeMenu) {
            var items = typeMenu.querySelectorAll('.home-type-item');
            items.forEach(function (it) {
                if (it.getAttribute('data-type') === currentType) {
                    it.classList.add('active');
                } else {
                    it.classList.remove('active');
                }
            });
        }
        closeMenu();
    }

    function goSearch() {
        var keyword = keywordEl ? keywordEl.value.trim() : '';
        var url = '/list';
        var params = [];
        if (keyword) {
            params.push('q=' + encodeURIComponent(keyword));
        }
        if (currentType && currentType !== '全部') {
            params.push('type=' + encodeURIComponent(currentType));
        }
        if (params.length) {
            url += '?' + params.join('&');
        }
        window.location.href = url;
    }

    if (typeBtn) {
        typeBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleMenu();
        });
    }

    if (typeMenu) {
        typeMenu.addEventListener('click', function (e) {
            var item = e.target.closest('.home-type-item');
            if (!item) return;
            e.preventDefault();
            e.stopPropagation();
            selectType(item.getAttribute('data-type'));
        });
    }

    document.addEventListener('click', function (e) {
        if (!searchBar) return;
        if (!searchBar.contains(e.target)) {
            closeMenu();
        }
    });

    window.addEventListener('resize', function () {
        if (typeMenu && typeMenu.classList.contains('is-open')) {
            openMenu();
        }
    });

    if (btn) {
        btn.addEventListener('click', goSearch);
    }
    if (keywordEl) {
        keywordEl.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') goSearch();
        });
    }
})();

/**
 * 首页统计数据加载
 */
(function () {
    var statTotal = document.getElementById('statTotal');
    var statYear = document.getElementById('statYear');
    var statYearChange = document.getElementById('statYearChange');
    var statCities = document.getElementById('statCities');
    var statCitiesCount = document.getElementById('statCitiesCount');
    var statLatest = document.getElementById('statLatest');
    var statLatestNote = document.getElementById('statLatestNote');

    if (!statTotal) return;

    fetch('/api/stats/overview')
        .then(function (r) {
            if (!r.ok) throw new Error('请求失败');
            return r.json();
        })
        .then(function (res) {
            if (res.success && res.data) {
                var data = res.data;
                if (statTotal) statTotal.textContent = data.total || 0;
                if (statYear) statYear.textContent = data.yearly || 0;
                if (statYearChange) statYearChange.textContent = data.year_change || '较去年 --';
                if (statCities) statCities.textContent = data.cities || 0;
                if (statCitiesCount) statCitiesCount.textContent = '去过 ' + (data.cities || 0) + ' 个城市';
                if (statLatest) {
                    statLatest.textContent = data.latest_date || '--';
                }
                if (statLatestNote) {
                    statLatestNote.textContent = data.latest_date ? '最近入库日期' : '暂无记录';
                }
            } else {
                console.warn('获取统计数据失败:', res.message);
            }
        })
        .catch(function (err) {
            console.warn('获取统计数据异常:', err.message);
        });
})();

/**
 * 记忆提醒小部件
 */
(function () {
    var memoryDays = document.getElementById('memoryDays');
    var memoryTicketDate = document.getElementById('memoryTicketDate');
    var memoryTicketFrom = document.getElementById('memoryTicketFrom');
    var memoryTicketTo = document.getElementById('memoryTicketTo');
    var memoryTicketInfo = document.getElementById('memoryTicketInfo');
    var memoryTodayText = document.getElementById('memoryTodayText');
    var memoryTodayReminder = document.getElementById('memoryTodayReminder');
    var memoryTicketPreview = document.getElementById('memoryTicketPreview');
    var memoryCaption = document.getElementById('memoryCaption');

    if (!memoryDays) return;

    fetch('/api/memory/reminder')
        .then(function (r) {
            if (!r.ok) throw new Error('请求失败');
            return r.json();
        })
        .then(function (res) {
            if (res.success && res.data) {
                var data = res.data;

                // 更新收藏天数
                if (memoryDays) {
                    memoryDays.textContent = data.first_ticket ? (data.days_since_first || 0) : '--';
                }
                if (memoryTicketPreview) memoryTicketPreview.hidden = !data.first_ticket;
                if (memoryCaption) memoryCaption.textContent = data.first_ticket
                    ? '距离你第一次收藏票根已经' : '还没有收藏票根';
                if (memoryTodayText) memoryTodayText.textContent = '暂无去年今天的回忆';

                // 更新第一张票根预览
                if (data.first_ticket) {
                    var ticket = data.first_ticket;
                    if (memoryTicketDate) {
                        memoryTicketDate.textContent = ticket.time || '--';
                    }
                    if (memoryTicketFrom && memoryTicketTo) {
                        var place = ticket.place || '';
                        if (place.indexOf('→') !== -1) {
                            var parts = place.split('→');
                            memoryTicketFrom.textContent = parts[0].trim();
                            memoryTicketTo.textContent = parts[1].trim();
                        } else {
                            memoryTicketFrom.textContent = place;
                            memoryTicketTo.textContent = '';
                        }
                    }
                    if (memoryTicketInfo) {
                        var info = ticket.platform || ticket.type || '';
                        if (info) {
                            memoryTicketInfo.textContent = info;
                        } else {
                            memoryTicketInfo.textContent = '--';
                        }
                    }
                }

                // 更新今日回忆
                if (data.today_memory) {
                    var today = data.today_memory;
                    var from = today.from || '';
                    var to = today.to || '';
                    if (from && to) {
                        if (memoryTodayText) {
                            memoryTodayText.textContent = '去年今天的票据：「' + from + ' → ' + to + '」';
                        }
                    } else if (today.place) {
                        if (memoryTodayText) {
                            memoryTodayText.textContent = '去年今天的票据：「' + today.place + '」';
                        }
                    } else if (memoryTodayText) {
                        memoryTodayText.textContent = '去年今天的票据：' + (today.type || '票据');
                    }
                }
            }
        })
        .catch(function (err) {
            console.warn('获取记忆提醒数据异常:', err.message);
        });
})();
