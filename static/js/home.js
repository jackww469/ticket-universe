/**
 * 首页搜索：支持关键词，跳转到列表页并复用筛选逻辑
 */
(function () {
    var keywordEl = document.getElementById('homeSearchKeyword');
    var btn = document.getElementById('homeSearchBtn');

    function goSearch() {
        var keyword = keywordEl ? keywordEl.value.trim() : '';
        var url = '/list';
        if (keyword) {
            url += '?q=' + encodeURIComponent(keyword);
        }
        window.location.href = url;
    }

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
                    statLatestNote.textContent = data.latest_date ? '最新票据' : '暂无记录';
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
                    memoryDays.textContent = data.days_since_first || 0;
                }

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
                            memoryTodayText.textContent = '去年今天，你收藏了一张「' + from + ' → ' + to + '」车票';
                        }
                    } else if (today.place) {
                        if (memoryTodayText) {
                            memoryTodayText.textContent = '去年今天，你收藏了一张「' + today.place + '」票据';
                        }
                    }
                }
            }
        })
        .catch(function (err) {
            console.warn('获取记忆提醒数据异常:', err.message);
        });
})();
